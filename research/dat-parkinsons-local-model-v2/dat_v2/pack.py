"""Whitelist-only deterministic submission bundle packer and verifier."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .contract import FEATURE_VERSION, RUNTIME_COMMIT, ModelContractError, canonical_json
from .io import load_model_json, parse_json_strict

PACKAGE_FILES = (
    "__init__.py",
    "artifact.py",
    "contract.py",
    "core.py",
    "features.py",
    "io.py",
    "training.py",
)
TEMPLATE_FILES = ("main.py", "model_backend.py")
MANIFEST_NAME = "bundle_manifest.json"
FIXED_ZIP_TIME = (2026, 9, 14, 0, 0, 0)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _member_bytes(model_path: Path, source_root: Path) -> tuple[dict[str, bytes], dict]:
    model = load_model_json(model_path)
    members: dict[str, bytes] = {}
    template = source_root / "submission_template"
    package = source_root / "dat_v2"
    for name in TEMPLATE_FILES:
        members[name] = (template / name).read_bytes()
    for name in PACKAGE_FILES:
        members[f"dat_v2/{name}"] = (package / name).read_bytes()
    members["model.json"] = (canonical_json(model) + "\n").encode("utf-8")
    manifest = {
        "schema": "dat-parkinsons-local-model-v2/bundle-v1",
        "runtime_commit": RUNTIME_COMMIT,
        "feature_version": FEATURE_VERSION,
        "model_sha256": model["model_sha256"],
        "members": {name: _sha256(data) for name, data in sorted(members.items())},
        "privacy_contract": {
            "whitelist_only": True,
            "contains_training_rows": False,
            "contains_training_manifest": False,
            "contains_oof_predictions": False,
        },
    }
    return members, manifest


def build_bundle(model_path: Path, output_zip: Path, *, source_root: Path | None = None) -> dict:
    """Build a deterministic whitelist-only runtime bundle from one validated local model."""
    root = Path(source_root) if source_root is not None else _source_root()
    members, manifest = _member_bytes(Path(model_path), root)
    destination = Path(output_zip)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite submission bundle: {destination}")
    with destination.open("xb") as raw:
        with zipfile.ZipFile(raw, mode="w") as archive:
            for name, data in sorted(members.items()):
                archive.writestr(_zip_info(name), data)
            archive.writestr(_zip_info(MANIFEST_NAME), (canonical_json(manifest) + "\n").encode("utf-8"))
    return manifest


def verify_bundle(path: Path) -> dict:
    """Fail closed unless the archive is exactly the expected public-source/model whitelist."""
    source = Path(path)
    if not source.is_file():
        raise ModelContractError("bundle is not a regular file")
    with zipfile.ZipFile(source, mode="r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ModelContractError("bundle contains duplicate member names")
        expected = {"main.py", "model_backend.py", "model.json", MANIFEST_NAME}
        expected.update(f"dat_v2/{name}" for name in PACKAGE_FILES)
        if set(names) != expected:
            raise ModelContractError("bundle member whitelist mismatch")
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise ModelContractError("bundle contains unsafe member path")
        manifest_raw = archive.read(MANIFEST_NAME).decode("utf-8")
        manifest = parse_json_strict(manifest_raw)
        if not isinstance(manifest, dict):
            raise ModelContractError("bundle manifest must be an object")
        if set(manifest) != {"schema", "runtime_commit", "feature_version", "model_sha256", "members", "privacy_contract"}:
            raise ModelContractError("bundle manifest fields mismatch")
        if manifest.get("schema") != "dat-parkinsons-local-model-v2/bundle-v1":
            raise ModelContractError("bundle schema mismatch")
        if manifest.get("runtime_commit") != RUNTIME_COMMIT or manifest.get("feature_version") != FEATURE_VERSION:
            raise ModelContractError("bundle runtime/feature contract mismatch")
        privacy = manifest.get("privacy_contract")
        if privacy != {
            "whitelist_only": True,
            "contains_training_rows": False,
            "contains_training_manifest": False,
            "contains_oof_predictions": False,
        }:
            raise ModelContractError("bundle privacy contract mismatch")
        member_hashes = manifest.get("members")
        if not isinstance(member_hashes, dict) or set(member_hashes) != expected - {MANIFEST_NAME}:
            raise ModelContractError("bundle hash manifest mismatch")
        for name in sorted(member_hashes):
            if member_hashes[name] != _sha256(archive.read(name)):
                raise ModelContractError(f"bundle member hash mismatch: {name}")
        model_obj = parse_json_strict(archive.read("model.json").decode("utf-8"))
        if not isinstance(model_obj, dict):
            raise ModelContractError("bundled model must be an object")
        from .artifact import validate_model_artifact
        validate_model_artifact(model_obj)
        if model_obj["model_sha256"] != manifest.get("model_sha256"):
            raise ModelContractError("bundle model digest mismatch")
        return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or verify a DaT V2 submission bundle")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("model", type=Path)
    build.add_argument("output", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        manifest = build_bundle(args.model, args.output)
    else:
        manifest = verify_bundle(args.bundle)
    print(canonical_json({
        "schema": manifest["schema"],
        "runtime_commit": manifest["runtime_commit"],
        "feature_version": manifest["feature_version"],
        "model_sha256": manifest["model_sha256"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
