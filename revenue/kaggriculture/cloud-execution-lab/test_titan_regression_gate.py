#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from titan_regression_gate import GateError, audit_current, compare_ledgers


class TitanRegressionGateTests(unittest.TestCase):
    def fixture(
        self,
        root: Path,
        *,
        test_sha: str | None = None,
        register: bool = True,
        games: int = 0,
        bind_games: bool = True,
    ) -> dict:
        archive_rel = "exports/titan-current.tar.gz"
        source_rel = "runtime/integrated-selected/CURRENT-SOURCE.json"
        archive = root / archive_rel
        source_path = root / source_rel
        tests_path = root / "runtime/integrated-selected/CURRENT-TESTS.json"
        receipt_path = root / "runtime/integrated-selected/CURRENT-ARCHIVE.json"
        registry_path = root / "exports/ARTIFACTS.json"
        for path in (archive, source_path, tests_path, receipt_path, registry_path):
            path.parent.mkdir(parents=True, exist_ok=True)

        archive.write_bytes(b"exact canonical titan archive\n")
        archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        source = {
            "checkpoint": {"playing_strength": "not_measured_for_changed_bytes"},
            "game_evidence_for_this_archive": {
                "new_full_games": games,
                "archive_sha256": archive_sha if bind_games else "f" * 64,
            },
        }
        source_path.write_text(json.dumps(source, indent=2) + "\n")
        source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
        receipt = {
            "path": archive_rel,
            "sha256": archive_sha,
            "bytes": len(archive.read_bytes()),
            "runtime_files": 7,
            "source_manifest": source_rel,
            "source_manifest_sha256": source_sha,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        tested = dict(receipt)
        if test_sha is not None:
            tested["sha256"] = test_sha
        tests_path.write_text(json.dumps({"candidate_archive": tested, "original_observation_checks": {"new_games": games}}, indent=2) + "\n")
        registry = {
            "canonical": {
                "file": archive_rel,
                "sha256": archive_sha if register else "0" * 64,
            }
        }
        registry_path.write_text(json.dumps(registry, indent=2) + "\n")
        return receipt

    def test_integrity_passes_without_claiming_promotion(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(Path(folder))
            report = audit_current(folder)
        self.assertEqual("PASS", report["verdict"])
        self.assertTrue(report["integrity_ready"])
        self.assertFalse(report["promotion_ready"])
        self.assertEqual(0, report["game_evidence"]["reported_full_games"])

    def test_promotion_mode_requires_current_games(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(Path(folder))
            report = audit_current(folder, require_games=True)
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIn("PROMOTION_REQUIRES_CURRENT_GAMES", {row["code"] for row in report["blockers"]})

    def test_exact_bound_games_make_promotion_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(Path(folder), games=32)
            report = audit_current(folder, require_games=True)
        self.assertEqual("PASS", report["verdict"])
        self.assertTrue(report["promotion_ready"])
        self.assertEqual(32, report["game_evidence"]["reported_full_games"])

    def test_stale_test_receipt_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(Path(folder), test_sha="1" * 64)
            report = audit_current(folder)
        self.assertEqual("BLOCKED", report["verdict"])
        self.assertIn("STALE_TEST_RECEIPT", {row["code"] for row in report["blockers"]})

    def test_unregistered_archive_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(Path(folder), register=False)
            report = audit_current(folder)
        self.assertIn("CURRENT_ARCHIVE_UNREGISTERED", {row["code"] for row in report["blockers"]})

    def test_changed_archive_bytes_are_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            receipt = self.fixture(root)
            (root / receipt["path"]).write_bytes(b"mutated after receipt\n")
            report = audit_current(folder)
        codes = {row["code"] for row in report["blockers"]}
        self.assertIn("CANONICAL_ARCHIVE_HASH_MISMATCH", codes)
        self.assertIn("CANONICAL_ARCHIVE_SIZE_MISMATCH", codes)

    def test_unbound_game_count_is_blocked_even_outside_promotion_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(Path(folder), games=8, bind_games=False)
            report = audit_current(folder)
        self.assertIn("UNBOUND_GAME_EVIDENCE", {row["code"] for row in report["blockers"]})

    @staticmethod
    def ledger(archive: str, margins: list[float], *, engine: str = "engine-v1", seeds=(10, 11)) -> dict:
        return {
            "archive_sha256": archive,
            "engine_sha256": engine,
            "rows": [
                {
                    "environment_seed": seed,
                    "opponent_sha256": "opponent-a",
                    "seat": seat,
                    "margin": margin,
                    "status": "DONE",
                }
                for (seed, seat), margin in zip(((seeds[0], 0), (seeds[0], 1), (seeds[1], 0), (seeds[1], 1)), margins)
            ],
        }

    def test_exact_paired_comparison_reports_deltas(self):
        left = self.ledger("left", [1, -2, 3, 0])
        right = self.ledger("right", [4, -2, 1, 7])
        report = compare_ledgers(left, right)
        self.assertEqual("COMPARABLE", report["verdict"])
        self.assertEqual(4, report["cells"])
        self.assertEqual({"right_better": 2, "tie": 1, "right_worse": 1}, report["wins_ties_losses"])
        self.assertEqual(2.0, report["delta"]["mean"])
        self.assertEqual(1.5, report["delta"]["median"])

    def test_different_engine_has_no_comparable_cells(self):
        left = self.ledger("left", [1, 2, 3, 4], engine="engine-a")
        right = self.ledger("right", [2, 3, 4, 5], engine="engine-b")
        report = compare_ledgers(left, right)
        self.assertEqual("REFUSED", report["verdict"])
        self.assertIn("NO_COMPARABLE_CELLS", {row["code"] for row in report["blockers"]})

    def test_partial_schedule_refused_by_default_and_reported_when_allowed(self):
        left = self.ledger("left", [1, 2, 3, 4])
        right = self.ledger("right", [2, 3, 4, 5])
        right["rows"].pop()
        strict = compare_ledgers(left, right)
        partial = compare_ledgers(left, right, require_identical_panel=False)
        self.assertIn("PANEL_MISMATCH", {row["code"] for row in strict["blockers"]})
        self.assertEqual("COMPARABLE", partial["verdict"])
        self.assertEqual(3, partial["cells"])

    def test_duplicate_cell_is_rejected(self):
        left = self.ledger("left", [1, 2, 3, 4])
        right = self.ledger("right", [2, 3, 4, 5])
        right["rows"].append(dict(right["rows"][0]))
        with self.assertRaisesRegex(GateError, "duplicate comparison cell"):
            compare_ledgers(left, right)

    def test_timeout_row_is_rejected(self):
        left = self.ledger("left", [1, 2, 3, 4])
        right = self.ledger("right", [2, 3, 4, 5])
        right["rows"][0]["timeout"] = True
        with self.assertRaisesRegex(GateError, "timeout"):
            compare_ledgers(left, right)


if __name__ == "__main__":
    unittest.main()
