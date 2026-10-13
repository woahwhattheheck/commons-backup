# SPDX-License-Identifier: Apache-2.0
"""Run canonical V4 unittest files, including hyphenated directories, in isolation.

This is a local correctness runner, not a gameplay/promotion or CI-trust gate.
Only explicit test/runner/bind-file digests are provenance; dependency closure is
not inferred. Every selected file must run at least one test in both modes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

EXCLUDED = frozenset({"donor", "legacy", "historical", "original", "raw", "fixtures", "__pycache__"})
SCHEMA = "titan-v4-component-smoke/v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_tests(root: Path, patterns: list[str]) -> list[Path]:
    """Select real files recursively, without requiring package __init__.py files."""
    found = set()
    for pattern in patterns:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ValueError("test selectors must stay within the V4 root")
        for candidate in root.glob(pattern):
            if not candidate.is_file() or candidate.suffix != ".py":
                continue
            relative = candidate.relative_to(root)
            if any(part in EXCLUDED or part.startswith("legacy-") for part in relative.parts[:-1]):
                continue
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError("test symlink escapes the V4 root")
            found.add(resolved)
    return sorted(found, key=lambda path: str(path.relative_to(root)))


def child(test: Path, receipt: Path) -> int:
    """Run one unittest module; do not invoke its __main__ or reuse other suites."""
    report = {"schema": SCHEMA, "test_sha256": digest(test),
              "optimized": sys.flags.optimize, "tests": 0, "status": "error"}
    try:
        sys.path.insert(0, str(test.parent))
        name = "_titan_component_" + hashlib.sha256(str(test).encode()).hexdigest()[:16]
        spec = importlib.util.spec_from_file_location(name, test)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {test}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        discovered = suite.countTestCases()
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        report.update(tests=result.testsRun, discovered=discovered,
                      failures=len(result.failures), errors=len(result.errors),
                      skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
                      unexpected_successes=len(result.unexpectedSuccesses))
        complete = (result.testsRun > 0 and result.testsRun == discovered
                    and result.wasSuccessful() and not result.skipped
                    and not result.expectedFailures and not result.unexpectedSuccesses)
        report["status"] = "passed" if complete else "failed"
        if not discovered:
            report["reason"] = "zero tests discovered"
        elif result.skipped or result.expectedFailures:
            report["reason"] = "incomplete: skipped or expected-failure tests"
        if digest(test) != report["test_sha256"]:
            report.update(status="failed", reason="test source changed during execution")
    except BaseException as exc:
        # SystemExit raised while importing must not turn an unrun suite green.
        report.update(status="error", reason=f"{type(exc).__name__}: {exc}")
    receipt.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


def run_file(test: Path, *, root: Path, optimized: bool, timeout: float,
             pythonpaths: list[Path]) -> dict:
    before = digest(test)
    report = {"path": test.relative_to(root).as_posix(), "optimized": int(optimized),
              "test_sha256": before, "status": "error", "tests": 0}
    env = os.environ.copy()
    # Do not inherit an unrelated session's PYTHONPATH or optimization setting.
    env.pop("PYTHONOPTIMIZE", None)
    env.pop("PYTHONPATH", None)
    if pythonpaths:
        env["PYTHONPATH"] = os.pathsep.join(str(path) for path in pythonpaths)
    command = [sys.executable, "-B"] + (["-S"] if sys.flags.no_site else []) + (["-O"] if optimized else [])
    with tempfile.TemporaryDirectory(prefix="titan-component-") as directory:
        receipt = Path(directory) / "result.json"
        log = Path(directory) / "output.log"
        command += [str(Path(__file__).resolve()), "--child", str(test), "--result", str(receipt)]
        try:
            with log.open("wb") as output:
                proc = subprocess.run(command, cwd=root, env=env, stdout=output,
                                      stderr=subprocess.STDOUT, timeout=timeout, check=False)
            report["exit_code"] = proc.returncode
            if receipt.is_file():
                result = json.loads(receipt.read_text(encoding="utf-8"))
                if (not isinstance(result, dict) or result.get("schema") != SCHEMA
                        or result.get("test_sha256") != before
                        or type(result.get("optimized")) is not int
                        or result["optimized"] != int(optimized)
                        or type(result.get("tests")) is not int):
                    raise ValueError("child receipt identity/schema mismatch")
                report.update({key: result[key] for key in (
                    "status", "tests", "discovered", "failures", "errors", "skipped",
                    "expected_failures", "unexpected_successes", "reason") if key in result})
                if (proc.returncode != 0 or report["tests"] <= 0
                        or report.get("discovered") != report["tests"]
                        or any(report.get(key, 0) for key in ("failures", "errors", "skipped",
                                                            "expected_failures", "unexpected_successes"))):
                    report["status"] = "failed"
                if report["status"] not in ("passed", "failed", "error"):
                    raise ValueError("unknown child status")
            else:
                report["reason"] = "child produced no receipt"
        except subprocess.TimeoutExpired:
            report.update(status="timeout", reason=f"exceeded {timeout:g} seconds")
        except (OSError, ValueError, TypeError) as exc:
            report.update(status="error", reason=f"{type(exc).__name__}: {exc}")
        if log.exists():
            with log.open("rb") as output:
                output.seek(max(0, log.stat().st_size - 32768))
                report["output_tail"] = output.read().decode("utf-8", errors="replace")
        if not test.is_file() or digest(test) != before:
            report.update(status="failed", reason="test source changed during execution")
    return report


def run(root: Path, patterns: list[str], *, timeout: float = 120,
        pythonpaths: list[Path] | None = None, binds: list[Path] | None = None) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("root must be a directory")
    if not 0 < timeout < float("inf"):
        raise ValueError("timeout must be finite and positive")
    pythonpaths = [path.resolve(strict=True) for path in (pythonpaths or [])]
    binds = [path.resolve(strict=True) for path in (binds or [])]
    bound_before = {str(path): digest(path) for path in binds}
    tests = select_tests(root, patterns)
    unmatched = [pattern for pattern in patterns if not select_tests(root, [pattern])]
    runner_before = digest(Path(__file__))
    tests_before = {test.relative_to(root).as_posix(): digest(test) for test in tests}
    rows = [run_file(test, root=root, optimized=mode, timeout=timeout, pythonpaths=pythonpaths)
            for test in tests for mode in (False, True)]
    bound_after = {str(path): digest(path) if path.is_file() else None for path in binds}
    tests_after = {test.relative_to(root).as_posix(): digest(test) if test.is_file() else None
                   for test in tests}
    tests_unchanged = (tests_before == tests_after and
                       all(row["test_sha256"] == tests_before[row["path"]] for row in rows))
    runner_unchanged = digest(Path(__file__)) == runner_before
    passed = (bool(rows) and not unmatched and tests_unchanged and runner_unchanged
              and all(row["status"] == "passed" for row in rows) and bound_before == bound_after)
    return {"schema": SCHEMA, "status": "passed" if passed else "failed",
            "scope": "local component correctness only; no full-package or gameplay-strength claim",
            "provenance_scope": "runner, selected test files and explicit --bind inputs; not dependency closure",
            "runner_sha256": runner_before, "runner_unchanged": runner_unchanged,
            "test_inputs": tests_before, "test_inputs_unchanged": tests_unchanged,
            "unmatched_selectors": unmatched, "python": sys.version,
            "selected_files": len(tests), "runs": rows, "bound_inputs": bound_before,
            "bound_inputs_unchanged": bound_before == bound_after,
            "reason": ("no tests selected" if not tests else
                       "selectors matched no eligible tests" if unmatched else None)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--include", action="append", help="V4-root-relative glob; repeatable")
    parser.add_argument("--pythonpath", action="append", type=Path, default=[])
    parser.add_argument("--bind", action="append", type=Path, default=[])
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        if args.result is None:
            parser.error("--child requires --result")
        return child(args.child.resolve(), args.result)
    try:
        result = run(args.root, args.include or ["repairs/**/test_*.py", "research/**/test_*.py"],
                     timeout=args.timeout, pythonpaths=args.pythonpath, binds=args.bind)
    except (OSError, ValueError) as exc:
        result = {"schema": SCHEMA, "status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
