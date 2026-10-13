from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from .core import (
    ValidationError,
    canonical_json_bytes,
    compile_cockpit,
    load_json_bytes,
    render_markdown,
    verify_cockpit,
)
from .custody import (
    MAX_INPUT_BYTES,
    read_regular as _read_regular,
    write_exclusive as _write_exclusive,
    write_bundle,
)


def _load(path: str) -> object:
    return load_json_bytes(_read_regular(path))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def cmd_compile(args: argparse.Namespace) -> int:
    packet = _load(args.input)
    policy = _load(args.policy)
    out = compile_cockpit(packet, policy, as_of=_now())
    json_bytes = canonical_json_bytes(out) + b"\n"
    md_bytes = render_markdown(out).encode("utf-8")
    outputs = [(args.output, json_bytes)]
    if args.markdown:
        outputs.append((args.markdown, md_bytes))
    write_bundle(outputs)
    print(out["receipt_sha256"])
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    packet = _load(args.input)
    policy = _load(args.policy)
    compiled = _load(args.output)
    ok = verify_cockpit(packet, policy, compiled, current_as_of=_now())
    if ok:
        print("VERIFIED")
        return 0
    print("NOT_VERIFIED", file=sys.stderr)
    return 2


def cmd_render(args: argparse.Namespace) -> int:
    packet = _load(args.input)
    policy = _load(args.policy)
    compiled = _load(args.output)
    if not verify_cockpit(packet, policy, compiled, current_as_of=_now()):
        raise ValidationError("compiled output is not currently verified")
    _write_exclusive(args.markdown, render_markdown(compiled).encode("utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline cross-bid owner-action cockpit")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile", help="compile normalized blocker evidence")
    compile_p.add_argument("--input", required=True)
    compile_p.add_argument("--policy", required=True)
    compile_p.add_argument("--output", required=True)
    compile_p.add_argument("--markdown")
    compile_p.set_defaults(func=cmd_compile)

    verify_p = sub.add_parser("verify", help="verify exact historical bytes and current semantics")
    verify_p.add_argument("--input", required=True)
    verify_p.add_argument("--policy", required=True)
    verify_p.add_argument("--output", required=True)
    verify_p.set_defaults(func=cmd_verify)

    render_p = sub.add_parser("render", help="render only after current verification")
    render_p.add_argument("--input", required=True)
    render_p.add_argument("--policy", required=True)
    render_p.add_argument("--output", required=True)
    render_p.add_argument("--markdown", required=True)
    render_p.set_defaults(func=cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
