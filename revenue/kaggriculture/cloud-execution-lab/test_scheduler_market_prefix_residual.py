# SPDX-License-Identifier: Apache-2.0
"""Residual executable-prefix contracts after scheduler market grammar hardening."""
from __future__ import annotations

import copy
import unittest

import scheduler


class _Controller:
    def __init__(self, base, route):
        self.base = copy.deepcopy(base)
        self.cur = "r"
        self.R = {"r": route}

    def act(self, _obs):
        return copy.deepcopy(self.base)


def _route(length=64):
    return [
        {"farmer": ["PASS"], "hands": [], "market": []}
        for _ in range(length)
    ]


def _obs(step=5):
    return {
        "step": step,
        "player": 0,
        "farms": [
            {"tiles": [], "unlocked_quadrants": [0], "hires_today": 0},
            {"tiles": []},
        ],
        "market": {"inventory": {"MILK": 100}, "params": None, "prices": {}},
        "town": {"unlocked_shops": []},
        "private": {},
    }


class SchedulerMarketPrefixResidualTests(unittest.TestCase):
    def _patch_post_units(self, shed):
        original = scheduler.post_units
        scheduler.post_units = lambda *_a, **_k: (
            {"money": 100, "tiles": [], "hands": []},
            {"shed": dict(shed), "inventories": []},
        )
        self.addCleanup(setattr, scheduler, "post_units", original)

    def test_inert_suffix_sell_is_preserved_and_does_not_clear_pending(self):
        base = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "MILK", 1], ["SELL", "MILK", 99, "suffix"]],
        }
        actor = scheduler.SellScheduler("naive")
        actor.controller = _Controller(base, _route())
        self._patch_post_units({"MILK": 5})

        out = actor.act(_obs(), {"maxMarketOrdersPerTurn": 1, "episodeSteps": 720})

        self.assertEqual(out["market"], base["market"])
        self.assertEqual(actor.pending.get("MILK"), 4)

    def test_nonpositive_cap_still_allows_engine_first_slot_append(self):
        base = {"farmer": ["PASS"], "hands": [], "market": []}
        actor = scheduler.SellScheduler("naive")
        actor.controller = _Controller(base, _route())
        self._patch_post_units({"MILK": 5})

        out = actor.act(_obs(), {"maxMarketOrdersPerTurn": 0, "episodeSteps": 720})

        self.assertEqual(out["market"], [["SELL", "MILK", 5]])
        self.assertEqual(actor.pending.get("MILK"), 0)

    def test_future_reference_and_full_slot_credit_ignore_suffix_sell(self):
        base = {"farmer": ["PASS"], "hands": [], "market": [[]]}
        route = _route()
        route[6]["market"] = [[], ["SELL", "MILK", 5, "suffix"]]
        actor = scheduler.SellScheduler("candidate")
        actor.controller = _Controller(base, route)
        actor.receipt_profile = lambda *_a, **_k: (lambda _plan: True)
        self._patch_post_units({"MILK": 5})

        captured = {}
        original_optimize = scheduler.optimize_lot

        def fake_optimize_lot(**kwargs):
            captured["reference"] = tuple(kwargs["reference"])
            captured["future_feasible"] = kwargs["capacity_ok"](((5, 0), (6, 5)))
            return tuple(kwargs["reference"]), {
                "worst_relative_gain": 0.0,
                "forced_feasibility": False,
                "plan": list(kwargs["reference"]),
            }

        scheduler.optimize_lot = fake_optimize_lot
        self.addCleanup(setattr, scheduler, "optimize_lot", original_optimize)

        actor.act(_obs(), {"maxMarketOrdersPerTurn": 1, "episodeSteps": 720})

        self.assertNotIn((6, 5), captured["reference"])
        self.assertFalse(captured["future_feasible"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
