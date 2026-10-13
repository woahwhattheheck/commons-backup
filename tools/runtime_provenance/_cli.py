"""Command-line entrypoint for the runtime provenance verifier."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from typing import Optional
from ._model import MAX_AGE_SECONDS_DEFAULT, RegistryError, _parse_time, registry_digest
from .runtime_registry import load_registry, verify_registry

def _parse_cli_now(raw: Optional[str]) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc)
    parsed = _parse_time(raw, "--now")
    if parsed is None:
        raise RegistryError("--now cannot be UNKNOWN")
    return parsed

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="verify and assess a registry")
    verify.add_argument("registry")
    verify.add_argument("--now", help="UTC ISO-8601 timestamp ending in Z")
    verify.add_argument("--max-age-seconds", type=int, default=MAX_AGE_SECONDS_DEFAULT)
    digest = sub.add_parser("digest", help="print canonical registry SHA-256")
    digest.add_argument("registry")
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.registry)
        if args.command == "digest":
            print(registry_digest(registry)); return 0
        receipt = verify_registry(registry, now=_parse_cli_now(args.now), max_age_seconds=args.max_age_seconds)
        print(json.dumps(receipt, sort_keys=True, indent=2)); return 0
    except (OSError, json.JSONDecodeError, RegistryError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True)); return 2
