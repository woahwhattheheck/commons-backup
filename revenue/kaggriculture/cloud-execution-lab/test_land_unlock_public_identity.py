# SPDX-License-Identifier: Apache-2.0
"""Exact public identity and state-atomicity for the P02 live overlay."""
from copy import deepcopy
import unittest

from land_unlock_runtime import LandUnlockOverlay
from land_unlock_runtime_support import _step, _unlocked_count


def observation(**updates):
    farm = {
        "unlocked_quadrants": ["NW"],
        "money": 5000,
        "farmer": [4, 4],
        "hands": [],
        "tiles": [[None] * 10 for _ in range(10)],
    }
    value = {
        "step": 25,
        "player": 0,
        "farms": [farm, deepcopy(farm)],
        "private": {"seeds": {}, "inventories": [{}], "shed": {}},
    }
    value.update(updates)
    return value


class LandUnlockPublicIdentityTests(unittest.TestCase):
    def test_canonical_step_and_day_hour_forms(self):
        self.assertEqual(_step(observation(step=25), {}), 25)
        redundant = observation(step=25, day=1, hour=1)
        self.assertEqual(_step(redundant, {"turnsPerDay": 24}), 25)
        fallback = observation(day=1, hour=1)
        del fallback["step"]
        self.assertEqual(_step(fallback, {"turnsPerDay": 24}), 25)
        self.assertEqual(_unlocked_count(observation(player=1)), 1)

    def test_step_aliases_present_null_and_negative_fail_closed(self):
        for value in (True, "25", 25.0, None, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _step(observation(step=value), {})

    def test_seat_aliases_fail_before_farm_indexing(self):
        for value in (False, True, "0", 0.0, -1, 2, None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _step(observation(player=value), {})
                with self.assertRaises(ValueError):
                    _unlocked_count(observation(player=value))

    def test_redundant_clock_must_be_paired_exact_and_in_range(self):
        cases = [
            (observation(step=25, day=1), {"turnsPerDay": 24}),
            (observation(step=25, hour=1), {"turnsPerDay": 24}),
            (observation(step=25, day=1, hour=2), {"turnsPerDay": 24}),
            (observation(step=25, day=True, hour=1), {"turnsPerDay": 24}),
            (observation(step=25, day=1, hour=24), {"turnsPerDay": 24}),
            (observation(step=25, day=1, hour=1), {"turnsPerDay": 24.0}),
        ]
        for obs, cfg in cases:
            with self.subTest(obs=obs, cfg=cfg):
                with self.assertRaises(ValueError):
                    _step(obs, cfg)

    def test_malformed_identity_cannot_mutate_existing_overlay_state(self):
        overlay = LandUnlockOverlay(analyzer=lambda *args, **kwargs: self.fail("analyzer called"),
                                    mechanics=object(), decision_steps=())
        pending = {"phase": "await_fill", "route_id": "MAIN", "emitted_step": 49}
        events = [{"step": 49, "kind": "sentinel"}]
        overlay.pending = deepcopy(pending)
        overlay.last_step = 50
        overlay.events = deepcopy(events)

        bad = observation(step=49, player="0")
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        with self.assertRaises(ValueError):
            overlay.apply(object(), bad, {}, action)

        self.assertEqual(overlay.pending, pending)
        self.assertEqual(overlay.last_step, 50)
        self.assertEqual(overlay.events, events)

    def test_malformed_clock_cannot_trigger_backward_reset(self):
        overlay = LandUnlockOverlay(analyzer=lambda *args, **kwargs: self.fail("analyzer called"),
                                    mechanics=object(), decision_steps=())
        pending = {"phase": "await_fill", "route_id": "MAIN", "emitted_step": 49}
        events = [{"step": 49, "kind": "sentinel"}]
        overlay.pending = deepcopy(pending)
        overlay.last_step = 50
        overlay.events = deepcopy(events)

        bad = observation(step="0", player=0)
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        with self.assertRaises(ValueError):
            overlay.apply(object(), bad, {}, action)

        self.assertEqual(overlay.pending, pending)
        self.assertEqual(overlay.last_step, 50)
        self.assertEqual(overlay.events, events)


if __name__ == "__main__":
    unittest.main()
