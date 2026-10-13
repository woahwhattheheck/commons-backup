"""Deterministic proof-of-value -> expansion/renewal evidence rail.

This module is deliberately provider-free. It evaluates caller-supplied evidence and
emits an integrity receipt. It never contacts a buyer, payment provider, or service.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

SCHEMA_VERSION = "1"
RECEIPT_VERSION = "1"
SIGNAL_MAX_AGE = timedelta(days=45)
SETTLEMENT_MAX_AGE = timedelta(days=180)
ACCEPTANCE_MAX_AGE = timedelta(days=180)
ALLOWED_SIGNAL_KINDS = {"EXPANSION_REQUEST", "RENEWAL_REQUEST"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")

AUTHORITY_FALSE = {
    "buyer_contact": False,
    "contract": False,
    "invoice_or_checkout": False,
    "payment": False,
    "fulfillment_start": False,
    "recognized_revenue": False,
    "causal_impact_claim": False,
}

RECEIPT_KEYS = {
    "receipt_version", "account_id", "offer", "decision", "hold_codes",
    "selected_catalog", "outcomes", "evidence_ids", "event_log", "authority",
    "notice", "receipt_digest",
}


class EvidenceError(ValueError):
    """Input cannot be safely interpreted."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _string(value: Any, field: str, *, max_len: int = 240) -> str:
    if not isinstance(value, str):
        raise EvidenceError(f"{field}:string")
    value = value.strip()
    if not value or len(value) > max_len or "\x00" in value:
        raise EvidenceError(f"{field}:bounds")
    return value


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{field}:object")
    return value


def _list(value: Any, field: str, *, max_len: int = 256) -> list[Any]:
    if not isinstance(value, list) or len(value) > max_len:
        raise EvidenceError(f"{field}:array")
    return value


def _int_cents(value: Any, field: str, *, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"{field}:integer")
    if value < 0 or (not allow_zero and value == 0) or value > 10**12:
        raise EvidenceError(f"{field}:bounds")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    text = _string(value, field, max_len=64)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{field}:timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise EvidenceError(f"{field}:timezone")
    return dt.astimezone(timezone.utc)


def _hex64(value: Any, field: str) -> str:
    text = _string(value, field, max_len=64).lower()
    if not HEX64.fullmatch(text):
        raise EvidenceError(f"{field}:sha256")
    return text


def _finite_decimal(value: Any, field: str) -> str:
    if isinstance(value, bool):
        raise EvidenceError(f"{field}:number")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EvidenceError(f"{field}:number") from exc
    if not d.is_finite() or d.copy_abs() > Decimal("1e18"):
        raise EvidenceError(f"{field}:finite")
    text = format(d.normalize(), "f")
    if len(text) > 96:
        raise EvidenceError(f"{field}:bounds")
    return text


def _normalize_catalog_row(raw: Any, field: str) -> tuple[dict[str, Any], datetime, datetime | None]:
    row = _mapping(raw, field)
    catalog_id = _string(row.get("catalog_id"), f"{field}.catalog_id", max_len=120)
    version = _string(row.get("version"), f"{field}.version", max_len=64)
    kind = _string(row.get("kind"), f"{field}.kind", max_len=32).upper()
    currency = _string(row.get("currency"), f"{field}.currency", max_len=12).upper()
    price_cents = _int_cents(row.get("price_cents"), f"{field}.price_cents", allow_zero=False)
    scope_digest = _hex64(row.get("scope_digest"), f"{field}.scope_digest")
    active_from = _timestamp(row.get("active_from"), f"{field}.active_from")
    active_until_raw = row.get("active_until")
    active_until = _timestamp(active_until_raw, f"{field}.active_until") if active_until_raw is not None else None
    if active_until is not None and active_until <= active_from:
        raise EvidenceError(f"{field}:activation_window")
    identity = {
        "catalog_id": catalog_id,
        "version": version,
        "kind": kind,
        "currency": currency,
        "price_cents": price_cents,
        "scope_digest": scope_digest,
        "active_from": active_from.isoformat().replace("+00:00", "Z"),
        "active_until": active_until.isoformat().replace("+00:00", "Z") if active_until is not None else None,
    }
    normalized = dict(identity)
    normalized["row_digest"] = digest_json(identity)
    return normalized, active_from, active_until


def catalog_row_digest(row: Any) -> str:
    """Return the canonical SHA-256 identity for one complete catalog revision."""
    normalized, _, _ = _normalize_catalog_row(row, "catalog")
    return normalized["row_digest"]


def _minimal_receipt(record: Any, hold_code: str) -> dict[str, Any]:
    account_id = "UNKNOWN"
    offer_id = "UNKNOWN"
    offer_version = "UNKNOWN"
    if isinstance(record, dict):
        raw_account = record.get("account_id")
        if isinstance(raw_account, str) and 0 < len(raw_account.strip()) <= 120:
            account_id = raw_account.strip()
        raw_offer = record.get("offer")
        if isinstance(raw_offer, dict):
            if isinstance(raw_offer.get("offer_id"), str) and raw_offer["offer_id"].strip():
                offer_id = raw_offer["offer_id"].strip()[:120]
            if isinstance(raw_offer.get("version"), str) and raw_offer["version"].strip():
                offer_version = raw_offer["version"].strip()[:64]
    body = {
        "receipt_version": RECEIPT_VERSION,
        "account_id": account_id,
        "offer": {"offer_id": offer_id, "version": offer_version},
        "decision": "HOLD",
        "hold_codes": [hold_code],
        "selected_catalog": [],
        "outcomes": [],
        "evidence_ids": [],
        "event_log": {"unique": 0, "exact_replays": 0, "conflicts": 0},
        "authority": deepcopy(AUTHORITY_FALSE),
        "notice": "Integrity receipt only; not buyer acceptance, contract, payment, or revenue authority.",
    }
    body["receipt_digest"] = digest_json(body)
    return body


def _event_log_summary(events: list[Any], holds: set[str]) -> dict[str, int]:
    seen: dict[str, str] = {}
    exact_replays = 0
    conflicts = 0
    for idx, raw in enumerate(events):
        event = _mapping(raw, f"event_log[{idx}]")
        if set(event) != {"event_id", "payload"}:
            raise EvidenceError(f"event_log[{idx}]:shape")
        event_id = _string(event.get("event_id"), f"event_log[{idx}].event_id", max_len=160)
        payload_digest = digest_json(event["payload"])
        prior = seen.get(event_id)
        if prior is None:
            seen[event_id] = payload_digest
        elif prior == payload_digest:
            exact_replays += 1
        else:
            conflicts += 1
            holds.add("EVENT_ID_PAYLOAD_CONFLICT")
    return {"unique": len(seen), "exact_replays": exact_replays, "conflicts": conflicts}


def evaluate(record: Any) -> dict[str, Any]:
    """Evaluate one commercial evidence packet and return a deterministic receipt."""
    try:
        top = _mapping(record, "record")
        if top.get("schema_version") != SCHEMA_VERSION:
            raise EvidenceError("schema_version")
        account_id = _string(top.get("account_id"), "account_id", max_len=120)
        as_of = _timestamp(top.get("as_of"), "as_of")

        offer = _mapping(top.get("offer"), "offer")
        offer_id = _string(offer.get("offer_id"), "offer.offer_id", max_len=120)
        offer_version = _string(offer.get("version"), "offer.version", max_len=64)
        offer_currency = _string(offer.get("currency"), "offer.currency", max_len=12).upper()
        expected_cents = _int_cents(offer.get("expected_cents"), "offer.expected_cents", allow_zero=False)
        scope_digest = _hex64(offer.get("scope_digest"), "offer.scope_digest")
        issued_at = _timestamp(offer.get("issued_at"), "offer.issued_at")
        expires_at = _timestamp(offer.get("expires_at"), "offer.expires_at")
        if issued_at >= expires_at:
            raise EvidenceError("offer:window")

        holds: set[str] = set()
        if as_of < issued_at:
            holds.add("AS_OF_BEFORE_OFFER")
        if as_of > expires_at:
            holds.add("OFFER_EXPIRED")

        settlement = _mapping(top.get("settlement"), "settlement")
        settlement_id = _string(settlement.get("evidence_id"), "settlement.evidence_id", max_len=160)
        settlement_account_id = _string(settlement.get("account_id"), "settlement.account_id", max_len=120)
        settlement_offer_id = _string(settlement.get("offer_id"), "settlement.offer_id", max_len=120)
        settlement_version = _string(settlement.get("offer_version"), "settlement.offer_version", max_len=64)
        settlement_currency = _string(settlement.get("currency"), "settlement.currency", max_len=12).upper()
        net_cents = _int_cents(settlement.get("net_cents"), "settlement.net_cents")
        refunded_cents = _int_cents(settlement.get("refunded_cents"), "settlement.refunded_cents")
        disputed_cents = _int_cents(settlement.get("disputed_cents"), "settlement.disputed_cents")
        settlement_status = _string(settlement.get("status"), "settlement.status", max_len=32).upper()
        settled_at = _timestamp(settlement.get("settled_at"), "settlement.settled_at")
        captured_at = _timestamp(settlement.get("captured_at"), "settlement.captured_at")
        if settlement_account_id != account_id:
            holds.add("SETTLEMENT_ACCOUNT_MISMATCH")
        if settlement_offer_id != offer_id or settlement_version != offer_version:
            holds.add("SETTLEMENT_OFFER_MISMATCH")
        if settlement_currency != offer_currency:
            holds.add("SETTLEMENT_CURRENCY_MISMATCH")
        if settlement_status != "SETTLED":
            holds.add("SETTLEMENT_NOT_FINAL")
        if refunded_cents:
            holds.add("SETTLEMENT_REFUNDED")
        if disputed_cents:
            holds.add("SETTLEMENT_DISPUTED")
        if net_cents < expected_cents:
            holds.add("SETTLEMENT_AMOUNT_SHORT")
        if captured_at < settled_at:
            holds.add("SETTLEMENT_CAPTURE_PRECEDES_SETTLEMENT")
        if captured_at > as_of + timedelta(minutes=5):
            holds.add("SETTLEMENT_EVIDENCE_FROM_FUTURE")
        if as_of - captured_at > SETTLEMENT_MAX_AGE:
            holds.add("SETTLEMENT_EVIDENCE_STALE")

        acceptance = _mapping(top.get("delivery_acceptance"), "delivery_acceptance")
        acceptance_id = _string(acceptance.get("evidence_id"), "delivery_acceptance.evidence_id", max_len=160)
        acceptance_account_id = _string(acceptance.get("account_id"), "delivery_acceptance.account_id", max_len=120)
        acceptance_offer_id = _string(acceptance.get("offer_id"), "delivery_acceptance.offer_id", max_len=120)
        acceptance_version = _string(acceptance.get("offer_version"), "delivery_acceptance.offer_version", max_len=64)
        acceptance_scope = _hex64(acceptance.get("scope_digest"), "delivery_acceptance.scope_digest")
        acceptance_status = _string(acceptance.get("status"), "delivery_acceptance.status", max_len=32).upper()
        acceptance_class = _string(acceptance.get("accepted_by_class"), "delivery_acceptance.accepted_by_class", max_len=48).upper()
        accepted_at = _timestamp(acceptance.get("accepted_at"), "delivery_acceptance.accepted_at")
        if acceptance_account_id != account_id:
            holds.add("ACCEPTANCE_ACCOUNT_MISMATCH")
        if acceptance_offer_id != offer_id or acceptance_version != offer_version:
            holds.add("ACCEPTANCE_OFFER_MISMATCH")
        if acceptance_scope != scope_digest:
            holds.add("ACCEPTANCE_SCOPE_MISMATCH")
        if acceptance_status != "ACCEPTED":
            holds.add("DELIVERY_NOT_ACCEPTED")
        if acceptance_class != "BUYER_HUMAN":
            holds.add("ACCEPTANCE_NOT_BUYER_HUMAN")
        if accepted_at > as_of + timedelta(minutes=5):
            holds.add("ACCEPTANCE_FROM_FUTURE")
        if as_of - accepted_at > ACCEPTANCE_MAX_AGE:
            holds.add("ACCEPTANCE_STALE")

        signal = _mapping(top.get("buyer_signal"), "buyer_signal")
        signal_id = _string(signal.get("evidence_id"), "buyer_signal.evidence_id", max_len=160)
        signal_account_id = _string(signal.get("account_id"), "buyer_signal.account_id", max_len=120)
        signal_kind = _string(signal.get("kind"), "buyer_signal.kind", max_len=32).upper()
        signal_source = _string(signal.get("source_class"), "buyer_signal.source_class", max_len=48).upper()
        signal_offer_id = _string(signal.get("offer_id"), "buyer_signal.offer_id", max_len=120)
        signal_observed = _timestamp(signal.get("observed_at"), "buyer_signal.observed_at")
        requested_catalog_ids = [
            _string(v, f"buyer_signal.requested_catalog_ids[{i}]", max_len=120)
            for i, v in enumerate(_list(signal.get("requested_catalog_ids"), "buyer_signal.requested_catalog_ids", max_len=32))
        ]
        if len(set(requested_catalog_ids)) != len(requested_catalog_ids) or not requested_catalog_ids:
            holds.add("BUYER_SIGNAL_CATALOG_INVALID")
        if signal_account_id != account_id:
            holds.add("BUYER_SIGNAL_ACCOUNT_MISMATCH")
        if signal_kind not in ALLOWED_SIGNAL_KINDS:
            holds.add("BUYER_SIGNAL_KIND_INVALID")
        if signal_source != "BUYER_AUTHORED":
            holds.add("BUYER_SIGNAL_NOT_BUYER_AUTHORED")
        if signal_offer_id != offer_id:
            holds.add("BUYER_SIGNAL_OFFER_MISMATCH")
        if signal_observed > as_of + timedelta(minutes=5):
            holds.add("BUYER_SIGNAL_FROM_FUTURE")
        if as_of - signal_observed > SIGNAL_MAX_AGE:
            holds.add("BUYER_SIGNAL_STALE")
        if signal_observed < accepted_at:
            holds.add("BUYER_SIGNAL_PREDATES_ACCEPTANCE")

        approval = _mapping(top.get("owner_approval"), "owner_approval")
        approval_id = _string(approval.get("evidence_id"), "owner_approval.evidence_id", max_len=160)
        approval_account_id = _string(approval.get("account_id"), "owner_approval.account_id", max_len=120)
        approval_class = _string(approval.get("approver_class"), "owner_approval.approver_class", max_len=48).upper()
        approval_at = _timestamp(approval.get("approved_at"), "owner_approval.approved_at")
        approved_catalog_bindings: dict[str, tuple[str, str]] = {}
        for idx, raw in enumerate(_list(approval.get("approved_catalog_rows"), "owner_approval.approved_catalog_rows", max_len=32)):
            binding = _mapping(raw, f"owner_approval.approved_catalog_rows[{idx}]")
            if set(binding) != {"catalog_id", "version", "row_digest"}:
                raise EvidenceError(f"owner_approval.approved_catalog_rows[{idx}]:shape")
            approved_id = _string(binding.get("catalog_id"), f"owner_approval.approved_catalog_rows[{idx}].catalog_id", max_len=120)
            approved_version = _string(binding.get("version"), f"owner_approval.approved_catalog_rows[{idx}].version", max_len=64)
            approved_digest = _hex64(binding.get("row_digest"), f"owner_approval.approved_catalog_rows[{idx}].row_digest")
            prior = approved_catalog_bindings.get(approved_id)
            current = (approved_version, approved_digest)
            if prior is None:
                approved_catalog_bindings[approved_id] = current
            elif prior == current:
                holds.add("OWNER_APPROVAL_ENTRY_DUPLICATE")
            else:
                holds.add("OWNER_APPROVAL_ENTRY_CONFLICT")
        if approval_account_id != account_id:
            holds.add("OWNER_APPROVAL_ACCOUNT_MISMATCH")
        if approval_class != "OWNER_HUMAN":
            holds.add("OWNER_APPROVAL_NOT_HUMAN")
        if approval_at > as_of + timedelta(minutes=5):
            holds.add("OWNER_APPROVAL_FROM_FUTURE")
        if approval_at < signal_observed:
            holds.add("OWNER_APPROVAL_PREDATES_BUYER_SIGNAL")

        catalog_rows: dict[str, tuple[dict[str, Any], datetime, datetime | None]] = {}
        for idx, raw in enumerate(_list(top.get("catalog"), "catalog", max_len=64)):
            row, active_from, active_until = _normalize_catalog_row(raw, f"catalog[{idx}]")
            catalog_id = row["catalog_id"]
            if catalog_id in catalog_rows:
                holds.add("CATALOG_ID_DUPLICATE")
                continue
            if row["kind"] not in {"EXPANSION", "RENEWAL"}:
                holds.add("CATALOG_KIND_INVALID")
            if row["currency"] != offer_currency:
                holds.add("CATALOG_CURRENCY_MISMATCH")
            if as_of < active_from or (active_until is not None and as_of > active_until):
                holds.add("CATALOG_NOT_ACTIVE")
            catalog_rows[catalog_id] = (row, active_from, active_until)

        selected_catalog: list[dict[str, Any]] = []
        for catalog_id in sorted(set(requested_catalog_ids)):
            row_data = catalog_rows.get(catalog_id)
            if row_data is None:
                holds.add("CATALOG_ITEM_MISSING")
                continue
            row, active_from, _ = row_data
            expected_kind = "EXPANSION" if signal_kind == "EXPANSION_REQUEST" else "RENEWAL"
            if row["kind"] != expected_kind:
                holds.add("CATALOG_SIGNAL_KIND_MISMATCH")
            approved = approved_catalog_bindings.get(catalog_id)
            if approved is None:
                holds.add("CATALOG_NOT_OWNER_APPROVED")
            elif approved != (row["version"], row["row_digest"]):
                holds.add("CATALOG_APPROVAL_IDENTITY_MISMATCH")
            if signal_observed < active_from:
                holds.add("BUYER_SIGNAL_PREDATES_CATALOG_REVISION")
            if approval_at < active_from:
                holds.add("OWNER_APPROVAL_PREDATES_CATALOG_REVISION")
            selected_catalog.append(row)

        normalized_outcomes: list[dict[str, Any]] = []
        metric_ids: set[str] = set()
        for idx, raw in enumerate(_list(top.get("outcomes"), "outcomes", max_len=128)):
            outcome = _mapping(raw, f"outcomes[{idx}]")
            metric_id = _string(outcome.get("metric_id"), f"outcomes[{idx}].metric_id", max_len=120)
            if metric_id in metric_ids:
                holds.add("OUTCOME_METRIC_DUPLICATE")
            metric_ids.add(metric_id)
            definition_digest = _hex64(outcome.get("definition_digest"), f"outcomes[{idx}].definition_digest")
            unit = _string(outcome.get("unit"), f"outcomes[{idx}].unit", max_len=64)
            baseline_value = _finite_decimal(outcome.get("baseline_value"), f"outcomes[{idx}].baseline_value")
            observed_value = _finite_decimal(outcome.get("observed_value"), f"outcomes[{idx}].observed_value")
            baseline_start = _timestamp(outcome.get("baseline_start"), f"outcomes[{idx}].baseline_start")
            baseline_end = _timestamp(outcome.get("baseline_end"), f"outcomes[{idx}].baseline_end")
            observed_start = _timestamp(outcome.get("observed_start"), f"outcomes[{idx}].observed_start")
            observed_end = _timestamp(outcome.get("observed_end"), f"outcomes[{idx}].observed_end")
            claim_class = _string(outcome.get("claim_class"), f"outcomes[{idx}].claim_class", max_len=32).upper()
            causal_claim = outcome.get("causal_claim")
            if not isinstance(causal_claim, bool):
                raise EvidenceError(f"outcomes[{idx}].causal_claim:boolean")
            source_ids = sorted({
                _string(v, f"outcomes[{idx}].source_evidence_ids", max_len=160)
                for v in _list(outcome.get("source_evidence_ids"), f"outcomes[{idx}].source_evidence_ids", max_len=32)
            })
            if not source_ids:
                holds.add("OUTCOME_EVIDENCE_MISSING")
            if not (baseline_start < baseline_end <= observed_start < observed_end <= as_of + timedelta(minutes=5)):
                holds.add("OUTCOME_WINDOW_INVALID")
            if claim_class != "DESCRIPTIVE" or causal_claim:
                holds.add("CAUSAL_OUTCOME_CLAIM_FORBIDDEN")
            normalized_outcomes.append({
                "metric_id": metric_id,
                "definition_digest": definition_digest,
                "unit": unit,
                "baseline_value": baseline_value,
                "observed_value": observed_value,
                "baseline_start": baseline_start.isoformat().replace("+00:00", "Z"),
                "baseline_end": baseline_end.isoformat().replace("+00:00", "Z"),
                "observed_start": observed_start.isoformat().replace("+00:00", "Z"),
                "observed_end": observed_end.isoformat().replace("+00:00", "Z"),
                "claim_class": "DESCRIPTIVE",
                "source_evidence_ids": source_ids,
            })

        event_summary = _event_log_summary(_list(top.get("event_log"), "event_log", max_len=256), holds)
        if not normalized_outcomes:
            holds.add("OUTCOME_EVIDENCE_MISSING")

        decision = "HOLD"
        if not holds and selected_catalog:
            decision = "EXPANSION_READY" if signal_kind == "EXPANSION_REQUEST" else "RENEWAL_READY"

        body = {
            "receipt_version": RECEIPT_VERSION,
            "account_id": account_id,
            "offer": {"offer_id": offer_id, "version": offer_version},
            "decision": decision,
            "hold_codes": sorted(holds),
            "selected_catalog": sorted(selected_catalog, key=lambda x: (x["catalog_id"], x["version"])),
            "outcomes": sorted(normalized_outcomes, key=lambda x: x["metric_id"]),
            "evidence_ids": sorted({settlement_id, acceptance_id, signal_id, approval_id}),
            "event_log": event_summary,
            "authority": deepcopy(AUTHORITY_FALSE),
            "notice": "Integrity receipt only; not buyer acceptance, contract, payment, or revenue authority.",
        }
        body["receipt_digest"] = digest_json(body)
        return body
    except (EvidenceError, KeyError, TypeError, ValueError, OverflowError):
        return _minimal_receipt(record, "MALFORMED_INPUT")


def verify_receipt(receipt: Any) -> bool:
    """Verify exact receipt schema and digest; this is not authenticity/signature."""
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        return False
    if receipt.get("receipt_version") != RECEIPT_VERSION:
        return False
    if receipt.get("decision") not in {"EXPANSION_READY", "RENEWAL_READY", "HOLD"}:
        return False
    if not isinstance(receipt.get("account_id"), str) or not receipt["account_id"]:
        return False
    offer = receipt.get("offer")
    if not isinstance(offer, dict) or set(offer) != {"offer_id", "version"}:
        return False
    if not all(isinstance(offer.get(k), str) and offer[k] for k in ("offer_id", "version")):
        return False
    hold_codes = receipt.get("hold_codes")
    if not isinstance(hold_codes, list) or hold_codes != sorted(set(hold_codes)):
        return False
    if not all(isinstance(v, str) and v for v in hold_codes):
        return False
    if receipt["decision"] == "HOLD" and not hold_codes:
        return False
    if receipt["decision"] != "HOLD" and hold_codes:
        return False
    if not isinstance(receipt.get("selected_catalog"), list) or not isinstance(receipt.get("outcomes"), list):
        return False
    evidence_ids = receipt.get("evidence_ids")
    if not isinstance(evidence_ids, list) or evidence_ids != sorted(set(evidence_ids)):
        return False
    if not all(isinstance(v, str) and v for v in evidence_ids):
        return False
    event_log = receipt.get("event_log")
    if not isinstance(event_log, dict) or set(event_log) != {"unique", "exact_replays", "conflicts"}:
        return False
    if any(isinstance(event_log[k], bool) or not isinstance(event_log[k], int) or event_log[k] < 0 for k in event_log):
        return False
    if receipt.get("authority") != AUTHORITY_FALSE:
        return False
    if receipt.get("notice") != "Integrity receipt only; not buyer acceptance, contract, payment, or revenue authority.":
        return False
    digest = receipt.get("receipt_digest")
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        return False
    body = dict(receipt)
    body.pop("receipt_digest", None)
    return hmac.compare_digest(digest, digest_json(body))
