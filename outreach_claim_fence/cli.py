"""Command-line interface for the canonical v2 outreach claim fence."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Mapping, Optional, Sequence

from .core import ClaimFenceError, ValidationError, _TARGET_KINDS, digest_message_file, normalize_target
from .store import GitHubContentsClaimStore


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValidationError(f"argument error: {message}")


def _store_from_args(args: argparse.Namespace) -> GitHubContentsClaimStore:
    token = os.environ.get(args.token_env)
    if not token:
        raise ValidationError(f"token environment variable {args.token_env!r} is empty")
    reconciliation_key = None
    if args.command == "reconcile-unsent":
        raw = os.environ.get(args.reconciliation_key_env)
        if not raw:
            raise ValidationError(f"trusted reconciliation key environment variable {args.reconciliation_key_env!r} is empty")
        reconciliation_key = raw.encode("utf-8")
    return GitHubContentsClaimStore(token=token, reconciliation_key=reconciliation_key)


def _add_target(p: argparse.ArgumentParser) -> None:
    p.add_argument("--kind", required=True, choices=sorted(_TARGET_KINDS)); p.add_argument("--contact", required=True)


def _add_owner(p: argparse.ArgumentParser) -> None:
    p.add_argument("--agent-id", required=True); p.add_argument("--operation-id", required=True)


def _add_message(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group(required=True); g.add_argument("--message-digest"); g.add_argument("--message-file")


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description="Canonical atomic outreach claim coordination over GitHub")
    parser.add_argument("--token-env", default="GITHUB_TOKEN", help="environment variable containing GitHub token; namespace itself is code-pinned")
    parser.add_argument("--reconciliation-key-env", default="OUTREACH_RECONCILIATION_KEY", help="trusted UNSENT-attestation key; used only by reconcile-unsent")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("key"); _add_target(p)
    p = sub.add_parser("acquire"); _add_target(p); _add_owner(p); p.add_argument("--opportunity", required=True); p.add_argument("--lease-seconds", type=int, default=3600)
    p = sub.add_parser("inspect"); _add_target(p)
    p = sub.add_parser("renew"); _add_target(p); _add_owner(p); p.add_argument("--lease-seconds", type=int, default=3600)
    p = sub.add_parser("arm"); _add_target(p); _add_owner(p); _add_message(p); p.add_argument("--channel", required=True); p.add_argument("--compensation-path", required=True)
    p = sub.add_parser("dispatch"); _add_target(p); _add_owner(p); p.add_argument("--dispatch-token", required=True)
    p = sub.add_parser("contacted"); _add_target(p); _add_owner(p); _add_message(p); p.add_argument("--channel", required=True); p.add_argument("--compensation-path", required=True); p.add_argument("--cooldown-seconds", type=int, default=3*24*3600)
    p = sub.add_parser("reconcile-unsent"); _add_target(p); _add_owner(p); p.add_argument("--provider-history-digest", required=True); p.add_argument("--signature", required=True)
    p = sub.add_parser("release"); _add_target(p); _add_owner(p); p.add_argument("--reason", required=True)
    return parser


def _message_digest(args: argparse.Namespace) -> str:
    return digest_message_file(args.message_file) if args.message_file else args.message_digest


def _print_json(value: Mapping[str, Any], *, stream: Optional[Any] = None) -> None:
    (sys.stdout if stream is None else stream).write(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "key":
            ident = normalize_target(args.kind, args.contact)
            _print_json({"ok": True, "claim_key": ident.claim_key, "target_kind": ident.kind, "target_hint": ident.hint})
            return 0
        store = _store_from_args(args)
        common = {"target_kind": args.kind, "contact": args.contact}
        if args.command == "acquire": result = store.acquire(**common, opportunity=args.opportunity, agent_id=args.agent_id, operation_id=args.operation_id, lease_seconds=args.lease_seconds).as_dict()
        elif args.command == "inspect": result = {"ok": True, "claim": store.inspect(**common)}
        elif args.command == "renew": result = store.renew(**common, agent_id=args.agent_id, operation_id=args.operation_id, lease_seconds=args.lease_seconds).as_dict()
        elif args.command == "arm": result = store.arm(**common, agent_id=args.agent_id, operation_id=args.operation_id, message_digest=_message_digest(args), channel=args.channel, compensation_path=args.compensation_path).as_dict()
        elif args.command == "dispatch": result = store.begin_dispatch(**common, agent_id=args.agent_id, operation_id=args.operation_id, dispatch_token=args.dispatch_token).as_dict()
        elif args.command == "contacted": result = store.mark_contacted(**common, agent_id=args.agent_id, operation_id=args.operation_id, message_digest=_message_digest(args), channel=args.channel, compensation_path=args.compensation_path, cooldown_seconds=args.cooldown_seconds).as_dict()
        elif args.command == "reconcile-unsent": result = store.reconcile_unsent(**common, agent_id=args.agent_id, operation_id=args.operation_id, provider_history_digest=args.provider_history_digest, signature=args.signature).as_dict()
        elif args.command == "release": result = store.release(**common, agent_id=args.agent_id, operation_id=args.operation_id, reason=args.reason).as_dict()
        else: raise ValidationError("unknown command")
        _print_json(result); return 0
    except ClaimFenceError as exc:
        _print_json(exc.safe_payload(), stream=sys.stderr); return exc.exit_code
