#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import americaninj_lims as lims

FIXTURE = HERE / "fixtures" / "americaninj_120_records.json"


class AmericanInjectablesLineageTests(unittest.TestCase):
    def setUp(self):
        self.records = lims.load_fixture(FIXTURE)
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def first_run(self):
        return lims.process_records(self.records, self.ledger)

    def load_ledger(self):
        return json.loads(self.ledger.read_text(encoding="utf-8"))

    def test_01_fixture_shape_and_seeded_cohorts(self):
        self.assertEqual(len(self.records), 120)
        self.assertEqual(len({r["submission_id"] for r in self.records}), 120)
        # The first 90 are the intended valid control cohort.
        self.assertTrue(all(r["ipc_fill_pass"] and r["sterility_qc_pass"] for r in self.records[:90]))

    def test_02_first_run_exact_totals(self):
        summary = self.first_run()
        self.assertEqual(summary["delta"]["ready"], 90)
        self.assertEqual(summary["delta"]["hold"], 30)
        self.assertEqual(summary["delta"]["scheduled_jobs"], 100)
        self.assertEqual(summary["delta"]["staged_dossiers"], 90)
        self.assertEqual(summary["totals"]["processed_records"], 120)

    def test_03_hold_code_counts_are_exact(self):
        summary = self.first_run()
        self.assertEqual(
            summary["delta"]["hold_codes"],
            {
                "CONTAINER_LINE_MISMATCH": 7,
                "DUPLICATE_PROGRAM_BATCH_ID": 8,
                "IPC_FILL_FAILURE": 5,
                "MISSING_FORMULATION_OR_METHOD_VERSION": 5,
                "STERILITY_QC_FAILURE": 5,
            },
        )

    def test_04_twenty_intake_defects_never_schedule(self):
        self.first_run()
        ledger = self.load_ledger()
        intake_holds = [
            item for item in ledger["submissions"].values()
            if item["hold_code"] in lims.INTAKE_HOLDS
        ]
        self.assertEqual(len(intake_holds), 20)
        self.assertTrue(all(not item["scheduled"] for item in intake_holds))
        self.assertTrue(all(item["submission_id"] not in ledger["jobs"] for item in intake_holds))

    def test_05_ten_post_intake_failures_schedule_but_never_stage(self):
        self.first_run()
        ledger = self.load_ledger()
        post = [
            item for item in ledger["submissions"].values()
            if item["hold_code"] in lims.POST_INTAKE_HOLDS
        ]
        self.assertEqual(len(post), 10)
        self.assertTrue(all(item["scheduled"] for item in post))
        self.assertTrue(all(item["submission_id"] in ledger["jobs"] for item in post))
        self.assertTrue(all(item["submission_id"] not in ledger["dossiers"] for item in post))

    def test_06_no_held_record_has_a_dossier(self):
        self.first_run()
        ledger = self.load_ledger()
        held = {
            sid for sid, item in ledger["submissions"].items()
            if item["status"] == "HOLD"
        }
        self.assertTrue(held.isdisjoint(ledger["dossiers"]))

    def test_07_ready_lineage_fields_and_hashes_match_source(self):
        self.first_run()
        ledger = self.load_ledger()
        by_sid = {r["submission_id"]: r for r in self.records}
        self.assertEqual(len(ledger["dossiers"]), 90)
        for sid, dossier in ledger["dossiers"].items():
            record = by_sid[sid]
            self.assertEqual(dossier["lineage"], lims.evidence_payload(record))
            self.assertEqual(dossier["lineage_sha256"], record["source_sha256"])
            self.assertEqual(dossier["state"], "STAGED_HUMAN_REVIEW")

    def test_08_full_replay_adds_zero_effects(self):
        first = self.first_run()
        before = self.ledger.read_bytes()
        second = lims.process_records(self.records, self.ledger)
        after = self.ledger.read_bytes()
        self.assertEqual(second["new_records"], 0)
        self.assertEqual(second["replayed"], 120)
        self.assertEqual(second["delta"]["scheduled_jobs"], 0)
        self.assertEqual(second["delta"]["staged_dossiers"], 0)
        self.assertEqual(first["totals"], second["totals"])
        self.assertEqual(before, after)

    def test_08b_changed_content_same_id_fails_closed_without_mutation(self):
        self.first_run()
        before = self.ledger.read_bytes()
        changed = copy.deepcopy(self.records[0])
        changed["material_lot"] = "MAT-CHANGED"
        changed["source_sha256"] = lims.evidence_sha256(changed)
        with self.assertRaisesRegex(ValueError, "replay payload mismatch"):
            lims.process_records([changed], self.ledger)
        self.assertEqual(before, self.ledger.read_bytes())

    def test_08c_unbound_legacy_replay_fails_closed_without_mutation(self):
        self.first_run()
        ledger = self.load_ledger()
        del ledger["submissions"]["SUB-000"]["record_sha256"]
        self.ledger.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        before = self.ledger.read_bytes()
        with self.assertRaisesRegex(ValueError, "replay payload mismatch"):
            lims.process_records([self.records[0]], self.ledger)
        self.assertEqual(before, self.ledger.read_bytes())

    def test_09_tampered_source_hash_aborts_before_write(self):
        tampered = copy.deepcopy(self.records)
        tampered[0]["material_lot"] = "TAMPERED"
        with self.assertRaisesRegex(ValueError, "source hash mismatch"):
            lims.process_records(tampered, self.ledger)
        self.assertFalse(self.ledger.exists())

    def test_10_release_requires_named_human_flag(self):
        self.first_run()
        with self.assertRaises(PermissionError):
            lims.release_dossier("SUB-000", self.ledger, human_name="Reviewer One", named_human=False)

    def test_11_release_rejects_reserved_actor_variants_without_mutation(self):
        self.first_run()
        before = self.ledger.read_bytes()
        for actor in ("", "system", "agent", "bot", "auto", " System Reviewer ", "BOT-Reviewer", "a-u-t-o", "AI Reviewer", "service_account", None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionError):
                    lims.release_dossier("SUB-000", self.ledger, human_name=actor, named_human=True)  # type: ignore[arg-type]
                self.assertEqual(before, self.ledger.read_bytes())

    def test_12_named_human_can_release_ready_dossier(self):
        self.first_run()
        dossier = lims.release_dossier(
            "SUB-000",
            self.ledger,
            human_name="Reviewer One",
            named_human=True,
        )
        self.assertEqual(dossier["state"], "RELEASED")
        self.assertEqual(dossier["released_by"], "Reviewer One")

    def test_13_held_record_can_never_release(self):
        self.first_run()
        with self.assertRaisesRegex(ValueError, "held submissions"):
            lims.release_dossier(
                "SUB-090",
                self.ledger,
                human_name="Reviewer One",
                named_human=True,
            )

    def test_14_cli_runs_fixture_and_emits_exact_summary(self):
        cli_ledger = Path(self.tmp.name) / "cli-ledger.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-B",
                str(HERE / "americaninj_lims.py"),
                str(FIXTURE),
                "--ledger",
                str(cli_ledger),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["totals"]["ready"], 90)
        self.assertEqual(summary["totals"]["hold"], 30)
        self.assertEqual(summary["totals"]["scheduled_jobs"], 100)
        self.assertEqual(summary["totals"]["staged_or_released_dossiers"], 90)


if __name__ == "__main__":
    unittest.main(verbosity=2)
