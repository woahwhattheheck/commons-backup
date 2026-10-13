# SPDX-License-Identifier: Apache-2.0
"""Focused F2 player-domain custody regression.

This is intentionally independent of the moving F2 mechanism test file.  The
broad donor spine currently carries only r04_feed_prebuy.py, so the serializer
can add this test as a new path together with the one-line helper hardening.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_feed_prebuy as lane  # noqa: E402


def _farm():
    return {
        "money": 5000.0,
        "farmer": [4, 4],
        "hands": [],
        "tiles": [[None for _ in range(10)] for _ in range(10)],
    }


def _observation(player=0, farms=None):
    return {
        "step": 39,
        "player": player,
        "farms": list(farms if farms is not None else [_farm()]),
        "private": {"shed": {"WHEAT": 0}, "inventories": [{}]},
        "market": {"prices": {"WHEAT": 30}},
    }


def _action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def _config():
    return {
        "episodeSteps": 720,
        "boardSize": 10,
        "turnsPerDay": 24,
        "shedCapacity": 100,
        "maxMarketOrdersPerTurn": 10,
        "marketParams": {},
    }


class F2PlayerDomainCustodyTests(unittest.TestCase):
    def test_player_two_three_farm_poison_fails_before_downstream_planning(self):
        farms = [_farm(), _farm(), _farm()]
        obs = _observation(player=2, farms=farms)
        parent = _action()
        with mock.patch.object(
            lane,
            "_remaining_day_cash_spend_free",
            side_effect=AssertionError("third-seat poison reached future-cash planning"),
        ), mock.patch.object(
            lane,
            "_next_v217_task",
            side_effect=AssertionError("third-seat poison reached V217 proxy planning"),
        ):
            self.assertIs(
                lane.apply_feed_prebuy(obs, parent, configuration=_config(), enabled=True),
                parent,
            )

    def test_player_zero_one_farm_view_is_not_rejected_by_cardinality(self):
        obs = _observation(player=0, farms=[_farm()])
        parent = _action()
        with mock.patch.object(
            lane,
            "_remaining_day_cash_spend_free",
            return_value=False,
        ) as cash_guard:
            self.assertIs(
                lane.apply_feed_prebuy(obs, parent, configuration=_config(), enabled=True),
                parent,
            )
        cash_guard.assert_called_once()

    def test_guard_itself_rejects_bool_negative_and_third_player(self):
        parent = _action()
        for player, farms in (
            (True, [_farm(), _farm()]),
            (-1, [_farm(), _farm()]),
            (2, [_farm(), _farm(), _farm()]),
        ):
            with self.subTest(player=player):
                self.assertFalse(lane._all_pass(_observation(player=player, farms=copy.deepcopy(farms)), parent))


if __name__ == "__main__":
    unittest.main()
