#!/usr/bin/env python3
"""Canonical key compiler for connector-native outbound seam leases.

This module has no provider authority and performs no network calls. It only
computes the deterministic GitHub branch name that a connector-capable worker
must attempt to create atomically before an external outreach mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from typing import Any, Mapping, Sequence

SCHEMA = "outbound-connector-lease/v1"
BRANCH_PREFIX = "outbound-connector-lease/v1/"
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._:/+\-]{0,190}$")
SUPPORTED_REPLY_PROVIDERS = frozenset({
    "devpost",
    "gmail",
    "github",
    "slack",
    "web-form",
})


class LeaseKeyError(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LeaseKeyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                LeaseKeyError(f"non-finite JSON number: {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise LeaseKeyError("invalid JSON") from exc
    if type(value) is not dict:
        raise LeaseKeyError("input must be a JSON object")
    return value


def _normalize_domain(value: Any, field: str) -> str:
    if type(value) is not str:
        raise LeaseKeyError(f"{field} must be a string")
    candidate = value.strip().rstrip(".").casefold()
    if not candidate or len(candidate) > 253:
        raise LeaseKeyError(f"{field} must be a non-empty domain <= 253 chars")
    if "://" in candidate or any(ch in candidate for ch in "/@?#"):
        raise LeaseKeyError(f"{field} must be an organization domain, not a URL/address")
    try:
        ascii_domain = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise LeaseKeyError(f"{field} is not a valid IDNA domain") from exc
    labels = ascii_domain.split(".")
    if len(labels) < 2:
        raise LeaseKeyError(f"{field} must contain a registrable-style dotted domain")
    for label in labels:
        if not label or len(label) > 63:
            raise LeaseKeyError(f"{field} contains an invalid domain label")
        if label[0] == "-" or label[-1] == "-":
            raise LeaseKeyError(f"{field} domain labels cannot start/end with '-'")
        if re.fullmatch(r"[a-z0-9-]+", label) is None:
            raise LeaseKeyError(f"{field} contains invalid domain characters")
    return ascii_domain


def _machine_token(value: Any, field: str) -> str:
    if type(value) is not str:
        raise LeaseKeyError(f"{field} must be a string")
    token = value.strip().casefold()
    if not token or len(token) > 191 or _TOKEN_RE.fullmatch(token) is None:
        raise LeaseKeyError(f"{field} must use 1..191 lowercase-token chars [a-z0-9._:/+-]")
    return token


def _provider_token(value: Any, field: str) -> str:
    if type(value) is not str:
        raise LeaseKeyError(f"{field} must be a string")
    token = value.strip().casefold()
    if token not in SUPPORTED_REPLY_PROVIDERS:
        supported = ",".join(sorted(SUPPORTED_REPLY_PROVIDERS))
        raise LeaseKeyError(f"{field} must be one of the canonical providers: {supported}")
    return token


def _normalize_opportunity(raw: Any) -> dict[str, str]:
    if type(raw) is not dict:
        raise LeaseKeyError("opportunity must be an object")
    kind = raw.get("kind")
    if type(kind) is not str:
        raise LeaseKeyError("opportunity.kind must be a string")
    kind = kind.strip().casefold()
    if kind == "cold":
        if set(raw) != {"kind"}:
            raise LeaseKeyError("cold opportunity requires exact field: kind")
        return {"kind": "cold"}
    if kind == "external":
        if set(raw) != {"kind", "authority", "id"}:
            raise LeaseKeyError("external opportunity requires exact fields: kind,authority,id")
        return {
            "kind": "external",
            "authority": _normalize_domain(raw["authority"], "opportunity.authority"),
            "id": _machine_token(raw["id"], "opportunity.id"),
        }
    if kind == "reply":
        if set(raw) != {"kind", "provider", "event_id"}:
            raise LeaseKeyError("reply opportunity requires exact fields: kind,provider,event_id")
        return {
            "kind": "reply",
            "provider": _provider_token(raw["provider"], "opportunity.provider"),
            "event_id": _machine_token(raw["event_id"], "opportunity.event_id"),
        }
    raise LeaseKeyError("opportunity.kind must be one of: cold, external, reply")


def compile_key(buyer_scope: Any, opportunity: Any) -> dict[str, Any]:
    buyer = _normalize_domain(buyer_scope, "buyer_scope")
    normalized_opportunity = _normalize_opportunity(opportunity)
    seam = {
        "schema": SCHEMA,
        "buyer_scope": buyer,
        "opportunity": normalized_opportunity,
    }
    canonical = json.dumps(
        seam,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    digest = hashlib.sha256(canonical).hexdigest()
    return {**seam, "seam_sha256": digest, "branch": BRANCH_PREFIX + digest}


def compile_document(raw: Mapping[str, Any]) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != {"schema", "buyer_scope", "opportunity"}:
        raise LeaseKeyError("input requires exact schema,buyer_scope,opportunity fields")
    if raw["schema"] != SCHEMA:
        raise LeaseKeyError(f"schema must be {SCHEMA}")
    return compile_key(raw["buyer_scope"], raw["opportunity"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a connector-native outbound seam branch")
    parser.add_argument("--buyer-scope", help="canonical organization primary domain")
    parser.add_argument("--cold", action="store_true", help="one organization-level unsolicited outreach seam")
    parser.add_argument("--external-authority", help="domain of authoritative opportunity issuer/source")
    parser.add_argument("--external-id", help="stable external procurement/project/issue ID")
    parser.add_argument("--reply-provider", help="canonical provider ID for one inbound reply event")
    parser.add_argument("--reply-event-id", help="durable provider inbound message/event ID")
    parser.add_argument("--json", dest="json_text", help="strict JSON input document")
    args = parser.parse_args(argv)
    try:
        if args.json_text is not None:
            if any((args.buyer_scope, args.cold, args.external_authority, args.external_id, args.reply_provider, args.reply_event_id)):
                raise LeaseKeyError("use either --json or scope flags")
            result = compile_document(_parse_json(args.json_text))
        else:
            if args.buyer_scope is None:
                raise LeaseKeyError("--buyer-scope is required")
            modes = int(args.cold) + int(args.external_authority is not None or args.external_id is not None) + int(args.reply_provider is not None or args.reply_event_id is not None)
            if modes != 1:
                raise LeaseKeyError("choose exactly one opportunity mode: --cold, external pair, or reply pair")
            if args.cold:
                opportunity = {"kind": "cold"}
            elif args.external_authority is not None or args.external_id is not None:
                if args.external_authority is None or args.external_id is None:
                    raise LeaseKeyError("external mode requires --external-authority and --external-id")
                opportunity = {"kind": "external", "authority": args.external_authority, "id": args.external_id}
            else:
                if args.reply_provider is None or args.reply_event_id is None:
                    raise LeaseKeyError("reply mode requires --reply-provider and --reply-event-id")
                opportunity = {"kind": "reply", "provider": args.reply_provider, "event_id": args.reply_event_id}
            result = compile_key(args.buyer_scope, opportunity)
    except LeaseKeyError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
