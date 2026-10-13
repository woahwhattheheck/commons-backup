from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from revenue.trusted_evidence_authority.strict_json import canonical_json

from .policy import (
    ClaimPolicyError,
    load_trusted_policy,
    packet_from_text,
    receipt_from_text,
    verify_current,
    verify_historical,
    verify_receipt,
)

UTC = timezone.utc
MAX_INPUT_BYTES = 4 * 1024 * 1024


def _read_text(path: str, field: str) -> str:
    data = Path(path).read_bytes()
    if len(data) > MAX_INPUT_BYTES:
        raise ClaimPolicyError(f"{field} exceeds size limit")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ClaimPolicyError(f"{field} must be UTF-8") from exc


def _parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ClaimPolicyError("--as-of must end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ClaimPolicyError("invalid --as-of") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ClaimPolicyError("--as-of must be UTC")
    return parsed.astimezone(UTC)


def _emit(value: Any, output: str | None) -> None:
    text = canonical_json(value) + "\n"
    if output is None:
        sys.stdout.write(text)
        return
    with Path(output).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--policy", required=True, help="trusted policy JSON path")
    parser.add_argument(
        "--expected-policy-sha256",
        required=True,
        help="independently pinned SHA-256 of exact policy file bytes",
    )
    parser.add_argument("--packet", required=True, help="candidate packet JSON path")
    parser.add_argument("--output", help="create this output path exclusively; stdout when omitted")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trusted-claim-policy",
        description=(
            "Verify exact source-to-claim bindings and trusted decision windows. "
            "The current command intentionally exposes no caller-selected clock."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    current = subparsers.add_parser("verify-current", help="evaluate with process UTC")
    _add_common(current)

    historical = subparsers.add_parser(
        "verify-historical", help="forensic replay; never emits current authority"
    )
    _add_common(historical)
    historical.add_argument("--as-of", required=True, help="UTC timestamp ending in Z")

    receipt = subparsers.add_parser(
        "verify-receipt", help="recompute a recorded receipt at its recorded instant"
    )
    _add_common(receipt)
    receipt.add_argument("--receipt", required=True, help="receipt JSON path")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        policy = load_trusted_policy(
            args.policy,
            expected_file_sha256=args.expected_policy_sha256,
        )
        packet = packet_from_text(_read_text(args.packet, "packet"))
        if args.command == "verify-current":
            result = verify_current(packet, policy)
            _emit(result, args.output)
            return 0 if result["current_claim_authority"] else 3
        if args.command == "verify-historical":
            result = verify_historical(packet, policy, as_of=_parse_utc(args.as_of))
            _emit(result, args.output)
            return 0
        if args.command == "verify-receipt":
            receipt = receipt_from_text(_read_text(args.receipt, "receipt"))
            ok = verify_receipt(receipt, packet, policy)
            _emit({"ok": ok}, args.output)
            return 0 if ok else 4
        parser.error("unknown command")
    except (ClaimPolicyError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
