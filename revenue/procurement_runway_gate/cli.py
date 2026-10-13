from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .engine import GateError, canonical_json_bytes, compile_gate, make_receipt, verify_bundle

MAX_INPUT_BYTES = 10 * 1024 * 1024


def _reject_constant(value: str) -> Any:
    raise GateError(f"non-finite JSON constant rejected: {value}")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateError(f"duplicate JSON key rejected: {key}")
        out[key] = value
    return out


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise GateError("input must be a regular file")
        if before.st_size <= 0 or before.st_size > MAX_INPUT_BYTES:
            raise GateError("input size invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise GateError("input changed during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise GateError("input grew during read")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise GateError("input changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _load_json(path: Path) -> Any:
    raw = _read_regular(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateError("input must be UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise GateError(f"invalid JSON: {exc.msg}") from exc


def _write_new(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OSError("short write")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _compile(input_path: Path, output_dir: Path) -> None:
    raw = _load_json(input_path)
    output = compile_gate(raw)
    receipt = make_receipt(output)
    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    _write_new(output_dir / "runway.json", canonical_json_bytes(output))
    _write_new(output_dir / "receipt.json", canonical_json_bytes(receipt))


def _verify(input_path: Path, output_dir: Path) -> None:
    raw = _load_json(input_path)
    output = _load_json(output_dir / "runway.json")
    receipt = _load_json(output_dir / "receipt.json")
    verify_bundle(raw, output, receipt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic procurement runway + partner-capacity gate")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        p = sub.add_parser(name)
        p.add_argument("input", type=Path)
        p.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            _compile(args.input, args.output_dir)
        else:
            _verify(args.input, args.output_dir)
    except (GateError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
