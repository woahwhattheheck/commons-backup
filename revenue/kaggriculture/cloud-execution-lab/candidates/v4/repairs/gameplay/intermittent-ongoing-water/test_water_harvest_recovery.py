import copy
import unittest

import water_harvest_recovery as R

CFG = {"boardSize": 10, "turnsPerDay": 24, "episodeSteps": 720}


def plant(*, streak=0, watered=False, units=2, fertilized_until=-1, planted_day=0):
    return {
        "kind": "PLANT",
        "crop": "TOMATO",
        "planted_day": planted_day,
        "consecutive_unwatered": streak,
        "watered_today": watered,
        "yield_units": units,
        "fertilized_until_day": fertilized_until,
    }


def observation(*, step=240, tile=None, hands=None, positions=None):
    tiles0 = [[None for _ in range(10)] for _ in range(10)]
    tiles1 = [[None for _ in range(10)] for _ in range(10)]
    tiles0[1][1] = plant() if tile is None else tile
    hand_positions = [] if positions is None else positions
    farm0 = {
        "tiles": tiles0,
        "farmer": [1, 1],
        "hands": hand_positions,
    }
    farm1 = {"tiles": tiles1, "farmer": [0, 0], "hands": []}
    return {"step": step, "player": 0, "farms": [farm0, farm1]}


def action(farmer=None, hands=None):
    return {
        "farmer": ["WATER"] if farmer is None else farmer,
        "hands": [] if hands is None else hands,
        "market": [],
    }


class WaterHarvestRecoveryTests(unittest.TestCase):
    def pair(self):
        now = observation(step=240, tile=plant(streak=0, units=2))
        future = observation(step=264, tile=plant(streak=1, units=3))
        return now, action(), future, action()

    def test_productive_pair_is_certified_and_rewrites_to_harvest(self):
        now, current, future, recovery = self.pair()
        certs = R.plan_water_harvest_recovery(current, now, recovery, future, CFG)
        self.assertEqual(len(certs), 1)
        cert = certs[0]
        self.assertEqual(cert["site"], [1, 1])
        self.assertEqual(cert["stored_yield_units"], 2)
        self.assertEqual(cert["replacement_row"], ["HARVEST"])
        self.assertEqual(cert["recovery_op"], "WATER")
        self.assertEqual(cert["same_callback_semantic_water_count"], 1)
        self.assertEqual(cert["recovery_day"], cert["current_day"] + 1)
        self.assertTrue(cert["same_callback_destructive_dig_absent"])
        candidate = R.apply_water_harvest_recovery(
            current, now, recovery, future, CFG, enabled=True)
        self.assertEqual(candidate["farmer"], ["HARVEST"])
        self.assertEqual(recovery["farmer"], ["WATER"])

    def test_disabled_mode_is_exact_identity(self):
        now, current, future, recovery = self.pair()
        self.assertIs(
            R.apply_water_harvest_recovery(current, now, recovery, future, CFG),
            current,
        )

    def test_zero_stored_yield_is_not_productive(self):
        now, current, future, recovery = self.pair()
        now["farms"][0]["tiles"][1][1]["yield_units"] = 0
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_earlier_same_site_harvest_blocks_later_replacement(self):
        now = observation(step=240, tile=plant(streak=0, units=2), positions=[[1, 1]])
        future = observation(step=264, tile=plant(streak=1, units=3), positions=[[1, 1]])
        current = action(["HARVEST", "extra"], [["WATER"]])
        recovery = action(["WATER"], [["PASS"]])
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])
        self.assertIs(
            R.apply_water_harvest_recovery(
                current, now, recovery, future, CFG, enabled=True),
            current,
        )

    def test_earlier_same_site_dig_blocks_later_replacement(self):
        now = observation(step=240, tile=plant(streak=0, units=2), positions=[[1, 1]])
        future = observation(step=264, tile=plant(streak=1, units=3), positions=[[1, 1]])
        current = action(["DIG", "extra"], [["WATER"]])
        recovery = action(["WATER"], [["PASS"]])
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_later_same_site_harvest_does_not_block_actor_zero_replacement(self):
        now = observation(step=240, tile=plant(streak=0, units=2), positions=[[1, 1]])
        future = observation(step=264, tile=plant(streak=1, units=3), positions=[[1, 1]])
        current = action(["WATER"], [["HARVEST", "extra"]])
        recovery = action(["WATER"], [["PASS"]])
        certs = R.plan_water_harvest_recovery(current, now, recovery, future, CFG)
        self.assertEqual(len(certs), 1)
        self.assertEqual(certs[0]["current_actor"], 0)
        candidate = R.apply_water_harvest_recovery(
            current, now, recovery, future, CFG, enabled=True)
        self.assertEqual(candidate["farmer"], ["HARVEST"])
        self.assertEqual(candidate["hands"], [["HARVEST", "extra"]])

    def test_missing_recovery_water_fails_closed(self):
        now, current, future, _ = self.pair()
        recovery = action(["PASS"])
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])
        self.assertIs(
            R.apply_water_harvest_recovery(current, now, recovery, future, CFG, enabled=True),
            current,
        )

    def test_recovery_must_be_next_day(self):
        now, current, future, recovery = self.pair()
        future["step"] = 263
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_step_719_is_not_executable_recovery_evidence(self):
        self.assertEqual(R._plain_step({"step": 718}), 718)
        self.assertIsNone(R._plain_step({"step": 719}))

    def test_future_plant_must_show_expected_one_day_streak(self):
        now, current, future, recovery = self.pair()
        future["farms"][0]["tiles"][1][1]["consecutive_unwatered"] = 0
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])
        future["farms"][0]["tiles"][1][1] = {"kind": "WEED"}
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_ambiguous_duplicate_recovery_water_is_rejected(self):
        now, current, future, _ = self.pair()
        future["farms"][0]["hands"] = [[1, 1]]
        recovery = action(["WATER"], [["WATER"]])
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_semantic_water_extra_before_exact_water_is_rejected(self):
        now, current, future, _ = self.pair()
        future["farms"][0]["hands"] = [[1, 1]]
        recovery = action(["WATER", "extra"], [["WATER"]])
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_exact_water_before_semantic_water_extra_is_rejected(self):
        now, current, future, _ = self.pair()
        future["farms"][0]["hands"] = [[1, 1]]
        recovery = action(["WATER"], [["WATER", "extra"]])
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_single_semantic_water_extra_is_accepted(self):
        now, current, future, _ = self.pair()
        recovery = action(["WATER", "extra"])
        certs = R.plan_water_harvest_recovery(current, now, recovery, future, CFG)
        self.assertEqual(len(certs), 1)
        self.assertEqual(certs[0]["recovery_actor"], 0)
        self.assertEqual(certs[0]["recovery_op"], "WATER")

    def test_same_site_dig_before_water_is_rejected(self):
        now, current, future, _ = self.pair()
        future["farms"][0]["hands"] = [[1, 1]]
        recovery = action(["DIG"], [["WATER"]])
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_same_site_dig_after_water_is_rejected(self):
        now, current, future, _ = self.pair()
        future["farms"][0]["hands"] = [[1, 1]]
        recovery = action(["WATER"], [["DIG"]])
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_benign_same_site_harvest_then_water_is_allowed(self):
        now, current, future, _ = self.pair()
        future["farms"][0]["hands"] = [[1, 1]]
        recovery = action(["HARVEST"], [["WATER"]])
        certs = R.plan_water_harvest_recovery(current, now, recovery, future, CFG)
        self.assertEqual(len(certs), 1)
        self.assertEqual(certs[0]["recovery_actor"], 1)

    def test_hydra_fertilizer_bonus_block_is_inherited(self):
        now, current, future, recovery = self.pair()
        # Day 10 is a TOMATO production day for this fixture. Active fertilizer
        # plus unsaturated yield makes skipping WATER source-unsafe.
        now["farms"][0]["tiles"][1][1]["fertilized_until_day"] = 10
        self.assertEqual(R.plan_water_harvest_recovery(current, now, recovery, future, CFG), [])

    def test_inputs_are_not_mutated(self):
        now, current, future, recovery = self.pair()
        before = copy.deepcopy((now, current, future, recovery))
        R.plan_water_harvest_recovery(current, now, recovery, future, CFG)
        R.apply_water_harvest_recovery(current, now, recovery, future, CFG, enabled=True)
        self.assertEqual((now, current, future, recovery), before)


if __name__ == "__main__":
    unittest.main()
