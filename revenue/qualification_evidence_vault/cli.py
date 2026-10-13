from __future__ import annotations

import argparse
import json
import os
import stat
import sys

from .engine import (
    EvidenceError,
    canonical_bytes,
    compile_assessment,
    redact_vault,
    render_markdown,
    strict_loads,
    verify_assessment,
)

MAX_FILE_BYTES = 1_048_576


def _read_regular(path: str) -> bytes:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EvidenceError(f"cannot open input as no-follow regular file: {path}") from exc
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise EvidenceError(f"input is not a regular file: {path}")
        if meta.st_size > MAX_FILE_BYTES:
            raise EvidenceError(f"input exceeds {MAX_FILE_BYTES} bytes: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise EvidenceError(f"input exceeds {MAX_FILE_BYTES} bytes: {path}")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _read_json(path: str):
    return strict_loads(_read_regular(path))


def _write_exclusive(path: str, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise EvidenceError(f"short write: {path}")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Qualification evidence vault")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--vault", required=True)
    compile_p.add_argument("--solicitation", required=True)
    compile_p.add_argument("--as-of", required=True)
    compile_p.add_argument("--packet", required=True)
    compile_p.add_argument("--brief", required=True)

    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--vault", required=True)
    verify_p.add_argument("--solicitation", required=True)
    verify_p.add_argument("--packet", required=True)
    verify_p.add_argument("--brief", required=True)

    redact_p = sub.add_parser("redact")
    redact_p.add_argument("--vault", required=True)
    redact_p.add_argument("--as-of", required=True)
    redact_p.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "compile":
            vault = _read_json(args.vault)
            solicitation = _read_json(args.solicitation)
            packet = compile_assessment(vault, solicitation, args.as_of)
            brief = render_markdown(packet)
            _write_exclusive(args.packet, canonical_bytes(packet))
            _write_exclusive(args.brief, brief.encode("utf-8"))
            print(json.dumps({"outcome": packet["outcome"], "assessment_sha256": packet["assessment_sha256"]}, sort_keys=True))
            return 0
        if args.command == "verify":
            vault = _read_json(args.vault)
            solicitation = _read_json(args.solicitation)
            packet = _read_json(args.packet)
            brief = _read_regular(args.brief).decode("utf-8", "strict")
            ok = verify_assessment(vault, solicitation, packet) and brief == render_markdown(packet)
            print("EXACT_QUALIFICATION_MATCH" if ok else "QUALIFICATION_MISMATCH")
            return 0 if ok else 3
        if args.command == "redact":
            vault = _read_json(args.vault)
            output = redact_vault(vault, args.as_of)
            _write_exclusive(args.out, canonical_bytes(output))
            print(output["public_vault_sha256"])
            return 0
        raise EvidenceError("unknown command")
    except (EvidenceError, OSError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
