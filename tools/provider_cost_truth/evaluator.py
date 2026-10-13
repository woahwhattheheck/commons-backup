"""Cost semantics evaluation without process-current receipt authority."""
from __future__ import annotations
from datetime import datetime as _DateTime, timezone as _Timezone
from typing import Any, Mapping
from .codec import MAX_EVIDENCE_AGE_SECONDS, GateError, _parse_ts, _sha256_value
from .schema import validate_snapshot, _target_scope, _request_identity, _scope_identity
from .trusted_sources import (
    TRUSTED_PROVIDER_EVIDENCE_FINGERPRINTS,
    TRUSTED_PROVIDER_EVIDENCE_MANIFEST_SHA256,
    TRUSTED_PROVIDER_EVIDENCE_SCHEMA,
)

_PROVIDER_EVIDENCE_FIELDS = (
    "event_id",
    "scope",
    "provider",
    "account_id",
    "product",
    "model",
    "session_id",
    "kind",
    "amount_minor",
    "currency",
    "event_at_utc",
    "observed_at_utc",
    "valid_until_utc",
    "source_ref",
    "source_sha256",
    "authority",
)


def _provider_evidence_fingerprint(
    event: Mapping[str, Any],
    _hash=_sha256_value,
    _schema=TRUSTED_PROVIDER_EVIDENCE_SCHEMA,
    _fields=_PROVIDER_EVIDENCE_FIELDS,
) -> str:
    """Bind every authority-relevant normalized event field to one digest."""
    return _hash(
        {
            "schema": _schema,
            "event": {field: event[field] for field in _fields},
        }
    )


def _current_provider_events(
    events: list[dict[str, Any]],
    now: _DateTime,
    _parse=_parse_ts,
    _max_age=MAX_EVIDENCE_AGE_SECONDS,
    _trusted=TRUSTED_PROVIDER_EVIDENCE_FINGERPRINTS,
    _fingerprint=_provider_evidence_fingerprint,
) -> tuple[list[dict[str, Any]], list[str]]:
    current: list[dict[str, Any]] = []
    reasons: list[str] = []
    for event in events:
        event_id = event["event_id"]
        if event["authority"] != "PROVIDER_AUTHENTICATED":
            reasons.append(f"IGNORED_NON_PROVIDER_AUTHORITY:{event_id}")
            continue
        if _fingerprint(event) not in _trusted:
            reasons.append(f"IGNORED_UNTRUSTED_PROVIDER_EVIDENCE:{event_id}")
            continue
        event_at = _parse(event["event_at_utc"], "event_at_utc")
        observed = _parse(event["observed_at_utc"], "observed_at_utc")
        valid = (
            _parse(event["valid_until_utc"], "valid_until_utc")
            if event["valid_until_utc"] is not None
            else None
        )
        if event_at > now or observed > now:
            reasons.append(f"IGNORED_FUTURE_EVIDENCE:{event_id}")
            continue
        if (now - observed).total_seconds() > _max_age:
            reasons.append(f"IGNORED_STALE_EVIDENCE:{event_id}")
            continue
        if valid is not None and valid < now:
            reasons.append(f"IGNORED_EXPIRED_EVIDENCE:{event_id}")
            continue
        current.append(event)
    return current, reasons


def _billing_class(event: Mapping[str, Any]) -> str:
    if event["kind"] == "ZERO_COST_CONFIRMED":
        return "ZERO"
    if event["kind"] == "PRICE_QUOTE":
        return "ZERO" if event["amount_minor"] == 0 else "BILLABLE"
    return "BILLABLE"


def _evaluate_snapshot(
    snapshot: Any,
    now: _DateTime,
    _utc=_Timezone.utc,
    _validate=validate_snapshot,
    _target=_target_scope,
    _request_id=_request_identity,
    _scope_id=_scope_identity,
    _current_events=_current_provider_events,
    _billing=_billing_class,
    _parse=_parse_ts,
    _hash=_sha256_value,
    _manifest_sha=TRUSTED_PROVIDER_EVIDENCE_MANIFEST_SHA256,
) -> dict[str, Any]:
    """Evaluate at caller time but deliberately emit no current receipt fields."""
    if now.tzinfo is None:
        raise GateError("evaluation time must be timezone-aware")
    now = now.astimezone(_utc).replace(microsecond=0)
    normalized = _validate(snapshot)
    request = normalized["request"]
    target_scope = _target(request)
    target_id = _request_id(request, target_scope)
    current, reasons = _current_events(normalized["evidence"], now)
    exact = [
        event
        for event in current
        if event["scope"] == target_scope and _scope_id(event) == target_id
    ]
    controlling: list[str] = []
    account_billing = sorted(
        event["event_id"]
        for event in current
        if event["amount_minor"] > 0 and _billing(event) == "BILLABLE"
    )
    if exact:
        latest_at = max(_parse(event["event_at_utc"], "event_at_utc") for event in exact)
        latest = [
            event
            for event in exact
            if _parse(event["event_at_utc"], "event_at_utc") == latest_at
        ]
        controlling = sorted(event["event_id"] for event in latest)
        classes = {_billing(event) for event in latest}
        if len(classes) > 1:
            state = "CONTRADICTORY"
            reasons.append("CONFLICTING_LATEST_EXACT_SCOPE_EVIDENCE")
        elif classes == {"ZERO"}:
            state = "ZERO_COST_VERIFIED"
            reasons.append("CURRENT_TRUSTED_PROVIDER_ZERO_COST_AT_EXACT_SCOPE")
        else:
            state = "BILLABLE_VERIFIED"
            reasons.append("CURRENT_TRUSTED_PROVIDER_NONZERO_BILLING_AT_EXACT_SCOPE")
    elif account_billing:
        state = "FREE_UNPROVEN_ACCOUNT_BILLING_PRESENT"
        reasons.append(
            "ACCOUNT_HAS_CURRENT_TRUSTED_NONZERO_BILLING_BUT_REQUESTED_SCOPE_COST_IS_UNPROVEN"
        )
    else:
        state = "COST_UNKNOWN"
        reasons.append("NO_CURRENT_TRUSTED_PROVIDER_COST_AUTHORITY_FOR_REQUESTED_SCOPE")
    satisfied = request["free_only"] and state == "ZERO_COST_VERIFIED"
    if request["free_only"] and not satisfied:
        reasons.append("FREE_ONLY_DELEGATION_HOLD")
    return {
        "state": state,
        "target_scope": target_scope,
        "request_sha256": _hash(request),
        "snapshot_sha256": _hash(normalized),
        "trusted_provider_evidence_manifest_sha256": _manifest_sha,
        "controlling_event_ids": controlling,
        "account_billing_event_ids": account_billing,
        "reasons": sorted(set(reasons)),
        "free_only_requested": request["free_only"],
        "free_only_satisfied": satisfied,
        "provider_session_authorized": False,
        "spend_authorized": False,
        "external_side_effects_authorized": False,
    }
