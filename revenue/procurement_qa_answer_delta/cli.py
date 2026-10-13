"""Create-exclusive CLI for procurement Q&A answer delta artifacts."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from .schema import Error, MAX_BYTES, digest
from .compiler import compile_delta, verify

def _open_regular(path: str, *, write=False, exclusive=False):
    flags = os.O_WRONLY | os.O_CREAT if write else os.O_RDONLY
    if exclusive:
        flags |= os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o644 if write else 0)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Error(f"{path}: regular file required")
        if hasattr(os, "O_NONBLOCK"):
            import fcntl

            current = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, current & ~os.O_NONBLOCK)
        return fd
    except Exception:
        os.close(fd)
        raise


def read_bytes(path: str):
    fd = _open_regular(path)
    try:
        chunks = []
        total = 0
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part:
                break
            total += len(part)
            if total > MAX_BYTES:
                raise Error(f"{path}: file exceeds size bound")
            chunks.append(part)
        return b"".join(chunks)
    finally:
        os.close(fd)


def write_exclusive(path: str, payload: bytes):
    fd = _open_regular(path, write=True, exclusive=True)
    try:
        view = memoryview(payload)
        while view:
            used = os.write(fd, view)
            view = view[used:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    comp = sub.add_parser("compile")
    comp.add_argument("--input", required=True)
    comp.add_argument("--out-dir", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--input", required=True)
    check.add_argument("--delta", required=True)
    check.add_argument("--markdown", required=True)
    check.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            result = compile_delta(read_bytes(args.input))
            out = Path(args.out_dir)
            out.mkdir(parents=True, exist_ok=True)
            for name, payload in (
                ("delta.json", result.delta),
                ("delta.md", result.markdown),
                ("receipt.json", result.receipt),
            ):
                write_exclusive(str(out / name), payload)
            print(json.dumps({"status": result.status, "delta_sha256": digest(result.delta)}, sort_keys=True))
        else:
            result = verify(
                read_bytes(args.input),
                read_bytes(args.delta),
                read_bytes(args.markdown),
                read_bytes(args.receipt),
            )
            print(json.dumps(result, sort_keys=True))
        return 0
    except (Error, OSError, FileExistsError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
