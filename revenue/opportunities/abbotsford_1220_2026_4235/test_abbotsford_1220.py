#!/usr/bin/env python3
from __future__ import annotations
import math, unittest
from copy import deepcopy
from pathlib import Path
from abbotsford_1220 import (
    AUTHORITY_FALSE, BID_NUMBER, CARRIER_ROOT, CLOSE_UTC, ContractError,
    DEMO_CAPABILITIES, compile_bundle, digest, evaluate_demo_case,
    load_fixture_cases, load_strict_json, public_facts, qualify,
    reject_nonfinite, verify_demo,
)
ROOT = Path(__file__).resolve().parent
class StrictParsingTests(unittest.TestCase):
    def test_duplicate_keys_fail(self):
        with self.assertRaises(ContractError):
            load_strict_json('{"a":1,"a":2}')
    def test_nonfinite_fails(self):
        with self.assertRaises(ContractError):
            reject_nonfinite({"x": math.inf})
        with self.assertRaises(ContractError):
            reject_nonfinite({"x": math.nan})
class QualificationTests(unittest.TestCase):
    def test_hold_without_packet(self):
        result = qualify()
        self.assertEqual(result["qualification"], "HOLD_PACKET_REQUIRED")
        self.assertFalse(result["authorized_packet_present"])
        self.assertFalse(result["demo_satisfies_unknown_mandatory"])
        self.assertGreaterEqual(len(result["missing_authorized_facts"]), 8)
        for key, value in AUTHORITY_FALSE.items():
            self.assertIs(result[key], value)
        self.assertEqual(result["receipt_sha256"], digest({k: v for k, v in result.items() if k != "receipt_sha256"}))
    def test_flag_without_bytes_stays_hold(self):
        result = qualify({"schema": "tjlabs.abbotsford-1220-qualification/v1", "bid_number": BID_NUMBER, "authorized_package_evidence": True})
        self.assertEqual(result["qualification"], "HOLD_PACKET_REQUIRED")
    def test_bytes_present_moves_to_partner_review_not_ready(self):
        result = qualify({"schema": "tjlabs.abbotsford-1220-qualification/v1", "bid_number": BID_NUMBER, "authorized_package_evidence": {"sha256": "0" * 64, "bytes_present": True}})
        self.assertEqual(result["qualification"], "PARTNER_REVIEW_REQUIRED")
        self.assertNotEqual(result["qualification"], "READY_FOR_OWNER_REVIEW")
        self.assertFalse(result["proposal_submission_authorized"])
    def test_past_source_capture_rejected(self):
        with self.assertRaises(ContractError):
            qualify(now_utc="2020-01-01T00:00:00Z")
    def test_windows(self):
        before = qualify(now_utc="2026-09-20T00:00:00Z")
        self.assertTrue(before["question_window_open"] and before["submission_window_open"])
        self.assertFalse(qualify(now_utc="2026-09-24T21:00:00Z")["question_window_open"])
        after_close = qualify(now_utc=CLOSE_UTC)
        self.assertFalse(after_close["submission_window_open"])
        self.assertTrue(after_close["source_freshness"]["stale_if_after_close"])
class DemoTests(unittest.TestCase):
    def test_fixture_compiles_and_recompiles(self):
        cases = load_fixture_cases()
        bundle = compile_bundle(cases)
        self.assertEqual(bundle["carrier_root"], CARRIER_ROOT)
        self.assertEqual(bundle["qualification"]["qualification"], "HOLD_PACKET_REQUIRED")
        self.assertEqual(bundle["demo_count"], 2)
        self.assertEqual(public_facts()["bid_number"], BID_NUMBER)
        for result in bundle["demo_results"]:
            self.assertEqual(result["label"], "DEMO_CAPABILITY")
            self.assertTrue(result["not_a_buyer_requirement"])
            self.assertEqual(len(result["resident_id"]), 64)
            self.assertFalse(result["revenue_recognized"])
        holiday = next(r for r in bundle["demo_results"] if r["case_id"] == "demo-holiday-skip")
        self.assertTrue(holiday["holiday_applied"])
        self.assertTrue(all(row["status"] == "SKIPPED_EXCEPTION" for row in holiday["schedule"]))
        verify_demo(cases[0], evaluate_demo_case(cases[0]))
    def test_demo_cannot_clear_packet_hold(self):
        bundle = compile_bundle(load_fixture_cases())
        self.assertEqual(bundle["qualification"]["qualification"], "HOLD_PACKET_REQUIRED")
        self.assertFalse(bundle["qualification"]["demo_satisfies_unknown_mandatory"])
        self.assertEqual(len(DEMO_CAPABILITIES), 9)
    def test_hostile_key_and_type_mutations(self):
        case = deepcopy(load_fixture_cases()[0])
        bad = deepcopy(case); bad["extra"] = "nope"
        with self.assertRaises(ContractError):
            evaluate_demo_case(bad)
        bad2 = deepcopy(case); bad2["exception_streams"] = ["nuclear"]
        with self.assertRaises(ContractError):
            evaluate_demo_case(bad2)
        bad3 = deepcopy(case); bad3["as_of_utc"] = "tomorrow"
        with self.assertRaises(ContractError):
            evaluate_demo_case(bad3)
        claimed = evaluate_demo_case(case); claimed["receipt_sha256"] = "f" * 64
        with self.assertRaises(ContractError):
            verify_demo(case, claimed)
    def test_duplicate_case_ids_fail(self):
        case = load_fixture_cases()[0]
        with self.assertRaises(ContractError):
            compile_bundle([case, deepcopy(case)])
    def test_path_is_isolated(self):
        self.assertTrue(str(ROOT).endswith("abbotsford_1220_2026_4235"))
        self.assertTrue((ROOT / "abbotsford_1220.py").is_file())
class ManifestTests(unittest.TestCase):
    def test_manifest_and_gap_brief_exist(self):
        manifest = load_strict_json((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["qualification"], "HOLD_PACKET_REQUIRED")
        brief = (ROOT / "gap_brief.md").read_text(encoding="utf-8")
        self.assertIn("HOLD_PACKET_REQUIRED", brief)
        self.assertIn("Appendix B", brief)
if __name__ == "__main__":
    unittest.main()
