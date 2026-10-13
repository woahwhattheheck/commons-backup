"""Deterministic synthetic acceptance exercise for the evidence rail."""

from __future__ import annotations

import argparse
import json
import random
from typing import Any

from rail import EvidenceRail, verify_receipt


def _event(shipment: str, suffix: str, event_type: str, when: int, payload: dict[str, Any], *, source_id: str | None = None) -> dict[str, Any]:
    return {
        "event_id": f"{shipment}:{suffix}",
        "shipment_id": shipment,
        "event_type": event_type,
        "occurred_at": when,
        "source_system": "synthetic-tms",
        "source_record_id": source_id or f"{shipment}:{suffix}",
        "payload": payload,
    }


def build_shipment(shipment: str, base: int, fault: str | None = None, reconciled_unknown: bool = False) -> list[dict[str, Any]]:
    parties = ["origin-lab", "regional-hub", "airport-hub", "recipient-site"]
    events: list[dict[str, Any]] = [
        _event(shipment, "open", "shipment_opened", base, {"origin_party": parties[0], "destination_party": parties[-1]})
    ]
    for index in range(1, 4):
        leg = f"L{index}"
        start = base + index * 100
        events.append(
            _event(
                shipment,
                f"{leg}:declare",
                "leg_declared",
                start,
                {
                    "leg_id": leg,
                    "sequence": index,
                    "from_party": parties[index - 1],
                    "to_party": parties[index],
                    "temp_min_c": 2.0,
                    "temp_max_c": 8.0,
                    "required_temp_samples": 2,
                },
            )
        )
        events.append(_event(shipment, f"{leg}:depart", "custody_departed", start + 10, {"leg_id": leg, "party": parties[index - 1]}))
        temp1 = _event(shipment, f"{leg}:temp1", "temperature_sample", start + 20, {"leg_id": leg, "temp_c": 5.0, "sensor_id": f"S{index}"})
        temp2 = _event(shipment, f"{leg}:temp2", "temperature_sample", start + 30, {"leg_id": leg, "temp_c": 5.2, "sensor_id": f"S{index}"})
        if fault == "excursion" and index == 2:
            temp2["payload"]["temp_c"] = 11.5
        events.append(temp1)
        if not (fault == "missing_temp" and index == 2):
            events.append(temp2)
        events.append(_event(shipment, f"{leg}:receive", "custody_received", start + 40, {"leg_id": leg, "party": parties[index]}))

    if fault == "open_exception":
        events.append(_event(shipment, "exception", "exception_opened", base + 350, {"exception_id": "EX-1", "code": "HANDOFF_NOTE_PENDING", "leg_id": "L3"}))
    if fault == "unknown_effect" or reconciled_unknown:
        events.append(_event(shipment, "unknown", "effect_unknown", base + 351, {"effect_id": "FX-1", "boundary": "partner-api", "operation_id": f"op-{shipment}"}))
        if reconciled_unknown:
            events.append(_event(shipment, "reconciled", "effect_reconciled", base + 352, {"effect_id": "FX-1", "outcome": "committed", "evidence_ref": f"receipt-{shipment}"}))
    if fault == "source_ambiguity":
        original = next(event for event in events if event["event_id"].endswith("L2:temp1"))
        duplicate = json.loads(json.dumps(original))
        duplicate["event_id"] = f"{shipment}:L2:temp1-shadow"
        events.append(duplicate)
    if fault == "event_id_conflict":
        original = next(event for event in events if event["event_id"].endswith("L2:temp1"))
        conflicting = json.loads(json.dumps(original))
        conflicting["payload"]["temp_c"] = 6.7
        events.append(conflicting)

    events.append(_event(shipment, "close", "shipment_closed", base + 400, {"decision_ref": f"operator-{shipment}"}))
    # Exact retry: every fixture includes one harmless duplicate.
    events.append(json.loads(json.dumps(events[1])))
    return events


def run_acceptance() -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    # 100 valid shipments. Ten exercise resolved UNKNOWN_EFFECT semantics.
    for i in range(100):
        shipment = f"CLEAN-{i:03d}"
        events.extend(build_shipment(shipment, i * 1000, reconciled_unknown=(i % 10 == 0)))
    faults = ["missing_temp", "excursion", "open_exception", "unknown_effect", "source_ambiguity"]
    for fault_index, fault in enumerate(faults):
        for j in range(4):
            shipment = f"HOLD-{fault_index}-{j}"
            events.extend(build_shipment(shipment, 200000 + fault_index * 10000 + j * 1000, fault=fault))

    rng = random.Random(913443)
    rng.shuffle(events)
    rail = EvidenceRail()
    results = rail.ingest_many(events)
    receipt = rail.receipt()
    manifest_bytes = rail.manifest_bytes()
    states = [rail.shipment_state(shipment_id) for shipment_id in rail.shipment_ids()]
    metrics = {
        "shipments": len(states),
        "ready": sum(state.status == "READY_FOR_HANDOFF" for state in states),
        "hold": sum(state.status == "HOLD" for state in states),
        "duplicate_retries": sum(result.status == "DUPLICATE" for result in results),
        "conflict_results": sum(result.status == "HOLD" for result in results),
        "receipt_valid": verify_receipt(manifest_bytes, receipt),
        "manifest_sha256": receipt["manifest_sha256"],
    }
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    metrics = run_acceptance()
    print(json.dumps(metrics, sort_keys=True))
    if args.require_pass:
        expected = {"shipments": 120, "ready": 100, "hold": 20, "receipt_valid": True}
        for key, value in expected.items():
            if metrics[key] != value:
                return 1
        if metrics["duplicate_retries"] != 120:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
