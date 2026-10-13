from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
import sys

HERE = pathlib.Path(__file__).resolve().parent
MODULE_PATH = HERE / "mvmtc_fastener_evidence.py"
spec = importlib.util.spec_from_file_location("mvmtc_fastener_evidence", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class MvmtcFastenerEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records, self.manifest = mod.load_fixture()

    def test_fixture_and_manifest_are_frozen_and_exact(self) -> None:
        self.assertEqual(len(self.records), 100)
        self.assertEqual(self.manifest["expected_ready"], 75)
        self.assertEqual(self.manifest["expected_hold"], 25)
        self.assertEqual(
            self.manifest["expected_hold_codes"],
            {
                "MISSING_PO_QUOTE_LINK": 8,
                "DUPLICATE_CONTAINER": 5,
                "METHOD_OUT_OF_SCOPE": 4,
                "CHEMISTRY_MATERIAL_MISMATCH": 4,
                "QC_FAIL": 4,
            },
        )
        mod.verify_records(self.records, self.manifest)

    def test_exact_acceptance_distribution_and_no_hold_worksheet(self) -> None:
        shadow = mod.MvmtcEvidenceShadow()
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual((report.ready, report.hold, report.replayed), (75, 25, 0))
        self.assertEqual(report.hold_counts, self.manifest["expected_hold_codes"])
        self.assertEqual(len(shadow.lots), 75)
        self.assertEqual(len(shadow.jobs), 75)
        self.assertEqual(len(shadow.worksheets), 75)
        self.assertEqual(len(shadow.evidence_packs), 75)
        self.assertEqual(len(shadow.holds), 25)
        for lot_id, hold in shadow.holds.items():
            self.assertNotIn(lot_id, shadow.jobs)
            self.assertNotIn(lot_id, shadow.worksheets)
            self.assertNotIn(lot_id, shadow.evidence_packs)
            self.assertFalse(hold["worksheet_created"])
            self.assertFalse(hold["evidence_pack_created"])

    def test_ready_records_preserve_all_required_lineage_hashes(self) -> None:
        shadow = mod.MvmtcEvidenceShadow()
        shadow.replay(self.records, self.manifest)
        by_id = {record["lot_id"]: record for record in self.records}
        for lot_id, pack in shadow.evidence_packs.items():
            record = by_id[lot_id]
            self.assertEqual(pack["status"], "STAGED_HUMAN_REVIEW")
            self.assertIsNone(pack["released_by"])
            for key in (
                "source_sha256",
                "scope_method_sha256",
                "specimen_sha256",
                "raw_value_unit_sha256",
            ):
                self.assertEqual(pack[key], record[key])
                self.assertEqual(shadow.jobs[lot_id][key], record[key])
                self.assertEqual(shadow.worksheets[lot_id][key], record[key])

    def test_full_replay_is_idempotent_and_state_digest_stable(self) -> None:
        shadow = mod.MvmtcEvidenceShadow()
        first = shadow.replay(self.records, self.manifest)
        second = shadow.replay(self.records, self.manifest)
        self.assertEqual(second.replayed, 100)
        self.assertEqual(
            (
                second.lots_added,
                second.jobs_added,
                second.worksheets_added,
                second.evidence_packs_added,
                second.holds_added,
                second.events_added,
            ),
            (0, 0, 0, 0, 0, 0),
        )
        self.assertEqual(first.state_digest, second.state_digest)

    def test_named_human_release_is_required(self) -> None:
        shadow = mod.MvmtcEvidenceShadow()
        shadow.replay(self.records, self.manifest)
        lot_id = sorted(shadow.evidence_packs)[0]
        before = shadow.state_digest()
        for bad in (
            "", "auto", "system", "bot", "x",
            "System Reviewer", "AI Reviewer", "Bot Reviewer", "service account",
            "agent007 reviewer", "pipeline/reviewer", None, 42,
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    shadow.release_evidence_pack(lot_id, bad)
                self.assertEqual(before, shadow.state_digest())
        released = shadow.release_evidence_pack(lot_id, "A. Reviewer")
        self.assertEqual(released["status"], "RELEASED_HUMAN_REVIEW")
        self.assertEqual(released["released_by"], "A. Reviewer")
        self.assertTrue(released["release_event_sha256"])
        with self.assertRaises(ValueError):
            shadow.release_evidence_pack(lot_id, "Second Reviewer")

    def test_tamper_detection_rejects_record_and_manifest_changes(self) -> None:
        records = copy.deepcopy(self.records)
        records[0]["raw_value"] += 1
        with self.assertRaises(mod.IntegrityError):
            mod.verify_records(records, self.manifest)

        manifest = copy.deepcopy(self.manifest)
        manifest["expected_ready"] = 74
        with self.assertRaises(mod.IntegrityError):
            mod.verify_manifest_signature(manifest)

    def test_fixture_file_tamper_is_rejected(self) -> None:
        fixture = HERE / "fixtures" / "mvmtc_100_lots.json"
        manifest = HERE / "fixtures" / "manifest.json"
        with tempfile.TemporaryDirectory() as td:
            bad = pathlib.Path(td) / "fixture.json"
            bad.write_text(fixture.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaises(mod.IntegrityError):
                mod.load_fixture(bad, manifest)

    def test_authoritative_state_is_read_only_and_restricted_fields_absent(self) -> None:
        authoritative = {"external": {"version": 7, "records": [1, 2, 3]}}
        original = copy.deepcopy(authoritative)
        shadow = mod.MvmtcEvidenceShadow(authoritative)
        shadow.replay(self.records, self.manifest)
        self.assertEqual(shadow.authoritative_state, original)
        for record in self.records:
            self.assertFalse(
                set(self.manifest["restricted_payload_fields"]).intersection(record),
                record["lot_id"],
            )

    def test_default_cli_summary_is_truthful(self) -> None:
        summary = mod.run_default()
        self.assertEqual((summary["ready"], summary["hold"]), (75, 25))
        self.assertEqual(summary["worksheets"], 75)
        self.assertEqual(summary["staged_evidence_packs"], 75)
        self.assertEqual(summary["replay"]["replayed"], 100)
        self.assertTrue(summary["replay"]["state_unchanged"])
        self.assertEqual(summary["release_policy"], "NAMED_HUMAN_ONLY")
        self.assertEqual(summary["production_writes"], 0)
        self.assertEqual(summary["controlled_payloads"], 0)


if __name__ == "__main__":
    unittest.main()
