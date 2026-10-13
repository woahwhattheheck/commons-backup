from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .allocator import AllocationError, canonical_json_bytes, compile_portfolio, verify_bundle

MAX_INPUT_BYTES = 10 * 1024 * 1024


def _reject_constant(value: str) -> Any:
    raise AllocationError(f"non-finite JSON constant rejected: {value}")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AllocationError(f"duplicate JSON key rejected: {key}")
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
            raise AllocationError("input must be a regular file")
        if before.st_size <= 0 or before.st_size > MAX_INPUT_BYTES:
            raise AllocationError("input size invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise AllocationError("input changed during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise AllocationError("input grew during read")
        after = os.fstat(fd)
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity_before != identity_after:
            raise AllocationError("input changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _load_json(path: Path) -> Any:
    raw = _read_regular(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AllocationError("input must be UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise AllocationError(f"invalid JSON: {exc.msg}") from exc


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


def compile_command(input_path: Path, output_dir: Path) -> dict[str, Any]:
    document = _load_json(input_path)
    output, markdown, receipt = compile_portfolio(document)
    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        _write_new(output_dir / "priority.json", canonical_json_bytes(output))
        _write_new(output_dir / "priority.md", markdown.encode("utf-8"))
        _write_new(output_dir / "receipt.json", canonical_json_bytes(receipt))
    except Exception:
        for name in ("priority.json", "priority.md", "receipt.json"):
            try:
                (output_dir / name).unlink()
            except FileNotFoundError:
                pass
        try:
            output_dir.rmdir()
        except OSError:
            pass
        raise
    return {
        "status": "OWNER_REVIEW_ONLY",
        "output_dir": str(output_dir),
        "output_sha256": output["output_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
        "external_send_authorized": False,
        "provider_mutation_authorized": False,
        "payment_or_revenue_inferred": False,
    }


def verify_command(input_path: Path, output_dir: Path) -> dict[str, Any]:
    document = _load_json(input_path)
    output = _load_json(output_dir / "priority.json")
    markdown = _read_regular(output_dir / "priority.md").decode("utf-8")
    receipt = _load_json(output_dir / "receipt.json")
    return verify_bundle(document, output, markdown, receipt)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="revenue-targeting-allocator")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("input", type=Path)
    c.add_argument("--output-dir", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("input", type=Path)
    v.add_argument("--output-dir", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = (
            compile_command(args.input, args.output_dir)
            if args.command == "compile"
            else verify_command(args.input, args.output_dir)
        )
    except (AllocationError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
