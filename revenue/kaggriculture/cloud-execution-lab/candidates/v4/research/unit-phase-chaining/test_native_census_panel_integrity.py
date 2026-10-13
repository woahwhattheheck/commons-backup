#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import native_census as census


def source():
    return {
        "artifact_id": census.ARTIFACT_ID,
        "inner_tar_sha256": census.INNER_TAR_SHA256,
        "engine_git_blob": census.ENGINE_GIT_BLOB,
        "main_git_blob": census.MAIN_GIT_BLOB,
        "config_git_blob": census.CONFIG_GIT_BLOB,
        "admission_git_blob": census.ADMISSION_GIT_BLOB,
    }


def cell(seed, seat):
    return {
        "schema": census.CELL_SCHEMA,
        "source": source(),
        "seed": seed,
        "seat": seat,
        "callbacks": census.EXPECTED_CALLBACKS_PER_CELL,
        "colocated_callbacks": 1,
        "colocated_groups": 1,
        "realized_chains": {key: 0 for key in census.CHAIN_KEYS},
        "admission": {"eligible_groups": 0, "changed_groups": 0},
        "examples": [],
        "scores": [0.0, 0.0],
    }


def exact_panel():
    return [cell(seed, seat) for seed in census.PANEL_SEEDS for seat in census.PANEL_SEATS]


def aggregate(cells):
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for index, payload in enumerate(cells):
            path = Path(tmp) / f"cell-{index}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            paths.append(path)
        return census.aggregate_cells(paths)


class NativeCensusPanelIntegrityTests(unittest.TestCase):
    def test_exact_panel_is_order_independent_and_cold(self):
        panel = aggregate(list(reversed(exact_panel())))
        self.assertEqual("COLD_CURRENT_NATIVE_B567", panel["disposition"])
        self.assertEqual(16, panel["panel"]["cells"])
        self.assertEqual(16 * census.EXPECTED_CALLBACKS_PER_CELL, panel["panel"]["callbacks"])
        self.assertEqual(list(census.PANEL_SEEDS), panel["panel"]["seeds"])
        self.assertEqual(list(census.PANEL_SEATS), panel["panel"]["seats"])
        self.assertEqual(source(), panel["source"])

    def test_single_cold_cell_cannot_mint_panel_disposition(self):
        with self.assertRaisesRegex(ValueError, "exactly 16"):
            aggregate([cell(census.PANEL_SEEDS[0], 0)])

    def test_duplicate_coordinate_is_rejected(self):
        cells = exact_panel()
        cells[-1] = deepcopy(cells[0])
        with self.assertRaisesRegex(ValueError, "duplicate seed/seat"):
            aggregate(cells)

    def test_unexpected_seed_is_rejected(self):
        cells = exact_panel()
        cells[-1]["seed"] = 999999999
        with self.assertRaisesRegex(ValueError, "unexpected seed/seat"):
            aggregate(cells)

    def test_missing_seat_is_rejected(self):
        cells = exact_panel()
        del cells[-1]["seat"]
        with self.assertRaisesRegex(ValueError, "exact integers"):
            aggregate(cells)

    def test_bool_seat_is_rejected_before_python_equality_can_alias_one(self):
        cells = exact_panel()
        cells[-1]["seat"] = True
        with self.assertRaisesRegex(ValueError, "exact integers"):
            aggregate(cells)

    def test_source_identity_drift_is_rejected(self):
        cells = exact_panel()
        cells[-1]["source"]["artifact_id"] += 1
        with self.assertRaisesRegex(ValueError, "source identity mismatch"):
            aggregate(cells)

    def test_schema_drift_is_rejected(self):
        cells = exact_panel()
        cells[-1]["schema"] = "titan-v4-unit-phase-chaining-native-cell/v0"
        with self.assertRaisesRegex(ValueError, "schema mismatch"):
            aggregate(cells)

    def test_missing_chain_key_cannot_alias_zero(self):
        cells = exact_panel()
        del cells[-1]["realized_chains"][census.CHAIN_KEYS[-1]]
        with self.assertRaisesRegex(ValueError, "realized_chains shape mismatch"):
            aggregate(cells)

    def test_type_poisoned_counter_is_rejected(self):
        cells = exact_panel()
        cells[-1]["admission"]["changed_groups"] = False
        with self.assertRaisesRegex(ValueError, "non-negative exact integer"):
            aggregate(cells)

    def test_partial_callback_cell_is_rejected(self):
        cells = exact_panel()
        cells[-1]["callbacks"] = census.EXPECTED_CALLBACKS_PER_CELL - 1
        with self.assertRaisesRegex(ValueError, "callbacks must equal 719"):
            aggregate(cells)

    def test_impossible_colocation_count_is_rejected(self):
        cells = exact_panel()
        cells[-1]["colocated_callbacks"] = cells[-1]["callbacks"] + 1
        with self.assertRaisesRegex(ValueError, "exceeds callbacks"):
            aggregate(cells)

    def test_colocated_callbacks_cannot_exceed_colocated_groups(self):
        cells = exact_panel()
        cells[-1]["colocated_callbacks"] = 2
        cells[-1]["colocated_groups"] = 1
        with self.assertRaisesRegex(ValueError, "colocated_callbacks exceeds colocated_groups"):
            aggregate(cells)

    def test_nonfinite_scores_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                cells = exact_panel()
                cells[-1]["scores"][0] = value
                with self.assertRaisesRegex(ValueError, "finite exact numeric values"):
                    aggregate(cells)

    def test_changed_groups_cannot_exceed_eligible_groups(self):
        cells = exact_panel()
        cells[-1]["colocated_groups"] = 2
        cells[-1]["admission"] = {"eligible_groups": 1, "changed_groups": 2}
        with self.assertRaisesRegex(ValueError, "changed_groups exceeds eligible_groups"):
            aggregate(cells)

    def test_eligible_groups_cannot_exceed_colocated_groups(self):
        cells = exact_panel()
        cells[-1]["admission"] = {"eligible_groups": 2, "changed_groups": 1}
        with self.assertRaisesRegex(ValueError, "eligible_groups exceeds colocated_groups"):
            aggregate(cells)

    def test_valid_engagement_still_produces_engaged(self):
        cells = exact_panel()
        cells[0]["admission"]["eligible_groups"] = 1
        panel = aggregate(cells)
        self.assertEqual("ENGAGED", panel["disposition"])
        self.assertEqual(1, panel["admission"]["eligible_groups"])


if __name__ == "__main__":
    unittest.main()
