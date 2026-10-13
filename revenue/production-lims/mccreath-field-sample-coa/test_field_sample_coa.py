#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "field_sample_coa.py"
FIXTURE = HERE / "fixtures" / "mccreath_100_jobs.json"
MANIFEST = HERE / "fixtures" / "manifest.json"

spec = importlib.util.spec_from_file_location("mccreath_field_sample_coa", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class McCreathFieldSampleCoATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = mod.load_fixture(FIXTURE)
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def fresh_run(self):
        return mod.process_fixture(self.rows)

    def test_01_fixture_manifest_hash_and_count(self):
        self.assertEqual(len(self.rows), 100)
        self.assertEqual(mod.file_sha256(FIXTURE), self.manifest["fixture_sha256"])
        self.assertEqual(self.manifest["row_count"], 100)

    def test_02_exact_status_and_hold_distribution(self):
        run = self.fresh_run()
        self.assertEqual(run["status_counts"], {mod.READY: 75, mod.HOLD: 25})
        self.assertEqual(run["hold_counts"], mod.EXPECTED_HOLDS)

    def test_03_unique_accessions_and_no_duplicate_container_land(self):
        ledger = self.fresh_run()["ledger"]
        self.assertEqual(len(ledger.accessions), 75)
        self.assertEqual(len(set(ledger.accessions)), 75)
        self.assertEqual(len(ledger.container_to_accession), 75)
        self.assertEqual(len(set(ledger.container_to_accession)), 75)

    def test_04_zero_orphan_preparation_splits(self):
        ledger = self.fresh_run()["ledger"]
        self.assertEqual(len(ledger.splits), 75)
        self.assertTrue(
            all(s["accession_id"] in ledger.accessions for s in ledger.splits.values())
        )

    def test_05_result_identity_matches_golden_fixture(self):
        ledger = self.fresh_run()["ledger"]
        expected = {
            row["job_id"]: row["golden_result_hash"]
            for row in self.rows
            if row["expected_status"] == mod.READY
        }
        observed = {
            result["accession_id"].removeprefix("ACC-"): result["result_hash"]
            for result in ledger.results.values()
        }
        self.assertEqual(observed, expected)
        for row in self.rows:
            if row["expected_status"] != mod.READY:
                continue
            result = ledger.results[f"RESULT-{row['job_id']}-A"]
            self.assertEqual(result["value"], row["analytical_result"]["value"])
            self.assertEqual(result["unit"], row["analytical_result"]["unit"])
            self.assertEqual(result["rounding"], row["analytical_result"]["rounding"])
            self.assertEqual(result["source_hash"], row["analytical_result"]["source_hash"])

    def test_06_all_coas_are_staged_human_review(self):
        ledger = self.fresh_run()["ledger"]
        self.assertEqual(len(ledger.coas), 75)
        self.assertTrue(
            all(c["state"] == mod.STAGED_HUMAN_REVIEW for c in ledger.coas.values())
        )
        self.assertTrue(all(c["released_by"] is None for c in ledger.coas.values()))

    def test_07_anonymous_release_is_denied_without_mutation(self):
        ledger = self.fresh_run()["ledger"]
        coa_id = sorted(ledger.coas)[0]
        before = ledger.snapshot_hash()
        with self.assertRaises(PermissionError):
            mod.release_coa(ledger, coa_id, reviewer="", approval_id="")
        self.assertEqual(ledger.snapshot_hash(), before)

    def test_08_named_human_release_requires_both_fields(self):
        ledger = self.fresh_run()["ledger"]
        coa_id = sorted(ledger.coas)[0]
        with self.assertRaises(PermissionError):
            mod.release_coa(ledger, coa_id, reviewer="QA Reviewer", approval_id="")
        released = mod.release_coa(
            ledger,
            coa_id,
            reviewer="QA Reviewer",
            approval_id="APPROVAL-SYNTHETIC-001",
        )
        self.assertEqual(released["state"], mod.RELEASED)
        self.assertEqual(released["released_by"], "QA Reviewer")

    def test_09_full_fixture_replay_is_zero_mutation(self):
        first = self.fresh_run()
        ledger = first["ledger"]
        before_counts = ledger.mutation_counts()
        before_hash = ledger.snapshot_hash()
        replay = mod.process_fixture(self.rows, ledger)
        self.assertEqual(replay["idempotent_replays"], 100)
        self.assertEqual(replay["delta"], {k: 0 for k in before_counts})
        self.assertEqual(ledger.mutation_counts(), before_counts)
        self.assertEqual(ledger.snapshot_hash(), before_hash)

    def test_10_fixture_order_reproduces_predetermined_duplicate_holds(self):
        ledger = mod.Ledger()
        outcomes = [mod.process_job(row, ledger) for row in self.rows]
        dup_jobs = [
            o["job_id"]
            for o in outcomes
            if o["hold_code"] == mod.HOLD_DUPLICATE_CONTAINER
        ]
        self.assertEqual(dup_jobs, [f"MCC-{i:04d}" for i in range(86, 91)])

    def test_11_contract_verifier_summary(self):
        summary = mod.verify_contract(self.rows, self.manifest)
        self.assertEqual(summary["ready"], 75)
        self.assertEqual(summary["hold"], 25)
        self.assertEqual(summary["accessions"], 75)
        self.assertEqual(summary["splits"], 75)
        self.assertEqual(summary["results"], 75)
        self.assertEqual(summary["staged_coas"], 75)
        self.assertEqual(summary["replay_idempotent"], 100)
        self.assertEqual(
            summary["replay_delta"],
            {
                "accessions": 0,
                "splits": 0,
                "results": 0,
                "coas": 0,
                "holds": 0,
                "events": 0,
            },
        )

    def test_12_cli_verify(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--fixture",
                str(FIXTURE),
                "--manifest",
                str(MANIFEST),
                "--verify",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["ready"], 75)
        self.assertEqual(summary["hold"], 25)

    def test_13_same_job_changed_payload_rejected_before_mutation(self):
        ledger = mod.Ledger()
        original = copy.deepcopy(self.rows[0])
        first = mod.process_job(original, ledger)
        self.assertEqual(first["status"], mod.READY)

        before_hash = ledger.snapshot_hash()
        before_counts = ledger.mutation_counts()
        changed = copy.deepcopy(original)
        changed["shipment"]["package_id"] = "PKG-CHANGED"

        with self.assertRaisesRegex(ValueError, "JOB_ID_PAYLOAD_MISMATCH"):
            mod.process_job(changed, ledger)
        self.assertEqual(ledger.snapshot_hash(), before_hash)
        self.assertEqual(ledger.mutation_counts(), before_counts)

        replay = mod.process_job(copy.deepcopy(original), ledger)
        self.assertTrue(replay["idempotent_replay"])

    def test_14_bad_golden_result_is_atomic_no_mutation(self):
        ledger = mod.Ledger()
        bad = copy.deepcopy(self.rows[0])
        bad["golden_result_hash"] = "0" * 64
        before_hash = ledger.snapshot_hash()
        before_counts = ledger.mutation_counts()

        with self.assertRaisesRegex(AssertionError, "golden result drift"):
            mod.process_job(bad, ledger)

        self.assertEqual(ledger.snapshot_hash(), before_hash)
        self.assertEqual(ledger.mutation_counts(), before_counts)

    def test_15_reserved_reviewer_labels_fail_closed_without_mutation(self):
        labels = [
            "auto reviewer",
            "System Reviewer",
            "AI Reviewer",
            "Bot Reviewer",
            "Service Account",
            "agent007 reviewer",
            "A-I Reviewer",
            "S Y S T E M Reviewer",
            "b.o.t Reviewer",
        ]
        for label in labels:
            with self.subTest(label=label):
                ledger = self.fresh_run()["ledger"]
                coa_id = sorted(ledger.coas)[0]
                before_hash = ledger.snapshot_hash()
                with self.assertRaises(PermissionError):
                    mod.release_coa(
                        ledger,
                        coa_id,
                        reviewer=label,
                        approval_id="APPROVAL-SYNTHETIC-001",
                    )
                self.assertEqual(ledger.snapshot_hash(), before_hash)

    def test_16_reviewer_gate_is_explicit_and_avoids_substring_false_positives(self):
        self.assertFalse(mod._named_human(None))
        self.assertFalse(mod._named_human("Jordan"))
        self.assertTrue(mod._named_human("Aisha Agentson"))
        self.assertTrue(mod._named_human("Serviceman Jones"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
