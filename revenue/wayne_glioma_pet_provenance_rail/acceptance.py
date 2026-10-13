"""Deterministic 100-episode synthetic acceptance fixture for the Wayne provenance rail."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

try:
    from .rail import canonical_json, reconcile, verify_receipt
except ImportError:  # direct-file clean-room execution
    from rail import canonical_json, reconcile, verify_receipt


EXPECTED_COUNTS = {
    "tracer_batches": 105,
    "dose_receipts_mapped": 100,
    "acquisitions_mapped": 100,
    "scan_qc_mapped": 100,
    "map_versions_mapped": 110,
    "handoffs_mapped": 100,
    "quarantined": 25,
}
EXPECTED_QUARANTINES = {
    "ACQUISITION_CROSS_SUBJECT": 5,
    "MAP_UNAVAILABLE_QC": 5,
    "MAP_VERSION_AMBIGUOUS": 10,
    "HANDOFF_SUPERSEDED_MAP": 5,
}


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _episode_ids(index: int) -> dict[str, str]:
    return {
        "subject": f"SYNTH-SUBJECT-{index:03d}",
        "protocol": "SYNTH-PROTOCOL-R01CA309136",
        "batch_r1": f"SYNTH-BATCH-{index:03d}-R1",
        "batch_r2": f"SYNTH-BATCH-{index:03d}-R2",
        "dose": f"SYNTH-DOSE-RECEIPT-{index:03d}",
        "acq": f"SYNTH-PETCT-ACQ-{index:03d}",
        "qc": f"SYNTH-SCAN-QC-{index:03d}",
        "map1": f"SYNTH-MAP-{index:03d}-V1",
        "map2": f"SYNTH-MAP-{index:03d}-V2",
        "handoff": f"SYNTH-HANDOFF-{index:03d}",
    }


def generate_acceptance_fixture() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for index in range(1, 101):
        ids = _episode_ids(index)

        events.append(
            {
                "event_id": f"EV-BATCH-{index:03d}-R1",
                "kind": "tracer_batch",
                "batch_id": ids["batch_r1"],
                "protocol_id": ids["protocol"],
                "synthesis_run_id": f"SYNTH-SYNTHESIS-{index:03d}-R1",
                "batch_revision": 1,
                "supersedes_batch_id": "NONE",
                "release_evidence_sha256": _sha(f"release-{index:03d}-r1"),
            }
        )
        batch_for_dose = ids["batch_r1"]
        if index <= 5:
            events.append(
                {
                    "event_id": f"EV-BATCH-{index:03d}-R2",
                    "kind": "tracer_batch",
                    "batch_id": ids["batch_r2"],
                    "protocol_id": ids["protocol"],
                    "synthesis_run_id": f"SYNTH-SYNTHESIS-{index:03d}-R2",
                    "batch_revision": 2,
                    "supersedes_batch_id": ids["batch_r1"],
                    "release_evidence_sha256": _sha(f"release-{index:03d}-r2"),
                }
            )
            batch_for_dose = ids["batch_r2"]

        events.append(
            {
                "event_id": f"EV-DOSE-{index:03d}",
                "kind": "dose_receipt",
                "dose_receipt_id": ids["dose"],
                "synthetic_subject_id": ids["subject"],
                "batch_id": batch_for_dose,
                "protocol_id": ids["protocol"],
                "administration_record_sha256": _sha(f"administration-record-{index:03d}"),
            }
        )
        events.append(
            {
                "event_id": f"EV-ACQ-{index:03d}",
                "kind": "acquisition",
                "acquisition_id": ids["acq"],
                "synthetic_subject_id": ids["subject"],
                "dose_receipt_id": ids["dose"],
                "protocol_id": ids["protocol"],
                "scanner_id": f"SYNTH-SCANNER-{((index - 1) % 4) + 1:02d}",
                "acquisition_evidence_sha256": _sha(f"acquisition-{index:03d}"),
                "acquisition_label": "DELAYED" if index % 25 == 0 else "PLANNED",
            }
        )
        events.append(
            {
                "event_id": f"EV-QC-{index:03d}",
                "kind": "scan_qc",
                "qc_id": ids["qc"],
                "synthetic_subject_id": ids["subject"],
                "acquisition_id": ids["acq"],
                "qc_evidence_sha256": _sha(f"scan-qc-{index:03d}"),
            }
        )
        events.append(
            {
                "event_id": f"EV-MAP-{index:03d}-V1",
                "kind": "map_version",
                "map_id": ids["map1"],
                "synthetic_subject_id": ids["subject"],
                "acquisition_id": ids["acq"],
                "qc_id": ids["qc"],
                "map_version": 1,
                "method_id": "SYNTH-METHOD-KINETIC-V1",
                "segmentation_sha256": _sha(f"segmentation-{index:03d}-v1"),
                "parameters_sha256": _sha(f"parameters-{index:03d}-v1"),
                "map_sha256": _sha(f"map-{index:03d}-v1"),
                "supersedes_map_id": "NONE",
            }
        )
        map_for_handoff = ids["map1"]
        if index <= 10:
            events.append(
                {
                    "event_id": f"EV-MAP-{index:03d}-V2",
                    "kind": "map_version",
                    "map_id": ids["map2"],
                    "synthetic_subject_id": ids["subject"],
                    "acquisition_id": ids["acq"],
                    "qc_id": ids["qc"],
                    "map_version": 2,
                    "method_id": "SYNTH-METHOD-KINETIC-V1",
                    "segmentation_sha256": _sha(f"segmentation-{index:03d}-v2"),
                    "parameters_sha256": _sha(f"parameters-{index:03d}-v2"),
                    "map_sha256": _sha(f"map-{index:03d}-v2"),
                    "supersedes_map_id": ids["map1"],
                }
            )
            map_for_handoff = ids["map2"]

        events.append(
            {
                "event_id": f"EV-HANDOFF-{index:03d}",
                "kind": "handoff_receipt",
                "handoff_id": ids["handoff"],
                "synthetic_subject_id": ids["subject"],
                "map_id": map_for_handoff,
                "handoff_role": "SYNTH-DOWNSTREAM-PLANNING-RECEIPT",
                "receipt_sha256": _sha(f"handoff-{index:03d}"),
            }
        )

    # Five cross-subject acquisition attempts. None may enter accepted lineage.
    for index in range(1, 6):
        ids = _episode_ids(index)
        events.append(
            {
                "event_id": f"EV-HOSTILE-CROSS-ACQ-{index:03d}",
                "kind": "acquisition",
                "acquisition_id": f"SYNTH-HOSTILE-CROSS-ACQ-{index:03d}",
                "synthetic_subject_id": f"SYNTH-SUBJECT-{100 + index:03d}",
                "dose_receipt_id": ids["dose"],
                "protocol_id": ids["protocol"],
                "scanner_id": "SYNTH-SCANNER-HOSTILE",
                "acquisition_evidence_sha256": _sha(f"hostile-cross-acq-{index:03d}"),
                "acquisition_label": "HOSTILE",
            }
        )

    # Five maps with missing QC evidence pointers.
    for index in range(11, 16):
        ids = _episode_ids(index)
        events.append(
            {
                "event_id": f"EV-HOSTILE-MISSING-QC-{index:03d}",
                "kind": "map_version",
                "map_id": f"SYNTH-HOSTILE-MISSING-QC-MAP-{index:03d}",
                "synthetic_subject_id": ids["subject"],
                "acquisition_id": ids["acq"],
                "qc_id": f"SYNTH-QC-MISSING-{index:03d}",
                "map_version": 9,
                "method_id": "SYNTH-METHOD-HOSTILE",
                "segmentation_sha256": _sha(f"hostile-seg-missing-qc-{index:03d}"),
                "parameters_sha256": _sha(f"hostile-param-missing-qc-{index:03d}"),
                "map_sha256": _sha(f"hostile-map-missing-qc-{index:03d}"),
                "supersedes_map_id": ids["map1"],
            }
        )

    # Five pairs claim the same explicit version for one subject/acquisition.
    # Both sides of each branch must quarantine as ambiguous.
    for index in range(21, 26):
        ids = _episode_ids(index)
        for branch in ("A", "B"):
            events.append(
                {
                    "event_id": f"EV-HOSTILE-AMBIG-{index:03d}-{branch}",
                    "kind": "map_version",
                    "map_id": f"SYNTH-HOSTILE-AMBIG-MAP-{index:03d}-{branch}",
                    "synthetic_subject_id": ids["subject"],
                    "acquisition_id": ids["acq"],
                    "qc_id": ids["qc"],
                    "map_version": 9,
                    "method_id": "SYNTH-METHOD-HOSTILE",
                    "segmentation_sha256": _sha(f"hostile-ambig-seg-{index:03d}-{branch}"),
                    "parameters_sha256": _sha(f"hostile-ambig-param-{index:03d}-{branch}"),
                    "map_sha256": _sha(f"hostile-ambig-map-{index:03d}-{branch}"),
                    "supersedes_map_id": ids["map1"],
                }
            )

    # Five stale handoffs point to a superseded map version.
    for index in range(1, 6):
        ids = _episode_ids(index)
        events.append(
            {
                "event_id": f"EV-HOSTILE-STALE-HANDOFF-{index:03d}",
                "kind": "handoff_receipt",
                "handoff_id": f"SYNTH-HOSTILE-STALE-HANDOFF-{index:03d}",
                "synthetic_subject_id": ids["subject"],
                "map_id": ids["map1"],
                "handoff_role": "SYNTH-DOWNSTREAM-PLANNING-RECEIPT",
                "receipt_sha256": _sha(f"hostile-stale-handoff-{index:03d}"),
            }
        )

    # Exact retries across every event class prove zero duplicate effects.
    retry_positions = (0, 105, 205, 305, 405, 515)
    if len(events) != 640:
        raise RuntimeError(f"acceptance fixture construction drifted: {len(events)} unique rows")
    for position in retry_positions:
        events.append(deepcopy(events[position]))
    if len(events) != 646:
        raise RuntimeError(f"acceptance fixture retry contract drifted: {len(events)} rows")
    return events


def check_acceptance(events: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    batch = list(events) if events is not None else generate_acceptance_fixture()
    manifest = reconcile(batch)
    failures: list[str] = []

    if len(batch) != 646:
        failures.append(f"input count {len(batch)} != 646")
    if manifest["unique_events"] != 640:
        failures.append(f"unique event count {manifest['unique_events']} != 640")
    if manifest["replay_collapsed"] != 6:
        failures.append(f"replay collapse count {manifest['replay_collapsed']} != 6")
    if manifest["complete_synthetic_subjects"] != 100:
        failures.append(
            f"complete synthetic subjects {manifest['complete_synthetic_subjects']} != 100"
        )
    if manifest["counts"] != EXPECTED_COUNTS:
        failures.append(f"count contract mismatch: {manifest['counts']!r}")

    actual_quarantines: dict[str, int] = {}
    for row in manifest["quarantines"]:
        actual_quarantines[row["code"]] = actual_quarantines.get(row["code"], 0) + 1
    if actual_quarantines != EXPECTED_QUARANTINES:
        failures.append(f"quarantine contract mismatch: {actual_quarantines!r}")

    if not verify_receipt(manifest):
        failures.append("integrity receipt self-verification failed")

    reverse_manifest = reconcile(list(reversed(batch)))
    if reverse_manifest["receipt_sha256"] != manifest["receipt_sha256"]:
        failures.append("reversed input produced a different deterministic receipt")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "fixture_records": len(batch),
        "complete_synthetic_episodes": manifest["complete_synthetic_subjects"],
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

    print(
        canonical_json(
            {
                "status": result["status"],
                "fixture_records": result["fixture_records"],
                "complete_synthetic_episodes": result["complete_synthetic_episodes"],
                "counts": result["manifest"]["counts"],
                "receipt_sha256": result["manifest"]["receipt_sha256"],
                "failures": result["failures"],
            }
        )
    )
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
