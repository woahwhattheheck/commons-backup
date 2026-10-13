#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a deterministic land-74/98 candidate from the exact current TITAN archive."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

HERE = Path(__file__).resolve().parent
BASE_ARCHIVE_SHA256 = "a055fd56ca5821208096f37787f77dbdddc2f65c14c24132d6e219a05e6f02ba"
BASE_MAIN_SHA256 = "0dae922de836cdb590891d9bbca9a58e18114ebcc64e16fb5b264311f07133e5"
BASE_CONFIG_SHA256 = "6096a8f120d79aa1e9fae1aab64e2135de483fb11961ab5062708f7dc9c92b12"
REVISION = "current-land-74-98-cow-v1"
INJECTED = ("canonical_main.py", "land_overlay.py", "LAND-74-98.json")


@dataclass(frozen=True)
class SourceMember:
    data: bytes
    mode: int


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: str) -> str:
    candidate = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise ValueError(f"unsafe archive member: {name!r}")
    normalized = candidate.as_posix()
    if normalized in ("", "."):
        raise ValueError(f"unsafe archive member: {name!r}")
    return normalized


def read_archive(path: Path) -> dict[str, SourceMember]:
    members: dict[str, SourceMember] = {}
    with tarfile.open(path, "r:gz") as archive:
        for info in archive.getmembers():
            name = _safe_name(info.name)
            if info.isdir():
                continue
            if not info.isfile():
                raise ValueError(f"unsupported archive member type: {info.name!r}")
            if name in members:
                raise ValueError(f"duplicate archive member: {name}")
            handle = archive.extractfile(info)
            if handle is None:
                raise ValueError(f"unreadable archive member: {name}")
            members[name] = SourceMember(handle.read(), info.mode & 0o777)
    return members


def _tar_bytes(files: dict[str, SourceMember]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        directories: set[str] = set()
        for name in files:
            parent = PurePosixPath(name).parent
            while parent.as_posix() not in (".", ""):
                directories.add(parent.as_posix())
                parent = parent.parent
        for directory in sorted(directories):
            info = tarfile.TarInfo(directory)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            archive.addfile(info)
        for name in sorted(files):
            member = files[name]
            info = tarfile.TarInfo(name)
            info.size = len(member.data)
            info.mode = member.mode or 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            archive.addfile(info, io.BytesIO(member.data))
    return raw.getvalue()


def _gzip_bytes(raw_tar: bytes) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0, compresslevel=9) as zipped:
        zipped.write(raw_tar)
    return out.getvalue()


def build_candidate(
    base_archive: Path,
    output: Path,
    *,
    expected_archive_sha256: str = BASE_ARCHIVE_SHA256,
    expected_main_sha256: str = BASE_MAIN_SHA256,
    expected_config_sha256: str = BASE_CONFIG_SHA256,
) -> dict:
    base_bytes = base_archive.read_bytes()
    actual_base_sha = sha256(base_bytes)
    if actual_base_sha != expected_archive_sha256:
        raise ValueError(
            f"base archive SHA-256 mismatch: expected {expected_archive_sha256}, got {actual_base_sha}"
        )
    files = read_archive(base_archive)
    if "main.py" not in files or "TITAN-CONFIG.json" not in files:
        raise ValueError("base archive must contain main.py and TITAN-CONFIG.json")
    if sha256(files["main.py"].data) != expected_main_sha256:
        raise ValueError("base main.py SHA-256 mismatch")
    if sha256(files["TITAN-CONFIG.json"].data) != expected_config_sha256:
        raise ValueError("base TITAN-CONFIG.json SHA-256 mismatch")
    for name in INJECTED:
        if name in files:
            raise ValueError(f"base archive already contains reserved member {name}")

    overlay_main = (HERE / "overlay" / "main.py").read_bytes()
    overlay_logic = (HERE / "overlay" / "land_overlay.py").read_bytes()
    original_main = files["main.py"].data
    original_names = set(files)
    original_hashes = {name: sha256(member.data) for name, member in files.items()}

    files["canonical_main.py"] = SourceMember(original_main, files["main.py"].mode)
    files["main.py"] = SourceMember(overlay_main, 0o644)
    files["land_overlay.py"] = SourceMember(overlay_logic, 0o644)
    internal = {
        "schema": 1,
        "revision": REVISION,
        "policy_delta": {"operation": "BUY_LAND", "steps": [74, 98], "mode": "append-if-room"},
        "base": {
            "archive_sha256": actual_base_sha,
            "main_sha256": expected_main_sha256,
            "config_sha256": expected_config_sha256,
            "members": len(original_names),
        },
        "injected": {
            "main.py": sha256(overlay_main),
            "canonical_main.py": sha256(original_main),
            "land_overlay.py": sha256(overlay_logic),
        },
        "unchanged_member_hashes_sha256": sha256(
            json.dumps(original_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
    }
    internal_bytes = (json.dumps(internal, sort_keys=True, indent=2) + "\n").encode("utf-8")
    files["LAND-74-98.json"] = SourceMember(internal_bytes, 0o644)

    candidate_bytes = _gzip_bytes(_tar_bytes(files))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate_bytes)

    changed = sorted(
        name for name in original_names if sha256(files[name].data) != original_hashes[name]
    )
    added = sorted(set(files) - original_names)
    sidecar = {
        "schema": 1,
        "revision": REVISION,
        "base_archive": str(base_archive),
        "base_archive_sha256": actual_base_sha,
        "candidate_archive": str(output),
        "candidate_archive_sha256": sha256(candidate_bytes),
        "candidate_bytes": len(candidate_bytes),
        "member_count": len(files),
        "changed_existing_members": changed,
        "added_members": added,
        "entrypoint": "main.py::agent",
    }
    sidecar_path = output.with_suffix(output.suffix + ".manifest.json")
    sidecar_path.write_text(json.dumps(sidecar, sort_keys=True, indent=2) + "\n")
    return sidecar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_candidate(args.base, args.output)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
