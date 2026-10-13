from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acceptance import build_cutover_gate, build_uat_packet, evaluate_interface_replay, ingest, normalize_record, reconcile_migration

FIX = json.loads((ROOT / "fixtures" / "synthetic.json").read_text())

class ErpEvidenceTests(unittest.TestCase):
    def test_normalize_deterministic(self):
        a = normalize_record(FIX["source"][0])
        b = normalize_record(dict(reversed(list(FIX["source"][0].items()))))
        self.assertEqual(a, b)

    def test_rejects_naive_time(self):
        row = copy.deepcopy(FIX["source"][0]); row["effective_at"] = "2026-01-01T00:00:00"
        with self.assertRaisesRegex(ValueError, "timezone"): normalize_record(row)

    def test_rejects_raw_sensitive_fixture_field(self):
        row = copy.deepcopy(FIX["source"][-1]); row["attributes"]["ssn"] = "000-00-0000"
        with self.assertRaisesRegex(ValueError, "sensitive fixture"): normalize_record(row)

    def test_rejects_nested_raw_sensitive_fixture_field(self):
        row = copy.deepcopy(FIX["source"][-1])
        row["attributes"]["nested"] = [{"profile": {"ssn": "000-00-0000"}}]
        with self.assertRaisesRegex(ValueError, "sensitive fixture"): normalize_record(row)

    def test_rejects_non_scalar_unicode(self):
        row = copy.deepcopy(FIX["source"][0]); row["source_id"] = "bad\ud800"
        with self.assertRaisesRegex(ValueError, "scalar Unicode"): normalize_record(row)

    def test_duplicate_stable_id_fails(self):
        with self.assertRaisesRegex(ValueError, "duplicate stable record"):
            ingest([FIX["source"][0], FIX["source"][0]])

    def test_exact_migration_passes_and_totals_conserve(self):
        result = reconcile_migration(FIX["source"], FIX["target"])
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["totals_match"])
        self.assertEqual(len(result["matched"]), 4)

    def test_changed_amount_is_review_required(self):
        target = copy.deepcopy(FIX["target"]); target[0]["amount"] = "1251"
        result = reconcile_migration(FIX["source"], target)
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["totals_match"])
        self.assertEqual(len(result["changed"]), 1)

    def test_missing_row_is_review_required(self):
        result = reconcile_migration(FIX["source"], FIX["target"][:-1])
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(len(result["missing"]), 1)

    def test_timeout_then_commit_replay_passes(self):
        result = evaluate_interface_replay(FIX["events"])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["requests"], 2)

    def test_duplicate_commit_fails(self):
        events = copy.deepcopy(FIX["events"])
        events.append({"request_id":"req-002","interface":"benefits-sync","payload_hash":"b"*64,"attempt":3,"committed":True,"response":"200"})
        result = evaluate_interface_replay(events)
        self.assertEqual(result["status"], "review_required")
        self.assertIn("req-002:duplicate_commit", result["violations"])

    def test_replay_identity_change_fails(self):
        events = copy.deepcopy(FIX["events"]); events[-1]["payload_hash"] = "f"*64
        self.assertIn("req-002:replay_identity_changed", evaluate_interface_replay(events)["violations"])

    def test_replay_types_fail_closed(self):
        events = copy.deepcopy(FIX["events"]); events[0]["attempt"] = 1.5
        with self.assertRaisesRegex(TypeError, "attempt must be an integer"): evaluate_interface_replay(events)
        events = copy.deepcopy(FIX["events"]); events[0]["committed"] = "false"
        with self.assertRaisesRegex(TypeError, "committed must be a boolean"): evaluate_interface_replay(events)

    def test_uat_duplicate_scenario_fails(self):
        with self.assertRaisesRegex(ValueError, "duplicate scenario_id"):
            build_uat_packet(FIX["uat"] + [copy.deepcopy(FIX["uat"][0])])

    def test_cutover_recomputes_raw_inputs_and_never_grants_external_authority(self):
        gate = build_cutover_gate(FIX["source"], FIX["target"], FIX["events"], FIX["uat"])
        self.assertTrue(gate["ready_for_owner_review"])
        self.assertEqual(gate["input_authority"], "caller_supplied_evidence_only")
        self.assertFalse(gate["production_cutover_authority"])
        self.assertFalse(gate["county_submission_authority"])
        self.assertEqual(gate["release_authority"], "owner_review_required")

        target = copy.deepcopy(FIX["target"]); target[0]["amount"] = "1251"
        bad_gate = build_cutover_gate(FIX["source"], target, FIX["events"], FIX["uat"])
        self.assertFalse(bad_gate["ready_for_owner_review"])

    def test_cutover_does_not_accept_precompiled_status_packets(self):
        fake = {"status": "pass", "evidence_hash": "a"*64}
        with self.assertRaises(TypeError):
            build_cutover_gate(fake, fake, fake, fake)

if __name__ == "__main__":
    unittest.main()
