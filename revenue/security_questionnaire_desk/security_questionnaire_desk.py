#!/usr/bin/env python3
"""Open-door, authority-honest Security Questionnaire Response Desk.

No login, identity, permission, credential, allowlist, or approval gate is added.
Candidate owner dispositions stay review context only. Evidence can be linked to
an exact question/answer generation without claiming authenticated provenance.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from typing import Sequence

try:
    from . import _engine as _core
    from ._secure_input import answer_binding_sha256
    from ._secure_packet import (
        artifact_bytes, compile_packet, render_public_safe_json, verify_packet,
    )
    from ._secure_publish import publish_artifacts as _publish
except ImportError:
    import _engine as _core  # type: ignore[no-redef]
    from _secure_input import answer_binding_sha256
    from _secure_packet import (
        artifact_bytes, compile_packet, render_public_safe_json, verify_packet,
    )
    from _secure_publish import publish_artifacts as _publish

for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))

DeskError = _core.DeskError
SCHEMA_VERSION = _core.SCHEMA_VERSION
canonical_bytes = _core.canonical_bytes
sha256_hex = _core.sha256_hex
loads_strict = _core.loads_strict
load_json_file = _core.load_json_file
render_markdown = _core.render_markdown
render_csv = _core.render_csv


def publish_artifacts(packet, output_dir):
    return _publish(packet, output_dir, artifact_bytes)


def _trusted_now() -> datetime:
    return _core._trusted_now()


def _cmd_compile(args: argparse.Namespace) -> int:
    raw = load_json_file(args.input)
    packet = compile_packet(raw, _trusted_now())
    publish_artifacts(packet, args.output_dir)
    print(packet["receipt_sha256"])
    return 0 if packet["status"] != "HOLD" else 2


def _cmd_verify(args: argparse.Namespace) -> int:
    raw = load_json_file(args.input)
    packet = load_json_file(args.packet)
    result = verify_packet(raw, packet, _trusted_now())
    print(canonical_bytes(result).decode("utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline evidence-linked security questionnaire response desk."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile", help="compile one owner-review packet")
    compile_parser.add_argument("input")
    compile_parser.add_argument("output_dir")
    compile_parser.set_defaults(func=_cmd_compile)
    verify_parser = sub.add_parser("verify", help="verify an exact packet")
    verify_parser.add_argument("input")
    verify_parser.add_argument("packet")
    verify_parser.set_defaults(func=_cmd_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except DeskError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


__all__ = sorted(
    {name for name in dir(_core) if not name.startswith("_")}
    | {
        "answer_binding_sha256", "artifact_bytes", "build_parser",
        "compile_packet", "main", "publish_artifacts",
        "render_public_safe_json", "verify_packet",
    }
)

if __name__ == "__main__":
    raise SystemExit(main())
