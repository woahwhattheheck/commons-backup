"""Deterministic, side-effect-free commercial lifecycle evidence ledger."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

SCHEMA_VERSION = "commons-commercial-lifecycle/v1"
RECEIPT_VERSION = "commons-commercial-lifecycle-receipt/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TIMESTAMP_RE = re.compile(
    r"^(?:[0-9]{4})-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)

EVENT_KEYS = {
    "event_id", "kind", "occurred_at", "authority", "evidence_sha256",
    "subject_sha256", "amount_minor", "currency", "reversal_of",
}
ROOT_KEYS = {
    "version", "deal_id", "opportunity_sha256", "offer_sha256", "scope_sha256",
    "buyer_ref_sha256", "currency", "contract_amount_minor", "offer_expires_at",
    "events",
}
KIND_AUTHORITY = {
    "OPPORTUNITY_QUALIFIED": "owner",
    "OFFER_OWNER_APPROVED": "owner",
    "OFFER_SENT": "transport",
    "BUYER_ACCEPTED": "buyer",
    "FUNDING_VERIFIED": "funding",
    "EXECUTION_STARTED": "owner",
    "FULFILLMENT_ACCEPTED": "buyer",
    "PAYMENT_SETTLED": "payment",
    "REVENUE_RECOGNIZED": "finance",
    "CANCELLED": "owner",
    "REFUND_SETTLED": "payment",
    "REVENUE_REVERSED": "finance",
}
AMOUNT_KINDS = {
    "FUNDING_VERIFIED", "PAYMENT_SETTLED", "REVENUE_RECOGNIZED",
    "REFUND_SETTLED", "REVENUE_REVERSED",
}
FORWARD_ORDER = [
    "OPPORTUNITY_QUALIFIED",
    "OFFER_OWNER_APPROVED",
    "OFFER_SENT",
    "BUYER_ACCEPTED",
    "FUNDING_VERIFIED",
    "EXECUTION_STARTED",
    "FULFILLMENT_ACCEPTED",
]
STAGE_STATE = {
    0: "EMPTY_EVIDENCE_ONLY",
    1: "OPPORTUNITY_QUALIFIED_EVIDENCE_ONLY",
    2: "OWNER_APPROVED_EVIDENCE_ONLY",
    3: "OFFER_SENT_EVIDENCE_ONLY",
    4: "BUYER_ACCEPTED_EVIDENCE_ONLY",
    5: "FUNDED_EVIDENCE_ONLY",
    6: "EXECUTION_STARTED_EVIDENCE_ONLY",
    7: "FULFILLMENT_ACCEPTED_EVIDENCE_ONLY",
}

class LedgerError(ValueError):
    pass

def _strict_object(obj: Any, keys: set[str], where: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise LedgerError(f"{where} must be an object")
    got = set(obj)
    if got != keys:
        missing = sorted(keys - got)
        extra = sorted(got - keys)
        raise LedgerError(f"{where} schema mismatch missing={missing} extra={extra}")
    return obj

def _strict_int(value: Any, where: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(f"{where} must be an integer")
    if value < minimum:
        raise LedgerError(f"{where} must be >= {minimum}")
    return value

def _strict_id(value: Any, where: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise LedgerError(f"{where} must be a bounded ASCII identifier")
    return value

def _digest(value: Any, where: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise LedgerError(f"{where} must be a lowercase SHA-256 hex digest")
    return value

def _currency(value: Any, where: str) -> str:
    if not isinstance(value, str) or not CURRENCY_RE.fullmatch(value):
        raise LedgerError(f"{where} must be exactly 3 uppercase ASCII letters")
    return value

def _timestamp(value: Any, where: str) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise LedgerError(f"{where} must be canonical whole-second UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise LedgerError(f"{where} is not a valid UTC timestamp") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise LedgerError(f"{where} must be canonical whole-second UTC YYYY-MM-DDTHH:MM:SSZ")
    return dt

def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

def _sha(obj: Any) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()

def load_json_strict(text: str) -> Any:
    def hook(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise LedgerError(f"duplicate JSON key: {k}")
            out[k] = v
        return out
    def bad_constant(value: str) -> Any:
        raise LedgerError(f"non-finite JSON number: {value}")
    try:
        return json.loads(text, object_pairs_hook=hook, parse_constant=bad_constant)
    except json.JSONDecodeError as exc:
        raise LedgerError(f"invalid JSON: {exc.msg}") from exc

def subject_commitment(payload: Dict[str, Any]) -> str:
    """Commit immutable deal terms. `events` are deliberately excluded."""
    _strict_object(payload, ROOT_KEYS, "ledger")
    static = {k: payload[k] for k in sorted(ROOT_KEYS - {"events"})}
    _validate_static(static)
    return _sha(static)

def _validate_static(static: Dict[str, Any]) -> None:
    if static["version"] != SCHEMA_VERSION:
        raise LedgerError("unsupported version")
    _strict_id(static["deal_id"], "deal_id")
    for k in ("opportunity_sha256", "offer_sha256", "scope_sha256", "buyer_ref_sha256"):
        _digest(static[k], k)
    _currency(static["currency"], "currency")
    _strict_int(static["contract_amount_minor"], "contract_amount_minor", minimum=1)
    _timestamp(static["offer_expires_at"], "offer_expires_at")

def _normalize_event(raw: Any, idx: int, subject: str, deal_currency: str) -> Dict[str, Any]:
    e = _strict_object(raw, EVENT_KEYS, f"events[{idx}]")
    _strict_id(e["event_id"], f"events[{idx}].event_id")
    kind = e["kind"]
    if kind not in KIND_AUTHORITY:
        raise LedgerError(f"events[{idx}].kind unsupported")
    if e["authority"] != KIND_AUTHORITY[kind]:
        raise LedgerError(f"{kind} requires authority={KIND_AUTHORITY[kind]}")
    _timestamp(e["occurred_at"], f"events[{idx}].occurred_at")
    _digest(e["evidence_sha256"], f"events[{idx}].evidence_sha256")
    if e["subject_sha256"] != subject:
        raise LedgerError(f"events[{idx}] subject commitment mismatch")
    amount = e["amount_minor"]
    curr = e["currency"]
    reversal = e["reversal_of"]
    if kind in AMOUNT_KINDS:
        _strict_int(amount, f"events[{idx}].amount_minor", minimum=1)
        if curr != deal_currency:
            raise LedgerError(f"{kind} currency must equal deal currency")
    else:
        if amount is not None or curr is not None:
            raise LedgerError(f"{kind} must not carry money")
    if kind in {"REFUND_SETTLED", "REVENUE_REVERSED"}:
        _strict_id(reversal, f"events[{idx}].reversal_of")
    elif reversal is not None:
        raise LedgerError(f"{kind} must not carry reversal_of")
    return dict(e)

def _stage_state(stage: int, settled: int, recognized: int, refunded: int, reversed_amt: int, cancelled: bool, reversal_pending: int) -> str:
    if reversal_pending:
        return "RECOGNITION_REVERSAL_REQUIRED_EVIDENCE_ONLY"
    if cancelled:
        if refunded or reversed_amt:
            return "CANCELLED_WITH_REVERSAL_EVIDENCE_ONLY"
        return "CANCELLED_EVIDENCE_ONLY"
    if refunded or reversed_amt:
        if settled and refunded == settled and recognized == reversed_amt:
            return "FULLY_REVERSED_EVIDENCE_ONLY"
        return "PARTIALLY_REVERSED_EVIDENCE_ONLY"
    if recognized:
        return "REVENUE_RECOGNITION_EVIDENCED"
    if settled:
        if stage < 7:
            return "PREPAID_CASH_EVIDENCE_ONLY"
        return "PAYMENT_SETTLED_EVIDENCE_ONLY"
    return STAGE_STATE[stage]

def compile_ledger(payload: Dict[str, Any], *, trusted_as_of: str) -> Dict[str, Any]:
    """Validate and deterministically reconcile one commercial deal's evidence."""
    _strict_object(payload, ROOT_KEYS, "ledger")
    static = {k: payload[k] for k in sorted(ROOT_KEYS - {"events"})}
    _validate_static(static)
    if not isinstance(payload["events"], list):
        raise LedgerError("events must be an array")
    now = _timestamp(trusted_as_of, "trusted_as_of")
    expires = _timestamp(payload["offer_expires_at"], "offer_expires_at")
    subject = _sha(static)

    unique: List[Dict[str, Any]] = []
    by_id: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    by_evidence: Dict[str, str] = {}
    last_time: datetime | None = None
    for idx, raw in enumerate(payload["events"]):
        e = _normalize_event(raw, idx, subject, payload["currency"])
        event_time = _timestamp(e["occurred_at"], f"events[{idx}].occurred_at")
        if event_time > now:
            raise LedgerError(f"events[{idx}] occurs after trusted_as_of")
        ed = _sha(e)
        old = by_id.get(e["event_id"])
        if old:
            if old[0] != ed:
                raise LedgerError(f"conflicting duplicate event_id: {e['event_id']}")
            continue
        old_evidence_event = by_evidence.get(e["evidence_sha256"])
        if old_evidence_event is not None:
            raise LedgerError(
                "evidence_sha256 reused by distinct event_id: "
                f"{old_evidence_event} and {e['event_id']}"
            )
        if last_time is not None and event_time < last_time:
            raise LedgerError("unique events must be nondecreasing by occurred_at")
        last_time = event_time
        by_id[e["event_id"]] = (ed, e)
        by_evidence[e["evidence_sha256"]] = e["event_id"]
        unique.append(e)

    stage = 0
    cancelled = False
    funded = 0
    settled = 0
    refunded = 0
    recognized = 0
    reversed_amt = 0
    payment_remaining: Dict[str, int] = {}
    refund_remaining: Dict[str, int] = {}
    event_chain = "0" * 64

    for e in unique:
        kind = e["kind"]
        if cancelled and kind not in {"REFUND_SETTLED", "REVENUE_REVERSED"}:
            raise LedgerError("cancelled lifecycle permits only financial reversals")

        if kind in FORWARD_ORDER:
            target = FORWARD_ORDER.index(kind) + 1
            if target != stage + 1:
                raise LedgerError(f"{kind} skips, repeats, or reorders lifecycle stage")
            if kind in {"OFFER_OWNER_APPROVED", "OFFER_SENT", "BUYER_ACCEPTED"}:
                if _timestamp(e["occurred_at"], "occurred_at") > expires:
                    raise LedgerError(f"{kind} occurred after offer expiry")
            if kind == "FUNDING_VERIFIED":
                if e["amount_minor"] != payload["contract_amount_minor"]:
                    raise LedgerError("funding evidence must equal contract amount")
                funded = e["amount_minor"]
            stage = target

        elif kind == "PAYMENT_SETTLED":
            if stage < 5:
                raise LedgerError("payment settlement requires buyer acceptance and funding evidence")
            amount = e["amount_minor"]
            if settled + amount > payload["contract_amount_minor"]:
                raise LedgerError("settled payments exceed contract amount")
            settled += amount
            payment_remaining[e["event_id"]] = amount

        elif kind == "REVENUE_RECOGNIZED":
            if stage < 7 or settled <= 0:
                raise LedgerError("revenue recognition requires fulfilled and settled evidence")
            amount = e["amount_minor"]
            if recognized + amount > settled - refunded:
                raise LedgerError("recognized amount exceeds net settled cash evidence")
            recognized += amount

        elif kind == "CANCELLED":
            cancelled = True

        elif kind == "REFUND_SETTLED":
            ref = e["reversal_of"]
            if ref not in payment_remaining:
                raise LedgerError("refund must reference a PAYMENT_SETTLED event")
            amount = e["amount_minor"]
            if amount > payment_remaining[ref]:
                raise LedgerError("refund exceeds referenced payment residual")
            payment_remaining[ref] -= amount
            refunded += amount
            refund_remaining[e["event_id"]] = amount

        elif kind == "REVENUE_REVERSED":
            ref = e["reversal_of"]
            if ref not in refund_remaining:
                raise LedgerError("revenue reversal must reference a REFUND_SETTLED event")
            amount = e["amount_minor"]
            if amount > refund_remaining[ref]:
                raise LedgerError("revenue reversal exceeds referenced refund residual")
            if reversed_amt + amount > recognized:
                raise LedgerError("revenue reversal exceeds recognized amount")
            refund_remaining[ref] -= amount
            reversed_amt += amount

        event_chain = hashlib.sha256((event_chain + _sha(e)).encode("ascii")).hexdigest()

    net_cash = settled - refunded
    net_recognized = recognized - reversed_amt
    reversal_pending = max(0, net_recognized - net_cash)

    normalized_input = {**static, "events": unique}
    receipt: Dict[str, Any] = {
        "version": RECEIPT_VERSION,
        "deal_id": payload["deal_id"],
        "subject_sha256": subject,
        "normalized_input_sha256": _sha(normalized_input),
        "trusted_as_of": trusted_as_of,
        "state": _stage_state(stage, settled, recognized, refunded, reversed_amt, cancelled, reversal_pending),
        "currency": payload["currency"],
        "contract_amount_minor": payload["contract_amount_minor"],
        "funding_evidenced_minor": funded,
        "settled_amount_minor": settled,
        "refunded_amount_minor": refunded,
        "reported_recognized_amount_minor": recognized,
        "reversed_recognition_amount_minor": reversed_amt,
        "net_cash_evidenced_minor": net_cash,
        "net_recognized_evidenced_minor": net_recognized,
        "recognition_reversal_pending_minor": reversal_pending,
        "unique_event_count": len(unique),
        "input_event_count": len(payload["events"]),
        "event_chain_head_sha256": event_chain,
        "authority": {
            "outreach_or_send_authorized": False,
            "contract_execution_authorized": False,
            "fulfillment_authorized": False,
            "payment_or_refund_authorized": False,
            "revenue_recognition_authorized": False,
        },
    }
    receipt["receipt_sha256"] = _sha(receipt)
    return receipt

def verify_receipt(payload: Dict[str, Any], receipt: Dict[str, Any], *, trusted_as_of: str) -> bool:
    if not isinstance(receipt, dict):
        return False
    claimed = receipt.get("receipt_sha256")
    if not isinstance(claimed, str) or not SHA256_RE.fullmatch(claimed):
        return False
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if _sha(body) != claimed:
        return False
    try:
        rebuilt = compile_ledger(payload, trusted_as_of=trusted_as_of)
    except LedgerError:
        return False
    return rebuilt == receipt
