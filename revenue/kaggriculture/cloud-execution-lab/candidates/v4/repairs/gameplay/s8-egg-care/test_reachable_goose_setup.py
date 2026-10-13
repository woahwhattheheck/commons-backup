# SPDX-License-Identifier: Apache-2.0
"""Run with --native-root CHECKED_TREE --candidate GENERATED_EXACT_S8.py.

Assertions use unittest and remain active under python -O. Full episodes are
shared within each test class; bad-input tests execute their own guarded paths.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import reachable_goose_setup as setup
import run_reachable_goose_gate as gate

CANDIDATE_SHA256 = "86be29534c8cfedef7d0b13043ec86586632b40eac2b16084dd1a9b6ac06d213"
ROOT = None
CANDIDATE = None


class ReachableGoose(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev, cls.engine, cls.identities = gate.get_engine(ROOT)
        cls.baseline, cls.fullshed, cls.control, cls.candidate, cls.freecare, cls.ablation = {}, {}, {}, {}, {}, {}
        for seat in (0, 1):
            cls.baseline[seat] = gate.run_game(cls.ev, cls.engine, 17, seat, audit=(seat == 0))
            cls.fullshed[seat] = gate.run_game(cls.ev, cls.engine, 17, seat, disposal=True, audit=(seat == 0))
            cls.control[seat] = gate.run_game(cls.ev, cls.engine, 17, seat, setup.identity_control, label="identity", disposal=True)
            adapter = gate.adapter_from_source(CANDIDATE, CANDIDATE_SHA256)
            cls.candidate[seat] = gate.run_game(cls.ev, cls.engine, 17, seat, adapter, label="candidate", disposal=True)
            cls.freecare[seat] = gate.run_game(cls.ev, cls.engine, 17, seat, setup.care_positive_control, label="freecare", disposal=True)
            cls.ablation[seat] = gate.run_game(cls.ev, cls.engine, 17, seat, setup.collect_ablation_control, label="ablation", disposal=True)
        cls.cfg = {k: v.get("default") if isinstance(v, dict) else v
                   for k, v in cls.engine.specification["configuration"].items()}
        cls.cfg["seed"] = None
        cls.obs0 = cls.baseline[0]["audit_rows"][0]["own_observation"]

    def test_all_runtime_members_are_authenticated(self):
        self.assertEqual(self.identities["runtime_members_authenticated"], 109)
        self.assertEqual(gate.digest(CANDIDATE), CANDIDATE_SHA256)

    def test_full_games_reach_official_final_callback(self):
        for group in (self.baseline, self.fullshed, self.control, self.candidate, self.freecare, self.ablation):
            for game in group.values():
                self.assertEqual(game["status"], "complete")
                self.assertEqual(game["counts"]["callbacks"], 719)
                self.assertEqual(game["final_goose_count"], 3)
                self.assertEqual(game["counts"]["geese_lost"], 0)

    def test_initializer_has_no_injected_animals_cash_or_stock(self):
        for game in (self.baseline[0], self.fullshed[0]):
            obs = game["audit_rows"][0]["own_observation"]
            farm = obs["farms"][0]
            self.assertEqual(farm["money"], 3000)
            self.assertEqual(gate.tile_count(farm), 0)
            self.assertEqual(sum(obs["private"]["shed"].values()), 0)
            self.assertEqual(obs["private"]["inventories"], [{}])

    def test_purchase_pickup_and_three_real_placements(self):
        for seat in (0, 1):
            game = self.fullshed[seat]
            self.assertEqual([p["step"] for p in game["placements"]], [3, 6, 10])
            self.assertEqual([p["carried_geese_before"] for p in game["placements"]], [3, 2, 1])
            self.assertTrue(all(p["action"] == ["PLACE", "GOOSE"] and p["delta"] == 1 for p in game["placements"]))
        after_buy = self.fullshed[0]["audit_rows"][0]["after_own_observation"]
        self.assertEqual(after_buy["private"]["shed"]["GOOSE"], 3)
        self.assertLess(after_buy["farms"][0]["money"], 3000)

    def test_every_goose_gets_real_daily_feed(self):
        for group in (self.baseline, self.fullshed, self.candidate):
            for game in group.values():
                self.assertEqual(game["counts"]["wheat_consumed_by_feed"], 90)

    def test_baseline_has_twenty_six_mechanical_opportunities(self):
        for game in (*self.baseline.values(), *self.fullshed.values()):
            rows = game["opportunities_before_price"]
            self.assertEqual(len(rows), 26)
            self.assertEqual([r["day"] for r in rows], list(range(2, 28)))

    def test_standard_cash_eventually_funds_full_shed(self):
        rows = self.fullshed[0]["opportunities_before_price"]
        full = [r for r in rows if r["shed_units"] == 100]
        self.assertTrue(full)
        self.assertEqual(full[0]["day"], 6)
        self.assertTrue(all(r["egg_price"] < r["fertilizer_price"] for r in self.candidate[0]["changes"]))

    def test_identity_preserves_complete_actions_world_and_cash(self):
        for seat in (0, 1):
            pair = gate.pair_result(self.fullshed[seat], self.control[seat])
            self.assertTrue(pair["same_action_trace"])
            self.assertTrue(pair["same_world_trace"])
            self.assertEqual(pair["delta_own"], 0)
            self.assertEqual(pair["delta_rival"], 0)
            self.assertEqual(pair["changed_actions"], 0)

    def test_exact_shared_candidate_engages_eleven_times(self):
        for seat in (0, 1):
            game = self.candidate[seat]
            self.assertEqual(len(game["changes"]), 11)
            self.assertEqual([r["step"] for r in game["changes"]], list(range(167, 648, 48)))
            self.assertTrue(all(r["shed_units"] == 100 for r in game["changes"]))
            self.assertEqual(game["counts"]["care_succeeded"], 11)

    def test_candidate_extra_eggs_are_produced_harvested_and_sold(self):
        for seat in (0, 1):
            old, new = self.fullshed[seat]["counts"], self.candidate[seat]["counts"]
            for name in ("eggs_produced_to_tile", "egg_harvested", "egg_sold_units"):
                self.assertEqual(new[name] - old[name], 11)
            self.assertEqual(new["egg_harvested"], 89)

    def test_candidate_loses_no_retained_fertilizer_or_feed(self):
        for seat in (0, 1):
            old, new = self.fullshed[seat]["counts"], self.candidate[seat]["counts"]
            self.assertEqual(old["fertilizer_collected_and_retained"], 63)
            self.assertEqual(new["fertilizer_collected_and_retained"], old["fertilizer_collected_and_retained"])
            self.assertEqual(new["fertilizer_sold_units"], old["fertilizer_sold_units"])
            self.assertEqual(new["wheat_consumed_by_feed"], old["wheat_consumed_by_feed"])

    def test_candidate_real_terminal_cash_gain_in_both_seats(self):
        for seat in (0, 1):
            pair = gate.pair_result(self.fullshed[seat], self.candidate[seat])
            self.assertEqual(pair["delta_own"], 577)
            self.assertEqual(pair["delta_rival"], 0)
            self.assertEqual(pair["delta_margin"], 577)

    def test_positive_control_is_distinct_from_source_candidate(self):
        for seat in (0, 1):
            pair = gate.pair_result(self.fullshed[seat], self.freecare[seat])
            self.assertEqual(pair["delta_eggs_harvested"], 13)
            self.assertEqual(pair["changed_actions"], 13)
            self.assertEqual(pair["delta_fertilizer_retained"], 0)
            self.assertEqual(pair["delta_margin"], 670)
            self.assertNotEqual(self.freecare[seat]["world_trace_sha256"], self.candidate[seat]["world_trace_sha256"])

    def test_ablation_exposes_early_admitted_fertilizer_cost(self):
        for seat in (0, 1):
            pair = gate.pair_result(self.fullshed[seat], self.ablation[seat])
            self.assertEqual(pair["delta_fertilizer_retained"], -4)
            self.assertEqual(pair["delta_margin"], -380)
            self.assertEqual(pair["delta_eggs_harvested"], 0)

    def test_terminal_stock_is_actually_liquidated(self):
        for group in (self.baseline, self.fullshed, self.control, self.candidate, self.freecare, self.ablation):
            for game in group.values():
                self.assertEqual(sum(game["final_own_shed"].values()), 0)

    def test_care_banks_after_current_production(self):
        events = {r["step"]: r for r in self.candidate[0]["production_events"] if r["site"] == [4, 4]}
        self.assertEqual(events[167]["produced"], 1)
        self.assertEqual(events[167]["pending_after"], 1)
        self.assertEqual(events[191]["produced"], 2)
        self.assertEqual(events[191]["pending_after"], 0)

    def test_setup_is_observation_driven_and_nonmutating(self):
        obs, cfg = copy.deepcopy(self.obs0), copy.deepcopy(self.cfg)
        before = gate.encoded([obs, cfg])
        first = setup.parent_action(obs, cfg)
        first["farmer"][0] = "BAD"
        self.assertEqual(setup.parent_action(obs, cfg)["farmer"], ["PASS"])
        self.assertEqual(before, gate.encoded([obs, cfg]))

    def test_clock_route_configuration_and_terminal_drift_rejected(self):
        for change in (lambda o, c: o.update(hour=1),
                       lambda o, c: o["farms"][0].update(farmer=[3, 3]),
                       lambda o, c: c.update(startingMoney=10000),
                       lambda o, c: c.update(turnsPerDay=25),
                       lambda o, c: o.update(step=719)):
            obs, cfg = copy.deepcopy(self.obs0), copy.deepcopy(self.cfg)
            change(obs, cfg)
            with self.assertRaises(ValueError):
                setup.parent_action(obs, cfg)

    def test_input_mutation_is_rejected(self):
        def bad(obs, action, cfg):
            obs["private"]["shed"]["EGG"] = 999
            return action
        with self.assertRaisesRegex(ValueError, "mutated"):
            gate.run_game(self.ev, self.engine, 17, 0, bad)

    def test_foreign_market_or_unit_changes_are_rejected(self):
        for item in ("market", "farmer"):
            def bad(obs, action, cfg, item=item):
                result = copy.deepcopy(action)
                result[item] = [] if item == "market" else ["NORTH"]
                return result
            with self.assertRaises(ValueError):
                gate.run_game(self.ev, self.engine, 17, 0, bad)

    def test_adapter_gets_only_public_config_and_own_private_view(self):
        seen = []
        def observe(obs, action, cfg):
            seen.append((cfg.get("seed"), set(obs)))
            self.assertNotIn("info", obs)
            self.assertNotIn("opponent_private", obs)
            return action
        game = gate.run_game(self.ev, self.engine, 17, 0, observe)
        self.assertEqual(len(seen), 719)
        self.assertTrue(all(seed is None for seed, _ in seen))
        self.assertEqual(game["world_trace_sha256"], self.baseline[0]["world_trace_sha256"])

    def test_source_changes_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.py"
            p.write_text("raise RuntimeError('must not execute')\n")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                gate.adapter_from_source(p, CANDIDATE_SHA256)
            with self.assertRaisesRegex(ValueError, "hexadecimal"):
                gate.adapter_from_source(p, "x" * 64)

    def test_runtime_corruption_and_missing_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "native"
            shutil.copytree(ROOT, root)
            main = root / "main.py"
            raw = main.read_bytes()
            main.write_bytes(raw + b"\n")
            with self.assertRaisesRegex(ValueError, "member mismatch"):
                gate.authenticate(root)
            main.write_bytes(raw)
            main.unlink()
            with self.assertRaisesRegex(ValueError, "member mismatch"):
                gate.authenticate(root)

    def test_pair_coordinate_and_fixture_mismatch_rejected(self):
        wrong = copy.deepcopy(self.candidate[0])
        for key, value in (("seat", 1), ("seed", 101), ("fixture", "ordinary")):
            bad = dict(wrong, **{key: value})
            with self.assertRaises(ValueError):
                gate.pair_result(self.fullshed[0], bad)

    def test_pair_uses_own_minus_rival_not_raw_own_gain(self):
        base = {"seed": 1, "seat": 0, "fixture": "ordinary", "own": 100, "rival": 80,
                "margin": 20, "action_trace_sha256": "a", "world_trace_sha256": "b",
                "counts": {"egg_harvested": 2, "fertilizer_collected_and_retained": 3}}
        new = dict(base, own=110, rival=105, margin=5, label="test", changes=[])
        pair = gate.pair_result(base, new)
        self.assertEqual(pair["delta_own"], 10)
        self.assertEqual(pair["delta_rival"], 25)
        self.assertEqual(pair["delta_margin"], -15)

    def test_reachable_original_schema_guard_keeps_noop_identity(self):
        # Uses an actual legal observation, not an invented mature-goose fixture.
        obs = self.baseline[0]["audit_rows"][167]["own_observation"]
        parent = setup.parent_action(obs, self.cfg)
        mod = gate.import_path(CANDIDATE, "reachable_test_exact_candidate")
        self.assertIs(mod.apply_egg_care(obs, parent, self.cfg, enabled=False), parent)
        self.assertIs(mod.apply_egg_care(obs, parent, self.cfg, enabled=True, price_mode="donor"), parent)
        self.assertIs(mod.apply_egg_care(obs, parent, self.cfg, enabled=True), parent)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args, unittest_args = parser.parse_known_args()
    ROOT, CANDIDATE = args.native_root.resolve(), args.candidate.resolve()
    unittest.main(argv=[sys.argv[0], *unittest_args], verbosity=2)
