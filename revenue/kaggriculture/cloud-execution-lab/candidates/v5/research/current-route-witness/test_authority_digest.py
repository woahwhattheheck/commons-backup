# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

from current_route_witness import SCHEMA, bind_current_route_window


class Controller:
    def __init__(self):
        # `cur` is intentionally incidental: v3 authority is the immutable
        # current producer receipt supplied by the caller.
        self.cur = "uncommitted-proposal"
        self.R = {
            "main": [
                {"farmer": ["PASS"], "hands": [["PASS"]], "market": []},
                {"farmer": ["MOVE", "EAST"], "hands": [["WATER"]], "market": []},
                {"farmer": ["HARVEST"], "hands": [["PASS"]], "market": [["SELL", "CARROT", 1]]},
                {"farmer": ["PASS"], "hands": [["PASS"]], "market": []},
            ]
        }


def observation(step: int, *, player: int = 0, hands: int = 1):
    farms = [
        {"farmer": [0, 0], "hands": []},
        {"farmer": [9, 9], "hands": []},
    ]
    farms[player]["hands"] = [[1, 0] for _ in range(hands)]
    return {
        "step": step,
        "player": player,
        "farms": farms,
        "private": {"inventories": [{} for _ in range(1 + hands)]},
    }


def receipt(obs, route="main"):
    return {
        "route_step": obs["step"],
        "last_step": obs["step"],
        "player": obs["player"],
        "route": route,
    }


class AlternateController(Controller):
    pass


class AuthorityDigestTests(unittest.TestCase):
    def bind(self, controller, obs, *, lookahead):
        return bind_current_route_window(
            controller,
            obs,
            completed_route_receipt=receipt(obs),
            lookahead=lookahead,
        )

    def test_schema_bumps_for_full_authority_digest(self):
        self.assertEqual(SCHEMA, "titan-v5-current-route-window-v3")

    def test_current_worker_authority_changes_window_digest(self):
        route = Controller()
        a = self.bind(route, observation(0, hands=1), lookahead=1)
        b = self.bind(route, observation(0, hands=2), lookahead=1)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual(a.route_sha256, b.route_sha256)
        self.assertEqual(a.rows[0].action_sha256, b.rows[0].action_sha256)
        self.assertNotEqual(a.current_worker_cardinality, b.current_worker_cardinality)
        self.assertNotEqual(a.window_sha256, b.window_sha256)

    def test_requested_lookahead_changes_digest_even_when_rows_truncate_equal(self):
        route = Controller()
        a = self.bind(route, observation(2), lookahead=1)
        b = self.bind(route, observation(2), lookahead=72)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual([row.receipt() for row in a.rows], [row.receipt() for row in b.rows])
        self.assertEqual(a.route_sha256, b.route_sha256)
        self.assertNotEqual(a.lookahead, b.lookahead)
        self.assertNotEqual(a.window_sha256, b.window_sha256)

    def test_controller_identity_changes_digest_for_identical_route_bytes(self):
        a_controller = Controller()
        b_controller = AlternateController()
        b_controller.R = copy.deepcopy(a_controller.R)
        a = self.bind(a_controller, observation(0), lookahead=2)
        b = self.bind(b_controller, observation(0), lookahead=2)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual(a.route_sha256, b.route_sha256)
        self.assertEqual([row.receipt() for row in a.rows], [row.receipt() for row in b.rows])
        self.assertNotEqual(a.controller_type, b.controller_type)
        self.assertNotEqual(a.window_sha256, b.window_sha256)

    def test_player_receipt_provenance_changes_digest(self):
        controller = Controller()
        a_obs = observation(0, player=0, hands=1)
        b_obs = observation(0, player=1, hands=1)
        a = self.bind(controller, a_obs, lookahead=1)
        b = self.bind(controller, b_obs, lookahead=1)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual(a.route_sha256, b.route_sha256)
        self.assertEqual(a.current_worker_cardinality, b.current_worker_cardinality)
        self.assertEqual([row.receipt() for row in a.rows], [row.receipt() for row in b.rows])
        self.assertNotEqual(a.player, b.player)
        self.assertNotEqual(a.window_sha256, b.window_sha256)

    def test_nonfinite_value_outside_requested_window_fails_closed(self):
        controller = Controller()
        controller.R["main"][3]["market"] = [["SELL", "CARROT", float("inf")]]
        self.assertIsNone(self.bind(controller, observation(0), lookahead=1))

    def test_nonfinite_value_in_requested_row_fails_closed(self):
        controller = Controller()
        controller.R["main"][1]["market"] = [["SELL", "CARROT", float("-inf")]]
        self.assertIsNone(self.bind(controller, observation(0), lookahead=1))


if __name__ == "__main__":
    unittest.main()
