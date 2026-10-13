#!/usr/bin/env python3
"""Isolated provenance regression for Denton bacteriology acceptance/reporting."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import denton_bacteriology_acceptance_reporting_lims as gate

SOURCE_FIELDS = (
    "submission_id",
    "sample_id",
    "account_id",
    "pws_id",
    "client_id",
    "route",
    "method",
    "report_form",
    "custody_signed",
    "custody_time",
    "collected_on",
    "bottle_expires",
    "temperature_c",
    "hold_time_hours",
    "source_revision",
)
COORDINATE_FIELDS = (
    "account_id",
    "pws_id",
    "client_id",
    "sample_id",
    "source_revision",
)

# Intentionally independent from gate.ROUTES / gate.build_acceptance_fixture() /
# gate.normalize_row(). These literals are the frozen Denton accepted-row oracle.
INDEPENDENT_ROUTES = (
    ("TCEQ_ECOLI_QUANT", "SM-9223B-Q", "TCEQ-ECOLI-QUANT"),
    ("TCEQ_AP", "SM-9221-PA", "TCEQ-AP"),
    ("HPC", "SM-9215B", "HPC-PLATE"),
)


def independent_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def independent_expected_acceptance() -> dict[str, dict[str, object]]:
    """Re-derive the 160 accepted rows without importing product generators."""
    expected: dict[str, dict[str, object]] = {}
    for index in range(1, 161):
        token = f"{index:03d}"
        route, method, report_form = INDEPENDENT_ROUTES[(index - 1) % 3]
        payload: dict[str, object] = {
            "submission_id": f"SUB-{token}",
            "sample_id": f"SMP-{token}",
            "account_id": f"ACCT-{(index % 20) + 1:02d}",
            "pws_id": f"TX061000{(index % 4) + 1}",
            "client_id": f"CLIENT-{(index % 20) + 1:02d}",
            "route": route,
            "method": method,
            "report_form": report_form,
            "custody_signed": "J-DOE",
            "custody_time": "2026-08-31T08:00:00Z",
            "collected_on": "2026-08-31",
            "bottle_expires": "2026-09-30",
            "temperature_c": 6.0,
            "hold_time_hours": 4.0,
            "source_revision": "DENTON-SYNTHETIC-2026-01",
        }
        expected[payload["submission_id"]] = {
            **{field: payload[field] for field in COORDINATE_FIELDS},
            "source_hash": independent_sha256(payload),
        }
    return expected


def actual_acceptance(result: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["submission_id"]: {
            **{field: item[field] for field in COORDINATE_FIELDS},
            "source_hash": item["source_hash"],
        }
        for item in result["submissions"]
    }


class DentonBacteriologyProvenanceTests(unittest.TestCase):
    def test_all_160_accepted_coordinates_and_hashes_match_independent_oracle(self) -> None:
        expected = independent_expected_acceptance()
        actual = actual_acceptance(gate.run_gate())
        self.assertEqual(len(expected), 160)
        self.assertEqual(actual, expected)

    def test_independent_oracle_detects_coherent_generator_coordinate_drift(self) -> None:
        rows = deepcopy(gate.build_acceptance_fixture())
        first = rows[0]
        self.assertIsNone(first["exception_type"])
        # Simulate a coherent product-side fixture/runtime drift. The row stays
        # valid and run_gate faithfully carries the changed coordinate/hash, but
        # the independent oracle must remain frozen and disagree.
        first["account_id"] = "ACCT-99"
        first["client_id"] = "CLIENT-99"
        first["source_revision"] = "DENTON-SYNTHETIC-DRIFT"
        actual = actual_acceptance(gate.run_gate(rows))
        expected = independent_expected_acceptance()
        self.assertIn("SUB-001", actual)
        self.assertNotEqual(actual["SUB-001"], expected["SUB-001"])
        self.assertNotEqual(
            actual["SUB-001"]["source_hash"], expected["SUB-001"]["source_hash"]
        )

    def test_lineage_is_exact_and_hold_rows_add_no_downstream_outputs(self) -> None:
        result = gate.run_gate()
        worksheets = {
            item["worksheet_id"]: item for item in result["worksheet_records"]
        }
        reports = {item["report_id"]: item for item in result["report_records"]}

        self.assertEqual(len(result["submissions"]), 160)
        self.assertEqual(len(worksheets), 160)
        self.assertEqual(len(reports), 160)
        for submission in result["submissions"]:
            worksheet = worksheets[submission["worksheet_id"]]
            report = reports[submission["report_id"]]
            self.assertEqual(worksheet["accession_id"], submission["accession_id"])
            self.assertEqual(worksheet["sample_id"], submission["sample_id"])
            self.assertEqual(worksheet["method"], submission["method"])
            self.assertEqual(worksheet["report_form"], submission["report_form"])
            self.assertEqual(worksheet["route"], submission["route"])
            self.assertEqual(report["accession_id"], submission["accession_id"])
            self.assertEqual(report["worksheet_id"], submission["worksheet_id"])
            self.assertEqual(report["sample_id"], submission["sample_id"])
            self.assertEqual(report["method"], submission["method"])
            self.assertEqual(report["report_form"], submission["report_form"])
            self.assertEqual(report["source_hash"], submission["source_hash"])

        journal = gate.empty_journal()
        hold_effects = 0
        for row in gate.build_acceptance_fixture():
            before = (
                len(journal["accessions"]),
                len(journal["worksheets"]),
                len(journal["reports"]),
            )
            effect = gate.ingest_row(journal, row)
            if effect["kind"] != "HOLD":
                continue
            hold_effects += 1
            after = (
                len(journal["accessions"]),
                len(journal["worksheets"]),
                len(journal["reports"]),
            )
            self.assertEqual(after, before)
            self.assertEqual(journal["holds"][-1]["worksheets_created"], 0)
            self.assertEqual(journal["holds"][-1]["reports_created"], 0)
            self.assertNotIn(
                gate.normalize_row(row)["submission_id"], journal["submissions"]
            )

        self.assertEqual(hold_effects, 40)
        self.assertEqual(len(journal["accessions"]), 160)
        self.assertEqual(len(journal["worksheets"]), 160)
        self.assertEqual(len(journal["reports"]), 160)
        self.assertEqual(len(journal["holds"]), 40)


if __name__ == "__main__":
    unittest.main()
