from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .composer import compile_bundle, load_json_strict, render_markdown, verify_receipt
except ImportError:  # direct script execution
    from composer import compile_bundle, load_json_strict, render_markdown, verify_receipt


def read_json(path: Path):
    return load_json_strict(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile or verify a cross-family Commons offering bundle.")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile")
    compile_p.add_argument("manifest", type=Path)
    compile_p.add_argument("--as-of", required=True, help="Trusted UTC instant, exact YYYY-MM-DDTHH:MM:SSZ")
    compile_p.add_argument("--json-out", type=Path)
    compile_p.add_argument("--markdown-out", type=Path)

    verify_p = sub.add_parser("verify")
    verify_p.add_argument("manifest", type=Path)
    verify_p.add_argument("receipt", type=Path)
    verify_p.add_argument("--as-of", required=True)

    args = parser.parse_args(argv)
    manifest = read_json(args.manifest)
    if args.command == "compile":
        receipt = compile_bundle(manifest, trusted_as_of=args.as_of)
        if args.json_out:
            write_json(args.json_out, receipt)
        else:
            print(json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False))
        if args.markdown_out:
            args.markdown_out.write_text(render_markdown(receipt), encoding="utf-8")
        return 0 if receipt["status"] == "READY_FOR_HUMAN_BUNDLE_REVIEW" else 3

    receipt = read_json(args.receipt)
    ok = verify_receipt(manifest, trusted_as_of=args.as_of, receipt=receipt)
    print(json.dumps({"verified": ok}, sort_keys=True))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
