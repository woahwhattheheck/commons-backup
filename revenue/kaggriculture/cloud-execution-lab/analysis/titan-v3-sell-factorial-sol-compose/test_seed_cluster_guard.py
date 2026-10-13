# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import seed_cluster_guard as guard


def digest(*parts):
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def parent(*, seeds=tuple(range(1, 9)), opponents=("replay",), effect=None,
           eligible=None, selected="both"):
    if effect is None:
        def effect(arm, opponent, seed, seat):
            del opponent, seed, seat
            return {"control": 100, "own_value": 101,
                    "certified_pressure": 101, "both": 103}[arm], 0
    eligible = eligible or {"own_value": True, "certified_pressure": True, "both": True}
    verdict = {"both": "SELECT_BOTH", "own_value": "SELECT_OWN_VALUE",
               "certified_pressure": "SELECT_CERTIFIED_PRESSURE", None: "NO_SAFE_ADVANCE"}[selected]
    cells = []
    for opponent in opponents:
        for seed in seeds:
            for seat in (0, 1):
                arms = {}
                for arm in guard.ARMS:
                    own, rival = map(float, effect(arm, opponent, seed, seat))
                    margin = own - rival
                    arms[arm] = {
                        "own_cash": own, "rival_cash": rival, "margin": margin,
                        "outcome": "win" if margin > 0 else "loss" if margin < 0 else "tie",
                        "candidate_action_sha256": digest("action", arm, opponent, seed, seat),
                        "trace_sha256": digest("trace", arm, opponent, seed, seat),
                    }
                cells.append({"opponent": opponent, "seed": seed,
                              "candidate_seat": seat, "arms": arms,
                              "pairwise": {}, "factorial": {}})
    return {
        "schema_version": 1, "operation": guard.PARENT_OP, "git_head": "a" * 40,
        "arms": list(guard.ARMS), "paired_provenance": {}, "arm_manifest_binding": {},
        "grid": {"cells_per_arm": len(cells), "total_games": 4 * len(cells),
                 "opponents": list(opponents), "seeds": list(seeds), "both_seats": True},
        "overall": {}, "by_opponent_seat": {},
        "selection": {"verdict": verdict, "selected_arm": selected,
                      "eligible_against_control": dict(eligible),
                      "composition_nondominated": selected == "both",
                      "promotion_authorized": False, "hosted_leaderboard_claim": False},
        "cells": cells,
    }


class GuardTests(unittest.TestCase):
    def test_seven_good_one_bad_seed_is_downgraded(self):
        def effect(arm, opponent, seed, seat):
            del opponent, seat
            return {"control": 100, "own_value": 101, "certified_pressure": 101,
                    "both": 95 if seed == 8 else 103}[arm], 0
        report = guard.assess(parent(effect=effect))
        self.assertEqual(report["selection"]["verdict"], "SELECT_OWN_VALUE")
        self.assertEqual(report["selection"]["downgrade_reason"],
                         "NEGATIVE_SEED_OR_OPPONENT_SEED_CLUSTER_REGRET")
        summary = report["seed_cluster_tail"]["summary"]
        self.assertEqual(summary["negative_seed_clusters"], 1)
        self.assertEqual(summary["seed_own_regret"]["min"], -6)
        self.assertEqual(report["grid"]["independent_clusters"], 8)
        self.assertEqual(report["grid"]["cells_per_arm"], 16)

    def test_opponent_seed_checkerboard_is_not_hidden_by_zero_seed_means(self):
        def effect(arm, opponent, seed, seat):
            del seat
            if arm != "both":
                return {"control": 100, "own_value": 101, "certified_pressure": 101}[arm], 0
            sign = 1 if (opponent == "arlene") == (seed == 1) else -1
            return 101 + 6 * sign, 0
        report = guard.assess(parent(seeds=(1, 2), opponents=("arlene", "v1"), effect=effect))
        summary = report["seed_cluster_tail"]["summary"]
        self.assertEqual(summary["seed_own_regret"]["min"], 0)
        self.assertEqual(summary["seed_own_regret"]["max"], 0)
        self.assertEqual(summary["negative_opponent_seed_clusters"], 2)
        self.assertEqual(report["selection"]["verdict"], "SELECT_OWN_VALUE")

    def test_clean_clusters_preserve_composition(self):
        report = guard.assess(parent())
        self.assertEqual(report["selection"]["verdict"], "SELECT_BOTH")
        self.assertTrue(report["selection"]["seed_cluster_nondominated"])
        self.assertFalse(report["selection"]["promotion_authorized"])

    def test_mirrored_seats_and_opponents_are_not_independent_replicates(self):
        report = guard.assess(parent(opponents=("arlene", "v1", "kaito")))
        self.assertEqual(report["grid"]["cells_per_arm"], 48)
        self.assertEqual(report["grid"]["independent_clusters"], 8)
        self.assertEqual(report["seed_cluster_tail"]["summary"]["opponent_seed_clusters"], 24)

    def test_within_seed_seat_offsets_are_paired(self):
        def effect(arm, opponent, seed, seat):
            del opponent
            if arm != "both":
                return {"control": 100, "own_value": 101, "certified_pressure": 101}[arm], 0
            return (95 if seed == 8 and seat == 0 else 107 if seed == 8 else 103), 0
        report = guard.assess(parent(effect=effect))
        self.assertEqual(report["seed_cluster_tail"]["seed_clusters"][-1]
                         ["own_cash_regret_vs_best_singleton"]["mean"], 0)
        self.assertEqual(report["selection"]["verdict"], "SELECT_BOTH")

    def test_no_eligible_singleton_makes_guard_inapplicable(self):
        report = guard.assess(parent(eligible={"own_value": False,
                                               "certified_pressure": False, "both": True}))
        self.assertFalse(report["seed_cluster_tail"]["applicable"])
        self.assertEqual(report["selection"]["verdict"], "SELECT_BOTH")

    def test_only_eligible_singleton_receives_fallback(self):
        def effect(arm, opponent, seed, seat):
            del opponent, seat
            return {"control": 100, "own_value": 99, "certified_pressure": 102,
                    "both": 101 if seed == 8 else 104}[arm], 0
        report = guard.assess(parent(effect=effect, eligible={"own_value": False,
                              "certified_pressure": True, "both": True}))
        self.assertEqual(report["selection"]["verdict"], "SELECT_CERTIFIED_PRESSURE")

    def test_lost_singleton_outcome_is_downgraded(self):
        def effect(arm, opponent, seed, seat):
            del opponent, seat
            if arm == "control": return 10, 9
            if arm in guard.SINGLES: return 12, 9
            return (8 if seed == 8 else 20), 9
        report = guard.assess(parent(effect=effect))
        self.assertGreater(report["seed_cluster_tail"]["summary"]
                           ["lost_singleton_outcome_cells"], 0)
        self.assertNotEqual(report["selection"]["verdict"], "SELECT_BOTH")

    def test_incomplete_duplicate_or_detached_cells_are_rejected(self):
        value = parent(); value["cells"].pop()
        with self.assertRaisesRegex(guard.EvidenceError, "incomplete"):
            guard.assess(value)
        value = parent(); value["cells"][-1] = copy.deepcopy(value["cells"][0])
        with self.assertRaisesRegex(guard.EvidenceError, "duplicate cell"):
            guard.assess(value)
        value = parent(); value["cells"][0]["arms"]["both"]["margin"] += 1
        with self.assertRaisesRegex(guard.EvidenceError, "detached margin"):
            guard.assess(value)

    def test_parent_cannot_authorize_promotion_or_select_ineligible_arm(self):
        value = parent(); value["selection"]["promotion_authorized"] = True
        with self.assertRaisesRegex(guard.EvidenceError, "must not authorize"):
            guard.assess(value)
        value = parent(); value["selection"]["eligible_against_control"]["both"] = False
        with self.assertRaisesRegex(guard.EvidenceError, "ineligible"):
            guard.assess(value)

    def test_requires_multiple_unique_seeds(self):
        with self.assertRaisesRegex(guard.EvidenceError, "at least two"):
            guard.assess(parent(seeds=(1,)))
        value = parent(seeds=(1, 2)); value["grid"]["seeds"] = [1, 1]
        with self.assertRaisesRegex(guard.EvidenceError, "duplicate seeds"):
            guard.assess(value)

    def test_strict_loader_and_digests(self):
        value = parent()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "parent.json"
            raw = json.dumps(value, sort_keys=True) + "\n"
            path.write_text(raw)
            loaded, byte_sha = guard.load(path)
            report = guard.assess(loaded, byte_sha256=byte_sha)
            self.assertEqual(report["parent_gate"]["byte_sha256"],
                             hashlib.sha256(raw.encode()).hexdigest())
            duplicate = Path(tmp) / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(guard.EvidenceError, "duplicate JSON"):
                guard.load(duplicate)
            nan = Path(tmp) / "nan.json"; nan.write_text('{"a":NaN}')
            with self.assertRaisesRegex(guard.EvidenceError, "non-finite"):
                guard.load(nan)

    def test_markdown_retains_boundary(self):
        text = guard.markdown(guard.assess(parent()))
        self.assertIn("SELECT_BOTH", text)
        self.assertIn("never authorizes promotion", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
