from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "wayne_smart_reconcile.py"
spec = importlib.util.spec_from_file_location("wayne_smart_reconcile", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class WayneSmartReconcileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.manifest = mod.load_fixture()

    def test_frozen_fixture_is_exact_150_state_truth_set(self):
        self.assertEqual(len(self.records), 150)
        self.assertEqual(
            self.manifest["expected_statuses"],
            {
                "RECONCILED": 120,
                "DUPLICATE_NOOP": 10,
                "HOLD_UNKNOWN_COMMIT": 10,
                "HOLD_UNAUTHORIZED": 10,
            },
        )
        mod.verify_manifest(self.manifest)
        mod.verify_records(self.records, self.manifest)

    def test_first_replay_classifies_all_150_exactly(self):
        shadow = mod.WayneSmartShadow()
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual(report.processed, 150)
        self.assertEqual(report.statuses, dict(sorted(self.manifest["expected_statuses"].items())))
        self.assertEqual(report.reconciled, 120)
        self.assertEqual(report.duplicate_noop, 10)
        self.assertEqual(report.holds, 20)
        self.assertEqual(len(shadow.staged_by_mutation), 120)
        self.assertEqual(len(shadow.holds), 20)
        self.assertEqual(len(shadow.events), 150)

    def test_duplicate_attempts_create_zero_duplicate_mutation_effects(self):
        shadow = mod.WayneSmartShadow()
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual(report.duplicate_mutation_effects, 0)
        duplicates = [r for r in self.records if r["truth_status"] == mod.DUPLICATE_NOOP]
        self.assertEqual(len(duplicates), 10)
        for record in duplicates:
            staged = shadow.staged_by_mutation[record["mutation_key"]]
            self.assertNotEqual(staged["record_id"], record["record_id"])
            self.assertEqual(staged["status"], "READ_ONLY_RECONCILED")

    def test_ledger_variance_is_exactly_zero_dollars(self):
        shadow = mod.WayneSmartShadow()
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual(report.ledger_variance_cents, 0)
        self.assertEqual(
            sum(
                staged["posted_cents"] - staged["expected_cents"]
                for staged in shadow.staged_by_mutation.values()
            ),
            0,
        )

    def test_unauthorized_principals_have_zero_protected_reads_or_effects(self):
        shadow = mod.WayneSmartShadow()
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual(report.unauthorized_reads_added, 0)
        unauthorized = [r for r in self.records if r["truth_status"] == mod.HOLD_UNAUTHORIZED]
        self.assertEqual(len(unauthorized), 10)
        for record in unauthorized:
            self.assertEqual(shadow.holds[record["record_id"]]["hold_code"], mod.HOLD_UNAUTHORIZED)
            self.assertFalse(shadow.holds[record["record_id"]]["protected_read"])
            self.assertNotIn(record["mutation_key"], {
                value["mutation_key"]
                for value in shadow.staged_by_mutation.values()
                if value["record_id"] == record["record_id"]
            })
        self.assertTrue(all(read["authorized"] is True for read in shadow.protected_reads))

    def test_all_unknown_commits_hold_before_protected_read(self):
        shadow = mod.WayneSmartShadow()
        shadow.replay(self.records, self.manifest)
        unknown = [r for r in self.records if r["truth_status"] == mod.HOLD_UNKNOWN_COMMIT]
        self.assertEqual(len(unknown), 10)
        read_ids = {read["record_id"] for read in shadow.protected_reads}
        for record in unknown:
            hold = shadow.holds[record["record_id"]]
            self.assertEqual(hold["hold_code"], mod.HOLD_UNKNOWN_COMMIT)
            self.assertFalse(hold["protected_read"])
            self.assertNotIn(record["record_id"], read_ids)

    def test_full_replay_adds_zero_state(self):
        shadow = mod.WayneSmartShadow()
        first = shadow.replay(self.records, self.manifest)
        counts = (
            len(shadow.staged_by_mutation),
            len(shadow.holds),
            len(shadow.events),
            len(shadow.protected_reads),
        )
        second = shadow.replay(copy.deepcopy(self.records), self.manifest)
        self.assertEqual(second.idempotent_replays, 150)
        self.assertEqual(
            (
                second.staged_effects_added,
                second.holds_added,
                second.events_added,
                second.protected_reads_added,
            ),
            (0, 0, 0, 0),
        )
        self.assertEqual(first.state_digest, second.state_digest)
        self.assertEqual(
            counts,
            (
                len(shadow.staged_by_mutation),
                len(shadow.holds),
                len(shadow.events),
                len(shadow.protected_reads),
            ),
        )

    def test_authoritative_state_is_never_mutated(self):
        authoritative = {"revision": 17, "ledger": {"synthetic": "authoritative"}}
        original = copy.deepcopy(authoritative)
        shadow = mod.WayneSmartShadow(authoritative)
        before = shadow.authoritative_digest()
        shadow.replay(self.records, self.manifest)
        self.assertEqual(shadow.authoritative_state, original)
        self.assertEqual(before, shadow.authoritative_digest())

    def test_fixture_and_record_tampering_fail_closed(self):
        fixture_path = HERE / "fixtures" / "wayne_150_states.json"
        manifest_path = HERE / "fixtures" / "manifest.json"
        with tempfile.TemporaryDirectory() as td:
            bad_fixture = Path(td) / "wayne_150_states.json"
            bad_fixture.write_text(fixture_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaises(mod.IntegrityError):
                mod.load_fixture(bad_fixture, manifest_path)

        bad_records = copy.deepcopy(self.records)
        bad_records[0]["posted_cents"] += 1
        with self.assertRaises(mod.IntegrityError):
            mod.verify_records(bad_records, self.manifest)

        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["expected_ledger_variance_cents"] = 1
        with self.assertRaises(mod.IntegrityError):
            mod.verify_manifest(bad_manifest)

    def test_forbidden_identity_fields_are_rejected(self):
        bad_records = copy.deepcopy(self.records)
        bad_records[0]["student_email"] = "synthetic@example.invalid"
        # Recompute expanded digest only to prove the field-level guard, then re-sign.
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["expanded_records_sha256"] = mod.sha_text(mod.canonical(bad_records))
        envelope = mod.manifest_envelope(bad_manifest)
        bad_manifest["signature"] = mod.sha_text(mod.PREFIX + mod.canonical(envelope))
        with self.assertRaisesRegex(mod.IntegrityError, "forbidden identity field"):
            mod.verify_records(bad_records, bad_manifest)

    def test_default_summary_matches_posted_acceptance(self):
        summary = mod.run_default()
        self.assertEqual(summary["records"], 150)
        self.assertEqual(summary["ledger_variance_cents"], 0)
        self.assertEqual(summary["duplicate_mutation_effects"], 0)
        self.assertEqual(summary["unauthorized_reads"], 0)
        self.assertEqual(summary["unknown_commits_held"], 10)
        self.assertEqual(summary["authoritative_writes"], 0)
        self.assertEqual(summary["replay"]["idempotent"], 150)
        self.assertTrue(summary["replay"]["state_unchanged"])


if __name__ == "__main__":
    unittest.main()
