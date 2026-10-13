from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
CAP_SPEC = importlib.util.spec_from_file_location(
    "crop_service_capacity", HERE / "crop_service_capacity.py"
)
cap = importlib.util.module_from_spec(CAP_SPEC)
assert CAP_SPEC.loader is not None
sys.modules[CAP_SPEC.name] = cap
CAP_SPEC.loader.exec_module(cap)

SPEC = importlib.util.spec_from_file_location(
    "plantguard_service", HERE / "plantguard_service.py"
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def obs(*, hour=0, step=None, hands=0, empty=25):
    side = 5
    cells = [None] * empty + ["LOCKED"] * (side * side - empty)
    rows = [cells[i:i + side] for i in range(0, len(cells), side)]
    farm = {
        "farmer": [2, 2],
        "hands": [[2, 2] for _ in range(hands)],
        "tiles": rows,
    }
    if step is None:
        step = hour
    return {"player": 0, "hour": hour, "step": step, "farms": [farm]}


def r(hour, order, op, site=None):
    out = {"hour": hour, "order": order, "op": op}
    if site is not None:
        out["site"] = list(site)
    return out


class PlantguardServiceTests(unittest.TestCase):
    def test_same_callback_later_actor_order_can_water_new_plant(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=23, hands=1),
            [(1, 1)],
            [r(23, 0, "PLANT", (1, 1)), r(23, 1, "WATER", (1, 1))],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "ESTABLISHMENT_SERVICE_PROVED")
        self.assertEqual(got["proved_pair_count"], 1)
        self.assertEqual(got["pairs"][0]["plant_order"], 0)
        self.assertEqual(got["pairs"][0]["water_order"], 1)

    def test_last_hour_one_actor_is_rejected_by_cropscale_before_pair_claim(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=23, hands=0),
            [(1, 1)],
            [r(23, 0, "PLANT", (1, 1))],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "IMPOSSIBLE_ACTION_BUDGET")
        self.assertEqual(got["capacity"]["ceiling"], 0)

    def test_water_before_plant_does_not_discharge_establishment(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=22, hands=1),
            [(1, 1)],
            [r(22, 0, "WATER", (1, 1)), r(22, 1, "PLANT", (1, 1))],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "SERVICE_SEQUENCE_UNPROVED")
        self.assertEqual(got["failures"][0]["reason"], "missing_same_eod_water")

    def test_water_on_wrong_site_does_not_count(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=22, hands=1),
            [(1, 1)],
            [r(22, 0, "PLANT", (1, 1)), r(22, 1, "WATER", (1, 2))],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "SERVICE_SEQUENCE_UNPROVED")
        self.assertEqual(got["failures"][0]["reason"], "missing_same_eod_water")

    def test_later_callback_same_day_is_valid(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=21, hands=0),
            [(1, 1)],
            [r(21, 0, "PLANT", (1, 1)), r(22, 0, "WATER", (1, 1))],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "ESTABLISHMENT_SERVICE_PROVED")
        self.assertEqual(got["pairs"][0]["water_hour"], 22)

    def test_fertilize_between_plant_and_water_is_conservatively_allowed(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=21, hands=1),
            [(1, 1)],
            [
                r(21, 0, "PLANT", (1, 1)),
                r(21, 1, "FERTILIZE", (1, 1)),
                r(22, 0, "WATER", (1, 1)),
            ],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "ESTABLISHMENT_SERVICE_PROVED")

    def test_other_same_site_action_between_plant_and_water_invalidates(self):
        for op in ("DIG", "HARVEST", "PLANT", "BUILD_COOP"):
            with self.subTest(op=op):
                got = mod.prove_same_eod_establishment(
                    obs(hour=21, hands=1),
                    [(1, 1)],
                    [
                        r(21, 0, "PLANT", (1, 1)),
                        r(21, 1, op, (1, 1)),
                        r(22, 0, "WATER", (1, 1)),
                    ],
                    no_future_hires=True,
                )
                self.assertEqual(got["verdict"], "SERVICE_SEQUENCE_UNPROVED")
                self.assertEqual(
                    got["failures"][0]["reason"],
                    "site_action_between_plant_and_water",
                )

    def test_same_callback_action_after_water_invalidates(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=23, hands=2),
            [(1, 1)],
            [
                r(23, 0, "PLANT", (1, 1)),
                r(23, 1, "WATER", (1, 1)),
                r(23, 2, "DIG", (1, 1)),
            ],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "SERVICE_SEQUENCE_UNPROVED")
        self.assertEqual(got["failures"][0]["reason"], "site_action_after_water_before_eod")
        self.assertEqual(got["failures"][0]["op"], "DIG")

    def test_later_callback_action_after_water_invalidates(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=21, hands=0),
            [(1, 1)],
            [
                r(21, 0, "PLANT", (1, 1)),
                r(22, 0, "WATER", (1, 1)),
                r(23, 0, "HARVEST", (1, 1)),
            ],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "SERVICE_SEQUENCE_UNPROVED")
        self.assertEqual(got["failures"][0]["reason"], "site_action_after_water_before_eod")
        self.assertEqual(got["failures"][0]["op"], "HARVEST")

    def test_unrelated_site_after_water_does_not_invalidate(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=22, hands=1),
            [(1, 1)],
            [
                r(22, 0, "PLANT", (1, 1)),
                r(22, 1, "WATER", (1, 1)),
                r(23, 0, "DIG", (1, 2)),
            ],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "ESTABLISHMENT_SERVICE_PROVED")

    def test_terminal_partial_day_cannot_claim_phantom_hour23_water(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=22, step=718, hands=1),
            [(1, 1)],
            [r(22, 0, "PLANT", (1, 1)), r(23, 0, "WATER", (1, 1))],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "SERVICE_SEQUENCE_UNPROVED")
        self.assertEqual(got["failures"], [{"reason": "eod_not_reachable_before_terminal"}])

    def test_last_real_eod_callback_can_still_certify_service(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=23, step=695, hands=1),
            [(1, 1)],
            [r(23, 0, "PLANT", (1, 1)), r(23, 1, "WATER", (1, 1))],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "ESTABLISHMENT_SERVICE_PROVED")

    def test_step_hour_mismatch_is_rejected(self):
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=22, step=717, hands=1),
                [(1, 1)],
                [r(22, 0, "PLANT", (1, 1)), r(22, 1, "WATER", (1, 1))],
                no_future_hires=True,
            )

    def test_step_after_final_executable_callback_is_rejected(self):
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=23, step=719, hands=1),
                [(1, 1)],
                [r(23, 0, "PLANT", (1, 1)), r(23, 1, "WATER", (1, 1))],
                no_future_hires=True,
            )

    def test_multiple_sites_all_need_independent_pairs(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=20, hands=1),
            [(1, 1), (1, 2)],
            [
                r(20, 0, "PLANT", (1, 1)),
                r(20, 1, "PLANT", (1, 2)),
                r(21, 0, "WATER", (1, 1)),
            ],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "SERVICE_SEQUENCE_UNPROVED")
        self.assertEqual(got["proved_pair_count"], 1)
        self.assertEqual(got["failures"], [{"site": [1, 2], "reason": "missing_same_eod_water"}])

    def test_two_sites_can_be_proved(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=20, hands=1),
            [(1, 1), (1, 2)],
            [
                r(20, 0, "PLANT", (1, 1)),
                r(20, 1, "PLANT", (1, 2)),
                r(21, 0, "WATER", (1, 1)),
                r(21, 1, "WATER", (1, 2)),
            ],
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "ESTABLISHMENT_SERVICE_PROVED")
        self.assertEqual(got["proved_pair_count"], 2)

    def test_empty_proposal_is_not_promoted(self):
        got = mod.prove_same_eod_establishment(obs(), [], [])
        self.assertEqual(got["verdict"], "NO_PROPOSAL")
        self.assertFalse(got["decision_authority"])

    def test_duplicate_proposed_site_rejected(self):
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(obs(), [(1, 1), (1, 1)], [])

    def test_proposed_site_outside_board_rejected(self):
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(obs(), [(5, 0)], [])

    def test_rows_must_be_strict_total_execution_order(self):
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=20),
                [(1, 1)],
                [r(21, 0, "PLANT", (1, 1)), r(20, 0, "WATER", (1, 1))],
            )
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=20),
                [(1, 1)],
                [r(20, 0, "PLANT", (1, 1)), r(20, 0, "WATER", (1, 1))],
            )

    def test_rows_cannot_escape_current_day_suffix(self):
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=20), [(1, 1)], [r(19, 0, "PLANT", (1, 1))]
            )
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=20), [(1, 1)], [r(24, 0, "PLANT", (1, 1))]
            )

    def test_custom_turns_per_day_controls_same_eod_boundary(self):
        cfg = {"turnsPerDay": 8, "maxMarketOrdersPerTurn": 10}
        got = mod.prove_same_eod_establishment(
            obs(hour=6, hands=1),
            [(1, 1)],
            [r(6, 0, "PLANT", (1, 1)), r(7, 0, "WATER", (1, 1))],
            cfg,
            no_future_hires=True,
        )
        self.assertEqual(got["verdict"], "ESTABLISHMENT_SERVICE_PROVED")
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=6, hands=1),
                [(1, 1)],
                [r(6, 0, "PLANT", (1, 1)), r(8, 0, "WATER", (1, 1))],
                cfg,
                no_future_hires=True,
            )

    def test_non_authority_boundaries_are_explicit(self):
        got = mod.prove_same_eod_establishment(
            obs(hour=22, hands=1),
            [(1, 1)],
            [r(22, 0, "PLANT", (1, 1)), r(22, 1, "WATER", (1, 1))],
            no_future_hires=True,
        )
        self.assertTrue(got["research_only"])
        self.assertFalse(got["decision_authority"])
        self.assertFalse(got["runtime_mutation_authority"])
        self.assertFalse(got["movement_certified"])
        self.assertFalse(got["seed_certified"])
        self.assertFalse(got["cash_certified"])
        self.assertFalse(got["tile_legality_certified"])
        self.assertFalse(got["future_service_certified"])
        self.assertFalse(got["economics_certified"])
        self.assertNotIn("allow", got)
        self.assertNotIn("choose", got)

    def test_inputs_are_not_mutated(self):
        o = obs(hour=20, hands=1)
        sites = [[1, 1]]
        rows = [r(20, 0, "PLANT", (1, 1)), r(20, 1, "WATER", (1, 1))]
        before = copy.deepcopy((o, sites, rows))
        mod.prove_same_eod_establishment(
            o, sites, rows, no_future_hires=True
        )
        self.assertEqual((o, sites, rows), before)

    def test_bool_poison_rejected(self):
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(obs(), [(True, 1)], [])
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=0), [(1, 1)], [r(True, 0, "PLANT", (1, 1))]
            )
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(obs(), [(1, 1)], [], no_future_hires=1)
        with self.assertRaises(mod.PlantguardEvidenceError):
            mod.prove_same_eod_establishment(
                obs(hour=0, hands=1),
                [(1, 1)],
                [r(0, 0, "PLANT", (1, 1)), r(0, 1, "WATER", (1, 1))],
                {"episodeSteps": True},
                no_future_hires=True,
            )


if __name__ == "__main__":
    unittest.main()
