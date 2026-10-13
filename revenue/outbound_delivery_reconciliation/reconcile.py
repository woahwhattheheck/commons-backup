from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

REPORT_SCHEMA = "outbound-delivery-reconciliation-report/v1"
ORIGINAL_SCHEMA = "outbound-delivery-original/v1"
EVENT_SCHEMA = "outbound-delivery-provider-event/v1"
FAILURE_REASONS = frozenset({
    "NO_SUCH_USER", "MAILBOX_FULL", "POLICY_OR_GROUP_RESTRICTION",
    "REMOTE_REJECTION", "UNKNOWN_PERMANENT_FAILURE",
})
EVENT_KINDS = frozenset({"PERMANENT_FAILURE", "PROVIDER_ACCEPTED"})
MAX_EVENTS = 1000
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+={}\-]{0,191}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
_EMAIL_RE = re.compile(r"^[^@\s\x00-\x1f\x7f]+@[^@\s\x00-\x1f\x7f]+$")


class ReconciliationError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReconciliationError(f"not canonical JSON: {exc}") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _keys(value: Any, expected: Iterable[str], where: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise ReconciliationError(f"{where} must be an object")
    want, got = set(expected), set(value)
    if want != got:
        raise ReconciliationError(f"{where} keys mismatch missing={sorted(want-got)} extra={sorted(got-want)}")
    return value


def _text(value: Any, where: str, maximum: int = 192) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise ReconciliationError(f"{where} must be non-empty text <= {maximum} chars")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ReconciliationError(f"{where} contains control characters")
    return value


def _id(value: Any, where: str) -> str:
    value = _text(value, where)
    if not _ID_RE.fullmatch(value):
        raise ReconciliationError(f"{where} is not a safe opaque id")
    return value


def _sha(value: Any, where: str) -> str:
    value = _text(value, where, 64)
    if not _SHA_RE.fullmatch(value):
        raise ReconciliationError(f"{where} must be lowercase sha256")
    return value


def _recipient(value: Any, where: str) -> str:
    value = _text(value, where, 254)
    if value != value.strip() or not _EMAIL_RE.fullmatch(value):
        raise ReconciliationError(f"{where} must be one email-like route without surrounding whitespace")
    return value.lower()


def _scope(value: Any, where: str) -> str:
    value = _text(value, where, 253)
    if value != value.strip() or value != value.lower() or not _SCOPE_RE.fullmatch(value):
        raise ReconciliationError(f"{where} must be a canonical lowercase buyer scope")
    return value


def _utc(value: Any, where: str) -> datetime:
    value = _text(value, where, 20)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ReconciliationError(f"{where} must be canonical UTC whole seconds")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReconciliationError(f"{where} is not a valid timestamp") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ReconciliationError(f"{where} is not canonical UTC")
    return dt


def _utc_text(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ReconciliationError("trusted time must be timezone-aware datetime")
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_original(value: Mapping[str, Any]) -> Dict[str, Any]:
    value = _keys(value, {
        "schema", "provider_message_id", "recipient", "buyer_scope",
        "opportunity_id", "sent_at", "evidence_sha256",
    }, "original")
    if value["schema"] != ORIGINAL_SCHEMA:
        raise ReconciliationError("unsupported original schema")
    return {
        "schema": ORIGINAL_SCHEMA,
        "provider_message_id": _id(value["provider_message_id"], "original.provider_message_id"),
        "recipient": _recipient(value["recipient"], "original.recipient"),
        "buyer_scope": _scope(value["buyer_scope"], "original.buyer_scope"),
        "opportunity_id": _id(value["opportunity_id"], "original.opportunity_id"),
        "sent_at": _utc_text(_utc(value["sent_at"], "original.sent_at")),
        "evidence_sha256": _sha(value["evidence_sha256"], "original.evidence_sha256"),
    }


def _normalize_event(value: Mapping[str, Any], index: int) -> Dict[str, Any]:
    where = f"events[{index}]"
    value = _keys(value, {
        "schema", "event_id", "provider_message_id", "recipient", "buyer_scope",
        "opportunity_id", "observed_at", "event_kind", "reason_code", "evidence_sha256",
    }, where)
    if value["schema"] != EVENT_SCHEMA:
        raise ReconciliationError(f"{where}.schema unsupported")
    kind = _text(value["event_kind"], f"{where}.event_kind", 32)
    if kind not in EVENT_KINDS:
        raise ReconciliationError(f"{where}.event_kind unsupported")
    reason = value["reason_code"]
    if kind == "PERMANENT_FAILURE":
        reason = _text(reason, f"{where}.reason_code", 64)
        if reason not in FAILURE_REASONS:
            raise ReconciliationError(f"{where}.reason_code unsupported")
    elif reason is not None:
        raise ReconciliationError(f"{where}.reason_code must be null for PROVIDER_ACCEPTED")
    return {
        "schema": EVENT_SCHEMA,
        "event_id": _id(value["event_id"], f"{where}.event_id"),
        "provider_message_id": _id(value["provider_message_id"], f"{where}.provider_message_id"),
        "recipient": _recipient(value["recipient"], f"{where}.recipient"),
        "buyer_scope": _scope(value["buyer_scope"], f"{where}.buyer_scope"),
        "opportunity_id": _id(value["opportunity_id"], f"{where}.opportunity_id"),
        "observed_at": _utc_text(_utc(value["observed_at"], f"{where}.observed_at")),
        "event_kind": kind,
        "reason_code": reason,
        "evidence_sha256": _sha(value["evidence_sha256"], f"{where}.evidence_sha256"),
    }


def _normalize_events(events: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    if type(events) is not list or len(events) > MAX_EVENTS:
        raise ReconciliationError(f"events must be a list with at most {MAX_EVENTS} rows")
    by_id: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for i, raw in enumerate(events):
        row = _normalize_event(raw, i)
        variants = by_id.setdefault(row["event_id"], {})
        variants[canonical_json(row)] = row
    holds = sorted(f"EVENT_ID_FORK:{event_id}" for event_id, variants in by_id.items() if len(variants) > 1)
    # Retain every distinct fork branch. Keeping the first one loses evidence
    # and can make a known bounce disappear when the input order changes.
    rows = sorted(
        (row for variants in by_id.values() for row in variants.values()),
        key=lambda row: (row["observed_at"], row["event_id"], canonical_json(row)),
    )
    return rows, holds


def _compile_at(original: Mapping[str, Any], events: Sequence[Mapping[str, Any]], *, at: datetime) -> Dict[str, Any]:
    as_of = _utc_text(at)
    now = _utc(as_of, "internal.as_of")
    original_n = _normalize_original(original)
    events_n, holds = _normalize_events(events)
    sent = _utc(original_n["sent_at"], "original.sent_at")
    if sent > now:
        holds.append("ORIGINAL_SENT_FROM_FUTURE")

    failure_reasons = set()
    accepted_times: list[datetime] = []
    failure_times: list[datetime] = []
    evidence = {original_n["evidence_sha256"]}
    exact_failure = False
    for row in events_n:
        evidence.add(row["evidence_sha256"])
        observed = _utc(row["observed_at"], "event.observed_at")
        identity_ok = all((
            row["provider_message_id"] == original_n["provider_message_id"],
            row["recipient"] == original_n["recipient"],
            row["buyer_scope"] == original_n["buyer_scope"],
            row["opportunity_id"] == original_n["opportunity_id"],
        ))
        chronology_ok = sent <= observed <= now
        if observed < sent:
            holds.append(f"EVENT_BEFORE_SEND:{row['event_id']}")
        if observed > now:
            holds.append(f"EVENT_FROM_FUTURE:{row['event_id']}")
        for field, code in (
            ("provider_message_id", "CROSS_MESSAGE_EVENT"),
            ("recipient", "CROSS_RECIPIENT_EVENT"),
            ("buyer_scope", "CROSS_BUYER_EVENT"),
            ("opportunity_id", "CROSS_OPPORTUNITY_EVENT"),
        ):
            if row[field] != original_n[field]:
                holds.append(f"{code}:{row['event_id']}")
        if identity_ok and chronology_ok:
            if row["event_kind"] == "PERMANENT_FAILURE":
                exact_failure = True
                failure_times.append(observed)
                failure_reasons.add(row["reason_code"])
            else:
                accepted_times.append(observed)

    # Provider acceptance is transport progress, not terminal delivery.
    # A later DSN/bounce normally supersedes it. Acceptance at or after a
    # permanent failure cannot reopen the same sent generation.
    if accepted_times and failure_times and max(accepted_times) >= min(failure_times):
        holds.append("INCOMPATIBLE_TERMINAL_PROVIDER_EVIDENCE")
    holds = sorted(set(holds))
    classification = (
        "HOLD_CONFLICTING_PROVIDER_EVIDENCE" if holds else
        "DELIVERY_FAILED" if exact_failure else
        "SENT_PENDING_PROVIDER_TRUTH"
    )
    core = {
        "schema": REPORT_SCHEMA,
        "generated_at": as_of,
        "classification": classification,
        "provider_message_id": original_n["provider_message_id"],
        "recipient": original_n["recipient"],
        "buyer_scope": original_n["buyer_scope"],
        "opportunity_id": original_n["opportunity_id"],
        "source_generation_sha256": sha256_json({"original": original_n, "events": events_n}),
        "provider_event_ids": list(dict.fromkeys(row["event_id"] for row in events_n)),
        "provider_evidence_sha256": sorted(evidence),
        "failure_reason_codes": sorted(failure_reasons),
        "hold_reasons": holds,
        "failed_route_dnr": exact_failure,
        "alternate_route_authorized": False,
        "retry_authorized": False,
        "buyer_rejection_asserted": False,
        "buyer_opt_out_asserted": False,
        "buyer_acceptance_asserted": False,
        "payment_asserted": False,
        "cash_asserted": False,
        "revenue_asserted": False,
    }
    report = dict(core)
    report["receipt_sha256"] = sha256_json(core)
    return report


def reconcile(original: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Compile current provider-delivery truth using the host-owned UTC clock."""
    return _compile_at(original, events, at=datetime.now(timezone.utc))


def verify(report: Mapping[str, Any], original: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> bool:
    """Replay the receipt-bound historical instant for integrity only; never authorizes contact."""
    if type(report) is not dict or report.get("schema") != REPORT_SCHEMA:
        return False
    try:
        expected = _compile_at(original, events, at=_utc(report.get("generated_at"), "report.generated_at"))
    except (ReconciliationError, TypeError, ValueError):
        return False
    return canonical_json(report) == canonical_json(expected)
