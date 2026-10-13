"""Deterministic, fail-closed competition submission packager and verifier."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

_SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}"),
]
_NETWORK_PATTERNS = [
    re.compile(rb"(?m)^\s*(?:import|from)\s+(?:requests|httpx|urllib|socket|aiohttp)\b"),
    re.compile(rb"\b(?:requests|httpx|urllib\.request)\.(?:get|post|request)\s*\("),
]
_ALLOWED_SUFFIXES = {".py", ".json", ".txt", ".model", ".bin", ".pt", ".safetensors", ".tiktoken", ".npz", ".npy"}


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def scan_source(root: Path, *, max_bytes: int | None = None) -> list[tuple[str, bytes]]:
    if not root.is_dir():
        raise ValueError("submission source must be a directory")
    members: list[tuple[str, bytes]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_symlink():
            raise ValueError(f"symlink forbidden: {rel}")
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in rel.parts):
            raise ValueError(f"hidden path forbidden: {rel}")
        if path.suffix not in _ALLOWED_SUFFIXES:
            raise ValueError(f"unapproved file type: {rel}")
        mode = path.stat().st_mode
        if mode & (stat.S_ISUID | stat.S_ISGID):
            raise ValueError(f"privileged mode bits forbidden: {rel}")
        data = path.read_bytes()
        total += len(data)
        if max_bytes is not None and total > max_bytes:
            raise ValueError("operator submission-size ceiling exceeded")
        for pattern in _SECRET_PATTERNS:
            if pattern.search(data):
                raise ValueError(f"secret-like material found: {rel}")
        if path.suffix == ".py":
            for pattern in _NETWORK_PATTERNS:
                if pattern.search(data):
                    raise ValueError(f"network-capable code found: {rel}")
        posix = PurePosixPath(*rel.parts).as_posix()
        if posix.startswith("/") or ".." in PurePosixPath(posix).parts:
            raise ValueError(f"unsafe member path: {rel}")
        members.append((posix, data))
    names = {name for name, _ in members}
    if "main.py" not in names:
        raise ValueError("submission root must contain main.py")
    return members


def build_zip(root: Path, output: Path, *, max_bytes: int | None = None) -> dict:
    members = scan_source(root, max_bytes=max_bytes)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in members:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    blob = output.read_bytes()
    receipt = {
        "format": 1,
        "archive_sha256": _sha(blob),
        "archive_bytes": len(blob),
        "members": [{"path": name, "bytes": len(data), "sha256": _sha(data)} for name, data in members],
    }
    receipt_bytes = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    receipt["receipt_sha256"] = _sha(receipt_bytes)
    return receipt


def verify_zip(archive_path: Path, receipt: dict) -> None:
    blob = archive_path.read_bytes()
    if _sha(blob) != receipt["archive_sha256"] or len(blob) != receipt["archive_bytes"]:
        raise ValueError("archive digest/size mismatch")
    expected = {m["path"]: m for m in receipt["members"]}
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("archive member set mismatch")
        for info in archive.infolist():
            pure = PurePosixPath(info.filename)
            if info.filename.startswith("/") or ".." in pure.parts:
                raise ValueError("unsafe archive member")
            data = archive.read(info)
            exp = expected[info.filename]
            if len(data) != exp["bytes"] or _sha(data) != exp["sha256"]:
                raise ValueError(f"member mismatch: {info.filename}")
    if "main.py" not in expected:
        raise ValueError("root main.py missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int)
    args = parser.parse_args()
    receipt = build_zip(args.source, args.output, max_bytes=args.max_bytes)
    args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    verify_zip(args.output, receipt)
    print(f"PASS {receipt['archive_sha256']} {receipt['archive_bytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
