#!/usr/bin/env python3
"""Generate a fictional UI-shaped report and draft; never compiler output."""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from . import bundle
except ImportError:
    import bundle


def synthetic_pair() -> tuple[dict, dict]:
    cells = []
    for group in ("ESS", "RIS", "IAM"):
        for dimension in ("software_development", "security", "deployment", "ai_readiness"):
            cells.append({
                "group": group, "dimension": dimension,
                "status": ("HOLD_MISSING_EVIDENCE" if dimension == "security"
                           else "UNTRUSTED_EVIDENCE_CONSISTENT"),
                "maturity": None, "confidence_bp": None,
                "source_ids": [f"synthetic-{group.lower()}-{dimension}"],
                "source_record_sha256s": ["0" * 64],
                "reason_codes": ["SYNTHETIC_REHEARSAL_ONLY"],
            })
    report = {
        "schema": bundle.DEMO_SCHEMA, "synthetic_demo": True,
        "mode": "UNTRUSTED_INSPECTION", "receipt_sha256": "d" * 64,
        "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED",
        "trust": {"authority_root_supplied_out_of_band": False,
                  "current_evidence_review_authority": False},
        "commercial_terms": {"status": "PROPOSED_NOT_ACCEPTED"},
        "assessment_matrix": cells,
        "status_counts": {"HOLD_MISSING_EVIDENCE": 3,
                          "UNTRUSTED_EVIDENCE_CONSISTENT": 9},
    }
    handoff = {
        "schema": bundle.HANDOFF_SCHEMA, "status": "DRAFT_NON_AUTHORITATIVE",
        "report_receipt_sha256": report["receipt_sha256"], "report_mode": report["mode"],
        "aggregate_state": report["aggregate_state"], "synthetic_demo": True,
        "cell_notes": [{"group": c["group"], "dimension": c["dimension"],
                        "compiler_status": c["status"],
                        "disposition": "NEEDS_EVIDENCE" if c["dimension"] == "security"
                                       else "UNREVIEWED",
                        "analyst_note": "Fictional rehearsal: identify a corroborating artifact."
                                         if c["dimension"] == "security" else ""}
                       for c in cells],
        "authority": {key: False for key in bundle.AUTHORITY_KEYS},
    }
    return report, handoff


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    # A new directory is deliberate: never replace an analyst's existing files.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report, handoff = synthetic_pair()
    for name, value in (("report.json", report), ("handoff.json", handoff)):
        with (args.output_dir / name).open("xb") as handle:
            handle.write(bundle.canonical(value))
    print("SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT")


if __name__ == "__main__":
    main()
