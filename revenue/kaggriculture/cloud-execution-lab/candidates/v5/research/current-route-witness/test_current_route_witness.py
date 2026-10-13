# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

from current_route_witness import (
    MAX_LOOKAHEAD,
    ROUTE_SOURCE,
    SCHEMA,
    bind_b5_kwargs,
    bind_current_route,
    bind_current_route_window,
)


class Controller:
    def __init__(self):
        self.cur = "main"
        self.R = {
            "main": [
                {"farmer": ["PASS"], "hands": [["PASS"]], "market": []},
                {"farmer": ["MOVE", "EAST"], "hands": [["WATER"]], "market": []},
                {"farmer": ["HARVEST"], "hands": [["PASS"]], "market": [["SELL", "CARROT", 1]]},
                {"farmer": ["PASS"], "hands": [["PASS"]], "market": []},
            ],
            "alt": [
                {"farmer": ["PASS"], "hands": [["PASS"]], "market": []},
                {"farmer": ["MOVE", "WEST"], "hands": [["PASS"]], "market": []},
                {"farmer": ["PASS"], "hands": [["PASS"]], "market": []},
            ],
        }
        self.calls = 0

    def act(self, _obs):
        self.calls += 1
        raise AssertionError("route witness must not call producer")


def observation(step=0, player=0, hands=1):
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


def route_receipt(step=0, player=0, route="main"):
    return {
        "route_step": step,
        "last_step": step,
        "player": player,
        "route": route,
    }


def bind(controller, step=0):
    return bind_current_route(
        controller,
        observation(step),
        completed_route_receipt=route_receipt(step),
    )


class CurrentRouteWitnessTests(unittest.TestCase):
    def test_binds_exact_next_row_without_calling_producer(self):
        controller = Controller()
        witness = bind(controller)
        self.assertIsNotNone(witness)
        self.assertEqual(controller.calls, 0)
        self.assertEqual(witness.schema, SCHEMA)
        self.assertEqual(witness.route_source, ROUTE_SOURCE)
        self.assertEqual(witness.route_id, "main")
        self.assertEqual(witness.route_step, 0)
        self.assertEqual(witness.last_step, 0)
        self.assertEqual(witness.player, 0)
        self.assertEqual(witness.current_step, 0)
        self.assertEqual(witness.current_index, 0)
        self.assertEqual(witness.next_step, 1)
        self.assertEqual(witness.worker_cardinality, 2)
        self.assertEqual(witness.route_length, 4)
        self.assertEqual(
            witness.next_authored_action(),
            {"farmer": ["MOVE", "EAST"], "hands": [["WATER"]], "market": []},
        )
        self.assertEqual(len(witness.route_sha256), 64)
        self.assertEqual(len(witness.action_sha256), 64)
        self.assertEqual(len(witness.window_sha256), 64)

    def test_omitted_authority_fails_closed(self):
        controller = Controller()
        self.assertIsNone(bind_current_route(controller, observation(0)))
        self.assertIsNone(bind_b5_kwargs(controller, observation(0)))
        self.assertIsNone(bind_current_route_window(controller, observation(0), lookahead=1))

    def test_committed_route_authority_beats_raw_controller_cur(self):
        controller = Controller()
        controller.cur = "alt"
        witness = bind_current_route(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0, route="main"),
        )
        self.assertIsNotNone(witness)
        self.assertEqual(witness.route_id, "main")
        self.assertEqual(witness.next_authored_action()["farmer"], ["MOVE", "EAST"])
        self.assertNotEqual(witness.next_authored_action(), controller.R["alt"][1])

    def test_raw_cur_may_be_missing_when_receipt_is_valid(self):
        controller = Controller()
        controller.cur = "uncommitted-missing"
        witness = bind(controller)
        self.assertIsNotNone(witness)
        self.assertEqual(witness.route_id, "main")

    def test_explicit_alt_receipt_binds_alt_even_when_cur_is_main(self):
        controller = Controller()
        witness = bind_current_route(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0, route="alt"),
        )
        self.assertIsNotNone(witness)
        self.assertEqual(witness.route_id, "alt")
        self.assertEqual(witness.next_authored_action()["farmer"], ["MOVE", "WEST"])

    def test_receipt_must_be_current_exact_player_boundary(self):
        controller = Controller()
        obs = observation(2)
        bad = (
            {"route_step": 1, "last_step": 2, "player": 0, "route": "main"},
            {"route_step": 1, "last_step": 1, "player": 0, "route": "main"},
            {"route_step": 2, "last_step": 3, "player": 0, "route": "main"},
            {"route_step": 2, "last_step": 2, "player": 1, "route": "main"},
            {"route_step": True, "last_step": 2, "player": 0, "route": "main"},
            {"route_step": 2, "last_step": 2, "player": True, "route": "main"},
            {"route_step": 2, "last_step": 2, "player": 0, "route": True},
            {"route_step": 2, "last_step": 2, "player": 0, "route": "main", "extra": 1},
            {"route_step": 2, "last_step": 2, "route": "main"},
        )
        for receipt in bad:
            with self.subTest(receipt=receipt):
                self.assertIsNone(
                    bind_current_route_window(
                        controller,
                        obs,
                        completed_route_receipt=receipt,
                        lookahead=1,
                    )
                )

    def test_window_captures_ordered_rows_from_one_snapshot(self):
        controller = Controller()
        window = bind_current_route_window(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0),
            lookahead=3,
        )
        self.assertIsNotNone(window)
        self.assertEqual(controller.calls, 0)
        self.assertEqual([row.step for row in window.rows], [1, 2, 3])
        self.assertEqual([row.worker_cardinality for row in window.rows], [2, 2, 2])
        self.assertEqual(window.actions()[1]["market"], [["SELL", "CARROT", 1]])
        self.assertEqual(window.current_index, 0)
        self.assertEqual(window.lookahead, 3)

    def test_window_rows_may_bind_future_worker_cardinality_change(self):
        controller = Controller()
        controller.R["main"][2] = {
            "farmer": ["PASS"],
            "hands": [["PASS"], ["PASS"]],
            "market": [],
        }
        window = bind_current_route_window(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0),
            lookahead=2,
        )
        self.assertIsNotNone(window)
        self.assertEqual([row.worker_cardinality for row in window.rows], [2, 3])
        self.assertIsNotNone(window.b5_witness())

    def test_b5_rejects_immediate_worker_cardinality_change(self):
        controller = Controller()
        controller.R["main"][1]["hands"] = []
        window = bind_current_route_window(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0),
            lookahead=2,
        )
        self.assertIsNotNone(window)
        self.assertEqual(window.rows[0].worker_cardinality, 1)
        self.assertIsNone(window.b5_witness())
        self.assertIsNone(bind(controller))

    def test_capture_is_detached_from_later_route_mutation(self):
        controller = Controller()
        window = bind_current_route_window(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0),
            lookahead=2,
        )
        self.assertIsNotNone(window)
        before_digest = window.route_sha256
        controller.R["main"][1]["farmer"][0] = "BROKEN"
        self.assertEqual(window.actions()[0]["farmer"], ["MOVE", "EAST"])
        self.assertEqual(window.route_sha256, before_digest)

    def test_returned_action_is_detached_from_snapshot(self):
        controller = Controller()
        witness = bind(controller)
        self.assertIsNotNone(witness)
        action = witness.next_authored_action()
        action["farmer"][0] = "BROKEN"
        self.assertEqual(controller.R["main"][1]["farmer"], ["MOVE", "EAST"])
        self.assertEqual(witness.next_authored_action()["farmer"], ["MOVE", "EAST"])

    def test_controller_tape_is_not_mutated(self):
        controller = Controller()
        before = copy.deepcopy(controller.R)
        bind_current_route_window(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0),
            lookahead=3,
        )
        self.assertEqual(controller.R, before)

    def test_b5_adapter_is_exact(self):
        controller = Controller()
        kwargs = bind_b5_kwargs(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0),
        )
        self.assertEqual(
            kwargs,
            {
                "next_authored": {"farmer": ["MOVE", "EAST"], "hands": [["WATER"]], "market": []},
                "next_authored_step": 1,
            },
        )

    def test_route_digest_binds_rows_outside_requested_window(self):
        a = Controller()
        b = Controller()
        b.R["main"][3]["farmer"] = ["MOVE", "WEST"]
        wa = bind_current_route_window(
            a, observation(0), completed_route_receipt=route_receipt(0), lookahead=1
        )
        wb = bind_current_route_window(
            b, observation(0), completed_route_receipt=route_receipt(0), lookahead=1
        )
        self.assertIsNotNone(wa)
        self.assertIsNotNone(wb)
        self.assertNotEqual(wa.route_sha256, wb.route_sha256)
        self.assertEqual(wa.rows[0].action_sha256, wb.rows[0].action_sha256)
        self.assertNotEqual(wa.window_sha256, wb.window_sha256)

    def test_lookahead_is_exact_and_bounded(self):
        controller = Controller()
        kwargs = {"completed_route_receipt": route_receipt(0)}
        self.assertIsNone(bind_current_route_window(controller, observation(0), lookahead=True, **kwargs))
        self.assertIsNone(bind_current_route_window(controller, observation(0), lookahead=0, **kwargs))
        self.assertIsNone(bind_current_route_window(controller, observation(0), lookahead=MAX_LOOKAHEAD + 1, **kwargs))
        self.assertIsNotNone(bind_current_route_window(controller, observation(0), lookahead=MAX_LOOKAHEAD, **kwargs))

    def test_rejects_non_plain_step(self):
        class IntLike(int):
            pass

        controller = Controller()
        obs = observation(0)
        obs["step"] = IntLike(0)
        self.assertIsNone(
            bind_current_route(controller, obs, completed_route_receipt=route_receipt(0))
        )
        obs["step"] = True
        self.assertIsNone(
            bind_current_route(controller, obs, completed_route_receipt=route_receipt(0))
        )

    def test_rejects_bad_player_and_private_cardinality(self):
        controller = Controller()
        obs = observation(0)
        obs["player"] = True
        self.assertIsNone(
            bind_current_route(controller, obs, completed_route_receipt=route_receipt(0))
        )
        obs = observation(0)
        obs["private"]["inventories"] = [{}]
        self.assertIsNone(
            bind_current_route(controller, obs, completed_route_receipt=route_receipt(0))
        )

    def test_rejects_unknown_or_malformed_authorized_route(self):
        controller = Controller()
        for route in (None, "", True, "missing"):
            self.assertIsNone(
                bind_current_route(
                    controller,
                    observation(0),
                    completed_route_receipt=route_receipt(0, route=route),
                )
            )
        controller.R["main"] = {"not": "a route"}
        self.assertIsNone(bind(controller))

    def test_rejects_malformed_window_row(self):
        controller = Controller()
        controller.R["main"][2]["farmer"] = []
        self.assertIsNone(
            bind_current_route_window(
                controller,
                observation(0),
                completed_route_receipt=route_receipt(0),
                lookahead=2,
            )
        )
        controller = Controller()
        controller.R["main"][2]["market"] = None
        self.assertIsNone(
            bind_current_route_window(
                controller,
                observation(0),
                completed_route_receipt=route_receipt(0),
                lookahead=2,
            )
        )

    def test_rejects_end_of_route(self):
        controller = Controller()
        self.assertIsNone(bind(controller, 3))
        self.assertIsNone(
            bind_current_route_window(
                controller,
                observation(3),
                completed_route_receipt=route_receipt(3),
                lookahead=1,
            )
        )

    def test_rejects_non_json_route_anywhere_in_snapshot(self):
        controller = Controller()
        controller.R["main"][3]["market"] = [{"bad": object()}]
        self.assertIsNone(
            bind_current_route_window(
                controller,
                observation(0),
                completed_route_receipt=route_receipt(0),
                lookahead=1,
            )
        )

    def test_receipts_exclude_action_bytes_but_bind_digests(self):
        controller = Controller()
        window = bind_current_route_window(
            controller,
            observation(0),
            completed_route_receipt=route_receipt(0),
            lookahead=2,
        )
        self.assertIsNotNone(window)
        receipt = window.receipt()
        self.assertNotIn("action_json", repr(receipt))
        self.assertEqual(receipt["route_sha256"], window.route_sha256)
        self.assertEqual(receipt["window_sha256"], window.window_sha256)
        self.assertEqual(receipt["route_step"], 0)
        self.assertEqual(receipt["last_step"], 0)
        self.assertEqual(receipt["player"], 0)
        self.assertEqual(receipt["rows"][0]["action_sha256"], window.rows[0].action_sha256)
        witness = window.b5_witness()
        self.assertIsNotNone(witness)
        self.assertNotIn("next_authored", witness.receipt())
        self.assertEqual(witness.receipt()["route_sha256"], window.route_sha256)
        self.assertEqual(witness.schema, "titan-v5-current-route-window-v3")


if __name__ == "__main__":
    unittest.main()
