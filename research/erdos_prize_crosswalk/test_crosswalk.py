from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import verify_crosswalk as vc


ROOT = Path(__file__).resolve().parent


class CrosswalkTests(unittest.TestCase):
    def setUp(self):
        self.doc = vc.load_strict(ROOT / "crosswalk.json")

    def test_snapshot_verifies(self):
        digest = vc.verify(self.doc)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def assert_rejected(self, mutate):
        hostile = copy.deepcopy(self.doc)
        mutate(hostile)
        with self.assertRaises(vc.CrosswalkError):
            vc.verify(hostile)

    def test_duplicate_problem_rejected(self):
        self.assert_rejected(lambda d: d["problems"].__setitem__(1, copy.deepcopy(d["problems"][0])))

    def test_reward_drift_rejected(self):
        self.assert_rejected(lambda d: d["problems"][0].__setitem__("reward_usd", 999999))

    def test_total_drift_rejected(self):
        self.assert_rejected(lambda d: d["scope"].__setitem__("expected_total_usd", 999999))

    def test_false_formal_presence_rejected(self):
        def mutate(d):
            row = next(r for r in d["problems"] if r["erdos_number"] == 625)
            row["formal_target"]["status"] = "PRESENT"
        self.assert_rejected(mutate)

    def test_missing_present_blob_rejected(self):
        def mutate(d):
            row = next(r for r in d["problems"] if r["erdos_number"] == 142)
            row["formal_target"]["blob_sha"] = None
        self.assert_rejected(mutate)

    def test_625_reward_scope_rejected_if_symmetric(self):
        def mutate(d):
            row = next(r for r in d["problems"] if r["erdos_number"] == 625)
            row["reward_scope"] = "resolution"
        self.assert_rejected(mutate)

    def test_64_active_owner_fence_rejected_if_erased(self):
        def mutate(d):
            row = next(r for r in d["problems"] if r["erdos_number"] == 64)
            row["commons_ownership"] = {"status": "NO_ACTIVE_TAKE_OBSERVED_IN_CENSUS", "carrier": None}
        self.assert_rejected(mutate)

    def test_parallel_rewards_must_not_be_double_counted(self):
        self.assert_rejected(lambda d: d["scope"].__setitem__("parallel_platform_rewards_counted", True))

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(vc.CrosswalkError):
                vc.load_strict(path)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text('{"x":NaN}', encoding="utf-8")
            with self.assertRaises(vc.CrosswalkError):
                vc.load_strict(path)


if __name__ == "__main__":
    unittest.main()
