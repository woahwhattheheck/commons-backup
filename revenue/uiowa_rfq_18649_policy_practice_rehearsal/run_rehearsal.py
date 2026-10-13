#!/usr/bin/env python3
"""UIOWA-110 synthetic disagreement integration run."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
METHOD = ROOT / "revenue" / "uiowa_rfq_18649_workshare" / "methodology"
RATING = ROOT / "revenue" / "uiowa_rfq_18649_rating_model"
sys.path.insert(0, str(METHOD))
sys.path.insert(0, str(RATING))

import validate_23_evidence_register as confidence  # noqa: E402
import rating_model  # noqa: E402


def read_rows():
    with (HERE / "evidence-register.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def build_result():
    errors = confidence.validate(HERE / "evidence-register.csv")
    if errors:
        raise ValueError("; ".join(errors))

    rows = read_rows()
    unresolved = {
        row["finding_id"] for row in rows if row["confidence"] == "UNRESOLVED"
    }
    if unresolved != {"FND-SYN-IAM-DEP-110"}:
        raise ValueError("controlled disagreement lost its unresolved finding")

    payload = {
        "engagement": "UIOWA-110 synthetic disagreement",
        "criteria": [
            {
                "criterion_id": "SYN-CHANGE-REVIEW",
                "area": "delivery",
                "service": "SYN",
                "assessment_status": "unassessed",
                "criticality": "important",
            }
        ],
    }
    rating = rating_model.compose(payload)
    summary = rating["area_summaries"]["delivery"]
    if summary["composition_status"] != "unassessed":
        raise ValueError("unresolved disagreement must remain unassessed")
    if summary["maturity_distribution_by_rank"]:
        raise ValueError("unresolved disagreement acquired a maturity rank")

    return {
        "synthetic": True,
        "confidence": {
            "validation": "PASS",
            "finding_state": "UNRESOLVED",
            "evidence_rows": len(rows),
        },
        "rating": rating,
        "review": {
            "supported_strength": (
                "A current documented procedure exists and eight of twelve "
                "records in the bounded synthetic sample align with it."
            ),
            "specific_uncertainty": (
                "Four sampled records differ and lack an exception marker; "
                "the packet cannot yet distinguish exceptions, scope drift, "
                "recordkeeping gaps, or practice variation."
            ),
            "disposition": (
                "TARGETED_FOLLOW_UP_BEFORE_DEFINITIVE_PRACTICE_CHARACTERIZATION"
            ),
            "follow_up": [
                "Confirm procedure effective scope and date.",
                "Inspect classification and review history for the four differing records.",
                "Use a complete population source before making a group-wide claim.",
            ],
        },
    }


if __name__ == "__main__":
    print(json.dumps(build_result(), indent=2, sort_keys=True))
