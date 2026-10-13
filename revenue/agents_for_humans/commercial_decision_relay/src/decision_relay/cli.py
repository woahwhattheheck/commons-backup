from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .core import DecisionRelayError, verify_current_receipt
from .current import reconcile_current


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dump(value: object, path: str | None = None) -> None:
    """Emit JSON; file outputs are immutable claim-time receipts.

    O_EXCL prevents accidental overwrite and, together with O_NOFOLLOW where
    available, refuses an existing symlink target rather than following it.
    """
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if not path:
        sys.stdout.write(text)
        return

    target = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise DecisionRelayError(
            "output_exists",
            f"refusing to overwrite existing receipt path {target}",
        ) from exc
    except OSError as exc:
        if target.is_symlink():
            raise DecisionRelayError(
                "output_symlink",
                f"refusing to follow receipt symlink {target}",
            ) from exc
        raise
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decision-relay")
    sub = parser.add_subparsers(dest="command", required=True)

    p_reconcile = sub.add_parser("reconcile", help="build current deterministic decision receipt")
    p_reconcile.add_argument("--batch", required=True)
    p_reconcile.add_argument(
        "--evaluated-at",
        required=True,
        help="trusted current ISO-8601 UTC instant supplied out-of-band",
    )
    p_reconcile.add_argument("--output")

    p_verify = sub.add_parser("verify", help="verify receipt against source, digest, and trusted current UTC")
    p_verify.add_argument("--receipt", required=True)
    p_verify.add_argument("--batch", required=True)
    p_verify.add_argument("--expected-receipt-sha256", required=True)
    p_verify.add_argument("--evaluated-at", required=True, help="trusted current ISO-8601 UTC instant")

    p_agent = sub.add_parser("agent", help="run the Strands orchestration agent over trusted preloaded evidence")
    p_agent.add_argument("prompt", nargs="?", default="Show me only decisions that need a human.")
    p_agent.add_argument("--batch", required=True, help="trusted normalized evidence fixture/file")
    p_agent.add_argument("--evaluated-at", required=True, help="trusted current ISO-8601 UTC instant")
    p_agent.add_argument("--provider", choices=["bedrock", "openai"], default="bedrock")
    p_agent.add_argument("--audit-path", default=".relay/audit.jsonl")

    args = parser.parse_args(argv)
    try:
        if args.command == "reconcile":
            receipt = reconcile_current(_load(args.batch), evaluated_at=args.evaluated_at)
            _dump(receipt, args.output)
            return 0
        if args.command == "verify":
            valid = verify_current_receipt(
                _load(args.receipt),
                args.expected_receipt_sha256,
                _load(args.batch),
                evaluated_at=args.evaluated_at,
            )
            _dump({"valid": valid})
            return 0 if valid else 2

        from .strands_app import build_agent

        agent = build_agent(
            provider=args.provider,
            audit_path=args.audit_path,
            batch=_load(args.batch),
            evaluated_at=args.evaluated_at,
        )
        result = agent(args.prompt)
        print(result)
        return 0
    except (DecisionRelayError, json.JSONDecodeError, OSError) as exc:
        code = getattr(exc, "code", "runtime_error")
        print(f"ERROR {code}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
