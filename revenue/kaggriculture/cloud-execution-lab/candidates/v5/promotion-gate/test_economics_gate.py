#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("_economics_gate_under_test", HERE / "economics_gate.py")
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


CONTROL = "v5c:" + "1" * 64
CANDIDATE = "v5c:" + "2" * 64
ENGINE = "engine:official-pinned"
OPPONENT_PACK = "frontier:top30-union"
OPPONENTS = gate.AUTHORIZED_OPPONENT_IDS
CONTROL_ARCHIVE = "a" * 64
CANDIDATE_ARCHIVE = "b" * 64


def report(*, delta: int = 10, opponents=OPPONENTS, seeds=range(100, 104)):
    cells = []
    for opponent_id in opponents:
        for seed in seeds:
            for seat in (0, 1):
                control_own = 1000 + seed + seat
                control_rival = 900 + seed
                cells.append(
                    {
                        "opponent_id": opponent_id,
                        "seed": seed,
                        "seat": seat,
                        "control_own": control_own,
                        "control_rival": control_rival,
                        "candidate_own": control_own + delta,
                        "candidate_rival": control_rival,
                    }
                )
    return {
        "schema": gate.SCHEMA,
        "control_id": CONTROL,
        "candidate_id": CANDIDATE,
        "engine_id": ENGINE,
        "opponent_pack_id": OPPONENT_PACK,
        "control_archive_sha256": CONTROL_ARCHIVE,
        "candidate_archive_sha256": CANDIDATE_ARCHIVE,
        "cells": cells,
    }


def validate(value=None, **overrides):
    expected = dict(
        candidate_id=CANDIDATE,
        control_id=CONTROL,
        engine_id=ENGINE,
        opponent_pack_id=OPPONENT_PACK,
        control_archive_sha256=CONTROL_ARCHIVE,
        candidate_archive_sha256=CANDIDATE_ARCHIVE,
    )
    expected.update(overrides)
    return gate.validate_report(report() if value is None else value, **expected)


class EconomicsGateTests(unittest.TestCase):
    def test_positive_panel_passes_and_recomputes_raw_margins(self):
        receipt = validate(report(delta=10))
        self.assertEqual("PASS", receipt["classification"])
        self.assertTrue(receipt["promotion_ready"])
        self.assertEqual(16, receipt["cell_count"])
        self.assertEqual(4, receipt["seed_count"])
        self.assertEqual(2, receipt["opponent_count"])
        self.assertEqual(list(OPPONENTS), receipt["opponent_ids"])
        self.assertEqual(list(OPPONENTS), receipt["authorized_opponent_ids"])
        self.assertEqual(
            gate.REFERENCE_POLICIES_GIT_BLOB,
            receipt["opponent_registry_git_blob"],
        )
        self.assertEqual(160, receipt["sum_margin_delta"])
        self.assertEqual(10.0, receipt["mean_margin_delta"])
        self.assertEqual(16, receipt["positive_cells"])
        self.assertEqual(0, receipt["negative_cells"])
        self.assertEqual(ENGINE, receipt["engine_id"])
        self.assertEqual(OPPONENT_PACK, receipt["opponent_pack_id"])
        self.assertEqual(CONTROL_ARCHIVE, receipt["control_archive_sha256"])
        self.assertEqual(CANDIDATE_ARCHIVE, receipt["candidate_archive_sha256"])
        self.assertEqual(
            {
                opponent: {
                    "cell_count": 8,
                    "control_margin_sum": 804,
                    "candidate_margin_sum": 884,
                    "sum_margin_delta": 80,
                }
                for opponent in OPPONENTS
            },
            receipt["per_opponent"],
        )
        self.assertRegex(receipt["panel_sha256"], r"^[0-9a-f]{64}$")

    def test_exact_zero_mean_is_no_regression_pass(self):
        receipt = validate(report(delta=0))
        self.assertEqual(0, receipt["sum_margin_delta"])
        self.assertEqual(16, receipt["tied_cells"])
        for opponent in OPPONENTS:
            self.assertEqual(0, receipt["per_opponent"][opponent]["sum_margin_delta"])

    def test_negative_mean_is_rejected(self):
        with self.assertRaisesRegex(gate.EconomicsError, "opponent margin regresses"):
            validate(report(delta=-1))

    def test_positive_global_cannot_mask_one_opponent_regression(self):
        value = report(delta=0)
        for cell in value["cells"]:
            adjustment = -10 if cell["opponent_id"] == "apex_v7" else 20
            cell["candidate_own"] += adjustment
        self.assertGreater(
            sum(
                (cell["candidate_own"] - cell["candidate_rival"])
                - (cell["control_own"] - cell["control_rival"])
                for cell in value["cells"]
            ),
            0,
        )
        with self.assertRaisesRegex(
            gate.EconomicsError,
            "opponent margin regresses.*apex_v7",
        ):
            validate(value)

    def test_release_roster_is_exact_not_arbitrary_balanced_strings(self):
        cases = (
            ("subset", ("apex_v7",)),
            ("superset", ("apex_v7", "arlene_v14", "kaito_v43")),
            ("fake", ("apex_v7", "favorable_fake")),
        )
        for label, opponents in cases:
            with self.subTest(label=label):
                # Keep the subset above the minimum cell count so this
                # predecessor reaches roster validation rather than size.
                seeds = range(100, 108) if label == "subset" else range(100, 104)
                value = report(opponents=opponents, seeds=seeds)
                with self.assertRaisesRegex(
                    gate.EconomicsError,
                    "opponent roster must exactly equal authorized release roster",
                ):
                    validate(value)

    def test_reported_summary_cannot_be_smuggled(self):
        value = report()
        value["mean_margin_delta"] = 999999
        with self.assertRaisesRegex(gate.EconomicsError, "keys mismatch"):
            validate(value)

    def test_cross_build_candidate_is_rejected(self):
        with self.assertRaisesRegex(gate.EconomicsError, "does not match promotion candidate"):
            validate(candidate_id="v5c:" + "3" * 64)

    def test_cross_build_control_is_rejected(self):
        with self.assertRaisesRegex(gate.EconomicsError, "does not match promotion control"):
            validate(control_id="v5c:" + "4" * 64)

    def test_same_control_and_candidate_is_rejected(self):
        value = report()
        value["candidate_id"] = value["control_id"]
        with self.assertRaisesRegex(gate.EconomicsError, "must differ"):
            gate.validate_report(value)

    def test_execution_authority_must_match(self):
        cases = [
            ("engine", {"engine_id": "engine:other"}, "engine_id does not match"),
            (
                "opponent-pack",
                {"opponent_pack_id": "frontier:other"},
                "opponent_pack_id does not match",
            ),
            (
                "control-archive",
                {"control_archive_sha256": "c" * 64},
                "control archive does not match",
            ),
            (
                "candidate-archive",
                {"candidate_archive_sha256": "d" * 64},
                "candidate archive does not match",
            ),
        ]
        for label, expected, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(gate.EconomicsError, message):
                    validate(**expected)

    def test_none_opponent_pack_can_be_bound_exactly(self):
        value = report()
        value["opponent_pack_id"] = None
        receipt = gate.validate_report(
            value,
            candidate_id=CANDIDATE,
            control_id=CONTROL,
            engine_id=ENGINE,
            opponent_pack_id=None,
            control_archive_sha256=CONTROL_ARCHIVE,
            candidate_archive_sha256=CANDIDATE_ARCHIVE,
        )
        self.assertIsNone(receipt["opponent_pack_id"])

    def test_control_and_candidate_archives_must_differ(self):
        value = report()
        value["candidate_archive_sha256"] = value["control_archive_sha256"]
        with self.assertRaisesRegex(gate.EconomicsError, "archive hashes must differ"):
            gate.validate_report(value)

    def test_single_opponent_panel_is_rejected_even_with_enough_cells(self):
        value = report(opponents=("apex_v7",), seeds=range(100, 108))
        with self.assertRaisesRegex(gate.EconomicsError, "authorized release roster"):
            validate(value)

    def test_opponents_must_cover_identical_seed_sets(self):
        value = report()
        for cell in value["cells"]:
            if cell["opponent_id"] == "arlene_v14" and cell["seed"] == 103:
                cell["seed"] = 104
        value["cells"].sort(key=lambda cell: (cell["opponent_id"], cell["seed"], cell["seat"]))
        with self.assertRaisesRegex(gate.EconomicsError, "identical seed sets"):
            validate(value)

    def test_every_opponent_seed_requires_both_seats(self):
        value = report(seeds=range(100, 105))
        value["cells"] = [
            cell for cell in value["cells"]
            if not (
                cell["opponent_id"] == "arlene_v14"
                and cell["seed"] == 104
                and cell["seat"] == 1
            )
        ]
        with self.assertRaisesRegex(gate.EconomicsError, "exactly both seats"):
            validate(value)

    def test_duplicate_opponent_seed_seat_is_rejected(self):
        value = report()
        value["cells"][1] = copy.deepcopy(value["cells"][0])
        with self.assertRaisesRegex(gate.EconomicsError, "must be unique"):
            validate(value)

    def test_too_small_panel_is_rejected(self):
        value = report()
        value["cells"] = value["cells"][:14]
        with self.assertRaisesRegex(gate.EconomicsError, "at least 16 cells"):
            validate(value)

    def test_noncanonical_cell_order_is_rejected(self):
        value = report()
        value["cells"][0], value["cells"][1] = value["cells"][1], value["cells"][0]
        with self.assertRaisesRegex(gate.EconomicsError, "canonically sorted"):
            validate(value)

    def test_empty_opponent_id_is_rejected(self):
        value = report()
        value["cells"][0]["opponent_id"] = ""
        with self.assertRaisesRegex(gate.EconomicsError, "non-empty string"):
            validate(value)

    def test_bool_and_noninteger_scores_are_rejected(self):
        for bad in (True, 10.0, "10"):
            with self.subTest(bad=bad):
                value = report()
                value["cells"][0]["candidate_own"] = bad
                with self.assertRaisesRegex(gate.EconomicsError, "plain int"):
                    validate(value)

    def test_oversized_scores_and_seeds_are_rejected(self):
        for field in ("candidate_own", "seed"):
            with self.subTest(field=field):
                value = report()
                value["cells"][0][field] = 1 << 100
                with self.assertRaisesRegex(gate.EconomicsError, "plain int"):
                    validate(value)

    def test_cell_shape_is_closed(self):
        value = report()
        value["cells"][0]["claimed_delta"] = 1000000
        with self.assertRaisesRegex(gate.EconomicsError, "exact raw score keys"):
            validate(value)

    def test_mixed_sign_panel_uses_recomputed_per_opponent_aggregate(self):
        value = report(delta=0)
        adjustments = [50, -10, -10, -10, -10, -10, 0, 0] * 2
        for cell, adjustment in zip(value["cells"], adjustments):
            cell["candidate_own"] += adjustment
        receipt = validate(value)
        self.assertEqual(0, receipt["sum_margin_delta"])
        self.assertEqual(2, receipt["positive_cells"])
        self.assertEqual(10, receipt["negative_cells"])
        self.assertEqual(4, receipt["tied_cells"])
        for opponent in OPPONENTS:
            self.assertEqual(0, receipt["per_opponent"][opponent]["sum_margin_delta"])

    def test_authority_constants_are_canonical(self):
        self.assertEqual(("apex_v7", "arlene_v14"), gate.AUTHORIZED_OPPONENT_IDS)
        self.assertRegex(gate.REFERENCE_POLICIES_GIT_BLOB, r"^[0-9a-f]{40}$")

    def test_json_loader_rejects_duplicate_keys_and_nonfinite_constants(self):
        with self.assertRaisesRegex(gate.EconomicsError, "duplicate JSON object key"):
            gate._loads_strict('{"a":1,"a":2}')
        with self.assertRaisesRegex(gate.EconomicsError, "non-finite JSON constant"):
            gate._loads_strict('{"a":NaN}')


if __name__ == "__main__":
    unittest.main()
