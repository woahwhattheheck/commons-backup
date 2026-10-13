#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest


HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load("animal_cadence_reachable_probe", "reachable_probe.py")
summary = _load("animal_cadence_reachable_summary", "summarize_reachable_probe.py")


def _event(step, action, *, player=0, position=(2, 1), wheat=1):
    return {
        "schema": "titan-v5/animal-cadence/reachable-probe/v1",
        "step": step,
        "player": player,
        "route_id": "route-a",
        "runtime_status": "completed",
        "parent_calls": 1,
        "relevant": [{
            "actor": 0,
            "action": [action],
            "position": list(position),
            "tile": {
                "kind": "PASTURE",
                "animal": "SHEEP",
                "fed_today": False,
                "cared_today": False,
                "consecutive_unfed": 0,
                "pending_care_bonus": 0,
            },
            "inventory": {"WHEAT": wheat},
        }],
        "action_sha256": "0" * 64,
    }


class ReachableProbeTest(unittest.TestCase):
    def setUp(self):
        self.original_agent = probe.CURRENT.agent
        self.original_instance = probe.CURRENT._INSTANCE
        self.original_output = probe.OUTPUT

    def tearDown(self):
        probe.CURRENT.agent = self.original_agent
        probe.CURRENT._INSTANCE = self.original_instance
        probe.OUTPUT = self.original_output

    def test_probe_is_observational_and_records_exact_prestate(self):
        output = {"farmer": ["FEED"], "hands": [["CARE"]], "market": []}
        probe.CURRENT.agent = lambda observation, configuration=None: output
        probe.CURRENT._INSTANCE = types.SimpleNamespace(
            controller=types.SimpleNamespace(cur="route-a"),
            diagnostics={"status": "completed", "parent_calls": 1},
        )
        observation = {
            "step": 8,
            "player": 0,
            "farms": [{
                "farmer": [2, 1],
                "hands": [[3, 1]],
                "tiles": [[{}, {}, {}, {}], [{}, {}, {
                    "kind": "PASTURE", "animal": "SHEEP",
                    "fed_today": False, "cared_today": False,
                    "consecutive_unfed": 0, "pending_care_bonus": 0,
                }, {
                    "kind": "PASTURE", "animal": "COW",
                    "fed_today": True, "cared_today": False,
                    "consecutive_unfed": 0, "pending_care_bonus": 0,
                }]],
            }],
            "private": {"inventories": [{"WHEAT": 1}, {}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            probe.OUTPUT = Path(directory) / "probe.jsonl"
            returned = probe.agent(copy.deepcopy(observation), {})
            self.assertIs(returned, output)
            event = json.loads(probe.OUTPUT.read_text())
        self.assertEqual(event["step"], 8)
        self.assertEqual(event["route_id"], "route-a")
        self.assertEqual([row["action"] for row in event["relevant"]], [["FEED"], ["CARE"]])
        self.assertEqual(event["relevant"][0]["inventory"], {"WHEAT": 1})
        self.assertFalse(event["relevant"][0]["tile"]["fed_today"])

    def test_non_service_action_has_no_receipt(self):
        output = {"farmer": ["NORTH"], "hands": [], "market": []}
        probe.CURRENT.agent = lambda observation, configuration=None: output
        observation = {"step": 0, "player": 0, "farms": [], "private": {}}
        with tempfile.TemporaryDirectory() as directory:
            probe.OUTPUT = Path(directory) / "probe.jsonl"
            self.assertIs(probe.agent(observation, {}), output)
            self.assertFalse(probe.OUTPUT.exists())


class ReachableSummaryTest(unittest.TestCase):
    def test_distinguishes_future_care_from_care_neutral_feed(self):
        events = [
            _event(8, "FEED", position=(2, 1)),
            _event(9, "CARE", position=(2, 1)),
            _event(10, "FEED", position=(3, 1)),
            _event(24, "CARE", position=(3, 1)),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in events))
            report = summary.summarize([path], turns_per_day=24)
        self.assertEqual(report["candidate_guard_feeds"], 2)
        self.assertEqual(report["care_dependent_guard_feeds"], 1)
        self.assertEqual(report["care_neutral_guard_feeds"], 1)
        self.assertEqual(report["first_followups"], [{"feed_step": 8, "care_step": 9}])

    def test_rejects_non_plain_day_length_and_bad_schema(self):
        with self.assertRaisesRegex(ValueError, "positive plain integer"):
            summary.summarize([], turns_per_day=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text(json.dumps({"schema": "wrong", "step": 0}) + "\n")
            with self.assertRaisesRegex(ValueError, "unexpected schema"):
                summary.summarize([path], turns_per_day=24)


if __name__ == "__main__":
    unittest.main()
