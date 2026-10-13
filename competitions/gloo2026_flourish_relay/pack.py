"""Deterministic source bundle builder/verifier for FlourishRelay."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile

FIXED_TIME = (2020, 1, 1, 0, 0, 0)
MANIFEST = "MANIFEST.json"
IGNORED_PARTS = {"__pycache__", ".pytest_cache", ".git"}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".zip"}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def collect(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if any(part in IGNORED_PARTS for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise ValueError(f"symlink forbidden: {rel}")
        if not path.is_file() or path.suffix in IGNORED_SUFFIXES or rel == MANIFEST:
            continue
        if not _safe_name(rel):
            raise ValueError(f"unsafe path: {rel}")
        files[rel] = path.read_bytes()
    if not files:
        raise ValueError("no source files")
    return files


def build(root: Path, output: Path) -> dict:
    files = collect(root)
    manifest = {
        "schema": "flourish-relay-source-bundle.v1",
        "files": [{"path": name, "sha256": _digest(data), "size": len(data)} for name, data in sorted(files.items())],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            zf.writestr(info, data)
        info = zipfile.ZipInfo(MANIFEST, FIXED_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        zf.writestr(info, _canonical(manifest))
    return {"archive_sha256": _digest(output.read_bytes()), "manifest_sha256": _digest(_canonical(manifest)), **manifest}


def verify(path: Path) -> dict:
    raw = path.read_bytes()
    with zipfile.ZipFile(path, "r") as zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise ValueError("duplicate zip member")
        if MANIFEST not in names:
            raise ValueError("manifest missing")
        for info in infos:
            if not _safe_name(info.filename):
                raise ValueError("unsafe zip member")
            mode = (info.external_attr >> 16) & 0o170000
            if mode not in {0, stat.S_IFREG}:
                raise ValueError("non-regular zip member")
            if info.file_size > 2_000_000:
                raise ValueError("member exceeds bound")
        manifest = json.loads(zf.read(MANIFEST))
        if manifest.get("schema") != "flourish-relay-source-bundle.v1" or not isinstance(manifest.get("files"), list):
            raise ValueError("manifest schema invalid")
        rows = manifest["files"]
        expected = {row.get("path") for row in rows}
        if len(expected) != len(rows) or None in expected:
            raise ValueError("duplicate/invalid manifest paths")
        if set(names) != expected | {MANIFEST}:
            raise ValueError("archive membership mismatch")
        for row in rows:
            name = row["path"]
            data = zf.read(name)
            if row.get("size") != len(data) or row.get("sha256") != _digest(data):
                raise ValueError(f"content mismatch: {name}")
    return {
        "verified": True,
        "archive_sha256": _digest(raw),
        "manifest_sha256": _digest(_canonical(manifest)),
        "file_count": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("root", type=Path)
    b.add_argument("output", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("archive", type=Path)
    args = parser.parse_args()
    result = build(args.root, args.output) if args.cmd == "build" else verify(args.archive)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
