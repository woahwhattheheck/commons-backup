"""CLI for the read-only inbound lead controller."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .engine import InputError, compile_snapshot, render_markdown, verify_compiled

_MAX_INPUT_BYTES = 2_000_000


def _no_duplicate_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InputError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _read_json(path_text: str):
    path = Path(path_text)
    if path.is_symlink() or not path.is_file():
        raise InputError(f"input must be a regular non-symlink file: {path}")
    if path.stat().st_size > _MAX_INPUT_BYTES:
        raise InputError(f"input exceeds {_MAX_INPUT_BYTES} bytes: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid UTF-8 JSON: {path}") from exc


def _write_exclusive(path_text: str, content: str):
    path = Path(path_text)
    if path.exists() or path.is_symlink():
        raise InputError(f"refusing to overwrite existing output: {path}")
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise InputError(f"output parent does not exist: {parent}")
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _json_text(value) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _cmd_compile(args) -> int:
    source = _read_json(args.input)
    compiled = compile_snapshot(source)
    markdown = render_markdown(compiled)
    if args.json_out:
        _write_exclusive(args.json_out, _json_text(compiled))
    if args.markdown_out:
        _write_exclusive(args.markdown_out, markdown)
    if not args.json_out and not args.markdown_out:
        sys.stdout.write(_json_text(compiled))
    return 0


def _cmd_verify(args) -> int:
    source = _read_json(args.input)
    compiled = _read_json(args.compiled)
    if not verify_compiled(source, compiled):
        print("INVALID", file=sys.stderr)
        return 2
    # Also force the self-receipt/renderer path.
    render_markdown(compiled)
    print("VALID")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inbound-lead-control",
        description="Compile retained inbound provider truth into a read-only response queue.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile", help="compile one retained snapshot")
    compile_p.add_argument("input")
    compile_p.add_argument("--json-out")
    compile_p.add_argument("--markdown-out")
    compile_p.set_defaults(func=_cmd_compile)

    verify_p = sub.add_parser("verify", help="verify compiled output by exact semantic replay")
    verify_p.add_argument("input")
    verify_p.add_argument("compiled")
    verify_p.set_defaults(func=_cmd_verify)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.func(args)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
