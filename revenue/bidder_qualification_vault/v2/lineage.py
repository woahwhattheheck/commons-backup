from __future__ import annotations

from datetime import datetime
from typing import Any

from .strict import _parse_utc, canonical_json


def _generation_conflicts(evidence: list[dict[str, Any]]) -> tuple[set[str], dict[str, str], set[str]]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        by_id.setdefault(item["id"], []).append(item)

    conflicts: set[str] = set()
    canonical_one: dict[str, dict[str, Any]] = {}
    for eid, items in by_id.items():
        payloads = {canonical_json(i) for i in items}
        if len(items) > 1:
            conflicts.add(eid)
        if len(payloads) == 1:
            canonical_one[eid] = items[0]

    superseded_by: dict[str, str] = {}
    for item in evidence:
        old = item["supersedes"]
        if old is None:
            continue
        if old == item["id"] or old not in by_id:
            conflicts.add(item["id"])
            conflicts.add(old)
            continue
        old_item = canonical_one.get(old)
        if old_item is None:
            conflicts.add(item["id"])
            conflicts.add(old)
            continue
        if (
            old_item["entity_id"] != item["entity_id"]
            or old_item["category"] != item["category"]
            or old_item["subject_id"] != item["subject_id"]
        ):
            conflicts.add(item["id"])
            conflicts.add(old)
            continue
        old_issued = _parse_utc(old_item["issued_at"], "lineage.old.issued_at")
        new_issued = _parse_utc(item["issued_at"], "lineage.new.issued_at")
        old_captured = _parse_utc(old_item["captured_at"], "lineage.old.captured_at")
        new_captured = _parse_utc(item["captured_at"], "lineage.new.captured_at")
        assert old_issued is not None and new_issued is not None
        assert old_captured is not None and new_captured is not None
        if new_issued < old_issued or new_captured < old_captured:
            conflicts.add(item["id"])
            conflicts.add(old)
            continue
        prior = superseded_by.get(old)
        if prior is not None and prior != item["id"]:
            conflicts.update({old, prior, item["id"]})
        superseded_by[old] = item["id"]

    for start in list(by_id):
        seen: set[str] = set()
        cur = start
        while cur in superseded_by:
            if cur in seen:
                conflicts.update(seen)
                break
            seen.add(cur)
            cur = superseded_by[cur]
    return conflicts, superseded_by, set(by_id)


def _candidate_matches(req: dict[str, Any], ev: dict[str, Any], entity_id: str) -> bool:
    if ev["entity_id"] != entity_id or ev["category"] != req["category"]:
        return False
    if ev["subject_id"] != req["subject_id"]:
        return False
    if req["stage"] not in ev["stages"]:
        return False
    if ev["reuse_scope"] == "OPPORTUNITY_ONLY" and req["opportunity_id"] not in ev["opportunity_ids"]:
        return False
    if req["category"] == "FINANCIAL_STATEMENT" and ev["metadata"].get("financial_class") != req["required_financial_class"]:
        return False
    return True


def _state_for_evidence(
    ev: dict[str, Any], *, as_of: datetime, conflicts: set[str], superseded_by: dict[str, str]
) -> tuple[str, str]:
    if ev["id"] in conflicts:
        return "CONFLICT", "GENERATION_OR_LINEAGE_CONFLICT"
    issued = _parse_utc(ev["issued_at"], "internal.issued")
    captured = _parse_utc(ev["captured_at"], "internal.captured")
    expires = _parse_utc(ev["expires_at"], "internal.expires", nullable=True)
    revoked = _parse_utc(ev["revoked_at"], "internal.revoked", nullable=True)
    assert issued is not None and captured is not None
    if issued > as_of or captured > as_of:
        return "CONFLICT", "FUTURE_EVIDENCE_AT_CALLER_AS_OF"
    if ev["id"] in superseded_by:
        return "SUPERSEDED", f"SUPERSEDED_BY:{superseded_by[ev['id']]}"
    if revoked is not None and revoked <= as_of:
        return "SUPERSEDED", "REVOKED_AT_CALLER_AS_OF"
    if expires is not None and expires <= as_of:
        return "EXPIRED", "EXPIRED_AT_CALLER_AS_OF"
    if ev["verification_state"] != "VERIFIED" or ev["source_class"] == "SELF_ASSERTED":
        return "HOLD_PRIVATE_REVIEW", "CALLER_EVIDENCE_NOT_ASSERTED_VERIFIED"
    # This is intentionally only a candidate judgment over caller-supplied
    # bytes. No independent source root or current verifier clock is present.
    return "CANDIDATE_VERIFIED", "CALLER_ASSERTED_VERIFIED_CANDIDATE"
