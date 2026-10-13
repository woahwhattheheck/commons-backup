import copy
import json
from pathlib import Path
import tempfile
import types
import unittest

import league
import variants


class VariantsTests(unittest.TestCase):
    def setUp(self):
        self.obs = {"day": 0, "hour": 1, "private": {"shed": {"WHEAT": 10}},
                    "town": {"unlocked_shops": ["Bread", "Bread", "Soup"]}}
        self.cfg = {"turnsPerDay": 24, "days": 30, "shedCapacity": 100}
        self.shops = {"Bread": ["WHEAT"], "Soup": ["CARROT", "TOMATO"]}
        self.action = {"market": [["SELL", "WHEAT", 10], ["SELL", "CARROT", 3],
                                  ["BUY", "SEED_WHEAT", 2], ["HIRE"], ["HIRE"]],
                       "units": [["MOVE", 0, 2, 3]]}

    def apply(self, variant):
        return variants.transform(self.action, self.obs, variant, self.shops, self.cfg)

    def test_sale_cadence_changes_only_sales_without_mutation(self):
        obs, action = copy.deepcopy(self.obs), copy.deepcopy(self.action)
        got = self.apply("sale_cadence")
        self.assertEqual(got["market"], [[], []] + self.action["market"][2:])
        self.assertEqual(got["units"], self.action["units"])
        self.assertEqual((self.obs, self.action), (obs, action))
        got["units"][0][1] = 99
        self.assertNotEqual(got["units"], self.action["units"])

    def test_final_day_uses_day_hour_without_step(self):
        self.obs["day"] = 29
        self.assertEqual(self.apply("sale_cadence"), self.action)
        self.assertEqual(self.apply("crop_demand"), self.action)

    def test_shed_capacity_release_uses_configuration(self):
        self.obs["private"]["shed"]["WHEAT"] = 80
        self.assertEqual(self.apply("sale_cadence"), self.action)

    def test_periodic_sale_release(self):
        self.obs["hour"] = 4
        self.assertEqual(self.apply("sale_cadence"), self.action)

    def test_duplicate_shops_and_official_crop_demand(self):
        got = self.apply("crop_demand")
        self.assertEqual(got["market"][0], ["SELL", "WHEAT", 10])
        self.assertEqual(got["market"][1], [])
        self.assertIn(["BUY", "SEED_WHEAT", 2], got["market"])

    def test_no_known_demand_does_not_invent_hold(self):
        self.obs["town"]["unlocked_shops"] = []
        self.assertEqual(self.apply("crop_demand"), self.action)

    def test_labor_is_observation_cadence_not_cross_game_state(self):
        got = self.apply("labor_cadence")
        self.assertEqual(got["market"][3:], [[], []])
        self.obs["hour"] = 2
        got = self.apply("labor_cadence")
        self.assertEqual(got["market"][3], ["HIRE"])
        self.assertEqual(got["market"][4], [])

    def test_unknown_and_invalid_parent_fail_closed(self):
        with self.assertRaises(ValueError): self.apply("unknown")
        with self.assertRaises(ValueError):
            variants.transform([], self.obs, "sale_cadence", self.shops, self.cfg)

    def test_engine_inert_non_list_market_is_independent_noop(self):
        for market in (17, "market", ("SELL",), {"bad": "shape"}):
            with self.subTest(market=market):
                action = {"market": market, "units": [["MOVE", 0, 2, 3]]}
                original = copy.deepcopy(action)
                got = variants.transform(action, self.obs, "sale_cadence", self.shops, self.cfg)
                self.assertEqual(got, original)
                self.assertIsNot(got, action)
                got["units"][0][1] = 99
                self.assertEqual(action, original)

    def test_sale_filter_preserves_raw_prefix_and_capped_suffix(self):
        action = {"market": [["SELL", "WHEAT", 1], ["SELL", "CARROT", 1],
                             ["HIRE"], ["SELL", "MELON", 1]],
                  "units": [["PASS"]]}
        cfg = dict(self.cfg, maxMarketOrdersPerTurn=1)
        got = variants.transform(action, self.obs, "sale_cadence", self.shops, cfg)
        self.assertEqual(got["market"],
                         [[], ["SELL", "CARROT", 1], ["HIRE"], ["SELL", "MELON", 1]])
        self.assertEqual(action["market"][0], ["SELL", "WHEAT", 1])

    def test_engine_market_cap_floor_is_raw_slot_floor(self):
        action = {"market": [["SELL", "WHEAT", 1], ["SELL", "CARROT", 1]]}
        cfg = dict(self.cfg, maxMarketOrdersPerTurn=0)
        got = variants.transform(action, self.obs, "sale_cadence", self.shops, cfg)
        self.assertEqual(got["market"], [[], ["SELL", "CARROT", 1]])

    def test_labor_filter_does_not_pull_capped_hire_forward(self):
        action = {"market": [["PASS"], ["PASS"], ["PASS"], ["HIRE"], ["HIRE"]]}
        cfg = dict(self.cfg, maxMarketOrdersPerTurn=4)
        got = variants.transform(action, self.obs, "labor_cadence", self.shops, cfg)
        self.assertEqual(got["market"], [["PASS"], ["PASS"], ["PASS"], [], ["HIRE"]])

    def test_crop_demand_filter_respects_executable_prefix(self):
        action = {"market": [["SELL", "CARROT", 1], ["SELL", "WHEAT", 1],
                             ["SELL", "CARROT", 1]]}
        cfg = dict(self.cfg, maxMarketOrdersPerTurn=2)
        got = variants.transform(action, self.obs, "crop_demand", self.shops, cfg)
        self.assertEqual(got["market"], [[], ["SELL", "WHEAT", 1], ["SELL", "CARROT", 1]])

    def test_inert_sell_grammar_is_preserved_and_trailing_fields_are_valid(self):
        rows = [["SELL", "WHEAT"],
                ["SELL", ["WHEAT"], 1],
                ["SELL", "WHEAT", "bad"],
                ["SELL", "WHEAT", 0],
                ["SELL", "WHEAT", float("nan")],
                ["SELL", "WHEAT", 1, "trailing"]]
        action = {"market": copy.deepcopy(rows)}
        got = variants.transform(action, self.obs, "sale_cadence", self.shops, self.cfg)
        self.assertEqual(got["market"][:-1], rows[:-1])
        self.assertEqual(got["market"][-1], [])
        self.assertEqual(action["market"], rows)

    def test_sell_quantity_overflow_remains_engine_fatal(self):
        action = {"market": [["SELL", "WHEAT", float("inf")]]}
        with self.assertRaises(OverflowError):
            variants.transform(action, self.obs, "sale_cadence", self.shops, self.cfg)

    def test_market_cap_overflow_remains_engine_fatal(self):
        action = {"market": [["SELL", "WHEAT", 1]]}
        cfg = dict(self.cfg, maxMarketOrdersPerTurn=float("inf"))
        with self.assertRaises(OverflowError):
            variants.transform(action, self.obs, "sale_cadence", self.shops, cfg)

    def test_hire_trailing_fields_match_atomic_engine_grammar(self):
        action = {"market": [["HIRE", "trailing"], ["HIRE"]]}
        got = variants.transform(action, self.obs, "labor_cadence", self.shops, self.cfg)
        self.assertEqual(got["market"], [[], []])

    def test_actual_actor_signature_and_stats(self):
        class Parent:
            def __init__(self, spec, cache, loader, rng_seed, startup_timeout=10):
                self.spec, self.args = spec, (cache, loader, rng_seed, startup_timeout)
                self.stats = {}
            def act(parent, obs, cfg, timeout):
                return {"kind": "action", "action": copy.deepcopy(self.action)}
        cls = variants.actor_class(Parent, self.shops)
        actor = cls("/tmp/a.py|league=sale_cadence", Path("cache"), Path("loader"), 123)
        self.assertEqual(actor.spec, "/tmp/a.py")
        self.assertEqual(actor.args[2:], (123, 10))
        actor.act(self.obs, self.cfg, 1.0)
        self.assertEqual(actor.stats["league_changed_turns"], 1)
        fresh = cls("/tmp/a.py|league=sale_cadence", Path("cache"), Path("loader"), 123)
        self.assertEqual(fresh.stats["league_changed_turns"], 0)

    def test_intact_actor_does_not_transform(self):
        class Parent:
            def __init__(self, *args, **kwargs): self.stats = {}
            def act(parent, *args): return {"kind": "action", "action": self.action}
        actor = variants.actor_class(Parent, self.shops)("/tmp/a.py")
        self.assertIs(actor.act(self.obs, self.cfg, 1)["action"], self.action)
        self.assertEqual(actor.stats["league_changed_turns"], 0)


class SummaryTests(unittest.TestCase):
    def rows(self):
        return [{"seed": 1, "seat": 0, "opponent": "arlene", "arm": arm,
                 "own_cash": own, "margin": margin, "outcome": out, "valid": True}
                for arm, own, margin, out in [("control", 100, -10, "loss"),
                    ("cap", 95, 5, "win"), ("carrot", 110, -2, "loss")]]

    def test_pair_cash_distinct_from_margin_and_flips(self):
        got = league.stratify(self.rows())
        cap = got["overall"]["cap"]
        self.assertEqual(cap["mean_paired_cash_delta"], -5)
        self.assertEqual(cap["mean_paired_margin_delta"], 15)
        self.assertEqual(cap["paired_flips"], {"loss->win": 1})
        self.assertEqual(got["ranking"][0], "cap")
        self.assertEqual(got["by_seat"]["0"], got["overall"])

    def test_incomplete_pair_rejected(self):
        with self.assertRaises(ValueError): league.stratify(self.rows()[:-1])

    def test_duplicate_pair_rejected(self):
        rows = self.rows()
        with self.assertRaises(ValueError): league.stratify(rows + [rows[0]])

    def test_empty_summary_rejected(self):
        with self.assertRaises(ValueError): league.stratify([])

    def test_nonfinite_summary_rejected(self):
        rows = self.rows(); rows[1]["own_cash"] = float("nan")
        with self.assertRaises(ValueError): league.stratify(rows)

    def test_invalid_game_cannot_be_ranked(self):
        rows = self.rows(); rows[1]["valid"] = False
        with self.assertRaises(ValueError): league.stratify(rows)

    def test_frozen_seeds_disjoint_and_full_panel_size(self):
        self.assertFalse(set(league.PANELS["development"]) & set(league.PANELS["evaluation"]))
        self.assertEqual(len(league.PANELS["development"]) * len(league.OPPONENTS) * len(league.ARMS) * 2, 60)


class FreezeTests(unittest.TestCase):
    def make_runtime(self, root):
        root.mkdir()
        paths = {k: k + ".py" for k in ("control", "cap", "carrot", "apex", "engine", "schema", "utils", "evaluator", "loader")}
        for path in paths.values(): (root/path).write_text("# pinned\n")
        (root/"assets.json").write_text(json.dumps({"paths": paths, "provenance": {"test": True}}))

    def test_freeze_verifies_and_detects_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"runtime"; self.make_runtime(root)
            frozen=league.freeze(root,Path(tmp)/"freeze.json"); league.verify(root,frozen)
            (root/"cap.py").write_text("# changed\n")
            with self.assertRaises(ValueError): league.verify(root,frozen)

    def test_added_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"runtime"; self.make_runtime(root)
            frozen=league.freeze(root,Path(tmp)/"freeze.json")
            (root/"extra.py").write_text("x")
            with self.assertRaises(ValueError): league.verify(root,frozen)

    def test_deleted_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"runtime"; self.make_runtime(root)
            frozen=league.freeze(root,Path(tmp)/"freeze.json")
            (root/"cap.py").unlink()
            with self.assertRaises(ValueError): league.verify(root,frozen)

    def test_no_overwrite_or_self_contaminating_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"runtime"; self.make_runtime(root)
            dest=Path(tmp)/"freeze.json"; league.freeze(root,dest)
            with self.assertRaises(FileExistsError): league.freeze(root,dest)
            with self.assertRaises(ValueError): league.freeze(root,root/"inside.json")


class EvaluatorContractTests(unittest.TestCase):
    def test_tie_keeps_real_bank_cash_and_variant_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("control", "cap", "engine", "loader"):
                (root / name).write_text("fixture")
            frozen = {"assets": {"paths": {name: name for name in
                      ("control", "cap", "engine", "loader")}}}
            fake_engine = types.SimpleNamespace(specification={})
            result = {"status": "complete", "scores": [0, 0],
                      "bank_snapshot": {"bank": [1234, 1234]},
                      "actors": [{}, {"league_changed_turns": 7}],
                      "steps": 720, "failure": None, "wall_seconds": 1.0,
                      "trace_sha256": "fixture"}
            def play(*args):
                self.assertEqual(args[1][1], str(root / "control") + "|league=sale_cadence")
                return result
            row, trace = league.run_game(root, frozen, types.SimpleNamespace(play=play),
                                         fake_engine, 1, 0, "arlene/sale_cadence", "cap")
            self.assertEqual((row["outcome"], row["own_cash"], row["margin"]),
                             ("tie", 1234.0, 0.0))
            self.assertEqual(row["opponent_changed_turns"], 7)
            self.assertEqual(row["actor_resources"], result["actors"])

    def test_trace_records_only_daily_and_final_economy_without_mutating_state(self):
        fake_engine = types.SimpleNamespace(specification={}, interpreter=lambda state, env: state)
        traced = league.TraceEngine(fake_engine, 0)
        observation = {"day": 0, "hour": 0, "farms": [{"money": 1}, {"money": 2}],
                       "private": {"shed": {"CARROT": 3}}, "town": {}, "market": {}}
        states = [types.SimpleNamespace(observation=observation, action={"market": []})
                  for _ in range(2)]
        for i in range(50):
            observation["hour"] = i % 24
            traced.interpreter(states, None)
        self.assertEqual([r["step"] for r in traced.trace], [0, 24, 42, 43, 44, 45, 46, 47, 48, 49])
        self.assertEqual(observation["private"]["shed"], {"CARROT": 3})
        self.assertNotIn("private", traced.trace[0])


if __name__=='__main__': unittest.main()
