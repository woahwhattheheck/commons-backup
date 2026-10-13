from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from .core import CoordinationError, Envelope, MailCoordinator, QueueRequest
from .server import serve


def _json(value: Any) -> None:
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _body(args: argparse.Namespace) -> str:
    if args.body is not None:
        return args.body
    if args.body_file is not None:
        return Path(args.body_file).read_text(encoding="utf-8")
    raise SystemExit("one of --body or --body-file is required")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Durable outbound-mail coordination boundary")
    root.add_argument("--db", default="mail-coordinator.sqlite3", help="SQLite database path")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("init")

    inbound = commands.add_parser("record-inbound")
    inbound.add_argument("--operation-id", required=True)
    inbound.add_argument("--mailbox", required=True)
    inbound.add_argument("--conversation-key", required=True)
    inbound.add_argument("--provider-message-id", required=True)
    inbound.add_argument("--received-at", required=True, type=float)

    enqueue = commands.add_parser("enqueue")
    enqueue.add_argument("--operation-id", required=True)
    enqueue.add_argument("--message-id")
    enqueue.add_argument("--mailbox", required=True)
    enqueue.add_argument("--sender", required=True)
    enqueue.add_argument("--to", action="append", default=[])
    enqueue.add_argument("--cc", action="append", default=[])
    enqueue.add_argument("--bcc", action="append", default=[])
    enqueue.add_argument("--subject", default="")
    enqueue.add_argument("--body")
    enqueue.add_argument("--body-file")
    enqueue.add_argument("--conversation-key")
    enqueue.add_argument("--inbound-message-id")
    enqueue.add_argument("--inbound-received-at", type=float)

    claim = commands.add_parser("claim")
    claim.add_argument("--operation-id", required=True)
    claim.add_argument("--message-id", required=True)
    claim.add_argument("--worker-id", required=True)
    claim.add_argument("--claim-id")
    claim.add_argument("--lease-seconds", type=float, default=120)

    attempt = commands.add_parser("begin-attempt")
    attempt.add_argument("--operation-id", required=True)
    attempt.add_argument("--claim-id", required=True)
    attempt.add_argument("--attempt-id")

    receipt = commands.add_parser("record-receipt")
    receipt.add_argument("--operation-id", required=True)
    receipt.add_argument("--attempt-id", required=True)
    receipt.add_argument("--provider-message-id", required=True)
    receipt.add_argument("--accepted-at", required=True, type=float)

    uncertain = commands.add_parser("mark-uncertain")
    uncertain.add_argument("--operation-id", required=True)
    uncertain.add_argument("--attempt-id", required=True)
    uncertain.add_argument("--detail", required=True)

    reconcile = commands.add_parser("reconcile-not-sent")
    reconcile.add_argument("--operation-id", required=True)
    reconcile.add_argument("--attempt-id", required=True)
    reconcile.add_argument("--evidence-ref", required=True)

    suppress = commands.add_parser("suppress")
    suppress.add_argument("--operation-id", required=True)
    suppress.add_argument("--address", required=True)
    suppress.add_argument("--reason", required=True)
    suppress.add_argument("--evidence-ref", required=True)

    status = commands.add_parser("status")
    status.add_argument("message_id")
    status.add_argument("--include-body", action="store_true")

    ready = commands.add_parser("ready")
    ready.add_argument("--mailbox")
    ready.add_argument("--limit", type=int, default=100)

    server = commands.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8788)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    coordinator = MailCoordinator(args.db)
    coordinator.initialize()
    try:
        if args.command == "init":
            result: Any = {"status": "initialized", "database": args.db}
        elif args.command == "record-inbound":
            result = coordinator.record_inbound(
                operation_id=args.operation_id,
                mailbox=args.mailbox,
                conversation_key=args.conversation_key,
                provider_message_id=args.provider_message_id,
                received_at=args.received_at,
            )
        elif args.command == "enqueue":
            result = coordinator.enqueue(
                QueueRequest(
                    operation_id=args.operation_id,
                    message_id=args.message_id,
                    mailbox=args.mailbox,
                    envelope=Envelope(
                        sender=args.sender,
                        to=tuple(args.to),
                        cc=tuple(args.cc),
                        bcc=tuple(args.bcc),
                        subject=args.subject,
                        body=_body(args),
                    ),
                    conversation_key=args.conversation_key,
                    inbound_message_id=args.inbound_message_id,
                    inbound_received_at=args.inbound_received_at,
                )
            )
        elif args.command == "claim":
            result = coordinator.claim(
                operation_id=args.operation_id,
                message_id=args.message_id,
                worker_id=args.worker_id,
                claim_id=args.claim_id,
                lease_seconds=args.lease_seconds,
            )
        elif args.command == "begin-attempt":
            result = coordinator.begin_attempt(operation_id=args.operation_id, claim_id=args.claim_id, attempt_id=args.attempt_id)
        elif args.command == "record-receipt":
            result = coordinator.record_provider_receipt(
                operation_id=args.operation_id,
                attempt_id=args.attempt_id,
                provider_message_id=args.provider_message_id,
                accepted_at=args.accepted_at,
            )
        elif args.command == "mark-uncertain":
            result = coordinator.mark_uncertain(operation_id=args.operation_id, attempt_id=args.attempt_id, detail=args.detail)
        elif args.command == "reconcile-not-sent":
            result = coordinator.reconcile_not_sent(
                operation_id=args.operation_id,
                attempt_id=args.attempt_id,
                evidence_ref=args.evidence_ref,
            )
        elif args.command == "suppress":
            result = coordinator.suppress(
                operation_id=args.operation_id,
                address=args.address,
                reason=args.reason,
                evidence_ref=args.evidence_ref,
            )
        elif args.command == "status":
            result = coordinator.status(args.message_id, include_body=args.include_body)
        elif args.command == "ready":
            result = coordinator.list_ready(mailbox=args.mailbox, limit=args.limit)
        elif args.command == "serve":
            serve(coordinator, host=args.host, port=args.port)
            return 0
        else:
            raise AssertionError(args.command)
    except CoordinationError as exc:
        _json({"error": exc.code, "message": str(exc), "details": exc.details})
        return 2
    _json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
