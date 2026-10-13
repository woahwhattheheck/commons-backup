from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from typing import Any, Dict

from .engine import ContractError, canonical_json, compile_board, render_markdown, verify_board

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
        st1 = os.fstat(fd)
        if not stat.S_ISREG(st1.st_mode):
            raise ContractError("input must be regular file")
        if st1.st_size > MAX_INPUT_BYTES:
            raise ContractError("input too large")
        data = bytearray()
        while True:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_INPUT_BYTES:
                raise ContractError("input too large")
        st2 = os.fstat(fd)
        if (st1.st_dev, st1.st_ino, st1.st_size, st1.st_mtime_ns, st1.st_ctime_ns) != (
            st2.st_dev, st2.st_ino, st2.st_size, st2.st_mtime_ns, st2.st_ctime_ns
        ):
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
    parser = argparse.ArgumentParser(prog="commercial-deal-room")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("packet")
    c.add_argument("--format", choices=("json", "markdown"), default="json")
    v = sub.add_parser("verify")
    v.add_argument("packet")
    v.add_argument("board")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            packet = _read_json(args.packet)
            board = compile_board(packet)
            if args.format == "json":
                sys.stdout.buffer.write(canonical_json(board))
            else:
                sys.stdout.write(render_markdown(board))
            return 0 if board["stage"] != "HOLD" else 2
        packet = _read_json(args.packet)
        board = _read_json(args.board)
        result = verify_board(packet, board)
        sys.stdout.buffer.write(canonical_json(result))
        return 0 if result["historical_valid"] else 2
    except (ContractError, OSError) as exc:
        print(f"commercial-deal-room: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
