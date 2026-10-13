from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .engine import LearningError, compile_current, compile_historical, loads_strict, render_markdown, verify_package

MAX_INPUT_BYTES = 16 * 1024 * 1024


def _read_regular(path: str) -> str:
    p = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise LearningError("INPUT_NOT_REGULAR_FILE")
        if st.st_size > MAX_INPUT_BYTES:
            raise LearningError("INPUT_TOO_LARGE")
        data = b""
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_INPUT_BYTES + 1 - len(data)))
            if not chunk:
                break
            data += chunk
            if len(data) > MAX_INPUT_BYTES:
                raise LearningError("INPUT_TOO_LARGE")
        return data.decode("utf-8")
    finally:
        os.close(fd)


def _write_new(path: str, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        data = text.encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-bound post-outreach revenue learning")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build")
    build.add_argument("--input", required=True)
    build.add_argument("--json-out", required=True)
    build.add_argument("--markdown-out", required=True)
    build.add_argument("--historical-at")

    verify = sub.add_parser("verify")
    verify.add_argument("--input", required=True)
    verify.add_argument("--package", required=True)

    args = parser.parse_args(argv)
    try:
        raw = loads_strict(_read_regular(args.input))
        if args.cmd == "build":
            package = compile_historical(raw, args.historical_at) if args.historical_at else compile_current(raw)
            _write_new(args.json_out, json.dumps(package, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
            _write_new(args.markdown_out, render_markdown(package))
            print(package["receipt_sha256"])
            return 0
        package = loads_strict(_read_regular(args.package))
        result = verify_package(raw, package)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (LearningError, OSError, UnicodeError) as exc:
        print(f"offer-outcome-learning: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())