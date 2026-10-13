"""Export deadline-review metadata to the existing command-center ingest contract.

Offline only: constructing this payload never posts, schedules or dispatches it.
Source authority labels are upstream declarations, not authenticated buyer facts.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import timedelta
from typing import Any, Sequence

from .engine import (
    AUTHORITY_CEILING, EvidenceError, _system_now, _utc, canonical_bytes,
    compile_portfolio, digest, read_bounded_json, write_new_file,
)

PORTFOLIO_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
PROVIDER = "opportunity-deadline-command"
TERMINAL_STATES = {"EXPIRED", "TERMINAL_NO_BID"}
NEXT_ACTION = {
    "SOURCE_RECOVERY_REQUIRED": "Recover the controlling source or missing deadline; recompile after review.",
    "ADDENDA_REVIEW_REQUIRED": "Check official addenda and deadline changes before planning further action.",
    "QUESTION_WINDOW_OPEN": "Review unresolved questions with the pursuit owner; no contact is authorized.",
    "CONFERENCE_ACTION_REVIEW": "Review the conference milestone with the pursuit owner; no registration is authorized.",
    "REGISTRATION_ACTION_REVIEW": "Review registration requirements with the pursuit owner; no registration is authorized.",
    "RESPONSE_DUE_SOON": "Review response readiness and owner-only blockers before the recorded cutoff.",
    "RESPONSE_WINDOW_OPEN": "Review response preparation and owner-only blockers against the recorded cutoff.",
    "NOT_YET_OPEN": "Review preparation needs; the recorded response window is not yet open.",
    "EXPIRED": "Retain the observed closed window as history; no new deadline is inferred.",
    "TERMINAL_NO_BID": "Retain the owner-supplied no-bid state; do not reopen automatically.",
    "HOLD": "Resolve the route or source uncertainty with the pursuit owner.",
}


def _freshness_budget(raw_input: Any, raw_policy: Any, result: dict[str, Any]) -> int:
    """Mark observations stale before any known time-based classification change."""
    now = _utc(result["manifest"]["as_of"], "$snapshot.as_of")
    boundaries = []
    for opportunity in raw_input["opportunities"]:
        for source in opportunity["sources"]:
            boundaries.append(_utc(source["captured_at"], "$snapshot.captured_at")
                              + timedelta(minutes=raw_policy["max_source_age_minutes"], seconds=1))
    for row in result["rows"]:
        for deadline in row["deadlines"]:
            at = _utc(deadline["at"], "$snapshot.deadline.at")
            if at <= now:
                continue
            boundaries.append(at)
            for window in ("critical_window_minutes", "high_window_minutes", "addenda_review_window_minutes"):
                boundaries.append(at - timedelta(minutes=raw_policy[window]))
            if deadline["opens_at"] is not None:
                boundaries.append(_utc(deadline["opens_at"], "$snapshot.opens_at"))
    # WorkstreamStore marks stale at age > threshold, so subtract one second.
    future = [int((at - now).total_seconds()) - 1 for at in boundaries if at > now]
    return max(0, min([300, *future]))


def build_work_snapshot(raw_input: Any, raw_policy: Any, *, portfolio_ref: str) -> dict[str, Any]:
    """Compile at process UTC and prepare one selected-metadata ingest payload.

    This is not a complete fleet census. Omitted rows are never deleted from the
    native store, and derived review rows never count as new work or revenue.
    Reuse the exact returned payload after an uncertain ingest; do not recompile
    merely to mint a new operation ID and repeat the same provider effect.
    """
    if type(portfolio_ref) is not str or not PORTFOLIO_REF.fullmatch(portfolio_ref):
        raise EvidenceError("portfolio_ref must be an opaque 1-64 character identifier")
    result = compile_portfolio(raw_input, raw_policy, as_of=_system_now())
    manifest = result["manifest"]
    source_id = f"opportunity-deadlines:{portfolio_ref}"
    items = []
    for rank, row in enumerate(result["rows"], start=1):
        state = row["operating_state"]
        deadline = row["next_deadline"]
        items.append({
            "id": row["opportunity_id"],
            "kind": "opportunity_deadline",
            "row_type": "control",
            "control": True,
            "countable": False,
            "title": row["title"],
            "status": state,
            "priority": row["priority"],
            "owner": row["owner_ref"],
            "project": "Opportunity deadlines",
            "url": row["controlling_source"]["url"],
            "due_at": None if deadline is None else deadline["at"],
            "summary": f"{row['buyer']} / {row['solicitation_id']}. {AUTHORITY_CEILING}",
            "next_action": ("" if deadline is None else
                            f"Recorded cutoff: {deadline['kind']} at {deadline['at']}. ") + NEXT_ACTION[state],
            "needs_attention": state not in TERMINAL_STATES,
            "attention_reason": "; ".join(row["reason_codes"]) or state,
            "actions": [],
            "metadata": {
                "evaluation_rank": rank,
                "evaluated_at": manifest["as_of"],
                "receipt_sha256": manifest["receipt_sha256"],
                "route_state": row["route_state"],
                "packet_state": row["packet_state"],
                "declared_controlling_source": row["controlling_source"],
                "declared_next_deadline": deadline,
                "blocker_codes": row["blocker_codes"],
                "owner_action_refs": row["owner_action_refs"],
                "evidence_kind": "UPSTREAM_SOURCE_DECLARATIONS",
                "external_action_authorized": False,
            },
        })
    payload = {
        "source": {
            "id": source_id,
            "provider": PROVIDER,
            "label": f"Deadline review / {portfolio_ref}",
            "sync_mode": "connector_fed",
            "observed_at": manifest["as_of"],
            "scope": {"portfolio_ref": portfolio_ref, "selection": "owner-review-metadata"},
            "coverage": {
                "complete": False,
                "pagination_remaining": False,
                "notes": "Selected supplied records, not a fleet census. Omitted items remain retained.",
            },
            "status": "ok",
            "stale_after_seconds": _freshness_budget(raw_input, raw_policy, result),
            "metadata": {
                "input_sha256": manifest["input_sha256"],
                "policy_sha256": manifest["policy_sha256"],
                "receipt_sha256": manifest["receipt_sha256"],
                "evaluated_at": manifest["as_of"],
                "observed_at_means": "derived queue computation, not a buyer-source refresh",
                "external_action_authorized": False,
            },
        },
        "items": items,
    }
    # The identity binds every emitted byte, including scope and observation time.
    return {"operation_id": "deadline-ingest:" + digest(payload), **payload}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--portfolio-ref", required=True)
    parser.add_argument("--snapshot-out", required=True)
    args = parser.parse_args(argv)
    try:
        snapshot = build_work_snapshot(read_bounded_json(args.input), read_bounded_json(args.policy),
                                       portfolio_ref=args.portfolio_ref)
        write_new_file(args.snapshot_out, canonical_bytes(snapshot) + b"\n")
    except (EvidenceError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(snapshot["operation_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
