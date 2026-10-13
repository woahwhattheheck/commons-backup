#!/usr/bin/env python3
"""Generate corrected and deliberate-mismatch fixtures for UIOWA-117."""
from __future__ import annotations

import argparse
import csv
import json
from copy import deepcopy
from pathlib import Path
from typing import Optional, Sequence


CANONICAL = {
    "fixture": "UIOWA-117 synthetic cross-output consistency example",
    "source_note": (
        "IDs F-001..F-003 and R-001..R-002 intentionally align with the merged "
        "UIOWA-093 traceability rehearsal. F-004 and planning phase/estimate fields "
        "exist only for this synthetic consistency exercise."
    ),
    "findings": [
        {"finding_id": "F-001", "service": "ESS", "area": "software", "state": "SUPPORTED"},
        {"finding_id": "F-002", "service": "RIS", "area": "deployment", "state": "PARTIAL"},
        {"finding_id": "F-003", "service": "IAM", "area": "deployment", "state": "PARTIAL"},
        {"finding_id": "F-004", "service": "ESS", "area": "ai", "state": "UNKNOWN"},
    ],
    "recommendations": [
        {
            "recommendation_id": "R-001",
            "finding_ids": ["F-002"],
            "phase": "0-90",
            "estimate_low": 2,
            "estimate_high": 5,
        },
        {
            "recommendation_id": "R-002",
            "finding_ids": ["F-003"],
            "phase": "90-180",
            "estimate_low": 1,
            "estimate_high": 3,
        },
    ],
}


def write_csv(path: Path, fields, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def corrected_payloads():
    matrix = [
        {
            "cell_id": f"{x['service']}-{x['area'].upper()}",
            "service": x["service"],
            "area": x["area"],
            "finding_id": x["finding_id"],
            "finding_state": x["state"],
        }
        for x in CANONICAL["findings"]
    ]
    recs = [
        {
            "recommendation_id": r["recommendation_id"],
            "linked_findings": ";".join(r["finding_ids"]),
            "phase": r["phase"],
            "estimate_low": r["estimate_low"],
            "estimate_high": r["estimate_high"],
        }
        for r in CANONICAL["recommendations"]
    ]
    claims = [
        {
            "claim_id": "S-001",
            "finding_id": "F-001",
            "finding_state": "SUPPORTED",
            "recommendation_id": "",
        },
        {
            "claim_id": "S-002",
            "finding_id": "F-002",
            "finding_state": "PARTIAL",
            "recommendation_id": "R-001",
            "phase": "0-90",
            "estimate_low": 2,
            "estimate_high": 5,
        },
        {
            "claim_id": "S-003",
            "finding_id": "F-003",
            "finding_state": "PARTIAL",
            "recommendation_id": "R-002",
            "phase": "90-180",
            "estimate_low": 1,
            "estimate_high": 3,
        },
        {
            "claim_id": "S-004",
            "finding_id": "F-004",
            "finding_state": "UNKNOWN",
            "recommendation_id": "",
        },
    ]
    exec_summary = {
        "declared_counts": {"findings": 4, "recommendations": 2},
        "claims": deepcopy(claims),
    }
    presentation = {
        "declared_counts": {"findings": 4, "recommendations": 2},
        "claims": deepcopy(claims),
    }
    return matrix, recs, exec_summary, presentation


def write_bundle(out: Path, mismatch: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    matrix, recs, summary, presentation = corrected_payloads()
    if mismatch:
        matrix[1]["finding_state"] = "SUPPORTED"
        recs[1]["phase"] = "0-90"
        summary["declared_counts"]["recommendations"] = 3
        summary["claims"][1]["estimate_low"] = 4
        presentation["claims"].append({
            "claim_id": "S-999",
            "finding_id": "F-999",
            "finding_state": "SUPPORTED",
            "recommendation_id": "",
        })

    (out / "canonical.json").write_text(
        json.dumps(CANONICAL, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_csv(
        out / "matrix.csv",
        ["cell_id", "service", "area", "finding_id", "finding_state"],
        matrix,
    )
    write_csv(
        out / "recommendations.csv",
        ["recommendation_id", "linked_findings", "phase", "estimate_low", "estimate_high"],
        recs,
    )
    (out / "executive-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out / "presentation.json").write_text(
        json.dumps(presentation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--mismatch", action="store_true")
    args = p.parse_args(argv)
    write_bundle(args.out, args.mismatch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
