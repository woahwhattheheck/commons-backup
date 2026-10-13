# SPDX-License-Identifier: Apache-2.0
"""CLI for current OHSU RFP-2027-2012 qualification authority."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from current_authority import QualificationError, evaluate_current_bytes

_MAX_INPUT_BYTES = 2 * 1024 * 1024


def _fingerprint(st: os.stat_result) -> tuple[int, ...]:
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_nlink,
        st.st_uid,
        st.st_gid,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def _read_regular_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY
    for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= getattr(os, name, 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("qualification bundle must be a regular file")
        if before.st_nlink != 1:
            raise OSError("qualification bundle must have one link")
        if before.st_size < 1 or before.st_size > _MAX_INPUT_BYTES:
            raise OSError("qualification bundle size is invalid")

        data = bytearray()
        while len(data) <= _MAX_INPUT_BYTES:
            chunk = os.read(fd, _MAX_INPUT_BYTES + 1 - len(data))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > _MAX_INPUT_BYTES:
            raise OSError("qualification bundle exceeds byte limit")

        after = os.fstat(fd)
        if _fingerprint(before) != _fingerprint(after):
            raise OSError("qualification bundle changed during read")
        visible = os.stat(path, follow_symlinks=False)
        if _fingerprint(after) != _fingerprint(visible):
            raise OSError("qualification bundle visible generation changed")
        if len(data) != after.st_size:
            raise OSError("qualification bundle byte count changed")
        return bytes(data)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate current OHSU RFP-2027-2012 qualification evidence"
    )
    parser.add_argument("bundle", type=Path, help="JSON qualification bundle")
    parser.add_argument(
        "--output",
        type=Path,
        help="write receipt atomically instead of stdout",
    )
    args = parser.parse_args(argv)

    try:
        raw = _read_regular_bytes(args.bundle)
        receipt = evaluate_current_bytes(raw)
    except (OSError, QualificationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.output.with_name(args.output.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(args.output)
    return 0 if receipt["decision"] == "READY_FOR_INTERNAL_BID_REVIEW" else 3


if __name__ == "__main__":
    raise SystemExit(main())
