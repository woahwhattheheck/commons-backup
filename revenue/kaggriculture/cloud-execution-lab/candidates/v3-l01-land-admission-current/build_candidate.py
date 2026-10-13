#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build baseline and LAND candidates from the exact current TITAN archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

# Hook the single construction boundary rather than individual call sites. The
# deadline-aware entrypoint can reconstruct an agent from multiple branches;
# wrapping the constructor return covers every fresh instance while preserving
# those control-flow and fallback paths byte-for-byte.
ENTRYPOINT_NEEDLE = (
    "    return FinalPressureAgent(features, fourth_quadrant_admission=admission)\n"
)
ENTRYPOINT_REPLACEMENT = (
    "    from land_admission import wrap as _wrap_land_admission\n"
    "    return _wrap_land_admission(\n"
    "        FinalPressureAgent(features, fourth_quadrant_admission=admission)\n"
    "    )\n"
)
SOURCE_MEMBER = "SOURCE.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def extracted_inventory(root: Path) -> dict[str, Any]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    embedded = [
        path for path in files
        if path.relative_to(root).as_posix() == SOURCE_MEMBER
    ]
    if len(embedded) != 1:
        raise ValueError(
            f"expected exactly one root {SOURCE_MEMBER}, found {len(embedded)}"
        )
    return {
        "regular_files": len(files),
        "runtime_files": len(files) - 1,
        "embedded_source_sha256": sha256(embedded[0]),
        "embedded_source_bytes": embedded[0].stat().st_size,
    }


def safe_extract(archive: Path, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        seen: set[str] = set()
        regular: list[tarfile.TarInfo] = []
        embedded: list[tarfile.TarInfo] = []
        for member in members:
            relative = PurePosixPath(member.name)
            if not member.name or relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"archive path is unsafe: {member.name!r}")
            normalized = relative.as_posix()
            if normalized in seen:
                raise ValueError(f"duplicate archive member: {normalized!r}")
            seen.add(normalized)
            if member.issym() or member.islnk():
                raise ValueError(f"archive link is forbidden: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported archive member: {member.name!r}")
            target = (root.joinpath(*relative.parts)).resolve()
            try:
                target.relative_to(root)
            except ValueError as error:
                raise ValueError(
                    f"archive path escapes destination: {member.name!r}"
                ) from error
            if member.isfile():
                regular.append(member)
                if normalized == SOURCE_MEMBER:
                    embedded.append(member)

        if len(embedded) != 1:
            raise ValueError(
                f"expected exactly one root {SOURCE_MEMBER}, found {len(embedded)}"
            )
        source_stream = handle.extractfile(embedded[0])
        if source_stream is None:
            raise ValueError(f"cannot read embedded {SOURCE_MEMBER}")
        source_bytes = source_stream.read()
        handle.extractall(destination, members=members, filter="data")

    inventory = extracted_inventory(destination)
    if inventory["regular_files"] != len(regular):
        raise ValueError("archive extraction changed the regular-file cardinality")
    if inventory["embedded_source_sha256"] != hashlib.sha256(source_bytes).hexdigest():
        raise ValueError("archive extraction changed embedded SOURCE.json bytes")
    return inventory


def patch_entrypoint(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    count = source.count(ENTRYPOINT_NEEDLE)
    if count != 1:
        raise ValueError(
            "expected exactly one current constructor hook site, "
            f"found {count}"
        )
    patched = source.replace(ENTRYPOINT_NEEDLE, ENTRYPOINT_REPLACEMENT, 1)
    compile(patched, str(path), "exec")
    before = hashlib.sha256(source.encode("utf-8")).hexdigest()
    after = hashlib.sha256(patched.encode("utf-8")).hexdigest()
    path.write_text(patched, encoding="utf-8")
    return {
        "insertion_count": 1,
        "hook_surface": "_new_instance.return",
        "baseline_main_sha256": before,
        "candidate_main_sha256": after,
    }


def build(lab_root: Path, output_root: Path, mechanism: Path) -> dict[str, Any]:
    lab_root = lab_root.resolve()
    output_root = output_root.resolve()
    mechanism = mechanism.resolve()

    manifest_path = lab_root / "runtime/integrated-selected/CURRENT-ARCHIVE.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive = lab_root / manifest["path"]
    source_manifest = lab_root / manifest["source_manifest"]

    actual_archive_sha = sha256(archive)
    if actual_archive_sha != manifest["sha256"]:
        raise ValueError(
            f"current archive hash mismatch: {actual_archive_sha} "
            f"!= {manifest['sha256']}"
        )
    if archive.stat().st_size != int(manifest["bytes"]):
        raise ValueError("current archive byte count does not match manifest")
    actual_source_sha = sha256(source_manifest)
    if actual_source_sha != manifest["source_manifest_sha256"]:
        raise ValueError(
            f"source manifest hash mismatch: {actual_source_sha} "
            f"!= {manifest['source_manifest_sha256']}"
        )

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    baseline = output_root / "baseline"
    candidate = output_root / "land"
    baseline_inventory = safe_extract(archive, baseline)
    if baseline_inventory["embedded_source_sha256"] != actual_source_sha:
        raise ValueError(
            "embedded source manifest mismatch: "
            f"{baseline_inventory['embedded_source_sha256']} != {actual_source_sha}"
        )
    if baseline_inventory["runtime_files"] != int(manifest["runtime_files"]):
        raise ValueError(
            "archive runtime file count mismatch: "
            f"{baseline_inventory['runtime_files']} "
            f"!= {manifest['runtime_files']}"
        )
    shutil.copytree(baseline, candidate)

    baseline_main = baseline / "main.py"
    candidate_main = candidate / "main.py"
    if not baseline_main.is_file() or not candidate_main.is_file():
        raise FileNotFoundError("archive did not contain main.py")

    mechanism_target = candidate / "land_admission.py"
    shutil.copyfile(mechanism, mechanism_target)
    compile(
        mechanism_target.read_text(encoding="utf-8"),
        str(mechanism_target),
        "exec",
    )
    patch = patch_entrypoint(candidate_main)
    candidate_inventory = extracted_inventory(candidate)
    if candidate_inventory["embedded_source_sha256"] != actual_source_sha:
        raise ValueError("candidate changed embedded source manifest bytes")
    if candidate_inventory["runtime_files"] != baseline_inventory["runtime_files"] + 1:
        raise ValueError("candidate did not add exactly one runtime file")

    receipt = {
        "schema": "titan-v3-land-admission-build-v1",
        "archive_manifest": str(manifest_path.relative_to(lab_root)),
        "archive_path": str(archive.relative_to(lab_root)),
        "archive_sha256": actual_archive_sha,
        "archive_bytes": archive.stat().st_size,
        "source_manifest": str(source_manifest.relative_to(lab_root)),
        "source_manifest_sha256": actual_source_sha,
        "embedded_source_sha256": baseline_inventory["embedded_source_sha256"],
        "embedded_source_bytes": baseline_inventory["embedded_source_bytes"],
        "entrypoint": manifest["entrypoint"],
        "baseline_regular_files": baseline_inventory["regular_files"],
        "baseline_runtime_files": baseline_inventory["runtime_files"],
        "candidate_regular_files": candidate_inventory["regular_files"],
        "candidate_runtime_files": candidate_inventory["runtime_files"],
        "baseline_tree_sha256": tree_digest(baseline),
        "candidate_tree_sha256": tree_digest(candidate),
        "mechanism_source_sha256": sha256(mechanism),
        "mechanism_installed_sha256": sha256(mechanism_target),
        **patch,
    }
    if receipt["mechanism_source_sha256"] != receipt["mechanism_installed_sha256"]:
        raise ValueError("mechanism copy was not byte exact")
    (output_root / "BUILD.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--mechanism",
        type=Path,
        default=Path(__file__).with_name("land_admission.py"),
    )
    args = parser.parse_args()
    receipt = build(args.lab_root, args.output_root, args.mechanism)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
