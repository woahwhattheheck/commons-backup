#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused regression for current-native field opponent-call signatures."""
from __future__ import annotations

import unittest

import run_current_native_field as field


class _StarterEngine:
    def __init__(self) -> None:
        self.observations = []

    # Match the authenticated official engine contract exactly: starter_agent
    # accepts observation only, unlike external challengers which take config.
    def starter_agent(self, observation):
        self.observations.append(observation)
        return {"farmer": ["PASS"], "hands": [], "market": []}


class CurrentNativeOpponentContractTests(unittest.TestCase):
    def test_starter_is_adapted_to_runner_two_argument_contract(self) -> None:
        engine = _StarterEngine()
        opponent = field.load_opponent(engine, "starter", None)
        observation = {"step": 17}
        configuration = object()

        result = opponent(observation, configuration)

        self.assertEqual(engine.observations, [observation])
        self.assertEqual(result, {"farmer": ["PASS"], "hands": [], "market": []})

    def test_unknown_opponent_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported opponent"):
            field.load_opponent(_StarterEngine(), "unknown", None)


if __name__ == "__main__":
    unittest.main()
