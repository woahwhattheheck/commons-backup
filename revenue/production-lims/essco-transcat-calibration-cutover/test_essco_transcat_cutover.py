from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from essco_transcat_cutover import (  # noqa: E402
    CalibrationCutoverShadow,
    IntegrityError,
    assert_customer_isolation,
    load_fixture,
    verify_manifest_signature,
    verify_records,
)


class EsscoTranscatCutoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.manifest = load_fixture()
        cls.by_id = {record["history_id"]: record for record in cls.records}

    def test_frozen_manifest_and_truth_set_are_exact(self):
        self.assertEqual(500, len(self.records))
        self.assertEqual(400, self.manifest["expected_clean"])
        self.assertEqual(100, self.manifest["expected_hold"])
        self.assertEqual(
            Counter(self.manifest["expected_hold_codes"]),
            Counter(
                record["truth_hold"]
                for record in self.records
                if record["truth_hold"] is not None
            ),
        )
        verify_manifest_signature(self.manifest)
        verify_records(self.records, self.manifest)

        fixture_text = (HERE / "fixtures" / "essco_transcat_500_histories.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            self.manifest["dataset_sha256"],
            hashlib.sha256(fixture_text.encode("utf-8")).hexdigest(),
        )

    def test_replay_maps_400_once_and_holds_100_with_exact_codes(self):
        shadow = CalibrationCutoverShadow({"authoritative": "unchanged"})
        report = shadow.replay(self.records, self.manifest)

        self.assertEqual(400, report.clean)
        self.assertEqual(100, report.hold)
        self.assertEqual(
            dict(sorted(self.manifest["expected_hold_codes"].items())),
            report.hold_counts,
        )
        self.assertEqual(0, report.auto_released)
        self.assertEqual(400, report.human_qa_required)

        clean = [item for item in report.outcomes if item["status"] == "CLEAN"]
        held = [item for item in report.outcomes if item["status"] == "HOLD"]
        self.assertTrue(all(item["mapping_count"] == 1 for item in clean))
        self.assertTrue(all(item["release_state"] == "QA_REQUIRED" for item in clean))
        self.assertTrue(all(item["mapping_count"] == 0 for item in held))
        self.assertTrue(all(item["release_state"] == "HOLD" for item in held))
        self.assertEqual(
            {record["history_id"]: record["truth_hold"] for record in self.records if record["truth_hold"]},
            {item["history_id"]: item["hold_code"] for item in held},
        )

    def test_clean_values_units_uncertainty_procedure_and_certificate_hash_survive(self):
        report = CalibrationCutoverShadow().replay(self.records, self.manifest)
        for outcome in report.outcomes:
            if outcome["status"] != "CLEAN":
                continue
            source = self.by_id[outcome["history_id"]]
            mapped = outcome["mapped"]
            self.assertEqual(source["as_found"], mapped["as_found_as_left"]["as_found"])
            self.assertEqual(source["as_left"], mapped["as_found_as_left"]["as_left"])
            self.assertEqual(source["unit"], mapped["as_found_as_left"]["unit"])
            self.assertEqual(source["uncertainty"], mapped["as_found_as_left"]["uncertainty"])
            self.assertEqual(source["procedure_id"], mapped["scope_procedure"]["procedure_id"])
            self.assertEqual(
                source["procedure_revision"], mapped["scope_procedure"]["revision"]
            )
            self.assertEqual(
                source["certificate_hash"], mapped["certificate"]["sha256"]
            )
            expected_record_sha = hashlib.sha256(
                json.dumps(
                    source, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(expected_record_sha, outcome["record_sha256"])

    def test_zero_cross_customer_assets_or_certificates(self):
        assert_customer_isolation(self.records)
        owners_by_asset = {}
        owners_by_certificate = {}
        for record in self.records:
            owners_by_asset.setdefault(record["asset_id"], set()).add(record["customer_id"])
            owners_by_certificate.setdefault(record["certificate_id"], set()).add(
                record["customer_id"]
            )
        self.assertTrue(all(len(owners) == 1 for owners in owners_by_asset.values()))
        self.assertTrue(all(len(owners) == 1 for owners in owners_by_certificate.values()))

    def test_full_replay_is_idempotent_and_rollback_restores_exact_baseline(self):
        authoritative = {"source": "authoritative", "revision": 7}
        shadow = CalibrationCutoverShadow(authoritative)
        shadow.shadow_state = {"preexisting": {"status": "BASELINE"}}
        baseline = shadow.snapshot()
        authoritative_fingerprint = shadow.authoritative_fingerprint

        first = shadow.replay(self.records, self.manifest)
        first_state = shadow.snapshot()
        second = shadow.replay(self.records, self.manifest)
        second_state = shadow.snapshot()

        self.assertEqual(first.outcome_digest, second.outcome_digest)
        self.assertEqual(first_state, second_state)
        self.assertEqual(authoritative_fingerprint, shadow.authoritative_fingerprint)
        self.assertEqual(authoritative, shadow.authoritative_state)

        shadow.rollback(baseline)
        self.assertEqual(baseline, shadow.snapshot())

    def test_manifest_and_record_tampering_are_rejected(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["expected_clean"] = 399
        with self.assertRaises(IntegrityError):
            verify_manifest_signature(bad_manifest)

        bad_records = copy.deepcopy(self.records)
        bad_records[0]["as_found"] += 1
        with self.assertRaises(IntegrityError):
            verify_records(bad_records, self.manifest)

    def test_automatic_release_is_impossible(self):
        shadow = CalibrationCutoverShadow()
        report = shadow.replay(self.records, self.manifest)
        self.assertEqual(0, report.auto_released)
        with self.assertRaises(PermissionError):
            shadow.automatic_release("H0001")


if __name__ == "__main__":
    unittest.main()
