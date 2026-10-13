from __future__ import annotations

import copy
import hashlib
import json

from .gate import canonical_json, evaluate, sha256, verify_decision

AS_OF = "2026-09-13T11:00:00Z"
VERIFY_AT = "2026-09-13T11:01:00Z"
HOLD_REASONS = (
    "RECIPE_MISMATCH",
    "MATERIAL_COVERAGE_MISMATCH",
    "MATERIAL_UNRELEASED",
    "EQUIPMENT_COVERAGE_MISMATCH",
    "CALIBRATION_EXPIRED",
    "ENVIRONMENT_HOLD",
    "ENVIRONMENT_STALE_FOR_SLOT",
    "INSPECTION_LINEAGE_MISMATCH",
    "BOM_MISMATCH",
)


def h(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def packet(index: int) -> dict:
    batch_id = f"batch-{index:03d}"
    approved_digest = h(f"recipe-approved-{index:03d}")
    return {
        "schema_version": "pci.fill-finish-batch-readiness/v2",
        "packet_id": f"packet-{index:03d}",
        "batch_id": batch_id,
        "planned_slot_at": "2026-09-13T12:00:00Z",
        "recipe": {
            "recipe_id": "recipe-sterile-A",
            "version": "v7",
            "approved": True,
            "approved_digest": approved_digest,
            "observed_at": "2026-09-13T10:54:00Z",
            "scheduled_recipe_id": "recipe-sterile-A",
            "scheduled_version": "v7",
            "required_material_components": ["drug-A", "excipient-B"],
            "required_equipment_ids": ["filler-1", "isolator-1"],
        },
        "materials": [
            {
                "lot_id": f"lot-drug-{index:03d}",
                "component": "drug-A",
                "released": True,
                "release_digest": h(f"drug-release-{index:03d}"),
                "observed_at": "2026-09-13T10:55:00Z",
            },
            {
                "lot_id": f"lot-excipient-{index:03d}",
                "component": "excipient-B",
                "released": True,
                "release_digest": h(f"excipient-release-{index:03d}"),
                "observed_at": "2026-09-13T10:55:00Z",
            },
        ],
        "equipment": [
            {
                "equipment_id": "filler-1",
                "calibration_valid_until": "2026-09-14T00:00:00Z",
                "calibration_digest": h(f"filler-cal-{index:03d}"),
                "observed_at": "2026-09-13T10:56:00Z",
            },
            {
                "equipment_id": "isolator-1",
                "calibration_valid_until": "2026-09-14T00:00:00Z",
                "calibration_digest": h(f"isolator-cal-{index:03d}"),
                "observed_at": "2026-09-13T10:56:00Z",
            },
        ],
        "environment": {
            "isolator_state": "READY",
            "em_state": "PASS",
            "captured_at": "2026-09-13T10:57:00Z",
            "valid_until": "2026-09-13T12:30:00Z",
            "evidence_digest": h(f"environment-{index:03d}"),
        },
        "fill_inspection": {
            "fill_weight_batch_id": batch_id,
            "inspection_batch_id": batch_id,
            "recipe_digest": approved_digest,
            "fill_weight_digest": h(f"fill-weight-{index:03d}"),
            "inspection_digest": h(f"inspection-{index:03d}"),
            "observed_at": "2026-09-13T10:58:00Z",
        },
        "bom": {
            "required": [
                {"component_id": "label-A", "version": "v2"},
                {"component_id": "device-A", "version": "v5"},
            ],
            "staged": [
                {"component_id": "device-A", "version": "v5"},
                {"component_id": "label-A", "version": "v2"},
            ],
            "evidence_digest": h(f"bom-{index:03d}"),
            "observed_at": "2026-09-13T10:59:00Z",
        },
    }


def trusted_definition(index: int) -> dict:
    return {
        "recipe_id": "recipe-sterile-A",
        "version": "v7",
        "approved_digest": h(f"recipe-approved-{index:03d}"),
        "required_material_components": ["drug-A", "excipient-B"],
        "required_equipment_ids": ["filler-1", "isolator-1"],
        "required_bom": [
            {"component_id": "label-A", "version": "v2"},
            {"component_id": "device-A", "version": "v5"},
        ],
    }


def inject(raw: dict, reason: str) -> None:
    if reason == "RECIPE_MISMATCH":
        raw["recipe"]["scheduled_version"] = "v8"
    elif reason == "MATERIAL_COVERAGE_MISMATCH":
        raw["materials"] = raw["materials"][:1]
    elif reason == "MATERIAL_UNRELEASED":
        raw["materials"][0]["released"] = False
    elif reason == "EQUIPMENT_COVERAGE_MISMATCH":
        raw["equipment"] = raw["equipment"][:1]
    elif reason == "CALIBRATION_EXPIRED":
        raw["equipment"][0]["calibration_valid_until"] = "2026-09-13T11:59:59Z"
    elif reason == "ENVIRONMENT_HOLD":
        raw["environment"]["em_state"] = "HOLD"
    elif reason == "ENVIRONMENT_STALE_FOR_SLOT":
        raw["environment"]["valid_until"] = "2026-09-13T11:59:59Z"
    elif reason == "INSPECTION_LINEAGE_MISMATCH":
        raw["fill_inspection"]["inspection_batch_id"] = "batch-wrong"
    elif reason == "BOM_MISMATCH":
        raw["bom"]["staged"][0]["version"] = "v6"
    else:
        raise RuntimeError(f"unknown injected reason: {reason}")


def run_acceptance() -> dict:
    decisions: list[dict] = []
    counts = {reason: 0 for reason in HOLD_REASONS}
    ready = 0
    hold = 0

    for index in range(180):
        raw = packet(index)
        expected_reason = None
        if index < 54:
            expected_reason = HOLD_REASONS[index % len(HOLD_REASONS)]
            inject(raw, expected_reason)
        decision = evaluate(raw, trusted_as_of=AS_OF, trusted_definition=trusted_definition(index))
        verified = verify_decision(
            raw,
            decision,
            trusted_definition=trusted_definition(index),
            expected_evaluated_at=AS_OF,
            trusted_verify_at=VERIFY_AT,
        )
        if verified["valid"] is not True:
            raise RuntimeError("decision verification did not return valid=true")
        if expected_reason is None:
            if decision["status"] != "READY" or decision["hold_reasons"] != []:
                raise RuntimeError(f"packet {index} should be READY")
            ready += 1
        else:
            if decision["status"] != "HOLD" or decision["hold_reasons"] != [expected_reason]:
                raise RuntimeError(
                    f"packet {index} expected singleton {expected_reason}, got {decision['hold_reasons']}"
                )
            counts[expected_reason] += 1
            hold += 1
        decisions.append(decision)

    if ready != 126 or hold != 54:
        raise RuntimeError(f"unexpected totals ready={ready} hold={hold}")
    if any(count != 6 for count in counts.values()):
        raise RuntimeError(f"unexpected hold distribution: {counts}")
    receipt_set_digest = sha256([decision["receipt_digest"] for decision in decisions])
    report = {
        "schema_version": "pci.fill-finish-batch-readiness-acceptance/v2",
        "packets": len(decisions),
        "ready": ready,
        "hold": hold,
        "hold_counts": counts,
        "trusted_evaluated_at": AS_OF,
        "trusted_verify_at": VERIFY_AT,
        "receipt_set_digest": receipt_set_digest,
    }
    # Ensure serialization itself is canonicalizable before success.
    canonical_json(report)
    return report


# Backward-compatible local alias; the manifest continues to name run_acceptance.
run = run_acceptance


def main() -> None:
    print(json.dumps(run_acceptance(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
