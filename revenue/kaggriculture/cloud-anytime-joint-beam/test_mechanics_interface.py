# SPDX-License-Identifier: Apache-2.0
"""Contract tests for the game-agnostic search/evaluator interface.

- The Kaggriculture worker-phase adapter and the toy grid game both satisfy
  the MechanicsProvider contract (``game_rules.run_provider_checks``).
- The beam core produces identical results through the interface and through
  the legacy module-level callables, proving the split is faithful, not a fork.
- The beam's search function touches no title vocabulary (game-agnostic guard),
  and a full beam search runs end-to-end on the toy game through the interface
  alone -- the same code path, a different title.
"""
from __future__ import annotations

import copy
import inspect
import unittest
from pathlib import Path

from joint_action_beam import (
    BeamConfig,
    search_joint_actions,
)
from game_rules import (
    MechanicsProvider,
    ProviderScenario,
    provider_callbacks,
    run_provider_checks,
)
from mechanics_adapter import (
    KaggricultureRules,
    KaggricultureScorer,
    MechanicsContext,
    bounded_worker_candidates,
    mechanics_scorer,
    mechanics_transition,
)
from test_mechanics_adapter import fixture, load_mechanics
from toy_grid_game import ToyGridRules, ToyScorer, initial_state as toy_initial

HERE = Path(__file__).resolve().parent

# Title vocabulary that must never appear in the search core. "worker" and
# "unit" are generic search terms; everything below names a specific title's
# state fields, actions, or goods.
_TITLE_TOKENS = (
    "farm",
    "farmer",
    "hands",
    "plant",
    "kaggriculture",
    "mechanics",
    "tile",
    "crop",
    "seed",
    "shed",
    "harvest",
    "apple",
    "basket",
    "picker",
    "toy",
)


def check_all(testcase: unittest.TestCase, rules, scenario: ProviderScenario) -> None:
    failures = [
        (check.name, check.detail)
        for check in run_provider_checks(rules, scenario)
        if not check.passed
    ]
    testcase.assertEqual([], failures, f"{scenario.name} contract failures")


def kaggriculture_scenario() -> ProviderScenario:
    return ProviderScenario(
        name="kaggriculture",
        initial_state=fixture(2),
        canonical=(["PASS"], ["PASS"]),
        probes=[
            (0, ["PASS"]),
            (0, ["EAST"]),
            (0, ["WEST"]),
            (0, ["NORTH"]),
            (1, ["PLANT", "WHEAT"]),
            (1, ["PASS"]),
            (0, ["BUILD_COOP"]),
        ],
        effective_probe=(0, ["EAST"]),
        max_candidates=64,
    )


def toy_scenario() -> ProviderScenario:
    return ProviderScenario(
        name="toy-grid",
        initial_state=toy_initial(),
        canonical=(["PASS"], ["PASS"]),
        probes=[
            (0, ["PASS"]),
            (0, ["E"]),
            (0, ["PICK"]),
            (0, ["N"]),
            (1, ["W"]),
            (1, ["PICK"]),
            (0, ["FLY"]),
        ],
        effective_probe=(0, ["PICK"]),
        max_candidates=64,
    )


class ProviderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_mechanics()
        cls.ctx = MechanicsContext(board_size=10, day=0, turns_per_day=24)
        cls.rules = KaggricultureRules(cls.m, cls.ctx)
        cls.toy = ToyGridRules()

    def test_kaggriculture_satisfies_provider_contract(self):
        check_all(self, self.rules, kaggriculture_scenario())

    def test_toy_grid_satisfies_provider_contract(self):
        check_all(self, self.toy, toy_scenario())

    def test_implementations_are_protocol_members(self):
        self.assertIsInstance(self.rules, MechanicsProvider)
        self.assertIsInstance(self.toy, MechanicsProvider)
        self.assertIsInstance(KaggricultureScorer(self.m), object)

    def test_titles_share_no_state_shape(self):
        # The two implementations' states are disjoint in structure: nothing
        # about the interface is shaped by either title's fields.
        kag_state = fixture(1)
        toy_state = toy_initial()
        self.assertNotIn("farm", toy_state)
        self.assertNotIn("private", toy_state)
        self.assertNotIn("units", kag_state)
        self.assertNotIn("apples", kag_state)
        # ... yet both keys are stable and hashable through the same method.
        self.assertEqual(
            self.rules.state_key(copy.deepcopy(kag_state)),
            self.rules.state_key(kag_state),
        )
        self.assertEqual(
            self.toy.state_key(copy.deepcopy(toy_state)),
            self.toy.state_key(toy_state),
        )


class InterfaceFidelityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_mechanics()
        cls.ctx = MechanicsContext(board_size=10, day=0, turns_per_day=24)

    def test_beam_via_interface_matches_legacy_callables(self):
        rules = KaggricultureRules(self.m, self.ctx)
        scorer = KaggricultureScorer(self.m)
        via_candidates, via_transition = provider_callbacks(rules)

        legacy_candidates = lambda s, i, c: bounded_worker_candidates(self.m, s, i, c)
        legacy_transition = mechanics_transition(self.m, self.ctx)
        legacy_scorer = mechanics_scorer(self.m)

        config = BeamConfig(width=8, depth=2, budget_ns=10_000_000_000)
        canonical = (["PASS"], ["PASS"])
        first = search_joint_actions(
            fixture(2), canonical, via_candidates, via_transition, scorer, config=config
        )
        second = search_joint_actions(
            fixture(2),
            canonical,
            legacy_candidates,
            legacy_transition,
            legacy_scorer,
            config=config,
        )
        self.assertTrue(first.complete)
        self.assertEqual(first.actions, second.actions)
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.reason, second.reason)

    def test_beam_search_core_touches_no_title_vocabulary(self):
        source = inspect.getsource(search_joint_actions).lower()
        for token in _TITLE_TOKENS:
            self.assertNotIn(token, source, f"title token in search core: {token}")

    def test_interface_module_names_no_title(self):
        # The interface file may reference implementation *module* names, but
        # must not name any title or its state fields, actions, or goods.
        source = (HERE / "game_rules.py").read_text().lower()
        for token in (
            "kaggriculture",
            "apple",
            "farm",
            "plant",
            "tile",
            "crop",
            "seed",
            "shed",
            "harvest",
            "picker",
            "basket",
        ):
            self.assertNotIn(token, source, f"title token in interface: {token}")

    def test_beam_solves_toy_game_through_interface_only(self):
        rules = ToyGridRules()
        scorer = ToyScorer()
        candidates, transition = provider_callbacks(rules)
        state = toy_initial()
        canonical = (["PASS"], ["PASS"])
        baseline = scorer(state, ())

        result = search_joint_actions(
            state,
            canonical,
            candidates,
            transition,
            scorer,
            config=BeamConfig(width=16, depth=2, budget_ns=10_000_000_000),
        )
        self.assertTrue(result.complete, result.reason)
        self.assertGreater(result.score, baseline)
        # Every emitted action is toy vocabulary; replay collects the apples.
        for action in result.actions:
            self.assertIn(action[0], ("N", "S", "E", "W", "PICK", "PASS"))
        replayed = copy.deepcopy(state)
        for idx, action in enumerate(result.actions):
            replayed = transition(replayed, idx, action)
            self.assertIsNotNone(replayed)
        collected = sum(replayed["baskets"])
        self.assertEqual(result.score, 100 * collected)
        self.assertGreaterEqual(collected, 1)

    def test_same_callback_shape_serves_both_titles(self):
        kag_candidates, kag_transition = provider_callbacks(
            KaggricultureRules(self.m, self.ctx)
        )
        toy_candidates, toy_transition = provider_callbacks(ToyGridRules())
        config = BeamConfig(width=8, depth=2, budget_ns=10_000_000_000)

        kag_result = search_joint_actions(
            fixture(2),
            (["PASS"], ["PASS"]),
            kag_candidates,
            kag_transition,
            KaggricultureScorer(self.m),
            config=config,
        )
        toy_result = search_joint_actions(
            toy_initial(),
            (["PASS"], ["PASS"]),
            toy_candidates,
            toy_transition,
            ToyScorer(),
            config=config,
        )
        self.assertTrue(kag_result.complete, kag_result.reason)
        self.assertTrue(toy_result.complete, toy_result.reason)
        self.assertTrue(all(isinstance(a, list) for a in kag_result.actions))
        self.assertTrue(
            all(a[0] in ("N", "S", "E", "W", "PICK", "PASS") for a in toy_result.actions)
        )


if __name__ == "__main__":
    unittest.main()
