from __future__ import annotations

import math
import sys
import unittest
from fractions import Fraction
from pathlib import Path

from clustered_sign_gate import EvidenceError, analyze, exact_upper_sign_tail


SEEDS = [539131249, 1834999074, 2609097301, 2609097302, 2609097303, 2609097304, 2611092201, 2611092207]
OPPONENTS = ["arlene", "v1"]
PACKET_DIR = Path(__file__).resolve().parent
REPO_ROOT = next(
    path
    for path in (PACKET_DIR, *PACKET_DIR.parents)
    if (path / "open_door_guard.py").is_file()
)


def row(opponent, seed, seat, own=0, rival=0, changed=False):
    return {
        "opponent": opponent,
        "seed": seed,
        "seat": seat,
        "own_delta": own,
        "rival_delta": rival,
        "margin_delta": own - rival,
        "candidate_action_changed": changed,
    }


def sparse_admitted_fixture():
    rows = []
    effects = {
        ("arlene", 2609097301): (54, 3),
        ("v1", 1834999074): (26, 28),
        ("v1", 2609097301): (54, 3),
    }
    for opponent in OPPONENTS:
        for seed in SEEDS:
            own, rival = effects.get((opponent, seed), (0, 0))
            for seat in (0, 1):
                rows.append(row(opponent, seed, seat, own, rival, bool(own or rival)))
    return rows


class ExactTailTests(unittest.TestCase):
    def test_exact_rational_tail(self):
        self.assertEqual(exact_upper_sign_tail(6, 0), Fraction(1, 64))
        self.assertEqual(exact_upper_sign_tail(3, 0), Fraction(1, 8))
        self.assertEqual(exact_upper_sign_tail(2, 0), Fraction(1, 4))
        self.assertEqual(exact_upper_sign_tail(4, 1), Fraction(6, 32))
        self.assertEqual(exact_upper_sign_tail(0, 0), Fraction(1, 1))

    def test_bool_is_not_an_integer_count(self):
        with self.assertRaises(EvidenceError):
            exact_upper_sign_tail(True, 0)


class ClusteredSelectorTests(unittest.TestCase):
    def test_six_mirrored_rows_are_not_six_independent_signs(self):
        receipt = analyze(sparse_admitted_fixture())
        self.assertEqual(receipt["verdict"], "MORE_EVIDENCE")
        self.assertEqual(
            receipt["overall"]["naive_cell_sign_tail_diagnostic_only"],
            {"numerator": 1, "denominator": 64, "decimal": 1 / 64},
        )
        self.assertEqual(
            receipt["opponent_seed_sensitivity"]["one_sided_exact_sign_tail"],
            {"numerator": 1, "denominator": 8, "decimal": 1 / 8},
        )
        self.assertEqual(
            receipt["seed_selector"]["one_sided_exact_sign_tail"],
            {"numerator": 1, "denominator": 4, "decimal": 1 / 4},
        )
        self.assertEqual(receipt["seed_selector"]["positive_clusters"], 2)
        self.assertEqual(receipt["seed_selector"]["negative_clusters"], 0)

    def test_concentration_and_bootstrap_zero_mass_are_exact(self):
        receipt = analyze(sparse_admitted_fixture())
        concentration = receipt["concentration"]
        self.assertEqual(concentration["largest_positive_seed"], 2609097301)
        self.assertAlmostEqual(concentration["largest_positive_seed_share"], 216 / 268)
        self.assertEqual(
            concentration["all_zero_seed_cluster_bootstrap_probability"],
            {"numerator": 6561, "denominator": 65536, "decimal": 6561 / 65536},
        )
        self.assertTrue(concentration["bootstrap_2_5_percentile_is_zero"])

    def test_leave_one_dominant_seed_out_stays_positive_but_loses_margin(self):
        receipt = analyze(sparse_admitted_fixture())
        row_ = next(
            value
            for value in receipt["leave_one_seed_out"]
            if value["omitted_seed"] == 2609097301
        )
        self.assertAlmostEqual(row_["mean_own_delta"], 52 / 28)
        self.assertAlmostEqual(row_["mean_margin_delta"], -4 / 28)
        self.assertEqual(row_["negative_cells"], 0)

    def test_five_independent_positive_seed_clusters_pass_five_percent_gate(self):
        rows = []
        for seed in range(5):
            for opponent in OPPONENTS:
                for seat in (0, 1):
                    rows.append(row(opponent, seed, seat, 1, 0, True))
        receipt = analyze(rows)
        self.assertEqual(receipt["verdict"], "SIGN_SUPPORTED")
        self.assertEqual(
            receipt["seed_selector"]["one_sided_exact_sign_tail"],
            {"numerator": 1, "denominator": 32, "decimal": 1 / 32},
        )
        self.assertFalse(receipt["promotion_authority"])
        self.assertIn("not gameplay-promotion authority", receipt["reason"])
        self.assertIn("conditional", receipt["tail_assumption"])

    def test_negative_cell_is_regression_even_when_cluster_mean_is_positive(self):
        rows = [
            row("arlene", 1, 0, 10, 0, True),
            row("arlene", 1, 1, -1, 0, True),
        ]
        receipt = analyze(rows)
        self.assertEqual(receipt["verdict"], "REGRESSION_SCREEN")

    def test_score_delta_without_candidate_action_change_fails_closed(self):
        rows = [row("arlene", 1, 0, 1, 0, False), row("arlene", 1, 1, 1, 0, False)]
        with self.assertRaisesRegex(EvidenceError, "without candidate-action activation"):
            analyze(rows)

    def test_missing_mirrored_seat_fails_closed(self):
        with self.assertRaisesRegex(EvidenceError, "mirrored-seat grid is incomplete"):
            analyze([row("arlene", 1, 0)])

    def test_duplicate_cell_fails_closed(self):
        duplicate = row("arlene", 1, 0)
        with self.assertRaisesRegex(EvidenceError, "duplicate paired cell"):
            analyze([duplicate, dict(duplicate), row("arlene", 1, 1)])

    def test_nonfinite_and_boolean_numbers_fail_closed(self):
        for bad in (math.inf, math.nan, True):
            with self.subTest(bad=bad):
                rows = [row("arlene", 1, 0), row("arlene", 1, 1)]
                rows[0]["own_delta"] = bad
                with self.assertRaises(EvidenceError):
                    analyze(rows)

    def test_inconsistent_margin_fails_closed(self):
        rows = [row("arlene", 1, 0), row("arlene", 1, 1)]
        rows[0]["margin_delta"] = 9
        with self.assertRaisesRegex(EvidenceError, "margin_delta is inconsistent"):
            analyze(rows)

    def test_no_action_or_score_signal_is_not_a_rejection(self):
        rows = [row("arlene", 1, 0), row("arlene", 1, 1)]
        self.assertEqual(analyze(rows)["verdict"], "NO_SIGNAL")

    def test_packet_sources_do_not_add_admission_lock_phrases(self):
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        import open_door_guard as guard

        added = []
        for path in sorted(PACKET_DIR.iterdir()):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                added.append(guard.AddedLine(rel, number, line))
        self.assertEqual(guard.scan_added(added), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
