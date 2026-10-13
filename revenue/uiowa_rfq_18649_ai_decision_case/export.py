"""Portable tables and source records for the synthetic decision case."""
from __future__ import annotations

import csv
import dataclasses
import json
from pathlib import Path

from model import is_known


def case_document(case):
    """Keep effective assumptions and the original document/quality records together."""
    return {
        "case_id": case.case_id, "workflow": case.workflow, "synthetic": True,
        "documents": [
            {"id": doc.id, "variant": doc.variant, "events": [
                {"id": event.id, "kind": event.kind, "day": event.day,
                 "minutes": event.minutes if is_known(event.minutes) else None}
                for event in doc.events]}
            for doc in case.documents],
        "quality_measurements": [dataclasses.asdict(row) for row in case.quality],
        "assumptions": [dataclasses.asdict(case.assumptions[name])
                        for name in sorted(case.assumptions)],
    }


def write_outputs(directory, case, decision, payload, explanation):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    (root / "explanation.md").write_text(explanation + "\n", encoding="utf-8")
    (root / "decision.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (root / "effective_case.json").write_text(
        json.dumps(case_document(case), indent=2, allow_nan=False) + "\n", encoding="utf-8")

    def table(name, headers, rows):
        with (root / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)

    def cell(value):
        return value if is_known(value) else "UNKNOWN"

    results = decision.to_dict()
    summary = []
    for metric, value in results.items():
        if metric in {"baseline", "assisted", "case_id", "reasons"}:
            continue
        if isinstance(value, dict):
            summary.extend([case.case_id, metric + "." + edge, cell(number),
                            "MODELED_SYNTHETIC" if number is not None else "UNKNOWN"]
                           for edge, number in value.items())
        else:
            summary.append([case.case_id, metric, cell(value),
                            "MODELED_SYNTHETIC" if value is not None else "UNKNOWN"])
    table("summary.csv", ["case_id", "metric", "value", "basis"], summary)
    table("lifecycle.csv", ["case_id", "document_id", "variant", "event_id",
                            "day", "kind", "minutes", "basis"],
          ([case.case_id, doc.id, doc.variant, event.id, event.day, event.kind,
            cell(event.minutes), "SYNTHETIC_RECORD" if is_known(event.minutes) else "UNKNOWN"]
           for doc in case.documents for event in doc.sorted_events()))
    table("quality.csv", ["case_id", "measurement_id", "document_id",
                          "required_elements", "correct_elements", "fabricated_references", "basis"],
          ([case.case_id, row.id, row.document_id, row.required_elements,
            row.correct_elements, row.fabricated_references, "SYNTHETIC_RECORD"]
           for row in sorted(case.quality, key=lambda row: row.id)))
    table("assumptions.csv", ["case_id", "assumption_id", "name", "value", "low",
                              "high", "unit", "basis", "source"],
          ([case.case_id, row.id, row.name, row.value, row.low, row.high,
            row.unit, row.basis, row.source]
           for row in sorted(case.assumptions.values(), key=lambda row: row.name)))
