# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

import compare


def report(*, offsets=None, same_trace=False):
    offsets = offsets or {}
    opponents = {"arlene": {"entry": "a.py"}, "v1": {"entry": "v1.py"}}
    seeds = [11, 22]
    games = []
    for opponent in opponents:
        for seed in seeds:
            for seat in (0, 1):
                key = (opponent, seed, seat)
                offset = float(offsets.get(key, 0))
                own = 100.0 + seed + seat + offset
                rival = 80.0 + seat
                scores = [own, rival] if seat == 0 else [rival, own]
                token = "0" if same_trace else f"{opponent}-{seed}-{seat}-{offset}"
                trace = (token.encode().hex() + "0" * 64)[:64]
                games.append(
                    {
                        "opponent": opponent,
                        "seed": seed,
                        "candidate_seat": seat,
                        "status": "complete",
                        "failure": None,
                        "scores": scores,
                        "trace_sha256": trace,
                        "daily_bank": [
                            {"step": 23, "bank": scores},
                            {"step": 47, "bank": scores},
                        ],
                    }
                )
    return {
        "schema_version": 1,
        "engine_ref": "engine",
        "engine_sha256": {"x": "y"},
        "loader_sha256": "loader",
        "evaluator_sha256": "evaluator",
        "seeds": seeds,
        "agent_rng_seed": 7,
        "limits": {"action_rpc_seconds": 1.0},
        "opponents": opponents,
        "candidate": {"entry": "control.py", "sha256": "a" * 64},
        "progress": {"state": "complete"},
        "games": games,
    }


def paired(offsets, same_trace=False):
    control = report(same_trace=True)
    candidate = report(offsets=offsets, same_trace=same_trace)
    candidate["candidate"] = {"entry": "candidate.py", "sha256": "b" * 64}
    return control, candidate


class CompareTests(unittest.TestCase):
    def test_upside_screen(self):
        offsets = {
            (opponent, seed, seat): 5
            for opponent in ("arlene", "v1")
            for seed in (11, 22)
            for seat in (0, 1)
        }
        control, candidate = paired(offsets)
        result = compare.compare(control, candidate, git_head="head")
        self.assertEqual(result["verdict"], "UPSIDE_SCREEN")
        self.assertEqual(result["overall"]["mean_own_cash_delta"], 5)
        self.assertEqual(result["overall"]["positive_cells"], 8)
        self.assertFalse(result["promotion_authorized"])

    def test_regression_screen(self):
        offsets = {
            (opponent, seed, seat): -3
            for opponent in ("arlene", "v1")
            for seed in (11, 22)
            for seat in (0, 1)
        }
        control, candidate = paired(offsets)
        self.assertEqual(compare.compare(control, candidate)["verdict"], "REGRESSION_SCREEN")

    def test_no_action_change(self):
        control, candidate = paired({}, same_trace=True)
        self.assertEqual(compare.compare(control, candidate)["verdict"], "NO_ACTION_CHANGE")

    def test_mixed_screen(self):
        offsets = {
            ("arlene", 11, 0): 10,
            ("arlene", 11, 1): -10,
        }
        control, candidate = paired(offsets)
        self.assertEqual(compare.compare(control, candidate)["verdict"], "MIXED_SCREEN")

    def test_rejects_incomplete_cell(self):
        control, candidate = paired({})
        candidate["games"][0]["status"] = "failed"
        with self.assertRaisesRegex(compare.ComparisonError, "not complete"):
            compare.compare(control, candidate)

    def test_rejects_grid_hole(self):
        control, candidate = paired({})
        candidate["games"].pop()
        with self.assertRaisesRegex(compare.ComparisonError, "grid mismatch"):
            compare.compare(control, candidate)

    def test_rejects_provenance_drift(self):
        control, candidate = paired({})
        candidate["engine_ref"] = "other"
        with self.assertRaisesRegex(compare.ComparisonError, "engine_ref"):
            compare.compare(control, candidate)

    def test_rejects_equal_entrypoints(self):
        control, candidate = paired({})
        candidate["candidate"] = copy.deepcopy(control["candidate"])
        with self.assertRaisesRegex(compare.ComparisonError, "equal"):
            compare.compare(control, candidate)

    def test_rejects_duplicate_cell(self):
        control, candidate = paired({})
        candidate["games"].append(copy.deepcopy(candidate["games"][0]))
        with self.assertRaisesRegex(compare.ComparisonError, "duplicate"):
            compare.compare(control, candidate)

    def test_markdown_contains_verdict_and_cells(self):
        offsets = {("v1", 11, 0): 2}
        control, candidate = paired(offsets)
        text = compare.markdown(compare.compare(control, candidate))
        self.assertIn("TITAN V3 own-value objective", text)
        self.assertIn("Paired cells", text)
        self.assertIn("promotion authorization", text)


if __name__ == "__main__":
    unittest.main()
