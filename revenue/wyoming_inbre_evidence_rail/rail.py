"""Deterministic synthetic evidence rail for the Wyoming INBRE product specification.

The module is intentionally side-effect free. It reconciles approved synthetic
allocation, amendment, transfer, trainee-appointment, resource-use, and
report-evidence records into a canonical receipt. It never selects trainees or
projects, moves funds, makes compliance decisions, or calls external systems.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
MAX_EVENTS = 100_000
MAX_TEXT = 128
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
PERIOD_RE = re.compile(r"^\d{4}-(?:Q[1-4]|P\d{2}|FY\d{2,4})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

FORBIDDEN_PII_KEYS = frozenset(
    {
        "name",
        "first_name",
        "last_name",
        "full_name",
        "email",
        "phone",
        "address",
        "ssn",
        "social_security_number",
        "dob",
        "date_of_birth",
        "student_id",
        "participant_id",
        "mrn",
    }
)

SCHEMAS: dict[str, frozenset[str]] = {
    "allocation": frozenset(
        {
            "event_id",
            "kind",
            "allocation_id",
            "campus_id",
            "project_id",
            "period",
            "amount_cents",
        }
    ),
    "allocation_amendment": frozenset(
        {"event_id", "kind", "amendment_id", "allocation_id", "delta_cents"}
    ),
    "transfer": frozenset(
        {
            "event_id",
            "kind",
            "transfer_id",
            "from_allocation_id",
            "to_allocation_id",
            "amount_cents",
        }
    ),
    "trainee_appointment": frozenset(
        {
            "event_id",
            "kind",
            "appointment_id",
            "synthetic_person_id",
            "allocation_id",
            "campus_id",
            "project_id",
            "period",
            "start_date",
            "end_date",
        }
    ),
    "resource_use": frozenset(
        {
            "event_id",
            "kind",
            "use_id",
            "allocation_id",
            "campus_id",
            "project_id",
            "period",
            "resource_id",
            "units_milli",
        }
    ),
    "report_evidence": frozenset(
        {
            "event_id",
            "kind",
            "evidence_id",
            "allocation_id",
            "campus_id",
            "project_id",
            "period",
            "evidence_kind",
            "source_sha256",
        }
    ),
}

ID_FIELDS = frozenset(
    {
        "event_id",
        "allocation_id",
        "amendment_id",
        "transfer_id",
        "from_allocation_id",
        "to_allocation_id",
        "appointment_id",
        "synthetic_person_id",
        "campus_id",
        "project_id",
        "use_id",
        "resource_id",
        "evidence_id",
        "evidence_kind",
    }
)


class RailError(ValueError):
    """Fail-closed domain error with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise RailError(code, message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _root(items: Iterable[Any]) -> str:
    serialized = [canonical_json(item) for item in items]
    serialized.sort()
    return sha256_text("\n".join(serialized))


def _plain_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_EVENT", f"{field} must be an object")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        _fail("INVALID_EVENT", f"{field} must be text")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_TEXT:
        _fail("INVALID_EVENT", f"{field} must contain 1-{MAX_TEXT} characters")
    return cleaned


def _identifier(value: Any, field: str) -> str:
    cleaned = _text(value, field)
    if not ID_RE.fullmatch(cleaned):
        _fail("INVALID_EVENT", f"{field} is not a canonical identifier")
    return cleaned


def _integer(value: Any, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("INVALID_EVENT", f"{field} must be an integer")
    if positive and value <= 0:
        _fail("INVALID_EVENT", f"{field} must be greater than zero")
    if abs(value) > 10**15:
        _fail("INVALID_EVENT", f"{field} exceeds the bounded integer range")
    return value


def _iso_date(value: Any, field: str) -> str:
    cleaned = _text(value, field)
    try:
        parsed = date.fromisoformat(cleaned)
    except ValueError:
        _fail("INVALID_EVENT", f"{field} must be a real ISO calendar date")
    if parsed.isoformat() != cleaned:
        _fail("INVALID_EVENT", f"{field} must use YYYY-MM-DD form")
    return cleaned


def _period(value: Any, field: str = "period") -> str:
    cleaned = _text(value, field)
    if not PERIOD_RE.fullmatch(cleaned):
        _fail("INVALID_EVENT", f"{field} must use YYYY-Qn, YYYY-Pnn, or YYYY-FYnn form")
    return cleaned


def _reject_nonscalar(value: Any, field: str) -> None:
    if isinstance(value, (Mapping, list, tuple, set)):
        _fail("NESTED_DATA_FORBIDDEN", f"{field} must be a scalar; nested payloads are forbidden")
    if value is None or isinstance(value, float):
        _fail("INVALID_EVENT", f"{field} uses an unsupported scalar type")


def normalize_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    event = _plain_mapping(raw, "event")
    for key in event:
        if not isinstance(key, str):
            _fail("INVALID_EVENT", "event keys must be text")
        if key.lower() in FORBIDDEN_PII_KEYS:
            _fail("PII_FORBIDDEN", f"PII-shaped field {key!r} is forbidden; use synthetic identifiers only")
        _reject_nonscalar(event[key], key)

    kind = _text(event.get("kind"), "kind")
    allowed = SCHEMAS.get(kind)
    if allowed is None:
        _fail("UNKNOWN_KIND", f"unsupported event kind {kind!r}")
    actual = frozenset(event.keys())
    missing = allowed - actual
    extra = actual - allowed
    if missing:
        _fail("MISSING_FIELD", f"{kind} missing fields: {', '.join(sorted(missing))}")
    if extra:
        _fail("UNKNOWN_FIELD", f"{kind} contains unknown fields: {', '.join(sorted(extra))}")

    normalized: dict[str, Any] = {"kind": kind}
    for key in sorted(allowed - {"kind"}):
        value = event[key]
        if key in ID_FIELDS:
            normalized[key] = _identifier(value, key)
        elif key == "period":
            normalized[key] = _period(value)
        elif key in {"start_date", "end_date"}:
            normalized[key] = _iso_date(value, key)
        elif key == "source_sha256":
            digest = _text(value, key).lower()
            if not SHA256_RE.fullmatch(digest):
                _fail("INVALID_EVENT", "source_sha256 must be 64 lowercase hexadecimal characters")
            normalized[key] = digest
        elif key == "delta_cents":
            normalized[key] = _integer(value, key)
        elif key in {"amount_cents", "units_milli"}:
            normalized[key] = _integer(value, key, positive=True)
        else:
            _fail("INVALID_SCHEMA", f"schema normalizer missing field {key}")

    if kind == "allocation" and normalized["amount_cents"] <= 0:
        _fail("INVALID_EVENT", "allocation amount_cents must be positive")
    if kind == "trainee_appointment" and normalized["start_date"] > normalized["end_date"]:
        _fail("INVALID_EVENT", "appointment start_date cannot follow end_date")
    return {key: normalized[key] for key in sorted(normalized)}


def _scope_matches(event: Mapping[str, Any], allocation: Mapping[str, Any]) -> bool:
    return all(event[field] == allocation[field] for field in ("campus_id", "project_id", "period"))


def _quarantine(event: Mapping[str, Any], code: str) -> dict[str, str]:
    return {"event_id": str(event["event_id"]), "kind": str(event["kind"]), "code": code}


def reconcile(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reconcile an event batch into a canonical, order-invariant receipt manifest."""

    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        _fail("INVALID_BATCH", "events must be a finite sequence")
    if len(events) > MAX_EVENTS:
        _fail("BATCH_TOO_LARGE", f"event count exceeds {MAX_EVENTS}")

    by_event_id: dict[str, dict[str, Any]] = {}
    replay_collapsed = 0
    for raw in events:
        normalized = normalize_event(raw)
        event_id = normalized["event_id"]
        previous = by_event_id.get(event_id)
        if previous is None:
            by_event_id[event_id] = normalized
        elif previous == normalized:
            replay_collapsed += 1
        else:
            _fail("IDEMPOTENCY_CONFLICT", f"event_id {event_id} was reused for different content")

    unique_events = sorted(by_event_id.values(), key=lambda item: item["event_id"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in unique_events:
        grouped[event["kind"]].append(event)

    allocations: dict[str, dict[str, Any]] = {}
    for event in grouped["allocation"]:
        allocation_id = event["allocation_id"]
        if allocation_id in allocations:
            _fail("DUPLICATE_ALLOCATION_ID", f"allocation_id {allocation_id} appears in multiple events")
        allocations[allocation_id] = {
            "allocation_id": allocation_id,
            "campus_id": event["campus_id"],
            "project_id": event["project_id"],
            "period": event["period"],
            "base_cents": event["amount_cents"],
            "amendment_cents": 0,
            "transferred_in_cents": 0,
            "transferred_out_cents": 0,
        }

    seen_amendments: set[str] = set()
    for event in grouped["allocation_amendment"]:
        amendment_id = event["amendment_id"]
        if amendment_id in seen_amendments:
            _fail("DUPLICATE_AMENDMENT_ID", f"amendment_id {amendment_id} appears more than once")
        seen_amendments.add(amendment_id)
        allocation = allocations.get(event["allocation_id"])
        if allocation is None:
            _fail("UNKNOWN_ALLOCATION", f"amendment references unknown allocation {event['allocation_id']}")
        allocation["amendment_cents"] += event["delta_cents"]

    for allocation in allocations.values():
        funded = allocation["base_cents"] + allocation["amendment_cents"]
        if funded < 0:
            _fail("NEGATIVE_AUTHORITY", f"amendments make {allocation['allocation_id']} negative")
        allocation["funded_cents"] = funded

    seen_transfers: set[str] = set()
    for event in grouped["transfer"]:
        transfer_id = event["transfer_id"]
        if transfer_id in seen_transfers:
            _fail("DUPLICATE_TRANSFER_ID", f"transfer_id {transfer_id} appears more than once")
        seen_transfers.add(transfer_id)
        source = allocations.get(event["from_allocation_id"])
        target = allocations.get(event["to_allocation_id"])
        if source is None or target is None:
            _fail("UNKNOWN_ALLOCATION", f"transfer {transfer_id} references an unknown allocation")
        if source is target:
            _fail("INVALID_TRANSFER", f"transfer {transfer_id} cannot transfer to the same allocation")
        amount = event["amount_cents"]
        source["transferred_out_cents"] += amount
        target["transferred_in_cents"] += amount

    for allocation in allocations.values():
        allocation["balance_cents"] = (
            allocation["funded_cents"]
            + allocation["transferred_in_cents"]
            - allocation["transferred_out_cents"]
        )
        if allocation["balance_cents"] < 0:
            _fail("TRANSFER_OVERDRAW", f"transfers overdraw {allocation['allocation_id']}")

    appointments: list[dict[str, Any]] = []
    seen_appointment_ids: set[str] = set()
    by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in grouped["trainee_appointment"]:
        appointment_id = event["appointment_id"]
        if appointment_id in seen_appointment_ids:
            _fail("DUPLICATE_APPOINTMENT_ID", f"appointment_id {appointment_id} appears more than once")
        seen_appointment_ids.add(appointment_id)
        allocation = allocations.get(event["allocation_id"])
        if allocation is None:
            _fail("UNKNOWN_ALLOCATION", f"appointment {appointment_id} references an unknown allocation")
        if not _scope_matches(event, allocation):
            _fail("APPOINTMENT_SCOPE_MISMATCH", f"appointment {appointment_id} disagrees with allocation scope")
        appointment = {
            key: event[key]
            for key in (
                "appointment_id",
                "synthetic_person_id",
                "allocation_id",
                "campus_id",
                "project_id",
                "period",
                "start_date",
                "end_date",
            )
        }
        appointments.append(appointment)
        by_person[event["synthetic_person_id"]].append(appointment)

    for person_id, person_appointments in by_person.items():
        ordered = sorted(person_appointments, key=lambda item: (item["start_date"], item["end_date"], item["appointment_id"]))
        previous: dict[str, Any] | None = None
        for current in ordered:
            if previous is not None and current["start_date"] <= previous["end_date"]:
                _fail(
                    "APPOINTMENT_OVERLAP",
                    f"synthetic person {person_id} has overlapping appointments {previous['appointment_id']} and {current['appointment_id']}",
                )
            previous = current

    mapped_resource_uses: list[dict[str, Any]] = []
    mapped_evidence: list[dict[str, Any]] = []
    quarantines: list[dict[str, str]] = []

    seen_use_ids: set[str] = set()
    for event in grouped["resource_use"]:
        use_id = event["use_id"]
        if use_id in seen_use_ids:
            _fail("DUPLICATE_USE_ID", f"use_id {use_id} appears more than once")
        seen_use_ids.add(use_id)
        allocation = allocations.get(event["allocation_id"])
        if allocation is None:
            quarantines.append(_quarantine(event, "RESOURCE_UNKNOWN_ALLOCATION"))
            continue
        if not _scope_matches(event, allocation):
            quarantines.append(_quarantine(event, "RESOURCE_SCOPE_MISMATCH"))
            continue
        mapped_resource_uses.append(
            {
                key: event[key]
                for key in (
                    "use_id",
                    "allocation_id",
                    "campus_id",
                    "project_id",
                    "period",
                    "resource_id",
                    "units_milli",
                )
            }
        )

    seen_evidence_ids: set[str] = set()
    for event in grouped["report_evidence"]:
        evidence_id = event["evidence_id"]
        if evidence_id in seen_evidence_ids:
            _fail("DUPLICATE_EVIDENCE_ID", f"evidence_id {evidence_id} appears more than once")
        seen_evidence_ids.add(evidence_id)
        allocation = allocations.get(event["allocation_id"])
        if allocation is None:
            quarantines.append(_quarantine(event, "EVIDENCE_UNKNOWN_ALLOCATION"))
            continue
        if not _scope_matches(event, allocation):
            quarantines.append(_quarantine(event, "EVIDENCE_SCOPE_MISMATCH"))
            continue
        mapped_evidence.append(
            {
                key: event[key]
                for key in (
                    "evidence_id",
                    "allocation_id",
                    "campus_id",
                    "project_id",
                    "period",
                    "evidence_kind",
                    "source_sha256",
                )
            }
        )

    allocations_list = sorted(allocations.values(), key=lambda item: item["allocation_id"])
    appointments.sort(key=lambda item: item["appointment_id"])
    mapped_resource_uses.sort(key=lambda item: item["use_id"])
    mapped_evidence.sort(key=lambda item: item["evidence_id"])
    quarantines.sort(key=lambda item: (item["event_id"], item["code"]))

    funded_total = sum(item["funded_cents"] for item in allocations_list)
    balance_total = sum(item["balance_cents"] for item in allocations_list)
    if funded_total != balance_total:
        _fail("INTERNAL_TOTAL_MISMATCH", "transfer accounting failed to preserve network total")

    event_digests = [sha256_text(canonical_json(event)) for event in unique_events]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "product": "WYOMING_INBRE_CAMPUS_AWARD_TRAINEE_COMPUTE_EVIDENCE_RAIL",
        "authority": "SYNTHETIC_INTERNAL_DELIVERY_CORE_ONLY",
        "input_records": len(events),
        "unique_events": len(unique_events),
        "replay_collapsed": replay_collapsed,
        "campuses": sorted({item["campus_id"] for item in allocations_list}),
        "counts": {
            "allocations": len(allocations_list),
            "amendments": len(grouped["allocation_amendment"]),
            "transfers": len(grouped["transfer"]),
            "appointments": len(appointments),
            "resource_use_mapped": len(mapped_resource_uses),
            "report_evidence_mapped": len(mapped_evidence),
            "quarantined": len(quarantines),
        },
        "money": {
            "base_authorized_cents": sum(item["base_cents"] for item in allocations_list),
            "amendment_delta_cents": sum(item["amendment_cents"] for item in allocations_list),
            "network_authorized_cents": funded_total,
            "network_balance_cents": balance_total,
            "transfer_volume_cents": sum(item["amount_cents"] for item in grouped["transfer"]),
        },
        "roots": {
            "events_sha256": sha256_text("\n".join(sorted(event_digests))),
            "allocation_state_sha256": _root(allocations_list),
            "appointments_sha256": _root(appointments),
            "resource_use_sha256": _root(mapped_resource_uses),
            "report_evidence_sha256": _root(mapped_evidence),
            "quarantine_sha256": _root(quarantines),
        },
        "quarantines": quarantines,
    }
    manifest["receipt_sha256"] = sha256_text(canonical_json(manifest))
    return manifest


def verify_receipt(manifest: Mapping[str, Any]) -> bool:
    if not isinstance(manifest, Mapping):
        return False
    supplied = manifest.get("receipt_sha256")
    if not isinstance(supplied, str) or not SHA256_RE.fullmatch(supplied):
        return False
    unsigned = deepcopy(dict(manifest))
    unsigned.pop("receipt_sha256", None)
    return sha256_text(canonical_json(unsigned)) == supplied
