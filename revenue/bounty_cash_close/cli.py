from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import CloseBoardError, canonical_json_bytes, compile_board, verify_bundle

MAX_INPUT_BYTES = 10 * 1024 * 1024


def _reject_constant(value: str) -> Any:
    raise CloseBoardError(f"non-finite JSON constant rejected: {value}")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CloseBoardError(f"duplicate JSON key rejected: {key}")
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
            raise CloseBoardError("input must be a regular file")
        if before.st_size <= 0 or before.st_size > MAX_INPUT_BYTES:
            raise CloseBoardError("input size invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise CloseBoardError("input changed during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise CloseBoardError("input grew during read")
        after = os.fstat(fd)
        identity_before = (
            before.st_mode, before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns,
        )
        identity_after = (
            after.st_mode, after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns,
        )
        if identity_before != identity_after:
            raise CloseBoardError("input changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _load_json(path: Path) -> Any:
    raw = _read_regular(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CloseBoardError("input must be UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise CloseBoardError(f"invalid JSON: {exc.msg}") from exc


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _write_new(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def compile_command(input_path: Path, output_dir: Path) -> dict[str, Any]:
    document = _load_json(input_path)
    output, markdown, receipt = compile_board(document, _now_utc())
    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    _write_new(output_dir / "board.json", canonical_json_bytes(output))
    _write_new(output_dir / "board.md", markdown.encode("utf-8"))
    _write_new(output_dir / "receipt.json", canonical_json_bytes(receipt))
    return {
        "status": "OWNER_REVIEW_ONLY",
        "output_dir": str(output_dir),
        "output_sha256": output["output_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
        **output["authority"],
    }


def verify_command(input_path: Path, output_dir: Path) -> dict[str, Any]:
    document = _load_json(input_path)
    output = _load_json(output_dir / "board.json")
    markdown = _read_regular(output_dir / "board.md").decode("utf-8")
    receipt = _load_json(output_dir / "receipt.json")
    return verify_bundle(document, output, markdown, receipt)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bounty-cash-close")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("input", type=Path)
    compile_p.add_argument("--output-dir", type=Path, required=True)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("input", type=Path)
    verify_p.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = (
            compile_command(args.input, args.output_dir)
            if args.command == "compile"
            else verify_command(args.input, args.output_dir)
        )
    except (CloseBoardError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
