from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import lean_feed_source_contract as s


HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "d2_contract.json"


def evidence() -> dict:
    return {
        "schema": "titan-v5-lean-feed-carry-economics-v1",
        "authority": {
            "archive_sha256": s.D2_ARCHIVE_SHA256,
            "archive_member_count": 94,
        },
        "runs": [
            {
                "arm": "MIN_PROVABLE",
                "decision_windows": [
                    {
                        "snapshot": {
                            "feed_on_hand": {"Corn": 1, "Pasture": 1, "Straw": 1},
                            "current_authored": {"Corn": 2, "Pasture": 5, "Straw": 1},
                        }
                    }
                ],
            }
        ],
    }


class SourceContractTests(unittest.TestCase):
    def test_retained_contract_is_blocked_and_non_authorizing(self):
        result = s.assess_retained_source_contract(CONTRACT)
        self.assertEqual(result["state"], "SOURCE_MODEL_BLOCKED")
        self.assertFalse(result["promotion_authorized"])
        self.assertFalse(result["candidate_build_authorized"])
        self.assertEqual(result["facts"]["feed_item"], "WHEAT")

    def test_impossible_v1_evidence_cannot_promote(self):
        assessment = s.assess_retained_source_contract(CONTRACT)
        report = s.build_source_blocked_report(evidence(), assessment)
        self.assertEqual(report["promotion"]["conclusion"], "SOURCE_MODEL_BLOCKED")
        self.assertIsNone(report["promotion"]["selected_arm"])
        self.assertEqual(report["runs"], [])
        self.assertEqual(report["paired_deltas"], [])

    def test_report_is_deterministic(self):
        assessment = s.assess_retained_source_contract(CONTRACT)
        first = s.build_source_blocked_report(copy.deepcopy(evidence()), assessment)
        second = s.build_source_blocked_report(copy.deepcopy(evidence()), assessment)
        self.assertEqual(first, second)
        self.assertEqual(first["report_sha256"], second["report_sha256"])

    def test_fictional_feed_contract_is_rejected(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        raw["feed_item"] = "Corn"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(s.SourceContractError):
                s.assess_retained_source_contract(path)

    def test_fixed_reserve_vector_is_rejected(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        raw["fixed_reserve_vector"] = {"WHEAT": 2}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(s.SourceContractError):
                s.assess_retained_source_contract(path)

    def test_wrong_lineage_blob_is_rejected(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        raw["lineage_operating_stock_git_blob"] = "0" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(s.SourceContractError):
                s.assess_retained_source_contract(path)

    def test_raw_archive_claim_cannot_be_self_promoted(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        raw["d2_member_binding"] = "VERIFIED"
        raw["promotion_authorized"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(s.SourceContractError):
                s.assess_retained_source_contract(path)

    def test_duplicate_json_key_is_rejected(self):
        text = CONTRACT.read_text(encoding="utf-8")
        malicious = text.replace(
            '"feed_item": "WHEAT",',
            '"feed_item": "WHEAT",\n  "feed_item": "Corn",',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(malicious, encoding="utf-8")
            with self.assertRaises(s.SourceContractError):
                s.assess_retained_source_contract(path)

    def test_wrong_archive_in_evidence_fails(self):
        assessment = s.assess_retained_source_contract(CONTRACT)
        bad = evidence()
        bad["authority"]["archive_sha256"] = "0" * 64
        with self.assertRaises(s.SourceContractError):
            s.build_source_blocked_report(bad, assessment)


if __name__ == "__main__":
    unittest.main()
