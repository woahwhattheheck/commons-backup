# SPDX-License-Identifier: Apache-2.0
"""Tests for the differential fuzzer (diff_fuzz.py).

Covers: pin integrity, oracle sanity against known official semantics, the
hand-built adversarial templates as differential oracles, generator
determinism, shrinker minimization logic, and a bounded live fuzz run.
"""
from __future__ import annotations

import copy
import unittest

import diff_fuzz
from diff_fuzz import (
    ENGINE_BLOCK_SHA256,
    adapter_run,
    check_case,
    check_pins,
    directed_cases,
    gen_case,
    official_worker_phase,
    run_fuzz,
    shrink,
)
from mechanics_adapter import _TRANSITION_META_KEY
from test_mechanics_adapter import load_mechanics


class DiffFuzzTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_mechanics()
        cls.pins = check_pins()

    def test_pins_match_expected(self):
        self.assertEqual("044a4f9c0a4a44dde10ada57563238bcaf82075d",
                         self.pins["mechanics_git_blob"])
        self.assertEqual(ENGINE_BLOCK_SHA256, self.pins["engine_block_sha256"])

    def test_oracle_reproduces_11690_official_semantics(self):
        # The pinned official interpreter rewrites BOTH PLANT requests to PASS
        # when demand (2) exceeds seeds (1); BUILD_COOP then succeeds.
        name, initial, turns, params = directed_cases(self.m)[0]
        self.assertIn("#11690", name)
        o_farm, o_private, all_steps, all_blocked = official_worker_phase(
            self.m, initial["farm"], initial["private"], turns, **params)
        steps, blocked = all_steps[0], all_blocked[0]
        self.assertEqual({"WHEAT"}, blocked)
        self.assertEqual([["PASS"], ["BUILD_COOP"], ["PASS"]],
                         [s["effective_action"] for s in steps])
        self.assertEqual(1, o_private["seeds"]["WHEAT"])
        self.assertEqual({"kind": "COOP"}, o_farm["tiles"][1][1])

    def test_oracle_applies_unblocked_plants(self):
        name = "unblocked"
        initial = {
            "farm": {"farmer": [1, 1], "hands": [[2, 2]],
                     "tiles": [[None] * 4 for _ in range(4)], "money": 0},
            "private": {"shed": {}, "seeds": {"WHEAT": 2},
                        "inventories": [{}, {}]},
        }
        params = {"board_size": 4, "day": 1, "turns_per_day": 24,
                  "shed_capacity": 100}
        o_farm, o_private, all_steps, all_blocked = official_worker_phase(
            self.m, initial["farm"], initial["private"],
            [[["PLANT", "WHEAT"], ["PLANT", "WHEAT"]]], **params)
        steps, blocked = all_steps[0], all_blocked[0]
        self.assertEqual(set(), blocked)
        self.assertEqual(0, o_private["seeds"]["WHEAT"])
        self.assertEqual("PLANT", o_farm["tiles"][1][1]["kind"])
        self.assertEqual("PLANT", o_farm["tiles"][2][2]["kind"])
        self.assertTrue(all(s["changed"] for s in steps))

    def test_directed_templates_match_adapter(self):
        for name, initial, turns, params in directed_cases(self.m):
            with self.subTest(name=name):
                stats = check_case(self.m, initial, turns, **params)
                self.assertIsInstance(stats, dict)

    def test_generator_is_deterministic(self):
        first = gen_case(__import__("random").Random(42), self.m)
        second = gen_case(__import__("random").Random(42), self.m)
        self.assertEqual(first, second)

    def test_generator_emits_adversarial_pressure(self):
        # Over a few seeds the generator must produce PLANT oversubscription
        # shapes (the bug class under test), BUILD races, and shed ops.
        import random
        seen_plant = seen_build = seen_shed_op = False
        for seed in range(6):
            rng = random.Random(seed)
            for _ in range(40):
                _, turns, _ = gen_case(rng, self.m)
                flat = [a for turn in turns for a in turn]
                plants = sum(1 for a in flat
                             if isinstance(a, list) and a[:1] == ["PLANT"])
                if plants >= 2:
                    seen_plant = True
                if any(a in (["BUILD_COOP"], ["BUILD_PASTURE"]) for a in flat):
                    seen_build = True
                if any(isinstance(a, list) and a[:1] in (["PICKUP"], ["DROP"], ["PLACE"])
                       for a in flat):
                    seen_shed_op = True
        self.assertTrue(seen_plant, "no multi-PLANT pressure generated")
        self.assertTrue(seen_build, "no BUILD contention generated")
        self.assertTrue(seen_shed_op, "no shed ops generated")

    def test_shrink_minimizes_with_stubbed_oracle(self):
        # Shrinker logic is tested with a stubbed fingerprint so it does not
        # depend on the existence of a real adapter bug.
        calls = []

        def fake_fingerprint(mechanics, initial, turns, params):
            calls.append([list(t) for t in turns])
            flat = [a for turn in turns for a in turn]
            if any(a == ["TRIGGER"] for a in flat):
                return ("state-divergence", ("$.farm",))
            return ("ok", ())

        original = diff_fuzz._case_fingerprint
        diff_fuzz._case_fingerprint = fake_fingerprint
        try:
            initial, params = {}, {}
            shrunk, (kind, _sig) = shrink(
                self.m, initial,
                [[["PASS"], ["TRIGGER"], ["NORTH"], ["PASS"], ["DROP"]]], params)
            self.assertEqual(kind, "state-divergence")
            self.assertEqual([[["TRIGGER"]]], shrunk)
        finally:
            diff_fuzz._case_fingerprint = original
        self.assertGreater(len(calls), 0)

    def test_shrink_rejects_clean_case(self):
        name, initial, turns, params = directed_cases(self.m)[0]
        with self.assertRaises(ValueError):
            shrink(self.m, initial, turns, params)

    def test_adapter_walk_strips_internal_metadata(self):
        name, initial, turns, params = directed_cases(self.m)[0]
        farm, private, pruned = adapter_run(self.m, initial, turns, **params)
        self.assertNotIn(_TRANSITION_META_KEY, farm)
        self.assertNotIn(_TRANSITION_META_KEY, private)

    def test_bounded_live_fuzz_run_finds_no_mismatch(self):
        report = run_fuzz(self.m, cases=30, seeds=2, run_directed=True)
        self.assertEqual(0, report["mismatches_found"], report["mismatches"])
        self.assertEqual(len(directed_cases(self.m)) + 60, report["cases"])
        self.assertGreater(report["cases_per_second"], 0)

    def test_prune_path_is_exercised(self):
        # A lone ineffective WATER must prune in the adapter and stay a no-op
        # officially: exercises the prune-correctness leg of check_case.
        initial = {
            "farm": {"farmer": [1, 1], "hands": [],
                     "tiles": [[None] * 4 for _ in range(4)], "money": 0},
            "private": {"shed": {}, "seeds": {"WHEAT": 1}, "inventories": [{}]},
        }
        params = {"board_size": 4, "day": 1, "turns_per_day": 24,
                  "shed_capacity": 100}
        stats = check_case(self.m, copy.deepcopy(initial), [[["WATER"]]], **params)
        self.assertEqual([[0]], stats["pruned"])


if __name__ == "__main__":
    unittest.main()
