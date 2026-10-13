from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys

from .engine import ContractError, compile_packet, load_json_strict, render_markdown, verify_report

MAX_BYTES = 2_000_000


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ContractError(f"not a regular file: {path}")
        if st.st_size > MAX_BYTES:
            raise ContractError(f"file too large: {path}")
        chunks: list[bytes] = []
        remaining = MAX_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_BYTES:
            raise ContractError(f"file too large: {path}")
        after = os.fstat(fd)
        if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ContractError(f"file changed during read: {path}")
        return data
    finally:
        os.close(fd)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="technical-capability-packet")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("packet", type=Path)
    c.add_argument("--format", choices=("json", "markdown"), default="json")
    v = sub.add_parser("verify")
    v.add_argument("packet", type=Path)
    v.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        packet = load_json_strict(_read_regular(args.packet))
        if args.cmd == "compile":
            report = compile_packet(packet, as_of=_now())
            if args.format == "markdown":
                print(render_markdown(report), end="")
            else:
                print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
            return 0 if report["readiness"] == "READY_FOR_OWNER_SEND_REVIEW" else 2
        report = load_json_strict(_read_regular(args.report))
        verification = verify_report(packet, report, current_as_of=_now())
        print(json.dumps(verification, sort_keys=True, indent=2, allow_nan=False))
        return 0 if verification["verdict"] == "CURRENT_VERIFIED" else 3
    except (ContractError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
