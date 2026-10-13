import unittest

from calibrate import calibrate, rank_interval, validate_games


def payload():
    return {
        "source": {
            "opponent_family": "arlene",
            "candidate_archive_sha256": "95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153",
            "candidate_runtime_sha256": "9e5e4eb6fe66d2516365f96ad9e2366d07c446b6c70e5cada28602ae46c3a1b8",
            "baseline_archive_sha256": "7dcb73bb0d8bc6d0d003b107fcb47c93f9e77c4d8c64d39fec8bd54d406bb407",
            "baseline_candidate_sha256": "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4",
            "opponent_runtime_sha256": "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4",
        },
        "games": [
            {"seed": 10, "seat": 0, "candidate_cash": 120, "baseline_cash": 100},
            {"seed": 10, "seat": 1, "candidate_cash": 90, "baseline_cash": 100},
            {"seed": 20, "seat": 0, "candidate_cash": 100, "baseline_cash": 100},
            {"seed": 20, "seat": 1, "candidate_cash": 130, "baseline_cash": 100},
        ],
        "baseline_anchor": {"submission_id": 1, "score": 2000.0, "observed_at": "2026-09-08T00:00:00Z"},
    }


class CalibrationTests(unittest.TestCase):
    def test_grouped_fit_and_ties(self):
        report = calibrate(payload(), iterations=2000, bootstrap_seed=7)
        self.assertEqual(report["sample"]["seed_clusters"], 2)
        self.assertEqual((report["sample"]["W"], report["sample"]["T"], report["sample"]["L"]), (2, 1, 1))
        self.assertAlmostEqual(report["fit"]["raw_score_fraction"], 0.625)
        self.assertAlmostEqual(report["expected_match_outcome"]["T"]["empirical_probability"], 0.25)
        self.assertFalse(report["rank"]["identified"])

    def test_pair_contract_rejects_missing_and_duplicate_seats(self):
        with self.assertRaises(ValueError):
            validate_games([{"seed": 1, "seat": 0, "result": "W"}])
        with self.assertRaises(ValueError):
            validate_games([
                {"seed": 1, "seat": 0, "result": "W"},
                {"seed": 1, "seat": 0, "result": "L"},
            ])

    def test_contemporaneous_interpolation(self):
        snap = {"anchors": [
            {"score": 1800, "rank": 1000, "observed_at": "x"},
            {"score": 2200, "rank": 700, "observed_at": "x"},
            {"score": 2600, "rank": 300, "observed_at": "x"},
        ]}
        result = rank_interval([2000, 2400], snap)
        self.assertTrue(result["identified"])
        self.assertEqual(result["interval"], [500, 850])

    def test_rank_refuses_extrapolation_or_longitudinal_mix(self):
        snap = {"anchors": [
            {"score": 1800, "rank": 1000, "observed_at": "a"},
            {"score": 2200, "rank": 700, "observed_at": "b"},
            {"score": 2600, "rank": 300, "observed_at": "b"},
        ]}
        self.assertFalse(rank_interval([2000, 2400], snap)["identified"])
        snap["anchors"][0]["observed_at"] = "b"
        self.assertFalse(rank_interval([1700, 2400], snap)["identified"])

    def test_temporal_anchor_band(self):
        case = payload()
        case["baseline_anchor"] = {"submission_id": 1, "score_low": 1900, "score_high": 2100}
        report = calibrate(case, iterations=100, bootstrap_seed=4)
        self.assertLess(report["anchored_score_proxy_sensitivity_band"][0], report["anchored_score_proxy_sensitivity_band"][1])

    def test_source_mismatch_is_rejected(self):
        case = payload()
        case["source"]["baseline_archive_sha256"] = "wrong"
        with self.assertRaises(ValueError):
            calibrate(case, iterations=10)

    def test_source_backed_unhosted_opponent_stays_relative(self):
        case = payload()
        case["source"] = {
            "opponent_family": "frozen_sell",
            "candidate_archive_sha256": "95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153",
            "candidate_runtime_sha256": "9e5e4eb6fe66d2516365f96ad9e2366d07c446b6c70e5cada28602ae46c3a1b8",
            "opponent_runtime_sha256": "ca810092542eed9d862466df71ef6ee723170a54d5ad5764babd3d4a727202ae",
        }
        case.pop("baseline_anchor")
        report = calibrate(case, iterations=100, bootstrap_seed=2)
        self.assertIsNone(report["anchored_score_proxy_point"])
        self.assertFalse(report["rank"]["identified"])

    def test_failed_game_is_rejected(self):
        case = payload()
        case["games"][0]["error"] = "timeout"
        with self.assertRaises(ValueError):
            calibrate(case, iterations=10)


if __name__ == "__main__":
    unittest.main()
