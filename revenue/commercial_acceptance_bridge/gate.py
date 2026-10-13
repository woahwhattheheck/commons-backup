"""Deterministic evidence bridge between human-reviewed replies and human closing.

The module accepts *normalized, human-reviewed* commercial evidence only. It does
not parse email, infer intent from text, determine signer/legal authority, create
contracts, collect payment, start fulfillment, or recognize revenue.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
MAX_EVENTS = 50_000
MAX_TEXT = 160
MAX_RECEIPT_AGE_SECONDS = 300
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
NONE = "NONE"

REVIEW_CLASSES = frozenset(
    {
        "EXACT_ACCEPT",
        "COUNTEROFFER",
        "PARTIAL_ACCEPT",
        "QUESTION",
        "DECLINE",
        "AMBIGUOUS",
    }
)

FORBIDDEN_RAW_KEYS = frozenset(
    {
        "body",
        "raw_body",
        "raw_email",
        "message_text",
        "quote_text",
        "name",
        "email",
        "phone",
        "address",
        "signature",
        "signer_name",
    }
)

OFFER_KEYS = frozenset(
    {
        "event_id",
        "kind",
        "offer_series_id",
        "offer_version_id",
        "version",
        "supersedes_version_id",
        "counterparty_id",
        "provider_thread_id",
        "scope_sha256",
        "acceptance_criteria_sha256",
        "terms_sha256",
        "currency",
        "price_minor",
        "issued_at",
        "expires_at",
    }
)
RESPONSE_KEYS = frozenset(
    {
        "event_id",
        "kind",
        "response_id",
        "provider_message_id",
        "provider_thread_id",
        "counterparty_id",
        "received_at",
        "reviewed_offer_version_id",
        "review_class",
        "scope_sha256",
        "acceptance_criteria_sha256",
        "terms_sha256",
        "currency",
        "price_minor",
        "reviewer_attestation_sha256",
    }
)
BATCH_KEYS = frozenset({"schema_version", "snapshot_at", "events"})

MATCH_FIELDS = (
    "scope_sha256",
    "acceptance_criteria_sha256",
    "terms_sha256",
    "currency",
    "price_minor",
)


class AcceptanceError(ValueError):
    """Fail-closed input or evidence-contract error with a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise AcceptanceError(code, message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _root(items: Iterable[Any]) -> str:
    return sha256_text("\n".join(sorted(canonical_json(item) for item in items)))


def _object(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_INPUT", f"{where} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], where: str) -> None:
    actual = frozenset(value.keys())
    missing = expected - actual
    extra = actual - expected
    if missing:
        _fail("MISSING_FIELD", f"{where} missing fields: {', '.join(sorted(missing))}")
    if extra:
        _fail("UNKNOWN_FIELD", f"{where} has unknown fields: {', '.join(sorted(extra))}")


def _text(value: Any, field: str) -> str:
    if type(value) is not str:
        _fail("INVALID_INPUT", f"{field} must be text")
    cleaned = value.strip()
    if not cleaned or cleaned != value or len(cleaned) > MAX_TEXT:
        _fail("INVALID_INPUT", f"{field} must be canonical non-empty text <= {MAX_TEXT} chars")
    return cleaned


def _id(value: Any, field: str) -> str:
    cleaned = _text(value, field)
    if not ID_RE.fullmatch(cleaned):
        _fail("INVALID_INPUT", f"{field} must be a canonical identifier")
    return cleaned


def _sha(value: Any, field: str) -> str:
    cleaned = _text(value, field)
    if not HEX_RE.fullmatch(cleaned):
        _fail("INVALID_INPUT", f"{field} must be lowercase SHA-256 hex")
    return cleaned


def _positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0 or value > 10**15:
        _fail("INVALID_INPUT", f"{field} must be a bounded positive integer")
    return value


def _timestamp(value: Any, field: str) -> tuple[str, datetime]:
    cleaned = _text(value, field)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cleaned):
        _fail("INVALID_INPUT", f"{field} must use canonical UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        _fail("INVALID_INPUT", f"{field} is not a real UTC timestamp")
    if parsed.tzinfo != timezone.utc:
        _fail("INVALID_INPUT", f"{field} must be UTC")
    return cleaned, parsed


def _currency(value: Any, field: str) -> str:
    cleaned = _text(value, field)
    if not CURRENCY_RE.fullmatch(cleaned):
        _fail("INVALID_INPUT", f"{field} must be an uppercase ISO-like 3-letter code")
    return cleaned


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _evaluation_time(value: str | datetime | None) -> datetime:
    if value is None:
        return _utcnow()
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timedelta(0) or value.microsecond:
            _fail("INVALID_EVALUATION_TIME", "evaluated_at must be whole-second UTC")
        return value.astimezone(timezone.utc)
    if type(value) is str:
        _, parsed = _timestamp(value, "evaluated_at")
        return parsed
    _fail("INVALID_EVALUATION_TIME", "evaluated_at must be canonical UTC text or datetime")


def _reject_raw_or_nested(event: Mapping[str, Any], where: str) -> None:
    for key, value in event.items():
        if not isinstance(key, str):
            _fail("INVALID_INPUT", f"{where} keys must be text")
        if key.lower() in FORBIDDEN_RAW_KEYS:
            _fail("RAW_CONTENT_FORBIDDEN", f"{key} is forbidden; supply normalized evidence only")
        if isinstance(value, (Mapping, list, tuple, set)):
            _fail("NESTED_DATA_FORBIDDEN", f"{key} must be scalar")
        if value is None or isinstance(value, float):
            _fail("INVALID_INPUT", f"{key} uses an unsupported scalar type")


def normalize_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    event = _object(raw, "event")
    _reject_raw_or_nested(event, "event")
    kind = _text(event.get("kind"), "kind")
    if kind == "offer":
        _exact_keys(event, OFFER_KEYS, "offer")
        issued_text, issued = _timestamp(event["issued_at"], "issued_at")
        expires_text, expires = _timestamp(event["expires_at"], "expires_at")
        if expires <= issued:
            _fail("INVALID_OFFER_WINDOW", "expires_at must be after issued_at")
        supersedes = _id(event["supersedes_version_id"], "supersedes_version_id")
        return {
            "event_id": _id(event["event_id"], "event_id"),
            "kind": kind,
            "offer_series_id": _id(event["offer_series_id"], "offer_series_id"),
            "offer_version_id": _id(event["offer_version_id"], "offer_version_id"),
            "version": _positive_int(event["version"], "version"),
            "supersedes_version_id": supersedes,
            "counterparty_id": _id(event["counterparty_id"], "counterparty_id"),
            "provider_thread_id": _id(event["provider_thread_id"], "provider_thread_id"),
            "scope_sha256": _sha(event["scope_sha256"], "scope_sha256"),
            "acceptance_criteria_sha256": _sha(event["acceptance_criteria_sha256"], "acceptance_criteria_sha256"),
            "terms_sha256": _sha(event["terms_sha256"], "terms_sha256"),
            "currency": _currency(event["currency"], "currency"),
            "price_minor": _positive_int(event["price_minor"], "price_minor"),
            "issued_at": issued_text,
            "expires_at": expires_text,
        }
    if kind == "response":
        _exact_keys(event, RESPONSE_KEYS, "response")
        received_text, _ = _timestamp(event["received_at"], "received_at")
        review_class = _text(event["review_class"], "review_class")
        if review_class not in REVIEW_CLASSES:
            _fail("INVALID_REVIEW_CLASS", f"unsupported review_class {review_class}")
        return {
            "event_id": _id(event["event_id"], "event_id"),
            "kind": kind,
            "response_id": _id(event["response_id"], "response_id"),
            "provider_message_id": _id(event["provider_message_id"], "provider_message_id"),
            "provider_thread_id": _id(event["provider_thread_id"], "provider_thread_id"),
            "counterparty_id": _id(event["counterparty_id"], "counterparty_id"),
            "received_at": received_text,
            "reviewed_offer_version_id": _id(event["reviewed_offer_version_id"], "reviewed_offer_version_id"),
            "review_class": review_class,
            "scope_sha256": _sha(event["scope_sha256"], "scope_sha256"),
            "acceptance_criteria_sha256": _sha(event["acceptance_criteria_sha256"], "acceptance_criteria_sha256"),
            "terms_sha256": _sha(event["terms_sha256"], "terms_sha256"),
            "currency": _currency(event["currency"], "currency"),
            "price_minor": _positive_int(event["price_minor"], "price_minor"),
            "reviewer_attestation_sha256": _sha(event["reviewer_attestation_sha256"], "reviewer_attestation_sha256"),
        }
    _fail("UNKNOWN_KIND", f"unsupported event kind {kind!r}")


def normalize_batch(payload: Mapping[str, Any]) -> dict[str, Any]:
    batch = _object(payload, "batch")
    _exact_keys(batch, BATCH_KEYS, "batch")
    if batch["schema_version"] != SCHEMA_VERSION:
        _fail("INVALID_SCHEMA_VERSION", f"schema_version must be {SCHEMA_VERSION}")
    snapshot_text, _ = _timestamp(batch["snapshot_at"], "snapshot_at")
    events = batch["events"]
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        _fail("INVALID_BATCH", "events must be a finite sequence")
    if len(events) > MAX_EVENTS:
        _fail("BATCH_TOO_LARGE", f"events exceed {MAX_EVENTS}")
    by_event_id: dict[str, dict[str, Any]] = {}
    replay_collapsed = 0
    for raw in events:
        event = normalize_event(raw)
        event_id = event["event_id"]
        previous = by_event_id.get(event_id)
        if previous is None:
            by_event_id[event_id] = event
        elif previous == event:
            replay_collapsed += 1
        else:
            _fail("IDEMPOTENCY_CONFLICT", f"event_id {event_id} was reused for changed content")
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_at": snapshot_text,
        "events": sorted(by_event_id.values(), key=lambda row: row["event_id"]),
        "input_records": len(events),
        "replay_collapsed": replay_collapsed,
    }


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _offer_match_differences(offer: Mapping[str, Any], response: Mapping[str, Any]) -> list[str]:
    return [field for field in MATCH_FIELDS if offer[field] != response[field]]


def _quarantine(event: Mapping[str, Any], code: str, *, series_id: str = "") -> dict[str, str]:
    return {
        "event_id": str(event["event_id"]),
        "kind": str(event["kind"]),
        "series_id": series_id,
        "code": code,
    }


def _counterparty_ref(counterparty_id: str) -> str:
    return sha256_text(f"counterparty\n{counterparty_id}")[:16]


def reconcile(
    payload: Mapping[str, Any],
    *,
    evaluated_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Reconcile normalized evidence at a trusted, fresh evaluation time.

    Production callers should omit ``evaluated_at`` so current UTC is used. The
    explicit argument exists for deterministic tests/replays and must never be
    populated from the untrusted evidence payload itself.
    """

    batch = normalize_batch(payload)
    evaluation = _evaluation_time(evaluated_at)
    snapshot = _parse(batch["snapshot_at"])
    if snapshot > evaluation:
        _fail("FUTURE_SNAPSHOT", "snapshot_at cannot be later than trusted evaluation time")
    if evaluation - snapshot > timedelta(seconds=MAX_RECEIPT_AGE_SECONDS):
        _fail("STALE_SNAPSHOT", f"snapshot_at is older than {MAX_RECEIPT_AGE_SECONDS} seconds")

    offers_raw = [row for row in batch["events"] if row["kind"] == "offer"]
    responses_raw = [row for row in batch["events"] if row["kind"] == "response"]

    offer_by_version: dict[str, dict[str, Any]] = {}
    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    quarantines: list[dict[str, str]] = []

    for offer in offers_raw:
        version_id = offer["offer_version_id"]
        if version_id in offer_by_version:
            _fail("DUPLICATE_OFFER_VERSION_ID", f"offer_version_id {version_id} appears more than once")
        if _parse(offer["issued_at"]) > snapshot:
            _fail("FUTURE_OFFER", f"offer {version_id} was issued after snapshot_at")
        offer_by_version[version_id] = offer
        series[offer["offer_series_id"]].append(offer)

    current_by_series: dict[str, dict[str, Any]] = {}
    for series_id, rows in series.items():
        ordered = sorted(rows, key=lambda row: row["version"])
        expected_versions = list(range(1, len(ordered) + 1))
        actual_versions = [row["version"] for row in ordered]
        if actual_versions != expected_versions:
            _fail("OFFER_VERSION_GAP", f"series {series_id} versions must be contiguous from 1")
        first = ordered[0]
        if first["supersedes_version_id"] != NONE:
            _fail("OFFER_LINEAGE_INVALID", f"series {series_id} version 1 must supersede NONE")
        invariant_counterparty = first["counterparty_id"]
        invariant_thread = first["provider_thread_id"]
        previous = first
        for row in ordered[1:]:
            if row["supersedes_version_id"] != previous["offer_version_id"]:
                _fail("OFFER_LINEAGE_INVALID", f"series {series_id} version {row['version']} must supersede the prior version")
            if row["counterparty_id"] != invariant_counterparty:
                _fail("OFFER_LINEAGE_INVALID", f"series {series_id} changes counterparty")
            if row["provider_thread_id"] != invariant_thread:
                _fail("OFFER_LINEAGE_INVALID", f"series {series_id} changes provider thread")
            if _parse(row["issued_at"]) <= _parse(previous["issued_at"]):
                _fail("OFFER_LINEAGE_INVALID", f"series {series_id} issue times must strictly increase")
            previous = row
        current_by_series[series_id] = ordered[-1]

    response_ids: set[str] = set()
    provider_messages: dict[str, dict[str, Any]] = {}
    valid_by_series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocking_by_series: dict[str, list[dict[str, str]]] = defaultdict(list)

    for response in responses_raw:
        response_id = response["response_id"]
        if response_id in response_ids:
            _fail("DUPLICATE_RESPONSE_ID", f"response_id {response_id} appears more than once")
        response_ids.add(response_id)
        provider_id = response["provider_message_id"]
        previous_provider = provider_messages.get(provider_id)
        if previous_provider is not None and previous_provider != response:
            _fail("PROVIDER_MESSAGE_COLLISION", f"provider_message_id {provider_id} maps to different normalized responses")
        provider_messages[provider_id] = response

        offer = offer_by_version.get(response["reviewed_offer_version_id"])
        if offer is None:
            quarantines.append(_quarantine(response, "UNKNOWN_OFFER_VERSION"))
            continue
        series_id = offer["offer_series_id"]
        current = current_by_series[series_id]
        received = _parse(response["received_at"])

        def block(code: str) -> None:
            row = _quarantine(response, code, series_id=series_id)
            quarantines.append(row)
            blocking_by_series[series_id].append(row)

        if received > snapshot:
            block("RESPONSE_AFTER_SNAPSHOT")
            continue
        if response["counterparty_id"] != offer["counterparty_id"]:
            block("COUNTERPARTY_MISMATCH")
            continue
        if response["provider_thread_id"] != offer["provider_thread_id"]:
            block("THREAD_MISMATCH")
            continue
        if received < _parse(offer["issued_at"]):
            block("RESPONSE_BEFORE_OFFER")
            continue
        if received > _parse(offer["expires_at"]):
            block("RESPONSE_AFTER_EXPIRY")
            continue
        if offer["offer_version_id"] != current["offer_version_id"]:
            quarantines.append(_quarantine(response, "SUPERSEDED_OFFER_VERSION", series_id=series_id))
            continue
        differences = _offer_match_differences(offer, response)
        response = dict(response)
        response["changed_fields"] = differences
        if response["review_class"] == "EXACT_ACCEPT" and differences:
            block("EXACT_ACCEPT_MISMATCH")
            continue
        valid_by_series[series_id].append(response)

    states: list[dict[str, Any]] = []
    state_counts: dict[str, int] = defaultdict(int)

    class_to_state = {
        "EXACT_ACCEPT": "HUMAN_CLOSING_READY",
        "COUNTEROFFER": "COUNTEROFFER_REVIEW",
        "PARTIAL_ACCEPT": "CLARIFICATION_REQUIRED",
        "QUESTION": "OWNER_REPLY_REQUIRED",
        "DECLINE": "DECLINED",
        "AMBIGUOUS": "HUMAN_REVIEW_REQUIRED",
    }
    class_to_next = {
        "EXACT_ACCEPT": "HUMAN_CLOSING_REVIEW",
        "COUNTEROFFER": "HUMAN_COUNTEROFFER_REVIEW",
        "PARTIAL_ACCEPT": "HUMAN_CLARIFICATION",
        "QUESTION": "HUMAN_REPLY",
        "DECLINE": "NO_ACTION",
        "AMBIGUOUS": "HUMAN_EVIDENCE_REVIEW",
    }

    for series_id in sorted(current_by_series):
        offer = current_by_series[series_id]
        responses = sorted(
            valid_by_series.get(series_id, []),
            key=lambda row: (row["received_at"], row["provider_message_id"]),
        )
        blockers = blocking_by_series.get(series_id, [])
        state_blocker_codes = sorted({row["code"] for row in blockers})
        state: str
        next_action: str
        effective_class = "NONE"
        effective_response_ref = ""
        changed_fields: list[str] = []

        if blockers:
            state = "HUMAN_REVIEW_REQUIRED"
            next_action = "HUMAN_EVIDENCE_REVIEW"
        elif responses:
            latest_time = responses[-1]["received_at"]
            tied = [row for row in responses if row["received_at"] == latest_time]
            if len(tied) > 1:
                state = "HUMAN_REVIEW_REQUIRED"
                next_action = "HUMAN_EVIDENCE_REVIEW"
            else:
                effective = responses[-1]
                effective_class = effective["review_class"]
                effective_response_ref = sha256_text(
                    f"provider-message\n{effective['provider_message_id']}"
                )[:16]
                changed_fields = list(effective["changed_fields"])
                state = class_to_state[effective_class]
                next_action = class_to_next[effective_class]
                if state == "HUMAN_CLOSING_READY" and evaluation > _parse(offer["expires_at"]):
                    state = "HUMAN_REVIEW_REQUIRED"
                    next_action = "HUMAN_EVIDENCE_REVIEW"
                    effective_class = "NONE"
                    effective_response_ref = ""
                    changed_fields = []
                    state_blocker_codes = ["OFFER_EXPIRED_AT_EVALUATION"]
        elif snapshot > _parse(offer["expires_at"]):
            state = "EXPIRED_NO_ACCEPTANCE"
            next_action = "HUMAN_REISSUE_DECISION"
        else:
            state = "AWAITING_RESPONSE"
            next_action = "NO_ACTION"

        state_counts[state] += 1
        states.append(
            {
                "offer_series_id": series_id,
                "offer_version_id": offer["offer_version_id"],
                "version": offer["version"],
                "counterparty_ref": _counterparty_ref(offer["counterparty_id"]),
                "state": state,
                "next_action": next_action,
                "effective_review_class": effective_class,
                "effective_response_ref": effective_response_ref,
                "changed_fields": changed_fields,
                "blocker_codes": state_blocker_codes,
                "contract_authority": False,
                "signer_authority_determined": False,
                "payment_authority": False,
                "fulfillment_authority": False,
                "revenue_authority": False,
            }
        )

    quarantines.sort(key=lambda row: (row["series_id"], row["event_id"], row["code"]))
    event_digests = [sha256_text(canonical_json(row)) for row in batch["events"]]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "product": "COMMERCIAL_ACCEPTANCE_BRIDGE",
        "authority": "NORMALIZED_HUMAN_REVIEWED_EVIDENCE_ONLY",
        "snapshot_at": batch["snapshot_at"],
        "input_records": batch["input_records"],
        "unique_events": len(batch["events"]),
        "replay_collapsed": batch["replay_collapsed"],
        "counts": {
            "offer_series": len(current_by_series),
            "offer_versions": len(offer_by_version),
            "responses": len(responses_raw),
            "quarantined": len(quarantines),
            "states": dict(sorted(state_counts.items())),
        },
        "series": states,
        "quarantines": quarantines,
        "roots": {
            "events_sha256": sha256_text("\n".join(sorted(event_digests))),
            "series_state_sha256": _root(states),
            "quarantine_sha256": _root(quarantines),
        },
        "authorities": {
            "raw_message_parsing": False,
            "signer_or_legal_authority": False,
            "contract_creation_or_execution": False,
            "invoice_or_checkout_creation": False,
            "payment_or_charge": False,
            "fulfillment_start": False,
            "recognized_revenue": False,
        },
    }
    manifest["receipt_sha256"] = sha256_text(canonical_json(manifest))
    return manifest


_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "product",
        "authority",
        "snapshot_at",
        "input_records",
        "unique_events",
        "replay_collapsed",
        "counts",
        "series",
        "quarantines",
        "roots",
        "authorities",
        "receipt_sha256",
    }
)
_COUNT_KEYS = frozenset({"offer_series", "offer_versions", "responses", "quarantined", "states"})
_ROOT_KEYS = frozenset({"events_sha256", "series_state_sha256", "quarantine_sha256"})
_AUTHORITY_KEYS = frozenset(
    {
        "raw_message_parsing",
        "signer_or_legal_authority",
        "contract_creation_or_execution",
        "invoice_or_checkout_creation",
        "payment_or_charge",
        "fulfillment_start",
        "recognized_revenue",
    }
)
_SERIES_KEYS = frozenset(
    {
        "offer_series_id",
        "offer_version_id",
        "version",
        "counterparty_ref",
        "state",
        "next_action",
        "effective_review_class",
        "effective_response_ref",
        "changed_fields",
        "blocker_codes",
        "contract_authority",
        "signer_authority_determined",
        "payment_authority",
        "fulfillment_authority",
        "revenue_authority",
    }
)
_QUARANTINE_KEYS = frozenset({"event_id", "kind", "series_id", "code"})
_STATE_NEXT_ACTION = {
    "HUMAN_CLOSING_READY": "HUMAN_CLOSING_REVIEW",
    "COUNTEROFFER_REVIEW": "HUMAN_COUNTEROFFER_REVIEW",
    "CLARIFICATION_REQUIRED": "HUMAN_CLARIFICATION",
    "OWNER_REPLY_REQUIRED": "HUMAN_REPLY",
    "DECLINED": "NO_ACTION",
    "HUMAN_REVIEW_REQUIRED": "HUMAN_EVIDENCE_REVIEW",
    "AWAITING_RESPONSE": "NO_ACTION",
    "EXPIRED_NO_ACCEPTANCE": "HUMAN_REISSUE_DECISION",
}
_STATE_REVIEW_CLASS = {
    "HUMAN_CLOSING_READY": "EXACT_ACCEPT",
    "COUNTEROFFER_REVIEW": "COUNTEROFFER",
    "CLARIFICATION_REQUIRED": "PARTIAL_ACCEPT",
    "OWNER_REPLY_REQUIRED": "QUESTION",
    "DECLINED": "DECLINE",
    "AWAITING_RESPONSE": "NONE",
    "EXPIRED_NO_ACCEPTANCE": "NONE",
}
_BLOCKER_CODES = frozenset(
    {
        "RESPONSE_AFTER_SNAPSHOT",
        "COUNTERPARTY_MISMATCH",
        "THREAD_MISMATCH",
        "RESPONSE_BEFORE_OFFER",
        "RESPONSE_AFTER_EXPIRY",
        "EXACT_ACCEPT_MISMATCH",
        "OFFER_EXPIRED_AT_EVALUATION",
    }
)
_QUARANTINE_CODES = _BLOCKER_CODES - {"OFFER_EXPIRED_AT_EVALUATION"} | frozenset(
    {"UNKNOWN_OFFER_VERSION", "SUPERSEDED_OFFER_VERSION"}
)
_REF16_RE = re.compile(r"^[0-9a-f]{16}$")


def receipt_self_digest_matches(manifest: Mapping[str, Any]) -> bool:
    """Return only whether the receipt's self-authored digest matches its bytes."""

    if not isinstance(manifest, Mapping):
        return False
    digest = manifest.get("receipt_sha256")
    if type(digest) is not str or not HEX_RE.fullmatch(digest):
        return False
    unsigned = deepcopy(dict(manifest))
    unsigned.pop("receipt_sha256", None)
    return sha256_text(canonical_json(unsigned)) == digest


def _receipt_exact_keys(value: Any, expected: frozenset[str]) -> bool:
    return isinstance(value, Mapping) and frozenset(value.keys()) == expected


def _receipt_bounded_int(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_EVENTS


def _receipt_identifier(value: Any, *, allow_empty: bool = False) -> bool:
    if allow_empty and value == "":
        return True
    return type(value) is str and bool(ID_RE.fullmatch(value))


def _receipt_timestamp(value: Any) -> bool:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc


def _receipt_series_row_valid(row: Any) -> bool:
    if not _receipt_exact_keys(row, _SERIES_KEYS):
        return False
    if not _receipt_identifier(row["offer_series_id"]) or not _receipt_identifier(row["offer_version_id"]):
        return False
    if type(row["version"]) is not int or row["version"] <= 0 or row["version"] > MAX_EVENTS:
        return False
    if type(row["counterparty_ref"]) is not str or not _REF16_RE.fullmatch(row["counterparty_ref"]):
        return False
    state = row["state"]
    if state not in _STATE_NEXT_ACTION or row["next_action"] != _STATE_NEXT_ACTION[state]:
        return False
    review_class = row["effective_review_class"]
    if review_class not in REVIEW_CLASSES | {"NONE"}:
        return False
    expected_class = _STATE_REVIEW_CLASS.get(state)
    if expected_class is not None and review_class != expected_class:
        return False
    if state == "HUMAN_REVIEW_REQUIRED" and review_class not in {"NONE", "AMBIGUOUS"}:
        return False
    response_ref = row["effective_response_ref"]
    if review_class == "NONE":
        if response_ref != "":
            return False
    elif type(response_ref) is not str or not _REF16_RE.fullmatch(response_ref):
        return False
    changed_fields = row["changed_fields"]
    if not isinstance(changed_fields, list) or any(type(field) is not str or field not in MATCH_FIELDS for field in changed_fields):
        return False
    if len(changed_fields) != len(set(changed_fields)):
        return False
    if changed_fields != [field for field in MATCH_FIELDS if field in set(changed_fields)]:
        return False
    blocker_codes = row["blocker_codes"]
    if not isinstance(blocker_codes, list) or any(type(code) is not str or code not in _BLOCKER_CODES for code in blocker_codes):
        return False
    if blocker_codes != sorted(set(blocker_codes)):
        return False
    if blocker_codes and (state != "HUMAN_REVIEW_REQUIRED" or review_class != "NONE"):
        return False
    if state in {"AWAITING_RESPONSE", "EXPIRED_NO_ACCEPTANCE"} and (response_ref or changed_fields or blocker_codes):
        return False
    for key in (
        "contract_authority",
        "signer_authority_determined",
        "payment_authority",
        "fulfillment_authority",
        "revenue_authority",
    ):
        if row[key] is not False:
            return False
    return True


def _receipt_quarantine_row_valid(row: Any) -> bool:
    if not _receipt_exact_keys(row, _QUARANTINE_KEYS):
        return False
    if not _receipt_identifier(row["event_id"]) or row["kind"] != "response":
        return False
    if not _receipt_identifier(row["series_id"], allow_empty=True):
        return False
    code = row["code"]
    if code not in _QUARANTINE_CODES:
        return False
    if code == "UNKNOWN_OFFER_VERSION":
        return row["series_id"] == ""
    return row["series_id"] != ""


def _receipt_schema_valid(manifest: Mapping[str, Any]) -> bool:
    if not _receipt_exact_keys(manifest, _RECEIPT_KEYS):
        return False
    if manifest["schema_version"] != SCHEMA_VERSION:
        return False
    if manifest["product"] != "COMMERCIAL_ACCEPTANCE_BRIDGE":
        return False
    if manifest["authority"] != "NORMALIZED_HUMAN_REVIEWED_EVIDENCE_ONLY":
        return False
    if not _receipt_timestamp(manifest["snapshot_at"]):
        return False
    for key in ("input_records", "unique_events", "replay_collapsed"):
        if not _receipt_bounded_int(manifest[key]):
            return False
    if manifest["unique_events"] > manifest["input_records"]:
        return False
    if manifest["replay_collapsed"] != manifest["input_records"] - manifest["unique_events"]:
        return False

    counts = manifest["counts"]
    if not _receipt_exact_keys(counts, _COUNT_KEYS):
        return False
    for key in ("offer_series", "offer_versions", "responses", "quarantined"):
        if not _receipt_bounded_int(counts[key]):
            return False
    states_count = counts["states"]
    if not isinstance(states_count, Mapping):
        return False
    if any(type(key) is not str or key not in _STATE_NEXT_ACTION for key in states_count):
        return False
    if any(type(value) is not int or value <= 0 or value > MAX_EVENTS for value in states_count.values()):
        return False

    series = manifest["series"]
    quarantines = manifest["quarantines"]
    if not isinstance(series, list) or not isinstance(quarantines, list):
        return False
    if len(series) > MAX_EVENTS or len(quarantines) > MAX_EVENTS:
        return False
    if not all(_receipt_series_row_valid(row) for row in series):
        return False
    if not all(_receipt_quarantine_row_valid(row) for row in quarantines):
        return False
    series_ids = [row["offer_series_id"] for row in series]
    version_ids = [row["offer_version_id"] for row in series]
    if len(series_ids) != len(set(series_ids)) or len(version_ids) != len(set(version_ids)):
        return False
    computed_states: dict[str, int] = defaultdict(int)
    for row in series:
        computed_states[row["state"]] += 1
    if dict(sorted(computed_states.items())) != dict(states_count):
        return False
    if counts["offer_series"] != len(series):
        return False
    if counts["quarantined"] != len(quarantines):
        return False
    if counts["offer_versions"] < counts["offer_series"]:
        return False
    if counts["responses"] < counts["quarantined"]:
        return False
    if manifest["unique_events"] != counts["offer_versions"] + counts["responses"]:
        return False

    roots = manifest["roots"]
    if not _receipt_exact_keys(roots, _ROOT_KEYS):
        return False
    if any(type(roots[key]) is not str or not HEX_RE.fullmatch(roots[key]) for key in _ROOT_KEYS):
        return False
    if roots["series_state_sha256"] != _root(series):
        return False
    if roots["quarantine_sha256"] != _root(quarantines):
        return False

    authorities = manifest["authorities"]
    if not _receipt_exact_keys(authorities, _AUTHORITY_KEYS):
        return False
    if any(authorities[key] is not False for key in _AUTHORITY_KEYS):
        return False
    return True


def verify_receipt(
    manifest: Mapping[str, Any],
    expected_receipt_sha256: str,
    source_payload: Mapping[str, Any],
    *,
    evaluated_at: str | datetime | None = None,
) -> bool:
    """Validate a receipt against commitment, source evidence, and trusted time.

    ``expected_receipt_sha256`` and ``source_payload`` must come from trusted channels
    outside the receipt being checked. Production callers should omit ``evaluated_at``
    so current UTC enforces the five-minute snapshot freshness and current-offer expiry
    fences. Explicit evaluation time is for deterministic tests/replays only.
    """

    if type(expected_receipt_sha256) is not str or not HEX_RE.fullmatch(expected_receipt_sha256):
        return False
    if not receipt_self_digest_matches(manifest):
        return False
    if manifest.get("receipt_sha256") != expected_receipt_sha256:
        return False
    if not _receipt_schema_valid(manifest):
        return False
    try:
        recomputed = reconcile(source_payload, evaluated_at=evaluated_at)
    except (AcceptanceError, TypeError, ValueError):
        return False
    return recomputed == dict(manifest)
