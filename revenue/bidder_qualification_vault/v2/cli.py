from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .engine import RegistryError, compile_registry, load_json_strict, render_markdown, verify_receipt


def _read(path: str):
    return load_json_strict(Path(path).read_text(encoding="utf-8"))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compile or verify a deterministic candidate evidence manifest")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("input")
    compile_p.add_argument("--json-out", required=True)
    compile_p.add_argument("--md-out", required=True)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("input")
    verify_p.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            payload = _read(args.input)
            receipt = compile_registry(payload)
            Path(args.json_out).write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
            Path(args.md_out).write_text(render_markdown(receipt), encoding="utf-8")
            return 0
        return 0 if verify_receipt(_read(args.input), _read(args.receipt)) else 2
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(f"INVALID: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
