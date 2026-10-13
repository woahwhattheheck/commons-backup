#!/usr/bin/env python3
"""Deterministic commercial scope carrier for Wyoming OSPD RFP 0046-N.

This is not the private delivery engine and does not submit a bid or contact the buyer.
It turns a checked offer manifest + synthetic acceptance matrix into a partner-facing
scope sheet while enforcing the procurement and paid-work boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REQUIRED_CASE_IDS = {
    "valid-standard-01", "valid-standard-02", "valid-standard-03",
    "valid-standard-04", "valid-standard-05", "missing-case-id",
    "missing-event-time", "duplicate-event-id", "corrected-date",
    "stale-correction", "closed-case", "timezone-boundary",
}
ALLOWED_EXPECTED = {"TASK_READY", "HELD"}


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_offer(offer: dict[str, Any]) -> None:
    errors: list[str] = []
    if offer.get("rfp_id") != "0046-N": errors.append("rfp_id must be 0046-N")
    if offer.get("buyer_contact_policy") != "portal_only": errors.append("buyer contact policy must be portal_only")
    if offer.get("direct_buyer_email_allowed") is not False: errors.append("direct buyer email must be forbidden")
    if offer.get("prime_teaming_only") is not True: errors.append("prime_teaming_only must be true")
    if offer.get("free_custom_work") is not False: errors.append("free_custom_work must be false")
    if offer.get("sandbox_proof_price_usd") != 2500: errors.append("sandbox proof price must be 2500 USD")
    if offer.get("sandbox_inputs") != 12: errors.append("sandbox_inputs must be 12")
    if offer.get("live_client_data") is not False: errors.append("live client data must be false")
    if offer.get("production_writes") is not False: errors.append("production writes must be false")
    if offer.get("legal_deadline_advice") is not False: errors.append("legal deadline advice must be false")
    gate = str(offer.get("delivery_gate", "")).lower()
    if "paid" not in gate and "purchase order" not in gate: errors.append("delivery_gate must require payment or PO")
    routes = offer.get("partner_routes")
    if not isinstance(routes, list) or len(routes) < 1: errors.append("at least one partner route is required")
    else:
        for route in routes:
            if "@" not in str(route.get("route", "")): errors.append("partner route must be an email address")
    if errors:
        raise ValueError("; ".join(errors))


def validate_cases(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 12:
        raise ValueError(f"expected 12 acceptance cases, got {len(cases)}")
    ids = [str(case.get("id", "")) for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("acceptance case IDs must be unique")
    if set(ids) != REQUIRED_CASE_IDS:
        missing = sorted(REQUIRED_CASE_IDS - set(ids))
        extra = sorted(set(ids) - REQUIRED_CASE_IDS)
        raise ValueError(f"acceptance case set mismatch: missing={missing}, extra={extra}")
    bad = [case.get("id") for case in cases if case.get("expected") not in ALLOWED_EXPECTED]
    if bad:
        raise ValueError(f"unsupported expected terminal state for: {bad}")


def render_scope(offer: dict[str, Any], cases: list[dict[str, Any]], partner: str) -> str:
    validate_offer(offer)
    validate_cases(cases)
    matching = [route for route in offer["partner_routes"] if route["name"].lower() == partner.lower()]
    if len(matching) != 1:
        raise ValueError(f"partner must match exactly one configured route: {partner}")
    route = matching[0]
    ready = sum(1 for case in cases if case["expected"] == "TASK_READY")
    held = sum(1 for case in cases if case["expected"] == "HELD")
    evidence_digest = sha256_hex({"offer": offer, "cases": cases})
    lines = [
        f"# Wyoming OSPD 0046-N — paid teaming work package for {route['name']}",
        "",
        f"**Prime platform:** {route['product']}",
        "**Commercial shape:** paid subcontract / integration-acceptance workstream",
        f"**Bounded sandbox proof:** ${offer['sandbox_proof_price_usd']:,} fixed",
        f"**Delivery gate:** {offer['delivery_gate']}",
        "",
        "## What the proof covers",
        "",
        "A 12-input, synthetic/no-PII case-event → deadline/calendar acceptance run that checks exactly-once task creation, duplicate suppression, correction ordering, typed holds, deterministic replay, and audit receipts. The buyer supplies the static routing/deadline rule; no legal deadline advice is provided.",
        "",
        f"Acceptance matrix: **{ready} TASK_READY / {held} HELD** expected terminal receipts. Exact-input replay must be byte-stable and must create zero second task.",
        "",
        "## Hard boundaries",
        "",
        "- No direct email/phone contact with Wyoming procurement; solicitation communication stays in Public Purchase.",
        "- No bid submission, portal/account action, prime-qualification claim, certification claim, or representation that an award is likely.",
        "- No live client/case data, court feed, production calendar write, identity integration, or production migration in the sandbox proof.",
        "- No free custom build. Buyer-specific configuration starts only after a written partner yes and paid scope / purchase order.",
        "",
        "## Handoff after partner yes",
        "",
        "1. Lock the prime-owned interface and buyer-supplied static rule.",
        "2. Run the 12 synthetic cases twice against the agreed adapter boundary.",
        "3. Deliver terminal receipt ledger, duplicate/revision evidence, replay digest, exceptions, and pass/fail scorecard.",
        "4. If the proof passes, negotiate any larger paid implementation/migration acceptance work as a separate scope.",
        "",
        f"Evidence manifest SHA-256: `{evidence_digest}`",
        "",
        f"Operation: `{offer['operation_id']}`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partner", required=True, help="Configured partner name")
    parser.add_argument("--offer", type=Path, default=ROOT / "offer.json")
    parser.add_argument("--cases", type=Path, default=ROOT / "fixtures" / "acceptance_cases.json")
    args = parser.parse_args()
    offer = load_json(args.offer)
    cases = load_json(args.cases)
    print(render_scope(offer, cases, args.partner), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
