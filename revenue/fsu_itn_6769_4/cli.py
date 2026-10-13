"""Current-work CLI for the FSU ITN 6769-4 qualification compiler.

The production boundary owns evaluation time from process UTC. Historical replay
with caller-selected time is intentionally library-only so a user cannot turn an
old source snapshot into current commercial authority through this CLI.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .qualifier import (
        QualificationError,
        canonical_bytes,
        compile_qualification,
        loads_strict,
        verify_current_qualification,
    )
except ImportError:  # direct script execution
    from qualifier import (
        QualificationError,
        canonical_bytes,
        compile_qualification,
        loads_strict,
        verify_current_qualification,
    )

MAX_INPUT_BYTES = 2 * 1024 * 1024


def read_json_regular(path: str):
    p = Path(path)
    st = p.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_size > MAX_INPUT_BYTES:
        raise QualificationError("input must be bounded ordinary regular file")
    return loads_strict(p.read_text(encoding="utf-8"))


def publish_new(path: str, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)


def trusted_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FSU ITN 6769-4 current qualification compiler")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--source", required=True)
    c.add_argument("--expected-source-packet-sha256")
    c.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--source", required=True)
    v.add_argument("--receipt", required=True)
    v.add_argument("--expected-source-packet-sha256")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        source = read_json_regular(args.source)
        current_as_of = trusted_utc_now()
        if args.command == "compile":
            result = compile_qualification(
                source,
                as_of=current_as_of,
                expected_source_packet_sha256=args.expected_source_packet_sha256,
            )
            publish_new(args.out, canonical_bytes(result))
            print(result["receipt"]["disposition"])
            return 0
        candidate = read_json_regular(args.receipt)
        receipt = candidate.get("receipt") if type(candidate) is dict and "receipt" in candidate else candidate
        ok = verify_current_qualification(
            source,
            receipt,
            current_as_of=current_as_of,
            expected_source_packet_sha256=args.expected_source_packet_sha256,
        )
        print("VERIFIED_CURRENT" if ok else "MISMATCH_OR_STALE")
        return 0 if ok else 2
    except (QualificationError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
