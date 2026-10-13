from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

VERSION = "life-couriers-custody-evidence/v1"
MANIFEST_VERSION = "life-couriers-custody-manifest/v1"
STATUS_COMPLETE = "EVIDENCE_COMPLETE"
STATUS_HOLD = "HOLD"

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
SECRET_OR_PII_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|credential|authorization|cookie|session[_-]?id|ssn|social[_-]?security|dob|date[_-]?of[_-]?birth|mrn|medical[_-]?record|patient[_-]?name)",
    re.I,
)
FORBIDDEN_AUTHORITY_KEY = re.compile(
    r"(?:release[_-]?decision|dispatch[_-]?decision|temperature[_-]?disposition|customs[_-]?judg(?:e)?ment|clinical[_-]?decision|clinical[_-]?classification)",
    re.I,
)
SIGNATURE = re.compile(r"^[A-Za-z0-9+/=_:.-]{16,4096}$")


class EvidenceInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DetachedSigner:
    signer_id: str
    algorithm: str
    sign_digest: Callable[[bytes], str]


@dataclass(frozen=True)
class LegFinding:
    shipment_id: str
    leg_id: str
    sequence: int
    status: str
    codes: tuple[str, ...]


def _fail(code: str, message: str) -> None:
    raise EvidenceInputError(code, message)


def _plain(value: Any) -> bool:
    return isinstance(value, dict)


def _text(value: Any, field: str, *, minimum: int = 1, maximum: int = 240) -> str:
    if not isinstance(value, str):
        _fail("MALFORMED_INPUT", f"{field} must be text")
    cleaned = " ".join(value.split())
    if not minimum <= len(cleaned) <= maximum:
        _fail("MALFORMED_INPUT", f"{field} must be {minimum}-{maximum} characters")
    return cleaned


def _identifier(value: Any, field: str) -> str:
    text = _text(value, field, maximum=96)
    if not SAFE_ID.fullmatch(text):
        _fail("MALFORMED_INPUT", f"{field} has invalid identifier shape")
    return text


def _walk_reject(value: Any, path: str = "$", depth: int = 0, budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [0]
    if depth > 14:
        _fail("MALFORMED_INPUT", f"{path} exceeds maximum nesting depth")
    budget[0] += 1
    if budget[0] > 200000:
        _fail("MALFORMED_INPUT", "input exceeds maximum structural size")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_reject(item, f"{path}[{index}]", depth + 1, budget)
    elif _plain(value):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("MALFORMED_INPUT", f"{path} contains a non-text key")
            if SECRET_OR_PII_KEY.search(key):
                _fail("SECRET_OR_PII_FIELD", f"{path}.{key} is outside the shipment evidence schema")
            if FORBIDDEN_AUTHORITY_KEY.search(key):
                _fail("FORBIDDEN_AUTHORITY_FIELD", f"{path}.{key} exceeds evidence-only authority")
            _walk_reject(item, f"{path}.{key}", depth + 1, budget)


def _ts(value: Any, field: str) -> datetime:
    text = _text(value, field, minimum=20, maximum=35)
    if not text.endswith("Z"):
        _fail("MALFORMED_INPUT", f"{field} must be UTC RFC3339 ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        _fail("MALFORMED_INPUT", f"{field} is not valid RFC3339: {exc}")
    if parsed.tzinfo != timezone.utc:
        _fail("MALFORMED_INPUT", f"{field} must be UTC")
    return parsed


def _ts_text(value: Any, field: str) -> str:
    return _ts(value, field).isoformat().replace("+00:00", "Z")


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        _fail("MALFORMED_INPUT", f"{field} must be decimal-compatible")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        _fail("MALFORMED_INPUT", f"{field} must be a finite decimal")
    if not parsed.is_finite():
        _fail("MALFORMED_INPUT", f"{field} must be a finite decimal")
    return parsed


def _decimal_text(value: Any, field: str) -> str:
    parsed = _decimal(value, field)
    normalized = parsed.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _acknowledged(incidents: list[dict[str, Any]], code: str) -> bool:
    return any(item["code"] == code and bool(item["acknowledged_by"]) for item in incidents)


def _normalize_documents(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        if not _plain(raw):
            _fail("MALFORMED_INPUT", f"{field}[{index}] must be an object")
        doc_id = _identifier(raw.get("document_id"), f"{field}[{index}].document_id")
        if doc_id.lower() in seen:
            _fail("MALFORMED_INPUT", f"duplicate document id {doc_id}")
        seen.add(doc_id.lower())
        doc_type = _text(raw.get("type"), f"{field}[{index}].type", maximum=80)
        valid_from = _ts_text(raw.get("valid_from"), f"{field}[{index}].valid_from")
        valid_until = _ts_text(raw.get("valid_until"), f"{field}[{index}].valid_until")
        if _ts(valid_from, "valid_from") > _ts(valid_until, "valid_until"):
            _fail("MALFORMED_INPUT", f"{field}[{index}] validity interval is reversed")
        result.append({"document_id": doc_id, "type": doc_type, "valid_from": valid_from, "valid_until": valid_until})
    return sorted(result, key=lambda item: (item["type"], item["document_id"]))


def _normalize_incidents(value: Any, field: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        _fail("MALFORMED_INPUT", f"{field} must be an array")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        if not _plain(raw):
            _fail("MALFORMED_INPUT", f"{field}[{index}] must be an object")
        incident_id = _identifier(raw.get("incident_id"), f"{field}[{index}].incident_id")
        if incident_id.lower() in seen:
            _fail("MALFORMED_INPUT", f"duplicate incident id {incident_id}")
        seen.add(incident_id.lower())
        code = _identifier(raw.get("code"), f"{field}[{index}].code").upper()
        acknowledged_by = raw.get("acknowledged_by", "")
        if acknowledged_by is None:
            acknowledged_by = ""
        if not isinstance(acknowledged_by, str):
            _fail("MALFORMED_INPUT", f"{field}[{index}].acknowledged_by must be text")
        acknowledged_by = " ".join(acknowledged_by.split())
        result.append({"incident_id": incident_id, "code": code, "acknowledged_by": acknowledged_by})
    return sorted(result, key=lambda item: item["incident_id"])


def _normalize_leg(raw: Any, shipment_id: str, index: int) -> dict[str, Any]:
    field = f"shipments[{shipment_id}].legs[{index}]"
    if not _plain(raw):
        _fail("MALFORMED_INPUT", f"{field} must be an object")
    sequence = raw.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1 or sequence > 999:
        _fail("MALFORMED_INPUT", f"{field}.sequence must be an integer 1-999")
    predecessor = raw.get("predecessor_leg_id")
    if predecessor is not None:
        predecessor = _identifier(predecessor, f"{field}.predecessor_leg_id")
    sensor = raw.get("sensor")
    if not _plain(sensor):
        _fail("MALFORMED_INPUT", f"{field}.sensor must be an object")
    recipient = raw.get("recipient")
    if not _plain(recipient):
        recipient = {}
    pod = raw.get("pod")
    if not _plain(pod):
        pod = {}
    incidents = _normalize_incidents(raw.get("incidents", []), f"{field}.incidents")
    return {
        "leg_id": _identifier(raw.get("leg_id"), f"{field}.leg_id"),
        "sequence": sequence,
        "predecessor_leg_id": predecessor,
        "pickup_at": _ts_text(raw.get("pickup_at"), f"{field}.pickup_at"),
        "handoff_at": _ts_text(raw.get("handoff_at"), f"{field}.handoff_at"),
        "courier_id": "" if raw.get("courier_id") in (None, "") else _identifier(raw.get("courier_id"), f"{field}.courier_id"),
        "custodian_from": "" if raw.get("custodian_from") in (None, "") else _identifier(raw.get("custodian_from"), f"{field}.custodian_from"),
        "custodian_to": "" if raw.get("custodian_to") in (None, "") else _identifier(raw.get("custodian_to"), f"{field}.custodian_to"),
        "lane_id": _identifier(raw.get("lane_id"), f"{field}.lane_id"),
        "window_start": _ts_text(raw.get("window_start"), f"{field}.window_start"),
        "window_end": _ts_text(raw.get("window_end"), f"{field}.window_end"),
        "packout_id": _identifier(raw.get("packout_id"), f"{field}.packout_id"),
        "sensor": {
            "sensor_id": _identifier(sensor.get("sensor_id"), f"{field}.sensor.sensor_id"),
            "packout_id": _identifier(sensor.get("packout_id"), f"{field}.sensor.packout_id"),
            "min_temp_c": _decimal_text(sensor.get("min_temp_c"), f"{field}.sensor.min_temp_c"),
            "max_temp_c": _decimal_text(sensor.get("max_temp_c"), f"{field}.sensor.max_temp_c"),
            "observed_min_c": _decimal_text(sensor.get("observed_min_c"), f"{field}.sensor.observed_min_c"),
            "observed_max_c": _decimal_text(sensor.get("observed_max_c"), f"{field}.sensor.observed_max_c"),
        },
        "documents": _normalize_documents(raw.get("documents", []), f"{field}.documents"),
        "incidents": incidents,
        "recipient": {
            "recipient_id": "" if recipient.get("recipient_id") in (None, "") else _identifier(recipient.get("recipient_id"), f"{field}.recipient.recipient_id"),
            "received_at": "" if recipient.get("received_at") in (None, "") else _ts_text(recipient.get("received_at"), f"{field}.recipient.received_at"),
        },
        "pod": {
            "pod_id": "" if pod.get("pod_id") in (None, "") else _identifier(pod.get("pod_id"), f"{field}.pod.pod_id"),
            "signed_by": "" if pod.get("signed_by") in (None, "") else _identifier(pod.get("signed_by"), f"{field}.pod.signed_by"),
            "signed_at": "" if pod.get("signed_at") in (None, "") else _ts_text(pod.get("signed_at"), f"{field}.pod.signed_at"),
        },
    }


def _normalize_shipments(shipments: Any) -> list[dict[str, Any]]:
    if not isinstance(shipments, list) or not shipments:
        _fail("MALFORMED_INPUT", "shipments must be a non-empty array")
    if len(shipments) > 5000:
        _fail("MALFORMED_INPUT", "shipments exceeds maximum batch size")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(shipments):
        if not _plain(raw):
            _fail("MALFORMED_INPUT", f"shipments[{index}] must be an object")
        shipment_id = _identifier(raw.get("shipment_id"), f"shipments[{index}].shipment_id")
        if shipment_id.lower() in seen:
            _fail("MALFORMED_INPUT", f"duplicate shipment id {shipment_id}")
        seen.add(shipment_id.lower())
        legs_raw = raw.get("legs")
        if not isinstance(legs_raw, list) or not legs_raw:
            _fail("MALFORMED_INPUT", f"shipment {shipment_id} must contain at least one leg")
        if len(legs_raw) > 100:
            _fail("MALFORMED_INPUT", f"shipment {shipment_id} exceeds maximum leg count")
        legs = [_normalize_leg(leg, shipment_id, leg_index) for leg_index, leg in enumerate(legs_raw)]
        result.append(
            {
                "shipment_id": shipment_id,
                "service_line": _text(raw.get("service_line"), f"shipments[{index}].service_line", maximum=80),
                "material_class": _text(raw.get("material_class"), f"shipments[{index}].material_class", maximum=120),
                "legs": legs,
            }
        )
    return sorted(result, key=lambda item: item["shipment_id"])

