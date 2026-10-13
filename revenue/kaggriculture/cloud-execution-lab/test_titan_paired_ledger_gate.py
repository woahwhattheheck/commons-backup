#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import math
import unittest

from titan_regression_gate import compare_ledgers as predecessor_compare
from titan_paired_ledger_gate import (
    PairedLedgerError,
    SCHEMA,
    ScheduleKey,
    compare_paired_ledgers,
    schedule_sha256,
    validate_ledger,
)


LEFT = "a" * 64
RIGHT = "b" * 64
ENGINE = "c" * 64
OPPONENT_A = "d" * 64
OPPONENT_B = "e" * 64


def ledger(
    archive: str,
    margins: tuple[float, ...] = (10.0, -2.0, 5.0, 0.0),
    *,
    seeds: tuple[int, ...] = (101, 102),
    opponent: str = OPPONENT_A,
) -> dict:
    coordinates = [(seed, seat) for seed in seeds for seat in (0, 1)]
    rows = [
        {
            "candidate_archive_sha256": archive,
            "environment_seed": seed,
            "opponent_sha256": opponent,
            "seat": seat,
            "margin": margin,
            "status": "DONE",
        }
        for (seed, seat), margin in zip(coordinates, margins)
    ]
    keys = [ScheduleKey(ENGINE, row["environment_seed"], opponent, row["seat"]) for row in rows]
    return {
        "schema": SCHEMA,
        "archive_sha256": archive,
        "engine_sha256": ENGINE,
        "games": len(rows),
        "schedule_sha256": schedule_sha256(keys),
        "rows": rows,
    }


class TitanPairedLedgerGateTests(unittest.TestCase):
    def test_exact_two_seat_panel_is_comparable(self):
        left = ledger(LEFT)
        right = ledger(RIGHT, (12.0, -1.0, 3.0, 4.0))
        report = compare_paired_ledgers(left, right)
        self.assertEqual("COMPARABLE", report["verdict"])
        self.assertTrue(report["custody"]["candidate_archive_bound_per_row"])
        self.assertTrue(report["panel"]["complete_two_seat_pairs"])
        self.assertEqual(2, report["panel"]["matchup_pairs"])
        self.assertEqual({"0", "1"}, set(report["strata"]["by_seat"]))

    def test_predecessor_accepts_relabelled_rows_but_firewall_rejects(self):
        left = ledger(LEFT)
        right = ledger(RIGHT)
        for row in right["rows"]:
            row["candidate_archive_sha256"] = LEFT
        self.assertEqual("COMPARABLE", predecessor_compare(left, right)["verdict"])
        with self.assertRaisesRegex(PairedLedgerError, "candidate archive"):
            compare_paired_ledgers(left, right)

    def test_predecessor_accepts_one_seat_panel_but_firewall_rejects(self):
        left = ledger(LEFT)
        right = ledger(RIGHT)
        for value in (left, right):
            value["rows"] = [row for row in value["rows"] if row["seat"] == 0]
            value["games"] = len(value["rows"])
            keys = [
                ScheduleKey(ENGINE, row["environment_seed"], row["opponent_sha256"], row["seat"])
                for row in value["rows"]
            ]
            value["schedule_sha256"] = schedule_sha256(keys)
        self.assertEqual("COMPARABLE", predecessor_compare(left, right)["verdict"])
        with self.assertRaisesRegex(PairedLedgerError, "incomplete two-seat matchup pairs"):
            compare_paired_ledgers(left, right)

    def test_missing_row_archive_binding_is_rejected(self):
        value = ledger(LEFT)
        del value["rows"][0]["candidate_archive_sha256"]
        with self.assertRaisesRegex(PairedLedgerError, "must include candidate_archive"):
            validate_ledger(value, "candidate")

    def test_declared_schedule_digest_must_match_rows(self):
        value = ledger(LEFT)
        value["schedule_sha256"] = "f" * 64
        with self.assertRaisesRegex(PairedLedgerError, "schedule_sha256 mismatch"):
            validate_ledger(value, "candidate")

    def test_declared_game_count_must_match_rows(self):
        value = ledger(LEFT)
        value["games"] += 1
        with self.assertRaisesRegex(PairedLedgerError, "does not equal rows"):
            validate_ledger(value, "candidate")

    def test_duplicate_exact_cell_is_rejected(self):
        value = ledger(LEFT)
        value["rows"].append(copy.deepcopy(value["rows"][0]))
        value["games"] += 1
        with self.assertRaisesRegex(PairedLedgerError, "duplicate comparison cell"):
            validate_ledger(value, "candidate")

    def test_margin_must_agree_with_scores(self):
        value = ledger(LEFT)
        value["rows"][0].update(candidate_score=10, opponent_score=3, margin=99)
        with self.assertRaisesRegex(PairedLedgerError, "contradicts"):
            validate_ledger(value, "candidate")

    def test_partial_score_pair_is_rejected_even_when_margin_exists(self):
        value = ledger(LEFT)
        value["rows"][0]["candidate_score"] = 10
        with self.assertRaisesRegex(PairedLedgerError, "provide candidate_score and opponent_score together"):
            validate_ledger(value, "candidate")

    def test_nonfinite_evidence_is_rejected(self):
        for bad in (math.inf, -math.inf, math.nan):
            with self.subTest(bad=bad):
                value = ledger(LEFT)
                value["rows"][0]["margin"] = bad
                with self.assertRaisesRegex(PairedLedgerError, "must be finite"):
                    validate_ledger(value, "candidate")

    def test_boolean_evidence_is_not_numeric(self):
        value = ledger(LEFT)
        value["rows"][0]["margin"] = True
        with self.assertRaisesRegex(PairedLedgerError, "must be numeric"):
            validate_ledger(value, "candidate")

    def test_engine_override_cannot_escape_top_level_pin(self):
        value = ledger(LEFT)
        value["rows"][0]["engine_sha256"] = "f" * 64
        with self.assertRaisesRegex(PairedLedgerError, "does not match"):
            validate_ledger(value, "candidate")

    def test_schedule_mismatch_is_refused_not_partially_compared(self):
        left = ledger(LEFT)
        right = ledger(RIGHT, seeds=(101, 103))
        report = compare_paired_ledgers(left, right)
        self.assertEqual("REFUSED", report["verdict"])
        self.assertEqual("PANEL_MISMATCH", report["blockers"][0]["code"])

    def test_same_archive_is_refused(self):
        left = ledger(LEFT)
        right = ledger(LEFT, (12.0, -1.0, 3.0, 4.0))
        report = compare_paired_ledgers(left, right)
        self.assertEqual("REFUSED", report["verdict"])
        self.assertEqual("SAME_ARCHIVE", report["blockers"][0]["code"])

    def test_sha_fields_are_exact_lowercase_hex(self):
        value = ledger(LEFT)
        value["archive_sha256"] = "LEFT"
        with self.assertRaisesRegex(PairedLedgerError, "lowercase 64-hex"):
            validate_ledger(value, "candidate")


if __name__ == "__main__":
    unittest.main()
