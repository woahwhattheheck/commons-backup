"""Deterministic synthetic acceptance matrix for laboratory-interface UAT."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from .engine import (
    SCHEMA, SOURCE_SCHEMA, TARGET_SCHEMA, evaluate, verify_receipt
)


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def contract() -> dict[str, Any]:
    code_map = {"GLU": "GLUCOSE", "HGB": "HEMOGLOBIN", "WBC": "WBC_COUNT"}
    unit_map = {"mg_dL": "mg_per_dL", "g_dL": "g_per_dL", "count_uL": "count_per_uL"}
    mapping_version = "synthetic-map-v1"
    mapping_sha256 = _h(json.dumps(
        {"code_map": dict(sorted(code_map.items())),
         "mapping_version": mapping_version,
         "unit_map": dict(sorted(unit_map.items()))},
        sort_keys=True, separators=(",", ":")
    ))
    return {
        "schema": SCHEMA,
        "contract_id": "lab-interface-synthetic",
        "version": "2026.09.synthetic.1",
        "source_system": "lims-synthetic",
        "target_system": "dhis2-synthetic",
        "mapping_version": mapping_version,
        "mapping_sha256": mapping_sha256,
        "code_map": code_map,
        "unit_map": unit_map,
        "allowed_statuses": ["FINAL", "CORRECTED"],
        "allowed_specimen_types": ["BLOOD", "SERUM"],
    }


def source(index: int, *, revision: int = 1, supersedes: str | None = None) -> dict[str, Any]:
    tests = [
        ("GLU", "mg_dL", "91.0", "70", "110", "SERUM"),
        ("HGB", "g_dL", "13.7", "12.0", "17.5", "BLOOD"),
        ("WBC", "count_uL", "6200", "4000", "11000", "BLOOD"),
    ]
    code, unit, value, low, high, specimen = tests[index % len(tests)]
    return {
        "schema": SOURCE_SCHEMA,
        "event_id": f"src-{index:03d}-r{revision}",
        "source_system": "lims-synthetic",
        "logical_id": f"logical-{index:03d}",
        "revision": revision,
        "supersedes_event_id": supersedes,
        "accession_id": f"acc-{index:03d}",
        "specimen_type": specimen,
        "test_code": code,
        "result_value": value,
        "unit": unit,
        "reference_low": low,
        "reference_high": high,
        "status": "FINAL" if revision == 1 else "CORRECTED",
        "site": f"site-{index % 4}",
    }


def target_for(src: dict[str, Any], *, event_suffix: str = "") -> dict[str, Any]:
    c = contract()
    return {
        "schema": TARGET_SCHEMA,
        "event_id": f"tgt-{src['event_id']}{event_suffix}",
        "target_system": c["target_system"],
        "source_event_id": src["event_id"],
        "logical_id": src["logical_id"],
        "revision": src["revision"],
        "contract_id": c["contract_id"],
        "contract_version": c["version"],
        "mapping_sha256": c["mapping_sha256"],
        "accession_id": src["accession_id"],
        "specimen_type": src["specimen_type"],
        "test_code": c["code_map"].get(src["test_code"], "UNMAPPED"),
        "result_value": src["result_value"],
        "unit": c["unit_map"].get(src["unit"], "UNMAPPED"),
        "reference_low": src["reference_low"],
        "reference_high": src["reference_high"],
        "status": src["status"],
        "site": src["site"],
    }


def run_acceptance() -> dict[str, Any]:
    counts = {"PASS": 0, "HOLD": 0}
    reason_counts: dict[str, int] = {}
    receipts = []
    for index in range(200):
        c = contract()
        s1 = source(index)
        sources = [s1]
        targets = [target_for(s1)]
        bucket = index // 8
        if 20 <= bucket < 21:  # 160..167: missing target
            targets = []
        elif 21 <= bucket < 22:  # 168..175: parity drift
            targets[0]["result_value"] = "999"
        elif 22 <= bucket < 23:  # 176..183: same-id conflict
            changed = deepcopy(s1)
            changed["result_value"] = "999"
            sources.append(changed)
        elif 23 <= bucket < 24:  # 184..191: broken correction lineage
            s2 = source(index, revision=2, supersedes="src-wrong-r1")
            sources.append(s2)
            targets.append(target_for(s2))
        elif 24 <= bucket < 25:  # 192..199: unmapped terminology
            sources[0]["test_code"] = "NOVEL_TEST"
            targets[0] = target_for(sources[0])
        receipt = evaluate(c, sources, targets)
        counts[receipt["status"]] += 1
        for reason in receipt["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        receipts.append(receipt)

    c = contract()
    clean_s = source(777)
    clean_t = target_for(clean_s)
    clean = evaluate(c, [clean_s], [clean_t])
    replay = evaluate(c, [deepcopy(clean_s), deepcopy(clean_s)], [deepcopy(clean_t), deepcopy(clean_t)])
    return {
        "schema": "lab-interface-uat-acceptance/v1",
        "counts": counts,
        "reason_counts": dict(sorted(reason_counts.items())),
        "replay_idempotent": clean == replay,
        "receipt_verifies": verify_receipt(clean, c, [clean_s], [clean_t]),
        "receipt_set_sha256": _h(json.dumps(receipts, sort_keys=True, separators=(",", ":"))),
    }


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), sort_keys=True, indent=2))
