"""Command-line surface for the offline #outbound-leases v1 verifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    from .protocol import (
        LeaseError,
        compile_snapshot,
        organization_key,
        purpose_fingerprint,
        route_fingerprint,
        strict_loads,
    )
except ImportError:  # direct script execution from repository root
    from protocol import (  # type: ignore
        LeaseError,
        compile_snapshot,
        organization_key,
        purpose_fingerprint,
        route_fingerprint,
        strict_loads,
    )


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise LeaseError("input must be a regular non-symlink file")
    if p.stat().st_size > 2_000_000:
        raise LeaseError("input exceeds 2,000,000 bytes")
    return p.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    key = sub.add_parser("org-key")
    key.add_argument("root_domain")
    route = sub.add_parser("route-fp")
    route.add_argument("canonical_route")
    purpose = sub.add_parser("purpose-fp")
    purpose.add_argument("canonical_purpose")
    verify = sub.add_parser("verify")
    verify.add_argument("snapshot", help="snapshot JSON path or '-' for stdin")
    args = parser.parse_args(argv)
    try:
        if args.command == "org-key":
            value = organization_key(args.root_domain)
        elif args.command == "route-fp":
            value = route_fingerprint(args.canonical_route)
        elif args.command == "purpose-fp":
            value = purpose_fingerprint(args.canonical_purpose)
        else:
            value = compile_snapshot(strict_loads(_read_text(args.snapshot)))
        if isinstance(value, str):
            print(value)
        else:
            print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
        return 0
    except LeaseError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
