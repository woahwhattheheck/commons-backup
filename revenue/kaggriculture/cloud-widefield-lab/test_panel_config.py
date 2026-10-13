#!/usr/bin/env python3
"""Exercise actual panel CLI validation and planning without evaluator games."""
from __future__ import annotations

import argparse
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNNER = Path(__file__).with_name("run_panel.py")
OBSERVATIONS = []


def configuration():
    return {"seeds": {"first": 12, "last": 15, "shard_size": 2},
            "arms": {"one": "existing-candidate.py", "two": "other:agent"},
            "opponents": ["arlene", "existing-opponent.py"],
            "evaluator": "not-invoked.py", "engine": "existing-engine"}


def module():
    name = "finch_panel_config_subject"
    spec = importlib.util.spec_from_file_location(name, RUNNER)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    exec(compile(RUNNER.read_bytes(), str(RUNNER), "exec"), loaded.__dict__)
    return loaded


class PanelConfigTests(unittest.TestCase):
    def invalid(self, cfg, *, workers=2, existing=False, raw=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "panel.json"
            config.write_bytes(raw if raw is not None else json.dumps(cfg).encode())
            output = root / "output"
            sentinel = b"retained previous checkpoint\n"
            if existing:
                output.mkdir()
                (output / "run-state.json").write_bytes(sentinel)
                (output / "old.raw").write_bytes(b"preserved\x00bytes")
            before = {p.relative_to(output).as_posix(): p.read_bytes()
                      for p in output.rglob("*") if p.is_file()}
            process = subprocess.run(
                [sys.executable, "-B", str(RUNNER), "--config", str(config),
                 "--output", str(output), "--jobs", str(workers)],
                capture_output=True, text=True, timeout=10)
            after = {p.relative_to(output).as_posix(): p.read_bytes()
                     for p in output.rglob("*") if p.is_file()}
            OBSERVATIONS.append({"test": self.id().split(".")[-1],
                                 "returncode": process.returncode,
                                 "stdout": process.stdout, "stderr": process.stderr,
                                 "output_exists": output.exists(),
                                 "files_unchanged": before == after})
            self.assertEqual(process.returncode, 2, process.stderr)
            self.assertIn("invalid panel configuration:", process.stderr)
            self.assertNotIn("Traceback", process.stderr)
            self.assertEqual(process.stdout, "")
            self.assertEqual(output.exists(), existing)
            self.assertEqual(before, after)

    def plan(self, cfg, *, workers=2):
        loaded = module()
        received = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            original = json.dumps(cfg)
            source.write_text(original)
            output = root / "output"
            def job(job, evaluator, engine, opponents, out):
                received.append({"job": copy.deepcopy(job), "evaluator": str(evaluator),
                                 "engine": str(engine), "opponents": list(opponents)})
                return {**job, "status": "complete", "planning_fixture": True}
            args = [str(RUNNER), "--config", str(source), "--output", str(output),
                    "--jobs", str(workers)]
            captured = io.StringIO()
            with patch.object(sys, "argv", args), patch.object(loaded, "run_job", job), \
                    contextlib.redirect_stdout(captured):
                result = loaded.main()
            self.assertEqual(result, 0)
            self.assertEqual(source.read_text(), original)
            records = json.loads((output / "run-state.json").read_text())
            self.assertEqual(len(records), len(received))
            self.assertEqual(len(captured.getvalue().splitlines()), len(received))
            return sorted(received, key=lambda row: (row["job"]["arm"], row["job"]["seeds"]))

    def test_01_reversed_range_does_not_succeed_empty(self):
        cfg = configuration(); cfg["seeds"].update(first=3, last=2)
        self.invalid(cfg)

    def test_02_negative_shard_does_not_succeed_empty(self):
        for size in (-1, "-2"):
            with self.subTest(size=size):
                cfg = configuration(); cfg["seeds"]["shard_size"] = size
                self.invalid(cfg)

    def test_03_zero_shard_is_cli_error(self):
        cfg = configuration(); cfg["seeds"]["shard_size"] = 0
        self.invalid(cfg)

    def test_04_empty_arms_does_not_succeed_empty(self):
        cfg = configuration(); cfg["arms"] = {}
        self.invalid(cfg)

    def test_05_empty_opponents_never_dispatches(self):
        cfg = configuration(); cfg["opponents"] = []
        self.invalid(cfg)

    def test_06_invalid_worker_counts_do_not_create_output(self):
        for count in (0, -3):
            with self.subTest(workers=count):
                self.invalid(configuration(), workers=count)

    def test_07_missing_fields_are_cli_errors(self):
        for field in ("seeds", "arms", "opponents", "evaluator", "engine"):
            with self.subTest(field=field):
                cfg = configuration(); del cfg[field]
                self.invalid(cfg)

    def test_08_wrong_container_types(self):
        for field, value in (("seeds", []), ("arms", ["candidate"]),
                             ("opponents", "arlene")):
            with self.subTest(field=field):
                cfg = configuration(); cfg[field] = value
                self.invalid(cfg)
        self.invalid([])

    def test_09_seed_endpoint_types(self):
        for value in (None, True, 1.5, "12"):
            with self.subTest(value=value):
                cfg = configuration(); cfg["seeds"]["first"] = value
                self.invalid(cfg)

    def test_10_unusable_shard_value(self):
        for value in (None, "oops", [], 0.2):
            with self.subTest(value=value):
                cfg = configuration(); cfg["seeds"]["shard_size"] = value
                self.invalid(cfg)

    def test_11_empty_references(self):
        for field in ("evaluator", "engine"):
            with self.subTest(field=field):
                cfg = configuration(); cfg[field] = " "
                self.invalid(cfg)
        cfg = configuration(); cfg["arms"]["one"] = ""
        self.invalid(cfg)
        cfg = configuration(); cfg["opponents"][0] = None
        self.invalid(cfg)

    def test_12_unreadable_json_and_encoding(self):
        for data in (b"{", b"\xff"):
            with self.subTest(data=data):
                self.invalid(None, raw=data)

    def test_13_invalid_request_preserves_existing_checkpoint(self):
        for dimension in ("range", "size", "arms", "opponents"):
            with self.subTest(dimension=dimension):
                cfg = configuration()
                if dimension == "range": cfg["seeds"].update(first=3, last=2)
                if dimension == "size": cfg["seeds"]["shard_size"] = -1
                if dimension == "arms": cfg["arms"] = {}
                if dimension == "opponents": cfg["opponents"] = []
                self.invalid(cfg, existing=True)

    def test_14_valid_grid_and_reference_order(self):
        cfg = configuration()
        rows = self.plan(cfg)
        expected = [(arm, chunk) for arm in ("one", "two") for chunk in ([12, 13], [14, 15])]
        self.assertEqual([(r["job"]["arm"], r["job"]["seeds"]) for r in rows], expected)
        for row in rows:
            self.assertEqual(row["opponents"], cfg["opponents"])
            self.assertEqual(row["job"]["candidate"], cfg["arms"][row["job"]["arm"]])
            self.assertEqual(row["evaluator"], cfg["evaluator"])
            self.assertEqual(row["engine"], cfg["engine"])

    def test_15_single_seed_and_large_shard(self):
        cfg = configuration(); cfg["seeds"].update(first=0, last=0, shard_size=99)
        self.assertEqual([r["job"]["seeds"] for r in self.plan(cfg)], [[0], [0]])

    def test_16_integer_conversion_and_negative_seed_range_preserved(self):
        for value in ("2", 2.0, 2.9):
            with self.subTest(size=value):
                cfg = configuration(); cfg["seeds"].update(first=-2, last=0, shard_size=value)
                rows = self.plan(cfg)
                self.assertEqual([r["job"]["seeds"] for r in rows], [[-2, -1], [0]] * 2)

    def test_17_additional_configuration_and_actor_references_preserved(self):
        cfg = configuration()
        cfg["future_configuration"] = {"notes": [1, 2]}
        cfg["arms"] = {"": "somewhere/agent.py:call", "custom": "arbitrary-reference"}
        cfg["opponents"] = ["other-reference", "other-reference"]
        rows = self.plan(cfg)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r["opponents"] == cfg["opponents"] for r in rows))

    def test_18_ragged_last_shard_preserved(self):
        cfg = configuration(); cfg["seeds"].update(first=1, last=5, shard_size=2)
        rows = self.plan(cfg, workers=1)
        self.assertEqual([r["job"]["seeds"] for r in rows], [[1, 2], [3, 4], [5]] * 2)


def main():
    global RUNNER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, default=RUNNER)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    RUNNER = args.runner.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PanelConfigTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"schema": "titan.panel-config-check.v1", "tests_run": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "successful": result.wasSuccessful(),
              "runner_sha256": hashlib.sha256(RUNNER.read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "full_games": 0, "policy_calls": 0, "engine_calls": 0,
              "scope": "real CLI argument failures; planning-only run_job fixture for valid grids",
              "invalid_cli_attempts": OBSERVATIONS}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
