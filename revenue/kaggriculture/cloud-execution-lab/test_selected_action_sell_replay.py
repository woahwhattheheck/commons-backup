"""Replay contracts for the selected-action seller's public rival history."""
from __future__ import annotations

import copy
import unittest

from selected_action_sell import SelectedActionSell


def observation(step, rival_yield, player=0):
    own = {"tiles": [[None]]}
    rival = {"tiles": [[{"kind": "ANIMAL", "animal": "COW", "yield_units": rival_yield}]]}
    farms = [own, rival] if player == 0 else [rival, own]
    return {"step": step, "player": player, "farms": farms}


class SelectedActionSellReplayTests(unittest.TestCase):
    def test_same_step_replay_preserves_history_and_replaces_snapshot(self):
        seller = SelectedActionSell()
        seller._observe(observation(10, 5), 10)
        at_11 = observation(11, 2)
        seller._observe(at_11, 11)
        self.assertEqual(seller.observed_harvests, {"MILK": [(11, 3)]})
        pressure = seller._rival(at_11, "MILK", 11)

        seller._observe(copy.deepcopy(at_11), 11)
        self.assertEqual(seller.observed_harvests, {"MILK": [(11, 3)]})
        self.assertEqual(seller._rival(at_11, "MILK", 11), pressure)

        revised = observation(11, 1)
        seller._observe(revised, 11)
        self.assertEqual(seller.observed_harvests, {"MILK": [(11, 3)]},
                         "same-step replacement is not a second harvest")
        self.assertEqual(seller.previous[2][0][0]["yield_units"], 1,
                         "the newest same-step public snapshot becomes the forward baseline")

        at_12 = observation(12, 0)
        seller._observe(at_12, 12)
        self.assertEqual(seller.observed_harvests, {"MILK": [(11, 3), (12, 1)]},
                         "forward observation must compare against the replaced step snapshot")

    def test_backward_step_and_player_transition_reset_history(self):
        seller = SelectedActionSell()
        seller._observe(observation(10, 5), 10)
        seller._observe(observation(11, 2), 11)
        self.assertTrue(seller.observed_harvests)

        seller._observe(observation(9, 4), 9)
        self.assertEqual(seller.observed_harvests, {})
        self.assertEqual(seller.previous[0:2], (9, 0))

        seller.observed_harvests = {"MILK": [(9, 1)]}
        seller._observe(observation(9, 4, player=1), 9)
        self.assertEqual(seller.observed_harvests, {})
        self.assertEqual(seller.previous[0:2], (9, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
