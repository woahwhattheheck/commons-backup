from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from typing import Any

from .engine import ContractError, canonical_json, compile_plan, render_markdown, verify_plan

MAX_INPUT_BYTES = 4 * 1024 * 1024


def _reject_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _read_json(path: str) -> Any:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("input must be regular file")
        if before.st_size > MAX_INPUT_BYTES:
            raise ContractError("input too large")
        data = bytearray()
        while True:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_INPUT_BYTES:
                raise ContractError("input too large")
        after = os.fstat(fd)
        fingerprint_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        fingerprint_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if fingerprint_before != fingerprint_after:
            raise ContractError("input changed while being read")
    finally:
        os.close(fd)
    try:
        return json.loads(bytes(data).decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except UnicodeDecodeError as exc:
        raise ContractError("input must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ContractError("invalid JSON") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="commercial-portfolio-allocator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("packet")
    compile_cmd.add_argument("--format", choices=("json", "markdown"), default="json")
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("packet")
    verify_cmd.add_argument("plan")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            packet = _read_json(args.packet)
            plan = compile_plan(packet)
            if args.format == "json":
                sys.stdout.buffer.write(canonical_json(plan))
            else:
                sys.stdout.write(render_markdown(plan))
            return 0 if plan["stage"] != "HOLD" else 2
        packet = _read_json(args.packet)
        plan = _read_json(args.plan)
        result = verify_plan(packet, plan)
        sys.stdout.buffer.write(canonical_json(result))
        return 0 if result["current_gate_clear"] else 2
    except (ContractError, OSError) as exc:
        print(f"commercial-portfolio-allocator: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
