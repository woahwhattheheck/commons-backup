from __future__ import annotations

from datetime import datetime
from typing import Any

from .lineage import _candidate_matches, _state_for_evidence


def _resolve_requirement(
    req: dict[str, Any], evidence: list[dict[str, Any]], entity_id: str, as_of: datetime,
    conflicts: set[str], superseded_by: dict[str, str]
) -> dict[str, Any]:
    candidates = [ev for ev in evidence if _candidate_matches(req, ev, entity_id)]
    if not candidates:
        return {
            "requirement_id": req["id"], "category": req["category"], "stage": req["stage"],
            "state": "MISSING", "reason": "NO_APPLICABLE_EVIDENCE", "evidence_id": None,
            "evidence_sha256": None,
        }

    evaluated = [(ev, *_state_for_evidence(ev, as_of=as_of, conflicts=conflicts, superseded_by=superseded_by)) for ev in candidates]
    positive = [(ev, reason) for ev, state, reason in evaluated if state == "CANDIDATE_VERIFIED"]
    if len(positive) == 1:
        ev, reason = positive[0]
        return {
            "requirement_id": req["id"], "category": req["category"], "stage": req["stage"],
            "state": "CANDIDATE_VERIFIED", "reason": reason, "evidence_id": ev["id"],
            "evidence_sha256": ev["content_sha256"],
        }
    if len(positive) > 1:
        return {
            "requirement_id": req["id"], "category": req["category"], "stage": req["stage"],
            "state": "CONFLICT", "reason": "MULTIPLE_CANDIDATE_GENERATIONS", "evidence_id": None,
            "evidence_sha256": None,
        }

    precedence = ["CONFLICT", "HOLD_PRIVATE_REVIEW", "EXPIRED", "SUPERSEDED"]
    for target in precedence:
        subset = [(ev, reason) for ev, state, reason in evaluated if state == target]
        if subset:
            ev, reason = sorted(subset, key=lambda p: p[0]["id"])[0]
            return {
                "requirement_id": req["id"], "category": req["category"], "stage": req["stage"],
                "state": target, "reason": reason, "evidence_id": ev["id"],
                "evidence_sha256": ev["content_sha256"],
            }
    raise AssertionError("unreachable requirement state")
