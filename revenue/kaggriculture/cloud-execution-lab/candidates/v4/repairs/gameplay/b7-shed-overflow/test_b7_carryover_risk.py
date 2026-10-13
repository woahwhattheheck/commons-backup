#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Negative evidence: the immediate EOD gate is necessary, not sufficient.

Saved inventory from an earlier turn can still crowd out later cargo at EOD.
This test intentionally proves that residual risk rather than claiming safety.
"""
import copy
import json
import unittest

import test_b7_full_turn_eod as evidence

WITNESSES = []


class CarryoverRiskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence.FullTurnB7Tests.setUpClass()
        cls.engine = evidence.FullTurnB7Tests.engine
        cls.helper = evidence.FullTurnB7Tests.repaired

    def test_prior_turn_retention_still_needs_rollout_gate(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                initial, env = evidence.fixture(self.engine, seat=seat, step=262)
                parent, guarded = copy.deepcopy(initial), copy.deepcopy(initial)
                guarded[seat].action = self.helper.transform(
                    evidence.observation(guarded, seat), guarded[seat].action,
                    vars(env.configuration), enabled=True)
                self.assertEqual(guarded[seat].action["farmer"], ["PASS"])
                for state in (parent, guarded):
                    evidence.interpret(self.engine, state, copy.deepcopy(env))
                    for agent in state:
                        agent.observation.step = 263
                        agent.action = evidence.pass_action(len(agent.observation.farms[agent.observation.player]["hands"]))
                    state[seat].action["market"] = [["SELL", "CARROT", 10]]
                before = guarded[seat].action
                guarded[seat].action = self.helper.transform(
                    evidence.observation(guarded, seat), before,
                    vars(env.configuration), enabled=True)
                self.assertIs(guarded[seat].action, before)  # EOD gate really fires.
                for state in (parent, guarded):
                    evidence.interpret(self.engine, state, copy.deepcopy(env))
                    for agent in state:
                        agent.observation.step = 264
                        agent.action = evidence.pass_action()
                    state[seat].action["market"] = [["SELL", "WHEAT", 10], ["SELL", "MILK", 10]]
                    evidence.interpret(self.engine, state, copy.deepcopy(env))
                cash = [state[seat].observation.farms[seat]["money"] for state in (parent, guarded)]
                self.assertEqual(cash, [4834.0, 3565.0])
                WITNESSES.append({"seat": seat, "parent_cash": cash[0],
                                  "repaired_cash": cash[1], "delta": cash[1] - cash[0],
                                  "retention_step": 262, "eod_veto_step": 263})


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CarryoverRiskTests))
    print(json.dumps({"status": "RESIDUAL_RISK_CONFIRMED" if result.wasSuccessful() else "FAIL",
                      "tests": result.testsRun, "witnesses": WITNESSES,
                      "activation_authorized": False,
                      "scope": "constructed three-turn counterexample; not field frequency"},
                     indent=2, sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
