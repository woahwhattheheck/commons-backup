from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "infinitecal_parity.py"
spec = importlib.util.spec_from_file_location("infinitecal_parity", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
import sys
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class InfiniteCALParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_path = HERE / "fixtures" / "infinitecal_180_records.json"
        cls.manifest_path = HERE / "fixtures" / "manifest.json"
        cls.records = mod.load_fixture(cls.fixture_path, cls.manifest_path)

    def first_run(self):
        result = mod.run_records(copy.deepcopy(self.records))
        mod.assert_acceptance(self.records, result)
        return result

    def test_fixture_hash_matches_manifest(self):
        manifest = mod.validate_fixture_hash(self.fixture_path, self.manifest_path)
        self.assertEqual(manifest["record_count"], 180)

    def test_exact_state_material_shape(self):
        self.assertEqual(len(self.records), 180)
        for state in mod.STATES:
            rows = [r for r in self.records if r["state"] == state]
            self.assertEqual(len(rows), 60)
            self.assertEqual(len({r["material_id"] for r in rows}), 20)
            self.assertEqual({r["canonical"]["analyte"] for r in rows}, {"ANALYTE_A", "ANALYTE_B", "ANALYTE_C"})

    def test_seeded_fault_truth_set(self):
        counts = {}
        for record in self.records:
            fault = record["seeded_fault"]
            if fault:
                counts[fault] = counts.get(fault, 0) + 1
        self.assertEqual(counts, {
            mod.METHOD_MISMATCH: 12,
            mod.UNIT_ROUNDING_MISMATCH: 9,
            mod.DUPLICATE_ACCESSION: 6,
            mod.MISSING_SOURCE_FILE: 3,
        })

    def test_exact_acceptance_counts(self):
        result = self.first_run()
        self.assertEqual(result["statuses"], {
            mod.CLEAN: 150,
            mod.METHOD_MISMATCH: 12,
            mod.UNIT_ROUNDING_MISMATCH: 9,
            mod.DUPLICATE_ACCESSION: 6,
            mod.MISSING_SOURCE_FILE: 3,
        })

    def test_ledger_counts(self):
        result = self.first_run()
        self.assertEqual(result["ledger"].counts(), {
            "processed": 180,
            "accepted": 150,
            "holds": 30,
            "drafts": 150,
            "events": 180,
        })

    def test_zero_cross_state_sample_swaps(self):
        for record in self.records:
            self.assertEqual(record["state_output"]["material_id"], record["material_id"])

    def test_clean_records_share_canonical_parity_hashes_across_states(self):
        result = self.first_run()
        ledger = result["ledger"]
        by_key = {}
        for record in self.records:
            if record["record_id"] not in ledger.drafts:
                continue
            key = (record["material_id"], record["canonical"]["analyte"])
            hashes = mod.parity_hashes(record)
            by_key.setdefault(key, set()).add((hashes["analyte_hash"], hashes["unit_hash"], hashes["loq_hash"]))
        self.assertTrue(by_key)
        self.assertTrue(all(len(values) == 1 for values in by_key.values()))

    def test_state_rule_and_method_lineage_is_retained(self):
        result = self.first_run()
        ledger = result["ledger"]
        for accepted in ledger.accepted_by_accession.values():
            self.assertRegex(accepted["rule_pack_id"], r"^(CA|MI|NY)-PARITY-RULES$")
            self.assertEqual(accepted["rule_pack_version"], "2026.09")
            self.assertEqual(len(accepted["lineage_hash"]), 64)

    def test_full_replay_adds_zero_mutations(self):
        result = self.first_run()
        before = result["ledger"].counts().copy()
        replay = mod.run_records(copy.deepcopy(self.records), result["ledger"])
        self.assertEqual(replay["delta"], {
            "processed": 0,
            "accepted": 0,
            "holds": 0,
            "drafts": 0,
            "events": 0,
        })
        self.assertEqual(result["ledger"].counts(), before)
        self.assertEqual(replay["statuses"], {"IDEMPOTENT_REPLAY": 180})

    def test_holds_never_stage_drafts(self):
        result = self.first_run()
        ledger = result["ledger"]
        self.assertTrue(set(ledger.holds).isdisjoint(ledger.drafts))
        self.assertEqual(len(ledger.holds), 30)

    def test_duplicate_accession_preserves_original(self):
        result = self.first_run()
        ledger = result["ledger"]
        duplicate_holds = [h for h in ledger.holds.values() if h["hold_code"] == mod.DUPLICATE_ACCESSION]
        self.assertEqual(len(duplicate_holds), 6)
        for hold in duplicate_holds:
            self.assertIn(hold["accession_id"], ledger.accepted_by_accession)

    def test_missing_source_file_fails_closed(self):
        result = self.first_run()
        ledger = result["ledger"]
        missing = [h for h in ledger.holds.values() if h["hold_code"] == mod.MISSING_SOURCE_FILE]
        self.assertEqual(len(missing), 3)
        for hold in missing:
            self.assertNotIn(hold["record_id"], ledger.drafts)

    def test_all_clean_drafts_are_staged_with_no_reviewer(self):
        result = self.first_run()
        for draft in result["ledger"].drafts.values():
            self.assertEqual(draft["status"], mod.STAGED)
            self.assertIsNone(draft["reviewer"])

    def test_anonymous_release_is_rejected(self):
        result = self.first_run()
        record_id = next(iter(result["ledger"].drafts))
        with self.assertRaisesRegex(ValueError, "NAMED_HUMAN_REVIEWER_REQUIRED"):
            mod.release_draft(result["ledger"], record_id, "")

    def test_reserved_automation_reviewer_identities_are_rejected(self):
        result = self.first_run()
        record_id = next(iter(result["ledger"].drafts))
        original = copy.deepcopy(result["ledger"].drafts[record_id])
        for reviewer in (
            "auto",
            "SYSTEM",
            "bot",
            "Auto Reviewer",
            "system.operator",
            "bot_user",
            "automation reviewer",
            "automated-reviewer",
            "robot reviewer",
            "AI Reviewer",
            "Agent Reviewer",
            "Service Account",
            "ai-reviewer",
            "agent.reviewer",
            "service_account",
            "AI2 Reviewer",
            "agent007 reviewer",
            "service2 account",
            "A I Reviewer",
            "A-I Reviewer",
            "a.i reviewer",
            "a_i reviewer",
            "S Y S T E M Reviewer",
            "s.y.s.t.e.m reviewer",
            "B O T Reviewer",
            "b.o.t reviewer",
            "S E R V I C E Account",
        ):
            with self.subTest(reviewer=reviewer):
                with self.assertRaisesRegex(ValueError, "NAMED_HUMAN_REVIEWER_REQUIRED"):
                    mod.release_draft(result["ledger"], record_id, reviewer)
                self.assertEqual(result["ledger"].drafts[record_id], original)

    def test_named_human_release_returns_copy_only(self):
        result = self.first_run()
        record_id = next(iter(result["ledger"].drafts))
        original = copy.deepcopy(result["ledger"].drafts[record_id])
        released = mod.release_draft(result["ledger"], record_id, "QA Reviewer")
        self.assertEqual(released["status"], mod.RELEASED)
        self.assertEqual(released["reviewer"], "QA Reviewer")
        self.assertEqual(result["ledger"].drafts[record_id], original)
        for reviewer in ("Aisha Reviewer", "Agentson Reviewer", "Serviceman Reviewer"):
            with self.subTest(reviewer=reviewer):
                released = mod.release_draft(result["ledger"], record_id, reviewer)
                self.assertEqual(released["reviewer"], reviewer)
                self.assertEqual(result["ledger"].drafts[record_id], original)

    def test_fixture_tamper_is_rejected(self):
        fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        manifest = self.manifest_path.read_text(encoding="utf-8")
        fixture["schema_version"] = fixture.get("schema_version", 1) + 1
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            fp = td / "fixture.json"
            mp = td / "manifest.json"
            fp.write_text(json.dumps(fixture, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
            mp.write_text(manifest, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "FIXTURE_HASH_MISMATCH"):
                mod.validate_fixture_hash(fp, mp)


if __name__ == "__main__":
    unittest.main()