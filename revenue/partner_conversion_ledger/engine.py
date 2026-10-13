from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .schema import (
    REPORT_SCHEMA, LedgerError, _canonical_time, _dt, canonical_bytes,
    sha256_bytes, validate_packet,
)

Owner = tuple[str, str]


@dataclass(frozen=True)
class CandidateAnalysis:
    state: str
    reasons: tuple[str, ...]
    action: str | None
    sent_count: int
    reply_count: int
    latest_event_at: str | None


def _provider_replay_owners(normalized: dict[str, Any]) -> tuple[set[Owner], set[Owner]]:
    """Return every candidate affected by message/thread identity replay.

    Provider message ids are event identities and therefore single-use across the
    whole packet, including within one candidate. Provider thread ids are allowed
    to repeat inside one candidate for conversation continuity, but a thread that
    appears under multiple candidates holds every owner rather than blessing the
    canonical first owner.
    """
    message_occurrences: dict[str, list[Owner]] = {}
    thread_owners: dict[str, set[Owner]] = {}
    for opp in normalized["opportunities"]:
        opp_id = opp["opportunity_id"]
        for cand in opp["candidates"]:
            owner = (opp_id, cand["candidate_id"])
            for event in cand["events"]:
                if event["type"] not in {"SENT", "REPLY"}:
                    continue
                message_occurrences.setdefault(event["provider_message_id"], []).append(owner)
                thread_owners.setdefault(event["provider_thread_id"], set()).add(owner)

    message_replay: set[Owner] = set()
    for owners in message_occurrences.values():
        if len(owners) > 1:
            message_replay.update(owners)

    thread_replay: set[Owner] = set()
    for owners in thread_owners.values():
        if len(owners) > 1:
            thread_replay.update(owners)
    return message_replay, thread_replay


def _analyze_candidate(
    opp_id: str,
    cand: dict[str, Any],
    now: datetime,
    qualification: dict[str, Any],
    *,
    provider_message_replay: bool = False,
    provider_thread_replay: bool = False,
) -> CandidateAnalysis:
    reasons: set[str] = set()
    if provider_message_replay:
        reasons.add("PROVIDER_MESSAGE_REPLAY")
    if provider_thread_replay:
        reasons.add("PROVIDER_THREAD_REPLAY")
    if _dt(qualification["captured_at"]) > now:
        reasons.add("QUALIFICATION_FROM_FUTURE")
    if _dt(qualification["valid_until"]) < now:
        reasons.add("QUALIFICATION_STALE")

    exceptions = {e["exception_id"]: e for e in cand["exceptions"]}
    used_exceptions: set[str] = set()
    sends: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []
    handoffs: list[dict[str, Any]] = []
    terminals: list[dict[str, Any]] = []

    for event in cand["events"]:
        event_time = _dt(event["at"])
        if terminals:
            reasons.add("EVENT_AFTER_TERMINAL")
        if event_time > now:
            reasons.add("EVENT_FROM_FUTURE")

        if event["type"] == "SENT":
            if event_time < _dt(qualification["captured_at"]):
                reasons.add("SEND_BEFORE_QUALIFICATION")
            if not sends:
                if event["exception_id"] is not None:
                    reasons.add("FIRST_SEND_MUST_NOT_USE_EXCEPTION")
            else:
                exc_id = event["exception_id"]
                if exc_id is None:
                    reasons.add("DUPLICATE_SEND_WITHOUT_EXCEPTION")
                elif exc_id in used_exceptions:
                    reasons.add("FOLLOWUP_EXCEPTION_REUSED")
                elif exc_id not in exceptions:
                    reasons.add("FOLLOWUP_EXCEPTION_MISSING")
                else:
                    exc = exceptions[exc_id]
                    if exc["prior_send_event_id"] != sends[-1]["event_id"]:
                        reasons.add("FOLLOWUP_EXCEPTION_WRONG_PRIOR_SEND")
                    if _dt(exc["approved_at"]) > event_time:
                        reasons.add("FOLLOWUP_EXCEPTION_APPROVED_AFTER_SEND")
                    if _dt(exc["expires_at"]) < event_time:
                        reasons.add("FOLLOWUP_EXCEPTION_EXPIRED")
                    used_exceptions.add(exc_id)
            sends.append(event)
        elif event["type"] == "REPLY":
            if not sends:
                reasons.add("REPLY_BEFORE_SEND")
            else:
                latest_send = sends[-1]
                if event_time < _dt(latest_send["at"]):
                    reasons.add("REPLY_BEFORE_SEND")
                if event["provider_thread_id"] != latest_send["provider_thread_id"]:
                    reasons.add("REPLY_THREAD_MISMATCH")
            replies.append(event)
        elif event["type"] == "HANDOFF":
            if not replies:
                reasons.add("HANDOFF_BEFORE_REPLY")
            else:
                latest_reply = replies[-1]
                if event_time < _dt(latest_reply["at"]):
                    reasons.add("HANDOFF_BEFORE_REPLY")
                if latest_reply["reply_class"] not in {"POSITIVE", "CONDITIONAL"}:
                    reasons.add("HANDOFF_WITHOUT_POSITIVE_REPLY")
            handoffs.append(event)
        elif event["type"] == "TERMINAL":
            if terminals:
                reasons.add("MULTIPLE_TERMINAL_EVENTS")
            if event["terminal_class"] == "DECLINED":
                if not replies or replies[-1]["reply_class"] != "NEGATIVE":
                    reasons.add("DECLINED_WITHOUT_NEGATIVE_REPLY")
            terminals.append(event)

    unused = sorted(set(exceptions) - used_exceptions)
    if unused:
        reasons.add("UNUSED_FOLLOWUP_EXCEPTION")

    latest = cand["events"][-1]["at"] if cand["events"] else None
    if reasons:
        return CandidateAnalysis("HOLD", tuple(sorted(reasons)), "RECONCILE_EVIDENCE", len(sends), len(replies), latest)
    if terminals:
        return CandidateAnalysis("TERMINAL", (), None, len(sends), len(replies), latest)
    if handoffs:
        return CandidateAnalysis("HANDOFF_COMPLETE", (), None, len(sends), len(replies), latest)
    if replies:
        return CandidateAnalysis("REPLY_REVIEW_REQUIRED", (), "REVIEW_REPLY", len(sends), len(replies), latest)
    if sends:
        return CandidateAnalysis("AWAITING_REPLY", (), None, len(sends), len(replies), latest)
    return CandidateAnalysis("READY_FOR_OWNER_REVIEW", (), "REVIEW_INITIAL_CONTACT", 0, 0, latest)


def _compile_at(packet: Any, evaluated_at: str) -> dict[str, Any]:
    evaluated_at = _canonical_time(evaluated_at, name="evaluated_at")
    now = _dt(evaluated_at)
    normalized = validate_packet(packet)
    input_sha = sha256_bytes(canonical_bytes(normalized))
    message_replay, thread_replay = _provider_replay_owners(normalized)
    opp_reports: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    counts = {state: 0 for state in ["READY_FOR_OWNER_REVIEW", "AWAITING_REPLY", "REPLY_REVIEW_REQUIRED", "HANDOFF_COMPLETE", "TERMINAL", "HOLD"]}

    for opp in normalized["opportunities"]:
        candidate_reports: list[dict[str, Any]] = []
        for cand in opp["candidates"]:
            owner = (opp["opportunity_id"], cand["candidate_id"])
            analysis = _analyze_candidate(
                opp["opportunity_id"], cand, now, opp["qualification"],
                provider_message_replay=owner in message_replay,
                provider_thread_replay=owner in thread_replay,
            )
            counts[analysis.state] += 1
            report = {
                "candidate_id": cand["candidate_id"],
                "org_ref": cand["org_ref"],
                "route_digest": cand["route_digest"],
                "fit_evidence_sha256": sha256_bytes(canonical_bytes(cand["fit_evidence"])),
                "event_log_sha256": sha256_bytes(canonical_bytes(cand["events"])),
                "exception_set_sha256": sha256_bytes(canonical_bytes(cand["exceptions"])),
                "state": analysis.state,
                "reasons": list(analysis.reasons),
                "sent_count": analysis.sent_count,
                "reply_count": analysis.reply_count,
                "latest_event_at": analysis.latest_event_at,
            }
            candidate_reports.append(report)
            if analysis.action is not None:
                queue.append({
                    "opportunity_id": opp["opportunity_id"],
                    "candidate_id": cand["candidate_id"],
                    "action": analysis.action,
                    "reasons": list(analysis.reasons),
                })
        if any(c["state"] == "HOLD" for c in candidate_reports):
            opp_state = "HOLD"
        elif any(c["state"] in {"READY_FOR_OWNER_REVIEW", "REPLY_REVIEW_REQUIRED"} for c in candidate_reports):
            opp_state = "OWNER_REVIEW_REQUIRED"
        elif all(c["state"] in {"TERMINAL", "HANDOFF_COMPLETE"} for c in candidate_reports):
            opp_state = "COMPLETE"
        else:
            opp_state = "MONITORING"
        opp_reports.append({
            "opportunity_id": opp["opportunity_id"],
            "qualification_digest": opp["qualification"]["digest"],
            "qualification_source_set_sha256": sha256_bytes(canonical_bytes(opp["qualification"]["source_refs"])),
            "state": opp_state,
            "candidates": candidate_reports,
        })

    authority = {
        "send_authorized": False,
        "followup_authorized": False,
        "partner_selection_authorized": False,
        "submission_authorized": False,
        "pricing_authorized": False,
        "spend_authorized": False,
        "contract_authorized": False,
        "payment_authorized": False,
        "revenue_authorized": False,
    }
    core = {
        "schema": REPORT_SCHEMA,
        "ledger_id": normalized["ledger_id"],
        "evaluated_at": evaluated_at,
        "input_sha256": input_sha,
        "opportunities": opp_reports,
        "owner_review_queue": sorted(queue, key=lambda x: (x["opportunity_id"], x["candidate_id"], x["action"])),
        "summary": {**counts, "opportunity_count": len(opp_reports), "candidate_count": sum(counts.values())},
        "authority": authority,
    }
    markdown = render_markdown_core(core)
    report = {**core, "markdown_sha256": sha256_bytes(markdown.encode("utf-8"))}
    report["receipt_sha256"] = sha256_bytes(canonical_bytes(report))
    return report


def _make_current_compiler(_compile=_compile_at, _datetime=datetime, _timezone=timezone):
    """Bind process-UTC primitives once so helper-global rebinding cannot select time."""
    def current(packet: Any) -> dict[str, Any]:
        evaluated_at = _datetime.now(_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return _compile(packet, evaluated_at)
    return current


compile_current = _make_current_compiler()


def verify_historical(packet: Any, report: Any) -> bool:
    if type(report) is not dict:
        return False
    evaluated_at = report.get("evaluated_at")
    if type(evaluated_at) is not str:
        return False
    try:
        expected = _compile_at(packet, evaluated_at)
        return canonical_bytes(expected) == canonical_bytes(report)
    except LedgerError:
        return False


def _semantic_projection(report: dict[str, Any]) -> dict[str, Any]:
    keys = ["ledger_id", "input_sha256", "opportunities", "owner_review_queue", "summary", "authority"]
    return {key: report.get(key) for key in keys}


def _make_current_verifier(
    _verify_historical=verify_historical,
    _current=compile_current,
    _canonical=canonical_bytes,
    _projection=_semantic_projection,
):
    """Bind the current compiler once; ordinary module-global rebinding cannot stale it."""
    def current(packet: Any, report: Any) -> bool:
        if not _verify_historical(packet, report):
            return False
        try:
            fresh = _current(packet)
        except LedgerError:
            return False
        return _canonical(_projection(fresh)) == _canonical(_projection(report))
    return current


verify_current = _make_current_verifier()


def render_markdown_core(core: dict[str, Any]) -> str:
    lines = [
        "# Partner Conversion Ledger",
        "",
        f"Ledger: `{core['ledger_id']}`",
        f"Evaluated: `{core['evaluated_at']}`",
        "",
        "## Owner review queue",
    ]
    queue = core["owner_review_queue"]
    if not queue:
        lines.append("- No owner-review action is currently queued.")
    else:
        for row in queue:
            reasons = ", ".join(row["reasons"]) if row["reasons"] else "none"
            lines.append(f"- `{row['opportunity_id']}` / `{row['candidate_id']}` — **{row['action']}** (reasons: {reasons})")
    lines.extend(["", "## Opportunity states"])
    for opp in core["opportunities"]:
        lines.append(f"- `{opp['opportunity_id']}` — **{opp['state']}**")
        for cand in opp["candidates"]:
            reasons = ", ".join(cand["reasons"]) if cand["reasons"] else "none"
            lines.append(f"  - `{cand['candidate_id']}` / `{cand['org_ref']}` — `{cand['state']}`; reasons: {reasons}")
    lines.extend([
        "",
        "## Authority ceiling",
        "This artifact is evidence/control only. It grants **no** send, follow-up, partner-selection, submission, pricing, spend, contract, payment, or revenue authority.",
        "",
    ])
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    core = {k: report[k] for k in ["schema", "ledger_id", "evaluated_at", "input_sha256", "opportunities", "owner_review_queue", "summary", "authority"]}
    return render_markdown_core(core)
