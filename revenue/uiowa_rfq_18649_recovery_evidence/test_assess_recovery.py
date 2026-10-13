#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("uiowa68", HERE / "assess_recovery.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
assert spec.loader is not None
spec.loader.exec_module(m)

FIXTURE = HERE / "fixtures" / "synthetic_recovery_records.json"


class RecoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.data = m.load(FIXTURE)

    def test_synthetic_fixture_boundaries(self):
        report = m.assess(self.data)
        by_id = {r["service_id"]: r for r in report["services"]}
        self.assertEqual(report["summary"]["service_count"], 3)
        self.assertEqual(report["summary"]["backup_evidenced"], 3)
        self.assertEqual(report["summary"]["restoration_demonstrated"], 1)
        self.assertEqual(by_id["SVC-RIS"]["restoration_status"], "DEMONSTRATED")
        self.assertEqual(by_id["SVC-RIS"]["observed_rpo_minutes"], 30.0)
        self.assertEqual(by_id["SVC-RIS"]["observed_rto_minutes"], 100.0)
        self.assertEqual(by_id["SVC-RIS"]["rpo_result"], "MEETS_TARGET")
        self.assertEqual(by_id["SVC-RIS"]["rto_result"], "MEETS_TARGET")
        self.assertEqual(by_id["SVC-IAM"]["restoration_status"], "PARTIAL")
        self.assertEqual(by_id["SVC-REG"]["restoration_status"], "NOT_DEMONSTRATED")

    def test_backup_alone_never_demonstrates_restoration(self):
        report = m.assess(self.data)
        reg = next(r for r in report["services"] if r["service_id"] == "SVC-REG")
        self.assertEqual(reg["backup_status"], "EVIDENCED")
        self.assertEqual(reg["restoration_status"], "NOT_DEMONSTRATED")
        self.assertEqual(reg["rpo_result"], "UNKNOWN")
        self.assertEqual(reg["rto_result"], "UNKNOWN")

    def test_missing_business_verification_keeps_rto_unknown(self):
        report = m.assess(self.data)
        iam = next(r for r in report["services"] if r["service_id"] == "SVC-IAM")
        self.assertEqual(iam["business_verification"], "NOT_EVIDENCED")
        self.assertIsNone(iam["observed_rto_minutes"])
        self.assertEqual(iam["restoration_status"], "PARTIAL")

    def test_missing_dependency_evidence_is_partial(self):
        data = copy.deepcopy(self.data)
        ris = next(s for s in data["services"] if s["service_id"] == "SVC-RIS")
        ris["exercise"]["dependency_results"] = []
        report = m.assess(data)
        out = next(r for r in report["services"] if r["service_id"] == "SVC-RIS")
        self.assertEqual(out["dependency_verification"], "PARTIAL")
        self.assertEqual(out["restoration_status"], "PARTIAL")

    def test_rpo_target_can_be_exceeded_without_becoming_unknown(self):
        data = copy.deepcopy(self.data)
        ris = next(s for s in data["services"] if s["service_id"] == "SVC-RIS")
        ris["exercise"]["restored_data_as_of"] = "2026-09-17T23:00:00Z"
        report = m.assess(data)
        out = next(r for r in report["services"] if r["service_id"] == "SVC-RIS")
        self.assertEqual(out["observed_rpo_minutes"], 120.0)
        self.assertEqual(out["rpo_result"], "EXCEEDS_TARGET")

    def test_impossible_restore_chronology_rejected(self):
        data = copy.deepcopy(self.data)
        ris = next(s for s in data["services"] if s["service_id"] == "SVC-RIS")
        ris["exercise"]["restore_completed_at"] = "2026-09-18T00:50:00Z"
        with self.assertRaises(m.DataError):
            m.assess(data)

    def test_duplicate_service_rejected(self):
        data = copy.deepcopy(self.data)
        data["services"].append(copy.deepcopy(data["services"][0]))
        with self.assertRaises(m.DataError):
            m.assess(data)


if __name__ == "__main__":
    unittest.main()
