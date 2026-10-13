"""Deterministic, read-only inbound commercial response controller.

This module compiles retained provider truth into a response queue.  It has no
provider, messaging, calendar, pricing, contract, payment, or revenue authority.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "inbound-lead-control/v1"

_STATES = {
    "NEW_INBOUND_UNANSWERED",
    "WAITING_ON_COUNTERPARTY",
    "COLLISION_HOLD",
    "CENSUS_HOLD",
    "OWNER_DECISION_REQUIRED",
    "CHECK_CALENDAR_REQUIRED",
    "ROUTE_FAILURE_HOLD",
    "NO_INBOUND_SIGNAL",
    "EVIDENCE_HOLD",
}
_EVENT_KINDS = {"HUMAN_INBOUND", "OUTBOUND_SENT", "BOUNCE", "MUSE_SELECTED"}
_STATE_DRIVING_EVENT_KINDS = {"HUMAN_INBOUND", "OUTBOUND_SENT", "BOUNCE"}
_INTENTS = {"GENERAL", "MEETING", "BINDING_TERMS"}
_PRIORITIES = {"HOT", "WARM", "GENERAL"}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+~-]{0,199}$")


class InputError(ValueError):
    """The retained input is malformed or self-contradictory."""


def _obj(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InputError(f"{name} must be an object")
    return value


def _list(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise InputError(f"{name} must be an array")
    return value


def _text(value: Any, name: str, *, max_len: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise InputError(f"{name} must be non-empty text <= {max_len} chars")
    return value


def _ident(value: Any, name: str) -> str:
    text = _text(value, name, max_len=200)
    if not _ID.fullmatch(text):
        raise InputError(f"{name} has unsafe identifier syntax")
    return text


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise InputError(f"{name} must be a boolean")
    return value


def _int(value: Any, name: str, *, minimum: int = 0, maximum: int = 525600) -> int:
    if type(value) is not int or not (minimum <= value <= maximum):
        raise InputError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _utc(value: Any, name: str) -> datetime:
    text = _text(value, name, max_len=40)
    if not text.endswith("Z"):
        raise InputError(f"{name} must use UTC Z form")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise InputError(f"{name} is not valid ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise InputError(f"{name} must be UTC")
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    if text != canonical:
        raise InputError(f"{name} must be canonical second-precision UTC")
    return parsed


def _sha(value: Any, name: str) -> str:
    text = _text(value, name, max_len=64)
    if not _HEX64.fullmatch(text):
        raise InputError(f"{name} must be lowercase sha256 hex")
    return text


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _receipt(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _scope_key(route: str, thread: str) -> str:
    return f"{route}\x1f{thread}"


def _event_semantic_key(event: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        event["kind"],
        event["route_key"],
        event["thread_key"],
        event["occurred_utc"],
        event["content_sha256"],
    )


def _reject_ambiguous_chronology(events: Sequence[Mapping[str, Any]], lead: Mapping[str, Any]) -> None:
    """Fail closed when retained second precision cannot authenticate event order."""

    route = lead["route_key"]
    thread = lead["thread_key"]
    by_second: dict[str, list[Mapping[str, Any]]] = {}
    for event in events:
        if event["kind"] not in _STATE_DRIVING_EVENT_KINDS:
            continue
        if event["route_key"] != route or event["thread_key"] != thread:
            continue
        by_second.setdefault(event["occurred_utc"], []).append(event)

    for occurred, tied in sorted(by_second.items()):
        if len(tied) <= 1:
            continue
        event_ids = sorted(str(event["event_id"]) for event in tied)
        raise InputError(
            "chronology ambiguity: state-driving events share "
            f"route/thread second {occurred}: {event_ids}"
        )


def _validate_event(raw: Any, lead_id: str, as_of: datetime) -> dict[str, Any]:
    e = _obj(raw, "event")
    event_id = _ident(e.get("event_id"), "event.event_id")
    provider = _ident(e.get("provider"), "event.provider")
    provider_ref = _ident(e.get("provider_ref"), "event.provider_ref")
    kind = _text(e.get("kind"), "event.kind", max_len=40)
    if kind not in _EVENT_KINDS:
        raise InputError(f"event.kind unsupported: {kind}")
    route = _ident(e.get("route_key"), "event.route_key")
    thread = _ident(e.get("thread_key"), "event.thread_key")
    ev_lead = _ident(e.get("lead_id"), "event.lead_id")
    if ev_lead != lead_id:
        raise InputError("event.lead_id does not match containing lead")
    occurred_text = _text(e.get("occurred_utc"), "event.occurred_utc", max_len=40)
    occurred = _utc(occurred_text, "event.occurred_utc")
    future = occurred > as_of
    intent = e.get("intent", "GENERAL")
    if kind == "HUMAN_INBOUND":
        intent = _text(intent, "event.intent", max_len=40)
        if intent not in _INTENTS:
            raise InputError(f"event.intent unsupported: {intent}")
    else:
        if intent not in (None, "GENERAL"):
            raise InputError("only HUMAN_INBOUND may carry non-GENERAL intent")
        intent = "GENERAL"
    return {
        "event_id": event_id,
        "provider": provider,
        "provider_ref": provider_ref,
        "kind": kind,
        "route_key": route,
        "thread_key": thread,
        "lead_id": ev_lead,
        "occurred_utc": occurred_text,
        "content_sha256": _sha(e.get("content_sha256"), "event.content_sha256"),
        "intent": intent,
        "_occurred": occurred,
        "_future": future,
    }


def _validate_claim(raw: Any, lead: Mapping[str, Any], as_of: datetime) -> dict[str, Any]:
    c = _obj(raw, "claim")
    claimed_text = _text(c.get("claimed_utc"), "claim.claimed_utc", max_len=40)
    expires_text = _text(c.get("expires_utc"), "claim.expires_utc", max_len=40)
    claimed = _utc(claimed_text, "claim.claimed_utc")
    expires = _utc(expires_text, "claim.expires_utc")
    if expires < claimed:
        raise InputError("claim expires before it was claimed")
    state = _text(c.get("state"), "claim.state", max_len=20)
    if state not in {"ACTIVE", "RELEASED"}:
        raise InputError("claim.state must be ACTIVE or RELEASED")
    route = _ident(c.get("route_key"), "claim.route_key")
    thread = _ident(c.get("thread_key"), "claim.thread_key")
    if route != lead["route_key"] or thread != lead["thread_key"]:
        raise InputError("claim scope does not match lead route/thread")
    return {
        "claim_id": _ident(c.get("claim_id"), "claim.claim_id"),
        "writer_id": _ident(c.get("writer_id"), "claim.writer_id"),
        "route_key": route,
        "thread_key": thread,
        "claimed_utc": claimed_text,
        "expires_utc": expires_text,
        "state": state,
        "_claimed": claimed,
        "_expires": expires,
        "_active_now": state == "ACTIVE" and claimed <= as_of <= expires,
        "_future": claimed > as_of,
    }


def _validate_policy(raw: Any) -> dict[str, Any]:
    p = _obj(raw, "policy")
    slas = _obj(p.get("response_sla_minutes"), "policy.response_sla_minutes")
    parsed = {}
    for priority in sorted(_PRIORITIES):
        if priority not in slas:
            raise InputError(f"missing SLA for {priority}")
        parsed[priority] = _int(slas[priority], f"policy.response_sla_minutes.{priority}", minimum=1)
    stale = _int(p.get("max_census_age_minutes"), "policy.max_census_age_minutes", minimum=1)
    claim_horizon = _int(p.get("max_claim_horizon_minutes"), "policy.max_claim_horizon_minutes", minimum=1)
    return {
        "response_sla_minutes": parsed,
        "max_census_age_minutes": stale,
        "max_claim_horizon_minutes": claim_horizon,
    }


def _classify(
    lead: Mapping[str, Any],
    events: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    census: Mapping[str, Any],
    policy: Mapping[str, Any],
    as_of: datetime,
) -> dict[str, Any]:
    reasons: list[str] = []
    route = lead["route_key"]
    thread = lead["thread_key"]

    wrong_scope = [e["event_id"] for e in events if e["route_key"] != route or e["thread_key"] != thread]
    if wrong_scope:
        reasons.append("EVENT_SCOPE_MISMATCH")
    if any(e["_future"] for e in events):
        reasons.append("FUTURE_EVENT")
    if any(c["_future"] for c in claims):
        reasons.append("FUTURE_CLAIM")

    active_claims = sorted({c["writer_id"] for c in claims if c["_active_now"]})
    if len(active_claims) > 1:
        state = "COLLISION_HOLD"
        next_action = "RESOLVE_SINGLE_WRITER"
    elif reasons:
        state = "EVIDENCE_HOLD"
        next_action = "REPAIR_RETAINED_EVIDENCE"
    else:
        census_observed = census["_observed"]
        age_min = int((as_of - census_observed).total_seconds() // 60)
        census_ok = (
            census["provider_complete"]
            and census["coordination_complete"]
            and census["pages_complete"]
            and 0 <= age_min <= policy["max_census_age_minutes"]
        )
        if not census_ok:
            state = "CENSUS_HOLD"
            next_action = "REFRESH_PROVIDER_AND_COORDINATION_CENSUS"
        else:
            scoped = [e for e in events if e["route_key"] == route and e["thread_key"] == thread]
            latest_bounce = max((e for e in scoped if e["kind"] == "BOUNCE"), key=lambda x: x["_occurred"], default=None)
            latest_inbound = max((e for e in scoped if e["kind"] == "HUMAN_INBOUND"), key=lambda x: x["_occurred"], default=None)
            latest_outbound = max((e for e in scoped if e["kind"] == "OUTBOUND_SENT"), key=lambda x: x["_occurred"], default=None)

            route_failed = latest_bounce is not None and (
                latest_inbound is None or latest_bounce["_occurred"] >= latest_inbound["_occurred"]
            ) and (
                latest_outbound is None or latest_bounce["_occurred"] >= latest_outbound["_occurred"]
            )
            if route_failed:
                state = "ROUTE_FAILURE_HOLD"
                next_action = "NO_ALIAS_HUNT_NEW_ROUTE_REQUIRES_FRESH_GENERATION"
            elif latest_inbound is None:
                state = "NO_INBOUND_SIGNAL"
                next_action = "NONE"
            elif latest_outbound is not None and latest_outbound["_occurred"] >= latest_inbound["_occurred"]:
                state = "WAITING_ON_COUNTERPARTY"
                next_action = "HARD_DNR_UNTIL_NEW_HUMAN_OR_PROVIDER_EVENT"
            else:
                intent = latest_inbound["intent"]
                if intent == "MEETING":
                    state = "CHECK_CALENDAR_REQUIRED"
                    next_action = "CHECK_CALENDAR_THEN_RECENSUS_AND_MUSE_ARBITRATION"
                elif intent == "BINDING_TERMS":
                    state = "OWNER_DECISION_REQUIRED"
                    next_action = "OWNER_DECISION_THEN_RECENSUS_AND_MUSE_ARBITRATION"
                else:
                    state = "NEW_INBOUND_UNANSWERED"
                    next_action = "RECENSUS_THEN_MUSE_ARBITRATION"

    scoped_events = [e for e in events if e["route_key"] == route and e["thread_key"] == thread]
    latest_inbound = max((e for e in scoped_events if e["kind"] == "HUMAN_INBOUND"), key=lambda x: x["_occurred"], default=None)
    latest_outbound = max((e for e in scoped_events if e["kind"] == "OUTBOUND_SENT"), key=lambda x: x["_occurred"], default=None)
    latest_bounce = max((e for e in scoped_events if e["kind"] == "BOUNCE"), key=lambda x: x["_occurred"], default=None)
    age_minutes = None
    sla_breached = False
    if latest_inbound is not None:
        age_minutes = max(0, int((as_of - latest_inbound["_occurred"]).total_seconds() // 60))
        sla_breached = (
            state in {"NEW_INBOUND_UNANSWERED", "CHECK_CALENDAR_REQUIRED", "OWNER_DECISION_REQUIRED"}
            and age_minutes > policy["response_sla_minutes"][lead["priority"]]
        )

    muse_selected = any(
        e["kind"] == "MUSE_SELECTED" and e["route_key"] == route and e["thread_key"] == thread for e in events
    )
    return {
        "lead_id": lead["lead_id"],
        "counterparty": lead["counterparty"],
        "priority": lead["priority"],
        "route_key": route,
        "thread_key": thread,
        "state": state,
        "next_action": next_action,
        "active_writers": active_claims,
        "latest_inbound_utc": latest_inbound["occurred_utc"] if latest_inbound else None,
        "inbound_age_minutes": age_minutes,
        "response_sla_minutes": policy["response_sla_minutes"][lead["priority"]],
        "sla_breached": sla_breached,
        "muse_selected_evidence_present": muse_selected,
        "evidence_refs": {
            "latest_inbound": (
                {"event_id": latest_inbound["event_id"], "provider": latest_inbound["provider"], "provider_ref": latest_inbound["provider_ref"]}
                if latest_inbound else None
            ),
            "latest_outbound": (
                {"event_id": latest_outbound["event_id"], "provider": latest_outbound["provider"], "provider_ref": latest_outbound["provider_ref"]}
                if latest_outbound else None
            ),
            "latest_bounce": (
                {"event_id": latest_bounce["event_id"], "provider": latest_bounce["provider"], "provider_ref": latest_bounce["provider_ref"]}
                if latest_bounce else None
            ),
        },
        "reasons": sorted(reasons),
    }


def compile_snapshot(document: Mapping[str, Any]) -> dict[str, Any]:
    """Compile retained evidence into a deterministic read-only response queue."""
    doc = _obj(document, "document")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise InputError(f"schema_version must be {SCHEMA_VERSION!r}")
    as_of_text = _text(doc.get("as_of_utc"), "as_of_utc", max_len=40)
    as_of = _utc(as_of_text, "as_of_utc")
    policy = _validate_policy(doc.get("policy"))

    census_raw = _obj(doc.get("census"), "census")
    observed_text = _text(census_raw.get("observed_utc"), "census.observed_utc", max_len=40)
    observed = _utc(observed_text, "census.observed_utc")
    if observed > as_of:
        raise InputError("census.observed_utc cannot be after as_of_utc")
    census = {
        "provider_complete": _bool(census_raw.get("provider_complete"), "census.provider_complete"),
        "coordination_complete": _bool(census_raw.get("coordination_complete"), "census.coordination_complete"),
        "pages_complete": _bool(census_raw.get("pages_complete"), "census.pages_complete"),
        "observed_utc": observed_text,
        "_observed": observed,
    }

    leads_raw = _list(doc.get("leads"), "leads")
    leads: list[dict[str, Any]] = []
    seen_leads: set[str] = set()
    seen_scopes: set[str] = set()
    all_event_ids: set[str] = set()
    all_provider_refs: set[tuple[str, str]] = set()
    all_event_semantics: set[tuple[str, ...]] = set()
    all_claim_ids: set[str] = set()

    for raw in leads_raw:
        l = _obj(raw, "lead")
        lead_id = _ident(l.get("lead_id"), "lead.lead_id")
        if lead_id in seen_leads:
            raise InputError(f"duplicate lead_id: {lead_id}")
        seen_leads.add(lead_id)
        route = _ident(l.get("route_key"), "lead.route_key")
        thread = _ident(l.get("thread_key"), "lead.thread_key")
        scope = _scope_key(route, thread)
        if scope in seen_scopes:
            raise InputError("two leads cannot own the same route/thread scope")
        seen_scopes.add(scope)
        priority = _text(l.get("priority"), "lead.priority", max_len=20)
        if priority not in _PRIORITIES:
            raise InputError(f"unsupported lead.priority: {priority}")
        lead = {
            "lead_id": lead_id,
            "counterparty": _text(l.get("counterparty"), "lead.counterparty", max_len=200),
            "priority": priority,
            "route_key": route,
            "thread_key": thread,
        }
        events = []
        for eraw in _list(l.get("events"), "lead.events"):
            e = _validate_event(eraw, lead_id, as_of)
            if e["event_id"] in all_event_ids:
                raise InputError(f"duplicate event_id: {e['event_id']}")
            all_event_ids.add(e["event_id"])
            pref = (e["provider"], e["provider_ref"])
            if pref in all_provider_refs:
                raise InputError("same provider/provider_ref retained more than once")
            all_provider_refs.add(pref)
            semantic = _event_semantic_key(e)
            if semantic in all_event_semantics:
                raise InputError("semantic duplicate provider event under a different id/ref")
            all_event_semantics.add(semantic)
            events.append(e)
        _reject_ambiguous_chronology(events, lead)
        claims = []
        for craw in _list(l.get("claims"), "lead.claims"):
            c = _validate_claim(craw, lead, as_of)
            if c["claim_id"] in all_claim_ids:
                raise InputError(f"duplicate claim_id: {c['claim_id']}")
            all_claim_ids.add(c["claim_id"])
            if (c["_expires"] - c["_claimed"]).total_seconds() > policy["max_claim_horizon_minutes"] * 60:
                raise InputError("claim horizon exceeds policy maximum")
            claims.append(c)
        leads.append({"lead": lead, "events": events, "claims": claims})

    classified = [
        _classify(item["lead"], item["events"], item["claims"], census, policy, as_of) for item in leads
    ]
    severity = {
        "COLLISION_HOLD": 0,
        "EVIDENCE_HOLD": 1,
        "CHECK_CALENDAR_REQUIRED": 2,
        "OWNER_DECISION_REQUIRED": 3,
        "NEW_INBOUND_UNANSWERED": 4,
        "CENSUS_HOLD": 5,
        "ROUTE_FAILURE_HOLD": 6,
        "WAITING_ON_COUNTERPARTY": 7,
        "NO_INBOUND_SIGNAL": 8,
    }
    porder = {"HOT": 0, "WARM": 1, "GENERAL": 2}
    classified.sort(
        key=lambda x: (
            0 if x["sla_breached"] else 1,
            severity[x["state"]],
            porder[x["priority"]],
            -(x["inbound_age_minutes"] or 0),
            x["lead_id"],
        )
    )
    summary = dict(sorted(Counter(row["state"] for row in classified).items()))
    core = {
        "schema_version": SCHEMA_VERSION,
        "as_of_utc": as_of_text,
        "census": {k: v for k, v in census.items() if not k.startswith("_")},
        "policy": policy,
        "summary": summary,
        "leads": classified,
        "authority": {
            "send_authorized": False,
            "calendar_mutation_authorized": False,
            "recipient_selection_authorized": False,
            "pricing_or_contract_acceptance_authorized": False,
            "provider_mutation_authorized": False,
            "payment_or_accounting_mutation_authorized": False,
            "revenue_recognition_authorized": False,
        },
    }
    result = dict(core)
    result["semantic_receipt_sha256"] = _receipt(core)
    return result


def verify_compiled(document: Mapping[str, Any], compiled: Mapping[str, Any]) -> bool:
    """Return True only for an exact semantic replay of ``document``."""
    try:
        expected = compile_snapshot(document)
    except (InputError, TypeError, ValueError):
        return False
    return _canonical(expected) == _canonical(compiled)


def render_markdown(compiled: Mapping[str, Any]) -> str:
    """Render deterministic, human-readable queue text from a self-consistent bundle."""
    c = _obj(compiled, "compiled")
    if c.get("schema_version") != SCHEMA_VERSION:
        raise InputError("compiled schema mismatch")
    provided_receipt = _sha(c.get("semantic_receipt_sha256"), "compiled.semantic_receipt_sha256")
    receipt_core = {k: v for k, v in c.items() if k != "semantic_receipt_sha256"}
    if _receipt(receipt_core) != provided_receipt:
        raise InputError("compiled semantic receipt mismatch")
    lines = [
        "# Inbound lead response queue",
        "",
        f"As of: `{c.get('as_of_utc')}`",
        f"Receipt: `{c.get('semantic_receipt_sha256')}`",
        "",
        "| Lead | Priority | State | Age min | SLA | Next safe step |",
        "|---|---|---|---:|---:|---|",
    ]
    leads = _list(c.get("leads"), "compiled.leads")
    for row_raw in leads:
        row = _obj(row_raw, "compiled.lead")
        lead_id = _text(row.get("lead_id"), "compiled.lead.lead_id")
        priority = _text(row.get("priority"), "compiled.lead.priority")
        state = _text(row.get("state"), "compiled.lead.state")
        if state not in _STATES:
            raise InputError("compiled lead state unsupported")
        age = row.get("inbound_age_minutes")
        age_text = "-" if age is None else str(_int(age, "compiled.lead.inbound_age_minutes", maximum=10_000_000))
        sla = _int(row.get("response_sla_minutes"), "compiled.lead.response_sla_minutes")
        next_action = _text(row.get("next_action"), "compiled.lead.next_action", max_len=200)
        lines.append(f"| `{lead_id}` | {priority} | `{state}` | {age_text} | {sla} | `{next_action}` |")
    lines.extend([
        "",
        "> Read-only triage. No row authorizes an external send, calendar mutation, pricing/contract acceptance, payment, or revenue recognition.",
        "",
    ])
    return "\n".join(lines)
