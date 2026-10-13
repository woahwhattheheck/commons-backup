from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Iterable


HEX64 = re.compile(r"^[0-9a-f]{64}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
RESPONSE_CLASSES = {"exact_acceptance", "counteroffer", "decline", "clarification"}
AUTHORITY = {
    "signer_or_legal_authority": False,
    "contract_creation_or_execution": False,
    "invoice_or_checkout_creation": False,
    "payment_or_charge": False,
    "fulfillment_start": False,
    "recognized_revenue": False,
}
DECISION_STATUSES = {
    "HUMAN_CLOSING_READY",
    "COUNTEROFFER_REVIEW",
    "CLARIFICATION_REQUIRED",
    "EVIDENCE_CONFLICT",
    "LATE_RESPONSE_REVIEW",
    "REISSUE_REQUIRED",
}
ROUTINE_STATUSES = {"AWAITING_RESPONSE", "DECLINED"}


class DecisionRelayError(ValueError):
    """Raised when normalized commercial evidence violates the relay contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AuthorityBoundaryError(DecisionRelayError):
    """Raised if code attempts to turn a decision signal into commercial authority."""


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canonicalize(value), separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionRelayError("invalid_text", f"{field} must be non-empty text")
    return value.strip()


def _hex64(value: Any, field: str) -> str:
    value = _text(value, field).lower()
    if not HEX64.fullmatch(value):
        raise DecisionRelayError("invalid_digest", f"{field} must be a 64-character lowercase SHA-256 hex digest")
    return value


def _currency(value: Any) -> str:
    value = _text(value, "currency").upper()
    if not CURRENCY.fullmatch(value):
        raise DecisionRelayError("invalid_currency", "currency must be an explicit three-letter uppercase code")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DecisionRelayError("invalid_integer", f"{field} must be a positive integer")
    return value


def _instant(value: Any, field: str) -> str:
    raw = _text(value, field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionRelayError("invalid_time", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DecisionRelayError("invalid_time", f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ts(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _normalize_offer(event: dict[str, Any]) -> dict[str, Any]:
    issued_at = _instant(event.get("issued_at"), "issued_at")
    expires_at = _instant(event.get("expires_at"), "expires_at")
    if _ts(expires_at) <= _ts(issued_at):
        raise DecisionRelayError("invalid_offer_window", "expires_at must be after issued_at")
    return {
        "event_id": _text(event.get("event_id"), "event_id"),
        "kind": "offer",
        "series_id": _text(event.get("series_id"), "series_id"),
        "offer_version": _positive_int(event.get("offer_version"), "offer_version"),
        "counterparty_id": _text(event.get("counterparty_id"), "counterparty_id"),
        "thread_id": _text(event.get("thread_id"), "thread_id"),
        "currency": _currency(event.get("currency")),
        "amount_minor": _positive_int(event.get("amount_minor"), "amount_minor"),
        "terms_digest": _hex64(event.get("terms_digest"), "terms_digest"),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def _normalize_response(event: dict[str, Any]) -> dict[str, Any]:
    response_class = _text(event.get("response_class"), "response_class").lower()
    if response_class not in RESPONSE_CLASSES:
        raise DecisionRelayError("invalid_response_class", f"unsupported response_class {response_class}")
    received_at = _instant(event.get("received_at"), "received_at")
    reviewed_at = _instant(event.get("reviewed_at"), "reviewed_at")
    if _ts(reviewed_at) < _ts(received_at):
        raise DecisionRelayError("review_before_receipt", "reviewed_at cannot predate received_at")
    return {
        "event_id": _text(event.get("event_id"), "event_id"),
        "kind": "response",
        "series_id": _text(event.get("series_id"), "series_id"),
        "offer_version": _positive_int(event.get("offer_version"), "offer_version"),
        "counterparty_id": _text(event.get("counterparty_id"), "counterparty_id"),
        "thread_id": _text(event.get("thread_id"), "thread_id"),
        "currency": _currency(event.get("currency")),
        "amount_minor": _positive_int(event.get("amount_minor"), "amount_minor"),
        "terms_digest": _hex64(event.get("terms_digest"), "terms_digest"),
        "response_class": response_class,
        "received_at": received_at,
        "reviewed_at": reviewed_at,
        "source_digest": _hex64(event.get("source_digest"), "source_digest"),
        "reviewer_attestation_digest": _hex64(event.get("reviewer_attestation_digest"), "reviewer_attestation_digest"),
    }


def normalize_batch(batch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(batch, dict):
        raise DecisionRelayError("invalid_batch", "batch must be an object")
    schema_version = batch.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        raise DecisionRelayError("unsupported_schema", "schema_version must be the integer 1")
    snapshot_at = _instant(batch.get("snapshot_at"), "snapshot_at")
    raw_events = batch.get("events")
    if not isinstance(raw_events, list):
        raise DecisionRelayError("invalid_events", "events must be an array")

    events: list[dict[str, Any]] = []
    event_fingerprints: dict[str, str] = {}
    series_versions: dict[tuple[str, int], str] = {}
    for raw in raw_events:
        if not isinstance(raw, dict):
            raise DecisionRelayError("invalid_event", "every event must be an object")
        kind = _text(raw.get("kind"), "kind").lower()
        if kind == "offer":
            event = _normalize_offer(raw)
            key = (event["series_id"], event["offer_version"])
            fingerprint = canonical_digest(event)
            previous = series_versions.get(key)
            if previous is not None and previous != fingerprint:
                raise DecisionRelayError("offer_version_conflict", "same series/version cannot carry different offer facts")
            series_versions[key] = fingerprint
        elif kind == "response":
            event = _normalize_response(raw)
        else:
            raise DecisionRelayError("invalid_kind", f"unsupported event kind {kind}")

        fingerprint = canonical_digest(event)
        event_id = event["event_id"]
        previous = event_fingerprints.get(event_id)
        if previous is not None:
            if previous != fingerprint:
                raise DecisionRelayError("event_id_conflict", f"event_id {event_id} was reused with different facts")
            continue  # exact replay collapse
        event_fingerprints[event_id] = fingerprint
        events.append(event)

    return {
        "schema_version": 1,
        "snapshot_at": snapshot_at,
        "events": events,
    }


def _series_record(offer: dict[str, Any], response: dict[str, Any] | None, evaluated_at: str) -> dict[str, Any]:
    now = _ts(evaluated_at)
    expired = now > _ts(offer["expires_at"])
    base = {
        "series_id": offer["series_id"],
        "offer_version": offer["offer_version"],
        "counterparty_id": offer["counterparty_id"],
        "thread_id": offer["thread_id"],
        "currency": offer["currency"],
        "amount_minor": offer["amount_minor"],
        "terms_digest": offer["terms_digest"],
        "expires_at": offer["expires_at"],
        "response_event_id": response["event_id"] if response else None,
    }

    if response is None:
        if expired:
            return {**base, "status": "REISSUE_REQUIRED", "reason": "offer_expired_without_reviewed_response"}
        return {**base, "status": "AWAITING_RESPONSE", "reason": "no_reviewed_response_for_current_offer"}

    if _ts(response["received_at"]) < _ts(offer["issued_at"]):
        return {**base, "status": "EVIDENCE_CONFLICT", "reason": "response_predates_offer"}
    if _ts(response["received_at"]) > _ts(offer["expires_at"]):
        return {**base, "status": "LATE_RESPONSE_REVIEW", "reason": "response_received_after_offer_expiry"}

    identity_matches = response["counterparty_id"] == offer["counterparty_id"] and response["thread_id"] == offer["thread_id"]
    terms_match = (
        response["currency"] == offer["currency"]
        and response["amount_minor"] == offer["amount_minor"]
        and response["terms_digest"] == offer["terms_digest"]
    )
    if not identity_matches:
        return {**base, "status": "EVIDENCE_CONFLICT", "reason": "counterparty_or_thread_mismatch"}

    if response["response_class"] == "exact_acceptance":
        if not terms_match:
            return {**base, "status": "EVIDENCE_CONFLICT", "reason": "acceptance_does_not_match_current_offer_exactly"}
        return {
            **base,
            "status": "HUMAN_CLOSING_READY",
            "reason": "reviewed_exact_acceptance_matches_current_offer",
        }
    if response["response_class"] == "counteroffer":
        return {**base, "status": "COUNTEROFFER_REVIEW", "reason": "reviewed_counteroffer_requires_human_decision"}
    if response["response_class"] == "clarification":
        return {**base, "status": "CLARIFICATION_REQUIRED", "reason": "reviewed_clarification_requires_human_answer"}
    return {**base, "status": "DECLINED", "reason": "reviewed_decline_is_routine_terminal_state"}


def reconcile(batch: dict[str, Any], *, evaluated_at: str | None = None) -> dict[str, Any]:
    normalized = normalize_batch(batch)
    evaluated_at = _instant(evaluated_at or normalized["snapshot_at"], "evaluated_at")
    if _ts(evaluated_at) < _ts(normalized["snapshot_at"]):
        raise DecisionRelayError("evaluation_before_snapshot", "evaluated_at cannot predate snapshot_at")

    offers_by_series: dict[str, list[dict[str, Any]]] = {}
    responses: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []

    for event in normalized["events"]:
        event_time = event["issued_at"] if event["kind"] == "offer" else event["reviewed_at"]
        if _ts(event_time) > _ts(evaluated_at):
            quarantined.append({"event_id": event["event_id"], "reason": "future_evidence"})
            continue
        if event["kind"] == "offer":
            offers_by_series.setdefault(event["series_id"], []).append(event)
        else:
            responses.append(event)

    series_records: list[dict[str, Any]] = []
    for series_id in sorted(offers_by_series):
        offers = offers_by_series[series_id]
        offers.sort(key=lambda item: (item["offer_version"], _ts(item["issued_at"])))
        offer = offers[-1]
        matching = [
            item for item in responses
            if item["series_id"] == series_id and item["offer_version"] == offer["offer_version"]
        ]
        matching.sort(key=lambda item: (_ts(item["reviewed_at"]), _ts(item["received_at"]), item["event_id"]))

        stale_after_supersession = [
            item for item in responses
            if item["series_id"] == series_id
            and item["offer_version"] < offer["offer_version"]
            and _ts(item["reviewed_at"]) >= _ts(offer["issued_at"])
        ]
        if stale_after_supersession:
            latest_stale = sorted(
                stale_after_supersession,
                key=lambda item: (_ts(item["reviewed_at"]), _ts(item["received_at"]), item["event_id"]),
            )[-1]
            record = _series_record(offer, None, evaluated_at)
            record.update({
                "status": "EVIDENCE_CONFLICT",
                "reason": "response_to_superseded_offer_arrived_after_new_offer",
                "response_event_id": latest_stale["event_id"],
            })
            series_records.append(record)
            continue

        response_facts = {
            (
                item["response_class"], item["counterparty_id"], item["thread_id"],
                item["currency"], item["amount_minor"], item["terms_digest"],
            )
            for item in matching
        }
        if len(response_facts) > 1:
            latest = matching[-1]
            record = _series_record(offer, latest, evaluated_at)
            record.update({
                "status": "EVIDENCE_CONFLICT",
                "reason": "conflicting_reviewed_responses_for_current_offer",
            })
            series_records.append(record)
            continue

        response = matching[-1] if matching else None
        series_records.append(_series_record(offer, response, evaluated_at))

    orphan_responses = []
    offer_keys = {(offer["series_id"], offer["offer_version"]) for offers in offers_by_series.values() for offer in offers}
    for response in responses:
        if (response["series_id"], response["offer_version"]) not in offer_keys:
            orphan_responses.append({"event_id": response["event_id"], "reason": "response_without_matching_offer"})

    decisions = [deepcopy(item) for item in series_records if item["status"] in DECISION_STATUSES]
    routine_count = sum(item["status"] in ROUTINE_STATUSES for item in series_records)
    source_digest = canonical_digest(normalized)
    body = {
        "schema_version": 1,
        "receipt_type": "commercial_decision_relay",
        "source_digest": source_digest,
        "evaluated_at": evaluated_at,
        "series": series_records,
        "decision_queue": decisions,
        "quarantined": quarantined + orphan_responses,
        "summary": {
            "series_count": len(series_records),
            "decision_count": len(decisions),
            "routine_count": routine_count,
            "quarantine_count": len(quarantined) + len(orphan_responses),
        },
        "authority": deepcopy(AUTHORITY),
    }
    body["receipt_sha256"] = canonical_digest(body)
    return body


def receipt_self_digest_matches(receipt: dict[str, Any]) -> bool:
    if not isinstance(receipt, dict):
        return False
    claimed = receipt.get("receipt_sha256")
    if not isinstance(claimed, str) or not HEX64.fullmatch(claimed):
        return False
    body = deepcopy(receipt)
    body.pop("receipt_sha256", None)
    return canonical_digest(body) == claimed


def _validate_receipt_shape(receipt: dict[str, Any]) -> None:
    if not isinstance(receipt, dict):
        raise DecisionRelayError("invalid_receipt_schema", "receipt must be an object")
    required_root = {
        "schema_version", "receipt_type", "source_digest", "evaluated_at", "series",
        "decision_queue", "quarantined", "summary", "authority", "receipt_sha256",
    }
    if set(receipt) != required_root:
        raise DecisionRelayError("invalid_receipt_schema", "receipt root fields must match the exact schema")
    schema_version = receipt.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        raise DecisionRelayError("invalid_receipt_schema", "receipt schema_version must be the integer 1")
    if type(receipt.get("receipt_type")) is not str or receipt.get("receipt_type") != "commercial_decision_relay":
        raise DecisionRelayError("invalid_receipt_schema", "receipt type/schema version mismatch")
    _hex64(receipt.get("source_digest"), "source_digest")
    _hex64(receipt.get("receipt_sha256"), "receipt_sha256")
    _instant(receipt.get("evaluated_at"), "evaluated_at")
    if not isinstance(receipt.get("series"), list) or not isinstance(receipt.get("decision_queue"), list):
        raise DecisionRelayError("invalid_receipt_schema", "series and decision_queue must be arrays")
    if not isinstance(receipt.get("quarantined"), list):
        raise DecisionRelayError("invalid_receipt_schema", "quarantined must be an array")
    summary = receipt.get("summary")
    summary_keys = {"series_count", "decision_count", "routine_count", "quarantine_count"}
    if not isinstance(summary, dict) or set(summary) != summary_keys:
        raise DecisionRelayError("invalid_receipt_schema", "summary must match the exact schema")
    if any(type(value) is not int or value < 0 for value in summary.values()):
        raise DecisionRelayError("invalid_receipt_schema", "summary counters must be non-negative integers")
    if summary["series_count"] != len(receipt["series"]) or summary["decision_count"] != len(receipt["decision_queue"]):
        raise DecisionRelayError("invalid_receipt_schema", "summary counters do not match receipt arrays")
    if summary["quarantine_count"] != len(receipt["quarantined"]):
        raise DecisionRelayError("invalid_receipt_schema", "quarantine counter does not match receipt array")
    authority = receipt.get("authority")
    if not isinstance(authority, dict) or set(authority) != set(AUTHORITY):
        raise DecisionRelayError("invalid_receipt_schema", "authority must match the exact schema")
    if any(type(authority[key]) is not bool for key in AUTHORITY):
        raise DecisionRelayError("invalid_receipt_schema", "authority values must be exact booleans")


def _assert_authority(receipt: dict[str, Any]) -> None:
    _validate_receipt_shape(receipt)
    if any(receipt["authority"][key] is not False for key in AUTHORITY):
        raise AuthorityBoundaryError("authority_escalation", "receipt authority must remain all-false")
    for record in receipt["series"]:
        if not isinstance(record, dict) or record.get("status") not in DECISION_STATUSES | ROUTINE_STATUSES:
            raise DecisionRelayError("unknown_status", "receipt contains an unknown decision status")
    expected_decisions = [record for record in receipt["series"] if record.get("status") in DECISION_STATUSES]
    if canonical_json(receipt["decision_queue"]) != canonical_json(expected_decisions):
        raise DecisionRelayError("invalid_decision_queue", "decision_queue must exactly mirror decision-status series")
    expected_routine = sum(record.get("status") in ROUTINE_STATUSES for record in receipt["series"] if isinstance(record, dict))
    if receipt["summary"]["routine_count"] != expected_routine:
        raise DecisionRelayError("invalid_receipt_schema", "routine counter does not match series statuses")


def _verify_at(
    receipt: dict[str, Any],
    expected_receipt_sha256: str,
    source_batch: dict[str, Any],
    *,
    evaluated_at: str,
    require_embedded_time_match: bool,
) -> bool:
    try:
        expected = _hex64(expected_receipt_sha256, "expected_receipt_sha256")
        trusted = _instant(evaluated_at, "evaluated_at")
    except DecisionRelayError:
        return False
    if not receipt_self_digest_matches(receipt):
        return False
    try:
        _assert_authority(receipt)
    except DecisionRelayError:
        return False
    if receipt.get("receipt_sha256") != expected:
        return False
    try:
        embedded = _instant(receipt.get("evaluated_at"), "evaluated_at")
    except DecisionRelayError:
        return False
    if require_embedded_time_match and embedded != trusted:
        return False
    try:
        recomputed = reconcile(source_batch, evaluated_at=trusted)
    except DecisionRelayError:
        return False
    return canonical_json(recomputed) == canonical_json(receipt)


def verify_receipt(
    receipt: dict[str, Any],
    expected_receipt_sha256: str,
    source_batch: dict[str, Any],
    *,
    evaluated_at: str | None = None,
) -> bool:
    """Verify deterministic historical integrity.

    When ``evaluated_at`` is omitted, recomputation uses the receipt's embedded
    instant. Current authority checks must use :func:`verify_current_receipt`.
    """
    if not isinstance(receipt, dict):
        return False
    try:
        embedded = _instant(receipt.get("evaluated_at"), "evaluated_at")
    except DecisionRelayError:
        return False
    when = embedded if evaluated_at is None else evaluated_at
    return _verify_at(
        receipt,
        expected_receipt_sha256,
        source_batch,
        evaluated_at=when,
        require_embedded_time_match=evaluated_at is not None,
    )


def verify_current_receipt(
    receipt: dict[str, Any],
    expected_receipt_sha256: str,
    source_batch: dict[str, Any],
    *,
    evaluated_at: str,
) -> bool:
    """Verify current authority at an externally supplied trusted instant."""
    return _verify_at(
        receipt,
        expected_receipt_sha256,
        source_batch,
        evaluated_at=evaluated_at,
        require_embedded_time_match=True,
    )


@dataclass
class RelayEngine:
    """In-memory evidence engine exposed to Strands tools.

    It deliberately owns no email, signing, payment, checkout, fulfillment, or
    revenue mutation capability.
    """

    batch: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None

    def ingest(self, batch: dict[str, Any]) -> dict[str, Any]:
        self.batch = normalize_batch(batch)
        self.receipt = None
        return {
            "accepted": True,
            "event_count": len(self.batch["events"]),
            "source_digest": canonical_digest(self.batch),
            "snapshot_at": self.batch["snapshot_at"],
        }

    def reconcile(self, *, evaluated_at: str | None = None) -> dict[str, Any]:
        if self.batch is None:
            raise DecisionRelayError("no_batch", "ingest normalized evidence before reconciliation")
        self.receipt = reconcile(self.batch, evaluated_at=evaluated_at)
        return deepcopy(self.receipt)

    def decisions(self) -> list[dict[str, Any]]:
        if self.receipt is None:
            raise DecisionRelayError("no_receipt", "reconcile evidence before reading the decision queue")
        return deepcopy(self.receipt["decision_queue"])

    def explain(self, series_id: str) -> dict[str, Any]:
        if self.receipt is None:
            raise DecisionRelayError("no_receipt", "reconcile evidence before explaining a series")
        sid = _text(series_id, "series_id")
        for record in self.receipt["series"]:
            if record["series_id"] == sid:
                return deepcopy(record)
        raise DecisionRelayError("unknown_series", f"series {sid} was not found")

    def verify(self, expected_receipt_sha256: str, *, evaluated_at: str | None = None) -> bool:
        if self.batch is None or self.receipt is None:
            raise DecisionRelayError("no_receipt", "ingest and reconcile before verification")
        if evaluated_at is None:
            raise DecisionRelayError(
                "trusted_time_required",
                "current receipt verification requires caller-supplied trusted evaluated_at",
            )
        return verify_current_receipt(
            self.receipt,
            expected_receipt_sha256,
            self.batch,
            evaluated_at=evaluated_at,
        )

    def mutate_commercial_authority(self, *_: Any, **__: Any) -> None:
        raise AuthorityBoundaryError(
            "forbidden_authority",
            "Commercial Decision Relay cannot sign, contract, invoice, charge, start fulfillment, or recognize revenue",
        )
