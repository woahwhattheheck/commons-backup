"""Deterministic synthetic acceptance fixture for the MRHD evidence rail."""

from __future__ import annotations

import json
from typing import Any

from .rail import ELIGIBLE_GEOGRAPHIES, FOCUS_CATEGORIES

FIXTURE_EVENT_COUNT = 180


def _event(
    sequence: int,
    event_type: str,
    award_id: str,
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id or f"evt-{sequence:03d}",
        "sequence": sequence,
        "event_type": event_type,
        "award_id": award_id,
        "payload": payload,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """Return exactly 180 synthetic events covering promised hostile cases."""
    records: list[dict[str, Any]] = []
    seq = 1

    for i in range(20):
        award_id = f"SYN-AWARD-{i+1:02d}"
        award_cents = (100_000 + i * 4_000) * 100
        required = award_cents // 4
        records.append(
            _event(
                seq,
                "AWARD_APPROVED",
                award_id,
                {
                    "applicant_id": f"SYN-APPLICANT-{i+1:02d}",
                    "project_id": f"SYN-PROJECT-{i+1:02d}",
                    "cycle_id": "SYN-2026-IMPACT-MATCH",
                    "category": FOCUS_CATEGORIES[i % len(FOCUS_CATEGORIES)],
                    "geography": ELIGIBLE_GEOGRAPHIES[i % len(ELIGIBLE_GEOGRAPHIES)],
                    "award_cents": award_cents,
                    "required_match_cents": required,
                },
            )
        )
        seq += 1

        cash_commit = (required * 3) // 4
        inkind_commit = required - cash_commit
        records.append(
            _event(
                seq,
                "MATCH_COMMITMENT",
                award_id,
                {
                    "commitment_id": f"{award_id}-CASH",
                    "kind": "cash",
                    "committed_cents": cash_commit,
                    "source_id": f"SYN-CASH-SOURCE-{i+1:02d}",
                },
            )
        )
        seq += 1
        records.append(
            _event(
                seq,
                "MATCH_COMMITMENT",
                award_id,
                {
                    "commitment_id": f"{award_id}-INKIND",
                    "kind": "in_kind",
                    "committed_cents": inkind_commit,
                    "source_id": f"SYN-INKIND-SOURCE-{i+1:02d}",
                    "valuation_method": "synthetic-approved-rate-card",
                    "evidence_hash": f"sha256:syn-commit-{i+1:02d}",
                },
            )
        )
        seq += 1
        records.append(
            _event(
                seq,
                "CONTRIBUTION_VERIFIED",
                award_id,
                {
                    "commitment_id": f"{award_id}-CASH",
                    "realized_cents": cash_commit,
                    "evidence_hash": f"sha256:syn-cash-{i+1:02d}",
                    "reviewer_id": "SYN-MRHD-REVIEWER",
                },
            )
        )
        seq += 1
        records.append(
            _event(
                seq,
                "CONTRIBUTION_VERIFIED",
                award_id,
                {
                    "commitment_id": f"{award_id}-INKIND",
                    "realized_cents": inkind_commit,
                    "evidence_hash": f"sha256:syn-inkind-{i+1:02d}",
                    "reviewer_id": "SYN-MRHD-REVIEWER",
                },
            )
        )
        seq += 1
        records.append(
            _event(
                seq,
                "MILESTONE_RECORDED",
                award_id,
                {
                    "milestone_id": f"{award_id}-M1",
                    "due_on": "2027-04-22",
                    "observed_on": "2027-04-20",
                    "status": "complete",
                    "evidence_hash": f"sha256:syn-mile-{i+1:02d}",
                },
            )
        )
        seq += 1
        records.append(
            _event(
                seq,
                "PARTNER_CHANGED",
                award_id,
                {
                    "partner_id": f"SYN-PARTNER-{i+1:02d}",
                    "change": "added",
                    "approval_ref": f"SYN-APPROVAL-{i+1:02d}",
                },
            )
        )
        seq += 1
        records.append(
            _event(
                seq,
                "CLOSEOUT_REQUESTED",
                award_id,
                {
                    "closeout_id": f"SYN-CLOSEOUT-{i+1:02d}",
                    "evidence_hash": f"sha256:syn-closeout-{i+1:02d}",
                },
            )
        )
        seq += 1

    records.append(
        _event(
            seq,
            "AMENDMENT_APPROVED",
            "SYN-AWARD-01",
            {
                "amendment_id": "SYN-AMEND-01",
                "approver_id": "SYN-MRHD-APPROVER",
                "new_award_cents": 104_000 * 100,
                "new_required_match_cents": 26_000 * 100,
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "RETURN_RECORDED",
            "SYN-AWARD-02",
            {
                "return_id": "SYN-RETURN-01",
                "amount_cents": 1_000 * 100,
                "evidence_hash": "sha256:syn-return-01",
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "MILESTONE_RECORDED",
            "SYN-AWARD-03",
            {
                "milestone_id": "SYN-AWARD-03-LATE",
                "due_on": "2027-02-01",
                "observed_on": "2027-02-03",
                "status": "complete",
                "evidence_hash": "sha256:syn-late",
            },
        )
    )
    seq += 1

    cap_award = "SYN-AWARD-04"
    records.append(
        _event(
            seq,
            "MATCH_COMMITMENT",
            cap_award,
            {
                "commitment_id": f"{cap_award}-EXTRA-INKIND",
                "kind": "in_kind",
                "committed_cents": 10_000 * 100,
                "source_id": "SYN-EXTRA-INKIND-SOURCE",
                "valuation_method": "synthetic-revised-valuation",
                "evidence_hash": "sha256:syn-extra-inkind-commit",
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "CONTRIBUTION_VERIFIED",
            cap_award,
            {
                "commitment_id": f"{cap_award}-EXTRA-INKIND",
                "realized_cents": 10_000 * 100,
                "evidence_hash": "sha256:syn-extra-inkind-realized",
                "reviewer_id": "SYN-MRHD-REVIEWER",
            },
        )
    )
    seq += 1

    records.append(
        _event(
            seq,
            "MATCH_COMMITMENT",
            "SYN-AWARD-01",
            {
                "commitment_id": "SYN-AWARD-01-AMENDMENT-GAP",
                "kind": "cash",
                "committed_cents": 1_000 * 100,
                "source_id": "SYN-PENDING-CASH",
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "PARTNER_CHANGED",
            "SYN-AWARD-05",
            {
                "partner_id": "SYN-PARTNER-05",
                "change": "updated",
                "approval_ref": "SYN-PARTNER-CHANGE-APPROVAL",
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "CONTRIBUTION_VERIFIED",
            "SYN-AWARD-06",
            {
                "commitment_id": "NO-SUCH-COMMITMENT",
                "realized_cents": 500 * 100,
                "evidence_hash": "sha256:syn-unmatched",
                "reviewer_id": "SYN-MRHD-REVIEWER",
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "MILESTONE_RECORDED",
            "SYN-AWARD-07",
            {
                "milestone_id": "SYN-AWARD-07-PARTIAL",
                "due_on": "2027-03-01",
                "observed_on": "2027-03-01",
                "status": "partial",
                "evidence_hash": "sha256:syn-partial",
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "MILESTONE_RECORDED",
            "SYN-AWARD-08",
            {
                "milestone_id": "SYN-AWARD-08-MISSED",
                "due_on": "2027-03-01",
                "observed_on": "2027-03-02",
                "status": "missed",
                "evidence_hash": "sha256:syn-missed",
            },
        )
    )
    seq += 1

    original = next(r for r in records if r["event_id"] == "evt-012")
    records.append(json.loads(json.dumps(original, sort_keys=True)))
    original2 = next(r for r in records if r["event_id"] == "evt-044")
    records.append(json.loads(json.dumps(original2, sort_keys=True)))

    conflict = json.loads(
        json.dumps(next(r for r in records if r["event_id"] == "evt-052"))
    )
    conflict["payload"]["evidence_hash"] = "sha256:changed-after-timeout"
    records.append(conflict)

    records.append(
        _event(
            seq,
            "MILESTONE_RECORDED",
            "SYN-AWARD-99",
            {
                "milestone_id": "UNKNOWN",
                "due_on": "2027-01-01",
                "observed_on": "2027-01-01",
                "status": "complete",
                "evidence_hash": "sha256:unknown-award",
            },
        )
    )
    seq += 1
    records.append(
        _event(
            1,
            "MILESTONE_RECORDED",
            "SYN-AWARD-09",
            {
                "milestone_id": "COLLISION",
                "due_on": "2027-01-01",
                "observed_on": "2027-01-01",
                "status": "complete",
                "evidence_hash": "sha256:sequence-collision",
            },
            event_id="evt-sequence-collision",
        )
    )

    records.append(
        _event(
            seq,
            "AWARD_APPROVED",
            "SYN-AWARD-10",
            {
                "applicant_id": "SYN-DUPLICATE",
                "project_id": "SYN-DUPLICATE",
                "cycle_id": "SYN-2026-IMPACT-MATCH",
                "category": FOCUS_CATEGORIES[0],
                "geography": ELIGIBLE_GEOGRAPHIES[0],
                "award_cents": 100_000 * 100,
                "required_match_cents": 25_000 * 100,
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "AWARD_APPROVED",
            "SYN-AWARD-BAD-GEO",
            {
                "applicant_id": "SYN-BAD-GEO",
                "project_id": "SYN-BAD-GEO",
                "cycle_id": "SYN-2026-IMPACT-MATCH",
                "category": FOCUS_CATEGORIES[0],
                "geography": "IA:NotEligible",
                "award_cents": 100_000 * 100,
                "required_match_cents": 25_000 * 100,
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "AWARD_APPROVED",
            "SYN-AWARD-BAD-CAT",
            {
                "applicant_id": "SYN-BAD-CAT",
                "project_id": "SYN-BAD-CAT",
                "cycle_id": "SYN-2026-IMPACT-MATCH",
                "category": "not_a_focus_area",
                "geography": ELIGIBLE_GEOGRAPHIES[0],
                "award_cents": 100_000 * 100,
                "required_match_cents": 25_000 * 100,
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "RETURN_RECORDED",
            "SYN-AWARD-11",
            {
                "return_id": "SYN-RETURN-OVERFLOW",
                "amount_cents": 999_999 * 100,
                "evidence_hash": "sha256:syn-return-overflow",
            },
        )
    )
    seq += 1
    records.append(
        _event(
            seq,
            "CONTRIBUTION_VERIFIED",
            "SYN-AWARD-12",
            {
                "commitment_id": "SYN-AWARD-12-CASH",
                "realized_cents": 999_999 * 100,
                "evidence_hash": "sha256:syn-over-realized",
                "reviewer_id": "SYN-MRHD-REVIEWER",
            },
        )
    )
    seq += 1

    if len(records) != FIXTURE_EVENT_COUNT:
        raise AssertionError(
            f"fixture contract requires {FIXTURE_EVENT_COUNT} events, got {len(records)}"
        )
    return records
