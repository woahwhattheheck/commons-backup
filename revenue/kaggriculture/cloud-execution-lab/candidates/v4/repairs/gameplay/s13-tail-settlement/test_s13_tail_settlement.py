# SPDX-License-Identifier: Apache-2.0
"""Standalone S13 boundary/quantity tests, not a full-engine or economic panel."""
from copy import deepcopy
import hashlib
import itertools
from pathlib import Path
import random
import unittest
from unittest.mock import patch

import s13_tail_settlement as guard


def observation(step=717, stock=10):
    return {"step": step, "market": {"inventory": {"MILK": 10000, "WHEAT": 10000}},
            "private": {"shed": {"MILK": stock, "WHEAT": stock}}}


def action(quantity=1):
    return {"farmer": ["PASS"], "hands": [], "market": [["SELL", "MILK", quantity]],
            "metadata": {"owner": "parent"}}


def project(obs, selected, cfg):
    """Contract fixture only: unit-stage DROP adds explicit fixture cargo."""
    private = deepcopy(obs["private"])
    if selected.get("farmer") == ["DROP"]:
        for item, qty in obs.get("fixture_cargo", {}).items():
            private["shed"][item] = private["shed"].get(item, 0) + qty
    return {}, private


def call(obs=None, cfg=None, selected=None, **kw):
    return guard.compose_tail_settlement(
        observation() if obs is None else obs, cfg,
        action() if selected is None else selected,
        project_units=kw.pop("project_units", project), enabled=kw.pop("enabled", True), **kw)


class S13BoundaryTests(unittest.TestCase):
    def test_exact_donor_custody(self):
        data = (Path(__file__).parent / "legacy" / "tail_settlement.py").read_bytes()
        self.assertEqual(len(data), 20360)
        self.assertEqual(hashlib.sha256(data).hexdigest(), guard.DONOR_SHA256)
        self.assertEqual(hashlib.sha1(b"blob 20360\0" + data).hexdigest(),
                         "6a08f2febbe1c5012482ccc5ee1ed2b787ae75f4")

    def test_disabled_is_opaque_and_identity(self):
        opaque = object()
        with patch.object(guard, "_donor", side_effect=AssertionError("must not load")):
            out, report = guard.compose_tail_settlement(
                opaque, opaque, opaque, project_units=opaque)
        self.assertIs(out, opaque)
        self.assertEqual(report["reason"], "disabled")

    def test_invalid_enabled_or_flags_never_project(self):
        for key in ("enabled", "consumption_safe", "net_new_only", "require_certified_reserve"):
            for value in (0, 1, "false", None, []):
                with self.subTest(key=key, value=value):
                    parent = action()
                    out, r = call(selected=parent, **{key: value},
                                  project_units=lambda *a: self.fail("projected poison"))
                    self.assertIs(out, parent)
                    self.assertFalse(r["execution_certified"])

    def test_default_shop_boundary(self):
        for step in range(670, 720):
            out, r = call(observation(step))
            self.assertEqual(out["market"][0][2], 10 if step in (717, 718) else 1)

    def test_known_nonshop_center_boundary(self):
        for step in range(670, 720):
            out, r = call(observation(step), shop_consumed={"WHEAT"})
            self.assertEqual(out["market"][0][2], 10 if 697 <= step <= 718 else 1)

    def test_poison_shop_set_cannot_widen(self):
        for value in ("MILK", b"MILK", {"MILK": True}, ["MILK", 1], [1],
                      {"UNKNOWN"}, False, iter(["MILK"]), 1):
            with self.subTest(value=repr(value)):
                parent = action()
                out, r = call(observation(700), selected=parent, shop_consumed=value)
                self.assertIs(out, parent)
                self.assertEqual(r["reason"], "invalid_shop_consumed")

    def test_supported_shop_collections(self):
        for collection in ({"MILK"}, frozenset({"MILK"}), ["MILK"], ("MILK",)):
            self.assertEqual(call(observation(700), shop_consumed=collection)[0], action())
            self.assertEqual(call(observation(717), shop_consumed=collection)[0]["market"][0][2], 10)

    def test_later_center_clock_holds_shop_product(self):
        cfg = {"townShopSellInterval": 24, "townCenterSellInterval": 4}
        self.assertEqual(call(observation(700), cfg)[0], action())
        self.assertEqual(call(observation(717), cfg)[0]["market"][0][2], 10)

    def test_config_clock_is_used_without_override(self):
        cfg = {"townShopSellInterval": 3}
        self.assertEqual(call(observation(717), cfg)[0], action())
        self.assertEqual(call(observation(718), cfg)[0]["market"][0][2], 10)

    def test_explicit_legacy_clocks_must_match_config(self):
        for kw in ({"shop_interval": 3}, {"town_interval": 4},
                   {"shop_interval": 4.0}, {"town_interval": True}):
            parent = action()
            out, r = call(selected=parent, **kw)
            self.assertIs(out, parent)
            self.assertEqual(r["reason"], "clock_configuration_mismatch")
        self.assertEqual(call(shop_interval=4, town_interval=24)[0]["market"][0][2], 10)

    def test_malformed_configuration_fails_closed(self):
        for cfg in (1, True, [], (), "bad"):
            parent = action()
            out, r = call(cfg=cfg, selected=parent)
            self.assertIs(out, parent)
            self.assertEqual(r["reason"], "malformed_inputs")

    def test_calendar_and_cap_types(self):
        for key in ("episodeSteps", "maxMarketOrdersPerTurn", "townShopSellInterval", "townCenterSellInterval"):
            for bad in (True, 1.0, "4", 0, -1, None):
                parent = action()
                out, r = call(cfg={key: bad}, selected=parent)
                self.assertIs(out, parent)
                self.assertEqual(r["reason"], "invalid_calendar_or_cap")
        for bad in (True, 717.0, "717", -1, None):
            parent = action()
            self.assertIs(call(observation(bad), selected=parent)[0], parent)
        for bad in (True, 48.0, 0, -1, None):
            parent = action()
            self.assertIs(call(selected=parent, window=bad)[0], parent)

    def test_inactive_suffix_is_opaque(self):
        suffixes = [[], [None], [["HIRE"]], [False, {}, ["SELL", "BOGUS", -1]],
                    [["SELL", "MILK", 999]], [["SELL", "WHEAT", 999]], ["bad"]]
        for suffix in suffixes:
            parent = action()
            parent["market"] += deepcopy(suffix)
            before = deepcopy(parent)
            out, r = call(cfg={"maxMarketOrdersPerTurn": 1}, selected=parent)
            self.assertEqual(out["market"][0], ["SELL", "MILK", 10])
            self.assertEqual(out["market"][1:], suffix)
            self.assertEqual(parent, before)
            self.assertEqual(r["added_sell_units"], {"MILK": 9})

    def test_reachable_mixed_or_invalid_rows_reject(self):
        rows = [None, [], ["HIRE"], ["BUY_PRODUCT", "MILK", 1], ["SELL", "MILK", 0],
                ["SELL", "MILK", 1.0], ["SELL", "MILK", True], ["SELL", "NOPE", 1]]
        for row in rows:
            parent = action()
            parent["market"].append(row)
            out, r = call(selected=parent)
            self.assertIs(out, parent)
            self.assertEqual(r["reason"], "invalid_executable_sale_prefix")

    def test_duplicate_product_grows_only_last_executable(self):
        parent = action(2)
        parent["market"] += [["SELL", "WHEAT", 2], ["SELL", "MILK", 1], ["SELL", "MILK", 100]]
        out, r = call(cfg={"maxMarketOrdersPerTurn": 3}, selected=parent)
        self.assertEqual(out["market"], [["SELL", "MILK", 2], ["SELL", "WHEAT", 10],
                                         ["SELL", "MILK", 8], ["SELL", "MILK", 100]])
        self.assertEqual(r["added_sell_units"], {"MILK": 7, "WHEAT": 8})

    def test_parent_units_metadata_and_inputs_unchanged(self):
        obs, cfg, parent = observation(), {}, action()
        original = deepcopy((obs, cfg, parent))
        out, r = call(obs, cfg, parent)
        self.assertIs(out["farmer"], parent["farmer"])
        self.assertIs(out["hands"], parent["hands"])
        self.assertIs(out["metadata"], parent["metadata"])
        self.assertEqual((obs, cfg, parent), original)
        self.assertIsNot(out, parent)

    def test_noop_returns_parent_identity(self):
        for obs in (observation(100), observation(717, stock=1)):
            parent = action()
            self.assertIs(call(obs, selected=parent)[0], parent)

    def test_unfunded_parent_not_promoted(self):
        parent = action(11)
        out, r = call(selected=parent)
        self.assertIs(out, parent)
        self.assertEqual(r["reason"], "baseline_sell_not_fully_funded")

    def test_raw_arm_retained(self):
        out, r = call(observation(680), consumption_safe=False)
        self.assertEqual(out["market"][0][2], 10)
        self.assertTrue(r["execution_certified"])

    def test_net_new_no_production_is_identity(self):
        parent = action()
        self.assertIs(call(selected=parent, net_new_only=True)[0], parent)

    def test_net_new_grows_only_unit_increase(self):
        obs, parent = observation(stock=7), action()
        obs["fixture_cargo"] = {"MILK": 3}
        parent["farmer"] = ["DROP"]
        out, r = call(obs, selected=parent, net_new_only=True)
        self.assertEqual(out["market"][0][2], 4)
        self.assertEqual(r["added_sell_units"], {"MILK": 3})

    def test_reserve_and_combined_caps(self):
        obs, parent = observation(stock=7), action()
        obs["fixture_cargo"] = {"MILK": 3}
        parent["farmer"] = ["DROP"]
        out, r = call(obs, selected=parent, net_new_only=True,
                      require_certified_reserve=True, reserve={"MILK": 8})
        self.assertEqual(out["market"][0][2], 2)
        self.assertEqual(call(reserve={"MILK": 4})[0]["market"][0][2], 6)
        self.assertIs(call(selected=parent, require_certified_reserve=True)[0], parent)

    def test_invalid_reserve_fails_closed(self):
        for reserve in ({"MILK": True}, {"MILK": -1}, {"MILK": 1.0}, {"NOPE": 0}, [], 1):
            parent = action()
            out, r = call(selected=parent, reserve=reserve)
            self.assertIs(out, parent)
            self.assertEqual(r["reason"], "invalid_reserve")

    def test_projector_receives_detached_inputs(self):
        obs, cfg, parent = observation(), {}, action()
        before = deepcopy((obs, cfg, parent))
        def mutate(o, a, c):
            o["private"]["shed"]["MILK"] = 20
            a["farmer"][:] = ["DROP"]
            c["poison"] = True
            return {}, o["private"]
        out, r = call(obs, cfg, parent, project_units=mutate)
        self.assertEqual((obs, cfg, parent), before)
        self.assertEqual(out["farmer"], ["PASS"])

    def test_projector_failure_and_missing_shed(self):
        def error(*args):
            raise RuntimeError("projection unavailable")
        for projector in (error, lambda *a: None, lambda *a: ({}, {}),
                          lambda *a: ({}, {"shed": {"MILK": -1}}), None):
            parent = action()
            out, r = call(selected=parent, project_units=projector)
            self.assertIs(out, parent)
            self.assertFalse(r["execution_certified"])

    def test_missing_or_unknown_public_products(self):
        for inv in ({}, {"BOGUS": 10000}, None, []):
            obs, parent = observation(), action()
            obs["market"]["inventory"] = inv
            self.assertIs(call(obs, selected=parent)[0], parent)

    def test_exhaustive_calendar_admission(self):
        # Enumerate future clock pulses independently of implementation rounding.
        count = 0
        for horizon, shop, town, consumed in itertools.product(
                (80, 241, 720), (1, 3, 4, 7, 24, 31), (1, 3, 4, 7, 24, 31),
                (None, {"MILK"}, set())):
            final = horizon - 2
            for step in range(final - 47, final + 1):
                cfg = {"episodeSteps": horizon, "townShopSellInterval": shop,
                       "townCenterSellInterval": town}
                later = any(t % town == 0 or (consumed != set() and t % shop == 0)
                            for t in range(step, final + 1))
                out, r = call(observation(step), cfg, shop_consumed=consumed)
                self.assertEqual(out["market"][0][2], 1 if later else 10,
                                 (horizon, shop, town, consumed, step))
                count += 1
        self.assertEqual(count, 15552)

    def test_quantity_prefix_properties(self):
        rng = random.Random(20260911)
        for _ in range(800):
            milk, wheat = rng.randint(2, 100), rng.randint(1, 100)
            first, second = rng.randint(1, milk - 1), 1
            second = rng.randint(1, milk - first)
            parent = action(first)
            parent["market"] += [["SELL", "WHEAT", 1], ["SELL", "MILK", second]]
            suffix = rng.choice([[None], [["HIRE"]], [["SELL", "MILK", 999]], []])
            parent["market"] += deepcopy(suffix)
            obs = observation(stock=milk)
            obs["private"]["shed"]["WHEAT"] = wheat
            out, r = call(obs, {"maxMarketOrdersPerTurn": 3}, parent)
            self.assertEqual(out["market"][0], parent["market"][0])
            self.assertEqual(out["market"][0][2] + out["market"][2][2], milk)
            self.assertEqual(out["market"][1][2], wheat)
            self.assertEqual(out["market"][3:], suffix)
            self.assertEqual(len(out["market"]), len(parent["market"]))
            self.assertEqual(out["farmer"], parent["farmer"])

    def test_standard_valid_domain_matches_exact_donor(self):
        donor = guard._donor().compose_tail_settlement
        count = 0
        for step, consumed, raw, net, reserve in itertools.product(
                (670, 671, 696, 697, 700, 716, 717, 718, 719),
                (None, set(), {"MILK"}), (False, True), (False, True), (None, {"MILK": 4})):
            obs, parent = observation(stock=7), action()
            obs["fixture_cargo"] = {"MILK": 3}
            parent["farmer"] = ["DROP"]
            options = dict(shop_consumed=consumed, consumption_safe=not raw,
                           net_new_only=net, reserve=reserve)
            expected, _ = donor(obs, {}, parent, project_units=project, **options)
            actual, _ = call(obs, {}, parent, **options)
            self.assertEqual(actual, expected)
            count += 1
        self.assertEqual(count, 216)

    def test_five_executed_predecessor_discriminators(self):
        old = guard._donor().compose_tail_settlement
        obs, parent = observation(700), action()
        wrong, _ = old(obs, {}, parent, project_units=project, shop_consumed="MILK")
        self.assertEqual(wrong["market"][0][2], 10)
        self.assertEqual(call(obs, selected=parent, shop_consumed="MILK")[0], parent)
        wrong, _ = old(obs, {}, parent, project_units=project, shop_interval=24, town_interval=4)
        self.assertEqual(wrong["market"][0][2], 10)
        self.assertEqual(call(obs, {"townShopSellInterval": 24, "townCenterSellInterval": 4})[0], parent)
        wrong, _ = old(observation(717), {"townShopSellInterval": 3}, parent, project_units=project)
        self.assertEqual(wrong["market"][0][2], 10)
        self.assertEqual(call(observation(717), {"townShopSellInterval": 3})[0], parent)
        with self.assertRaises(TypeError):
            old(obs, 1, parent, project_units=project)
        self.assertIs(call(obs, 1, parent)[0], parent)
        parent["market"].append(["HIRE"])
        wrong, _ = old(observation(), {"maxMarketOrdersPerTurn": 1}, parent, project_units=project)
        self.assertEqual(wrong["market"][0][2], 1)
        self.assertEqual(call(observation(), {"maxMarketOrdersPerTurn": 1}, parent)[0]["market"][0][2], 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
