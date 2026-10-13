#!/usr/bin/env python3
"""Run trusted local lane suites without treating a quiet process as a test pass.

Extends OP5-CONTROL's lane verifier (ceaebe3e65099b7df3f71ed2f06aea249003eb74).
Unittest discovery supplies structured counts; script execution remains available
but an unobserved test count is UNVERIFIED. This executes repository code, not a
sandbox, and does not establish the truth of an agent's or a customer's claims.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import glob
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

TEST_GLOBS = ("test_*.py", "*_test.py", "tests/test_*.py", "tests/*_test.py")
STATES = ("PASS", "FAIL", "UNVERIFIED", "SKIPPED", "NO-TESTS")
CHILD_SCHEMA = "commons-unittest-observation/v1"

# Use unittest's result object, not a text search for "Ran N tests". Whole-case
# skips and other skip events are separate: a subtest skip is not a skipped case.
_CHILD = r'''
import json, os, pathlib, sys, unittest
path, receipt = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, os.getcwd())
top = path.parent
while (top / "__init__.py").is_file() and top != pathlib.Path.cwd():
    top = top.parent
class ObservedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started_tests = {}
        self.whole_skips = set()
    def startTest(self, test):
        self.started_tests[id(test)] = test
        super().startTest(test)
    def addSkip(self, test, reason):
        if id(test) in self.started_tests:
            self.whole_skips.add(id(test))
        super().addSkip(test, reason)
loader = unittest.TestLoader()
suite = loader.discover(str(path.parent), pattern=path.name, top_level_dir=str(top))
discovered = suite.countTestCases()
result = unittest.TextTestRunner(verbosity=1, resultclass=ObservedResult).run(suite)
skipped = len(result.whole_skips)
receipt.write_text(json.dumps({
    "schema": "commons-unittest-observation/v1", "discovered": discovered,
    "ran": result.testsRun, "tests_skipped": skipped,
    "skip_events": len(result.skipped), "other_skip_events": len(result.skipped) - skipped,
    "tests_executed": result.testsRun - skipped,
    "failures": len(result.failures), "errors": len(result.errors),
    "expected_failures": len(result.expectedFailures),
    "unexpected_successes": len(result.unexpectedSuccesses),
    "successful": result.wasSuccessful()
}), encoding="utf-8")
raise SystemExit(0 if result.wasSuccessful() else 1)
'''


def find_lanes(root, pattern):
    return sorted(d for d in glob.glob(os.path.join(root, pattern)) if os.path.isdir(d))


def find_tests(lane):
    return sorted({p for pattern in TEST_GLOBS
                   for p in glob.glob(os.path.join(lane, pattern)) if os.path.isfile(p)})


def select_runner(path: Path) -> str:
    """Recognize imported TestCase aliases/local subclasses or load_tests hooks.

    Unknown frameworks still execute as scripts; their absence of observations
    is reported, not guessed. --runner unittest explicitly handles other layouts.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except (SyntaxError, UnicodeError, OSError):
        return "script"
    modules, cases = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names if a.name == "unittest")
        elif isinstance(node, ast.ImportFrom) and node.module == "unittest":
            cases.update(a.asname or a.name for a in node.names if a.name == "TestCase")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "load_tests":
            return "unittest"
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    for _ in range(len(classes) + 1):
        derived = {n.name for n in classes if any(
            isinstance(b, ast.Name) and b.id in cases or
            isinstance(b, ast.Attribute) and b.attr == "TestCase"
            and isinstance(b.value, ast.Name) and b.value.id in modules
            for b in n.bases)}
        if not derived - cases:
            break
        cases.update(derived)
    return "unittest" if any(n.name in cases for n in classes) else "script"


def _observation(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    fields = ("discovered", "ran", "tests_skipped", "skip_events", "other_skip_events",
              "tests_executed", "failures", "errors", "expected_failures", "unexpected_successes")
    if not isinstance(value, dict) or value.get("schema") != CHILD_SCHEMA:
        raise ValueError("missing unittest observation schema")
    if any(type(value.get(k)) is not int or value[k] < 0 for k in fields):
        raise ValueError("invalid unittest observation counts")
    if (type(value.get("successful")) is not bool
            or value["tests_skipped"] + value["tests_executed"] != value["ran"]
            or value["tests_skipped"] + value["other_skip_events"] != value["skip_events"]):
        raise ValueError("inconsistent unittest observation")
    return value


def _script_observation(output: str, returncode: int) -> dict:
    # Compatibility with existing direct unittest runners. Skipped text is not
    # convertible to whole-case counts: class and subtest skips use that too.
    matches = re.findall(r"^Ran (\d+) tests? in [^\r\n]+$", output, re.MULTILINE)
    clean_ok = re.search(r"^OK\s*$", output, re.MULTILINE) is not None
    if returncode != 0:
        argument_error = returncode == 2 and "usage:" in output and not matches
        return {"status": "UNVERIFIED" if argument_error else "FAIL", "ran": 0,
                "tests_executed": 0, "detail": "script requires a runner/arguments" if argument_error
                else "script exited unsuccessfully"}
    if len(matches) == 1 and clean_ok and int(matches[0]) > 0:
        return {"status": "PASS", "ran": int(matches[0]), "tests_executed": int(matches[0]),
                "detail": "script-reported unittest summary (not structured discovery)"}
    return {"status": "UNVERIFIED", "ran": 0, "tests_executed": 0,
            "detail": "exit zero without an unambiguous executed-test observation"}


def _run_one(lane: Path, path: Path, timeout: float, runner: str) -> dict:
    mode = select_runner(path) if runner == "auto" else runner
    started = time.perf_counter()
    detail = {"file": str(path.relative_to(lane)), "runner": mode, "not_a_test": False,
              "ran": 0, "tests_executed": 0, "tests_skipped": 0, "skip_events": 0,
              "other_skip_events": 0, "status": "FAIL", "returncode": None}
    interpreter = [sys.executable] + (["-" + "O" * sys.flags.optimize] if sys.flags.optimize else [])
    with tempfile.TemporaryDirectory(prefix="commons-lane-") as temporary, tempfile.TemporaryFile() as log:
        receipt = Path(temporary) / "result.json"
        command = interpreter + (["-c", _CHILD, str(path), str(receipt)] if mode == "unittest"
                                 else [str(path.relative_to(lane))])
        try:
            completed = subprocess.run(command, cwd=lane, stdout=log, stderr=subprocess.STDOUT,
                                       timeout=timeout, check=False)
            detail["returncode"] = completed.returncode
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 65536))
            output = log.read().decode("utf-8", errors="replace")
            detail["tail"] = output.strip().splitlines()[-1] if output.strip() else ""
            if mode == "script":
                detail.update(_script_observation(output, completed.returncode))
            else:
                observed = _observation(receipt)
                detail.update(observed)
                failed = (not observed["successful"] or completed.returncode != 0
                          or observed["failures"] or observed["errors"] or observed["unexpected_successes"])
                detail["status"] = ("FAIL" if failed else "PASS" if observed["tests_executed"]
                                    else "SKIPPED" if observed["skip_events"] else "NO-TESTS")
        except subprocess.TimeoutExpired:
            detail["tail"] = f"TIMEOUT after {timeout}s"
        except (OSError, ValueError, TypeError, KeyError) as exc:
            detail["tail"] = f"ERROR: {type(exc).__name__}: {exc}"
    detail["ok"] = detail["status"] == "PASS"
    detail["seconds"] = round(time.perf_counter() - started, 3)
    return detail


def run_tests(lane, timeout, runner="auto"):
    """Observe one lane. A skip or quiet script cannot produce a suite PASS."""
    if not math.isfinite(timeout) or timeout <= 0 or runner not in {"auto", "unittest", "script"}:
        raise ValueError("timeout must be finite and positive; runner must be auto, unittest or script")
    lane = Path(lane).resolve()
    details = [_run_one(lane, Path(p).absolute(), timeout, runner) for p in find_tests(str(lane))]
    statuses = {d["status"] for d in details}
    status = next((s for s in STATES if s in statuses and s in {"FAIL", "UNVERIFIED"}), None)
    status = status or ("PASS" if "PASS" in statuses else "SKIPPED" if "SKIPPED" in statuses else "NO-TESTS")
    return {"status": status, "tests": sum(d["ran"] for d in details),
            "tests_executed": sum(d["tests_executed"] for d in details),
            "tests_skipped": sum(d["tests_skipped"] for d in details),
            "skip_events": sum(d["skip_events"] for d in details),
            "skipped": sum(d["status"] == "SKIPPED" for d in details), "files": details}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root")
    ap.add_argument("--glob", default="revenue/uiowa_rfq_18649_*")
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--runner", choices=("auto", "unittest", "script"), default="auto")
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    if not Path(args.root).is_dir() or not math.isfinite(args.timeout) or args.timeout <= 0:
        ap.error("root must be an existing directory and timeout must be finite and positive")
    results = []
    for lane in find_lanes(args.root, args.glob):
        result = {**run_tests(lane, args.timeout, args.runner), "lane": os.path.basename(lane)}
        results.append(result)
        print(f"{result['status']:<11} {result['lane']:<52} {result['tests_executed']:>4} non-skipped results "
              f"({result['tests_skipped']} case skips, {result['skip_events']} skip events)")
        for item in result["files"]:
            if item["status"] != "PASS":
                print(f"  {item['file']}: {item['status']} {item.get('detail', item.get('tail', ''))}")
    counts = Counter(r["status"] for r in results)
    summary = {"lanes": len(results), **{s.lower().replace('-', '_'): counts[s] for s in STATES},
               "tests": sum(r["tests"] for r in results),
               "tests_executed": sum(r["tests_executed"] for r in results),
               "tests_skipped": sum(r["tests_skipped"] for r in results),
               "skip_events": sum(r["skip_events"] for r in results), "results": results}
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, sort_keys=True))
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    # No-tests and skips remain coverage findings, not code failures. Unknown
    # runner outcomes are non-conclusive (2); only actual failed runs return 1.
    return 1 if counts["FAIL"] else 2 if counts["UNVERIFIED"] or not results else 0


if __name__ == "__main__":
    raise SystemExit(main())
