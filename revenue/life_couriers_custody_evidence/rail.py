"""Deterministic synthetic custody/temperature evidence rail.

This module is deliberately provider-free.  It records evidence supplied by a
buyer-controlled integration boundary; it does not move shipments, make
clinical/regulatory decisions, or mutate carrier systems.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping


MANIFEST_SCHEMA = "life-couriers-custody-evidence.manifest.v1"
RECEIPT_SCHEMA = "life-couriers-custody-evidence.receipt.v1"
EVENT_TYPES = {
    "shipment_opened",
    "leg_declared",
    "custody_departed",
    "custody_received",
    "temperature_sample",
    "exception_opened",
    "exception_closed",
    "effect_unknown",
    "effect_reconciled",
    "shipment_closed",
}
TOP_LEVEL_KEYS = {
    "event_id",
    "shipment_id",
    "event_type",
    "occurred_at",
    "source_system",
    "source_record_id",
    "payload",
}
PAYLOAD_KEYS = {
    "shipment_opened": {"origin_party", "destination_party"},
    "leg_declared": {
        "leg_id",
        "sequence",
        "from_party",
        "to_party",
        "temp_min_c",
        "temp_max_c",
        "required_temp_samples",
    },
    "custody_departed": {"leg_id", "party"},
    "custody_received": {"leg_id", "party"},
    "temperature_sample": {"leg_id", "temp_c", "sensor_id"},
    "exception_opened": {"exception_id", "code", "leg_id"},
    "exception_closed": {"exception_id", "resolution_ref"},
    "effect_unknown": {"effect_id", "boundary", "operation_id"},
    "effect_reconciled": {"effect_id", "outcome", "evidence_ref"},
    "shipment_closed": {"decision_ref"},
}


@dataclass(frozen=True)
class IngestResult:
    status: str
    event_id: str
    detail: str = ""


@dataclass(frozen=True)
class ShipmentState:
    shipment_id: str
    status: str
    holds: tuple[dict[str, str], ...]
    leg_count: int
    event_count: int
    unresolved_effects: tuple[str, ...]
    unresolved_exceptions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "shipment_id": self.shipment_id,
            "status": self.status,
            "holds": list(self.holds),
            "leg_count": self.leg_count,
            "event_count": self.event_count,
            "unresolved_effects": list(self.unresolved_effects),
            "unresolved_exceptions": list(self.unresolved_exceptions),
        }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_int(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _require_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _hold(code: str, ref: str, detail: str) -> dict[str, str]:
    return {"code": code, "ref": ref, "detail": detail}


class EvidenceRail:
    """Append-only, replay-safe evidence collector.

    Event IDs are idempotency keys.  Exact retries collapse.  If the same key
    appears with different bytes, every variant is retained as evidence but no
    variant is applied to state; the shipment is held as ambiguous.
    """

    def __init__(self) -> None:
        self._variants: dict[str, dict[str, dict[str, Any]]] = {}

    @staticmethod
    def normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(event, Mapping):
            raise ValueError("event must be an object")
        if set(event) != TOP_LEVEL_KEYS:
            missing = sorted(TOP_LEVEL_KEYS - set(event))
            extra = sorted(set(event) - TOP_LEVEL_KEYS)
            raise ValueError(f"event keys mismatch missing={missing} extra={extra}")

        event_id = _require_string(event["event_id"], "event_id")
        shipment_id = _require_string(event["shipment_id"], "shipment_id")
        event_type = _require_string(event["event_type"], "event_type")
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported event_type {event_type!r}")
        occurred_at = _require_int(event["occurred_at"], "occurred_at")
        source_system = _require_string(event["source_system"], "source_system")
        source_record_id = _require_string(event["source_record_id"], "source_record_id")
        payload = event["payload"]
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be an object")
        expected = PAYLOAD_KEYS[event_type]
        if set(payload) != expected:
            missing = sorted(expected - set(payload))
            extra = sorted(set(payload) - expected)
            raise ValueError(f"{event_type} payload mismatch missing={missing} extra={extra}")
        payload = dict(payload)

        if event_type == "shipment_opened":
            _require_string(payload["origin_party"], "origin_party")
            _require_string(payload["destination_party"], "destination_party")
        elif event_type == "leg_declared":
            _require_string(payload["leg_id"], "leg_id")
            _require_int(payload["sequence"], "sequence", 1)
            _require_string(payload["from_party"], "from_party")
            _require_string(payload["to_party"], "to_party")
            low = _require_number(payload["temp_min_c"], "temp_min_c")
            high = _require_number(payload["temp_max_c"], "temp_max_c")
            if low > high:
                raise ValueError("temp_min_c must be <= temp_max_c")
            _require_int(payload["required_temp_samples"], "required_temp_samples", 0)
        elif event_type in {"custody_departed", "custody_received"}:
            _require_string(payload["leg_id"], "leg_id")
            _require_string(payload["party"], "party")
        elif event_type == "temperature_sample":
            _require_string(payload["leg_id"], "leg_id")
            _require_number(payload["temp_c"], "temp_c")
            _require_string(payload["sensor_id"], "sensor_id")
        elif event_type == "exception_opened":
            _require_string(payload["exception_id"], "exception_id")
            _require_string(payload["code"], "code")
            _require_string(payload["leg_id"], "leg_id")
        elif event_type == "exception_closed":
            _require_string(payload["exception_id"], "exception_id")
            _require_string(payload["resolution_ref"], "resolution_ref")
        elif event_type == "effect_unknown":
            _require_string(payload["effect_id"], "effect_id")
            _require_string(payload["boundary"], "boundary")
            _require_string(payload["operation_id"], "operation_id")
        elif event_type == "effect_reconciled":
            _require_string(payload["effect_id"], "effect_id")
            if payload["outcome"] not in {"committed", "not_committed"}:
                raise ValueError("effect_reconciled outcome must be committed or not_committed")
            _require_string(payload["evidence_ref"], "evidence_ref")
        elif event_type == "shipment_closed":
            _require_string(payload["decision_ref"], "decision_ref")

        normalized = {
            "event_id": event_id,
            "shipment_id": shipment_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "source_system": source_system,
            "source_record_id": source_record_id,
            "payload": payload,
        }
        return json.loads(_canonical_bytes(normalized).decode("utf-8"))

    def ingest(self, event: Mapping[str, Any]) -> IngestResult:
        normalized = self.normalize_event(event)
        event_id = normalized["event_id"]
        digest = _digest(normalized)
        variants = self._variants.setdefault(event_id, {})
        if digest in variants:
            return IngestResult("DUPLICATE", event_id, "exact retry collapsed")
        variants[digest] = normalized
        if len(variants) > 1:
            return IngestResult("HOLD", event_id, "event_id has conflicting payload variants")
        return IngestResult("APPLIED", event_id)

    def ingest_many(self, events: Iterable[Mapping[str, Any]]) -> list[IngestResult]:
        return [self.ingest(event) for event in events]

    def _conflicts(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for event_id in sorted(self._variants):
            variants = self._variants[event_id]
            if len(variants) <= 1:
                continue
            result.append(
                {
                    "event_id": event_id,
                    "variant_sha256": sorted(variants),
                    "shipment_ids": sorted({event["shipment_id"] for event in variants.values()}),
                }
            )
        return result

    def _usable_events(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for event_id in sorted(self._variants):
            variants = self._variants[event_id]
            if len(variants) == 1:
                result.append(next(iter(variants.values())))
        return result

    def shipment_ids(self) -> list[str]:
        shipment_ids: set[str] = set()
        for variants in self._variants.values():
            for event in variants.values():
                shipment_ids.add(event["shipment_id"])
        return sorted(shipment_ids)

    def shipment_state(self, shipment_id: str) -> ShipmentState:
        _require_string(shipment_id, "shipment_id")
        all_usable = self._usable_events()
        events = [event for event in all_usable if event["shipment_id"] == shipment_id]
        events.sort(key=lambda event: (event["occurred_at"], event["event_id"]))
        holds: list[dict[str, str]] = []

        for conflict in self._conflicts():
            if shipment_id in conflict["shipment_ids"]:
                holds.append(_hold("EVENT_ID_CONFLICT", conflict["event_id"], "same event_id has multiple payload variants"))

        source_to_ids: dict[tuple[str, str], set[str]] = {}
        source_to_shipments: dict[tuple[str, str], set[str]] = {}
        for event in all_usable:
            key = (event["source_system"], event["source_record_id"])
            source_to_ids.setdefault(key, set()).add(event["event_id"])
            source_to_shipments.setdefault(key, set()).add(event["shipment_id"])
        for key in sorted(source_to_ids):
            ids = source_to_ids[key]
            if len(ids) > 1 and shipment_id in source_to_shipments[key]:
                holds.append(_hold("SOURCE_LINEAGE_AMBIGUOUS", f"{key[0]}:{key[1]}", "one source record maps to multiple event IDs"))

        opened = [event for event in events if event["event_type"] == "shipment_opened"]
        closed = [event for event in events if event["event_type"] == "shipment_closed"]
        if len(opened) != 1:
            holds.append(_hold("SHIPMENT_OPEN_CARDINALITY", shipment_id, f"expected 1 shipment_opened, found {len(opened)}"))
        if len(closed) > 1:
            holds.append(_hold("SHIPMENT_CLOSE_CARDINALITY", shipment_id, f"expected at most 1 shipment_closed, found {len(closed)}"))

        declared: dict[str, dict[str, Any]] = {}
        declaration_time: dict[str, int] = {}
        sequence_to_leg: dict[int, str] = {}
        for event in events:
            if event["event_type"] != "leg_declared":
                continue
            p = event["payload"]
            leg_id = p["leg_id"]
            sequence = p["sequence"]
            if leg_id in declared:
                holds.append(_hold("LEG_DECLARATION_DUPLICATE", leg_id, "leg_id declared more than once"))
                continue
            if sequence in sequence_to_leg:
                holds.append(_hold("LEG_SEQUENCE_DUPLICATE", str(sequence), "multiple legs use the same sequence"))
            declared[leg_id] = p
            declaration_time[leg_id] = event["occurred_at"]
            sequence_to_leg[sequence] = leg_id

        if declared:
            expected_sequences = list(range(1, len(declared) + 1))
            actual_sequences = sorted(sequence_to_leg)
            if actual_sequences != expected_sequences:
                holds.append(_hold("LEG_SEQUENCE_GAP", shipment_id, f"expected {expected_sequences}, found {actual_sequences}"))
            ordered_legs = [declared[sequence_to_leg[seq]] for seq in actual_sequences]
            for left, right in zip(ordered_legs, ordered_legs[1:]):
                if left["to_party"] != right["from_party"]:
                    holds.append(_hold("ROUTE_DISCONTINUITY", f"{left['leg_id']}->{right['leg_id']}", "adjacent custody parties do not connect"))
            if opened:
                origin = opened[0]["payload"]["origin_party"]
                destination = opened[0]["payload"]["destination_party"]
                if ordered_legs and ordered_legs[0]["from_party"] != origin:
                    holds.append(_hold("ROUTE_ORIGIN_MISMATCH", ordered_legs[0]["leg_id"], "first leg does not start at shipment origin"))
                if ordered_legs and ordered_legs[-1]["to_party"] != destination:
                    holds.append(_hold("ROUTE_DESTINATION_MISMATCH", ordered_legs[-1]["leg_id"], "last leg does not end at shipment destination"))

        departures: dict[str, dict[str, Any]] = {}
        receipts: dict[str, dict[str, Any]] = {}
        temperatures: dict[str, list[dict[str, Any]]] = {leg_id: [] for leg_id in declared}
        exceptions_open: dict[str, dict[str, Any]] = {}
        exceptions_closed: set[str] = set()
        effects_unknown: dict[str, dict[str, Any]] = {}
        effects_reconciled: dict[str, dict[str, Any]] = {}

        for event in events:
            event_type = event["event_type"]
            p = event["payload"]
            if event_type in {"custody_departed", "custody_received", "temperature_sample", "exception_opened"}:
                leg_id = p["leg_id"]
                if leg_id not in declared:
                    holds.append(_hold("UNKNOWN_LEG_REFERENCE", event["event_id"], f"references undeclared leg {leg_id}"))
                    continue
                if event["occurred_at"] < declaration_time[leg_id]:
                    holds.append(_hold("LEG_EVENT_BEFORE_DECLARATION", event["event_id"], f"evidence predates leg declaration {leg_id}"))

            if event_type == "custody_departed":
                leg_id = p["leg_id"]
                if leg_id not in declared:
                    continue
                if leg_id in departures:
                    holds.append(_hold("DEPARTURE_DUPLICATE", leg_id, "multiple departure events"))
                else:
                    departures[leg_id] = event
                if p["party"] != declared[leg_id]["from_party"]:
                    holds.append(_hold("DEPARTURE_PARTY_MISMATCH", event["event_id"], "departure party differs from declared from_party"))
            elif event_type == "custody_received":
                leg_id = p["leg_id"]
                if leg_id not in declared:
                    continue
                if leg_id in receipts:
                    holds.append(_hold("RECEIPT_DUPLICATE", leg_id, "multiple receipt events"))
                else:
                    receipts[leg_id] = event
                if p["party"] != declared[leg_id]["to_party"]:
                    holds.append(_hold("RECEIPT_PARTY_MISMATCH", event["event_id"], "receipt party differs from declared to_party"))
            elif event_type == "temperature_sample":
                leg_id = p["leg_id"]
                if leg_id not in declared:
                    continue
                temperatures[leg_id].append(event)
                temp = float(p["temp_c"])
                low = float(declared[leg_id]["temp_min_c"])
                high = float(declared[leg_id]["temp_max_c"])
                if temp < low or temp > high:
                    holds.append(_hold("TEMPERATURE_EXCURSION", event["event_id"], f"{temp} outside [{low}, {high}]"))
            elif event_type == "exception_opened":
                exception_id = p["exception_id"]
                if exception_id in exceptions_open:
                    holds.append(_hold("EXCEPTION_ID_DUPLICATE", exception_id, "exception opened more than once"))
                else:
                    exceptions_open[exception_id] = event
            elif event_type == "exception_closed":
                exception_id = p["exception_id"]
                if exception_id not in exceptions_open:
                    holds.append(_hold("EXCEPTION_CLOSE_WITHOUT_OPEN", exception_id, "exception close has no matching open"))
                if exception_id in exceptions_closed:
                    holds.append(_hold("EXCEPTION_CLOSE_DUPLICATE", exception_id, "exception closed more than once"))
                exceptions_closed.add(exception_id)
            elif event_type == "effect_unknown":
                effect_id = p["effect_id"]
                if effect_id in effects_unknown:
                    holds.append(_hold("EFFECT_ID_DUPLICATE", effect_id, "effect_unknown appears more than once"))
                else:
                    effects_unknown[effect_id] = event
            elif event_type == "effect_reconciled":
                effect_id = p["effect_id"]
                if effect_id not in effects_unknown:
                    holds.append(_hold("EFFECT_RECONCILE_WITHOUT_UNKNOWN", effect_id, "reconciliation has no matching unknown effect"))
                if effect_id in effects_reconciled:
                    holds.append(_hold("EFFECT_RECONCILE_DUPLICATE", effect_id, "effect reconciled more than once"))
                effects_reconciled[effect_id] = event

        for leg_id in sorted(declared):
            if leg_id in departures and leg_id in receipts:
                if receipts[leg_id]["occurred_at"] < departures[leg_id]["occurred_at"]:
                    holds.append(_hold("CUSTODY_TIME_REVERSED", leg_id, "receipt occurred before departure"))

        unresolved_exceptions = sorted(set(exceptions_open) - exceptions_closed)
        unresolved_effects = sorted(set(effects_unknown) - set(effects_reconciled))

        if closed:
            close_time = closed[0]["occurred_at"]
            for event in events:
                if event["event_type"] != "shipment_closed" and event["occurred_at"] > close_time:
                    holds.append(_hold("EVIDENCE_AFTER_CLOSE", event["event_id"], "evidence timestamp is later than shipment close"))
            if not declared:
                holds.append(_hold("NO_ROUTE_LEGS", shipment_id, "closed shipment has no declared legs"))
            for leg_id in sorted(declared):
                if leg_id not in departures:
                    holds.append(_hold("MISSING_DEPARTURE", leg_id, "closed shipment lacks custody departure"))
                if leg_id not in receipts:
                    holds.append(_hold("MISSING_RECEIPT", leg_id, "closed shipment lacks custody receipt"))
                required = int(declared[leg_id]["required_temp_samples"])
                observed = len(temperatures.get(leg_id, []))
                if observed < required:
                    holds.append(_hold("MISSING_TEMPERATURE_EVIDENCE", leg_id, f"required {required}, observed {observed}"))
            for exception_id in unresolved_exceptions:
                holds.append(_hold("UNRESOLVED_EXCEPTION", exception_id, "shipment close requested with open exception"))
            for effect_id in unresolved_effects:
                holds.append(_hold("UNKNOWN_EFFECT", effect_id, "external effect remains unresolved"))

        hold_map = {_canonical_bytes(item): item for item in holds}
        normalized_holds = tuple(hold_map[key] for key in sorted(hold_map))
        if normalized_holds:
            status = "HOLD"
        elif closed:
            status = "READY_FOR_HANDOFF"
        else:
            status = "IN_PROGRESS"
        return ShipmentState(
            shipment_id=shipment_id,
            status=status,
            holds=normalized_holds,
            leg_count=len(declared),
            event_count=len(events),
            unresolved_effects=tuple(unresolved_effects),
            unresolved_exceptions=tuple(unresolved_exceptions),
        )

    def manifest(self) -> dict[str, Any]:
        variants: list[dict[str, Any]] = []
        for event_id in sorted(self._variants):
            for digest in sorted(self._variants[event_id]):
                variants.append({"sha256": digest, "event": self._variants[event_id][digest]})
        shipment_ids = self.shipment_ids()
        return {
            "schema": MANIFEST_SCHEMA,
            "event_variants": variants,
            "conflicts": self._conflicts(),
            "shipments": [self.shipment_state(shipment_id).to_dict() for shipment_id in shipment_ids],
        }

    def manifest_bytes(self) -> bytes:
        return _canonical_bytes(self.manifest())

    def receipt(self) -> dict[str, Any]:
        manifest = self.manifest()
        manifest_bytes = _canonical_bytes(manifest)
        return {
            "schema": RECEIPT_SCHEMA,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "event_variant_count": len(manifest["event_variants"]),
            "shipment_count": len(manifest["shipments"]),
            "hold_shipment_count": sum(1 for state in manifest["shipments"] if state["status"] == "HOLD"),
            "ready_shipment_count": sum(1 for state in manifest["shipments"] if state["status"] == "READY_FOR_HANDOFF"),
        }


def verify_receipt(manifest_bytes: bytes, receipt: Mapping[str, Any]) -> bool:
    if not isinstance(manifest_bytes, (bytes, bytearray)) or not isinstance(receipt, Mapping):
        return False
    if receipt.get("schema") != RECEIPT_SCHEMA:
        return False
    try:
        manifest = json.loads(bytes(manifest_bytes).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if manifest.get("schema") != MANIFEST_SCHEMA:
        return False
    if _canonical_bytes(manifest) != bytes(manifest_bytes):
        return False
    expected = hashlib.sha256(bytes(manifest_bytes)).hexdigest()
    if receipt.get("manifest_sha256") != expected:
        return False
    shipments = manifest.get("shipments")
    variants = manifest.get("event_variants")
    if not isinstance(shipments, list) or not isinstance(variants, list):
        return False
    if receipt.get("shipment_count") != len(shipments):
        return False
    if receipt.get("event_variant_count") != len(variants):
        return False
    if receipt.get("hold_shipment_count") != sum(1 for state in shipments if state.get("status") == "HOLD"):
        return False
    if receipt.get("ready_shipment_count") != sum(1 for state in shipments if state.get("status") == "READY_FOR_HANDOFF"):
        return False
    return True
