"""Evidence-bound compiler for bounded paid-discovery offers.

This module is deliberately side-effect free except for the create-exclusive bundle
writer.  It never sends an offer, accepts terms, starts work, or moves money.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

PACKET_VERSION = "paid-discovery-offer/v1"
ROOTS_VERSION = "paid-discovery-roots/v1"
INPUT_VERSION = "paid-discovery-input/v1"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_INBOUND_AGE = timedelta(days=14)
MAX_ROOTS_AGE = timedelta(days=30)
MAX_INPUT_BYTES = 2 * 1024 * 1024
READY = "READY_FOR_OWNER_PAID_DISCOVERY_REVIEW"
HOLD = "HOLD"
HISTORICAL = "HISTORICAL_INTEGRITY_ONLY"

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_EMAIL = re.compile(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}")
_URL = re.compile(r"(?i)(?:https?://|www\.)")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_SECRET = re.compile(
    r"(?i)\b(?:api[_ -]?key|bearer|authorization|password|client[_ -]?secret|"
    r"access[_ -]?token|refresh[_ -]?token|private[_ -]?key)\b"
)
_BIDI = {"RLO", "LRO", "RLE", "LRE", "PDF", "LRI", "RLI", "FSI", "PDI"}


class OfferError(ValueError):
    """Stable validation error for malformed/untrusted input shapes."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expect_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise OfferError(f"{path}: expected object")
    return value


def _expect_list(value: Any, path: str) -> List[Any]:
    if not isinstance(value, list):
        raise OfferError(f"{path}: expected array")
    return value


def _expect_keys(obj: Mapping[str, Any], keys: Iterable[str], path: str) -> None:
    expected = set(keys)
    actual = set(obj)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise OfferError(f"{path}: key mismatch missing={missing} extra={extra}")


def _bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise OfferError(f"{path}: expected bool")
    return value


def _int(value: Any, path: str, *, minimum: int = 0, maximum: int = MAX_SAFE_INTEGER) -> int:
    if type(value) is not int:
        raise OfferError(f"{path}: expected integer")
    if not minimum <= value <= maximum:
        raise OfferError(f"{path}: integer out of range")
    return value


def _id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise OfferError(f"{path}: invalid opaque identifier")
    if "://" in value or "@" in value:
        raise OfferError(f"{path}: contact/route-shaped identifier rejected")
    return value


def _digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise OfferError(f"{path}: expected lowercase sha256")
    return value


def _text(value: Any, path: str, *, allow_empty: bool = False, max_len: int = 320) -> str:
    if not isinstance(value, str):
        raise OfferError(f"{path}: expected string")
    if len(value) > max_len or (not allow_empty and not value.strip()):
        raise OfferError(f"{path}: empty/oversized text")
    if unicodedata.normalize("NFC", value) != value:
        raise OfferError(f"{path}: text must be NFC normalized")
    for ch in value:
        if unicodedata.category(ch) in {"Cc", "Cf"} or unicodedata.bidirectional(ch) in _BIDI:
            raise OfferError(f"{path}: unsafe control/bidi text")
    if _EMAIL.search(value) or _URL.search(value) or _PHONE.search(value) or _SECRET.search(value):
        raise OfferError(f"{path}: direct contact/route/secret-shaped text rejected")
    return value


def _timestamp(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not _TS.fullmatch(value):
        raise OfferError(f"{path}: expected canonical whole-second UTC timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise OfferError(f"{path}: invalid timestamp") from exc


def _fmt(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _bounded_text_list(value: Any, path: str, *, min_items: int = 1, max_items: int = 16) -> List[str]:
    items = _expect_list(value, path)
    if not min_items <= len(items) <= max_items:
        raise OfferError(f"{path}: wrong item count")
    return [_text(v, f"{path}[{i}]") for i, v in enumerate(items)]


def _validate_candidate(candidate: Any) -> Dict[str, Any]:
    top = dict(_expect_mapping(candidate, "input"))
    _expect_keys(
        top,
        {
            "version", "offer_id", "opportunity", "positive_inbound", "custody",
            "capabilities", "commercial_policy", "proposed_offer",
        },
        "input",
    )
    if top["version"] != INPUT_VERSION:
        raise OfferError("input.version: unsupported version")
    _id(top["offer_id"], "input.offer_id")

    opp = _expect_mapping(top["opportunity"], "input.opportunity")
    _expect_keys(opp, {"opportunity_id", "buyer_scope_id", "generation", "complete", "captured_at", "valid_until", "source_digest"}, "input.opportunity")
    _id(opp["opportunity_id"], "input.opportunity.opportunity_id")
    _id(opp["buyer_scope_id"], "input.opportunity.buyer_scope_id")
    _int(opp["generation"], "input.opportunity.generation", minimum=1)
    _bool(opp["complete"], "input.opportunity.complete")
    _timestamp(opp["captured_at"], "input.opportunity.captured_at")
    _timestamp(opp["valid_until"], "input.opportunity.valid_until")
    _digest(opp["source_digest"], "input.opportunity.source_digest")

    inbound = _expect_mapping(top["positive_inbound"], "input.positive_inbound")
    _expect_keys(inbound, {"inbound_id", "opportunity_id", "buyer_scope_id", "signal", "intent_code", "occurred_at", "captured_at", "source_digest"}, "input.positive_inbound")
    _id(inbound["inbound_id"], "input.positive_inbound.inbound_id")
    _id(inbound["opportunity_id"], "input.positive_inbound.opportunity_id")
    _id(inbound["buyer_scope_id"], "input.positive_inbound.buyer_scope_id")
    if inbound["signal"] not in {"VERIFIED_HUMAN_POSITIVE", "UNVERIFIED", "AMBIGUOUS"}:
        raise OfferError("input.positive_inbound.signal: unsupported value")
    if inbound["intent_code"] not in {"REQUESTED_SCOPE", "REQUESTED_PROPOSAL", "REQUESTED_DISCOVERY", "OTHER_POSITIVE"}:
        raise OfferError("input.positive_inbound.intent_code: unsupported value")
    _timestamp(inbound["occurred_at"], "input.positive_inbound.occurred_at")
    _timestamp(inbound["captured_at"], "input.positive_inbound.captured_at")
    _digest(inbound["source_digest"], "input.positive_inbound.source_digest")

    custody = _expect_mapping(top["custody"], "input.custody")
    _expect_keys(custody, {"custody_id", "opportunity_id", "buyer_scope_id", "operation_id", "owner_seat", "generation", "state", "complete", "acquired_at", "expires_at", "source_digest"}, "input.custody")
    for key in ("custody_id", "opportunity_id", "buyer_scope_id", "operation_id", "owner_seat"):
        _id(custody[key], f"input.custody.{key}")
    _int(custody["generation"], "input.custody.generation", minimum=1)
    if custody["state"] not in {"ACTIVE_EXCLUSIVE", "CONFLICT", "RELEASED"}:
        raise OfferError("input.custody.state: unsupported value")
    _bool(custody["complete"], "input.custody.complete")
    _timestamp(custody["acquired_at"], "input.custody.acquired_at")
    _timestamp(custody["expires_at"], "input.custody.expires_at")
    _digest(custody["source_digest"], "input.custody.source_digest")

    caps = _expect_list(top["capabilities"], "input.capabilities")
    if len(caps) > 32:
        raise OfferError("input.capabilities: too many records")
    seen_caps = set()
    for i, cap_any in enumerate(caps):
        cap = _expect_mapping(cap_any, f"input.capabilities[{i}]")
        _expect_keys(cap, {"capability_id", "carrier_ref", "carrier_digest", "state", "verified_at", "evidence_digest"}, f"input.capabilities[{i}]")
        cid = _id(cap["capability_id"], f"input.capabilities[{i}].capability_id")
        if cid in seen_caps:
            raise OfferError("input.capabilities: duplicate capability_id")
        seen_caps.add(cid)
        _id(cap["carrier_ref"], f"input.capabilities[{i}].carrier_ref")
        _digest(cap["carrier_digest"], f"input.capabilities[{i}].carrier_digest")
        if cap["state"] not in {"LANDED_VERIFIED", "UNVERIFIED", "DRAFT"}:
            raise OfferError(f"input.capabilities[{i}].state: unsupported value")
        _timestamp(cap["verified_at"], f"input.capabilities[{i}].verified_at")
        _digest(cap["evidence_digest"], f"input.capabilities[{i}].evidence_digest")

    policy = _expect_mapping(top["commercial_policy"], "input.commercial_policy")
    _expect_keys(policy, {"policy_id", "generation", "currency", "min_price_minor", "min_upfront_bps", "max_duration_days", "max_scope_items", "custom_work_before_payment_allowed", "free_discovery_allowed", "complete", "effective_at", "expires_at", "source_digest"}, "input.commercial_policy")
    _id(policy["policy_id"], "input.commercial_policy.policy_id")
    _int(policy["generation"], "input.commercial_policy.generation", minimum=1)
    if not isinstance(policy["currency"], str) or not re.fullmatch(r"[A-Z]{3}", policy["currency"]):
        raise OfferError("input.commercial_policy.currency: expected ISO-like uppercase code")
    _int(policy["min_price_minor"], "input.commercial_policy.min_price_minor", minimum=1)
    _int(policy["min_upfront_bps"], "input.commercial_policy.min_upfront_bps", minimum=1, maximum=10000)
    _int(policy["max_duration_days"], "input.commercial_policy.max_duration_days", minimum=1, maximum=365)
    _int(policy["max_scope_items"], "input.commercial_policy.max_scope_items", minimum=1, maximum=64)
    _bool(policy["custom_work_before_payment_allowed"], "input.commercial_policy.custom_work_before_payment_allowed")
    _bool(policy["free_discovery_allowed"], "input.commercial_policy.free_discovery_allowed")
    _bool(policy["complete"], "input.commercial_policy.complete")
    _timestamp(policy["effective_at"], "input.commercial_policy.effective_at")
    _timestamp(policy["expires_at"], "input.commercial_policy.expires_at")
    _digest(policy["source_digest"], "input.commercial_policy.source_digest")

    offer = _expect_mapping(top["proposed_offer"], "input.proposed_offer")
    _expect_keys(offer, {"currency", "price_minor", "upfront_minor", "duration_days", "prepayment_required", "scope_items", "buyer_inputs", "exclusions"}, "input.proposed_offer")
    if offer["currency"] != policy["currency"] and (not isinstance(offer["currency"], str) or not re.fullmatch(r"[A-Z]{3}", offer["currency"])):
        raise OfferError("input.proposed_offer.currency: invalid currency")
    _int(offer["price_minor"], "input.proposed_offer.price_minor", minimum=0)
    _int(offer["upfront_minor"], "input.proposed_offer.upfront_minor", minimum=0)
    _int(offer["duration_days"], "input.proposed_offer.duration_days", minimum=1, maximum=365)
    _bool(offer["prepayment_required"], "input.proposed_offer.prepayment_required")
    scope = _expect_list(offer["scope_items"], "input.proposed_offer.scope_items")
    if not 1 <= len(scope) <= 64:
        raise OfferError("input.proposed_offer.scope_items: wrong item count")
    seen_items = set()
    for i, item_any in enumerate(scope):
        item = _expect_mapping(item_any, f"input.proposed_offer.scope_items[{i}]")
        _expect_keys(item, {"item_id", "deliverable", "acceptance_evidence", "capability_ids"}, f"input.proposed_offer.scope_items[{i}]")
        item_id = _id(item["item_id"], f"input.proposed_offer.scope_items[{i}].item_id")
        if item_id in seen_items:
            raise OfferError("input.proposed_offer.scope_items: duplicate item_id")
        seen_items.add(item_id)
        _text(item["deliverable"], f"input.proposed_offer.scope_items[{i}].deliverable")
        _text(item["acceptance_evidence"], f"input.proposed_offer.scope_items[{i}].acceptance_evidence", allow_empty=True)
        ids = _expect_list(item["capability_ids"], f"input.proposed_offer.scope_items[{i}].capability_ids")
        if not 1 <= len(ids) <= 16:
            raise OfferError(f"input.proposed_offer.scope_items[{i}].capability_ids: wrong item count")
        if len(set(ids)) != len(ids):
            raise OfferError(f"input.proposed_offer.scope_items[{i}].capability_ids: duplicate id")
        for j, cid in enumerate(ids):
            _id(cid, f"input.proposed_offer.scope_items[{i}].capability_ids[{j}]")
    _bounded_text_list(offer["buyer_inputs"], "input.proposed_offer.buyer_inputs")
    _bounded_text_list(offer["exclusions"], "input.proposed_offer.exclusions")
    return top


def _validate_roots(roots: Any) -> Dict[str, Any]:
    obj = dict(_expect_mapping(roots, "roots"))
    _expect_keys(obj, {"version", "authority_generation", "captured_at", "opportunity_root", "positive_inbound_root", "custody_root", "capabilities_root", "commercial_policy_root"}, "roots")
    if obj["version"] != ROOTS_VERSION:
        raise OfferError("roots.version: unsupported version")
    _id(obj["authority_generation"], "roots.authority_generation")
    _timestamp(obj["captured_at"], "roots.captured_at")
    for key in ("opportunity_root", "positive_inbound_root", "custody_root", "capabilities_root", "commercial_policy_root"):
        _digest(obj[key], f"roots.{key}")
    return obj


def _authority_reasons(candidate: Dict[str, Any], roots: Dict[str, Any], at: datetime) -> Tuple[List[str], datetime]:
    reasons: List[str] = []
    opp = candidate["opportunity"]
    inbound = candidate["positive_inbound"]
    custody = candidate["custody"]
    caps = candidate["capabilities"]
    policy = candidate["commercial_policy"]
    offer = candidate["proposed_offer"]

    block_roots = {
        "opportunity_root": _sha256_value(opp),
        "positive_inbound_root": _sha256_value(inbound),
        "custody_root": _sha256_value(custody),
        "capabilities_root": _sha256_value(caps),
        "commercial_policy_root": _sha256_value(policy),
    }
    for key, actual in block_roots.items():
        if roots[key] != actual:
            reasons.append("AUTHORITY_ROOT_MISMATCH")
            break

    roots_at = _timestamp(roots["captured_at"], "roots.captured_at")
    if roots_at > at:
        reasons.append("AUTHORITY_ROOTS_FROM_FUTURE")
    elif at - roots_at > MAX_ROOTS_AGE:
        reasons.append("AUTHORITY_ROOTS_STALE")

    opp_captured = _timestamp(opp["captured_at"], "input.opportunity.captured_at")
    opp_until = _timestamp(opp["valid_until"], "input.opportunity.valid_until")
    if not opp["complete"]:
        reasons.append("OPPORTUNITY_INCOMPLETE")
    if opp_captured > at:
        reasons.append("OPPORTUNITY_FROM_FUTURE")
    if at >= opp_until:
        reasons.append("OPPORTUNITY_EXPIRED")

    inbound_occurred = _timestamp(inbound["occurred_at"], "input.positive_inbound.occurred_at")
    inbound_captured = _timestamp(inbound["captured_at"], "input.positive_inbound.captured_at")
    inbound_until = inbound_occurred + MAX_INBOUND_AGE
    if inbound["signal"] != "VERIFIED_HUMAN_POSITIVE":
        reasons.append("POSITIVE_INBOUND_UNVERIFIED")
    if inbound_captured < inbound_occurred or inbound_captured > at:
        reasons.append("INBOUND_CHRONOLOGY_INVALID")
    if at >= inbound_until:
        reasons.append("POSITIVE_INBOUND_STALE")

    cust_acquired = _timestamp(custody["acquired_at"], "input.custody.acquired_at")
    cust_until = _timestamp(custody["expires_at"], "input.custody.expires_at")
    if not custody["complete"]:
        reasons.append("CUSTODY_CENSUS_INCOMPLETE")
    if custody["state"] != "ACTIVE_EXCLUSIVE":
        reasons.append("CUSTODY_NOT_EXCLUSIVE")
    if cust_acquired > at:
        reasons.append("CUSTODY_FROM_FUTURE")
    if at >= cust_until:
        reasons.append("CUSTODY_EXPIRED")

    opp_id = opp["opportunity_id"]
    buyer = opp["buyer_scope_id"]
    if inbound["opportunity_id"] != opp_id or custody["opportunity_id"] != opp_id:
        reasons.append("OPPORTUNITY_BINDING_MISMATCH")
    if inbound["buyer_scope_id"] != buyer or custody["buyer_scope_id"] != buyer:
        reasons.append("BUYER_SCOPE_BINDING_MISMATCH")

    policy_eff = _timestamp(policy["effective_at"], "input.commercial_policy.effective_at")
    policy_until = _timestamp(policy["expires_at"], "input.commercial_policy.expires_at")
    if not policy["complete"]:
        reasons.append("COMMERCIAL_POLICY_INCOMPLETE")
    if at < policy_eff:
        reasons.append("COMMERCIAL_POLICY_NOT_YET_EFFECTIVE")
    if at >= policy_until:
        reasons.append("COMMERCIAL_POLICY_EXPIRED")
    if policy["custom_work_before_payment_allowed"] or policy["free_discovery_allowed"]:
        reasons.append("FREE_CUSTOM_WORK_POLICY_FORBIDDEN")

    if offer["currency"] != policy["currency"]:
        reasons.append("CURRENCY_MISMATCH")
    if offer["price_minor"] < policy["min_price_minor"]:
        reasons.append("PRICE_BELOW_POLICY_FLOOR")
    required_upfront = (offer["price_minor"] * policy["min_upfront_bps"] + 9999) // 10000
    if offer["upfront_minor"] < required_upfront:
        reasons.append("UPFRONT_BELOW_POLICY_FLOOR")
    if not offer["prepayment_required"]:
        reasons.append("PREPAYMENT_NOT_REQUIRED")
    if offer["duration_days"] > policy["max_duration_days"]:
        reasons.append("DURATION_EXCEEDS_POLICY")
    if len(offer["scope_items"]) > policy["max_scope_items"]:
        reasons.append("SCOPE_EXCEEDS_POLICY")

    cap_by_id = {c["capability_id"]: c for c in caps}
    referenced = set()
    for item in offer["scope_items"]:
        if not item["acceptance_evidence"].strip():
            reasons.append("MISSING_ACCEPTANCE_EVIDENCE")
        for cid in item["capability_ids"]:
            referenced.add(cid)
            cap = cap_by_id.get(cid)
            if cap is None or cap["state"] != "LANDED_VERIFIED":
                reasons.append("CAPABILITY_UNVERIFIED")
            elif _timestamp(cap["verified_at"], "capability.verified_at") > at:
                reasons.append("CAPABILITY_VERIFICATION_FROM_FUTURE")
    if not caps or not referenced:
        reasons.append("CAPABILITY_EVIDENCE_MISSING")

    valid_until = min(opp_until, inbound_until, cust_until, policy_until, roots_at + MAX_ROOTS_AGE)
    return sorted(set(reasons)), valid_until


def _base_packet(candidate: Dict[str, Any], roots: Dict[str, Any], at: datetime, mode: str) -> Dict[str, Any]:
    reasons, valid_until_dt = _authority_reasons(candidate, roots, at)
    offer = candidate["proposed_offer"]
    opp = candidate["opportunity"]
    custody = candidate["custody"]
    if mode == "CURRENT":
        decision = READY if not reasons else HOLD
        historical_assessment = None
    elif mode == HISTORICAL:
        decision = HISTORICAL
        historical_assessment = READY if not reasons else HOLD
    else:
        raise OfferError("internal: unsupported mode")
    packet: Dict[str, Any] = {
        "packet_version": PACKET_VERSION,
        "mode": mode,
        "decision": decision,
        "reasons": reasons,
        "evaluated_at": _fmt(at),
        "valid_until": _fmt(valid_until_dt),
        "authority_generation": roots["authority_generation"],
        "bindings": {
            "offer_id": candidate["offer_id"],
            "opportunity_id": opp["opportunity_id"],
            "buyer_scope_id": opp["buyer_scope_id"],
            "operation_id": custody["operation_id"],
            "owner_seat": custody["owner_seat"],
            "input_sha256": _sha256_value(candidate),
            "roots_sha256": _sha256_value(roots),
        },
        "commercial": {
            "currency": offer["currency"],
            "price_minor": offer["price_minor"],
            "upfront_minor": offer["upfront_minor"],
            "duration_days": offer["duration_days"],
            "scope_item_count": len(offer["scope_items"]),
        },
        "scope_items": offer["scope_items"],
        "buyer_inputs": offer["buyer_inputs"],
        "exclusions": offer["exclusions"],
        "authority": {
            "external_send_authorized": False,
            "acceptance_authorized": False,
            "contract_authorized": False,
            "payment_authorized": False,
            "work_start_authorized": False,
            "cash_or_revenue_asserted": False,
        },
    }
    if historical_assessment is not None:
        packet["historical_assessment"] = historical_assessment
    packet["receipt_sha256"] = _sha256_value(packet)
    return packet


def compile_current(candidate: Any, roots: Any) -> Dict[str, Any]:
    c = _validate_candidate(candidate)
    r = _validate_roots(roots)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return _base_packet(c, r, now, "CURRENT")


def audit_at(candidate: Any, roots: Any, at: str) -> Dict[str, Any]:
    c = _validate_candidate(candidate)
    r = _validate_roots(roots)
    when = _timestamp(at, "at")
    return _base_packet(c, r, when, HISTORICAL)


def _verify_receipt(packet: Mapping[str, Any]) -> None:
    receipt = packet.get("receipt_sha256")
    _digest(receipt, "packet.receipt_sha256")
    body = dict(packet)
    body.pop("receipt_sha256", None)
    if receipt != _sha256_value(body):
        raise OfferError("packet: receipt mismatch")


def verify_historical(candidate: Any, roots: Any, packet: Any) -> bool:
    p = dict(_expect_mapping(packet, "packet"))
    _verify_receipt(p)
    if p.get("mode") != HISTORICAL or p.get("decision") != HISTORICAL:
        raise OfferError("packet: not historical integrity mode")
    rebuilt = audit_at(candidate, roots, p.get("evaluated_at"))
    return canonical_json(rebuilt) == canonical_json(p)


def verify_current(candidate: Any, roots: Any, packet: Any) -> bool:
    c = _validate_candidate(candidate)
    r = _validate_roots(roots)
    p = dict(_expect_mapping(packet, "packet"))
    _verify_receipt(p)
    if p.get("mode") != "CURRENT" or p.get("decision") not in {READY, HOLD}:
        raise OfferError("packet: not a current packet")
    original_at = _timestamp(p.get("evaluated_at"), "packet.evaluated_at")
    rebuilt = _base_packet(c, r, original_at, "CURRENT")
    if canonical_json(rebuilt) != canonical_json(p):
        return False
    if p["decision"] == READY:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        if now > original_at + timedelta(minutes=15):
            return False
        fresh = _base_packet(c, r, now, "CURRENT")
        return fresh["decision"] == READY and now < _timestamp(p["valid_until"], "packet.valid_until")
    return True


def markdown(packet: Mapping[str, Any]) -> str:
    _verify_receipt(packet)
    lines = [
        "# Paid Discovery Offer — Owner Review Packet",
        "",
        f"- Decision: `{packet['decision']}`",
        f"- Mode: `{packet['mode']}`",
        f"- Offer ID: `{packet['bindings']['offer_id']}`",
        f"- Opportunity: `{packet['bindings']['opportunity_id']}`",
        f"- Buyer scope: `{packet['bindings']['buyer_scope_id']}`",
        f"- Owner seat: `{packet['bindings']['owner_seat']}`",
        f"- Evaluated at: `{packet['evaluated_at']}`",
        f"- Valid until: `{packet['valid_until']}`",
        "",
        "## Commercial envelope",
        "",
        f"- Currency: `{packet['commercial']['currency']}`",
        f"- Price minor units: `{packet['commercial']['price_minor']}`",
        f"- Upfront minor units: `{packet['commercial']['upfront_minor']}`",
        f"- Duration days: `{packet['commercial']['duration_days']}`",
        "",
        "## Scope and acceptance evidence",
        "",
    ]
    for item in packet["scope_items"]:
        acceptance = item["acceptance_evidence"] or "MISSING"
        caps = ", ".join(f"`{c}`" for c in item["capability_ids"])
        lines.extend([
            f"- **{item['item_id']}** — {item['deliverable']}",
            f"  - Acceptance evidence: {acceptance}",
            f"  - Capability bindings: {caps}",
        ])
    lines.extend(["", "## Buyer inputs", ""])
    lines.extend(f"- {x}" for x in packet["buyer_inputs"])
    lines.extend(["", "## Exclusions", ""])
    lines.extend(f"- {x}" for x in packet["exclusions"])
    lines.extend(["", "## Holds", ""])
    if packet["reasons"]:
        lines.extend(f"- `{x}`" for x in packet["reasons"])
    else:
        lines.append("- None at evaluation time.")
    lines.extend([
        "",
        "## Authority ceiling",
        "",
        "This packet is internal owner-review evidence only. It does **not** authorize external send, acceptance, contract execution, payment, work start, or any cash/revenue claim.",
        "",
        f"Receipt SHA-256: `{packet['receipt_sha256']}`",
        "",
    ])
    return "\n".join(lines)


def read_strict_json_file(path: str, *, max_bytes: int = MAX_INPUT_BYTES) -> Any:
    p = Path(path)
    try:
        before = os.lstat(p)
    except OSError as exc:
        raise OfferError(f"input file unavailable: {exc}") from exc
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise OfferError("input file must be a single-link regular file")
    if not 0 < before.st_size <= max_bytes:
        raise OfferError("input file empty/oversized")
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise OfferError(f"input file open failed: {exc}") from exc
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or fst.st_nlink != 1 or (fst.st_dev, fst.st_ino) != (before.st_dev, before.st_ino):
            raise OfferError("input file generation changed before read")
        chunks = []
        total = 0
        while True:
            data = os.read(fd, min(65536, max_bytes + 1 - total))
            if not data:
                break
            chunks.append(data)
            total += len(data)
            if total > max_bytes:
                raise OfferError("input file exceeds size bound")
        after_fd = os.fstat(fd)
    finally:
        os.close(fd)
    try:
        after_path = os.lstat(p)
    except OSError as exc:
        raise OfferError(f"input path disappeared after read: {exc}") from exc
    attrs_before = (fst.st_dev, fst.st_ino, fst.st_size, fst.st_mtime_ns, fst.st_ctime_ns)
    attrs_after = (after_fd.st_dev, after_fd.st_ino, after_fd.st_size, after_fd.st_mtime_ns, after_fd.st_ctime_ns)
    if attrs_before != attrs_after or (after_path.st_dev, after_path.st_ino) != (fst.st_dev, fst.st_ino):
        raise OfferError("input file generation changed during read")
    raw = b"".join(chunks)
    if len(raw) != fst.st_size:
        raise OfferError("input byte count changed")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise OfferError("input file is not valid UTF-8") from exc
    return loads_strict(text)


def loads_strict(text: str) -> Any:
    def pairs_hook(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise OfferError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def no_float(_: str) -> None:
        raise OfferError("JSON floats are forbidden")

    def no_constant(_: str) -> None:
        raise OfferError("non-finite JSON is forbidden")

    try:
        return json.loads(text, object_pairs_hook=pairs_hook, parse_float=no_float, parse_constant=no_constant)
    except OfferError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise OfferError("invalid JSON") from exc


def write_bundle(path: str, packet: Mapping[str, Any]) -> Dict[str, str]:
    _verify_receipt(packet)
    target = Path(path)
    parent = target.parent
    try:
        pst = os.lstat(parent)
    except OSError as exc:
        raise OfferError(f"output parent unavailable: {exc}") from exc
    if not stat.S_ISDIR(pst.st_mode) or stat.S_ISLNK(pst.st_mode):
        raise OfferError("output parent must be an ordinary directory")
    try:
        os.mkdir(target, 0o700)
    except FileExistsError as exc:
        raise OfferError("output bundle already exists") from exc
    except OSError as exc:
        raise OfferError(f"cannot create output bundle: {exc}") from exc
    packet_text = canonical_json(packet) + "\n"
    markdown_text = markdown(packet)
    manifest = {
        "packet.json": _sha256_text(packet_text),
        "offer.md": _sha256_text(markdown_text),
        "receipt.sha256": _sha256_text(packet["receipt_sha256"] + "\n"),
    }
    try:
        for name, content in (
            ("packet.json", packet_text),
            ("offer.md", markdown_text),
            ("receipt.sha256", packet["receipt_sha256"] + "\n"),
            ("manifest.json", canonical_json(manifest) + "\n"),
        ):
            with open(target / name, "x", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
        dfd = os.open(target, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except Exception as exc:
        raise OfferError(f"bundle publication failed; preserved for inspection: {exc}") from exc
    return {"bundle": str(target), "packet_receipt": packet["receipt_sha256"], "manifest_sha256": _sha256_value(manifest)}


__all__ = [
    "OfferError", "READY", "HOLD", "HISTORICAL", "compile_current", "audit_at",
    "verify_current", "verify_historical", "markdown", "loads_strict",
    "read_strict_json_file", "write_bundle", "canonical_json",
]
