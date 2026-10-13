# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest

LAB = Path(__file__).resolve().parent
SOURCE = LAB / "main.py"


def _load_main():
    name = "titan_v5_root_entrypoint_identity_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("main.py loader unavailable")
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Features:
    budget_seconds = 1.0
    reserve_seconds = 0.01
    consumer = "frozen"


class _Instance:
    def __init__(self):
        self.features = _Features()
        self.town_procurement_enabled = False
        self._entrypoint_last_step = 25
        self._finalizer_checkpoint = {"marker": "checkpoint"}
        self.selected = {"marker": "selected"}
        self.post = {"marker": "post"}
        self.diagnostics = {}
        self.ready = True
        self.act_calls = 0

    def _export_spatial_recovery(self):
        return {"marker": "committed"}

    def act(self, observation, configuration, *, entry_started):
        self.act_calls += 1
        return {"farmer": ["PASS"], "hands": [], "market": []}


class _DeadlineExceeded(Exception):
    pass


class _Timer:
    def __init__(self, seconds):
        self.seconds = seconds
        self.expired = _DeadlineExceeded("expired")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _deadline_module():
    return types.SimpleNamespace(
        DeadlineExceeded=_DeadlineExceeded,
        _DeadlineTimer=_Timer,
        legal_pass=lambda obs: {"farmer": ["PASS"], "hands": [], "market": []},
        terminal_liquidation_fallback=lambda obs, cfg: {
            "farmer": ["PASS"], "hands": [], "market": []
        },
    )


class RootEntrypointIdentityExactnessTests(unittest.TestCase):
    def setUp(self):
        self.main = _load_main()
        self.old_titan_runtime = sys.modules.get("titan_runtime")
        fake_runtime = types.ModuleType("titan_runtime")
        fake_runtime.deadline = _deadline_module()
        sys.modules["titan_runtime"] = fake_runtime
        self._reset_root_state()

    def tearDown(self):
        if self.old_titan_runtime is None:
            sys.modules.pop("titan_runtime", None)
        else:
            sys.modules["titan_runtime"] = self.old_titan_runtime

    def _reset_root_state(self):
        self.instance = _Instance()
        self.recovery = {"last_step": 25, "state": {"marker": "recovery"}}
        self.main._INSTANCE = self.instance
        self.main._SPATIAL_RECOVERY = copy.deepcopy(self.recovery)

    def _assert_rejected_without_root_state_mutation(self, observation, configuration=None):
        selected = self.instance.selected
        checkpoint = self.instance._finalizer_checkpoint
        post = self.instance.post
        before_recovery = copy.deepcopy(self.main._SPATIAL_RECOVERY)
        with self.assertRaises(ValueError):
            self.main.agent(observation, configuration or {})
        self.assertIs(self.main._INSTANCE, self.instance)
        self.assertEqual(self.main._SPATIAL_RECOVERY, before_recovery)
        self.assertIs(self.instance.selected, selected)
        self.assertIs(self.instance._finalizer_checkpoint, checkpoint)
        self.assertIs(self.instance.post, post)
        self.assertEqual(self.instance.act_calls, 0)

    def test_player_must_be_exact_public_plain_int(self):
        for player in (True, False, "1", 1.0, -1, 2, None):
            with self.subTest(player=player):
                self._reset_root_state()
                self._assert_rejected_without_root_state_mutation(
                    {"player": player, "step": 25}
                )

    def test_supplied_step_must_be_present_nonnegative_plain_int(self):
        for step in (True, False, "25", 25.0, -1, None):
            with self.subTest(step=step):
                self._reset_root_state()
                self._assert_rejected_without_root_state_mutation(
                    {"player": 1, "step": step}
                )

    def test_day_hour_fallback_requires_exact_complete_clock(self):
        bad = (
            ({"player": 1, "day": True, "hour": 1}, {"turnsPerDay": 24}),
            ({"player": 1, "day": "1", "hour": 1}, {"turnsPerDay": 24}),
            ({"player": 1, "day": 1.0, "hour": 1}, {"turnsPerDay": 24}),
            ({"player": 1, "day": -1, "hour": 1}, {"turnsPerDay": 24}),
            ({"player": 1, "day": 1, "hour": True}, {"turnsPerDay": 24}),
            ({"player": 1, "day": 1, "hour": "1"}, {"turnsPerDay": 24}),
            ({"player": 1, "day": 1, "hour": 1.0}, {"turnsPerDay": 24}),
            ({"player": 1, "day": 1, "hour": -1}, {"turnsPerDay": 24}),
            ({"player": 1, "day": 1, "hour": 24}, {"turnsPerDay": 24}),
            ({"player": 1, "day": 1}, {"turnsPerDay": 24}),
            ({"player": 1, "hour": 1}, {"turnsPerDay": 24}),
            ({"player": 1, "day": None, "hour": 1}, {"turnsPerDay": 24}),
            ({"player": 1, "day": 1, "hour": None}, {"turnsPerDay": 24}),
        )
        for observation, configuration in bad:
            with self.subTest(observation=observation, configuration=configuration):
                self._reset_root_state()
                self._assert_rejected_without_root_state_mutation(
                    observation, configuration
                )

    def test_day_hour_fallback_requires_positive_plain_int_turns_per_day(self):
        for turns in (True, False, "24", 24.0, 0, -1, None):
            with self.subTest(turnsPerDay=turns):
                self._reset_root_state()
                self._assert_rejected_without_root_state_mutation(
                    {"player": 1, "day": 1, "hour": 1},
                    {"turnsPerDay": turns},
                )

    def test_redundant_clock_fields_must_agree_with_supplied_step(self):
        bad = (
            {"player": 1, "step": 25, "day": 0, "hour": 1},
            {"player": 1, "step": 25, "day": 1, "hour": 2},
            {"player": 1, "step": 25, "day": "1", "hour": 1},
            {"player": 1, "step": 25, "day": 1, "hour": 1.0},
            {"player": 1, "step": 25, "day": None, "hour": 1},
            {"player": 1, "step": 25, "day": 1, "hour": None},
        )
        for observation in bad:
            with self.subTest(observation=observation):
                self._reset_root_state()
                self._assert_rejected_without_root_state_mutation(
                    observation, {"turnsPerDay": 24}
                )

    def test_canonical_step_only_and_clock_forms_still_reach_runtime(self):
        cases = (
            ({"player": 1, "step": 25}, {}),
            ({"player": 1, "day": 1, "hour": 1}, {"turnsPerDay": 24}),
            (
                {"player": 1, "step": 25, "day": 1, "hour": 1},
                {"turnsPerDay": 24},
            ),
        )
        for observation, configuration in cases:
            with self.subTest(observation=observation, configuration=configuration):
                self._reset_root_state()
                output = self.main.agent(observation, configuration)
                self.assertEqual(
                    output, {"farmer": ["PASS"], "hands": [], "market": []}
                )
                self.assertEqual(self.instance.act_calls, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
