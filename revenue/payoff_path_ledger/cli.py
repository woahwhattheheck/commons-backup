from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import GateError, compile_current, loads_strict_json, verify_current, verify_integrity


def _read(path: str):
    return loads_strict_json(Path(path).read_bytes())


def _write_exclusive(path: str, obj) -> None:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(data)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compile or verify payoff-path evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    comp = sub.add_parser("compile")
    comp.add_argument("packet")
    comp.add_argument("--out", required=True)
    vi = sub.add_parser("verify-integrity")
    vi.add_argument("packet")
    vi.add_argument("receipt")
    vc = sub.add_parser("verify-current")
    vc.add_argument("packet")
    vc.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            _write_exclusive(args.out, compile_current(_read(args.packet)))
            return 0
        if args.command == "verify-integrity":
            ok = verify_integrity(_read(args.packet), _read(args.receipt))
        else:
            ok = verify_current(_read(args.packet), _read(args.receipt))
        print("VALID" if ok else "INVALID")
        return 0 if ok else 1
    except (GateError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
