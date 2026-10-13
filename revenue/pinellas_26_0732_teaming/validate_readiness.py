#!/usr/bin/env python3
"""Fail-closed readiness compiler for Pinellas 26-0732-REQ teaming prep.

This program never sends email, contacts the buyer, submits to OpenGov, or
accepts a contract. It only evaluates a local JSON carrier.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HOLD = "HOLD_AWAITING_TEAMING_CONFIRMATION"
READY = "READY_FOR_PRIME_TEAMING_REVIEW"
CLOSED = "CLOSED_NO_FIT"
ALLOWED_GATE_STATUS = {"PROVEN", "HOLD", "MISSING", "NOT_APPLICABLE"}


def _evidence(entry):
    refs = entry.get("evidence", []) if isinstance(entry, dict) else []
    return isinstance(refs, list) and bool(refs) and all(
        isinstance(ref, str) and ref.strip() for ref in refs
    )


def _require_proven(name, entry, reasons):
    status = entry.get("status") if isinstance(entry, dict) else None
    if status not in ALLOWED_GATE_STATUS:
        reasons.append(f"{name}: invalid status")
    elif status != "PROVEN":
        reasons.append(f"{name}: {status}")
    elif not _evidence(entry):
        reasons.append(f"{name}: proven without evidence")


def _valid_fee(workshare, reasons):
    fee = workshare.get("proposed_fixed_fee_usd")
    if not isinstance(fee, int) or isinstance(fee, bool) or fee != 15000:
        reasons.append("proposed fee must be exact integer USD 15000")
    if workshare.get("currency") != "USD":
        reasons.append("currency must be USD")
    if workshare.get("commercial_status") != "PROPOSED_INTERNAL_NOT_SENT":
        reasons.append("commercial status must remain PROPOSED_INTERNAL_NOT_SENT")
    if workshare.get("binding") is not False:
        reasons.append("workshare binding must remain false")
    expected = [
        ("written_authorization_and_kickoff", "0.40", 6000),
        ("draft_specialist_package", "0.40", 6000),
        ("accepted_final_specialist_package", "0.20", 3000),
    ]
    got = workshare.get("payment_milestones")
    if not isinstance(got, list) or len(got) != len(expected):
        reasons.append("payment milestones malformed")
        return
    for idx, (name, fraction, amount) in enumerate(expected):
        row = got[idx]
        if not isinstance(row, dict):
            reasons.append(f"payment milestone {idx}: malformed")
            continue
        if row.get("name") != name or row.get("fraction") != fraction:
            reasons.append(f"payment milestone {idx}: identity/fraction mismatch")
        value = row.get("amount_usd")
        if not isinstance(value, int) or isinstance(value, bool) or value != amount:
            reasons.append(f"payment milestone {idx}: amount mismatch")


def check(opportunity, state, workshare, now=None):
    reasons = []

    if opportunity.get("opportunity_id") != "PINELLAS-26-0732-REQ":
        reasons.append("wrong opportunity_id")
    if state.get("opportunity_id") != "PINELLAS-26-0732-REQ":
        reasons.append("state opportunity mismatch")

    route = opportunity.get("submission_route", {})
    if route.get("carrier_may_submit") is not False:
        reasons.append("carrier_may_submit must remain false")
    if route.get("county_contact_authorized") is not False:
        reasons.append("county contact authority must remain false")

    boundary = opportunity.get("source_boundary", {})
    if boundary.get("invent_missing_requirements") is not False:
        reasons.append("invent_missing_requirements must remain false")

    thread = state.get("thread_state", {})
    if thread.get("correction_sent") is not True:
        reasons.append("existing correction receipt missing")
    if thread.get("dnr_until_new_human_procurement_teaming_event") is not True:
        reasons.append("outbound DNR must remain true")
    if thread.get("parallel_contact_forbidden") is not True:
        reasons.append("parallel contact fence must remain true")
    if thread.get("recruiter_authority") is not False:
        reasons.append("recruiter_authority must remain false")
    if thread.get("county_contact_authority") is not False:
        reasons.append("county_contact_authority must remain false")

    confidential = state.get("confidential_material", {})
    if confidential.get("consultant_profile_received") is not True:
        reasons.append("confidential-profile receipt state missing")
    for key in (
        "consultant_profile_use_allowed",
        "consultant_profile_forward_allowed",
        "consultant_contact_allowed",
        "profile_content_present_in_carrier",
    ):
        if confidential.get(key) is not False:
            reasons.append(f"{key} must remain false")

    authority = state.get("external_authority", {})
    for key in (
        "email_send_authorized",
        "county_submission_authorized",
        "contract_acceptance_authorized",
        "spend_authorized",
        "revenue_recognized",
    ):
        if authority.get(key) is not False:
            reasons.append(f"{key} must remain false")

    # Safety/identity/privacy reasons are captured before ordinary commercial
    # readiness checks so CLOSED_NO_FIT can ignore stale pricing/deadline gates
    # without ever bypassing anti-spam, private-material, or authority fences.
    safety_reasons = list(reasons)

    _valid_fee(workshare, reasons)

    deadline = opportunity.get("deadline", {})
    try:
        wall = dt.datetime.fromisoformat(deadline["local"])
        if wall.tzinfo is not None:
            raise ValueError("deadline.local must be offset-free")
        due = wall.replace(tzinfo=ZoneInfo(deadline["iana_zone"]))
    except Exception as exc:
        reasons.append(f"invalid deadline: {exc}")
        due = None
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if due is not None and now.astimezone(dt.timezone.utc) >= due.astimezone(dt.timezone.utc):
        reasons.append("deadline expired")

    disposition = state.get("disposition")
    if disposition == CLOSED:
        closeout_reasons = []
        closeout = state.get("closeout", {})
        if not isinstance(closeout.get("reason"), str) or not closeout["reason"].strip():
            closeout_reasons.append("closeout reason missing")
        if not _evidence(closeout):
            closeout_reasons.append("closeout evidence missing")
        blockers = safety_reasons + closeout_reasons
        return (CLOSED if not blockers else HOLD), blockers
    if disposition != "ACTIVE_HOLD":
        reasons.append("invalid disposition")

    gates = state.get("gates", {})
    for name in (
        "new_human_procurement_teaming_confirmation",
        "live_public_deadline_recheck",
        "complete_controlling_packet_or_prime_requirement_set",
        "owner_commercial_terms_approved",
    ):
        _require_proven(name, gates.get(name, {}), reasons)

    if thread.get("latest_human_event_kind") != "PROCUREMENT_TEAMING_CONFIRMATION":
        reasons.append("latest human event is not procurement teaming confirmation")
    if thread.get("awaiting_new_human_reply") is not False:
        reasons.append("still awaiting new human reply")

    return (READY if not reasons else HOLD), reasons


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 3:
        print("usage: validate_readiness.py OPPORTUNITY.json STATE.json WORKSHARE.json", file=sys.stderr)
        return 2
    state_name, reasons = check(_load(argv[0]), _load(argv[1]), _load(argv[2]))
    print(json.dumps({"state": state_name, "reasons": reasons}, indent=2, sort_keys=True))
    return 0 if state_name in {READY, CLOSED} else 3


if __name__ == "__main__":
    raise SystemExit(main())
