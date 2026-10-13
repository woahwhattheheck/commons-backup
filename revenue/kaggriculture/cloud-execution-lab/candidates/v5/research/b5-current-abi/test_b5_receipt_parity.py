from __future__ import annotations

import unittest

from b5_current_safe import B5CurrentABI


class B5ReceiptParityTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        tiles = [[{} for _ in range(10)] for _ in range(10)]
        tiles[2][2] = {
            "kind": "PLANT",
            "crop": "CARROT",
            "planted_day": 0,
            "yield_units": 0,
            "fertilized_until_day": 1,
            "watered_today": False,
        }
        observation = {
            "step": 50,
            "player": 0,
            "farms": [
                {"farmer": [2, 2], "hands": [], "tiles": tiles},
                {"farmer": [0, 0], "hands": [], "tiles": []},
            ],
            "private": {"inventories": [{"FERTILIZER": 1}], "shed": {}},
        }
        selected = {"farmer": ["PASS"], "hands": [], "market": []}
        next_authored = {"farmer": ["WATER"], "hands": [], "market": []}
        return observation, selected, next_authored

    def test_jit_activation_retains_submitted_public_step(self):
        observation, selected, next_authored = self._fixture()

        result, report = B5CurrentABI(jit=True).transform(
            observation,
            selected,
            next_authored=next_authored,
            next_authored_step=51,
        )

        self.assertEqual(result["farmer"], ["FERTILIZE"])
        self.assertEqual(len(report["jit_activations"]), 1)
        activation = report["jit_activations"][0]
        self.assertEqual(activation["step"], 50)
        self.assertEqual(activation["worker"], 0)
        self.assertEqual(activation["crop"], "CARROT")
        self.assertEqual(activation["position"], [2, 2])
        self.assertEqual(activation["fertilizer_before"], 1)
        self.assertEqual(
            activation["reason"], "literal_pass_before_same_worker_yield_water"
        )

    def test_authenticated_public_step_overrides_stale_donor_receipt_step(self):
        observation, selected, next_authored = self._fixture()
        adapter = B5CurrentABI(jit=True)

        def stale_receipt(_observation, action, **_kwargs):
            return action, {
                "jit_activations": ({
                    "step": 999,
                    "worker": 0,
                    "reason": "stale-donor-step",
                },),
            }

        adapter._jit.transform = stale_receipt
        result, report = adapter.transform(
            observation,
            selected,
            next_authored=next_authored,
            next_authored_step=51,
        )

        self.assertEqual(result, selected)
        self.assertTrue(report["jit_route_bound"])
        self.assertEqual(len(report["jit_activations"]), 1)
        activation = report["jit_activations"][0]
        self.assertEqual(activation["step"], 50)
        self.assertEqual(activation["worker"], 0)
        self.assertEqual(activation["reason"], "stale-donor-step")


if __name__ == "__main__":
    unittest.main()
