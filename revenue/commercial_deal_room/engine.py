from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

VERSION = "commercial-deal-room/v1"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

EVENT_TYPES = {
    "OFFER_SENT",
    "BUYER_INTEREST",
    "PROPOSAL_SENT",
    "BUYER_ACCEPTED",
    "BUYER_REJECTED",
    "DNR",
    "PAYMENT_ROAD_CONFIGURED",
    "PAYMENT_REQUEST_SENT",
    "SETTLEMENT_OBSERVED",
    "SETTLEMENT_REVERSED",
    "FULFILLMENT_ARTIFACT",
    "FULFILLMENT_SENT",
    "BUYER_FULFILLMENT_ACCEPTED",
}
BUYER_EVENTS = {"BUYER_INTEREST", "BUYER_ACCEPTED", "BUYER_REJECTED", "BUYER_FULFILLMENT_ACCEPTED"}
EXTERNAL_EVENTS = BUYER_EVENTS | {"OFFER_SENT", "PROPOSAL_SENT", "PAYMENT_REQUEST_SENT", "SETTLEMENT_OBSERVED", "SETTLEMENT_REVERSED", "FULFILLMENT_SENT"}


class ContractError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_exact_keys(obj: Mapping[str, Any], required: set[str], optional: set[str] = set()) -> None:
    keys = set(obj)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise ContractError(f"missing keys: {sorted(missing)}")
    if extra:
        raise ContractError(f"unexpected keys: {sorted(extra)}")


def _require_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ContractError(f"invalid {name}")
    return value


def _require_sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ContractError(f"invalid {name}")
    return value


def _require_minor(value: Any, name: str, *, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{name} must be integer minor units")
    if value < 0 or (not allow_zero and value == 0):
        raise ContractError(f"invalid {name}")
    if value > 10**15:
        raise ContractError(f"{name} out of range")
    return value


def _parse_ts(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{name} must be UTC Z timestamp")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"invalid {name}") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ContractError(f"{name} must be UTC")
    return dt


def _ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ContractError("evaluation time must be timezone-aware")
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _normalize_offer(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContractError("offer must be object")
    _require_exact_keys(
        raw,
        {"offer_id", "currency", "price_minor", "required_before_start_minor", "scope_sha256", "terms_sha256", "created_at", "expires_at"},
    )
    offer_id = _require_id(raw["offer_id"], "offer.offer_id")
    currency = raw["currency"]
    if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
        raise ContractError("invalid offer.currency")
    price = _require_minor(raw["price_minor"], "offer.price_minor", allow_zero=False)
    required = _require_minor(raw["required_before_start_minor"], "offer.required_before_start_minor")
    if required > price:
        raise ContractError("required_before_start_minor exceeds price_minor")
    created = _parse_ts(raw["created_at"], "offer.created_at")
    expires = _parse_ts(raw["expires_at"], "offer.expires_at")
    if expires <= created:
        raise ContractError("offer.expires_at must be after created_at")
    return {
        "offer_id": offer_id,
        "currency": currency,
        "price_minor": price,
        "required_before_start_minor": required,
        "scope_sha256": _require_sha(raw["scope_sha256"], "offer.scope_sha256"),
        "terms_sha256": _require_sha(raw["terms_sha256"], "offer.terms_sha256"),
        "created_at": _ts(created),
        "expires_at": _ts(expires),
    }


def _normalize_event(raw: Any, identity: Tuple[str, str, str]) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContractError("event must be object")
    _require_exact_keys(
        raw,
        {"event_id", "type", "buyer_id", "opportunity_id", "offer_id", "observed_at", "source_ref", "source_sha256", "payload"},
    )
    event_id = _require_id(raw["event_id"], "event.event_id")
    event_type = raw["type"]
    if event_type not in EVENT_TYPES:
        raise ContractError(f"unsupported event type: {event_type!r}")
    buyer_id = _require_id(raw["buyer_id"], "event.buyer_id")
    opportunity_id = _require_id(raw["opportunity_id"], "event.opportunity_id")
    offer_id = _require_id(raw["offer_id"], "event.offer_id")
    if (buyer_id, opportunity_id, offer_id) != identity:
        raise ContractError("event identity does not match deal identity")
    observed = _parse_ts(raw["observed_at"], "event.observed_at")
    source_ref = raw["source_ref"]
    if not isinstance(source_ref, str) or not source_ref or len(source_ref) > 512:
        raise ContractError("invalid event.source_ref")
    source_sha = _require_sha(raw["source_sha256"], "event.source_sha256")
    payload = raw["payload"]
    if not isinstance(payload, Mapping):
        raise ContractError("event.payload must be object")
    normalized = {
        "event_id": event_id,
        "type": event_type,
        "buyer_id": buyer_id,
        "opportunity_id": opportunity_id,
        "offer_id": offer_id,
        "observed_at": _ts(observed),
        "source_ref": source_ref,
        "source_sha256": source_sha,
        "payload": _normalize_payload(event_type, payload),
    }
    return normalized


def _message_payload(payload: Mapping[str, Any], *, extra_required: set[str] = set(), extra_optional: set[str] = set()) -> Dict[str, Any]:
    required = {"provider", "provider_message_id"} | extra_required
    _require_exact_keys(payload, required, extra_optional)
    provider = _require_id(payload["provider"], "payload.provider")
    provider_message_id = _require_id(payload["provider_message_id"], "payload.provider_message_id")
    result: Dict[str, Any] = {"provider": provider, "provider_message_id": provider_message_id}
    return result


def _normalize_payload(event_type: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    if event_type == "OFFER_SENT":
        result = _message_payload(payload, extra_required={"scope_sha256", "terms_sha256"})
        result["scope_sha256"] = _require_sha(payload["scope_sha256"], "payload.scope_sha256")
        result["terms_sha256"] = _require_sha(payload["terms_sha256"], "payload.terms_sha256")
        return result
    if event_type == "BUYER_INTEREST":
        result = _message_payload(payload, extra_required={"reply_to_event_id"})
        result["reply_to_event_id"] = _require_id(payload["reply_to_event_id"], "payload.reply_to_event_id")
        return result
    if event_type == "PROPOSAL_SENT":
        result = _message_payload(payload, extra_required={"reply_to_event_id", "proposal_sha256", "revision"})
        result["reply_to_event_id"] = _require_id(payload["reply_to_event_id"], "payload.reply_to_event_id")
        result["proposal_sha256"] = _require_sha(payload["proposal_sha256"], "payload.proposal_sha256")
        revision = payload["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1 or revision > 1000000:
            raise ContractError("invalid payload.revision")
        result["revision"] = revision
        return result
    if event_type in {"BUYER_ACCEPTED", "BUYER_REJECTED"}:
        result = _message_payload(payload, extra_required={"reply_to_event_id", "accepted_proposal_sha256" if event_type == "BUYER_ACCEPTED" else "reason_code"})
        result["reply_to_event_id"] = _require_id(payload["reply_to_event_id"], "payload.reply_to_event_id")
        if event_type == "BUYER_ACCEPTED":
            result["accepted_proposal_sha256"] = _require_sha(payload["accepted_proposal_sha256"], "payload.accepted_proposal_sha256")
        else:
            result["reason_code"] = _require_id(payload["reason_code"], "payload.reason_code")
        return result
    if event_type == "DNR":
        _require_exact_keys(payload, {"reason_code"})
        return {"reason_code": _require_id(payload["reason_code"], "payload.reason_code")}
    if event_type == "PAYMENT_ROAD_CONFIGURED":
        _require_exact_keys(payload, {"route_id", "route_sha256"})
        return {
            "route_id": _require_id(payload["route_id"], "payload.route_id"),
            "route_sha256": _require_sha(payload["route_sha256"], "payload.route_sha256"),
        }
    if event_type == "PAYMENT_REQUEST_SENT":
        result = _message_payload(payload, extra_required={"route_id", "currency", "amount_minor"})
        result["route_id"] = _require_id(payload["route_id"], "payload.route_id")
        cur = payload["currency"]
        if not isinstance(cur, str) or not CURRENCY_RE.fullmatch(cur):
            raise ContractError("invalid payload.currency")
        result["currency"] = cur
        result["amount_minor"] = _require_minor(payload["amount_minor"], "payload.amount_minor", allow_zero=False)
        return result
    if event_type == "SETTLEMENT_OBSERVED":
        _require_exact_keys(payload, {"settlement_id", "route_id", "currency", "amount_minor"})
        cur = payload["currency"]
        if not isinstance(cur, str) or not CURRENCY_RE.fullmatch(cur):
            raise ContractError("invalid payload.currency")
        return {
            "settlement_id": _require_id(payload["settlement_id"], "payload.settlement_id"),
            "route_id": _require_id(payload["route_id"], "payload.route_id"),
            "currency": cur,
            "amount_minor": _require_minor(payload["amount_minor"], "payload.amount_minor", allow_zero=False),
        }
    if event_type == "SETTLEMENT_REVERSED":
        _require_exact_keys(payload, {"settlement_id", "reversal_id", "currency", "amount_minor"})
        cur = payload["currency"]
        if not isinstance(cur, str) or not CURRENCY_RE.fullmatch(cur):
            raise ContractError("invalid payload.currency")
        return {
            "settlement_id": _require_id(payload["settlement_id"], "payload.settlement_id"),
            "reversal_id": _require_id(payload["reversal_id"], "payload.reversal_id"),
            "currency": cur,
            "amount_minor": _require_minor(payload["amount_minor"], "payload.amount_minor", allow_zero=False),
        }
    if event_type == "FULFILLMENT_ARTIFACT":
        _require_exact_keys(payload, {"artifact_id", "artifact_sha256"})
        return {
            "artifact_id": _require_id(payload["artifact_id"], "payload.artifact_id"),
            "artifact_sha256": _require_sha(payload["artifact_sha256"], "payload.artifact_sha256"),
        }
    if event_type == "FULFILLMENT_SENT":
        result = _message_payload(payload, extra_required={"artifact_event_id"})
        result["artifact_event_id"] = _require_id(payload["artifact_event_id"], "payload.artifact_event_id")
        return result
    if event_type == "BUYER_FULFILLMENT_ACCEPTED":
        result = _message_payload(payload, extra_required={"reply_to_event_id", "artifact_event_id"})
        result["reply_to_event_id"] = _require_id(payload["reply_to_event_id"], "payload.reply_to_event_id")
        result["artifact_event_id"] = _require_id(payload["artifact_event_id"], "payload.artifact_event_id")
        return result
    raise AssertionError(event_type)


def normalize_packet(packet: Any) -> Dict[str, Any]:
    if not isinstance(packet, Mapping):
        raise ContractError("packet must be object")
    _require_exact_keys(packet, {"version", "buyer_id", "opportunity_id", "offer", "events"})
    if packet["version"] != VERSION:
        raise ContractError("unsupported version")
    buyer_id = _require_id(packet["buyer_id"], "buyer_id")
    opportunity_id = _require_id(packet["opportunity_id"], "opportunity_id")
    offer = _normalize_offer(packet["offer"])
    events = packet["events"]
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
        raise ContractError("events must be array")
    if len(events) > 10000:
        raise ContractError("too many events")
    identity = (buyer_id, opportunity_id, offer["offer_id"])
    normalized_events = [_normalize_event(event, identity) for event in events]
    return {"version": VERSION, "buyer_id": buyer_id, "opportunity_id": opportunity_id, "offer": offer, "events": normalized_events}


def _event_time(event: Mapping[str, Any]) -> datetime:
    return _parse_ts(event["observed_at"], "event.observed_at")


def _hold(reason: str, reasons: List[str]) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _collapse_events(events: Sequence[Mapping[str, Any]], reasons: List[str]) -> Tuple[List[Dict[str, Any]], int]:
    by_id: Dict[str, Dict[str, Any]] = {}
    replays = 0
    for event in events:
        eid = event["event_id"]
        event_copy = dict(event)
        prior = by_id.get(eid)
        if prior is None:
            by_id[eid] = event_copy
        elif canonical_json(prior) == canonical_json(event_copy):
            replays += 1
        else:
            _hold("EVENT_ID_CONFLICT", reasons)
    unique = sorted(by_id.values(), key=lambda e: (e["observed_at"], e["event_id"]))
    return unique, replays


def compile_board(packet: Any, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    normalized = normalize_packet(packet)
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ContractError("now must be timezone-aware")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    offer = normalized["offer"]
    reasons: List[str] = []
    events, replay_collapses = _collapse_events(normalized["events"], reasons)
    event_by_id = {e["event_id"]: e for e in events}

    # No future observations may influence current authority.
    for event in events:
        if _event_time(event) > now:
            _hold("FUTURE_EVENT", reasons)

    # Provider/external identifiers are namespace-bound. Same provider/message cannot describe two facts.
    ext_ids: Dict[Tuple[str, str], bytes] = {}
    for event in events:
        if event["type"] not in EXTERNAL_EVENTS:
            continue
        payload = event["payload"]
        provider = payload.get("provider")
        message_id = payload.get("provider_message_id")
        if provider is None or message_id is None:
            continue
        key = (provider, message_id)
        body = canonical_json(event)
        prior = ext_ids.get(key)
        if prior is None:
            ext_ids[key] = body
        elif prior != body:
            _hold("PROVIDER_MESSAGE_ID_CONFLICT", reasons)

    offer_created = _parse_ts(offer["created_at"], "offer.created_at")
    offer_expires = _parse_ts(offer["expires_at"], "offer.expires_at")
    for event in events:
        if _event_time(event) < offer_created:
            _hold("EVENT_BEFORE_OFFER", reasons)

    by_type: Dict[str, List[Dict[str, Any]]] = {t: [] for t in EVENT_TYPES}
    for event in events:
        by_type[event["type"]].append(event)

    offer_sends = by_type["OFFER_SENT"]
    if len(offer_sends) > 1:
        # A second materially same outbound offer is treated as a fleet collision, not a harmless retry.
        _hold("DUPLICATE_OFFER_SEND", reasons)
    for sent in offer_sends:
        if sent["payload"]["scope_sha256"] != offer["scope_sha256"] or sent["payload"]["terms_sha256"] != offer["terms_sha256"]:
            _hold("OFFER_SEND_BINDING_MISMATCH", reasons)

    # Buyer events must be replies to known outbound evidence and occur after it.
    for event in by_type["BUYER_INTEREST"] + by_type["BUYER_ACCEPTED"] + by_type["BUYER_REJECTED"]:
        ref = event["payload"]["reply_to_event_id"]
        target = event_by_id.get(ref)
        allowed = {"OFFER_SENT", "PROPOSAL_SENT"}
        if target is None or target["type"] not in allowed:
            _hold("BUYER_REPLY_REFERENCE_INVALID", reasons)
        elif _event_time(event) <= _event_time(target):
            _hold("BUYER_REPLY_CHRONOLOGY_INVALID", reasons)

    # Proposals require buyer interest (or a prior proposal revision) and monotonically increasing revisions.
    proposals = by_type["PROPOSAL_SENT"]
    seen_revisions: set[int] = set()
    latest_proposal: Optional[Dict[str, Any]] = None
    for proposal in proposals:
        ref = proposal["payload"]["reply_to_event_id"]
        target = event_by_id.get(ref)
        if target is None or target["type"] not in {"BUYER_INTEREST", "PROPOSAL_SENT"}:
            _hold("PROPOSAL_REFERENCE_INVALID", reasons)
        elif _event_time(proposal) <= _event_time(target):
            _hold("PROPOSAL_CHRONOLOGY_INVALID", reasons)
        rev = proposal["payload"]["revision"]
        if rev in seen_revisions:
            _hold("PROPOSAL_REVISION_DUPLICATE", reasons)
        seen_revisions.add(rev)
        if latest_proposal is None or (rev, proposal["observed_at"], proposal["event_id"]) > (
            latest_proposal["payload"]["revision"], latest_proposal["observed_at"], latest_proposal["event_id"]
        ):
            latest_proposal = proposal
    if proposals and seen_revisions and seen_revisions != set(range(1, max(seen_revisions) + 1)):
        _hold("PROPOSAL_REVISION_GAP", reasons)

    # Acceptance binds the exact latest proposal generation, or offer scope if no proposal exists.
    acceptances = by_type["BUYER_ACCEPTED"]
    latest_acceptance = max(acceptances, key=lambda e: (e["observed_at"], e["event_id"]), default=None)
    if latest_acceptance is not None:
        expected = latest_proposal["payload"]["proposal_sha256"] if latest_proposal else offer["scope_sha256"]
        if latest_acceptance["payload"]["accepted_proposal_sha256"] != expected:
            _hold("BUYER_ACCEPTANCE_BINDING_MISMATCH", reasons)
        if latest_proposal is not None:
            if latest_acceptance["payload"]["reply_to_event_id"] != latest_proposal["event_id"]:
                _hold("BUYER_ACCEPTANCE_REFERENCE_NOT_LATEST_PROPOSAL", reasons)
            if _event_time(latest_acceptance) <= _event_time(latest_proposal):
                _hold("BUYER_ACCEPTANCE_CHRONOLOGY_INVALID", reasons)

    # DNR/rejection remains effective until a strictly later genuine buyer-origin event reopens the seam.
    negative_events = by_type["DNR"] + by_type["BUYER_REJECTED"]
    latest_negative = max(negative_events, key=lambda e: (e["observed_at"], e["event_id"]), default=None)
    latest_buyer = max((e for e in events if e["type"] in BUYER_EVENTS), key=lambda e: (e["observed_at"], e["event_id"]), default=None)
    dnr_effective = False
    if latest_negative is not None:
        dnr_effective = latest_buyer is None or _event_time(latest_buyer) <= _event_time(latest_negative)

    # Payment road is metadata only; it can never prove payment.
    roads = by_type["PAYMENT_ROAD_CONFIGURED"]
    active_road = max(roads, key=lambda e: (e["observed_at"], e["event_id"]), default=None)
    requests = by_type["PAYMENT_REQUEST_SENT"]
    for request in requests:
        if active_road is None:
            _hold("PAYMENT_REQUEST_WITHOUT_ROAD", reasons)
            continue
        if request["payload"]["route_id"] != active_road["payload"]["route_id"]:
            _hold("PAYMENT_REQUEST_ROUTE_MISMATCH", reasons)
        if request["payload"]["currency"] != offer["currency"]:
            _hold("PAYMENT_REQUEST_CURRENCY_MISMATCH", reasons)
        if request["payload"]["amount_minor"] > offer["price_minor"]:
            _hold("PAYMENT_REQUEST_EXCEEDS_OFFER", reasons)
        if latest_acceptance is None or _event_time(request) <= _event_time(latest_acceptance):
            _hold("PAYMENT_REQUEST_BEFORE_ACCEPTANCE", reasons)

    latest_request = max(requests, key=lambda e: (e["observed_at"], e["event_id"]), default=None)

    settlements = by_type["SETTLEMENT_OBSERVED"]
    settlement_by_id: Dict[str, Dict[str, Any]] = {}
    for settlement in settlements:
        sid = settlement["payload"]["settlement_id"]
        prior = settlement_by_id.get(sid)
        if prior is not None and canonical_json(prior["payload"]) != canonical_json(settlement["payload"]):
            _hold("SETTLEMENT_ID_CONFLICT", reasons)
        settlement_by_id[sid] = settlement
        if active_road is None or settlement["payload"]["route_id"] != active_road["payload"]["route_id"]:
            _hold("SETTLEMENT_ROUTE_MISMATCH", reasons)
        if settlement["payload"]["currency"] != offer["currency"]:
            _hold("SETTLEMENT_CURRENCY_MISMATCH", reasons)
        if latest_request is None or _event_time(settlement) <= _event_time(latest_request):
            _hold("SETTLEMENT_BEFORE_PAYMENT_REQUEST", reasons)

    reversal_total = 0
    reversed_by_settlement: Dict[str, int] = {}
    reversal_by_id: Dict[str, Dict[str, Any]] = {}
    for reversal in by_type["SETTLEMENT_REVERSED"]:
        rid = reversal["payload"]["reversal_id"]
        prior_reversal = reversal_by_id.get(rid)
        if prior_reversal is not None:
            if canonical_json(prior_reversal["payload"]) != canonical_json(reversal["payload"]):
                _hold("REVERSAL_ID_CONFLICT", reasons)
            continue
        reversal_by_id[rid] = reversal
        sid = reversal["payload"]["settlement_id"]
        settlement = settlement_by_id.get(sid)
        if settlement is None:
            _hold("REVERSAL_UNKNOWN_SETTLEMENT", reasons)
            continue
        if reversal["payload"]["currency"] != offer["currency"]:
            _hold("REVERSAL_CURRENCY_MISMATCH", reasons)
        if _event_time(reversal) <= _event_time(settlement):
            _hold("REVERSAL_CHRONOLOGY_INVALID", reasons)
        reversed_by_settlement[sid] = reversed_by_settlement.get(sid, 0) + reversal["payload"]["amount_minor"]
        if reversed_by_settlement[sid] > settlement["payload"]["amount_minor"]:
            _hold("REVERSAL_EXCEEDS_SETTLEMENT", reasons)
        reversal_total += reversal["payload"]["amount_minor"]

    gross_settled = sum(s["payload"]["amount_minor"] for s in settlement_by_id.values())
    net_settled = gross_settled - reversal_total
    if net_settled < 0:
        _hold("NEGATIVE_NET_SETTLEMENT", reasons)
    if net_settled > offer["price_minor"]:
        _hold("OVERSETTLEMENT_REQUIRES_RECONCILIATION", reasons)

    # Fulfillment artifacts are not acceptance and not send evidence.
    artifacts = by_type["FULFILLMENT_ARTIFACT"]
    artifact_by_event = {e["event_id"]: e for e in artifacts}
    fulfillment_sends = by_type["FULFILLMENT_SENT"]
    for sent in fulfillment_sends:
        aid = sent["payload"]["artifact_event_id"]
        artifact = artifact_by_event.get(aid)
        if artifact is None:
            _hold("FULFILLMENT_SEND_UNKNOWN_ARTIFACT", reasons)
        elif _event_time(sent) <= _event_time(artifact):
            _hold("FULFILLMENT_SEND_CHRONOLOGY_INVALID", reasons)
        if latest_acceptance is None or _event_time(sent) <= _event_time(latest_acceptance):
            _hold("FULFILLMENT_SENT_BEFORE_BUYER_ACCEPTANCE", reasons)
        if net_settled < offer["required_before_start_minor"]:
            _hold("FULFILLMENT_SENT_BEFORE_REQUIRED_SETTLEMENT", reasons)

    fulfillment_send_by_event = {e["event_id"]: e for e in fulfillment_sends}
    fulfillment_acceptances = by_type["BUYER_FULFILLMENT_ACCEPTED"]
    for accepted in fulfillment_acceptances:
        reply = accepted["payload"]["reply_to_event_id"]
        sent = fulfillment_send_by_event.get(reply)
        artifact_id = accepted["payload"]["artifact_event_id"]
        if sent is None or sent["payload"]["artifact_event_id"] != artifact_id:
            _hold("FULFILLMENT_ACCEPTANCE_REFERENCE_INVALID", reasons)
        elif _event_time(accepted) <= _event_time(sent):
            _hold("FULFILLMENT_ACCEPTANCE_CHRONOLOGY_INVALID", reasons)

    # Current-time expiration is a gate only until explicit buyer acceptance exists.
    if latest_acceptance is None and now > offer_expires:
        _hold("OFFER_EXPIRED", reasons)

    blocking_reasons = list(reasons)

    if blocking_reasons:
        stage = "HOLD"
        next_action = "INVESTIGATE_EVIDENCE"
    elif dnr_effective:
        stage = "DNR"
        next_action = "WAIT_DNR"
    elif not offer_sends:
        stage = "OFFER_READY"
        next_action = "OWNER_SEND_REVIEW"
    else:
        latest_interest = max(by_type["BUYER_INTEREST"], key=lambda e: (e["observed_at"], e["event_id"]), default=None)
        if latest_acceptance is None and latest_interest is None and not latest_proposal:
            stage = "AWAITING_BUYER"
            next_action = "WAIT_BUYER"
        elif latest_acceptance is None and latest_interest is not None and latest_proposal is None:
            stage = "BUYER_INTEREST"
            next_action = "PREPARE_SCOPE"
        elif latest_acceptance is None and latest_proposal is not None:
            stage = "PROPOSAL_SENT"
            next_action = "WAIT_BUYER"
        elif active_road is None:
            stage = "BUYER_ACCEPTED"
            next_action = "ESTABLISH_PAYMENT_ROAD"
        elif latest_request is None:
            stage = "PAYMENT_ROAD_READY"
            next_action = "ASK_FOR_PAYMENT"
        elif net_settled < offer["required_before_start_minor"]:
            stage = "AWAITING_SETTLEMENT"
            next_action = "WAIT_SETTLEMENT"
        elif not artifacts:
            stage = "FUNDED_TO_START"
            next_action = "FULFILL"
        elif not fulfillment_sends:
            stage = "FULFILLMENT_READY"
            next_action = "OWNER_DELIVERY_REVIEW"
        elif not fulfillment_acceptances:
            stage = "DELIVERED"
            next_action = "WAIT_BUYER_ACCEPTANCE"
        elif net_settled < offer["price_minor"]:
            stage = "FULFILLMENT_ACCEPTED_BALANCE_DUE"
            next_action = "ASK_FOR_BALANCE"
        else:
            stage = "CLOSED_SETTLED"
            next_action = "CLOSE_SETTLED"

    event_counts = {k: len(v) for k, v in sorted(by_type.items()) if v}
    commitment_input = dict(normalized)
    commitment_input["events"] = sorted(
        normalized["events"],
        key=lambda e: (e["event_id"], e["observed_at"], canonical_json(e)),
    )
    input_sha = sha256_hex(canonical_json(commitment_input))
    board_core: Dict[str, Any] = {
        "version": VERSION,
        "buyer_id": normalized["buyer_id"],
        "opportunity_id": normalized["opportunity_id"],
        "offer_id": offer["offer_id"],
        "evaluated_at": _ts(now),
        "stage": stage,
        "next_action": next_action,
        "reasons": sorted(blocking_reasons),
        "currency": offer["currency"],
        "price_minor": offer["price_minor"],
        "required_before_start_minor": offer["required_before_start_minor"],
        "gross_settled_minor": gross_settled,
        "reversed_minor": reversal_total,
        "net_settled_minor": net_settled,
        "outstanding_minor": max(0, offer["price_minor"] - max(0, net_settled)),
        "replay_collapses": replay_collapses,
        "event_counts": event_counts,
        "evidence": {
            "provider_send_present": bool(offer_sends),
            "buyer_acceptance_event_present": latest_acceptance is not None,
            "payment_road_configured": active_road is not None,
            "payment_request_send_present": latest_request is not None,
            "settlement_evidence_present": bool(settlement_by_id),
            "fulfillment_artifact_present": bool(artifacts),
            "fulfillment_send_present": bool(fulfillment_sends),
            "buyer_fulfillment_acceptance_event_present": bool(fulfillment_acceptances),
            "dnr_effective": dnr_effective,
        },
        "authority_ceiling": {
            "external_action_authorized": False,
            "provider_mutation_authorized": False,
            "payment_mutation_authorized": False,
            "buyer_acceptance_inferred_from_silence": False,
            "recognized_revenue_authorized": False,
            "evidence_authenticity_self_proven_by_hashes": False,
        },
        "input_sha256": input_sha,
    }
    board_core["receipt_sha256"] = sha256_hex(canonical_json(board_core))
    return board_core


def verify_board(packet: Any, board: Any, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    if not isinstance(board, Mapping):
        raise ContractError("board must be object")
    if "evaluated_at" not in board:
        raise ContractError("board missing evaluated_at")
    historical_at = _parse_ts(board["evaluated_at"], "board.evaluated_at")
    expected = compile_board(packet, now=historical_at)
    historical_valid = canonical_json(expected) == canonical_json(dict(board))
    current = compile_board(packet, now=now)
    return {
        "historical_valid": historical_valid,
        "historical_receipt_sha256": expected["receipt_sha256"],
        "current_stage": current["stage"],
        "current_next_action": current["next_action"],
        "current_reasons": current["reasons"],
        "current_receipt_sha256": current["receipt_sha256"],
    }


def render_markdown(board: Mapping[str, Any]) -> str:
    lines = [
        "# Commercial Deal Room",
        "",
        f"- Buyer: `{board['buyer_id']}`",
        f"- Opportunity: `{board['opportunity_id']}`",
        f"- Offer: `{board['offer_id']}`",
        f"- Stage: **{board['stage']}**",
        f"- Next action: **{board['next_action']}**",
        f"- Evaluated: `{board['evaluated_at']}`",
        f"- Net settlement evidence: `{board['net_settled_minor']} {board['currency']} minor units`",
        f"- Outstanding: `{board['outstanding_minor']} {board['currency']} minor units`",
        "",
    ]
    if board["reasons"]:
        lines += ["## Holds", ""] + [f"- `{reason}`" for reason in board["reasons"]] + [""]
    lines += [
        "## Truth ceiling",
        "",
        "Hashes and receipts detect tamper/replay; they do **not** authenticate a provider, buyer, or settlement source by themselves.",
        "This compiler never authorizes external sends, provider/payment mutation, or accounting revenue recognition.",
        "",
        f"Receipt: `{board['receipt_sha256']}`",
        "",
    ]
    return "\n".join(lines)
