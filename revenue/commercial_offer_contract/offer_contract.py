from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = 1
MAX_TEXT = 4096
MAX_SHORT = 200
MAX_ITEMS = 100
CHANNELS = {"email", "portal", "marketplace", "other"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class ContractError(ValueError):
    """Raised when offer/authority evidence fails closed."""


def _fail(message: str) -> None:
    raise ContractError(message)


def _exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    if type(value) is not dict:
        _fail(f"{where} must be a plain object")
    got = set(value)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        _fail(f"{where} keys mismatch: missing={missing} extra={extra}")


def _text(value: Any, where: str, *, max_len: int = MAX_TEXT, allow_empty: bool = False) -> str:
    if type(value) is not str:
        _fail(f"{where} must be a string")
    if not allow_empty and not value:
        _fail(f"{where} must not be empty")
    if len(value) > max_len:
        _fail(f"{where} is too long")
    if "\x00" in value:
        _fail(f"{where} contains NUL")
    return value


def _identifier(value: Any, where: str) -> str:
    text = _text(value, where, max_len=128)
    if not ID_RE.fullmatch(text):
        _fail(f"{where} is not a canonical identifier")
    return text


def _sha256(value: Any, where: str) -> str:
    text = _text(value, where, max_len=64)
    if not HEX64.fullmatch(text):
        _fail(f"{where} must be 64 lowercase hex")
    return text


def _integer(value: Any, where: str, *, minimum: int = 0, maximum: int = 10**15) -> int:
    if type(value) is not int:
        _fail(f"{where} must be an integer")
    if value < minimum or value > maximum:
        _fail(f"{where} out of range")
    return value


def _timestamp(value: Any, where: str) -> tuple[str, datetime]:
    text = _text(value, where, max_len=40)
    if not text.endswith("Z"):
        _fail(f"{where} must use canonical UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{where} invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail(f"{where} must be UTC")
    canonical = parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if text != canonical:
        _fail(f"{where} must be canonical whole-second UTC")
    return text, parsed


def _canonical(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("value is not canonical JSON") from exc
    return rendered.encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_json_strict(raw: str) -> dict[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                _fail(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    try:
        parsed = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=lambda x: _fail(f"nonfinite JSON number: {x}"))
    except json.JSONDecodeError as exc:
        raise ContractError("invalid JSON") from exc
    if type(parsed) is not dict:
        _fail("root must be an object")
    return parsed


def validate_offer_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "offer_id",
        "opportunity_id",
        "buyer_ref",
        "created_at",
        "valid_until",
        "currency",
        "total_amount_minor",
        "deliverables",
        "milestones",
        "assumptions",
        "exclusions",
    }
    _exact_keys(spec, expected, "offer")
    if type(spec["schema_version"]) is not int or spec["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported schema_version")

    offer_id = _identifier(spec["offer_id"], "offer.offer_id")
    opportunity_id = _identifier(spec["opportunity_id"], "offer.opportunity_id")
    buyer_ref = _identifier(spec["buyer_ref"], "offer.buyer_ref")
    created_at, created_dt = _timestamp(spec["created_at"], "offer.created_at")
    valid_until, valid_dt = _timestamp(spec["valid_until"], "offer.valid_until")
    if valid_dt <= created_dt:
        _fail("offer.valid_until must be after created_at")

    currency = _text(spec["currency"], "offer.currency", max_len=3)
    if not CURRENCY_RE.fullmatch(currency):
        _fail("offer.currency must be 3 uppercase ASCII letters")
    total = _integer(spec["total_amount_minor"], "offer.total_amount_minor")

    deliverables_raw = spec["deliverables"]
    if type(deliverables_raw) is not list or not (1 <= len(deliverables_raw) <= MAX_ITEMS):
        _fail("offer.deliverables must contain 1..100 items")
    deliverables: list[dict[str, Any]] = []
    deliverable_ids: set[str] = set()
    for i, item in enumerate(deliverables_raw):
        where = f"offer.deliverables[{i}]"
        _exact_keys(item, {"id", "title", "acceptance_criteria", "evidence_sha256"}, where)
        did = _identifier(item["id"], f"{where}.id")
        if did in deliverable_ids:
            _fail(f"duplicate deliverable id: {did}")
        deliverable_ids.add(did)
        deliverables.append(
            {
                "id": did,
                "title": _text(item["title"], f"{where}.title", max_len=MAX_SHORT),
                "acceptance_criteria": _text(item["acceptance_criteria"], f"{where}.acceptance_criteria"),
                "evidence_sha256": _sha256(item["evidence_sha256"], f"{where}.evidence_sha256"),
            }
        )

    milestones_raw = spec["milestones"]
    if type(milestones_raw) is not list or not (1 <= len(milestones_raw) <= MAX_ITEMS):
        _fail("offer.milestones must contain 1..100 items")
    milestones: list[dict[str, Any]] = []
    milestone_ids: set[str] = set()
    assigned: set[str] = set()
    milestone_total = 0
    for i, item in enumerate(milestones_raw):
        where = f"offer.milestones[{i}]"
        _exact_keys(item, {"id", "deliverable_ids", "amount_minor", "acceptance_window_hours", "payment_due_days"}, where)
        mid = _identifier(item["id"], f"{where}.id")
        if mid in milestone_ids:
            _fail(f"duplicate milestone id: {mid}")
        milestone_ids.add(mid)
        ids = item["deliverable_ids"]
        if type(ids) is not list or not ids:
            _fail(f"{where}.deliverable_ids must be a nonempty list")
        normalized_ids: list[str] = []
        local: set[str] = set()
        for j, raw_id in enumerate(ids):
            did = _identifier(raw_id, f"{where}.deliverable_ids[{j}]")
            if did not in deliverable_ids:
                _fail(f"{where} references unknown deliverable: {did}")
            if did in local or did in assigned:
                _fail(f"deliverable assigned more than once: {did}")
            local.add(did)
            assigned.add(did)
            normalized_ids.append(did)
        amount = _integer(item["amount_minor"], f"{where}.amount_minor")
        milestone_total += amount
        milestones.append(
            {
                "id": mid,
                "deliverable_ids": normalized_ids,
                "amount_minor": amount,
                "acceptance_window_hours": _integer(
                    item["acceptance_window_hours"], f"{where}.acceptance_window_hours", minimum=1, maximum=24 * 90
                ),
                "payment_due_days": _integer(item["payment_due_days"], f"{where}.payment_due_days", minimum=0, maximum=365),
            }
        )
    if assigned != deliverable_ids:
        _fail(f"unassigned deliverables: {sorted(deliverable_ids - assigned)}")
    if milestone_total != total:
        _fail("milestone amounts do not equal total_amount_minor")

    def text_list(raw: Any, where: str) -> list[str]:
        if type(raw) is not list or len(raw) > MAX_ITEMS:
            _fail(f"{where} must be a list of at most 100 strings")
        return [_text(v, f"{where}[{i}]") for i, v in enumerate(raw)]

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "offer_id": offer_id,
        "opportunity_id": opportunity_id,
        "buyer_ref": buyer_ref,
        "created_at": created_at,
        "valid_until": valid_until,
        "currency": currency,
        "total_amount_minor": total,
        "deliverables": deliverables,
        "milestones": milestones,
        "assumptions": text_list(spec["assumptions"], "offer.assumptions"),
        "exclusions": text_list(spec["exclusions"], "offer.exclusions"),
    }
    return normalized


def compile_offer(spec: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_offer_spec(spec)
    digest = _digest(normalized)
    return {
        "kind": "commercial_offer_contract",
        "schema_version": SCHEMA_VERSION,
        "state": "READY_FOR_OWNER_APPROVAL",
        "offer": normalized,
        "offer_sha256": digest,
        "owner_approval": None,
        "send_authority": None,
        "buyer_acceptance": None,
        "authority": {
            "external_send_authorized": False,
            "buyer_acceptance_verified": False,
            "fulfillment_authorized": False,
            "payment_collected": False,
            "revenue_recognized": False,
        },
    }


def _secret(secret: bytes) -> bytes:
    if type(secret) is not bytes or len(secret) < 32:
        _fail("owner secret must be bytes and at least 32 bytes")
    return secret


def _hmac(secret: bytes, domain: str, payload: Mapping[str, Any]) -> str:
    message = domain.encode("ascii") + b"\0" + _canonical(payload)
    return hmac.new(_secret(secret), message, hashlib.sha256).hexdigest()


def _validate_compiled_base(contract: Mapping[str, Any]) -> dict[str, Any]:
    _exact_keys(
        contract,
        {"kind", "schema_version", "state", "offer", "offer_sha256", "owner_approval", "send_authority", "buyer_acceptance", "authority"},
        "contract",
    )
    if contract["kind"] != "commercial_offer_contract" or contract["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported contract kind/schema")
    offer = validate_offer_spec(contract["offer"])
    offer_sha = _sha256(contract["offer_sha256"], "contract.offer_sha256")
    if _digest(offer) != offer_sha:
        _fail("offer_sha256 mismatch")
    authority = contract["authority"]
    _exact_keys(
        authority,
        {"external_send_authorized", "buyer_acceptance_verified", "fulfillment_authorized", "payment_collected", "revenue_recognized"},
        "contract.authority",
    )
    for key, value in authority.items():
        if type(value) is not bool:
            _fail(f"contract.authority.{key} must be boolean")
    if authority["payment_collected"] or authority["revenue_recognized"]:
        _fail("commercial offer contract can never self-assert payment or revenue")
    return offer


def approve_offer(compiled: Mapping[str, Any], secret: bytes, *, key_id: str, approved_at: str) -> dict[str, Any]:
    offer = _validate_compiled_base(compiled)
    if compiled["state"] != "READY_FOR_OWNER_APPROVAL" or compiled["owner_approval"] is not None:
        _fail("contract is not awaiting owner approval")
    if compiled["send_authority"] is not None or compiled["buyer_acceptance"] is not None:
        _fail("pre-approval contract contains downstream authority")
    if any(compiled["authority"].values()):
        _fail("pre-approval authority must be false")
    key_id = _identifier(key_id, "key_id")
    approved_at, approved_dt = _timestamp(approved_at, "approved_at")
    _, created_dt = _timestamp(offer["created_at"], "offer.created_at")
    _, valid_dt = _timestamp(offer["valid_until"], "offer.valid_until")
    if approved_dt < created_dt or approved_dt > valid_dt:
        _fail("approval must occur within offer validity")
    payload = {
        "key_id": key_id,
        "approved_at": approved_at,
        "offer_sha256": compiled["offer_sha256"],
    }
    approval = {**payload, "hmac_sha256": _hmac(secret, "commercial-offer-owner-approval-v1", payload)}
    out = copy.deepcopy(compiled)
    out["state"] = "OWNER_APPROVED"
    out["owner_approval"] = approval
    return out


def verify_owner_approval(contract: Mapping[str, Any], secret: bytes, *, trusted_now: str | None = None) -> dict[str, Any]:
    offer = _validate_compiled_base(contract)
    approval = contract["owner_approval"]
    _exact_keys(approval, {"key_id", "approved_at", "offer_sha256", "hmac_sha256"}, "owner_approval")
    payload = {
        "key_id": _identifier(approval["key_id"], "owner_approval.key_id"),
        "approved_at": _timestamp(approval["approved_at"], "owner_approval.approved_at")[0],
        "offer_sha256": _sha256(approval["offer_sha256"], "owner_approval.offer_sha256"),
    }
    if payload["offer_sha256"] != contract["offer_sha256"]:
        _fail("owner approval is bound to a different offer")
    signature = _sha256(approval["hmac_sha256"], "owner_approval.hmac_sha256")
    expected = _hmac(secret, "commercial-offer-owner-approval-v1", payload)
    if not hmac.compare_digest(signature, expected):
        _fail("owner approval HMAC invalid")
    _, created_dt = _timestamp(offer["created_at"], "offer.created_at")
    _, valid_dt = _timestamp(offer["valid_until"], "offer.valid_until")
    _, approved_dt = _timestamp(payload["approved_at"], "owner_approval.approved_at")
    if approved_dt < created_dt or approved_dt > valid_dt:
        _fail("owner approval timestamp outside validity")
    if trusted_now is not None:
        _, now_dt = _timestamp(trusted_now, "trusted_now")
        if now_dt > valid_dt:
            _fail("offer expired at trusted_now")
    return copy.deepcopy(dict(contract))


def authorize_send(
    approved: Mapping[str, Any],
    secret: bytes,
    *,
    destination_sha256: str,
    channel: str,
    authorized_at: str,
) -> dict[str, Any]:
    verify_owner_approval(approved, secret, trusted_now=authorized_at)
    if approved["state"] != "OWNER_APPROVED" or approved["send_authority"] is not None:
        _fail("contract is not awaiting send authorization")
    if approved["buyer_acceptance"] is not None or approved["authority"]["external_send_authorized"]:
        _fail("unexpected downstream authority before send authorization")
    destination_sha256 = _sha256(destination_sha256, "destination_sha256")
    channel = _text(channel, "channel", max_len=32)
    if channel not in CHANNELS:
        _fail("unsupported send channel")
    authorized_at, authorized_dt = _timestamp(authorized_at, "authorized_at")
    _, approved_dt = _timestamp(approved["owner_approval"]["approved_at"], "owner_approval.approved_at")
    if authorized_dt < approved_dt:
        _fail("send authorization cannot predate owner approval")
    payload = {
        "offer_sha256": approved["offer_sha256"],
        "owner_approval_hmac": approved["owner_approval"]["hmac_sha256"],
        "destination_sha256": destination_sha256,
        "channel": channel,
        "authorized_at": authorized_at,
    }
    receipt = {**payload, "hmac_sha256": _hmac(secret, "commercial-offer-send-authority-v1", payload)}
    out = copy.deepcopy(approved)
    out["state"] = "READY_FOR_EXPLICIT_SEND"
    out["send_authority"] = receipt
    out["authority"]["external_send_authorized"] = True
    return out


def verify_send_authority(contract: Mapping[str, Any], secret: bytes, *, trusted_now: str | None = None) -> dict[str, Any]:
    verify_owner_approval(contract, secret, trusted_now=trusted_now)
    receipt = contract["send_authority"]
    _exact_keys(
        receipt,
        {"offer_sha256", "owner_approval_hmac", "destination_sha256", "channel", "authorized_at", "hmac_sha256"},
        "send_authority",
    )
    channel = _text(receipt["channel"], "send_authority.channel", max_len=32)
    if channel not in CHANNELS:
        _fail("unsupported send channel")
    authorized_at, authorized_dt = _timestamp(receipt["authorized_at"], "send_authority.authorized_at")
    _, approved_dt = _timestamp(contract["owner_approval"]["approved_at"], "owner_approval.approved_at")
    _, valid_dt = _timestamp(contract["offer"]["valid_until"], "offer.valid_until")
    if authorized_dt < approved_dt or authorized_dt > valid_dt:
        _fail("send authorization timestamp outside authorized offer window")
    payload = {
        "offer_sha256": _sha256(receipt["offer_sha256"], "send_authority.offer_sha256"),
        "owner_approval_hmac": _sha256(receipt["owner_approval_hmac"], "send_authority.owner_approval_hmac"),
        "destination_sha256": _sha256(receipt["destination_sha256"], "send_authority.destination_sha256"),
        "channel": channel,
        "authorized_at": authorized_at,
    }
    if payload["offer_sha256"] != contract["offer_sha256"]:
        _fail("send authority is bound to a different offer")
    if payload["owner_approval_hmac"] != contract["owner_approval"]["hmac_sha256"]:
        _fail("send authority is bound to a different owner approval")
    signature = _sha256(receipt["hmac_sha256"], "send_authority.hmac_sha256")
    expected = _hmac(secret, "commercial-offer-send-authority-v1", payload)
    if not hmac.compare_digest(signature, expected):
        _fail("send authority HMAC invalid")
    if contract["authority"]["external_send_authorized"] is not True:
        _fail("send authority receipt exists but authority flag is false")
    return copy.deepcopy(dict(contract))


def capture_buyer_acceptance(
    sent_authorized: Mapping[str, Any],
    secret: bytes,
    *,
    acceptance: Mapping[str, Any],
    trusted_now: str,
) -> dict[str, Any]:
    offer = _validate_compiled_base(sent_authorized)
    verify_send_authority(sent_authorized, secret, trusted_now=trusted_now)
    if sent_authorized["state"] != "READY_FOR_EXPLICIT_SEND" or sent_authorized["buyer_acceptance"] is not None:
        _fail("contract is not awaiting buyer acceptance evidence")
    _exact_keys(
        acceptance,
        {"offer_sha256", "buyer_ref", "accepted_at", "evidence_sha256", "identity_verification_sha256"},
        "acceptance",
    )
    accepted_at, accepted_dt = _timestamp(acceptance["accepted_at"], "acceptance.accepted_at")
    _, created_dt = _timestamp(offer["created_at"], "offer.created_at")
    _, valid_dt = _timestamp(offer["valid_until"], "offer.valid_until")
    _, now_dt = _timestamp(trusted_now, "trusted_now")
    _, authorized_dt = _timestamp(sent_authorized["send_authority"]["authorized_at"], "send_authority.authorized_at")
    if accepted_dt < created_dt or accepted_dt > valid_dt:
        _fail("buyer acceptance timestamp outside offer validity")
    if accepted_dt < authorized_dt:
        _fail("buyer acceptance cannot predate send authorization")
    if accepted_dt > now_dt:
        _fail("buyer acceptance is in the future relative to trusted_now")
    evidence = {
        "offer_sha256": _sha256(acceptance["offer_sha256"], "acceptance.offer_sha256"),
        "buyer_ref": _identifier(acceptance["buyer_ref"], "acceptance.buyer_ref"),
        "accepted_at": accepted_at,
        "evidence_sha256": _sha256(acceptance["evidence_sha256"], "acceptance.evidence_sha256"),
        "identity_verification_sha256": _sha256(
            acceptance["identity_verification_sha256"], "acceptance.identity_verification_sha256"
        ),
    }
    if evidence["offer_sha256"] != sent_authorized["offer_sha256"]:
        _fail("buyer acceptance is bound to a different offer")
    if evidence["buyer_ref"] != offer["buyer_ref"]:
        _fail("buyer acceptance identity does not match offer buyer_ref")
    out = copy.deepcopy(sent_authorized)
    out["state"] = "BUYER_ACCEPTANCE_EVIDENCE_CAPTURED"
    out["buyer_acceptance"] = evidence
    # Captured evidence is intentionally not self-asserted as buyer-verified authority.
    out["authority"]["buyer_acceptance_verified"] = False
    out["authority"]["fulfillment_authorized"] = False
    return out


def contract_receipt_sha256(contract: Mapping[str, Any]) -> str:
    _validate_compiled_base(contract)
    return _digest(dict(contract))
