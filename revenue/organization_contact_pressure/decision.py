"""Organization-level contact-pressure decision semantics."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from .core import (
    AuthorityView,
    LedgerView,
    EVENT_AUTO_REPLY,
    EVENT_DNR,
    EVENT_HARD_BOUNCE,
    EVENT_HUMAN_REPLY,
    EVENT_OWNER_RELEASE,
    EVENT_PROPOSED,
    EVENT_SENT,
    EVENT_UNSUBSCRIBE,
    HOLD_AUTHORITY,
    HOLD_CONFLICT,
    HOLD_DNR,
    HOLD_HUMAN_REPLY,
    HOLD_ORG_ACTIVE,
    HOLD_RECENT_CONTACT,
    READY,
    RELEASABLE_KINDS,
    _parse_time,
)


def _evaluate(
    request: Mapping[str, Any],
    authority: AuthorityView,
    ledger: LedgerView,
    now: datetime,
) -> tuple[str, tuple[str, ...]]:
    reasons: set[str] = set(ledger.conflicts)
    proposed_route = request["proposed_route_scope_sha256"]
    requested_at = _parse_time(request["requested_at"], "requested_at")
    skew = timedelta(seconds=authority.max_future_skew_seconds)
    if request["organization_scope_sha256"] != authority.organization_scope_sha256:
        reasons.add("REQUEST_ORGANIZATION_MISMATCH")
    if proposed_route not in set(authority.route_scope_sha256s):
        reasons.add("REQUEST_ROUTE_NOT_AUTHORIZED")
    if requested_at > now + skew:
        reasons.add("REQUEST_IN_FUTURE")
    if now - requested_at > timedelta(seconds=authority.request_max_age_seconds):
        reasons.add("REQUEST_STALE")

    by_id = {event.event_id: event for event in ledger.events}
    proposed_event_id = request["proposed_event_id"]
    if proposed_event_id in by_id:
        reasons.add(f"PROPOSED_EVENT_ID_ALREADY_RECORDED:{proposed_event_id}")

    released: set[str] = set()
    for event in ledger.events:
        if event.kind != EVENT_OWNER_RELEASE:
            continue
        target = by_id.get(event.target_event_id or "")
        if target is None:
            reasons.add(f"RELEASE_TARGET_MISSING:{event.event_id}")
            continue
        if target.kind not in RELEASABLE_KINDS:
            reasons.add(f"RELEASE_TARGET_KIND_INVALID:{event.event_id}")
            continue
        if event.route_scope_sha256 != target.route_scope_sha256:
            reasons.add(f"RELEASE_ROUTE_MISMATCH:{event.event_id}")
            continue
        if event.observed_at <= target.observed_at:
            reasons.add(f"RELEASE_NOT_LATER_THAN_TARGET:{event.event_id}")
            continue
        released.add(target.event_id)

    dnr_reasons: set[str] = set()
    human_reasons: set[str] = set()
    active_reasons: set[str] = set()
    recent_reasons: set[str] = set()

    active_proposed_routes: set[str] = set()
    cooldown = timedelta(seconds=authority.contact_cooldown_seconds)
    for event in ledger.events:
        if event.kind in {EVENT_DNR, EVENT_UNSUBSCRIBE}:
            dnr_reasons.add(f"ORG_{event.kind}:{event.event_id}")
        elif event.kind == EVENT_HARD_BOUNCE and event.route_scope_sha256 == proposed_route:
            dnr_reasons.add(f"ROUTE_HARD_BOUNCE:{event.event_id}")

        if event.event_id not in released:
            if event.kind == EVENT_HUMAN_REPLY:
                human_reasons.add(f"UNRESOLVED_HUMAN_REPLY:{event.event_id}")
            elif event.kind == EVENT_PROPOSED:
                active_proposed_routes.add(event.route_scope_sha256)
                active_reasons.add(f"UNRESOLVED_PROPOSAL:{event.event_id}")
            elif event.kind == EVENT_SENT:
                active_reasons.add(f"UNRESOLVED_SENT:{event.event_id}")
            elif event.kind == EVENT_AUTO_REPLY:
                active_reasons.add(f"UNRESOLVED_AUTO_REPLY:{event.event_id}")

        if event.kind in {EVENT_SENT, EVENT_HUMAN_REPLY, EVENT_AUTO_REPLY}:
            if now - event.observed_at < cooldown:
                recent_reasons.add(f"COOLDOWN_ACTIVE:{event.event_id}")

    if len(active_proposed_routes) > 1:
        active_reasons.add("MULTIPLE_PROPOSED_ROUTES")
    if active_proposed_routes and proposed_route not in active_proposed_routes:
        active_reasons.add("CROSS_ROUTE_PROPOSAL_PRESSURE")

    if any(
        reason.startswith((
            "EVENT_ID_MUTATION:",
            "PROPOSED_EVENT_ID_ALREADY_RECORDED:",
            "LEDGER_GENERATION_COUNT_MISMATCH",
            "RELEASE_TARGET_",
            "RELEASE_ROUTE_MISMATCH:",
            "RELEASE_NOT_LATER_",
        ))
        for reason in reasons
    ):
        return HOLD_CONFLICT, tuple(sorted(reasons | dnr_reasons | human_reasons | active_reasons | recent_reasons))
    if any(
        reason.startswith((
            "EVENT_ORGANIZATION_TRANSPLANT:",
            "UNKNOWN_ROUTE_SCOPE:",
            "FUTURE_EVENT:",
            "EVENT_AFTER_LEDGER_UPDATE:",
            "REQUEST_ORGANIZATION_MISMATCH",
            "REQUEST_ROUTE_NOT_AUTHORIZED",
            "REQUEST_IN_FUTURE",
            "REQUEST_STALE",
        ))
        for reason in reasons
    ):
        return HOLD_AUTHORITY, tuple(sorted(reasons | dnr_reasons | human_reasons | active_reasons | recent_reasons))
    if dnr_reasons:
        return HOLD_DNR, tuple(sorted(reasons | dnr_reasons | human_reasons | active_reasons | recent_reasons))
    if human_reasons:
        return HOLD_HUMAN_REPLY, tuple(sorted(reasons | human_reasons | active_reasons | recent_reasons))
    if active_reasons:
        return HOLD_ORG_ACTIVE, tuple(sorted(reasons | active_reasons | recent_reasons))
    if recent_reasons:
        return HOLD_RECENT_CONTACT, tuple(sorted(reasons | recent_reasons))
    return READY, ()
