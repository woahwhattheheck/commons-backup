from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from .core import (
    acquire_lease,
    canonical_json,
    finalize_lease,
    fingerprint_organization,
    normalize_organization_fingerprint,
    verify_lease_document,
)
from .stores import FileLeaseStore, GitHubContentsLeaseStore
from .strict import parse_json_strict, read_regular_text, write_exclusive


def _key_from_env(name: str) -> bytes:
    raw = os.environ.get(name)
    if raw is None:
        raise ValueError("missing environment variable %s" % name)
    data = raw.encode("utf-8")
    if len(data) < 32:
        raise ValueError("%s must contain at least 32 UTF-8 bytes" % name)
    return data


def _store(args):
    if args.store == "file":
        return FileLeaseStore(args.store_root)
    if not args.repository:
        raise ValueError("--repository is required for GitHub store")
    token = os.environ.get(args.github_token_env)
    if not token:
        raise ValueError("missing environment variable %s" % args.github_token_env)
    return GitHubContentsLeaseStore(repository=args.repository, branch=args.branch, token=token)


def _emit(value, output: Optional[str]):
    data = canonical_json(value) + b"\n"
    if output:
        write_exclusive(output, data)
    else:
        sys.stdout.buffer.write(data)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="organization-outbound-lease")
    sub = p.add_subparsers(dest="command", required=True)

    fp = sub.add_parser("fingerprint")
    fp.add_argument("--organization-file", required=True)
    fp.add_argument("--key-env", default="ORG_FINGERPRINT_KEY")

    for name in ("acquire", "finalize", "release"):
        sp = sub.add_parser(name)
        sp.add_argument("--input", required=True)
        sp.add_argument("--store", choices=("file", "github"), default="github")
        sp.add_argument("--store-root", default=".org-outbound-leases")
        sp.add_argument("--repository")
        sp.add_argument("--branch", default="outbound-lease-ledger")
        sp.add_argument("--github-token-env", default="GITHUB_TOKEN")
        sp.add_argument("--output")
        if name == "acquire":
            sp.add_argument("--lease-nonce-key-env", default="ORG_LEASE_NONCE_KEY")

    status = sub.add_parser("status")
    status.add_argument("--organization-fingerprint", required=True)
    status.add_argument("--store", choices=("file", "github"), default="github")
    status.add_argument("--store-root", default=".org-outbound-leases")
    status.add_argument("--repository")
    status.add_argument("--branch", default="outbound-lease-ledger")
    status.add_argument("--github-token-env", default="GITHUB_TOKEN")

    verify = sub.add_parser("verify")
    verify.add_argument("--input", required=True)

    args = p.parse_args(argv)
    try:
        if args.command == "fingerprint":
            raw = read_regular_text(args.organization_file, max_bytes=4096).encode("utf-8")
            print(fingerprint_organization(raw, _key_from_env(args.key_env)))
            return 0
        if args.command == "verify":
            value = parse_json_strict(read_regular_text(args.input))
            verify_lease_document(value)
            print("VALID")
            return 0
        if args.command == "status":
            store = _store(args)
            org = normalize_organization_fingerprint(args.organization_fingerprint)
            active = store.get_active(org)
            if active is None:
                _emit({"state": "UNLEASED", "organizationFingerprint": org, "externalSendAuthorized": False}, None)
                return 0
            raw, generation = active
            lease = verify_lease_document(parse_json_strict(raw.decode("utf-8")))
            _emit({"state": "LEASED", "activeGeneration": generation, "lease": lease, "externalSendAuthorized": False}, None)
            return 0
        value = parse_json_strict(read_regular_text(args.input))
        store = _store(args)
        if args.command == "acquire":
            result = acquire_lease(
                store,
                value,
                lease_nonce_key=_key_from_env(args.lease_nonce_key_env),
            )
            _emit({
                "state": result.state,
                "replay": result.replay,
                "activeGeneration": result.active_generation,
                "terminalOutcome": result.terminal_outcome,
                "lease": result.lease,
                "externalSendAuthorized": False,
            }, args.output)
            return 0 if result.state == "LEASE_ACQUIRED" else 3
        if args.command == "release" and value.get("outcome") != "UNSENT_RELEASED":
            raise ValueError("release command requires outcome=UNSENT_RELEASED")
        result = finalize_lease(store, value)
        _emit({
            "state": result.state,
            "replay": result.replay,
            "activeReleased": result.active_released,
            "outcomeGeneration": result.outcome_generation,
            "outcome": result.outcome,
            "externalSendAuthorized": False,
        }, args.output)
        return 0
    except Exception as exc:
        print("HOLD: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
