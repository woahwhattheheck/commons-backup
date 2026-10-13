import copy
import json
from pathlib import Path
import unittest

import analyze_field_snapshot as a

HERE = Path(__file__).resolve().parent
SNAPSHOT = json.loads((HERE / "snapshot_20260911.json").read_text())


class FieldSnapshotTests(unittest.TestCase):
    def test_expected_loss_strata(self):
        report = a.analyze(copy.deepcopy(SNAPSHOT))
        self.assertEqual(report["v3_close_losses"]["games"], 15)
        self.assertEqual(report["v3_close_losses"]["median_deficit"], 215)
        self.assertEqual(report["v3_close_losses"]["within_100"], 5)
        self.assertEqual(report["v3_close_losses"]["within_250"], 9)
        self.assertEqual(report["v3_close_losses"]["within_500"], 15)
        self.assertEqual(report["v3_close_losses"]["known_rank_median"], 86)

    def test_v31_exposure_is_not_top20_evidence(self):
        report = a.analyze(copy.deepcopy(SNAPSHOT))
        self.assertEqual(report["exposure"]["v31_top20_games"], 0)
        self.assertEqual(report["exposure"]["v31_best_known_opponent_rank"], 125)
        self.assertEqual(report["exposure"]["v31_median_known_opponent_rank"], 543)
        self.assertTrue(report["exposure"]["v31_losses_all_same_day_fresh"])

    def test_v3_top20_record_is_consistent(self):
        report = a.analyze(copy.deepcopy(SNAPSHOT))
        self.assertEqual(report["exposure"]["v3_top20_games"], 6)
        self.assertEqual(report["exposure"]["v3_top20_wins"], 0)
        self.assertTrue(report["exposure"]["v3_top20_group_means_all_negative"])

    def test_post_snapshot_loss_marks_snapshot_stale(self):
        report = a.analyze(copy.deepcopy(SNAPSHOT))
        self.assertEqual(report["post_snapshot_loss_events"], 1)
        self.assertFalse(report["snapshot_is_current"])

    def test_positive_loss_margin_rejected(self):
        bad = copy.deepcopy(SNAPSHOT)
        bad["v3_close_losses"][0]["margin"] = 1
        with self.assertRaises(a.DataError):
            a.analyze(bad)

    def test_bool_rank_rejected(self):
        bad = copy.deepcopy(SNAPSHOT)
        bad["v3_close_losses"][0]["opponent_rank"] = True
        with self.assertRaises(a.DataError):
            a.analyze(bad)

    def test_top20_group_count_mismatch_rejected(self):
        bad = copy.deepcopy(SNAPSHOT)
        bad["opponent_exposure"]["v3"]["top20_games"] = 7
        with self.assertRaises(a.DataError):
            a.analyze(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
