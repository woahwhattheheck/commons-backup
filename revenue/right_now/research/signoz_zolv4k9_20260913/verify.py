#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_HOSTS = {"signoz.io", "www.signoz.io"}
EXPECTED_KINDS = {"failure_mode", "owner_role", "first_party_route"}
OP = "COMMONS-SIGNOZ-RIGHTNOW-EVIDENCE-ZOLV4K9-20260913"


def canonical_bytes(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def digest(obj: object) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(evidence: dict, patch: dict) -> dict:
    require(evidence.get("schema_version") == "commons-signoz-research-evidence/v1", "bad evidence schema")
    require(patch.get("schema_version") == "commons-right-now-candidate-research-patch/v1", "bad patch schema")
    require(evidence.get("operation_id") == OP == patch.get("operation_id"), "operation mismatch")
    require(evidence.get("prospect_id") == "signoz", "wrong prospect")
    require(evidence.get("organization") == "SigNoz", "wrong organization")

    rows = evidence.get("evidence")
    require(isinstance(rows, list) and len(rows) == 3, "expected exactly three evidence classes")
    kinds = {row.get("kind") for row in rows if isinstance(row, dict)}
    require(kinds == EXPECTED_KINDS, f"evidence kinds mismatch: {sorted(kinds)}")

    for row in rows:
        require(isinstance(row, dict), "evidence row must be object")
        url = row.get("source_url")
        require(isinstance(url, str), "source_url missing")
        parsed = urlparse(url)
        require(parsed.scheme == "https", "source must use https")
        require(parsed.hostname in ALLOWED_HOSTS, f"non-first-party host: {parsed.hostname}")
        require(row.get("source_publisher") == "SigNoz", "source publisher must be SigNoz")
        require(isinstance(row.get("finding"), str) and len(row["finding"]) >= 40, "finding too weak")

    failure = next(r for r in rows if r["kind"] == "failure_mode")
    require(failure.get("internal_incident_asserted") is False, "must not claim a SigNoz internal incident")
    owner = next(r for r in rows if r["kind"] == "owner_role")
    require(owner.get("person") == "Ankit Nayan", "unexpected owner-role subject")
    require(owner.get("role") == "Co-Founder & CTO", "unexpected owner role")
    route = next(r for r in rows if r["kind"] == "first_party_route")
    require(route.get("route_used") is False, "research carrier must not use route")
    route_url = urlparse(route.get("route", ""))
    require(route_url.scheme == "https" and route_url.hostname in ALLOWED_HOSTS, "route must be first-party https")

    limits = evidence.get("semantic_limits")
    require(isinstance(limits, dict), "semantic limits missing")
    for key in (
        "buyer_intent_asserted",
        "purchasing_ability_asserted",
        "budget_asserted",
        "internal_sigNoz_incident_asserted",
        "transport_authorized",
        "contact_attempted",
        "revenue_asserted",
    ):
        require(limits.get(key) is False, f"{key} must remain false")

    expected_digest = digest(evidence)
    require(patch.get("evidence_sha256") == expected_digest, "evidence digest mismatch")
    target = patch.get("target", {})
    require(target == {
        "prospect_id": "signoz",
        "organization": "SigNoz",
        "offer_id": "same-day-agent-survival-proof",
    }, "target mismatch")

    resolution = patch.get("research_resolution", {})
    require(resolution.get("observable_production_failure_phrase") == "RESOLVED_AS_FIRST_PARTY_PRODUCT_FAILURE_MODE_NOT_BUYER_INCIDENT", "failure-mode resolution must stay qualified")
    require(resolution.get("relevant_owner_role") == "RESOLVED", "owner role unresolved")
    require(resolution.get("verified_first_party_route") == "RESOLVED_NOT_USED", "route must remain unused")

    rec = patch.get("recommended_state", {})
    require(rec.get("decision") == "QUALIFIED_RESEARCH_ONLY_OWNER_REVIEW", "unsafe decision")
    require(rec.get("ready_to_draft") is False, "research may not auto-draft")
    require(rec.get("transport_authorized") is False, "research may not authorize transport")
    gaps = patch.get("remaining_commercial_gaps")
    require(isinstance(gaps, list) and len(gaps) >= 3, "commercial gaps must remain explicit")

    return {
        "status": "PASS",
        "operation_id": OP,
        "evidence_sha256": expected_digest,
        "decision": rec["decision"],
        "transport_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", default=str(Path(__file__).with_name("evidence.json")))
    parser.add_argument("--patch", default=str(Path(__file__).with_name("candidate_patch.json")))
    args = parser.parse_args()
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    patch = json.loads(Path(args.patch).read_text(encoding="utf-8"))
    receipt = verify(evidence, patch)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
