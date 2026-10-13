from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from .qualification import ContractError, canonical_bytes, compile_current, verify_report

MAX_INPUT = 1_000_000


def _read_regular(path: str) -> bytes:
    p = Path(path)
    try:
        before = p.lstat()
    except OSError as exc:
        raise ContractError(f"cannot stat input: {path}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ContractError(f"input must be regular non-symlink file: {path}")
    flags = os.O_RDONLY
    for name in ("O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"):
        flags |= getattr(os, name, 0)
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise ContractError(f"cannot open stable input: {path}") from exc
    try:
        opened = os.fstat(fd)
        same_open = (
            before.st_dev == opened.st_dev
            and before.st_ino == opened.st_ino
            and before.st_mode == opened.st_mode
            and before.st_size == opened.st_size
            and before.st_mtime_ns == opened.st_mtime_ns
            and before.st_ctime_ns == opened.st_ctime_ns
        )
        if not same_open:
            raise ContractError(f"input changed before open: {path}")
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_INPUT:
            raise ContractError(f"input must be bounded regular file: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_INPUT + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT:
                raise ContractError(f"input too large: {path}")
        after = os.fstat(fd)
        stable = (
            opened.st_dev == after.st_dev
            and opened.st_ino == after.st_ino
            and opened.st_mode == after.st_mode
            and opened.st_size == after.st_size == total
            and opened.st_mtime_ns == after.st_mtime_ns
            and opened.st_ctime_ns == after.st_ctime_ns
        )
        if not stable:
            raise ContractError(f"input changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_exclusive(path: str, value: object) -> None:
    raw = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True).encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb", closefd=True) as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _optional(path: str | None) -> bytes | None:
    return None if path is None else _read_regular(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TXST AI advising qualification carrier")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile", help="compile current owner-review qualification")
    compile_p.add_argument("--candidate", required=True)
    compile_p.add_argument("--official")
    compile_p.add_argument("--owner-evidence")
    compile_p.add_argument("--partner-evidence")
    compile_p.add_argument("--out", required=True)

    verify_p = sub.add_parser("verify", help="verify receipt integrity and current semantics")
    verify_p.add_argument("--candidate", required=True)
    verify_p.add_argument("--report", required=True)
    verify_p.add_argument("--official")
    verify_p.add_argument("--owner-evidence")
    verify_p.add_argument("--partner-evidence")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidate = _read_regular(args.candidate)
        official = _optional(args.official)
        owner = _optional(args.owner_evidence)
        partner = _optional(args.partner_evidence)
        if args.command == "compile":
            report = compile_current(candidate, official_raw=official, owner_raw=owner, partner_raw=partner)
            _write_exclusive(args.out, report)
            print(json.dumps({"state": report["state"], "receipt_sha256": report["receipt_sha256"]}, sort_keys=True))
            return 0
        result = verify_report(candidate, _read_regular(args.report), official_raw=official, owner_raw=owner, partner_raw=partner)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["integrity_valid"] and result["current_semantics_match"] else 2
    except (ContractError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
