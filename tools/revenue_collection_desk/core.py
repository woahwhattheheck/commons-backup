"""Deterministic receivables / collection-state compiler.

Consumes sanitized retained evidence only. It never sends messages, moves money,
creates invoices, contacts providers, or recognizes cash without explicit
SETTLED_CASH evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import (
    Context, Decimal, Inexact, InvalidOperation, MAX_EMAX, MIN_EMIN,
    Overflow, ROUND_HALF_EVEN, Rounded, localcontext,
)
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

LEDGER_SCHEMA = "commons.revenue_collection_ledger/v1"
REPORT_SCHEMA = "commons.revenue_collection_report/v1"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9._:@/-]{1,256}$")
_INSTRUMENT = re.compile(r"^[A-Z][A-Z0-9._-]{0,15}$")
_AMOUNT = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?$")

FINANCIAL_KINDS = {
    "WORK_SUBMITTED",
    "ACCEPTED",
    "PAYMENT_ASSERTED",
    "PAYMENT_AVAILABLE",
    "SETTLED_CASH",
    "DISPUTED",
    "CLOSED_NO_PAY",
}
EVIDENCE_KINDS = {
    "ENTITLEMENT_CONFIRMED",
}
ROUTE_KINDS = {
    "COLLECTION_CONTACT_SENT",
    "DELIVERY_CONFIRMED",
    "DELIVERY_BOUNCED",
    "ROUTE_REPAIRED",
    "COLLECTION_RELEASED",
}
ALL_KINDS = FINANCIAL_KINDS | EVIDENCE_KINDS | ROUTE_KINDS

STATE_SUBMITTED = "WORK_SUBMITTED"
STATE_ACCEPTED = "ACCEPTED_AWAITING_PAYMENT"
STATE_ASSERTED = "PAYMENT_ASSERTED_HOLD"
STATE_AVAILABLE = "PAYMENT_AVAILABLE"
STATE_SETTLED = "SETTLED_CASH"
STATE_DISPUTED = "DISPUTED"
STATE_CLOSED = "CLOSED_NO_PAY"

ACTIONS = {
    "WAIT_HOLD",
    "WAIT_REPLY",
    "VERIFY_AVAILABLE",
    "VERIFY_SETTLEMENT",
    "VERIFY_ENTITLEMENT",
    "COLLECTION_ELIGIBLE",
    "ROUTE_REPAIR_REQUIRED",
    "DONE",
    "HOLD_CONFLICT",
}

AUTHORITY = {
    "send_email": False,
    "send_slack": False,
    "submit_claim": False,
    "create_invoice": False,
    "move_money": False,
    "wallet_mutation": False,
    "bank_mutation": False,
    "provider_mutation": False,
    "recognize_unsettled_cash": False,
}

class ContractError(ValueError):
    pass

def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant: {value}")

def _pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def loads_strict(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ContractError("input must be strict UTF-8") from exc
    if type(raw) is not str:
        raise ContractError("JSON input must be str or bytes")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc

def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError(f"value is not canonical JSON: {exc}") from exc

def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def _exact_object(value: Any, required: set[str], allowed: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{label} must be an object")
    keys = set(value)
    missing = required - keys
    extra = keys - allowed
    if missing or extra:
        raise ContractError(
            f"{label} keys mismatch missing={sorted(missing)} extra={sorted(extra)}"
        )
    return value

def _text(value: Any, label: str, pattern: re.Pattern[str] | None = None, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise ContractError(f"{label} must be a non-empty bounded string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ContractError(f"{label} has invalid format")
    return value

def _digest(value: Any, label: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise ContractError(f"{label} must be lowercase sha256")
    return value

def _instant(value: Any, label: str) -> tuple[datetime, str]:
    text = _text(value, label, maximum=64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{label} must include timezone")
    try:
        utc = parsed.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ContractError(f"{label} is outside the supported UTC range") from exc
    rendered = utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return utc, rendered

def _amount(value: Any, label: str, *, allow_zero: bool = False) -> tuple[Decimal, str]:
    if type(value) is not str or _AMOUNT.fullmatch(value) is None:
        raise ContractError(f"{label} must be an exact non-negative decimal string")
    try:
        dec = Decimal(value)
    except InvalidOperation as exc:
        raise ContractError(f"{label} is invalid decimal") from exc
    if dec < 0 or (dec == 0 and not allow_zero):
        raise ContractError(f"{label} must be {'non-negative' if allow_zero else 'positive'}")
    return dec, value

def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"

def _instrument(value: Any, label: str) -> str:
    return _text(value, label, _INSTRUMENT, 16)

def _source_ref(value: Any, label: str) -> str:
    return _text(value, label, _TOKEN, 256)

_ROOT_REQUIRED = {"schema", "as_of", "claims"}
_CLAIM_REQUIRED = {
    "claim_id", "counterparty_id", "work_ref", "instrument", "amount", "events"
}
_CLAIM_ALLOWED = _CLAIM_REQUIRED | {"reference_valuation"}
_REF_REQUIRED = {"currency", "amount", "source_ref", "source_digest"}
_EVENT_COMMON = {"event_id", "at", "kind", "source_ref", "source_digest"}
_EVENT_ALLOWED = _EVENT_COMMON | {
    "hold_until",
    "cooldown_until",
    "settlement_currency",
    "settlement_amount",
    "entitlement_instrument",
    "entitlement_amount",
}

def _normalize_reference(value: Any, label: str) -> dict[str, Any]:
    obj = _exact_object(value, _REF_REQUIRED, _REF_REQUIRED, label)
    _, amount = _amount(obj["amount"], f"{label}.amount")
    return {
        "currency": _instrument(obj["currency"], f"{label}.currency"),
        "amount": amount,
        "source_ref": _source_ref(obj["source_ref"], f"{label}.source_ref"),
        "source_digest": _digest(obj["source_digest"], f"{label}.source_digest"),
        "cash_recognition": False,
    }

def _normalize_event(value: Any, label: str) -> tuple[dict[str, Any], datetime]:
    obj = _exact_object(value, _EVENT_COMMON, _EVENT_ALLOWED, label)
    kind = _text(obj["kind"], f"{label}.kind", maximum=64)
    if kind not in ALL_KINDS:
        raise ContractError(f"{label}.kind unsupported: {kind}")
    at_dt, at = _instant(obj["at"], f"{label}.at")
    out = {
        "event_id": _source_ref(obj["event_id"], f"{label}.event_id"),
        "at": at,
        "kind": kind,
        "source_ref": _source_ref(obj["source_ref"], f"{label}.source_ref"),
        "source_digest": _digest(obj["source_digest"], f"{label}.source_digest"),
    }
    extras = set(obj) - _EVENT_COMMON
    if kind == "PAYMENT_ASSERTED":
        if extras - {"hold_until"}:
            raise ContractError(f"{label}: PAYMENT_ASSERTED only permits hold_until")
        if "hold_until" in obj:
            hold_dt, hold = _instant(obj["hold_until"], f"{label}.hold_until")
            if hold_dt < at_dt:
                raise ContractError(f"{label}.hold_until precedes event")
            out["hold_until"] = hold
    elif kind == "ENTITLEMENT_CONFIRMED":
        if extras != {"entitlement_instrument", "entitlement_amount"}:
            raise ContractError(
                f"{label}: ENTITLEMENT_CONFIRMED requires entitlement_instrument "
                "and entitlement_amount"
            )
        _, entitlement_amount = _amount(
            obj["entitlement_amount"], f"{label}.entitlement_amount"
        )
        out["entitlement_instrument"] = _instrument(
            obj["entitlement_instrument"], f"{label}.entitlement_instrument"
        )
        out["entitlement_amount"] = entitlement_amount
    elif kind == "COLLECTION_CONTACT_SENT":
        if extras != {"cooldown_until"}:
            raise ContractError(f"{label}: COLLECTION_CONTACT_SENT requires only cooldown_until")
        cooldown_dt, cooldown = _instant(obj["cooldown_until"], f"{label}.cooldown_until")
        if cooldown_dt < at_dt:
            raise ContractError(f"{label}.cooldown_until precedes event")
        out["cooldown_until"] = cooldown
    elif kind == "SETTLED_CASH":
        if extras != {"settlement_currency", "settlement_amount"}:
            raise ContractError(
                f"{label}: SETTLED_CASH requires settlement_currency and settlement_amount"
            )
        _, settlement_amount = _amount(obj["settlement_amount"], f"{label}.settlement_amount")
        out["settlement_currency"] = _instrument(
            obj["settlement_currency"], f"{label}.settlement_currency"
        )
        out["settlement_amount"] = settlement_amount
    elif extras:
        raise ContractError(f"{label}: {kind} does not permit extra fields")
    return out, at_dt

def _apply_financial(state: str | None, kind: str) -> str:
    if state is None:
        if kind != "WORK_SUBMITTED":
            raise ContractError("first financial event must be WORK_SUBMITTED")
        return STATE_SUBMITTED
    if kind == "WORK_SUBMITTED":
        raise ContractError("WORK_SUBMITTED cannot repeat")
    allowed: dict[str, dict[str, str]] = {
        STATE_SUBMITTED: {
            "ACCEPTED": STATE_ACCEPTED,
            "DISPUTED": STATE_DISPUTED,
            "CLOSED_NO_PAY": STATE_CLOSED,
        },
        STATE_ACCEPTED: {
            "PAYMENT_ASSERTED": STATE_ASSERTED,
            "PAYMENT_AVAILABLE": STATE_AVAILABLE,
            "SETTLED_CASH": STATE_SETTLED,
            "DISPUTED": STATE_DISPUTED,
            "CLOSED_NO_PAY": STATE_CLOSED,
        },
        STATE_ASSERTED: {
            "PAYMENT_AVAILABLE": STATE_AVAILABLE,
            "SETTLED_CASH": STATE_SETTLED,
            "DISPUTED": STATE_DISPUTED,
            "CLOSED_NO_PAY": STATE_CLOSED,
        },
        STATE_AVAILABLE: {
            "SETTLED_CASH": STATE_SETTLED,
            "DISPUTED": STATE_DISPUTED,
            "CLOSED_NO_PAY": STATE_CLOSED,
        },
        STATE_DISPUTED: {
            "SETTLED_CASH": STATE_SETTLED,
            "CLOSED_NO_PAY": STATE_CLOSED,
        },
        STATE_SETTLED: {},
        STATE_CLOSED: {},
    }
    if kind not in allowed[state]:
        raise ContractError(f"illegal financial transition {state} -> {kind}")
    return allowed[state][kind]

def _normalize_claim(value: Any, index: int, as_of_dt: datetime) -> dict[str, Any]:
    label = f"claims[{index}]"
    obj = _exact_object(value, _CLAIM_REQUIRED, _CLAIM_ALLOWED, label)
    claim_id = _source_ref(obj["claim_id"], f"{label}.claim_id")
    counterparty_id = _source_ref(obj["counterparty_id"], f"{label}.counterparty_id")
    work_ref = _source_ref(obj["work_ref"], f"{label}.work_ref")
    instrument = _instrument(obj["instrument"], f"{label}.instrument")
    amount_dec, amount = _amount(obj["amount"], f"{label}.amount")

    raw_events = obj["events"]
    if type(raw_events) is not list or not raw_events:
        raise ContractError(f"{label}.events must be a non-empty list")

    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    previous_at: datetime | None = None
    state: str | None = None
    asserted_hold_until: datetime | None = None
    asserted_hold_text: str | None = None
    settlement: dict[str, str] | None = None
    entitlement_evidence: dict[str, str] | None = None

    contact_sent = False
    contact_open = False
    contact_delivered = False
    route_dead = False
    collection_released = False
    cooldown_until: datetime | None = None
    cooldown_text: str | None = None

    for eindex, raw_event in enumerate(raw_events):
        event, event_at = _normalize_event(raw_event, f"{label}.events[{eindex}]")
        if event_at > as_of_dt:
            raise ContractError(f"{label}: event timestamp is after ledger as_of")
        if event["event_id"] in seen_event_ids:
            raise ContractError(f"{label}: duplicate event_id {event['event_id']}")
        seen_event_ids.add(event["event_id"])
        if previous_at is not None and event_at <= previous_at:
            raise ContractError(f"{label}: event timestamps must be strictly increasing")
        previous_at = event_at
        kind = event["kind"]

        if kind in FINANCIAL_KINDS:
            state = _apply_financial(state, kind)
            if kind == "PAYMENT_ASSERTED":
                if "hold_until" in event:
                    asserted_hold_until, asserted_hold_text = _instant(
                        event["hold_until"], "normalized hold_until"
                    )
                else:
                    asserted_hold_until = None
                    asserted_hold_text = None
            if kind == "SETTLED_CASH":
                settlement = {
                    "currency": event["settlement_currency"],
                    "amount": event["settlement_amount"],
                    "source_ref": event["source_ref"],
                    "source_digest": event["source_digest"],
                    "at": event["at"],
                }
        elif kind in EVIDENCE_KINDS:
            if state not in {STATE_SUBMITTED, STATE_ACCEPTED}:
                raise ContractError(
                    f"{label}: entitlement evidence not allowed in state {state}"
                )
            if entitlement_evidence is not None:
                raise ContractError(f"{label}: entitlement evidence cannot repeat")
            if event["entitlement_instrument"] != instrument:
                raise ContractError(
                    f"{label}: entitlement instrument does not match claim instrument"
                )
            if Decimal(event["entitlement_amount"]) != amount_dec:
                raise ContractError(
                    f"{label}: entitlement amount does not match claim amount"
                )
            entitlement_evidence = {
                "instrument": event["entitlement_instrument"],
                "amount": event["entitlement_amount"],
                "source_ref": event["source_ref"],
                "source_digest": event["source_digest"],
                "at": event["at"],
            }
        else:
            if state not in {STATE_ACCEPTED, STATE_ASSERTED, STATE_AVAILABLE, STATE_DISPUTED}:
                raise ContractError(f"{label}: route event {kind} not allowed in state {state}")
            if kind == "COLLECTION_CONTACT_SENT":
                if state != STATE_ACCEPTED:
                    raise ContractError(f"{label}: collection contact only allowed while awaiting payment")
                if entitlement_evidence is None:
                    raise ContractError(
                        f"{label}: collection contact requires confirmed compensation entitlement"
                    )
                if route_dead:
                    raise ContractError(f"{label}: cannot contact a dead route")
                if contact_open and not collection_released:
                    raise ContractError(f"{label}: collection DNR is still active")
                contact_sent = True
                contact_open = True
                contact_delivered = False
                collection_released = False
                cooldown_until, cooldown_text = _instant(
                    event["cooldown_until"], "normalized cooldown_until"
                )
            elif kind == "DELIVERY_CONFIRMED":
                if not contact_open or route_dead:
                    raise ContractError(f"{label}: no live contact to confirm")
                contact_delivered = True
            elif kind == "DELIVERY_BOUNCED":
                if not contact_open:
                    raise ContractError(f"{label}: no live contact to bounce")
                route_dead = True
                contact_open = False
                contact_delivered = False
            elif kind == "ROUTE_REPAIRED":
                if not route_dead:
                    raise ContractError(f"{label}: route is not dead")
                route_dead = False
                contact_open = False
                contact_delivered = False
                collection_released = True
            elif kind == "COLLECTION_RELEASED":
                if not contact_sent or route_dead:
                    raise ContractError(f"{label}: no retained contact generation can be released")
                contact_open = False
                contact_delivered = False
                collection_released = True
        events.append(event)

    if state is None:
        raise ContractError(f"{label}: missing financial lifecycle")
    if state == STATE_SETTLED:
        next_action = "DONE"
    elif state == STATE_CLOSED:
        next_action = "DONE"
    elif state == STATE_DISPUTED:
        next_action = "HOLD_CONFLICT"
    elif state == STATE_SUBMITTED:
        next_action = "HOLD_CONFLICT"
    elif state == STATE_ASSERTED:
        if asserted_hold_until is not None and as_of_dt < asserted_hold_until:
            next_action = "WAIT_HOLD"
        else:
            next_action = "VERIFY_AVAILABLE"
    elif state == STATE_AVAILABLE:
        next_action = "VERIFY_SETTLEMENT"
    elif state == STATE_ACCEPTED:
        if entitlement_evidence is None:
            next_action = "VERIFY_ENTITLEMENT"
        elif route_dead:
            next_action = "ROUTE_REPAIR_REQUIRED"
        elif contact_open and not collection_released:
            next_action = "WAIT_REPLY"
        else:
            next_action = "COLLECTION_ELIGIBLE"
    else:
        raise ContractError(f"{label}: unhandled state {state}")

    reference = None
    if "reference_valuation" in obj:
        reference = _normalize_reference(obj["reference_valuation"], f"{label}.reference_valuation")

    result: dict[str, Any] = {
        "claim_id": claim_id,
        "counterparty_id": counterparty_id,
        "work_ref": work_ref,
        "instrument": instrument,
        "amount": amount,
        "state": state,
        "entitlement_confirmed": entitlement_evidence is not None,
        "entitlement_evidence": entitlement_evidence,
        "next_action": next_action,
        "events": events,
        "route": {
            "contact_sent": contact_sent,
            "contact_open_dnr": bool(contact_open and not route_dead),
            "delivery_confirmed": contact_delivered,
            "route_dead": route_dead,
            "collection_released": collection_released,
            "cooldown_until": cooldown_text,
            "silence_authorizes_retry": False,
        },
        "payment_asserted_hold_until": asserted_hold_text,
        "settlement": settlement,
        "reference_valuation": reference,
        "economics_receipt_sha256": sha256_value(
            {
                "claim_id": claim_id,
                "counterparty_id": counterparty_id,
                "work_ref": work_ref,
                "instrument": instrument,
                "amount": amount,
                "reference_valuation": reference,
                "entitlement_evidence": entitlement_evidence,
            }
        ),
    }
    result["claim_receipt_sha256"] = sha256_value(result)
    return result

def _sum_exact(values: list[Decimal]) -> Decimal:
    """Sum validated positive amounts without inheriting the caller's context.

    At the finest input exponent, each coefficient uses at most ``width``
    digits. Adding n nonnegative coefficients needs no more than
    width + digits(n) digits, including every carry. Do not cap this at a
    currency scale or convert through float/int strings: the input contract
    allows large integers and up to eighteen fractional places.
    """
    if not values:
        return Decimal(0)
    parts = [value.as_tuple() for value in values]
    exponent = min(part.exponent for part in parts)
    width = max(len(part.digits) + part.exponent - exponent for part in parts)
    context = Context(
        prec=max(1, width + len(str(len(values)))),
        rounding=ROUND_HALF_EVEN, Emin=MIN_EMIN, Emax=MAX_EMAX,
        capitals=1, clamp=0, flags=[],
        traps=[Inexact, Rounded, InvalidOperation, Overflow],
    )
    with localcontext(context):
        return sum(values, Decimal(0))


def _totals(claims: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    instruments = sorted({claim["instrument"] for claim in claims})
    totals: dict[str, Any] = {}
    for instrument in instruments:
        buckets: dict[str, list[Decimal]] = {
            "accepted_outstanding": [],
            "accepted_unconfirmed": [],
            "asserted_hold": [],
            "available_not_settled": [],
            "disputed": [],
        }
        for claim in claims:
            if claim["instrument"] != instrument:
                continue
            amount = Decimal(claim["amount"])
            if claim["state"] == STATE_ACCEPTED:
                if claim["entitlement_confirmed"]:
                    buckets["accepted_outstanding"].append(amount)
                else:
                    buckets["accepted_unconfirmed"].append(amount)
            elif claim["state"] == STATE_ASSERTED:
                buckets["asserted_hold"].append(amount)
            elif claim["state"] == STATE_AVAILABLE:
                buckets["available_not_settled"].append(amount)
            elif claim["state"] == STATE_DISPUTED:
                buckets["disputed"].append(amount)
        totals[instrument] = {
            key: _decimal_text(_sum_exact(values)) for key, values in buckets.items()
        }

    settled: dict[str, list[Decimal]] = {}
    for claim in claims:
        item = claim["settlement"]
        if item is None:
            continue
        settled.setdefault(item["currency"], []).append(Decimal(item["amount"]))
    return totals, {
        key: _decimal_text(_sum_exact(settled[key])) for key in sorted(settled)
    }

def _markdown(claims: list[dict[str, Any]], as_of: str) -> str:
    action_order = {
        "ROUTE_REPAIR_REQUIRED": 0,
        "VERIFY_SETTLEMENT": 1,
        "VERIFY_AVAILABLE": 2,
        "VERIFY_ENTITLEMENT": 3,
        "COLLECTION_ELIGIBLE": 4,
        "WAIT_HOLD": 5,
        "WAIT_REPLY": 6,
        "HOLD_CONFLICT": 7,
        "DONE": 8,
    }
    rows = sorted(claims, key=lambda c: (action_order[c["next_action"]], c["claim_id"]))
    lines = [
        "# Revenue collection queue",
        "",
        f"As of `{as_of}`. Evidence compiler only; this output sends nothing and moves no money.",
        "",
        "| Next action | Claim | Counterparty | Work | Instrument | Amount | State |",
        "|---|---|---|---|---|---:|---|",
    ]
    for claim in rows:
        vals = [
            claim["next_action"],
            claim["claim_id"],
            claim["counterparty_id"],
            claim["work_ref"],
            claim["instrument"],
            claim["amount"],
            claim["state"],
        ]
        safe = [str(v).replace("|", r"\|").replace("\n", " ") for v in vals]
        lines.append("| " + " | ".join(safe) + " |")
    return "\n".join(lines) + "\n"

def compile_ledger(value: Any) -> dict[str, Any]:
    root = _exact_object(value, _ROOT_REQUIRED, _ROOT_REQUIRED, "ledger")
    if root["schema"] != LEDGER_SCHEMA:
        raise ContractError(f"schema must be exactly {LEDGER_SCHEMA}")
    as_of_dt, as_of = _instant(root["as_of"], "as_of")
    raw_claims = root["claims"]
    if type(raw_claims) is not list or not raw_claims:
        raise ContractError("claims must be a non-empty list")

    claims = [_normalize_claim(claim, index, as_of_dt) for index, claim in enumerate(raw_claims)]
    ids = [claim["claim_id"] for claim in claims]
    if len(ids) != len(set(ids)):
        raise ContractError("duplicate claim_id")
    claims.sort(key=lambda c: c["claim_id"])

    totals_by_instrument, settled_cash_by_currency = _totals(claims)
    normalized_input = {
        "schema": LEDGER_SCHEMA,
        "as_of": as_of,
        "claims": [
            {
                "claim_id": c["claim_id"],
                "counterparty_id": c["counterparty_id"],
                "work_ref": c["work_ref"],
                "instrument": c["instrument"],
                "amount": c["amount"],
                "reference_valuation": c["reference_valuation"],
                "events": c["events"],
            }
            for c in claims
        ],
    }
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "as_of": as_of,
        "input_receipt_sha256": sha256_value(normalized_input),
        "claims": claims,
        "totals_by_instrument": totals_by_instrument,
        "settled_cash_by_currency": settled_cash_by_currency,
        "mixed_currency_sum": None,
        "reference_valuations_recognized_as_cash": False,
        "collection_queue_markdown": _markdown(claims, as_of),
        "authority": dict(AUTHORITY),
    }
    report["receipt_sha256"] = sha256_value(report)
    return report

def compile_json(raw: str | bytes) -> dict[str, Any]:
    return compile_ledger(loads_strict(raw))

def verify_ledger(value: Any, report: Any) -> bool:
    if type(report) is not dict:
        raise ContractError("report must be an object")
    expected = compile_ledger(value)
    return canonical_bytes(expected) == canonical_bytes(report)

def verify_json(raw_ledger: str | bytes, raw_report: str | bytes) -> bool:
    return verify_ledger(loads_strict(raw_ledger), loads_strict(raw_report))
