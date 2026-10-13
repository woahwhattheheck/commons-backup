#!/usr/bin/env python3
"""Deterministic, buyer-neutral revenue lifecycle projector from immutable receipts.

The projector is read-only. It does not send messages, contact providers, or
manufacture lifecycle progress from silence. Every state transition must be
backed by an explicit receipt and PAID requires verified settlement evidence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

INPUT_SCHEMA = "revenue-event-receipts/v1"
OUTPUT_SCHEMA = "revenue-event-lifecycle/v1"

START = "START"
RESEARCHED = "RESEARCHED"
MUSE_SELECTED = "MUSE_SELECTED"
PROVIDER_SENT = "PROVIDER_SENT"
HUMAN_ROUTED = "HUMAN_ROUTED"
SCOPE_REQUEST = "SCOPE_REQUEST"
DNR = "DNR"
BOUNCE = "BOUNCE"
PROPOSAL_SENT = "PROPOSAL_SENT"
ACCEPTED = "ACCEPTED"
PAID = "PAID"

LIFECYCLE_STATES = {
    START,
    RESEARCHED,
    MUSE_SELECTED,
    PROVIDER_SENT,
    HUMAN_ROUTED,
    SCOPE_REQUEST,
    DNR,
    BOUNCE,
    PROPOSAL_SENT,
    ACCEPTED,
    PAID,
}

SOURCES = {"SLACK", "GMAIL", "PROVIDER", "PAYMENT"}
KINDS = {
    "RESEARCHED",
    "MUSE_SELECTED",
    "PROVIDER_SENT",
    "AUTO_ACK",
    "SUPPORT_TICKET",
    "HUMAN_ROUTED",
    "SCOPE_REQUEST",
    "DNR",
    "BOUNCE",
    "PROPOSAL_SENT",
    "ACCEPTED",
    "PAYMENT_SETTLED",
}
SIDE_KINDS = {"AUTO_ACK", "SUPPORT_TICKET"}
HUMAN_KINDS = {"HUMAN_ROUTED", "SCOPE_REQUEST", "ACCEPTED"}
TERMINAL_NEGATIVE = {DNR, BOUNCE}
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class ReceiptError(ValueError):
    pass


@dataclass(frozen=True)
class Receipt:
    id: str
    source: str
    kind: str
    observed_at: dt.datetime
    buyer_scope: str
    offer_key: str
    purpose_key: str
    seat: Optional[str] = None
    expires_at: Optional[dt.datetime] = None
    human: Optional[bool] = None
    verified: Optional[bool] = None
    settlement_id: Optional[str] = None
    amount_minor: Optional[int] = None
    currency: Optional[str] = None


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ReceiptError(f"{field} must be a string")
    value = unicodedata.normalize("NFKC", value).strip()
    if not value:
        raise ReceiptError(f"{field} must not be empty")
    return value


def _key(value: Any, field: str) -> str:
    return _text(value, field).casefold()


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ReceiptError(f"{field} must be a boolean")
    return value


def _int(value: Any, field: str, lo: int = 0, hi: int = 10**15) -> int:
    if type(value) is not int:
        raise ReceiptError(f"{field} must be an integer")
    if not lo <= value <= hi:
        raise ReceiptError(f"{field} must be between {lo} and {hi}")
    return value


def _parse_ts(value: Any, field: str) -> dt.datetime:
    raw = _text(value, field)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        out = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ReceiptError(f"{field} must be ISO-8601") from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise ReceiptError(f"{field} must include a timezone")
    return out.astimezone(dt.timezone.utc)


def _ts(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_source(kind: str, source: str) -> None:
    allowed = {
        "RESEARCHED": {"SLACK"},
        "MUSE_SELECTED": {"SLACK"},
        "PROVIDER_SENT": {"GMAIL", "PROVIDER"},
        "AUTO_ACK": {"GMAIL", "PROVIDER"},
        "SUPPORT_TICKET": {"GMAIL", "PROVIDER"},
        "HUMAN_ROUTED": {"GMAIL", "PROVIDER", "SLACK"},
        "SCOPE_REQUEST": {"GMAIL", "PROVIDER", "SLACK"},
        "DNR": {"GMAIL", "PROVIDER", "SLACK"},
        "BOUNCE": {"GMAIL", "PROVIDER"},
        "PROPOSAL_SENT": {"GMAIL", "PROVIDER"},
        "ACCEPTED": {"GMAIL", "PROVIDER", "SLACK"},
        "PAYMENT_SETTLED": {"PAYMENT"},
    }[kind]
    if source not in allowed:
        raise ReceiptError(f"{kind} cannot be sourced from {source}")


def _receipt(row: Mapping[str, Any], index: int, as_of: dt.datetime) -> Receipt:
    prefix = f"receipts[{index}]"
    if not isinstance(row, Mapping):
        raise ReceiptError(f"{prefix} must be an object")
    rid = _text(row.get("id"), f"{prefix}.id")
    source = _text(row.get("source"), f"{prefix}.source").upper()
    kind = _text(row.get("kind"), f"{prefix}.kind").upper()
    if source not in SOURCES:
        raise ReceiptError(f"{prefix}.source unsupported")
    if kind not in KINDS:
        raise ReceiptError(f"{prefix}.kind unsupported")
    _require_source(kind, source)
    observed = _parse_ts(row.get("observed_at"), f"{prefix}.observed_at")
    if observed > as_of:
        raise ReceiptError(f"{prefix}.observed_at must not be after as_of")

    seat = None
    expires = None
    human = None
    verified = None
    settlement_id = None
    amount_minor = None
    currency = None

    if kind == "MUSE_SELECTED":
        seat = _key(row.get("seat"), f"{prefix}.seat")
        expires = _parse_ts(row.get("expires_at"), f"{prefix}.expires_at")
        if expires < observed:
            raise ReceiptError(f"{prefix}.expires_at precedes observed_at")

    if kind in HUMAN_KINDS:
        human = _bool(row.get("human"), f"{prefix}.human")
        if not human:
            raise ReceiptError(f"{prefix}.human must be true for {kind}")
    elif kind in SIDE_KINDS:
        if "human" in row and _bool(row.get("human"), f"{prefix}.human"):
            raise ReceiptError(f"{prefix}.human must not be true for {kind}")
        human = False

    if kind == "PAYMENT_SETTLED":
        verified = _bool(row.get("verified"), f"{prefix}.verified")
        settlement_id = _text(row.get("settlement_id"), f"{prefix}.settlement_id")
        amount_minor = _int(row.get("amount_minor"), f"{prefix}.amount_minor", 1)
        currency = _text(row.get("currency"), f"{prefix}.currency").upper()
        if not _CURRENCY_RE.fullmatch(currency):
            raise ReceiptError(f"{prefix}.currency must be three ASCII letters")

    return Receipt(
        id=rid,
        source=source,
        kind=kind,
        observed_at=observed,
        buyer_scope=_key(row.get("buyer_scope"), f"{prefix}.buyer_scope"),
        offer_key=_key(row.get("offer_key"), f"{prefix}.offer_key"),
        purpose_key=_key(row.get("purpose_key"), f"{prefix}.purpose_key"),
        seat=seat,
        expires_at=expires,
        human=human,
        verified=verified,
        settlement_id=settlement_id,
        amount_minor=amount_minor,
        currency=currency,
    )


def _event_view(rec: Receipt) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": rec.id,
        "source": rec.source,
        "kind": rec.kind,
        "observed_at": _ts(rec.observed_at),
        "buyer_scope": rec.buyer_scope,
        "offer_key": rec.offer_key,
        "purpose_key": rec.purpose_key,
    }
    if rec.seat is not None:
        out["seat"] = rec.seat
    if rec.expires_at is not None:
        out["expires_at"] = _ts(rec.expires_at)
    if rec.human is not None:
        out["human"] = rec.human
    if rec.verified is not None:
        out["verified"] = rec.verified
        out["settlement_id"] = rec.settlement_id
        out["amount_minor"] = rec.amount_minor
        out["currency"] = rec.currency
    return out


def project(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ReceiptError("top-level payload must be an object")
    if payload.get("schema") != INPUT_SCHEMA:
        raise ReceiptError(f"schema must equal {INPUT_SCHEMA!r}")

    as_of = _parse_ts(payload.get("as_of"), "as_of")
    buyer = _key(payload.get("buyer_scope"), "buyer_scope")
    offer = _key(payload.get("offer_key"), "offer_key")
    purpose = _key(payload.get("purpose_key"), "purpose_key")
    rows = payload.get("receipts")
    if not isinstance(rows, list):
        raise ReceiptError("receipts must be an array")

    receipts = [_receipt(row, i, as_of) for i, row in enumerate(rows)]
    ids = [r.id for r in receipts]
    if len(ids) != len(set(ids)):
        dupes = sorted({rid for rid in ids if ids.count(rid) > 1})
        raise ReceiptError("duplicate receipt id(s): " + ", ".join(dupes))

    # This projector is buyer-neutral but exact-key scoped: unrelated receipts
    # are rejected rather than silently dropped, preventing cross-buyer leakage.
    for rec in receipts:
        if (rec.buyer_scope, rec.offer_key, rec.purpose_key) != (buyer, offer, purpose):
            raise ReceiptError(f"receipt {rec.id} key does not match projector key")

    # Receipt order is evidence time, then exact immutable ID for deterministic
    # ties. Conflicting mutating events at the same time are diagnosed below.
    receipts = sorted(receipts, key=lambda r: (r.observed_at, r.id))
    evidence_view = {
        "schema": INPUT_SCHEMA,
        "as_of": _ts(as_of),
        "buyer_scope": buyer,
        "offer_key": offer,
        "purpose_key": purpose,
        "receipts": [_event_view(r) for r in receipts],
    }

    diagnostics: List[Dict[str, Any]] = []
    side_events = {"AUTO_ACK": [], "SUPPORT_TICKET": []}

    # Collision and stale-owner diagnostics are independent of lifecycle stage.
    selections = [r for r in receipts if r.kind == "MUSE_SELECTED"]
    active = [r for r in selections if r.expires_at is not None and r.expires_at >= as_of]
    active_seats = sorted({r.seat for r in active if r.seat})
    if len(active_seats) > 1:
        diagnostics.append({
            "code": "COLLISION_MULTIPLE_ACTIVE_MUSE_SELECTIONS",
            "receipt_ids": [r.id for r in active],
            "seats": active_seats,
        })

    state = START
    state_receipt_id: Optional[str] = None
    state_observed_at: Optional[dt.datetime] = None
    evidence_path: List[Dict[str, str]] = []
    valid_provider_send = False

    def advance(new_state: str, rec: Receipt) -> None:
        nonlocal state, state_receipt_id, state_observed_at
        state = new_state
        state_receipt_id = rec.id
        state_observed_at = rec.observed_at
        evidence_path.append({"state": new_state, "receipt_id": rec.id, "observed_at": _ts(rec.observed_at)})

    # Same-timestamp mutating conflicts are deterministic but flagged because
    # the receipt time alone cannot establish real-world order.
    mutating_kinds = KINDS - SIDE_KINDS
    by_time: Dict[dt.datetime, List[Receipt]] = defaultdict(list)
    for rec in receipts:
        if rec.kind in mutating_kinds:
            by_time[rec.observed_at].append(rec)
    for when, same_time in sorted(by_time.items()):
        if len({r.kind for r in same_time}) > 1:
            diagnostics.append({
                "code": "AMBIGUOUS_SAME_TIMESTAMP_MUTATIONS",
                "observed_at": _ts(when),
                "receipt_ids": [r.id for r in same_time],
                "kinds": sorted({r.kind for r in same_time}),
            })

    for rec in receipts:
        if rec.kind in SIDE_KINDS:
            side_events[rec.kind].append(rec.id)
            continue

        if state in TERMINAL_NEGATIVE:
            diagnostics.append({"code": "POST_TERMINAL_RECEIPT_IGNORED", "receipt_ids": [rec.id], "terminal_state": state})
            continue

        if rec.kind == "RESEARCHED":
            if state == START:
                advance(RESEARCHED, rec)
            elif state != RESEARCHED:
                diagnostics.append({"code": "NONADVANCING_RECEIPT", "receipt_ids": [rec.id], "kind": rec.kind, "state": state})
            continue

        if rec.kind == "MUSE_SELECTED":
            if state == RESEARCHED:
                advance(MUSE_SELECTED, rec)
            elif state == MUSE_SELECTED:
                diagnostics.append({"code": "MULTIPLE_MUSE_SELECTION_RECEIPTS", "receipt_ids": [rec.id]})
            else:
                diagnostics.append({"code": "MISSING_PREDECESSOR_RESEARCHED", "receipt_ids": [rec.id]})
            continue

        if rec.kind == "PROVIDER_SENT":
            if state == MUSE_SELECTED:
                # Only an unexpired selection at send time can authorize this
                # transition as evidence of a coordinated send.
                candidate = [s for s in selections if s.observed_at <= rec.observed_at and s.expires_at is not None and s.expires_at >= rec.observed_at]
                if not candidate:
                    diagnostics.append({"code": "PROVIDER_SENT_WITHOUT_LIVE_MUSE_SELECTION", "receipt_ids": [rec.id]})
                else:
                    advance(PROVIDER_SENT, rec)
                    valid_provider_send = True
            else:
                diagnostics.append({"code": "MISSING_PREDECESSOR_MUSE_SELECTED", "receipt_ids": [rec.id]})
            continue

        if rec.kind == "HUMAN_ROUTED":
            if state == PROVIDER_SENT:
                advance(HUMAN_ROUTED, rec)
            elif state not in {HUMAN_ROUTED, SCOPE_REQUEST, PROPOSAL_SENT, ACCEPTED, PAID}:
                diagnostics.append({"code": "MISSING_PREDECESSOR_PROVIDER_SENT", "receipt_ids": [rec.id]})
            continue

        if rec.kind == "SCOPE_REQUEST":
            if state in {PROVIDER_SENT, HUMAN_ROUTED}:
                advance(SCOPE_REQUEST, rec)
            elif state not in {SCOPE_REQUEST, PROPOSAL_SENT, ACCEPTED, PAID}:
                diagnostics.append({"code": "MISSING_PREDECESSOR_PROVIDER_SENT", "receipt_ids": [rec.id]})
            continue

        if rec.kind == "DNR":
            if state in {PROVIDER_SENT, HUMAN_ROUTED, SCOPE_REQUEST}:
                advance(DNR, rec)
            else:
                diagnostics.append({"code": "DNR_WITHOUT_PROVIDER_SENT", "receipt_ids": [rec.id]})
            continue

        if rec.kind == "BOUNCE":
            if state == PROVIDER_SENT:
                advance(BOUNCE, rec)
            else:
                diagnostics.append({"code": "BOUNCE_WITHOUT_PROVIDER_SENT", "receipt_ids": [rec.id]})
            continue

        if rec.kind == "PROPOSAL_SENT":
            if state in {HUMAN_ROUTED, SCOPE_REQUEST}:
                advance(PROPOSAL_SENT, rec)
            else:
                diagnostics.append({"code": "MISSING_PREDECESSOR_HUMAN_EVENT", "receipt_ids": [rec.id]})
            continue

        if rec.kind == "ACCEPTED":
            if state == PROPOSAL_SENT:
                advance(ACCEPTED, rec)
            else:
                diagnostics.append({"code": "MISSING_PREDECESSOR_PROPOSAL_SENT", "receipt_ids": [rec.id]})
            continue

        if rec.kind == "PAYMENT_SETTLED":
            if not rec.verified:
                diagnostics.append({"code": "UNVERIFIED_SETTLEMENT_IGNORED", "receipt_ids": [rec.id]})
            elif state == ACCEPTED:
                advance(PAID, rec)
            else:
                diagnostics.append({"code": "SETTLEMENT_WITHOUT_ACCEPTED", "receipt_ids": [rec.id]})
            continue

        raise RuntimeError(f"unhandled receipt kind {rec.kind}")

    # A selected owner that expires without a valid provider send is stale.
    if selections and not valid_provider_send:
        expired = [r for r in selections if r.expires_at is not None and r.expires_at < as_of]
        if expired:
            diagnostics.append({
                "code": "STALE_OWNER_SELECTION",
                "receipt_ids": [r.id for r in expired],
                "seats": sorted({r.seat for r in expired if r.seat}),
            })

    # A live collision never rewrites the evidence-backed lifecycle state, but
    # it does block any interpretation that one seat is authoritative.
    collision = any(d["code"] == "COLLISION_MULTIPLE_ACTIVE_MUSE_SELECTIONS" for d in diagnostics)

    settlement = None
    if state == PAID:
        rec = next(r for r in receipts if r.id == state_receipt_id)
        settlement = {
            "receipt_id": rec.id,
            "settlement_id": rec.settlement_id,
            "amount_minor": rec.amount_minor,
            "currency": rec.currency,
            "verified": True,
        }

    result: Dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "as_of": _ts(as_of),
        "buyer_scope": buyer,
        "offer_key": offer,
        "purpose_key": purpose,
        "state": state,
        "state_receipt_id": state_receipt_id,
        "state_observed_at": _ts(state_observed_at) if state_observed_at else None,
        "evidence_path": evidence_path,
        "side_events": side_events,
        "silence_assessment": "NEUTRAL_NOT_EVIDENCE",
        "collision": collision,
        "diagnostics": diagnostics,
        "money_evidence": "VERIFIED_SETTLEMENT" if state == PAID else "NOT_ESTABLISHED",
        "cash_claim_authorized": state == PAID and settlement is not None,
        "settlement": settlement,
        "input_digest_sha256": _digest(evidence_view),
        "provider_mutation_performed": False,
    }

    if result["state"] not in LIFECYCLE_STATES:
        raise RuntimeError("invalid lifecycle state")
    if result["cash_claim_authorized"] and result["money_evidence"] != "VERIFIED_SETTLEMENT":
        raise RuntimeError("cash evidence invariant violated")
    if result["state"] == PAID and not result["settlement"]:
        raise RuntimeError("paid state without settlement")
    if result["provider_mutation_performed"] is not False:
        raise RuntimeError("read-only invariant violated")
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="revenue-event-receipts/v1 JSON file")
    args = parser.parse_args(argv)
    try:
        with open(args.input, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        result = project(payload)
    except (ReceiptError, OSError, json.JSONDecodeError) as exc:
        print(f"receipt-ledger-error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
