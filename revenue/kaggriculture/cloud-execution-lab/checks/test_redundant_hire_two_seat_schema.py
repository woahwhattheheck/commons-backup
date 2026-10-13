from __future__ import annotations

import copy
import importlib.util
import pathlib
import types
import unittest

LAB = pathlib.Path(__file__).resolve().parents[1]
SOURCE = LAB / "reference" / "titan-current" / "redundant_hire.py"
spec = importlib.util.spec_from_file_location("current_redundant_hire", SOURCE)
redundant_hire = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(redundant_hire)


class TwoSeatPublicSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mechanics = types.SimpleNamespace(PRODUCTS=set())
        self.selected = {"farmer": ["PASS"], "hands": [], "market": []}

    def call(self, observation):
        selected_before = copy.deepcopy(self.selected)
        out, report = redundant_hire.propose_redundant_hires(
            self.mechanics,
            observation,
            {},
            self.selected,
            route=[],
            route_id="",
            route_switch_steps=[],
        )
        self.assertEqual(self.selected, selected_before)
        self.assertEqual(out, selected_before)
        return report

    def test_malformed_public_seat_schema_fails_closed_before_policy_checks(self):
        malformed = (
            {"farms": [], "player": 0},
            {"farms": [{}, {}, {}], "player": 0},
            {"farms": ({}, {}), "player": 0},
            {"farms": [{}, {}], "player": -1},
            {"farms": [{}, {}], "player": 2},
            {"farms": [{}, {}], "player": True},
            {"farms": [{}, {}], "player": 0.0},
            {"farms": [{}, {}], "player": "0"},
            {"player": 0},
            {"farms": [{}, {}]},
        )
        for observation in malformed:
            with self.subTest(observation=observation):
                report = self.call(observation)
                self.assertFalse(report["changed"])
                self.assertFalse(report["route_changed"])
                self.assertEqual(report["reason"], "unsupported_public_seat_schema")

    def test_both_literal_public_seats_pass_schema_gate(self):
        for player in (0, 1):
            with self.subTest(player=player):
                report = self.call({"farms": [{}, {}], "player": player, "step": 0})
                self.assertEqual(report["reason"], "no_positive_cost_hire")


if __name__ == "__main__":
    unittest.main()
