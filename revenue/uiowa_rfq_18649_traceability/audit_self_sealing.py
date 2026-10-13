#!/usr/bin/env python3
"""Find checks that have stopped checking, across every landed lane.

The defect class: an integrity check whose expected value is written by the
same run that verifies it. A manifest that rewrites its own sha256 to match
whatever the suite just produced is a hash that can never fail -- it reports
PASS whether or not the artefact drifted. Nothing shows up red, which is
exactly why these survive.

This is the cross-lane version of the rule the traceability bundle next door
enforces on itself: recording an expected value is a DELIBERATE act, never a
side effect of running the check (see README, "Nothing self-heals").

Method, in descending order of confidence:

  1. BEHAVIOURAL (high confidence). Copy a lane to a scratch directory, hash
     every file, run the lane's own test suite there, hash everything again.
     Any tracked file the suite rewrote is non-hermetic. If a rewritten file
     also carried digest-shaped values and those values CHANGED, the check is
     self-sealing.
  2. STATIC (advisory). Flag source that writes a computed digest back into a
     file it also reads as the expected value. A static hit is a place to
     look, not a verdict.

Nothing in the repository is modified: every lane is copied first and the copy
is what runs. Python 3 standard library only, no network.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules"}
DIGEST_RE = re.compile(r"\b[0-9a-f]{32,64}\b")
STATIC_PATTERNS = [
    (re.compile(r"\[[\"']sha256[\"']\]\s*=", re.I), "assigns into a sha256 field"),
    (re.compile(r"[\"']sha256[\"']\s*:\s*(hashlib|_?(sha|digest|file_sha))", re.I),
     "builds a manifest entry from a freshly computed digest"),
]


def snapshot(root):
    out = {}
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, fn)
            try:
                with open(full, "rb") as f:
                    body = f.read()
            except OSError:
                continue
            out[os.path.relpath(full, root)] = (hashlib.sha256(body).hexdigest(), body)
    return out


def digests_in(body):
    return set(DIGEST_RE.findall(body.decode("utf-8", "replace")))


# Capture unittest's result object rather than parsing console prose. The
# receipt lives outside the audited tree, so recording it is not a lane write.
# This measures cooperative local tests; it is not a sandbox or attestation
# against test code that deliberately forges its own execution evidence.
_UNITTEST_RUNNER = r"""
import json
import sys
import unittest

class ExecutionResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_test = None
        self.skipped_test_cases = 0
        self.skipped_case_events = 0
        self.active_case_skipped = False
        self.skipped_fixtures = 0
        self.skipped_subtests = 0
        self.passed_subtests = 0

    def startTest(self, test):
        self.active_test = test
        self.active_case_skipped = False
        super().startTest(test)

    def stopTest(self, test):
        try:
            super().stopTest(test)
        finally:
            self.active_test = None

    def addSkip(self, test, reason):
        # unittest records fixture and subtest skips alongside case skips.
        # Only a skip of the active case can be subtracted from testsRun.
        if test is self.active_test:
            self.skipped_case_events += 1
            if not self.active_case_skipped:
                self.skipped_test_cases += 1
                self.active_case_skipped = True
        elif self.active_test is None:
            self.skipped_fixtures += 1
        else:
            self.skipped_subtests += 1
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        if err is None:
            self.passed_subtests += 1
        super().addSubTest(test, subtest, err)

receipt_path, names = sys.argv[1], sys.argv[2:]
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
selected = suite.countTestCases()
result = unittest.TextTestRunner(verbosity=1, resultclass=ExecutionResult).run(suite)
receipt = {
    "selected": selected,
    "tests_run": result.testsRun,
    "skipped": len(result.skipped),
    "skipped_test_cases": result.skipped_test_cases,
    "skipped_case_events": result.skipped_case_events,
    "skipped_fixtures": result.skipped_fixtures,
    "skipped_subtests": result.skipped_subtests,
    "passed_subtests": result.passed_subtests,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "expected_failures": len(result.expectedFailures),
    "unexpected_successes": len(result.unexpectedSuccesses),
    "successful": result.wasSuccessful(),
    "optimization": sys.flags.optimize,
}
with open(receipt_path, "w", encoding="utf-8") as stream:
    json.dump(receipt, stream, sort_keys=True)
raise SystemExit(0 if result.wasSuccessful() else 1)
"""
_COUNT_FIELDS = ("selected", "tests_run", "skipped", "failures", "errors",
                 "expected_failures", "unexpected_successes",
                 "skipped_test_cases", "skipped_case_events", "skipped_fixtures", "skipped_subtests",
                 "passed_subtests")


def _read_execution_receipt(path, returncode):
    """Unknown or inconsistent measurements never establish clean coverage."""
    with open(path, encoding="utf-8") as stream:
        receipt = json.load(stream)
    if not isinstance(receipt, dict):
        raise ValueError("unittest receipt is not an object")
    for key in _COUNT_FIELDS + ("optimization",):
        value = receipt.get(key)
        if type(value) is not int or value < 0:
            raise ValueError("invalid unittest receipt field: " + key)
    if type(receipt.get("successful")) is not bool:
        raise ValueError("invalid unittest receipt field: successful")
    if receipt["optimization"] != sys.flags.optimize:
        raise ValueError("child optimization differs from the auditor")
    if receipt["skipped"] != sum(receipt[k] for k in
                                ("skipped_case_events", "skipped_fixtures", "skipped_subtests")):
        raise ValueError("skip event totals disagree")
    if receipt["skipped_case_events"] < receipt["skipped_test_cases"]:
        raise ValueError("fewer case skip events than skipped cases")
    if bool(receipt["skipped_case_events"]) != bool(receipt["skipped_test_cases"]):
        raise ValueError("case skip events and skipped cases disagree")
    if receipt["skipped_test_cases"] > receipt["tests_run"]:
        raise ValueError("skipped case count exceeds started cases")
    if not receipt["tests_run"] and (receipt["skipped_subtests"] or receipt["passed_subtests"]):
        raise ValueError("subtest events require a started case")
    failed = any(receipt[k] for k in ("failures", "errors", "unexpected_successes"))
    if receipt["successful"] != (not failed):
        raise ValueError("unittest success disagrees with measured failures")
    if returncode != (0 if receipt["successful"] else 1):
        raise ValueError("process exit disagrees with unittest receipt")
    return receipt


def run_suite(workdir, test_files, timeout):
    """Run tests in the copy, retaining measured coverage and actual process state."""
    mods = [os.path.splitext(os.path.basename(t))[0] for t in test_files]
    out = {"ran": False, "returncode": None, "summary": "", "timed_out": False,
           "execution": None, "state": "TEST_EXECUTION_UNKNOWN"}
    command = [sys.executable]
    if sys.flags.optimize:
        command.append("-" + "O" * sys.flags.optimize)
    # Do not let an environment mutation change the child optimization level.
    env = dict(os.environ, PYTHONOPTIMIZE=str(sys.flags.optimize),
               PYTHONDONTWRITEBYTECODE="1")
    try:
        with tempfile.TemporaryDirectory(prefix="unittest-receipt-") as tmp:
            path = os.path.join(tmp, "result.json")
            p = subprocess.run(command + ["-c", _UNITTEST_RUNNER, path] + mods,
                               cwd=workdir, capture_output=True, text=True,
                               errors="replace", timeout=timeout, env=env)
            out.update(ran=True, returncode=p.returncode)
            tail = (p.stderr or p.stdout).strip().splitlines()
            out["summary"] = tail[-1] if tail else "no console summary"
            try:
                execution = _read_execution_receipt(path, p.returncode)
            except (OSError, ValueError, TypeError) as exc:
                out["summary"] += " | execution evidence unavailable: " + str(exc)
                return out
            out["execution"] = execution
            if not execution["successful"]:
                out["state"] = "TESTS_NOT_GREEN"
            elif (execution["tests_run"] <= execution["skipped_test_cases"]
                  and not execution["passed_subtests"]):
                # Fixture/subtest events are not skipped test cases. Preserve
                # completed subtests even when their parent later skips.
                out["state"] = "NO_TESTS_EXECUTED"
            elif (execution["skipped"] or execution["expected_failures"]
                  or execution["tests_run"] != execution["selected"]):
                out["state"] = "PARTIAL_TEST_COVERAGE"
            else:
                out["state"] = "CLEAN"
            return out
    except subprocess.TimeoutExpired:
        out.update(ran=True, summary="TIMEOUT", timed_out=True)
    except Exception as exc:
        out["summary"] = "%s: %s" % (type(exc).__name__, exc)
    return out


def static_scan(root):
    hits = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                for pat, why in STATIC_PATTERNS:
                    if pat.search(line):
                        hits.append({"file": os.path.relpath(full, root), "line": i,
                                     "why": why, "text": line.strip()[:120]})
                        break
    return hits


def _restore(scratch, pristine, changed):
    """Put the tree back so the next lane starts from clean bytes."""
    for rel in changed:
        src, dst = os.path.join(pristine, rel), os.path.join(scratch, rel)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        elif os.path.exists(dst):
            os.remove(dst)


def audit_lane(scratch, pristine, lane_name, timeout):
    """Audit one lane inside a shared copy of the whole tree.

    Why a shared tree and not a lone directory: the first version of this tool
    copied each lane on its own, and reported uiowa_rfq_18649_acceptance_map as
    TESTS_NOT_GREEN with six failures. It was a false positive of my own
    making -- that suite reads ACCEPTANCE_EXHIBIT.md from a SIBLING lane, and
    isolating the lane deleted the file it was pointing at. A checker that
    manufactures failures is the same defect class as one that manufactures
    passes, so the isolation model had to change rather than the verdict.
    """
    lane = os.path.join(scratch, lane_name)
    groups = {}
    for dirpath, dirnames, files in os.walk(lane):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        # Tests under fixtures/ are DATA, not this lane's suite. The operator
        # handoff kit ships a minikit whose README says outright: "Status:
        # production ready. All checks green. That claim is false and is here
        # on purpose: the verifier must contradict a README that asserts a
        # component works." Reporting that fixture's intended failure as a
        # defect would be the tool inventing a finding.
        if "fixtures" in os.path.relpath(dirpath, lane).split(os.sep):
            continue
        for fn in sorted(files):
            if fn.startswith("test_") and fn.endswith(".py"):
                groups.setdefault(dirpath, []).append(os.path.join(dirpath, fn))
    result = {"lane": lane_name, "tests": sorted(os.path.basename(f)
                                                 for g in groups.values() for f in g),
              "mutated": [], "foreign_writes": [], "self_sealing": [],
              "static_hits": static_scan(lane), "suite": None, "verdict": "NO_TESTS"}
    if not groups:
        if result["static_hits"]:
            result["verdict"] = "NO_TESTS_STATIC_HIT"
        return result

    before = snapshot(scratch)
    summaries, runs = [], []
    for workdir in sorted(groups):
        out = run_suite(workdir, groups[workdir], timeout)
        out["directory"] = os.path.relpath(workdir, scratch)
        summaries.append("%s: %s" % (out["directory"], out["summary"]))
        runs.append(out)
    # None means no trustworthy process exit. Preserve it rather than turning
    # failure to launch into integer zero via a truthiness test.
    codes = [out["returncode"] for out in runs]
    worst = next((code for code in codes if code is not None and code != 0),
                 None if None in codes else 0)
    states = {out["state"] for out in runs}
    suite_state = next((state for state in
                       ("TESTS_NOT_GREEN", "TEST_EXECUTION_UNKNOWN")
                       if state in states), "CLEAN")
    if suite_state == "CLEAN" and states != {"CLEAN"}:
        suite_state = ("NO_TESTS_EXECUTED" if states == {"NO_TESTS_EXECUTED"}
                       else "PARTIAL_TEST_COVERAGE")
    result["suite"] = {"summary": " | ".join(summaries), "returncode": worst,
                       "state": suite_state, "runs": runs}
    after = snapshot(scratch)

    changed = []
    lane_prefix = lane_name + os.sep
    for rel in sorted(set(before) | set(after)):
        b, a = before.get(rel), after.get(rel)
        if b is not None and a is not None and b[0] == a[0]:
            continue
        changed.append(rel)
        change = "created" if b is None else ("deleted" if a is None else "rewritten")
        entry = {"file": rel, "change": change}
        if change == "rewritten":
            moved = digests_in(a[1]) - digests_in(b[1])
            if moved and digests_in(b[1]):
                # The file carried digest values and they changed: running the
                # check rewrote its own expected value.
                entry["digests_changed"] = sorted(moved)[:3]
                result["self_sealing"].append(entry)
        if not rel.startswith(lane_prefix):
            result["foreign_writes"].append(entry)
        result["mutated"].append(entry)

    _restore(scratch, pristine, changed)

    if result["self_sealing"]:
        result["verdict"] = "SELF_SEALING"
    elif result["foreign_writes"]:
        result["verdict"] = "WRITES_OUTSIDE_LANE"
    elif result["mutated"]:
        result["verdict"] = "NON_HERMETIC"
    else:
        result["verdict"] = suite_state
    return result


def audit_exit_code(results, require_clean=False):
    """Keep the original self-sealing-only exit policy unless explicitly opted in."""
    verdicts = {result["verdict"] for result in results}
    if not require_clean:
        return int("SELF_SEALING" in verdicts)
    if verdicts & {"SELF_SEALING", "WRITES_OUTSIDE_LANE", "NON_HERMETIC",
                   "TESTS_NOT_GREEN"}:
        return 1
    return 0 if results and verdicts == {"CLEAN"} else 2


def main(argv=None):
    description = (__doc__ or "Audit copied lane tests for self-sealing checks.")
    ap = argparse.ArgumentParser(description=description.splitlines()[0])
    ap.add_argument("root", help="directory holding the lanes")
    ap.add_argument("--prefix", default="uiowa_rfq_18649_")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--only", help="audit a single lane by directory name")
    ap.add_argument("--require-clean", action="store_true",
                    help="exit 0 only with complete CLEAN coverage; 1 for observed "
                         "defects, 2 for missing or incomplete execution evidence")
    args = ap.parse_args(argv)

    names = sorted(d for d in os.listdir(args.root)
                   if d.startswith(args.prefix)
                   and os.path.isdir(os.path.join(args.root, d)))
    if args.only and args.only not in names:
        ap.error("--only must name an existing lane matching --prefix")
    if args.timeout <= 0:
        ap.error("--timeout must be greater than zero")
    tmp = tempfile.mkdtemp(prefix="lane-audit-")
    try:
        # Two copies: one the suites run in, one pristine to restore from. The
        # repository itself is never touched.
        scratch, pristine = os.path.join(tmp, "run"), os.path.join(tmp, "pristine")
        for dest in (scratch, pristine):
            os.makedirs(dest)
            for n in names:
                shutil.copytree(os.path.join(args.root, n), os.path.join(dest, n))
        targets = [args.only] if args.only else names
        results = [audit_lane(scratch, pristine, n, args.timeout) for n in targets]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    exit_code = audit_exit_code(results, args.require_clean)
    if args.format == "json":
        print(json.dumps(results, indent=2, sort_keys=True))
        return exit_code

    order = {"SELF_SEALING": 0, "WRITES_OUTSIDE_LANE": 1, "NON_HERMETIC": 2,
             "TESTS_NOT_GREEN": 3, "TEST_EXECUTION_UNKNOWN": 4,
             "NO_TESTS_EXECUTED": 5, "PARTIAL_TEST_COVERAGE": 6,
             "NO_TESTS_STATIC_HIT": 7, "CLEAN": 8, "NO_TESTS": 9}
    print("audited %d lane(s) under %s\n" % (len(results), args.root))
    for r in sorted(results, key=lambda r: (order.get(r["verdict"], 9), r["lane"])):
        if r["verdict"] in ("CLEAN", "NO_TESTS"):
            continue
        print("%-22s %s" % (r["verdict"], r["lane"]))
        if r["suite"]:
            print("    suite: %s" % r["suite"]["summary"])
        for m in r["mutated"][:6]:
            extra = ""
            if "digests_changed" in m:
                extra = "   <- DIGEST REWRITTEN: %s..." % m["digests_changed"][0][:16]
            print("    %-10s %s%s" % (m["change"], m["file"], extra))
        if len(r["mutated"]) > 6:
            print("    ... and %d more" % (len(r["mutated"]) - 6))
        print()
    untested = sorted(r["lane"] for r in results if r["verdict"] == "NO_TESTS")
    if untested:
        print("NO_TESTS -- these lanes have no runnable suite, so nothing here")
        print("was verified behaviourally. That is a coverage gap, not a pass:")
        for lane in untested:
            print("    %s" % lane)
        print()
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("summary: " + "  ".join("%s=%d" % (k, counts[k]) for k in sorted(counts)))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
