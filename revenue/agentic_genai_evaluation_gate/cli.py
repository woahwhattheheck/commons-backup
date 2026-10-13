"""Command-line interface for the agentic GenAI evaluation evidence gate."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import _publication
from ._ingress import (
    MAX_INPUT_BYTES,
    _READ_CHUNK,
    _read_bytes_bounded,
    _read_json,
    _strict_json_loads,
)
from ._publication import _commit_link, _drain_write, _revalidate_target
from .gate import (
    EvidenceError,
    compile_receipt,
    render_markdown,
    verify_receipt,
)


def _publish_exclusive(outputs: Sequence[tuple[Path, bytes]]) -> None:
    _publication._publish_exclusive(
        outputs,
        revalidator=_revalidate_target,
        linker=_commit_link,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _cmd_compile(args: argparse.Namespace) -> int:
    if args.markdown_out:
        raise EvidenceError(
            "--markdown-out cannot share the compile transaction; use render"
        )
    packet = _read_json(Path(args.packet))
    receipt = compile_receipt(packet, evaluated_at=_now())
    receipt_bytes = (
        json.dumps(
            receipt,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

    _publish_exclusive([(Path(args.receipt_out), receipt_bytes)])

    print(receipt["decision"])
    print(receipt["receipt_sha256"])
    return 0 if receipt["decision"] == "RELEASE_CANDIDATE" else 2


def _cmd_verify(args: argparse.Namespace) -> int:
    packet = _read_json(Path(args.packet))
    receipt = _read_json(Path(args.receipt))
    result = verify_receipt(packet, receipt, verified_at=_now())
    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )
    return 0 if result.get("valid") else 3


def _cmd_render(args: argparse.Namespace) -> int:
    receipt = _read_json(Path(args.receipt))
    if type(receipt) is not dict:
        raise EvidenceError("receipt: expected object")
    try:
        markdown = render_markdown(receipt).encode("utf-8")
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError("receipt: cannot render malformed receipt") from exc
    _publish_exclusive([(Path(args.markdown_out), markdown)])
    print(receipt.get("receipt_sha256", "UNKNOWN"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    compile_parser = commands.add_parser(
        "compile",
        help="compile evaluation evidence",
    )
    compile_parser.add_argument("packet")
    compile_parser.add_argument("receipt_out")
    compile_parser.add_argument(
        "--markdown-out",
        help="rejected in v2; use the separate render command",
    )
    compile_parser.set_defaults(func=_cmd_compile)

    render_parser = commands.add_parser(
        "render",
        help="render one receipt to one Markdown artifact",
    )
    render_parser.add_argument("receipt")
    render_parser.add_argument("markdown_out")
    render_parser.set_defaults(func=_cmd_render)

    verify_parser = commands.add_parser(
        "verify",
        help="verify historical integrity and current fitness",
    )
    verify_parser.add_argument("packet")
    verify_parser.add_argument("receipt")
    verify_parser.set_defaults(func=_cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except (EvidenceError, OSError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
