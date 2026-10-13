"""Strict file CLI for opportunity-portfolio intake compilation and verification."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
from typing import Any

from .intake import IntakeError, compile_intake, verify_receipt

MAX_INPUT_BYTES = 2 * 1024 * 1024


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise IntakeError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _constant(value: str) -> Any:
    raise IntakeError(f"non-finite JSON number refused: {value}")


def _read_regular_json(path: Path) -> Any:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise IntakeError(f"input open failed: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise IntakeError("input must be a regular file")
        if before.st_size > MAX_INPUT_BYTES:
            raise IntakeError("input exceeds byte limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > MAX_INPUT_BYTES:
                raise IntakeError("input exceeds byte limit")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise IntakeError("input changed during read")
    finally:
        os.close(fd)
    try:
        text = b"".join(chunks).decode("utf-8", "strict")
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except UnicodeDecodeError as exc:
        raise IntakeError("input must be strict UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise IntakeError(f"invalid JSON: {exc}") from exc


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise IntakeError(f"output create failed: {exc}") from exc
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise IntakeError("short output write")
            view = view[written:]
        os.fsync(fd)
    except Exception:
        try:
            owned = os.fstat(fd)
            visible = os.lstat(path)
            if (owned.st_dev, owned.st_ino) == (visible.st_dev, visible.st_ino):
                os.unlink(path)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile normalized live evidence into opportunity-portfolio input")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("input", type=Path)
    compile_cmd.add_argument("--trusted-as-of", required=True)
    compile_cmd.add_argument("--receipt", type=Path, required=True)
    compile_cmd.add_argument("--portfolio-input", type=Path, required=True)

    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("receipt", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            if args.receipt == args.portfolio_input:
                raise IntakeError("receipt and portfolio output paths must differ")
            payload = _read_regular_json(args.input)
            receipt = compile_intake(payload, trusted_as_of=args.trusted_as_of)
            _write_exclusive(args.portfolio_input, _json_bytes(receipt["portfolioInput"]))
            _write_exclusive(args.receipt, _json_bytes(receipt))
            print(receipt["receiptDigestSha256"])
            return 0
        receipt = _read_regular_json(args.receipt)
        verified = verify_receipt(receipt)
        print(verified["receiptDigestSha256"])
        return 0
    except (IntakeError, OSError) as exc:
        print(f"HOLD: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
