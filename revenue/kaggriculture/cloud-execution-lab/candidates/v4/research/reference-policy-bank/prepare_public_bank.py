#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recover COK V10 + lonespear v18 into the existing V4 reference-policy bank.

This is a publication-recovery tool, not a new evaluator or policy. It rebuilds
from immutable GitHub Actions artifacts and the already-landed public_bank
loader, preserving upstream policy bytes and branch semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from typing import Any

SCHEMA = "titan.v4.reforge.public-bank.v1"
SOURCEPACK_ARTIFACT_ID = 10030763484
SOURCEPACK_SHA256 = "68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62"
INTAKE_ARTIFACT_ID = 10032525998
INTAKE_SHA256 = "6601d709ffa3cd17d994228869ba770a7189bb9b69467cca07ff40e8e6023da5"
BANK_GIT_BLOB = "063b87dca064a8c673a6dd8839e6714abe46c4d4"
INTAKE_GIT_BLOB = "ee8a90bb8f8ba135ef4d5e8056289ae32eed1c48"
EXPECTED_SOURCE_SHA256 = {
    "cok-v10": "56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109",
    "lonespear-v18": "eb5b5f59a8ec2d40b77cc99d4ffe3b932136fdcf9f6b6e168726b7f07ab47cb0",
}
FAMILY = {
    "cok-v10": "cok-v10",
    "lonespear-v18-greedy": "lonespear-v18",
    "lonespear-v18-scipy": "lonespear-v18",
}


class RecoveryError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _safe_rel(name: str) -> PurePosixPath:
    if (not name or name.startswith("./") or "//" in name or "/./" in name
            or name.endswith("/.")):
        raise RecoveryError(f"unsafe archive member: {name!r}")
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        raise RecoveryError(f"unsafe archive member: {name!r}")
    return p


def extract_zip_safe(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            rel = _safe_rel(info.filename.rstrip("/"))
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise RecoveryError(f"zip symlink forbidden: {info.filename}")
            target = destination.joinpath(*rel.parts)
            target.resolve().relative_to(destination.resolve())
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def extract_tar_safe(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tf:
        for member in tf.getmembers():
            rel = _safe_rel(member.name.rstrip("/"))
            if member.issym() or member.islnk():
                raise RecoveryError(f"tar link forbidden: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise RecoveryError(f"tar special member forbidden: {member.name}")
            target = destination.joinpath(*rel.parts)
            target.resolve().relative_to(destination.resolve())
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = tf.extractfile(member)
            if source is None:
                raise RecoveryError(f"cannot read tar member: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as dst:
                shutil.copyfileobj(source, dst)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RecoveryError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p)
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def verify_runtime(root: Path, caller_frozen_manifest_sha256: str) -> dict[str, Any]:
    root = root.resolve(strict=True)
    manifest_path = root / "REFORGE-BANK.json"
    if sha256_file(manifest_path) != caller_frozen_manifest_sha256:
        raise RecoveryError("caller-frozen REFORGE manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise RecoveryError("unknown REFORGE bank schema")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RecoveryError("empty REFORGE runtime closure")
    for rel, expected in files.items():
        path = root / rel
        path.resolve(strict=True).relative_to(root)
        if path.is_symlink() or not path.is_file() or sha256_file(path) != expected:
            raise RecoveryError(f"runtime file mismatch: {rel}")
    bank = json.loads((root / "BANK.json").read_text(encoding="utf-8"))
    if set(bank.get("entries", {})) != set(FAMILY):
        raise RecoveryError("bank entry set changed")
    for identity, family in FAMILY.items():
        if manifest["entries"][identity]["family"] != family:
            raise RecoveryError(f"family identity changed: {identity}")
        source_rel = bank["entries"][identity]["source"]
        if sha256_file(root / source_rel) != bank["entries"][identity]["source_sha256"]:
            raise RecoveryError(f"entry source changed: {identity}")
    return manifest


def prepare(sourcepack_zip: Path, intake_zip: Path, bank_code: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    if sha256_file(sourcepack_zip) != SOURCEPACK_SHA256:
        raise RecoveryError("sourcepack artifact ZIP hash mismatch")
    if sha256_file(intake_zip) != INTAKE_SHA256:
        raise RecoveryError("intake artifact ZIP hash mismatch")
    bank_py, intake_py = bank_code / "bank.py", bank_code / "intake.py"
    if git_blob(bank_py) != BANK_GIT_BLOB or git_blob(intake_py) != INTAKE_GIT_BLOB:
        raise RecoveryError("public_bank code pins changed")

    with tempfile.TemporaryDirectory(prefix="reforge-recovery-") as td:
        temp = Path(td)
        sourcepack = temp / "sourcepack"
        sources = temp / "sources"
        tree = temp / "tree"
        extract_zip_safe(sourcepack_zip, sourcepack)
        extract_zip_safe(intake_zip, sources)
        reusable = sourcepack / "titan-reusable-sources.tar"
        if not reusable.is_file():
            raise RecoveryError("sourcepack missing titan-reusable-sources.tar")
        extract_tar_safe(reusable, tree)
        kg_root = tree / "revenue/kaggriculture"
        pack = kg_root / "cloud-pack"
        if not (pack / "official.py").is_file():
            raise RecoveryError("sourcepack missing cloud-pack closure")

        old_path = list(sys.path)
        try:
            sys.path.insert(0, str(bank_code.resolve()))
            intake = _load(intake_py, "reforge_public_bank_intake")
            manifest = intake.verify(sources)
            sys.modules["intake"] = intake
            bank = _load(bank_py, "reforge_public_bank_loader")
            output.mkdir(parents=True)
            bank_root = output / "bank"
            bank_manifest = bank.prepare(sources, pack, bank_root, include_scipy=True)
        finally:
            sys.path[:] = old_path
            sys.modules.pop("intake", None)

        for source_id, expected in EXPECTED_SOURCE_SHA256.items():
            row = manifest["opponents"][source_id]
            if sha256_file(sources / source_id / row["entry"]) != expected:
                raise RecoveryError(f"public source hash mismatch: {source_id}")
        if bank_manifest.get("source_policy_changes") is not False:
            raise RecoveryError("bank reports source-policy mutation")
        entries = {}
        for identity, family in FAMILY.items():
            row = dict(bank_manifest["entries"][identity])
            row["family"] = family
            row["entry"] = f"bank/{identity}.py"
            entries[identity] = row
        result = {
            "schema": SCHEMA,
            "artifacts": {
                "sourcepack": {"id": SOURCEPACK_ARTIFACT_ID, "sha256": SOURCEPACK_SHA256},
                "intake": {"id": INTAKE_ARTIFACT_ID, "sha256": INTAKE_SHA256},
            },
            "public_bank_code": {"bank.py_git_blob": BANK_GIT_BLOB,
                                 "intake.py_git_blob": INTAKE_GIT_BLOB},
            "entries": entries,
            "families": {
                "cok-v10": ["cok-v10"],
                "lonespear-v18": ["lonespear-v18-greedy", "lonespear-v18-scipy"],
            },
            "source_policy_changes": False,
            "branch_semantics": "existing public_bank.make_agent; greedy/SciPy are one source family",
            "consumer": "Use generated entry path with existing cloud-eval.Actor/BASALT bridge; fresh instance per actor/game.",
            "files": _files(bank_root),
        }
        (bank_root / "REFORGE-BANK.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                                       encoding="utf-8")
        return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sourcepack-zip", type=Path, required=True)
    p.add_argument("--intake-zip", type=Path, required=True)
    p.add_argument("--bank-code", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = prepare(args.sourcepack_zip, args.intake_zip, args.bank_code, args.output)
        frozen = sha256_file(args.output / "bank" / "REFORGE-BANK.json")
        verify_runtime(args.output / "bank", frozen)
    except (OSError, KeyError, RecoveryError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(f"REFORGE BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "manifest_sha256": frozen,
                      "entries": sorted(result["entries"]), "families": result["families"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
