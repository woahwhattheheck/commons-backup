"""Focused and preserved-engine contracts for TITAN S08 maximin economics."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from s08_maximin import (  # noqa: E402
    SCENARIOS,
    Candidate,
    candidate_from_queue,
    choose,
    compare,
    feasible,
    preserves_inherited_prefix,
)

EVALUATOR = HERE / "reference/evaluator/evaluate.py"
LOADER = HERE / "reference/evaluator/loader.py"
ENGINE_DIR = HERE / "reference/engine"


def values(*xs):
    return dict(zip(SCENARIOS, xs))


class MaximinContractTests(unittest.TestCase):
    def test_expected_and_maximin_can_make_different_economic_choices(self):
        candidates = [
            Candidate("canonical", values(10, 10, 10, 10, 10), total_slots=2),
            Candidate("swing", values(20, 20, 20, 1, 20), inherited_slots=2, total_slots=3),
            Candidate("robust", values(12, 12, 12, 12, 12), inherited_slots=2, total_slots=3),
        ]
        result = compare(candidates)
        self.assertEqual(result["expected"].candidate, "swing")
        self.assertEqual(result["maximin"].candidate, "robust")
        self.assertEqual(result["canonical"].candidate, "canonical")

    def test_funding_survival_and_queue_preservation_are_hard_gates(self):
        rich = values(100, 100, 100, 100, 100)
        candidates = [
            Candidate("canonical", values(1, 1, 1, 1, 1), total_slots=1),
            Candidate("unfunded", rich, funding_ok=False, total_slots=1),
            Candidate("unsafe", rich, survival_ok=False, total_slots=1),
            Candidate("rewrote", rich, inherited_orders_preserved=False, total_slots=1),
            Candidate("clipped", rich, inherited_slots=2, total_slots=11, max_slots=10),
        ]
        self.assertEqual(choose(candidates, strategy="maximin").candidate, "canonical")

    def test_inherited_queue_is_exact_prefix_and_slot_clipped(self):
        inherited = [["SELL", "MILK", 2], ["SELL", "WHEAT", 1]]
        good = inherited + [["SELL", "EGG", 1]]
        self.assertTrue(preserves_inherited_prefix(inherited, good, 3))
        self.assertFalse(preserves_inherited_prefix(inherited, list(reversed(inherited)), 3))
        self.assertFalse(preserves_inherited_prefix(inherited, good, 2))
        c = candidate_from_queue(
            name="good", values=values(1, 1, 1, 1, 1), inherited=inherited, proposed=good, max_slots=3
        )
        self.assertTrue(feasible(c))
        self.assertEqual(c.added_slots, 1)

    def test_cash_hoarding_is_not_a_ranking_dimension_and_canonical_wins_economic_tie(self):
        # There is deliberately no reserve-cash field in Candidate. A plan that
        # merely keeps a different queue shape but has identical economics is a no-op.
        candidates = [
            Candidate("canonical", values(5, 5, 5, 5, 5), inherited_slots=3, total_slots=3),
            Candidate("idle_cash_shape", values(5, 5, 5, 5, 5), inherited_slots=3, total_slots=3),
        ]
        for strategy in ("expected", "maximin"):
            decision = choose(candidates, strategy=strategy)
            self.assertEqual(decision.candidate, "canonical")
            self.assertIn("no feasible measurable improvement", decision.reason)

    def test_scenario_panel_must_be_exact_and_finite(self):
        wrong_order = {name: 1.0 for name in reversed(SCENARIOS)}
        missing = dict(list(values(1, 1, 1, 1, 1).items())[:-1])
        extra = dict(values(1, 1, 1, 1, 1), hidden_rival_state=999.0)
        self.assertTrue(feasible(Candidate("reordered", wrong_order)))
        self.assertFalse(feasible(Candidate("missing", missing)))
        self.assertFalse(feasible(Candidate("extra", extra)))
        self.assertFalse(feasible(Candidate("nan", values(1, 1, 1, float("nan"), 1))))

    def test_weighted_expected_uses_same_five_scenario_panel(self):
        candidates = [
            Candidate("canonical", values(10, 10, 10, 10, 10)),
            Candidate("buy_defense", values(9, 9, 9, 30, 9)),
        ]
        uniform = choose(candidates, strategy="expected")
        weighted = choose(
            candidates,
            strategy="expected",
            weights={
                "no_rival": 0.24,
                "incumbent_forecast": 0.24,
                "mirror": 0.24,
                "max_rival_buy": 0.04,
                "max_rival_sell": 0.24,
            },
        )
        self.assertEqual(uniform.candidate, "buy_defense")
        self.assertEqual(weighted.candidate, "canonical")


@unittest.skipUnless(EVALUATOR.exists() and LOADER.exists() and ENGINE_DIR.exists(), "preserved engine not materialized")
class ExactEngineLockstepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("s08_evaluator", EVALUATOR)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load evaluator at {EVALUATOR}")
        cls.ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ev)
        cls.engine, cls.hashes = cls.ev.get_engine(ENGINE_DIR, LOADER)

    @staticmethod
    def pass_action():
        return {"farmer": ["PASS"], "hands": [], "market": []}

    def fixture(self, *, inventory=10000, money0=0, money1=0):
        e, S = self.engine, self.ev.Struct
        cfg = S({
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in e.specification["configuration"].items()
        })
        cfg.weedSpawnChance = 0
        farms = [e._new_farm(10, money0), e._new_farm(10, money1)]
        market = e._new_market()
        market["inventory"]["FERTILIZER"] = inventory
        e._refresh_prices(market)
        town = {"unlocked_shops": []}
        state = []
        for seat in range(2):
            private = e._new_private()
            state.append(S(
                observation=S(player=seat, step=1, day=0, hour=1, farms=farms, private=private, market=market, town=town),
                action=self.pass_action(), status="ACTIVE", reward=0,
            ))
        return state, S(configuration=cfg, done=False, info={"seed": 9600803})

    def run_market(self, state, env, own, rival):
        state[0].action["market"] = copy.deepcopy(own)
        state[1].action["market"] = copy.deepcopy(rival)
        self.engine._process_market(state, env)

    @staticmethod
    def money(state, seat):
        return state[0].observation.farms[seat]["money"]

    @staticmethod
    def shed(state, seat, item):
        return state[seat].observation.private["shed"].get(item, 0)

    def test_sell_sell_same_unit_uses_precommit_quote_for_both_seats(self):
        state, env = self.fixture(inventory=10000)
        state[0].observation.private["shed"]["FERTILIZER"] = 1
        state[1].observation.private["shed"]["FERTILIZER"] = 1
        quoted = self.engine.market_price("FERTILIZER", 10000)
        self.run_market(state, env, [["SELL", "FERTILIZER", 1]], [["SELL", "FERTILIZER", 1]])
        self.assertEqual([self.money(state, 0), self.money(state, 1)], [quoted, quoted])
        self.assertEqual(state[0].observation.market["inventory"]["FERTILIZER"], 10002)

    def test_sell_buy_same_unit_commits_from_same_public_prestate(self):
        inventory = 10000
        sell_quote = self.engine.market_price("FERTILIZER", inventory)
        buy_quote = self.engine.market_price("FERTILIZER", inventory - 1)
        state, env = self.fixture(inventory=inventory, money0=0, money1=buy_quote)
        state[0].observation.private["shed"]["FERTILIZER"] = 1
        self.run_market(state, env, [["SELL", "FERTILIZER", 1]], [["BUY_PRODUCT", "FERTILIZER", 1]])
        self.assertEqual(self.money(state, 0), sell_quote)
        self.assertEqual(self.money(state, 1), 0)
        self.assertEqual(self.shed(state, 1, "FERTILIZER"), 1)
        self.assertEqual(state[0].observation.market["inventory"]["FERTILIZER"], inventory)


if __name__ == "__main__":
    unittest.main()
