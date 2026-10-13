#!/usr/bin/env python3
"""Compile research into a truthful Master-of-Accounts handoff packet.

This tool never sends, drafts, contacts, bids, charges, or mutates a CRM.  It
only distinguishes a complete internal research packet from one that still
needs work.  A READY result is a handoff label, not transport permission.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "commons-marketing-sales-prospect-packet/v1"
READY = "READY_FOR_MASTER_OF_ACCOUNTS"
SUPPRESSED = "SUPPRESSED"
ALLOWED_ROUTE_TYPES = {
    "email",
    "phone",
    "linkedin",
    "contact_form",
    "procurement_portal",
}
REQUIRED_DEDUPE_SURFACES = {"commons", "gmail_sent"}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _email(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value))


def _route_ok(route: Any) -> bool:
    if not isinstance(route, dict):
        return False
    route_type = route.get("type")
    value = _text(route.get("value"))
    evidence_url = route.get("evidence_url")
    if route_type not in ALLOWED_ROUTE_TYPES or not value or not _http_url(evidence_url):
        return False
    if route_type == "email":
        return _email(value)
    if route_type in {"linkedin", "contact_form", "procurement_portal"}:
        return _http_url(value)
    return True


def validate(packet: Any) -> dict[str, Any]:
    """Return a deterministic readiness classification and exact reasons."""
    reasons: list[str] = []
    if not isinstance(packet, dict):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": SUPPRESSED,
            "reasons": ["packet must be a JSON object"],
            "external_actions": 0,
            "cash_usd": 0,
        }

    if packet.get("schema_version") != SCHEMA_VERSION:
        reasons.append("schema_version must match the current packet contract")

    organization = packet.get("organization")
    if not isinstance(organization, dict):
        reasons.append("organization is required")
    else:
        if not _text(organization.get("name")):
            reasons.append("organization.name is required")
        if not _text(organization.get("domain")):
            reasons.append("organization.domain is required")
        if not _http_url(organization.get("evidence_url")):
            reasons.append("organization.evidence_url must be first-party or authoritative HTTP(S) evidence")

    decision_maker = packet.get("decision_maker")
    if not isinstance(decision_maker, dict):
        reasons.append("decision_maker is required")
    else:
        if not _text(decision_maker.get("name")):
            reasons.append("decision_maker.name is required")
        if not _text(decision_maker.get("role")):
            reasons.append("decision_maker.role is required")
        if not _http_url(decision_maker.get("authority_evidence_url")):
            reasons.append("decision_maker.authority_evidence_url must verify buying or program authority")
        if not _route_ok(decision_maker.get("public_professional_route")):
            reasons.append("decision_maker.public_professional_route must be a sourced professional route")

    need = packet.get("need")
    if not isinstance(need, dict):
        reasons.append("need is required")
    else:
        if not _text(need.get("failure_sentence")):
            reasons.append("need.failure_sentence is required")
        if not _http_url(need.get("evidence_url")):
            reasons.append("need.evidence_url must identify the current public signal")
        if not _text(need.get("observed_at")):
            reasons.append("need.observed_at is required")

    offer = packet.get("offer")
    if not isinstance(offer, dict):
        reasons.append("offer is required")
    else:
        if offer.get("diagnostic_price_usd") != 199:
            reasons.append("offer.diagnostic_price_usd must be 199")
        if offer.get("optional_proof_price_usd") != 2500:
            reasons.append("offer.optional_proof_price_usd must be 2500")
        if not _text(offer.get("narrow_sku")):
            reasons.append("offer.narrow_sku is required")
        if not _text(offer.get("one_day_deliverable")):
            reasons.append("offer.one_day_deliverable is required")
        checks = offer.get("binary_acceptance")
        if not isinstance(checks, list) or not checks or any(not _text(item) for item in checks):
            reasons.append("offer.binary_acceptance requires at least one explicit pass/fail condition")

    dedupe = packet.get("dedupe")
    if not isinstance(dedupe, dict):
        reasons.append("dedupe is required")
    else:
        checks = dedupe.get("checks")
        seen: set[str] = set()
        if isinstance(checks, list):
            for check in checks:
                if isinstance(check, dict) and check.get("result") == "CLEAR" and _text(check.get("query")):
                    seen.add(_text(check.get("surface")))
        missing = sorted(REQUIRED_DEDUPE_SURFACES - seen)
        if missing:
            reasons.append("dedupe requires CLEAR exact checks for: " + ", ".join(missing))
        if not _text(dedupe.get("checked_at")):
            reasons.append("dedupe.checked_at is required")

    suppression = packet.get("suppression")
    if not isinstance(suppression, dict) or suppression.get("hard_do_not_resend") is not False:
        reasons.append("suppression.hard_do_not_resend must be false before handoff")
    if isinstance(suppression, dict) and suppression.get("prior_transport_found") is not False:
        reasons.append("suppression.prior_transport_found must be false before handoff")

    return {
        "schema_version": SCHEMA_VERSION,
        "packet_id": _text(packet.get("packet_id")),
        "status": READY if not reasons else SUPPRESSED,
        "reasons": reasons,
        "handoff_owner": "MASTER_OF_ACCOUNTS" if not reasons else None,
        "transport_permission": False,
        "external_actions": 0,
        "cash_usd": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="prospect packet JSON")
    parser.add_argument("--json", action="store_true", help="emit compact JSON")
    args = parser.parse_args()
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": SUPPRESSED,
            "reasons": [f"unreadable packet: {exc}"],
            "external_actions": 0,
            "cash_usd": 0,
        }
    else:
        result = validate(packet)
    print(json.dumps(result, indent=None if args.json else 2, sort_keys=True))
    return 0 if result["status"] == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
