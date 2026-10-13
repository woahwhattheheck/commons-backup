import csv
import tempfile
import unittest
from pathlib import Path

import prioritize


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "recommendations.synthetic.csv"
WEIGHTS = HERE / "weights.json"


class PrioritizationTests(unittest.TestCase):
    def setUp(self):
        self.config = prioritize.load_weights(WEIGHTS)
        self.records = prioritize.load_recommendations(FIXTURES)

    def test_missing_estimate_is_visible_hold(self):
        rows = prioritize.rank_profile(
            self.records,
            "balanced",
            self.config["profiles"]["balanced"],
            self.config["tie_epsilon"],
        )
        r6 = next(r for r in rows if r["id"] == "R006")
        self.assertEqual(r6["status"], "HOLD_MISSING_ESTIMATE")
        self.assertEqual(r6["rank"], "")
        self.assertIn("security", r6["missing_estimates"])
        self.assertIsNone(r6["priority_score"])

    def test_balanced_profile_has_explained_tie(self):
        rows = prioritize.rank_profile(
            self.records,
            "balanced",
            self.config["profiles"]["balanced"],
            self.config["tie_epsilon"],
        )
        r2 = next(r for r in rows if r["id"] == "R002")
        r4 = next(r for r in rows if r["id"] == "R004")
        self.assertEqual(r2["rank"], r4["rank"])
        self.assertTrue(r2["tie_group"])
        self.assertEqual(r2["tie_group"], r4["tie_group"])
        self.assertIn("tie_epsilon", r2["tie_reason"])

    def test_weight_profiles_change_leader(self):
        balanced = prioritize.rank_profile(
            self.records,
            "balanced",
            self.config["profiles"]["balanced"],
            self.config["tie_epsilon"],
        )
        security = prioritize.rank_profile(
            self.records,
            "security_first",
            self.config["profiles"]["security_first"],
            self.config["tie_epsilon"],
        )
        balanced_leaders = {r["id"] for r in balanced if r["rank"] == 1}
        security_leaders = {r["id"] for r in security if r["rank"] == 1}
        self.assertNotEqual(balanced_leaders, security_leaders)
        self.assertIn("R003", security_leaders)

    def test_invalid_benefit_weights_are_rejected(self):
        bad = {
            "tie_epsilon": 0.01,
            "profiles": {
                "bad": {
                    "quality": 0.5,
                    "security": 0.5,
                    "delivery": 0.5,
                    "complexity": 0.3,
                }
            },
        }
        with self.assertRaises(ValueError):
            prioritize.validate_weights(bad)

    def test_end_to_end_outputs_are_complete(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            profiles = prioritize.run(FIXTURES, WEIGHTS, out)
            self.assertEqual(set(profiles), set(self.config["profiles"]))
            self.assertTrue((out / "sensitivity.csv").exists())
            self.assertTrue((out / "report.md").exists())
            for name in self.config["profiles"]:
                self.assertTrue((out / f"ranking_{name}.csv").exists())

            with (out / "sensitivity.csv").open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), len(self.records))
            held = next(r for r in rows if r["id"] == "R006")
            self.assertEqual(held["status"], "HOLD_MISSING_ESTIMATE")
            self.assertEqual(held["best_rank"], "")

            report = (out / "report.md").read_text(encoding="utf-8")
            self.assertIn("Missing required estimates", report)
            self.assertIn("security_first", report)
            self.assertIn("Tie epsilon", report)


if __name__ == "__main__":
    unittest.main()
