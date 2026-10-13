"""Deterministic 500-record synthetic acceptance fixture and checker."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

try:
    from .rail import RailError, canonical_json, reconcile, verify_receipt
except ImportError:  # direct-file execution for clean-room handoff
    from rail import RailError, canonical_json, reconcile, verify_receipt


EXPECTED_COUNTS = {
    "allocations": 100,
    "amendments": 50,
    "transfers": 95,
    "appointments": 95,
    "resource_use_mapped": 95,
    "report_evidence_mapped": 50,
    "quarantined": 10,
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _allocation_scope(index: int) -> tuple[str, str, str, str]:
    campus = f"CAMPUS-{((index - 1) % 10) + 1:02d}"
    project = f"PROJECT-{index:03d}"
    period = "2026-Q3"
    allocation = f"ALLOC-{index:03d}"
    return campus, project, period, allocation


def generate_acceptance_fixture() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for index in range(1, 101):
        campus, project, period, allocation = _allocation_scope(index)
        events.append(
            {
                "event_id": f"EV-ALLOC-{index:03d}",
                "kind": "allocation",
                "allocation_id": allocation,
                "campus_id": campus,
                "project_id": project,
                "period": period,
                "amount_cents": 1_000_000 + index * 100,
            }
        )

    for index in range(1, 51):
        _, _, _, allocation = _allocation_scope(index)
        events.append(
            {
                "event_id": f"EV-AMEND-{index:03d}",
                "kind": "allocation_amendment",
                "amendment_id": f"AMEND-{index:03d}",
                "allocation_id": allocation,
                "delta_cents": 10_000,
            }
        )

    for index in range(1, 96):
        _, _, _, source = _allocation_scope(index)
        _, _, _, target = _allocation_scope(index + 1)
        events.append(
            {
                "event_id": f"EV-XFER-{index:03d}",
                "kind": "transfer",
                "transfer_id": f"XFER-{index:03d}",
                "from_allocation_id": source,
                "to_allocation_id": target,
                "amount_cents": 1_000,
            }
        )

    for index in range(1, 96):
        campus, project, period, allocation = _allocation_scope(index)
        events.append(
            {
                "event_id": f"EV-APPT-{index:03d}",
                "kind": "trainee_appointment",
                "appointment_id": f"APPT-{index:03d}",
                "synthetic_person_id": f"SYNTH-PERSON-{index:03d}",
                "allocation_id": allocation,
                "campus_id": campus,
                "project_id": project,
                "period": period,
                "start_date": "2026-07-01",
                "end_date": "2026-09-30",
            }
        )

    for index in range(1, 101):
        campus, project, period, allocation = _allocation_scope(index)
        if index % 20 == 0:
            allocation = f"ALLOC-MISSING-{index:03d}"
        events.append(
            {
                "event_id": f"EV-USE-{index:03d}",
                "kind": "resource_use",
                "use_id": f"USE-{index:03d}",
                "allocation_id": allocation,
                "campus_id": campus,
                "project_id": project,
                "period": period,
                "resource_id": f"RESOURCE-{((index - 1) % 7) + 1:02d}",
                "units_milli": 1_000 + index,
            }
        )

    for index in range(1, 56):
        campus, project, period, allocation = _allocation_scope(index)
        if index % 11 == 0:
            project = "PROJECT-MISMATCH"
        events.append(
            {
                "event_id": f"EV-EVID-{index:03d}",
                "kind": "report_evidence",
                "evidence_id": f"EVID-{index:03d}",
                "allocation_id": allocation,
                "campus_id": campus,
                "project_id": project,
                "period": period,
                "evidence_kind": "SYNTHETIC-PROGRESS-POINTER",
                "source_sha256": _sha(f"synthetic-evidence-{index:03d}"),
            }
        )

    assert len(events) == 495
    for source_index in (0, 100, 200, 300, 400):
        events.append(deepcopy(events[source_index]))
    assert len(events) == 500
    return events


def check_acceptance(events: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    batch = list(events) if events is not None else generate_acceptance_fixture()
    manifest = reconcile(batch)

    failures: list[str] = []
    if len(batch) != 500:
        failures.append(f"input count {len(batch)} != 500")
    if manifest["unique_events"] != 495:
        failures.append(f"unique event count {manifest['unique_events']} != 495")
    if manifest["replay_collapsed"] != 5:
        failures.append(f"replay collapse count {manifest['replay_collapsed']} != 5")
    if manifest["campuses"] != [f"CAMPUS-{index:02d}" for index in range(1, 11)]:
        failures.append("fixture does not span exactly the ten synthetic campuses")
    if manifest["counts"] != EXPECTED_COUNTS:
        failures.append(f"count contract mismatch: {manifest['counts']!r}")
    if manifest["money"]["network_authorized_cents"] != manifest["money"]["network_balance_cents"]:
        failures.append("network transfer total was not preserved")
    if not verify_receipt(manifest):
        failures.append("receipt self-verification failed")

    reverse_manifest = reconcile(list(reversed(batch)))
    if reverse_manifest["receipt_sha256"] != manifest["receipt_sha256"]:
        failures.append("order-invariant replay produced a different receipt")

    expected_quarantine_codes = {
        "RESOURCE_UNKNOWN_ALLOCATION": 5,
        "EVIDENCE_SCOPE_MISMATCH": 5,
    }
    actual_codes: dict[str, int] = {}
    for row in manifest["quarantines"]:
        actual_codes[row["code"]] = actual_codes.get(row["code"], 0) + 1
    if actual_codes != expected_quarantine_codes:
        failures.append(f"quarantine contract mismatch: {actual_codes!r}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "fixture_records": len(batch),
        "manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-fixture", type=Path)
    parser.add_argument("--write-receipt", type=Path)
    parser.add_argument("--verify-receipt", type=Path)
    args = parser.parse_args(argv)

    if args.verify_receipt:
        payload = json.loads(args.verify_receipt.read_text(encoding="utf-8"))
        manifest = payload.get("manifest", payload)
        valid = verify_receipt(manifest)
        print(json.dumps({"valid": valid}, sort_keys=True))
        return 0 if valid else 2

    fixture = generate_acceptance_fixture()
    result = check_acceptance(fixture)
    if args.write_fixture:
        args.write_fixture.write_text(canonical_json(fixture) + "\n", encoding="utf-8")
    if args.write_receipt:
        args.write_receipt.write_text(canonical_json(result) + "\n", encoding="utf-8")
    print(canonical_json({
        "status": result["status"],
        "fixture_records": result["fixture_records"],
        "receipt_sha256": result["manifest"]["receipt_sha256"],
        "counts": result["manifest"]["counts"],
        "failures": result["failures"],
    }))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
