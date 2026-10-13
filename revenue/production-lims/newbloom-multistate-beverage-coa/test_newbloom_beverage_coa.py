import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import newbloom_beverage_coa as nb


class NewBloomBeverageCoATests(unittest.TestCase):
    def setUp(self):
        self.records, self.manifest = nb.load_fixture()

    def test_exact_truth_set_72_ready_24_hold(self):
        shadow = nb.NewBloomBeverageCoAShadow()
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual(72, report.ready)
        self.assertEqual(24, report.hold)
        self.assertEqual({
            "DUPLICATE_BATCH_ID": 4,
            "HOMOGENEITY_EXCEPTION": 4,
            "MISSING_PH_OR_STORAGE_METADATA": 8,
            "RULE_PACK_VERSION_MISMATCH": 8,
        }, report.hold_counts)
        self.assertEqual((72, 72 * 8, 24, 96), (
            report.packets_added, report.drafts_added, report.holds_added, report.events_added,
        ))

    def test_fixture_has_exactly_12_rows_per_configured_state_pack(self):
        counts = Counter(record["submitted_state_pack"] for record in self.records)
        self.assertEqual({pack: 12 for pack in nb.STATE_PACKS}, dict(counts))

    def test_every_ready_packet_preserves_source_and_analyte_unit_loq_across_all_drafts(self):
        shadow = nb.NewBloomBeverageCoAShadow()
        shadow.replay(self.records, self.manifest)
        self.assertEqual(72, len(shadow.staged_packets))
        for packet in shadow.staged_packets.values():
            self.assertEqual(8, len(packet["drafts"]))
            self.assertEqual(set(nb.STATE_PACKS), {draft["state_pack"] for draft in packet["drafts"]})
            self.assertEqual({packet["source_result_sha256"]}, {draft["source_result_sha256"] for draft in packet["drafts"]})
            self.assertEqual({packet["result_schema_sha256"]}, {draft["result_schema_sha256"] for draft in packet["drafts"]})
            for draft in packet["drafts"]:
                self.assertEqual("NOT_EVALUATED", draft["compliance_status"])
                self.assertEqual("STAGED_HUMAN_REVIEW", draft["state"])
                self.assertFalse(draft["sent"])

    def test_each_hold_family_is_exact_and_has_zero_downstream_state(self):
        shadow = nb.NewBloomBeverageCoAShadow()
        report = shadow.replay(self.records, self.manifest)
        expected = {
            "MISSING_PH_OR_STORAGE_METADATA": {f"NB-REC-{i:04d}" for i in range(73, 81)},
            "RULE_PACK_VERSION_MISMATCH": {f"NB-REC-{i:04d}" for i in range(81, 89)},
            "DUPLICATE_BATCH_ID": {f"NB-REC-{i:04d}" for i in range(89, 93)},
            "HOMOGENEITY_EXCEPTION": {f"NB-REC-{i:04d}" for i in range(93, 97)},
        }
        for code, ids in expected.items():
            actual = {outcome["record_id"] for outcome in report.outcomes if outcome.get("hold_code") == code}
            self.assertEqual(ids, actual)
            for record_id in ids:
                self.assertNotIn(record_id, shadow.staged_packets)
                self.assertEqual(0, shadow.holds[record_id]["packets_created"])
                self.assertEqual(0, shadow.holds[record_id]["drafts_created"])

    def test_duplicate_batch_holds_point_back_to_first_four_clean_batches(self):
        duplicate_records = [record for record in self.records if record["truth_hold"] == "DUPLICATE_BATCH_ID"]
        self.assertEqual([f"NB-BATCH-{i:04d}" for i in range(1, 5)], [record["batch_id"] for record in duplicate_records])
        shadow = nb.NewBloomBeverageCoAShadow()
        shadow.replay(self.records, self.manifest)
        self.assertTrue(all(record["record_id"] in shadow.holds for record in duplicate_records))

    def test_full_replay_is_zero_add_and_state_stable(self):
        shadow = nb.NewBloomBeverageCoAShadow()
        first = shadow.replay(self.records, self.manifest)
        digest = first.state_digest
        second = shadow.replay(self.records, self.manifest)
        self.assertEqual(96, second.replayed)
        self.assertEqual((0, 0, 0, 0), (
            second.packets_added, second.drafts_added, second.holds_added, second.events_added,
        ))
        self.assertEqual(digest, second.state_digest)

    def test_authoritative_state_is_read_only(self):
        authoritative = {"vendor": {"records": 123}, "mode": "production-read-only"}
        before = copy.deepcopy(authoritative)
        shadow = nb.NewBloomBeverageCoAShadow(authoritative)
        fingerprint = shadow.authoritative_fingerprint
        shadow.replay(self.records, self.manifest)
        self.assertEqual(before, authoritative)
        self.assertEqual(fingerprint, shadow.authoritative_fingerprint)

    def test_named_human_plus_approval_release_is_copy_only(self):
        shadow = nb.NewBloomBeverageCoAShadow()
        shadow.replay(self.records, self.manifest)
        record_id = next(iter(shadow.staged_packets))
        before = copy.deepcopy(shadow.staged_packets[record_id])
        for bad_name in (
            "", "auto", "system", "bot", "service-account", "AI", "Jordan",
            "System Reviewer", "AI Reviewer", "Bot Reviewer",
            "system/reviewer", "pipeline_reviewer", "service-account reviewer",
            "Worker.Reviewer",
        ):
            with self.assertRaises(PermissionError):
                shadow.release_packet(record_id, bad_name, "APR-SYN-0001")
        for bad_approval in ("", "A", "APPROVED", "APR 0001", "APR-"):
            with self.assertRaises(PermissionError):
                shadow.release_packet(record_id, "Jordan Reviewer", bad_approval)
        released = shadow.release_packet(record_id, "Jordan Reviewer", "APR-SYN-0001")
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", released["state"])
        self.assertEqual("Jordan Reviewer", released["released_by"])
        self.assertEqual("APR-SYN-0001", released["approval_id"])
        self.assertFalse(released["sent"])
        self.assertTrue(all(draft["state"] == "RELEASED_BY_NAMED_HUMAN" for draft in released["drafts"]))
        self.assertEqual(before, shadow.staged_packets[record_id])
        with self.assertRaises(PermissionError):
            shadow.automatic_release(record_id)
        shadow.staged_packets[record_id]["released_by"] = "Already Released"
        with self.assertRaises(PermissionError) as ineligible:
            shadow.release_packet(record_id, "Jordan Reviewer", "APR-SYN-0001")
        self.assertIn("release", str(ineligible.exception).casefold())

    def test_manifest_fixture_and_expanded_records_fail_closed_on_tamper(self):
        module_dir = Path(nb.__file__).resolve().parent
        fixture = module_dir / "fixtures" / "newbloom_96_batches.json"
        manifest = json.loads((module_dir / "fixtures" / "manifest.json").read_text())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            bad_fixture = tmp / "fixture.json"
            bad_fixture.write_text(fixture.read_text().replace('"clean_count":72', '"clean_count":71'))
            with self.assertRaises(nb.IntegrityError):
                nb.load_fixture(bad_fixture, module_dir / "fixtures" / "manifest.json")

            bad_manifest = dict(manifest)
            bad_manifest["expected_ready"] = 71
            bad_manifest_path = tmp / "manifest.json"
            bad_manifest_path.write_text(json.dumps(bad_manifest, sort_keys=True))
            with self.assertRaises(nb.IntegrityError):
                nb.load_fixture(fixture, bad_manifest_path)

            records = copy.deepcopy(self.records)
            records[0]["results"][0]["unit"] = "DRIFTED"
            with self.assertRaises(nb.IntegrityError):
                nb.verify_records(records, manifest)

    def test_runtime_acceptance_summary(self):
        result = nb.run_acceptance()
        self.assertEqual(72, result["ready"])
        self.assertEqual(24, result["hold"])
        self.assertEqual(72, result["packets"])
        self.assertEqual(576, result["drafts"])
        self.assertEqual(96, result["replayed"])
        self.assertTrue(result["replay_zero_add"])
        self.assertEqual("RELEASED_BY_NAMED_HUMAN", result["release_state"])
        self.assertEqual("APR-SYN-0001", result["release_approval_id"])
        self.assertFalse(result["sent"])
        self.assertEqual(1, result["draft_source_hash_count"])
        self.assertEqual(1, result["draft_schema_hash_count"])


if __name__ == "__main__":
    unittest.main()
