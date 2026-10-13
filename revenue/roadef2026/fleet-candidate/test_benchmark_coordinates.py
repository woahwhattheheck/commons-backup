# SPDX-License-Identifier: MIT
"""Validate benchmark load-coordinate universes before ranking.

The suite runs the real benchmark parser, worker, validation and filesystem
writes. Most methods replace only the child-process boundary with deterministic
fixtures; one method launches real local synthetic solver/checker children.
No official solver, official checker, network, benchmark panel or submission is
invoked.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
import random
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import types
import unittest
from unittest import mock

BENCHMARK = Path(__file__).with_name("benchmark.py")
EVIDENCE: Path | None = None
DETAILS: list[dict] = []

LANDED_FUNCTION_AST_SHA256 = {
    "digest": "59829d00320d583b609209a7c67d5a102b9a176355eeb805ab27cbacf9e042da",
    "execute": "a0f80bde4937e208e6c6e153c7ad1ae3f3a57d14b9c40208612479b200e3ee99",
    "finite_loads": "16c209cfd6601a245d64b3a209ec947dd4448568ab166218b5e1d772a3e92671",
    "reserve_outputs": "e4c2a04aad6a41009d6af23e41c5374cf247b00036145fc8b59bb1ab6ab0835b",
}


def loads(values=(0.75, 0.25)):
    return [
        {"t": 0, "from": 1, "to": index + 2, "sat": value}
        for index, value in enumerate(values)
    ]


def cells():
    base = {
        "six": {"valid": True, "saturations": loads(), "total_cost": 0},
        "twelve": {"valid": True, "saturations": loads(), "total_cost": 0},
        "stats": {
            "loads": loads(),
            "budget_used": [0],
            "accepted": 0,
            "attempted": 0,
        },
    }
    return {"baseline": copy.deepcopy(base), "candidate": copy.deepcopy(base)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_case(root, payload, benchmark=None, actual_children=False):
    benchmark = Path(benchmark or BENCHMARK).resolve()
    root.mkdir(parents=True, exist_ok=True)
    protocol = root / "fixtures.json"
    protocol.write_text(json.dumps(payload), encoding="utf-8")
    data = root / "data" / "setB"
    data.mkdir(parents=True)
    for suffix in ("net", "tm", "scenario"):
        (data / f"setB-01-{suffix}.json").write_text("{}\n")

    solver_code = """import json, os, pathlib, sys
root = pathlib.Path(__file__).resolve().parent
out = pathlib.Path(sys.argv[-1])
fixture = json.loads((root/'fixtures.json').read_text())[out.parent.name]
out.write_text('{"srpaths":[]}\\n')
pathlib.Path(os.environ['SEDGE_STATS']).write_text(json.dumps(fixture['stats']))
print('synthetic solver fixture; no optimization run')
"""
    checker_code = """import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parent
argv = sys.argv[1:]
solution = pathlib.Path(argv[argv.index('--srpaths') + 1])
decimals = argv[argv.index('--max-decimal-places') + 1]
fixture = json.loads((root/'fixtures.json').read_text())[solution.parent.name]
print(json.dumps(fixture['six' if decimals == '6' else 'twelve']))
"""
    for name, code in (("solver", solver_code), ("checker", checker_code)):
        path = root / name
        path.write_text("#!" + sys.executable + "\n" + code)
        path.chmod(0o755)

    output = root / "output"
    command = [
        sys.executable,
        str(benchmark),
        "--solver",
        f"baseline={root / 'solver'}",
        "--solver",
        f"candidate={root / 'solver'}",
        "--checker",
        str(root / "checker"),
        "--data",
        str(root / "data"),
        "--instances",
        "setB-01",
        "--seconds",
        "0.01",
        "--workers",
        "1",
        "--output",
        str(output),
    ]
    if actual_children:
        result = subprocess.run(command, capture_output=True, timeout=20)
    else:
        module = types.ModuleType("benchmark_under_test")
        module.__file__ = str(benchmark)
        exec(compile(benchmark.read_bytes(), str(benchmark), "exec"), module.__dict__)
        module.platform.platform()

        def fixture_run(cmd, **kwargs):
            cmd = list(map(str, cmd))
            if Path(cmd[0]).name == "solver":
                solution = Path(cmd[-1])
                fixture = payload[solution.parent.name]
                solution.write_text('{"srpaths":[]}\n')
                Path(kwargs["env"]["SEDGE_STATS"]).write_text(json.dumps(fixture["stats"]))
                stdout = b"synthetic solver fixture; no optimization run\n"
            else:
                solution = Path(cmd[cmd.index("--srpaths") + 1])
                precision = cmd[cmd.index("--max-decimal-places") + 1]
                key = "six" if precision == "6" else "twelve"
                stdout = (json.dumps(payload[solution.parent.name][key]) + "\n").encode()
            return subprocess.CompletedProcess(cmd, 0, stdout, b"")

        stdout = io.StringIO()
        stderr = io.StringIO()
        returncode = 0
        with (
            mock.patch.object(sys, "argv", command[1:]),
            mock.patch.object(module.subprocess, "run", side_effect=fixture_run),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                module.main()
            except Exception:
                returncode = 1
                traceback.print_exc()
        result = subprocess.CompletedProcess(
            command, returncode, stdout.getvalue().encode(), stderr.getvalue().encode()
        )

    (root / "benchmark.stdout").write_bytes(result.stdout)
    (root / "benchmark.stderr").write_bytes(result.stderr)
    (root / "process.json").write_text(
        json.dumps(
            {
                "command": command,
                "returncode": result.returncode,
                "benchmark_sha256": digest(benchmark),
            },
            indent=2,
        )
        + "\n"
    )
    return result, output


@unittest.skipUnless(os.name == "posix", "Controlled executable fixtures require POSIX")
class BenchmarkCoordinateTests(unittest.TestCase):
    def invoke(self, mutate=None, *, actual_children=False):
        temp = tempfile.TemporaryDirectory(prefix="roadef-coordinate-test-")
        self.addCleanup(temp.cleanup)
        payload = cells()
        if mutate:
            mutate(payload["candidate"])
        result, output = run_case(
            Path(temp.name), payload, benchmark=BENCHMARK, actual_children=actual_children
        )
        record = {
            "method": self._testMethodName,
            "returncode": result.returncode,
            "benchmark_sha256": digest(BENCHMARK),
            "summary_written": (output / "summary.json").exists(),
            "candidate_result_written": (
                output / "setB-01/candidate/result.json"
            ).exists(),
            "stderr": result.stderr.decode(errors="replace"),
        }
        DETAILS.append(record)
        if EVIDENCE is not None:
            destination = EVIDENCE / self._testMethodName
            destination.mkdir(parents=True, exist_ok=False)
            source = Path(temp.name)
            for path in source.rglob("*"):
                if path.is_file():
                    target = destination / path.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
        return result, output

    def rejected(self, mutate, message):
        result, output = self.invoke(mutate)
        self.assertNotEqual(result.returncode, 0, "malformed data received a success result")
        self.assertIn(message, result.stderr.decode(errors="replace"))
        self.assertFalse((output / "setB-01/candidate/result.json").exists())
        self.assertFalse((output / "summary.json").exists())
        self.assertTrue((output / "setB-01/baseline/result.json").exists())
        self.assertTrue((output / "setB-01/candidate/checker-6.stdout").exists())
        self.assertTrue((output / "setB-01/candidate/checker-12.stdout").exists())

    def test_unchanged_reports_remain_tie(self):
        result, output = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads((output / "setB-01/candidate/result.json").read_text())
        self.assertEqual(row["vs_first"], "tie")
        self.assertIsNone(row["first_difference_rank"])
        self.assertEqual(row["load_count"], 2)
        self.assertEqual(row["max_load_error"], 0)

    def test_real_lower_tail_improvement_remains_win(self):
        def mutate(candidate):
            for key in ("six", "twelve"):
                candidate[key]["saturations"][1]["sat"] = 0.2
            candidate["stats"]["loads"][1]["sat"] = 0.2

        result, output = self.invoke(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads((output / "setB-01/candidate/result.json").read_text())
        self.assertEqual((row["vs_first"], row["first_difference_rank"]), ("win", 2))

    def test_reordered_coordinates_remain_tie(self):
        result, output = self.invoke(lambda candidate: candidate["six"]["saturations"].reverse())
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads((output / "setB-01/candidate/result.json").read_text())
        self.assertEqual(row["vs_first"], "tie")

    def test_missing_tail_not_scored_as_win(self):
        self.rejected(lambda candidate: candidate["six"]["saturations"].pop(), "Load key mismatch")

    def test_missing_peak_not_scored_as_win(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"].pop(0),
            "Load key mismatch",
        )

    def test_wrong_six_decimal_coordinate_is_rejected(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"][1].update(to=99),
            "Load key mismatch",
        )

    def test_duplicate_six_decimal_coordinate_is_rejected(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"].append(
                copy.deepcopy(candidate["six"]["saturations"][0])
            ),
            "Duplicate load coordinate",
        )

    def test_duplicate_twelve_decimal_coordinate_is_rejected(self):
        self.rejected(
            lambda candidate: candidate["twelve"]["saturations"].append(
                copy.deepcopy(candidate["twelve"]["saturations"][0])
            ),
            "Duplicate load coordinate",
        )

    def test_duplicate_diagnostic_coordinate_is_rejected(self):
        self.rejected(
            lambda candidate: candidate["stats"]["loads"].append(
                copy.deepcopy(candidate["stats"]["loads"][0])
            ),
            "Duplicate load coordinate",
        )

    def test_canonicalized_id_duplicate_is_rejected(self):
        def mutate(candidate):
            duplicate = copy.deepcopy(candidate["twelve"]["saturations"][0])
            duplicate["from"] = "1"
            duplicate["to"] = "2"
            candidate["twelve"]["saturations"].append(duplicate)

        self.rejected(mutate, "Duplicate load coordinate")

    def test_shared_wrong_coordinates_across_candidate_files_are_rejected(self):
        def mutate(candidate):
            for kind in ("six", "twelve"):
                candidate[kind]["saturations"][0]["from"] = 99
            candidate["stats"]["loads"][0]["from"] = 99

        self.rejected(mutate, "Load key mismatch across solvers")

    def test_shared_missing_tail_across_candidate_files_is_rejected(self):
        def mutate(candidate):
            for kind in ("six", "twelve"):
                candidate[kind]["saturations"].pop()
            candidate["stats"]["loads"].pop()

        self.rejected(mutate, "Load key mismatch across solvers")

    def test_nan_six_decimal_saturation_retains_finite_guard(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"][0].update(sat=float("nan")),
            "non-finite saturation",
        )

    def test_infinite_six_decimal_saturation_retains_finite_guard(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"][0].update(sat=float("inf")),
            "non-finite saturation",
        )

    def test_negative_six_decimal_saturation_is_rejected(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"][0].update(sat=-0.1),
            "Invalid saturation",
        )

    def test_boolean_six_decimal_saturation_is_rejected(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"][0].update(sat=True),
            "Invalid saturation",
        )

    def test_string_six_decimal_saturation_is_rejected(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"][0].update(sat="0.75"),
            "Invalid saturation",
        )

    def test_nan_twelve_decimal_saturation_retains_finite_guard(self):
        self.rejected(
            lambda candidate: candidate["twelve"]["saturations"][0].update(sat=float("nan")),
            "non-finite saturation",
        )

    def test_nan_diagnostic_saturation_retains_finite_guard(self):
        self.rejected(
            lambda candidate: candidate["stats"]["loads"][0].update(sat=float("nan")),
            "non-finite saturation",
        )

    def test_missing_coordinate_field_is_rejected_explicitly(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"][0].pop("from"),
            "Invalid load row",
        )

    def test_empty_saturations_are_rejected_explicitly(self):
        self.rejected(
            lambda candidate: candidate["six"].update(saturations=[]),
            "Load rows must be a nonempty list",
        )

    def test_non_object_row_is_rejected_explicitly(self):
        self.rejected(
            lambda candidate: candidate["six"]["saturations"].__setitem__(0, None),
            "Invalid load row",
        )

    def test_existing_reporting_precision_is_accepted_without_rounding(self):
        def mutate(candidate):
            candidate["six"]["saturations"][1]["sat"] = 9.933579335793359e-7
            candidate["twelve"]["saturations"][1]["sat"] = 9.93357933579e-7
            candidate["stats"]["loads"][1]["sat"] = 9.933579335793359e-7

        result, output = self.invoke(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads((output / "setB-01/candidate/result.json").read_text())
        self.assertEqual((row["vs_first"], row["first_difference_rank"]), ("win", 2))
        raw = json.loads((output / "setB-01/candidate/checker-6.stdout").read_text())
        self.assertEqual(raw["saturations"][1]["sat"], 9.933579335793359e-7)

    def test_landed_process_and_finite_helpers_are_ast_identical(self):
        functions = {
            node.name: hashlib.sha256(
                ast.dump(node, include_attributes=False).encode()
            ).hexdigest()
            for node in ast.parse(BENCHMARK.read_text()).body
            if isinstance(node, ast.FunctionDef)
        }
        for name, expected in LANDED_FUNCTION_AST_SHA256.items():
            self.assertEqual(functions[name], expected, name)

    def test_generated_valid_reports_preserve_values_scores_and_errors(self):
        module = types.ModuleType("benchmark_coordinate_application")
        module.__file__ = str(BENCHMARK)
        exec(compile(BENCHMARK.read_bytes(), str(BENCHMARK), "exec"), module.__dict__)
        rng = random.Random(8022026)
        for case in range(300):
            count = rng.randrange(1, 80)
            actual_rows = [
                {
                    "t": index // 5,
                    "from": 1,
                    "to": index + 2,
                    "sat": rng.randrange(1_000_000) / 1_000_000,
                }
                for index in range(count)
            ]
            actual_rows[-1]["sat"] = 0
            score_rows = copy.deepcopy(actual_rows)
            predicted_rows = copy.deepcopy(actual_rows)
            for row in predicted_rows:
                row["sat"] += rng.choice((0, 1e-13))
            rng.shuffle(score_rows)
            rng.shuffle(predicted_rows)
            actual = {
                (row["t"], str(row["from"]), str(row["to"])): row["sat"]
                for row in actual_rows
            }
            predicted = {
                (row["t"], str(row["from"]), str(row["to"])): row["sat"]
                for row in predicted_rows
            }
            expected = (
                sorted((row["sat"] for row in score_rows), reverse=True),
                max(abs(actual[key] - value) for key, value in predicted.items()),
                frozenset(actual),
            )
            reports = {
                6: {"saturations": score_rows},
                12: {"saturations": actual_rows},
            }
            before = copy.deepcopy(reports)
            result = module.validated_loads(reports, {"loads": predicted_rows})
            self.assertEqual(result, expected, case)
            self.assertEqual(reports, before)

    def test_real_local_children_reject_missing_tail_and_retain_raw_output(self):
        result, output = self.invoke(
            lambda candidate: candidate["six"]["saturations"].pop(),
            actual_children=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Load key mismatch", result.stderr.decode(errors="replace"))
        folder = output / "setB-01/candidate"
        self.assertTrue((folder / "checker-6.stdout").exists())
        self.assertTrue((folder / "checker-12.stdout").exists())
        self.assertFalse((folder / "result.json").exists())


def main():
    global BENCHMARK, EVIDENCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=BENCHMARK)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--method", action="append")
    args = parser.parse_args()
    BENCHMARK = args.benchmark.resolve()
    if args.evidence:
        EVIDENCE = args.evidence.resolve()
        EVIDENCE.mkdir(parents=True, exist_ok=False)
    methods = args.method or unittest.defaultTestLoader.getTestCaseNames(
        BenchmarkCoordinateTests
    )
    suite = unittest.TestSuite(BenchmarkCoordinateTests(name) for name in methods)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "schema": "roadef-benchmark-coordinate-validation-v1",
        "benchmark_sha256": digest(BENCHMARK),
        "test_sha256": digest(__file__),
        "python": sys.version,
        "methods": methods,
        "tests_run": result.testsRun,
        "failures": [[str(test), error] for test, error in result.failures],
        "errors": [[str(test), error] for test, error in result.errors],
        "skipped": [[str(test), error] for test, error in result.skipped],
        "cases": DETAILS,
        "official_solver_runs": 0,
        "official_checker_runs": 0,
        "network_calls": 0,
        "scope": "actual benchmark CLI and local controlled child fixtures",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
