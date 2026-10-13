# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from panel_delta import (
    assert_historical_l01,
    compare,
    ensure_grid,
    load_games,
)


def game(opponent, seed, seat, own, rival):
    scores = [None, None]
    scores[seat] = own
    scores[1 - seat] = rival
    return {
        "opponent": opponent,
        "seed": seed,
        "candidate_seat": seat,
        "status": "complete",
        "scores": scores,
        "failure": None,
    }


class PanelDeltaTests(unittest.TestCase):
    def test_pair_math_and_opposite_seat_signature(self):
        baseline = {
            ("arlene", 1, 0): game("arlene", 1, 0, 80, 100),
            ("arlene", 1, 1): game("arlene", 1, 1, 90, 85),
        }
        candidate = {
            ("arlene", 1, 0): game("arlene", 1, 0, 90, 85),
            ("arlene", 1, 1): game("arlene", 1, 1, 90, 85),
        }
        report = compare(baseline, candidate)
        self.assertEqual(report["changed_only"]["transitions"], {"L->W": 1})
        self.assertEqual(report["overall"]["sum_margin_delta"], 25)
        self.assertEqual(report["seat_normalization"]["matches"], 1)
        self.assertEqual(report["verdict"], "advance")

    def test_new_loss_rejects(self):
        baseline = {("x", 1, 0): game("x", 1, 0, 10, 9)}
        candidate = {("x", 1, 0): game("x", 1, 0, 8, 9)}
        report = compare(baseline, candidate)
        self.assertEqual(report["overall"]["new_losses"], 1)
        self.assertEqual(report["verdict"], "reject")

    def test_loader_and_grid_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "games.jsonl"
            path.write_text(
                json.dumps(game("x", 1, 0, 10, 9)) + "\n",
                encoding="utf-8",
            )
            games = load_games(path)
            with self.assertRaises(ValueError):
                ensure_grid(games, opponents=["x"], seeds=[1])

    def test_historical_profile_contract(self):
        opponents = [
            "arlene",
            "apex",
            "kaito_v43",
            "cok_v10",
            "public_bt12",
            "v1_submitted",
        ]
        baseline = {}
        candidate = {}
        deltas = {
            2611061001: (118566, 139835, 106310, 104958),
            2611061002: (86933, 95680, 117943, 115767),
            2611061003: (83192, 86884, 67597, 66249),
            2611061004: (120875, 148476, 80578, 79529),
            2611061005: (81074, 100679, 69319, 67051),
            2611061006: (101214, 109839, 87720, 86148),
            2611061007: (91636, 105364, 101498, 100374),
            2611061008: (117463, 129694, 101948, 98759),
        }
        for opponent_index, opponent in enumerate(opponents):
            for seed in range(2611061001, 2611061017):
                for seat in (0, 1):
                    own = 100000 + opponent_index * 100 + seat
                    rival = own - 1
                    baseline[(opponent, seed, seat)] = game(
                        opponent, seed, seat, own, rival
                    )
                    candidate[(opponent, seed, seat)] = game(
                        opponent, seed, seat, own, rival
                    )
        for seed, (bo, br, co, cr) in deltas.items():
            baseline[("arlene", seed, 0)] = game(
                "arlene", seed, 0, bo, br
            )
            candidate[("arlene", seed, 0)] = game(
                "arlene", seed, 0, co, cr
            )
            # Seven historical corrections reproduce the baseline opposite-seat
            # own/rival pair; seed 1007 is the one non-exact match.
            if seed != 2611061007:
                baseline[("arlene", seed, 1)] = game(
                    "arlene", seed, 1, co, cr
                )
                candidate[("arlene", seed, 1)] = game(
                    "arlene", seed, 1, co, cr
                )

        report = compare(baseline, candidate)
        assert_historical_l01(report)
        self.assertTrue(report["historical_l01_profile"]["passed"])
        self.assertEqual(report["overall"]["sum_margin_delta"], 129576)


if __name__ == "__main__":
    unittest.main()
