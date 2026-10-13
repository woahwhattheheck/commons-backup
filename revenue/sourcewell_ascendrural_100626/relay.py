from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

ALLOWED_SERVICE_KINDS = frozenset({"NON_EMERGENCY_RIDE", "ESSENTIAL_GOODS_DELIVERY", "SERVICE_HANDOFF"})
ALLOWED_EVENTS = frozenset({"REQUEST_RECORDED", "ASSIGNMENT_OFFERED", "PROVIDER_ACCEPTED", "SERVICE_STARTED", "SERVICE_COMPLETED", "EXCEPTION_RECORDED", "CANCELLED"})

class RelayError(ValueError):
    pass

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()

def _strict_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    extra = set(value) - allowed
    if extra: raise RelayError(f"{label}: unknown keys: {sorted(extra)}")

@dataclass(frozen=True)
class RelayReceipt:
    request_id: str
    disposition: str
    state: str
    provider_id: str | None
    blockers: tuple[str, ...]
    event_count: int
    logical_event_count: int
    ledger_digest: str
    receipt_digest: str
    def as_dict(self) -> dict[str, Any]:
        return {"schema": "rural-access-relay/audit-v1", "request_id": self.request_id, "disposition": self.disposition, "state": self.state, "provider_id": self.provider_id, "blockers": list(self.blockers), "event_count": self.event_count, "logical_event_count": self.logical_event_count, "ledger_digest": self.ledger_digest, "receipt_digest": self.receipt_digest}

def audit_request(request: Mapping[str, Any], events: Iterable[Mapping[str, Any]]) -> RelayReceipt:
    _strict_keys(request, {"request_id", "service_kind", "emergency", "clinical_decision_required", "operator_review_required", "origin_zone", "destination_zone"}, "request")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 96: raise RelayError("invalid request_id")
    if request.get("service_kind") not in ALLOWED_SERVICE_KINDS: raise RelayError("unsupported service kind")
    if request.get("emergency") is not False: raise RelayError("emergency requests are outside authority")
    if request.get("clinical_decision_required") is not False: raise RelayError("clinical decision requests are outside authority")
    if request.get("operator_review_required") is not True: raise RelayError("operator review must remain required")
    for zone_key in ("origin_zone", "destination_zone"):
        zone = request.get(zone_key)
        if not isinstance(zone, str) or not zone or len(zone) > 96: raise RelayError(f"invalid {zone_key}")

    raw_events = list(events)
    seen: dict[str, bytes] = {}
    logical: list[dict[str, Any]] = []
    blockers: list[str] = []
    for i, event in enumerate(raw_events):
        if not isinstance(event, Mapping): raise RelayError(f"event[{i}] must be object")
        _strict_keys(event, {"event_id", "request_id", "type", "provider_id", "sequence", "evidence_sha256"}, f"event[{i}]")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 96: raise RelayError(f"event[{i}]: invalid event_id")
        if event.get("request_id") != request_id: raise RelayError(f"event[{i}]: cross-request event")
        typ = event.get("type")
        if typ not in ALLOWED_EVENTS: raise RelayError(f"event[{i}]: unknown type")
        seq = event.get("sequence")
        if type(seq) is not int or seq < 0: raise RelayError(f"event[{i}]: sequence must be non-negative int")
        evidence = event.get("evidence_sha256")
        if not isinstance(evidence, str) or len(evidence) != 64 or any(c not in "0123456789abcdef" for c in evidence): raise RelayError(f"event[{i}]: invalid evidence digest")
        provider = event.get("provider_id")
        if typ in {"ASSIGNMENT_OFFERED", "PROVIDER_ACCEPTED", "SERVICE_STARTED", "SERVICE_COMPLETED", "EXCEPTION_RECORDED"}:
            if not isinstance(provider, str) or not provider or len(provider) > 96: raise RelayError(f"event[{i}]: provider required")
        elif provider is not None and (not isinstance(provider, str) or not provider): raise RelayError(f"event[{i}]: invalid provider")
        encoded = _canonical(dict(event))
        previous = seen.get(event_id)
        if previous is not None:
            if previous != encoded: blockers.append(f"EVENT_ID_CONFLICT:{event_id}")
            continue
        seen[event_id] = encoded
        logical.append(dict(event))

    logical.sort(key=lambda e: (e["sequence"], e["event_id"]))
    sequences = [e["sequence"] for e in logical]
    if len(sequences) != len(set(sequences)): blockers.append("DUPLICATE_SEQUENCE")
    if sequences and sequences != list(range(sequences[0], sequences[0] + len(sequences))): blockers.append("SEQUENCE_GAP")
    if sequences and sequences[0] != 0: blockers.append("SEQUENCE_MUST_START_AT_ZERO")

    state = "EMPTY"; provider_id: str | None = None; accepted_provider: str | None = None; terminal = False
    for event in logical:
        typ = event["type"]; provider = event.get("provider_id")
        if terminal:
            blockers.append(f"EVENT_AFTER_TERMINAL:{typ}"); continue
        if typ == "REQUEST_RECORDED":
            if state != "EMPTY": blockers.append("REQUEST_RECORDED_OUT_OF_ORDER")
            else: state = "RECORDED"
        elif typ == "ASSIGNMENT_OFFERED":
            if state not in {"RECORDED", "EXCEPTION"}: blockers.append("ASSIGNMENT_OUT_OF_ORDER")
            else: state = "OFFERED"; provider_id = provider
        elif typ == "PROVIDER_ACCEPTED":
            if state != "OFFERED" or provider != provider_id: blockers.append("PROVIDER_ACCEPTANCE_MISMATCH")
            elif accepted_provider is not None and accepted_provider != provider: blockers.append("MULTIPLE_ACCEPTED_PROVIDERS")
            else: accepted_provider = provider; provider_id = provider; state = "ACCEPTED"
        elif typ == "SERVICE_STARTED":
            if state != "ACCEPTED" or provider != accepted_provider: blockers.append("SERVICE_START_WITHOUT_ACCEPTANCE")
            else: state = "STARTED"
        elif typ == "SERVICE_COMPLETED":
            if state != "STARTED" or provider != accepted_provider: blockers.append("SERVICE_COMPLETE_WITHOUT_START")
            else: state = "COMPLETED"; terminal = True
        elif typ == "EXCEPTION_RECORDED":
            if state not in {"OFFERED", "ACCEPTED", "STARTED"}: blockers.append("EXCEPTION_OUT_OF_ORDER")
            elif provider != provider_id: blockers.append("EXCEPTION_PROVIDER_MISMATCH")
            else: state = "EXCEPTION"; provider_id = None; accepted_provider = None
        elif typ == "CANCELLED":
            if state == "EMPTY": blockers.append("CANCEL_WITHOUT_REQUEST")
            else: state = "CANCELLED"; terminal = True
    if state == "EMPTY": blockers.append("REQUEST_EVENT_REQUIRED")

    ledger_digest = _digest({"request": dict(request), "events": logical})
    disposition = "HOLD" if blockers else "CONSISTENT_FOR_OPERATOR_REVIEW"
    body = {"schema": "rural-access-relay/audit-v1", "request_id": request_id, "disposition": disposition, "state": state, "provider_id": provider_id, "blockers": sorted(set(blockers)), "event_count": len(raw_events), "logical_event_count": len(logical), "ledger_digest": ledger_digest}
    return RelayReceipt(request_id, disposition, state, provider_id, tuple(body["blockers"]), len(raw_events), len(logical), ledger_digest, _digest(body))

def verify_receipt(receipt: Mapping[str, Any]) -> bool:
    _strict_keys(receipt, {"schema", "request_id", "disposition", "state", "provider_id", "blockers", "event_count", "logical_event_count", "ledger_digest", "receipt_digest"}, "receipt")
    if receipt.get("schema") != "rural-access-relay/audit-v1": return False
    digest = receipt.get("receipt_digest")
    if not isinstance(digest, str): return False
    body = dict(receipt); body.pop("receipt_digest", None)
    return _digest(body) == digest
