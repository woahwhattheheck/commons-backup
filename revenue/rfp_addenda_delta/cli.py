from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

try:
    from .schema import DeltaError, canonical, loads_strict
    from .engine import compile_current, markdown, verify_report
except ImportError:
    from schema import DeltaError, canonical, loads_strict
    from engine import compile_current, markdown, verify_report

MAX_INPUT_BYTES = 2 * 1024 * 1024


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise DeltaError(f"input is not a regular file: {path}")
        if before.st_size > MAX_INPUT_BYTES:
            raise DeltaError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        chunks, total = [], 0
        while True:
            block = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > MAX_INPUT_BYTES:
                raise DeltaError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise DeltaError(f"input changed during read: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _preflight_outputs(*paths: Path) -> None:
    if len({os.path.abspath(os.fspath(p)) for p in paths}) != len(paths):
        raise DeltaError("output paths must be distinct")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        raise DeltaError(f"output already exists: {path}")


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            n = os.write(fd, view[written:])
            if n <= 0:
                raise DeltaError(f"short write: {path}")
            written += n
        os.fsync(fd)
    finally:
        os.close(fd)


def _load(path: Path):
    return loads_strict(_read_regular(path))


def _compile(args: argparse.Namespace) -> int:
    old = _load(args.old)
    new = _load(args.new)
    decisions = _load(args.decisions) if args.decisions else []
    report = compile_current(old, new, decisions)
    ok, reason = verify_report(old, new, decisions, report)
    if not ok:
        raise DeltaError(f"self-verification failed: {reason}")
    report_bytes = canonical(report) + b"\n"
    md_bytes = markdown(report).encode("utf-8")
    # Preflight the pair before publishing either final path. O_EXCL still
    # re-checks each final component at creation time; a late race can yield a
    # truthful partial publication, which we never pathname-delete on rollback.
    _preflight_outputs(args.out_json, args.out_md)
    _write_new(args.out_json, report_bytes)
    _write_new(args.out_md, md_bytes)
    print(f"{report['state']} {report['semantic_sha256']}")
    return 0 if report["state"] == "NO_MATERIAL_CHANGE" else 3


def _verify(args: argparse.Namespace) -> int:
    old = _load(args.old)
    new = _load(args.new)
    decisions = _load(args.decisions) if args.decisions else []
    report = _load(args.report)
    ok, reason = verify_report(old, new, decisions, report)
    print("VALID" if ok else f"INVALID {reason}")
    return 0 if ok else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exact RFP/Addenda generation delta desk")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compile")
    c.add_argument("--old", required=True, type=Path)
    c.add_argument("--new", required=True, type=Path)
    c.add_argument("--decisions", type=Path)
    c.add_argument("--out-json", required=True, type=Path)
    c.add_argument("--out-md", required=True, type=Path)
    c.set_defaults(func=_compile)

    v = sub.add_parser("verify")
    v.add_argument("--old", required=True, type=Path)
    v.add_argument("--new", required=True, type=Path)
    v.add_argument("--decisions", type=Path)
    v.add_argument("--report", required=True, type=Path)
    v.set_defaults(func=_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (DeltaError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
