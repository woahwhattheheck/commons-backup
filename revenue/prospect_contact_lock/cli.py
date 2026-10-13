"""CLI for the canonical prospect contact lock."""
from __future__ import annotations
import argparse
import json
import os
import sys

from .lock import (
    AUTHORITY_DIGEST,
    LockError,
    digest_message_file,
    normalize_target,
)
from .hardened import ProspectContactLock


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prospect-contact-lock",
        description="Fail-closed canonical prospect contact coordination; never send authority.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    fp = sub.add_parser("fingerprint")
    fp.add_argument("--kind", required=True, choices=("email", "domain", "phone"))
    fp.add_argument("--target", required=True)

    for name in ("status", "acquire", "arm", "dispatch", "finalize", "release"):
        sp = sub.add_parser(name)
        sp.add_argument("--kind", required=True, choices=("email", "domain", "phone"))
        sp.add_argument("--target", required=True)
        if name in {"acquire", "arm", "dispatch", "finalize", "release"}:
            sp.add_argument("--agent-id", required=True)
            sp.add_argument("--operation-id", required=True)
        if name in {"arm", "finalize"}:
            sp.add_argument("--message-file", required=True)
            sp.add_argument("--channel", required=True)
            sp.add_argument("--compensation-path", required=True)
        if name == "finalize":
            sp.add_argument("--provider-receipt", required=True)
        if name == "release":
            sp.add_argument("--reason", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "fingerprint":
            target = normalize_target(args.kind, args.target)
            print(json.dumps({
                "schema": "prospect-contact-lock-fingerprint/v1",
                "authority_digest": AUTHORITY_DIGEST,
                "kind": target.kind,
                "key_sha256": target.fingerprint,
                "target_hint": target.hint,
                "external_send_authorized": False,
            }, sort_keys=True))
            return 0

        token = os.environ.get("GITHUB_TOKEN", "")
        lock = ProspectContactLock(token)
        if args.command == "status":
            result = lock.status(args.kind, args.target)
        elif args.command == "acquire":
            result = lock.acquire(
                args.kind, args.target,
                agent_id=args.agent_id, operation_id=args.operation_id,
            )
        elif args.command == "arm":
            result = lock.arm(
                args.kind, args.target,
                agent_id=args.agent_id, operation_id=args.operation_id,
                message_sha256=digest_message_file(args.message_file),
                channel=args.channel,
                compensation_path=args.compensation_path,
            )
        elif args.command == "dispatch":
            result = lock.dispatch(
                args.kind, args.target,
                agent_id=args.agent_id, operation_id=args.operation_id,
            )
        elif args.command == "finalize":
            result = lock.finalize_contacted(
                args.kind, args.target,
                agent_id=args.agent_id, operation_id=args.operation_id,
                message_sha256=digest_message_file(args.message_file),
                channel=args.channel,
                compensation_path=args.compensation_path,
                provider_receipt=args.provider_receipt,
            )
        else:
            result = lock.release_unsent(
                args.kind, args.target,
                agent_id=args.agent_id, operation_id=args.operation_id,
                reason=args.reason,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except LockError as exc:
        print(json.dumps({
            "schema": "prospect-contact-lock-error/v1",
            "error": type(exc).__name__,
            "message": str(exc),
            "external_send_authorized": False,
            "provider_send_completed": False,
            "payment_or_revenue_inferred": False,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
