#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("bind_result_provenance", HERE / "bind_result_provenance.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


class ResultProvenanceTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        candidate = root / "candidate"
        candidate.mkdir()
        (candidate / "main.py").write_text("def agent(obs, cfg): return {}\n")
        engine = root / "engine.py"
        engine.write_text("ENGINE = 'pinned'\n")
        opponents = root / "opponents"
        opponents.mkdir()
        (opponents / "starter.py").write_text("def agent(obs, cfg): return {}\n")
        rows = [
            {
                "environment_seed": 9922023,
                "opponent_artifact": "starter.py",
                "seat": 0,
                "status": "DONE",
                "rewards": [168572, 3550],
            },
            {
                "environment_seed": 9922023,
                "opponent_artifact": "starter.py",
                "seat": 1,
                "status": "DONE",
                "rewards": [3550, 168572],
            },
        ]
        return temp, root, candidate, engine, opponents, rows

    def bind(self, mutate=None):
        temp, root, candidate, engine, opponents, rows = self.fixture()
        self.addCleanup(temp.cleanup)
        if mutate:
            mutate(root, candidate, engine, opponents, rows)
        return mod.bind_results(
            candidate_path=candidate,
            engine_path=engine,
            opponent_root=opponents,
            rows=rows,
        )

    def test_large_legitimate_margin_is_preserved_without_ceiling(self):
        ledger, analyzer, receipt = self.bind()
        self.assertEqual([165022.0, 165022.0], [row["margin"] for row in analyzer])
        self.assertEqual(165022.0, receipt["max_abs_margin"])
        self.assertFalse(receipt["score_ceiling_applied"])
        self.assertEqual(2, len(ledger["rows"]))

    def test_candidate_digest_changes_with_candidate_bytes(self):
        ledger1, _, _ = self.bind()

        def change(root, candidate, engine, opponents, rows):
            (candidate / "main.py").write_text("def agent(obs, cfg): return {'changed': True}\n")

        ledger2, _, _ = self.bind(change)
        self.assertNotEqual(ledger1["candidate_sha256"], ledger2["candidate_sha256"])

    def test_engine_digest_changes_with_engine_bytes(self):
        ledger1, _, _ = self.bind()

        def change(root, candidate, engine, opponents, rows):
            engine.write_text("ENGINE = 'different'\n")

        ledger2, _, _ = self.bind(change)
        self.assertNotEqual(ledger1["engine_sha256"], ledger2["engine_sha256"])

    def test_contradictory_margin_is_rejected(self):
        def change(root, candidate, engine, opponents, rows):
            rows[0]["margin"] = 1e300

        with self.assertRaises(mod.ProvenanceError):
            self.bind(change)

    def test_relative_tolerance_cannot_authenticate_large_absolute_conflict(self):
        def change(root, candidate, engine, opponents, rows):
            rows[0]["rewards"] = [1e20, 0]
            rows[0]["candidate_score"] = 1e20 + 50_000_000
            rows[1]["rewards"] = [0, 1e20]

        with self.assertRaises(mod.ProvenanceError):
            self.bind(change)

    def test_large_integer_alias_cannot_collapse_through_float(self):
        def change(root, candidate, engine, opponents, rows):
            rows[0]["rewards"] = [10**20, 0]
            rows[0]["candidate_score"] = 10**20 + 1
            rows[1]["rewards"] = [0, 10**20]

        with self.assertRaises(mod.ProvenanceError):
            self.bind(change)

    def test_derived_margin_overflow_fails_closed(self):
        def change(root, candidate, engine, opponents, rows):
            rows[0]["rewards"] = [1e308, -1e308]
            rows[1]["rewards"] = [-1e308, 1e308]

        with self.assertRaises(mod.ProvenanceError):
            self.bind(change)

    def test_nonfinite_and_overflow_rewards_are_rejected(self):
        def inf(root, candidate, engine, opponents, rows):
            rows[0]["rewards"][0] = float("inf")

        with self.assertRaises(mod.ProvenanceError):
            self.bind(inf)

        def huge(root, candidate, engine, opponents, rows):
            rows[0]["rewards"][0] = 10**1000

        with self.assertRaises(mod.ProvenanceError):
            self.bind(huge)

    def test_bool_seat_is_rejected(self):
        def change(root, candidate, engine, opponents, rows):
            rows[0]["seat"] = True

        with self.assertRaises(mod.ProvenanceError):
            self.bind(change)

    def test_unfinished_or_error_result_is_rejected(self):
        def unfinished(root, candidate, engine, opponents, rows):
            rows[0]["status"] = "TIMEOUT"

        with self.assertRaises(mod.ProvenanceError):
            self.bind(unfinished)

        def errored(root, candidate, engine, opponents, rows):
            rows[0]["error"] = "boom"

        with self.assertRaises(mod.ProvenanceError):
            self.bind(errored)

    def test_duplicate_cell_is_rejected(self):
        def change(root, candidate, engine, opponents, rows):
            rows.append(dict(rows[0]))

        with self.assertRaises(mod.ProvenanceError):
            self.bind(change)

    def test_missing_opposite_seat_is_rejected(self):
        def change(root, candidate, engine, opponents, rows):
            rows.pop()

        with self.assertRaises(mod.ProvenanceError):
            self.bind(change)

    def test_opponent_path_traversal_and_symlink_are_rejected(self):
        def traversal(root, candidate, engine, opponents, rows):
            rows[0]["opponent_artifact"] = "../engine.py"

        with self.assertRaises(mod.ProvenanceError):
            self.bind(traversal)
        temp, root, candidate, engine, opponents, rows = self.fixture()
        self.addCleanup(temp.cleanup)
        link = opponents / "link.py"
        try:
            link.symlink_to(engine)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unsupported")
        rows[0]["opponent_artifact"] = "link.py"
        rows[1]["opponent_artifact"] = "link.py"
        with self.assertRaises(mod.ProvenanceError):
            mod.bind_results(candidate_path=candidate, engine_path=engine, opponent_root=opponents, rows=rows)

    def test_replicate_is_folded_into_legacy_seed_without_collision(self):
        def change(root, candidate, engine, opponents, rows):
            rows[0]["replicate"] = 2
            rows[1]["replicate"] = 2

        ledger, analyzer, receipt = self.bind(change)
        self.assertEqual({"9922023::replicate=2"}, {row["environment_seed"] for row in ledger["rows"]})
        self.assertEqual({"9922023::replicate=2"}, {row["seed"] for row in analyzer})
        self.assertEqual(1, receipt["paired_cells"])

    def test_duplicate_json_keys_fail_closed(self):
        with self.assertRaises(mod.ProvenanceError):
            mod._loads_strict('{"seat":0,"seat":1}', "row")

    def test_cli_writes_ledger_analyzer_and_receipt(self):
        temp, root, candidate, engine, opponents, rows = self.fixture()
        self.addCleanup(temp.cleanup)
        results = root / "results.jsonl"
        results.write_text("".join(json.dumps(row) + "\n" for row in rows))
        ledger = root / "ledger.json"
        analyzer = root / "analyzer.jsonl"
        receipt = root / "receipt.json"
        rc = mod.main([
            "--candidate", str(candidate),
            "--engine", str(engine),
            "--opponent-root", str(opponents),
            "--results", str(results),
            "--ledger-out", str(ledger),
            "--analyzer-jsonl", str(analyzer),
            "--receipt-out", str(receipt),
        ])
        self.assertEqual(0, rc)
        self.assertEqual(2, len(json.loads(ledger.read_text())["rows"]))
        self.assertEqual(2, len(analyzer.read_text().splitlines()))
        self.assertEqual("PASS", json.loads(receipt.read_text())["verdict"])


if __name__ == "__main__":
    unittest.main()
