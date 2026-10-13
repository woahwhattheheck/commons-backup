#!/usr/bin/env python3
"""Generate the frozen 100-batch / 24-fault acceptance corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FAULT_CLASSES = (
    "batch_identity",
    "co2_source_certificate",
    "renewable_power_certificate",
    "catalyst_electrolyzer_lot",
    "recipe_revision",
    "in_process_lab",
    "final_fuel_spec_coa",
    "tank_shipment_chain_of_custody",
)


def clean_batch(i: int) -> dict:
    n = i + 1
    return {
        "record_id": f"SYN-{n:03d}",
        "batch_id": f"EJ-SYN-{n:03d}",
        "co2_source": {"certificate_id": f"CO2-CERT-{n:03d}", "source_id": f"CO2-SRC-{(n % 7) + 1:02d}", "issued_at": "2026-09-01T05:00:00Z"},
        "renewable_power": {"certificate_id": f"REC-{n:03d}", "window_start": "2026-09-01T00:00:00Z", "window_end": "2026-09-01T23:59:59Z", "mwh": 8.25},
        "process_lots": {"catalyst_lot": f"CAT-{(n % 5) + 1:02d}", "electrolyzer_lot": f"ELY-{(n % 4) + 1:02d}"},
        "recipe_revision": "EJET-R17",
        "in_process_lab": {"sample_id": f"IP-{n:03d}", "result": "PASS", "measured_at": "2026-09-01T08:15:00Z"},
        "final_coa": {"coa_id": f"COA-{n:03d}", "spec_id": "ASTM-D7566-DEMO", "result": "PASS", "issued_at": "2026-09-01T10:00:00Z"},
        "custody": {
            "tank_id": f"TANK-{(n % 6) + 1:02d}",
            "shipment_id": f"SHIP-{n:03d}",
            "handoffs": [
                {"stage": "production_release", "timestamp": "2026-09-01T10:30:00Z", "owner": "Synthetic Plant Release"},
                {"stage": "carrier_pickup", "timestamp": "2026-09-01T14:00:00Z", "owner": "Synthetic Carrier"},
                {"stage": "buyer_receipt", "timestamp": "2026-09-02T09:00:00Z", "owner": "Synthetic Buyer"}
            ]
        }
    }


def apply_fault(batch: dict, fault_class: str) -> None:
    if fault_class == "batch_identity":
        batch["batch_id"] = ""
    elif fault_class == "co2_source_certificate":
        batch["co2_source"]["certificate_id"] = ""
    elif fault_class == "renewable_power_certificate":
        batch["renewable_power"]["window_start"] = "2026-09-02T00:00:00Z"
        batch["renewable_power"]["window_end"] = "2026-09-01T00:00:00Z"
    elif fault_class == "catalyst_electrolyzer_lot":
        batch["process_lots"]["catalyst_lot"] = ""
    elif fault_class == "recipe_revision":
        batch["recipe_revision"] = ""
    elif fault_class == "in_process_lab":
        batch["in_process_lab"]["result"] = "HOLD"
    elif fault_class == "final_fuel_spec_coa":
        batch["final_coa"]["result"] = "FAIL"
    elif fault_class == "tank_shipment_chain_of_custody":
        batch["custody"]["handoffs"][2]["owner"] = ""
    else:
        raise ValueError(f"unknown fault class {fault_class}")


def build_corpus() -> tuple[list[dict], dict[str, list[str]]]:
    batches = [clean_batch(i) for i in range(100)]
    plan: dict[str, list[str]] = {}
    cursor = 76
    for fault_class in FAULT_CLASSES:
        plan[fault_class] = []
        for _ in range(3):
            batch = batches[cursor]
            apply_fault(batch, fault_class)
            plan[fault_class].append(batch["record_id"])
            cursor += 1
    return batches, plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=Path("synthetic-100.json"))
    args = parser.parse_args()
    batches, plan = build_corpus()
    args.output.write_text(json.dumps(batches, sort_keys=True, indent=2) + "\n", encoding="ascii")
    print(json.dumps({"batches": len(batches), "fault_plan": plan}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
