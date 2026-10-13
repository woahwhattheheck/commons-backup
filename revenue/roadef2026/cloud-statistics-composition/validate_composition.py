#!/usr/bin/env python3
"""Validate the statistics/output repair on the exact frozen three-kernel source.

This performs only source composition, compilation, generated-fixture regressions,
and the two existing joint official-checker discriminators. It does not run set A,
set B, a public benchmark bank, or alter a qualification package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from compose_statistics import (
    COMPOSED_SHA256,
    FROZEN_SHA256,
    PATCH_SHA256,
    compose,
    identity,
)
import sys

ALGORITHM_FUNCTIONS = {
    "dag": "Dag& dag(",
    "segment": "const Sparse& segment(",
    "routeFlow": "bool routeFlow(",
    "distance": "int distance(",
    "quantizedImproves": "static bool quantizedImproves(",
    "moveTogether": "bool moveTogether(",
    "waypointCandidates": "Route waypointCandidates(",
    "eject": "bool eject(",
    "run": "void run()",
    "constructor": "Solver(const std::string& netPath",
}


def extract_function(text: str, needle: str) -> str:
    start = text.index(needle)
    brace = text.index("{", start)
    depth = 0
    in_string: str | None = None
    escaped = line_comment = block_comment = False
    index = brace
    while index < len(text):
        current = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if current == "\n":
                line_comment = False
        elif block_comment:
            if current == "*" and following == "/":
                block_comment = False
                index += 1
        elif in_string:
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == in_string:
                in_string = None
        else:
            if current == "/" and following == "/":
                line_comment = True
                index += 1
            elif current == "/" and following == "*":
                block_comment = True
                index += 1
            elif current in ("'", '"'):
                in_string = current
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        index += 1
    raise ValueError(f"unterminated function: {needle}")


def function_hashes(path: Path) -> dict[str, dict[str, Any]]:
    text = path.read_text()
    result: dict[str, dict[str, Any]] = {}
    for name, needle in ALGORITHM_FUNCTIONS.items():
        body = extract_function(text, needle)
        result[name] = {
            "bytes": len(body.encode()),
            "sha256": hashlib.sha256(body.encode()).hexdigest(),
        }
    return result


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def count_failed_methods(report: dict[str, Any]) -> int:
    return len({entry["test"].split(" (")[0] for entry in report["failures"]})


def validate(args: argparse.Namespace) -> dict[str, Any]:
    frozen = args.frozen_source.resolve(strict=True)
    patch = args.patch.resolve(strict=True)
    vendor = args.rapidjson_vendor.resolve(strict=True)
    regression = args.regression_script.resolve(strict=True)
    fixtures = args.fixtures.resolve(strict=True)
    checker = args.checker_binary.resolve(strict=True)
    verifier = args.joint_verifier.resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix="roadef-statistics-validation-") as name:
        root = Path(name)
        composed = root / "composed.cpp"
        compose_record = compose(frozen, patch, composed)

        source_functions = function_hashes(frozen)
        composed_functions = function_hashes(composed)
        if source_functions != composed_functions:
            changed = sorted(set(source_functions) | set(composed_functions))
            mismatch = [key for key in changed if source_functions.get(key) != composed_functions.get(key)]
            raise AssertionError(f"algorithm function changed: {mismatch}")

        binaries: dict[str, dict[str, Path]] = {}
        versions: dict[str, str] = {}
        for label, compiler in (("gcc", args.gxx), ("clang", args.clangxx)):
            versions[label] = run([compiler, "--version"]).stdout.splitlines()[0]
            binaries[label] = {}
            for arm, source in (("frozen", frozen), ("composed", composed)):
                binary = root / f"{arm}-{label}"
                run([
                    compiler,
                    "-std=c++17",
                    "-O2",
                    "-DNDEBUG",
                    "-I",
                    str(vendor),
                    str(source),
                    "-o",
                    str(binary),
                ])
                binaries[label][arm] = binary

        regression_results: dict[str, Any] = {}
        for label in ("gcc", "clang"):
            passed_report = root / f"passed-{label}.json"
            run([
                sys.executable,
                "-B",
                str(regression),
                "--binary",
                str(binaries[label]["composed"]),
                "--reference-binary",
                str(binaries[label]["frozen"]),
                "--fixtures",
                str(fixtures),
                "--report",
                str(passed_report),
            ])
            passed = json.loads(passed_report.read_text())
            if not passed["successful"] or passed["tests_run"] != 24:
                raise AssertionError((label, passed))

            control_report = root / f"control-{label}.json"
            control_run = subprocess.run([
                sys.executable,
                "-B",
                str(regression),
                "--binary",
                str(binaries[label]["frozen"]),
                "--reference-binary",
                str(binaries[label]["frozen"]),
                "--fixtures",
                str(fixtures),
                "--report",
                str(control_report),
            ], capture_output=True, text=True, timeout=180)
            control = json.loads(control_report.read_text())
            if control_run.returncode == 0 or control["successful"] or control["tests_run"] != 24:
                raise AssertionError((label, control_run.returncode, control))
            if len(control["failures"]) != 25 or control["errors"]:
                raise AssertionError((label, len(control["failures"]), control["errors"]))
            regression_results[label] = {
                "candidate": passed,
                "control": {
                    "tests_run": control["tests_run"],
                    "successful": control["successful"],
                    "failed_records": len(control["failures"]),
                    "failed_methods": count_failed_methods(control),
                    "errors": len(control["errors"]),
                },
            }

        joint_results: dict[str, Any] = {}
        summaries: dict[str, Any] = {}
        for arm, binary in (("frozen", binaries["gcc"]["frozen"]), ("composed", binaries["gcc"]["composed"])):
            output = root / f"joint-{arm}"
            run([
                sys.executable,
                "-B",
                str(verifier),
                "--solver",
                str(binary),
                "--checker",
                str(checker),
                "--output",
                str(output),
            ], timeout=300)
            summaries[arm] = json.loads((output / "summary.json").read_text())

        if summaries["frozen"]["cases"] != summaries["composed"]["cases"]:
            raise AssertionError("official-checker case summaries differ")
        byte_matches: dict[str, bool] = {}
        for case in ("joint", "joint-budget"):
            for suffix in ("disabled", "enabled", "repeat"):
                name = f"{case}-{suffix}.json"
                match = (root / "joint-frozen" / name).read_bytes() == (root / "joint-composed" / name).read_bytes()
                byte_matches[name] = match
                if not match:
                    raise AssertionError(f"solution output differs: {name}")
        joint_results = {
            "checker": identity(checker),
            "cases": summaries["composed"]["cases"],
            "solution_bytes_identical": byte_matches,
            "all_solution_bytes_identical": all(byte_matches.values()),
        }

        return {
            "schema": "roadef-statistics-three-kernel-validation-v1",
            "status": "PASS",
            "scope": "frozen_three_kernel_plus_output_publication_only",
            "composition": compose_record,
            "frozen_source_sha256": FROZEN_SHA256,
            "statistics_patch_sha256": PATCH_SHA256,
            "composed_source_sha256": COMPOSED_SHA256,
            "compiler_versions": versions,
            "regressions": regression_results,
            "algorithm_functions_identical": True,
            "algorithm_function_hashes": source_functions,
            "official_checker": joint_results,
            "limits": [
                "No set-A or set-B instance was executed.",
                "No calibration source, qualification archive, draft, or submission was changed.",
                "The joint fixtures are manufactured discriminators, not public-instance scores.",
                "The output repair changes file ownership and statistics publication only.",
            ],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument("--frozen-source", type=Path, required=True)
    parser.add_argument("--patch", type=Path, default=here / "frozen-three-kernel-statistics.patch")
    parser.add_argument("--rapidjson-vendor", type=Path, required=True)
    parser.add_argument("--regression-script", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--checker-binary", type=Path, required=True)
    parser.add_argument("--joint-verifier", type=Path, required=True)
    parser.add_argument("--gxx", default="g++")
    parser.add_argument("--clangxx", default="clang++")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("output already exists")
    try:
        report = validate(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, RuntimeError, AssertionError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
