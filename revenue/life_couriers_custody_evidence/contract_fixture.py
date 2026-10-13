from __future__ import annotations

import base64
import hashlib
import hmac
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from contract_gate import DetachedSigner, canonical_manifest_bytes, sign_manifest

SERVICE_LINES = (
    "radiopharma",
    "life_sciences",
    "stem_cell_onboard",
    "direct_to_patient",
    "pharma_freight",
    "emergency_logistics",
)
DEFECTS = (
    "CUSTODY_GAP",
    "PACKOUT_TEMPERATURE_MISMATCH",
    "DOCUMENT_INVALID",
    "WINDOW_BREACH_UNACKNOWLEDGED",
    "LEG_GRAPH_INVALID",
    "RECIPIENT_POD_INCOMPLETE",
)


def _z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _leg(shipment_number: int, sequence: int, start: datetime) -> dict[str, Any]:
    pickup = start + timedelta(hours=(sequence - 1) * 2)
    handoff = pickup + timedelta(minutes=75)
    prior_custodian = f"CUST-{shipment_number:04d}-{sequence - 1}" if sequence > 1 else f"ORIGIN-{shipment_number:04d}"
    next_custodian = f"CUST-{shipment_number:04d}-{sequence}"
    leg_id = f"LC-{shipment_number:04d}-L{sequence}"
    packout = f"PACK-{shipment_number:04d}-{sequence}"
    return {
        "leg_id": leg_id,
        "sequence": sequence,
        "predecessor_leg_id": None if sequence == 1 else f"LC-{shipment_number:04d}-L{sequence - 1}",
        "pickup_at": _z(pickup),
        "handoff_at": _z(handoff),
        "courier_id": f"COURIER-{(shipment_number + sequence) % 31:02d}",
        "custodian_from": prior_custodian,
        "custodian_to": next_custodian,
        "lane_id": f"LANE-{shipment_number % 17:02d}",
        "window_start": _z(pickup - timedelta(minutes=20)),
        "window_end": _z(handoff + timedelta(minutes=20)),
        "packout_id": packout,
        "sensor": {
            "sensor_id": f"SENSOR-{shipment_number:04d}-{sequence}",
            "packout_id": packout,
            "min_temp_c": "2",
            "max_temp_c": "8",
            "observed_min_c": "3.1",
            "observed_max_c": "6.8",
        },
        "documents": [
            {
                "document_id": f"DOC-{shipment_number:04d}-{sequence}",
                "type": "declared-permit",
                "valid_from": _z(pickup - timedelta(days=30)),
                "valid_until": _z(pickup + timedelta(days=30)),
            }
        ],
        "incidents": [],
        "recipient": {
            "recipient_id": next_custodian,
            "received_at": _z(handoff + timedelta(minutes=2)),
        },
        "pod": {
            "pod_id": f"POD-{shipment_number:04d}-{sequence}",
            "signed_by": next_custodian,
            "signed_at": _z(handoff + timedelta(minutes=3)),
        },
    }


def build_acceptance_fixture() -> tuple[list[dict[str, Any]], dict[str, str]]:
    shipments: list[dict[str, Any]] = []
    expected_holds: dict[str, str] = {}
    base = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    for index in range(240):
        number = index + 1
        shipment_id = f"LC-{number:04d}"
        service_line = SERVICE_LINES[index % len(SERVICE_LINES)]
        start = base + timedelta(hours=index * 4)
        shipment = {
            "shipment_id": shipment_id,
            "service_line": service_line,
            "material_class": f"DECLARED-{service_line.upper()}",
            "legs": [_leg(number, sequence, start) for sequence in (1, 2, 3)],
        }
        if index < 48:
            defect = DEFECTS[index // 8]
            target = shipment["legs"][2]
            if defect == "CUSTODY_GAP":
                target["custodian_from"] = ""
            elif defect == "PACKOUT_TEMPERATURE_MISMATCH":
                target["sensor"]["packout_id"] = f"WRONG-{number:04d}"
            elif defect == "DOCUMENT_INVALID":
                pickup = datetime.fromisoformat(target["pickup_at"].replace("Z", "+00:00"))
                target["documents"][0]["valid_until"] = _z(pickup - timedelta(minutes=1))
            elif defect == "WINDOW_BREACH_UNACKNOWLEDGED":
                handoff = datetime.fromisoformat(target["handoff_at"].replace("Z", "+00:00"))
                target["window_end"] = _z(handoff - timedelta(minutes=1))
            elif defect == "LEG_GRAPH_INVALID":
                target["predecessor_leg_id"] = f"ORPHAN-{number:04d}"
            elif defect == "RECIPIENT_POD_INCOMPLETE":
                target["pod"]["signed_by"] = ""
            expected_holds[shipment_id] = defect
        shipments.append(shipment)
    return shipments, expected_holds


class SyntheticFixtureSigner:
    signer_id = "SYNTHETIC-ACCEPTANCE"
    algorithm = "HMAC-SHA256-SYNTHETIC-ONLY"
    _key = b"public-test-fixture-key-not-for-production"

    @staticmethod
    def sign_digest(digest: bytes) -> str:
        return base64.b64encode(hmac.new(SyntheticFixtureSigner._key, digest, hashlib.sha256).digest()).decode("ascii")


def run_acceptance() -> dict[str, Any]:
    shipments, expected_holds = build_acceptance_fixture()
    signer = DetachedSigner(SyntheticFixtureSigner.signer_id, SyntheticFixtureSigner.algorithm, SyntheticFixtureSigner.sign_digest)
    first = sign_manifest(deepcopy(shipments), signer)
    second = sign_manifest(deepcopy(shipments), signer)
    third = sign_manifest(deepcopy(shipments), signer)
    if canonical_manifest_bytes(first) != canonical_manifest_bytes(second) or canonical_manifest_bytes(first) != canonical_manifest_bytes(third):
        raise AssertionError("three acceptance reruns were not byte-identical")
    summary = first["summary"]
    if summary["shipment_count"] != 240 or summary["complete_shipments"] != 192 or summary["held_shipments"] != 48:
        raise AssertionError(f"unexpected acceptance counts: {summary}")
    shipment_by_id = {row["shipment_id"]: row for row in first["shipments"]}
    for shipment_id, code in expected_holds.items():
        row = shipment_by_id[shipment_id]
        if row["status"] != "HOLD" or row["codes"] != [code]:
            raise AssertionError(f"{shipment_id} expected only {code}, got {row}")
    for shipment_id, row in shipment_by_id.items():
        if shipment_id not in expected_holds and row["status"] != "EVIDENCE_COMPLETE":
            raise AssertionError(f"valid fixture shipment held unexpectedly: {shipment_id} {row['codes']}")
    return first


if __name__ == "__main__":
    print(canonical_manifest_bytes(run_acceptance()).decode("utf-8"), end="")
