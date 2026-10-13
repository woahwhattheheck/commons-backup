# SPDX-License-Identifier: Apache-2.0
"""Real pinned-engine component cases, not new scored or held game panels."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from selected_seed_budget import compile_demand, transform, MAX_BRANCHES


def import_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PASS = {"farmer": ["PASS"], "hands": [], "market": []}


def action(market=None, farmer=None, hands=None):
    return {"farmer": farmer or ["PASS"], "hands": hands or [], "market": market or []}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.obs = {"step": 100, "player": 0, "farms": [{"money": 1000}, {"money": 1000}],
                    "private": {"seeds": {"WHEAT": 0}}, "market": {"inventory": {"WHEAT": 10000}}}
        self.cfg = {"episodeSteps": 104, "maxMarketOrdersPerTurn": 10}
        self.base = action([["BUY_SEED", "WHEAT", 9], ["HIRE"]])
        self.stock = {"WHEAT": 0}
        self.rows = [{"step": 101, "action": action(farmer=["PLANT", "WHEAT"])},
                     {"step": 102, "action": deepcopy(PASS)}]

    def contract(self, **kwargs):
        args = dict(post_unit_seeds=self.stock, continuations={"selected": self.rows}, complete=True)
        args.update(kwargs)
        return compile_demand(self.obs, self.cfg, self.base, **args)

    def apply(self, contract=None):
        return transform(self.obs, self.cfg, self.base, post_unit_seeds=self.stock,
                         contract=self.contract() if contract is None else contract)

    def test_bound_uses_rewritten_selected_continuation(self):
        out = self.apply()
        self.assertEqual(out["action"]["market"], [["BUY_SEED", "WHEAT", 1], ["HIRE"]])
        self.assertEqual(out["remaining_request_bounds"]["WHEAT"], 1)

    def test_maximum_per_crop_across_branches_not_average_or_sum(self):
        other = deepcopy(self.rows)
        other[0]["action"] = action(farmer=["PLANT", "TOMATO"], hands=[["PLANT", "TOMATO"]])
        demand = self.contract(continuations={"one_wheat": self.rows, "two_tomato": other})
        self.assertEqual(demand.bounds()["WHEAT"], 1)
        self.assertEqual(demand.bounds()["TOMATO"], 2)
        self.assertEqual(sum(demand.bounds().values()), 3)

    def test_current_post_unit_stock_and_reserve(self):
        self.stock = {"WHEAT": 2}
        out = self.apply(self.contract(reserves={"WHEAT": 3}))
        self.assertEqual(out["action"]["market"][0][2], 2)

    def test_possible_noop_and_nonexistent_worker_requests_count(self):
        self.rows[0]["action"] = action(farmer=["PLANT", "WHEAT"], hands=[["PLANT", "WHEAT"]] * 3)
        self.assertEqual(self.contract().bounds()["WHEAT"], 4)

    def test_future_seed_purchase_never_credited(self):
        self.rows[0]["action"]["market"] = [["BUY_SEED", "WHEAT", 100]]
        self.assertEqual(self.apply()["action"]["market"][0][2], 1)

    def test_incomplete_and_missing_horizon_leave_action(self):
        for c in (self.contract(complete=False), self.contract(continuations={}),
                  self.contract(continuations={"short": self.rows[:1]})):
            self.assertFalse(c.complete)
            self.assertEqual(self.apply(c)["action"], self.base)

    def test_dates_must_be_contiguous_excluding_current_units(self):
        for wrong in (100, 102, 103, True):
            rows = deepcopy(self.rows); rows[0]["step"] = wrong
            c = self.contract(continuations={"wrong": rows})
            self.assertFalse(c.complete)
            self.assertEqual(self.apply(c)["action"], self.base)

    def test_after_terminal_and_missing_explicit_pass_leave_action(self):
        rows = self.rows + [{"step": 103, "action": action(farmer=["PLANT", "WHEAT"])}]
        self.assertFalse(self.contract(continuations={"beyond_done": rows}).complete)
        self.rows[1].pop("action")
        self.assertFalse(self.contract().complete)

    def test_unknown_crop_and_malformed_hands_are_not_zero_demand(self):
        self.rows[0]["action"] = action(farmer=["PLANT", "UNKNOWN"])
        self.assertFalse(self.contract().complete)
        self.rows[0]["action"] = {"hands": "missing"}
        self.assertFalse(self.contract().complete)

    def test_branch_budget_and_terminal_empty_continuation(self):
        branches = {str(i): self.rows for i in range(MAX_BRANCHES + 1)}
        self.assertFalse(self.contract(continuations=branches).complete)
        self.obs["step"] = 102
        c = self.contract(continuations={"done": []})
        self.assertTrue(c.complete)
        self.assertEqual(self.apply(c)["action"]["market"][0], [])

    def test_stale_step_action_seeds_public_state_config(self):
        c = self.contract()
        cases = [deepcopy(self.obs) for _ in range(3)]
        cases[0]["step"] += 1
        cases[1]["farms"][0]["money"] -= 1
        cases[2]["market"]["inventory"]["WHEAT"] += 1
        for obs in cases:
            out = transform(obs, self.cfg, self.base, post_unit_seeds=self.stock, contract=c)
            self.assertEqual(out["action"], self.base)
            self.assertEqual(out["reason"], "stale_or_different_context")
        altered = deepcopy(self.base); altered["hands"] = [["PLANT", "TOMATO"]]
        for cfg, selected, stock in ((self.cfg, altered, self.stock),
                                     (self.cfg, self.base, {"WHEAT": 1}),
                                     ({**self.cfg, "episodeSteps": 105}, self.base, self.stock)):
            self.assertEqual(transform(self.obs, cfg, selected, post_unit_seeds=stock, contract=c)["action"], selected)

    def test_reserved_slots_extra_fields_and_extra_orders_unchanged(self):
        self.cfg["maxMarketOrdersPerTurn"] = 2
        self.base = action([["BUY_SEED", "WHEAT", 9, "metadata"], ["HIRE"], ["BUY_SEED", "WHEAT", 9]])
        out = self.apply()
        self.assertEqual(out["action"]["market"], [["BUY_SEED", "WHEAT", 1, "metadata"], ["HIRE"], ["BUY_SEED", "WHEAT", 9]])

    def test_inputs_and_returned_fallback_are_independent(self):
        before = deepcopy((self.obs, self.base, self.stock, self.rows))
        c = self.contract(); out = self.apply(c)
        out["action"]["farmer"].append("mutation")
        self.assertEqual((self.obs, self.base, self.stock, self.rows), before)
        fallback = transform(self.obs, self.cfg, self.base, post_unit_seeds=self.stock, contract=None)
        fallback["action"]["market"].clear()
        self.assertEqual(self.base, before[1])

    def test_invalid_stock_and_version_cannot_trim(self):
        with self.assertRaises(ValueError):
            self.contract(post_unit_seeds={"WHEAT": -1})
        self.assertEqual(self.apply(replace(self.contract(), version=999))["action"], self.base)
        c = self.contract()
        out = transform(self.obs, self.cfg, self.base, post_unit_seeds={"WHEAT": True}, contract=c)
        self.assertEqual(out["action"], self.base)

    def test_cli_uses_actual_input_and_emits_compiled_contract(self):
        payload = dict(observation=self.obs, configuration=self.cfg, selected_action=self.base,
                       post_unit_seeds=self.stock, continuations={"selected": self.rows}, complete=True)
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp)/"case.json", Path(tmp)/"result.json"
            inp.write_text(json.dumps(payload))
            run = subprocess.run([sys.executable, str(HERE/"selected_seed_budget.py"), str(inp), "--output", str(out)],
                                 capture_output=True, text=True, check=True)
            result = json.loads(out.read_text())
            self.assertEqual(result["action"], self.apply()["action"])
            self.assertTrue(result["contract"]["complete"])
            self.assertEqual(json.loads(run.stdout)["changes"], 1)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache = os.environ.get("KAG_ENGINE_DIR")
        if not cache:
            raise RuntimeError("KAG_ENGINE_DIR must point to the existing pinned engine cache; no download is attempted")
        cls.ev = import_file(HERE.parent / "cloud-eval/evaluate.py", "selected_seed_existing_eval")
        cls.engine, _ = cls.ev.get_engine(Path(cache))

    def state(self, seat, cash=1000, seeds=None, shed=None, end=102):
        engine = self.engine
        cfg = self.ev.Struct({k: v.get("default") if isinstance(v, dict) else v
                              for k, v in engine.specification["configuration"].items()})
        cfg.episodeSteps = end + 2
        farms = [engine._new_farm(10, cash), engine._new_farm(10, cash)]
        for f in farms:
            f["farmer"] = [0, 0]; f["hands"] = [[1, 0]]; f["hires_today"] = 1
        market, town = engine._new_market(), engine._new_town()
        state = []
        for i in (0, 1):
            private = engine._new_private(); private["inventories"].append({})
            if i == seat:
                private["seeds"].update(seeds or {}); private["shed"].update(shed or {})
            obs = self.ev.Struct(player=i, step=100, farms=farms, private=private, market=market, town=town, day=4, hour=4)
            state.append(self.ev.Struct(observation=obs, action=deepcopy(PASS), status="ACTIVE", reward=0))
        return state, self.ev.Struct(configuration=cfg, done=False, info={})

    def execute(self, state, env, seat, step, selected):
        for s in state:
            s.observation.step = step; s.action = deepcopy(PASS)
        state[seat].action = deepcopy(selected)
        self.engine.interpreter(state, env)

    def apply(self, state, env, seat, base, rows):
        # Use the actual interpreter with an empty market to expose current
        # post-unit seeds. These fixtures avoid EOD; no substitute unit model.
        shadow, shadow_env = deepcopy((state, env))
        units_only = deepcopy(base); units_only["market"] = []
        self.execute(shadow, shadow_env, seat, 100, units_only)
        stock = shadow[seat].observation.private["seeds"]
        obs = deepcopy(state[seat].observation)
        contract = compile_demand(obs, env.configuration, base, post_unit_seeds=stock,
                                  continuations={"selected": rows}, complete=True)
        return transform(obs, env.configuration, base, post_unit_seeds=stock, contract=contract)

    def test_rewritten_two_worker_planting_and_surplus_cash(self):
        for seat in (0, 1):
            s, e = self.state(seat, end=101)
            base = action([["BUY_SEED", "WHEAT", 9]])
            next_action = action(farmer=["PLANT", "WHEAT"], hands=[["PLANT", "WHEAT"]])
            rows = [{"step": 101, "action": next_action}]
            out = self.apply(s, e, seat, base, rows)
            self.assertEqual(out["action"]["market"][0], ["BUY_SEED", "WHEAT", 2])
            baseline, be = deepcopy((s, e))
            self.execute(s, e, seat, 100, out["action"]); self.execute(s, e, seat, 101, next_action)
            self.execute(baseline, be, seat, 100, base); self.execute(baseline, be, seat, 101, next_action)
            self.assertEqual(s[seat].observation.farms[seat]["tiles"], baseline[seat].observation.farms[seat]["tiles"])
            self.assertEqual(s[seat].reward - baseline[seat].reward, 70)
            self.assertEqual(s[seat].observation.private["seeds"]["WHEAT"], 0)
            self.assertEqual(s[seat].status, "DONE")

    def test_cash_limited_first_buy_does_not_cancel_later_funded_buy(self):
        for seat in (0, 1):
            s, e = self.state(seat, cash=0, shed={"WHEAT": 2}, end=101)
            base = action([["BUY_SEED", "WHEAT", 9], ["SELL", "WHEAT", 2], ["BUY_SEED", "WHEAT", 9]])
            next_action = action(farmer=["PLANT", "WHEAT"], hands=[["PLANT", "WHEAT"]])
            out = self.apply(s, e, seat, base, [{"step": 101, "action": next_action}])
            self.assertEqual([out["action"]["market"][i][2] for i in (0, 2)], [2, 2])
            self.execute(s, e, seat, 100, out["action"])
            self.assertEqual(s[seat].observation.private["seeds"]["WHEAT"], 2)
            self.assertEqual(s[seat].observation.farms[seat]["money"], 29)
            self.execute(s, e, seat, 101, next_action)
            self.assertEqual(s[seat].observation.farms[seat]["tiles"][0][0]["crop"], "WHEAT")
            self.assertEqual(s[seat].observation.farms[seat]["tiles"][0][1]["crop"], "WHEAT")

    def test_current_plant_consumption_uses_actual_post_unit_stock(self):
        for seat in (0, 1):
            s, e = self.state(seat, seeds={"WHEAT": 1}, end=102)
            base = action([["BUY_SEED", "WHEAT", 9]], farmer=["PLANT", "WHEAT"])
            move = action(farmer=["SOUTH"])
            plants = action(farmer=["PLANT", "WHEAT"], hands=[["PLANT", "WHEAT"]])
            rows = [{"step": 101, "action": move}, {"step": 102, "action": plants}]
            out = self.apply(s, e, seat, base, rows)
            self.assertEqual(out["action"]["market"][0][2], 2)
            for step, a in ((100, out["action"]), (101, move), (102, plants)):
                self.execute(s, e, seat, step, a)
            tiles = s[seat].observation.farms[seat]["tiles"]
            self.assertTrue(all(tiles[y][x]["crop"] == "WHEAT" for x, y in ((0, 0), (0, 1), (1, 0))))

    def test_same_turn_atomic_cancellation_not_repaired_by_market_buy(self):
        for seat in (0, 1):
            s, e = self.state(seat, seeds={"WHEAT": 1}, end=101)
            plants = action(farmer=["PLANT", "WHEAT"], hands=[["PLANT", "WHEAT"]])
            base = {**plants, "market": [["BUY_SEED", "WHEAT", 9]]}
            out = self.apply(s, e, seat, base, [{"step": 101, "action": plants}])
            self.assertEqual(out["action"]["market"][0][2], 1)
            self.execute(s, e, seat, 100, out["action"])
            self.assertIsNone(s[seat].observation.farms[seat]["tiles"][0][0])
            self.assertIsNone(s[seat].observation.farms[seat]["tiles"][0][1])
            self.execute(s, e, seat, 101, plants)
            self.assertEqual(s[seat].observation.farms[seat]["tiles"][0][0]["crop"], "WHEAT")

    def test_missing_input_negative_control_atomic_group_fails(self):
        for seat in (0, 1):
            s, e = self.state(seat, seeds={"WHEAT": 1}, end=101)
            plants = action(farmer=["PLANT", "WHEAT"], hands=[["PLANT", "WHEAT"]])
            self.execute(s, e, seat, 101, plants)
            self.assertIsNone(s[seat].observation.farms[seat]["tiles"][0][0])
            self.assertIsNone(s[seat].observation.farms[seat]["tiles"][0][1])
            self.assertEqual(s[seat].observation.private["seeds"]["WHEAT"], 1)

    def test_seed_storage_is_independent_of_full_shed(self):
        for seat in (0, 1):
            s, e = self.state(seat, shed={"WHEAT": 100}, end=101)
            base = action([["BUY_SEED", "WHEAT", 9]])
            nxt = action(farmer=["PLANT", "WHEAT"])
            out = self.apply(s, e, seat, base, [{"step": 101, "action": nxt}])
            self.execute(s, e, seat, 100, out["action"])
            self.assertEqual(s[seat].observation.private["seeds"]["WHEAT"], 1)
            self.assertEqual(sum(s[seat].observation.private["shed"].values()), 100)

    def test_freed_cash_can_enable_later_hire_negative_not_guaranteed_saving(self):
        for seat in (0, 1):
            s, e = self.state(seat, cash=233, end=101)
            # With 12 actual hands/hires the next HIRE costs233. The
            # unchanged later HIRE consumes the released seed-purchase cash.
            s[seat].observation.farms[seat]["hands"] = [[1, 0] for _ in range(12)]
            s[seat].observation.private["inventories"] = [{} for _ in range(13)]
            s[seat].observation.farms[seat]["hires_today"] = 12
            base = action([["BUY_SEED", "WHEAT", 9], ["HIRE"]])
            out = self.apply(s, e, seat, base, [{"step": 101, "action": deepcopy(PASS)}])
            baseline, be = deepcopy((s, e))
            self.execute(s, e, seat, 100, out["action"])
            self.execute(baseline, be, seat, 100, base)
            self.assertEqual(len(s[seat].observation.farms[seat]["hands"]), 13)
            self.assertEqual(len(baseline[seat].observation.farms[seat]["hands"]), 12)
            self.assertEqual(s[seat].observation.farms[seat]["money"], 0)
            self.assertEqual(baseline[seat].observation.farms[seat]["money"], 143)


if __name__ == "__main__":
    unittest.main(verbosity=2)
