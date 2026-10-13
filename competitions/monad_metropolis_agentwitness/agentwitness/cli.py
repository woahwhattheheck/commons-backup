"""Small dependency-free CLI for AgentWitness canonicalization and receipt hashes."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .core import (
    AgentWitnessError,
    canonical_event_bytes,
    event_key,
    intent_hash,
    outcome_hash,
    receipt_digest,
    strict_loads,
)


def _read(path: str) -> bytes:
    return sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()


def _json(path: str):
    return strict_loads(_read(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentwitness", description="Deterministic AgentWitness reference CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("event-key", help="derive event_key from a strict event JSON document")
    p.add_argument("path", help="event JSON path, or - for stdin")

    p = sub.add_parser("canonical-event", help="emit canonical event JSON bytes")
    p.add_argument("path", help="event JSON path, or - for stdin")

    p = sub.add_parser("intent-hash", help="hash a private intent payload without publishing it")
    p.add_argument("path", help="private payload path, or - for stdin")

    p = sub.add_parser("outcome-hash", help="hash a private outcome evidence payload")
    p.add_argument("path", help="private payload path, or - for stdin")

    p = sub.add_parser("receipt-digest", help="derive digest from a public receipt JSON document")
    p.add_argument("path", help="receipt JSON path, or - for stdin")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "event-key":
            print(event_key(_json(args.path)))
        elif args.command == "canonical-event":
            sys.stdout.buffer.write(canonical_event_bytes(_json(args.path)) + b"\n")
        elif args.command == "intent-hash":
            print(intent_hash(_read(args.path)))
        elif args.command == "outcome-hash":
            print(outcome_hash(_read(args.path)))
        elif args.command == "receipt-digest":
            value = _json(args.path)
            if type(value) is not dict:
                raise AgentWitnessError("receipt must be a JSON object")
            print(receipt_digest(value))
        else:  # pragma: no cover - argparse owns this branch
            raise AssertionError(args.command)
    except (AgentWitnessError, OSError, TypeError, ValueError) as exc:
        print(f"agentwitness: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
