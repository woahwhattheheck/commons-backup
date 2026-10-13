from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .engine import CollisionError, compile_preflight, load_json_strict, verify_bundle

MAX_INPUT = 2_000_000
NAMES = ("packet.json", "review.md", "collisions.csv", "receipt.json")

def _read_regular(path: Path) -> bytes:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_INPUT:
        raise CollisionError("input must be a bounded regular file")
    data = path.read_bytes()
    st2 = path.lstat()
    if (st.st_dev, st.st_ino, st.st_size) != (st2.st_dev, st2.st_ino, st2.st_size):
        raise CollisionError("input generation changed during read")
    return data

def _write_new(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OSError("short write")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)

def _bundle_from_dir(path: Path) -> dict[str, bytes]:
    return {name: _read_regular(path / name) for name in NAMES}

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Compile/verify product-lane collision evidence")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("input")
    c.add_argument("output_dir")
    v = sub.add_parser("verify")
    v.add_argument("input")
    v.add_argument("output_dir")
    ns = p.parse_args(argv)
    try:
        raw = load_json_strict(_read_regular(Path(ns.input)).decode("utf-8"))
        outdir = Path(ns.output_dir)
        if ns.cmd == "compile":
            outdir.mkdir(mode=0o700)
            bundle = compile_preflight(raw)
            for name in NAMES:
                _write_new(outdir / name, bundle[name])
            print(json.dumps({"status": json.loads(bundle["packet.json"])["status"], "files": list(NAMES)}, sort_keys=True))
            return 0
        valid = verify_bundle(raw, _bundle_from_dir(outdir))
        print(json.dumps({"valid": valid}, sort_keys=True))
        return 0 if valid else 2
    except (CollisionError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
