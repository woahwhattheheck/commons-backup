# SPDX-License-Identifier: Apache-2.0
"""Exact public-identity regressions for the deadline fallback adapter."""
import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "reference/titan-current/deadline_adapter.py"
SPEC = importlib.util.spec_from_file_location("deadline_adapter_identity_under_test", SOURCE)
DEADLINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEADLINE)


def observation(*, player=0, step=0):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    farms = [
        {"farmer": [4, 4], "hands": [], "tiles": copy.deepcopy(tiles)},
        {"farmer": [4, 4], "hands": [[4, 4], [5, 4]], "tiles": copy.deepcopy(tiles)},
    ]
    obs = {
        "player": player,
        "farms": farms,
        "private": {"shed": {}, "inventories": [{}]},
    }
    if step is not ...:
        obs["step"] = step
    return obs


class RecordingProduction:
    def __init__(self):
        self.calls = 0
        self.seen = None

    def act(self, obs):
        self.calls += 1
        self.seen = copy.deepcopy(obs)
        return {"farmer": ["PASS"], "hands": [], "market": []}


class RecordingIntegrated:
    def __init__(self):
        self.production = RecordingProduction()
        self.diagnostics = {}

    def transform(self, _obs, _cfg, selected, fallback_action=None):
        assert fallback_action is selected
        return selected


class DeadlineObservationContractTests(unittest.TestCase):
    def test_direct_fallbacks_reject_coercible_or_out_of_range_players(self):
        for bad in (True, False, "0", 0.0, -1, 2, None):
            with self.subTest(player=bad):
                obs = observation(player=bad)
                with self.assertRaises(ValueError):
                    DEADLINE.legal_pass(obs)
                with self.assertRaises(ValueError):
                    DEADLINE.terminal_liquidation_fallback(obs, {})

    def test_legal_pass_uses_exact_second_player_farm(self):
        action = DEADLINE.legal_pass(observation(player=1))
        self.assertEqual(action["farmer"], ["PASS"])
        self.assertEqual(action["hands"], [["PASS"], ["PASS"]])
        self.assertEqual(action["market"], [])

    def test_agent_rejects_player_alias_before_production(self):
        for bad in (True, False, "0", 0.0, -1, 2, None):
            with self.subTest(player=bad):
                integrated = RecordingIntegrated()
                agent = DEADLINE.DeadlineFallbackAgent(integrated)
                with self.assertRaises(ValueError):
                    agent.act(observation(player=bad, step=0), {})
                self.assertEqual(integrated.production.calls, 0)
                self.assertEqual(agent.diagnostics, {})

    def test_agent_rejects_step_alias_before_production_or_terminal_routing(self):
        for bad in (True, "718", 718.0, -1, None):
            with self.subTest(step=bad):
                integrated = RecordingIntegrated()
                agent = DEADLINE.DeadlineFallbackAgent(integrated)
                with self.assertRaises(ValueError):
                    agent.act(observation(player=0, step=bad), {"episodeSteps": 720})
                self.assertEqual(integrated.production.calls, 0)
                self.assertEqual(agent.diagnostics, {})

    def test_exact_day_hour_fallback_canonicalizes_only_when_step_is_absent(self):
        integrated = RecordingIntegrated()
        agent = DEADLINE.DeadlineFallbackAgent(integrated)
        obs = observation(player=0, step=...)
        obs.update({"day": 29, "hour": 22})
        output = agent.act(obs, {"turnsPerDay": 24, "episodeSteps": 720})
        self.assertEqual(output, {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertEqual(integrated.production.calls, 1)
        self.assertEqual(integrated.production.seen["step"], 718)

    def test_day_hour_aliases_fail_before_production_when_step_is_absent(self):
        cases = ((True, 22), (29, True), ("29", 22), (29, "22"), (-1, 22), (29, -1))
        for day, hour in cases:
            with self.subTest(day=day, hour=hour):
                integrated = RecordingIntegrated()
                agent = DEADLINE.DeadlineFallbackAgent(integrated)
                obs = observation(player=0, step=...)
                obs.update({"day": day, "hour": hour})
                with self.assertRaises(ValueError):
                    agent.act(obs, {"turnsPerDay": 24, "episodeSteps": 720})
                self.assertEqual(integrated.production.calls, 0)
                self.assertEqual(agent.diagnostics, {})

    def test_day_hour_clock_rejects_noncanonical_calendar_before_production(self):
        for turns in (True, 24.0, "24", 0, -1, None):
            with self.subTest(turnsPerDay=turns):
                integrated = RecordingIntegrated()
                agent = DEADLINE.DeadlineFallbackAgent(integrated)
                obs = observation(player=0, step=...)
                obs.update({"day": 29, "hour": 22})
                with self.assertRaises(ValueError):
                    agent.act(obs, {"turnsPerDay": turns, "episodeSteps": 720})
                self.assertEqual(integrated.production.calls, 0)
                self.assertEqual(agent.diagnostics, {})

        for hour in (24, 25, 718):
            with self.subTest(hour=hour):
                integrated = RecordingIntegrated()
                agent = DEADLINE.DeadlineFallbackAgent(integrated)
                obs = observation(player=0, step=...)
                obs.update({"day": 29, "hour": hour})
                with self.assertRaises(ValueError):
                    agent.act(obs, {"turnsPerDay": 24, "episodeSteps": 720})
                self.assertEqual(integrated.production.calls, 0)
                self.assertEqual(agent.diagnostics, {})

    def test_explicit_step_redundant_clock_must_be_complete_exact_and_agree(self):
        bad_observations = (
            {"day": 29},
            {"hour": 22},
            {"day": True, "hour": 22},
            {"day": 29, "hour": True},
            {"day": 29, "hour": 24},
            {"day": 29, "hour": 21},
            {"day": 30, "hour": 22},
        )
        for redundant in bad_observations:
            with self.subTest(redundant=redundant):
                integrated = RecordingIntegrated()
                agent = DEADLINE.DeadlineFallbackAgent(integrated)
                obs = observation(player=0, step=718)
                obs.update(redundant)
                with self.assertRaises(ValueError):
                    agent.act(obs, {"turnsPerDay": 24, "episodeSteps": 720})
                self.assertEqual(integrated.production.calls, 0)
                self.assertEqual(agent.diagnostics, {})

        for turns in (True, 24.0, "24", 0, -1, None):
            with self.subTest(redundant_turns=turns):
                integrated = RecordingIntegrated()
                agent = DEADLINE.DeadlineFallbackAgent(integrated)
                obs = observation(player=0, step=718)
                obs.update({"day": 29, "hour": 22})
                with self.assertRaises(ValueError):
                    agent.act(obs, {"turnsPerDay": turns, "episodeSteps": 720})
                self.assertEqual(integrated.production.calls, 0)
                self.assertEqual(agent.diagnostics, {})

    def test_explicit_step_accepts_matching_redundant_clock(self):
        integrated = RecordingIntegrated()
        agent = DEADLINE.DeadlineFallbackAgent(integrated)
        obs = observation(player=0, step=718)
        obs.update({"day": 29, "hour": 22})
        output = agent.act(obs, {"turnsPerDay": 24, "episodeSteps": 720})
        self.assertEqual(output, {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertEqual(integrated.production.calls, 1)
        self.assertEqual(integrated.production.seen["step"], 718)


if __name__ == "__main__":
    unittest.main(verbosity=2)
