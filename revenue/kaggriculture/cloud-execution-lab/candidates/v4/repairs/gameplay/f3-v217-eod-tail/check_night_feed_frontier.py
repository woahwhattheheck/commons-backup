#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute baseline tests and assertion-reject deliberately defective variants."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CHILD = '''
import io,json,unittest
import test_night_feed_frontier as t
suite=unittest.defaultTestLoader.loadTestsFromName(NAME)
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
print(json.dumps({"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
                 "skips":len(result.skipped),"failure_ids":[x.id() for x,_ in result.failures],
                 "interpreter_calls":0 if t.ENGINE is None else t.ENGINE.calls,
                 "log":stream.getvalue()}))
'''
MUTANTS = [
    ("default_on", "night_feed_frontier.py", "if enabled is not True:", "if False:", "test_opt_in_only"),
    ("steal_work", "night_feed_frontier.py", 'if any(unit(a, actor) != ["PASS"] for a in actions):', 'if False:', "test_later_real_work_is_not_stolen"),
    ("duplicate_feed", "night_feed_frontier.py", "covered = incumbent_feeds(positions, actions)", "covered = set()", "test_redundant_future_feed_is_excluded"),
    ("ignore_carried_budget", "night_feed_frontier.py", "min(wheat, max_targets, len(pool))", "min(max_targets, len(pool))", "test_cargo_bounds_target_count"),
    ("fake_final_reset", "night_feed_frontier.py", "not 0 <= step < 696", "not 0 <= step < 720", "test_final_day_has_no_reset_credit"),
    ("pass_instead_of_feed", "night_feed_frontier.py", 'commands.append(("FEED",))', 'commands.append(("PASS",))', "test_full_interpreter_reset_and_resource_cost"),
    ("ignore_actual_return", "night_feed_engine.py", 'if any(unit(a, proposal.actor) != ["PASS"] for a in actual):', 'if False:', "test_actual_suffix_drift_rejected_before_displacement"),
    ("feed_safe_animals", "night_feed_frontier.py", 'tile["consecutive_unfed"] >= 1', 'tile["consecutive_unfed"] >= 0', "test_unfed_but_not_endangered_is_not_a_rescue"),
]


def child(root: Path, name: str, env):
    flags = [] if __debug__ else ["-O"]
    result = subprocess.run([sys.executable, *flags, "-c", "NAME=" + repr(name) + "\n" + CHILD],
                            cwd=root, env=env, text=True, capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("test infrastructure failed: " + result.stderr)
    return json.loads(result.stdout)


def run(native_root: Path, output: Path):
    root = Path(__file__).resolve().parent
    env = dict(os.environ, TITAN_NATIVE_ROOT=str(native_root.resolve(strict=True)))
    baseline = child(root, "test_night_feed_frontier", env)
    if baseline["failures"] or baseline["errors"] or baseline["skips"]:
        raise AssertionError("unchanged source must pass without errors or skips")
    records = []
    for label, filename, old, new, test in MUTANTS:
        with tempfile.TemporaryDirectory(prefix="f3-semantic-control-") as td:
            target = Path(td)
            for source in ("night_feed_frontier.py", "night_feed_engine.py", "test_night_feed_frontier.py"):
                (target / source).write_bytes((root / source).read_bytes())
            path = target / filename
            text = path.read_text()
            if text.count(old) != 1:
                raise AssertionError(f"mutation anchor drift: {label}")
            path.write_text(text.replace(old, new, 1))
            record = child(target, "test_night_feed_frontier.PlannerTests." + test, env)
            record["variant"] = label
            record["assertion_rejected"] = record["tests"] == 1 and record["failures"] == 1 and record["errors"] == 0 and record["skips"] == 0
            if not record["assertion_rejected"]:
                raise AssertionError(f"semantic control did not fail behaviorally: {label}: {record}")
            records.append(record)
    receipt = {"mode": "normal" if __debug__ else "optimized", "baseline": baseline, "semantic_controls": records,
               "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob("*.py")}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"mode": receipt["mode"], "tests": baseline["tests"],
                      "interpreter_calls": baseline["interpreter_calls"], "assertion_rejected_variants": len(records)}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--native-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    run(a.native_root, a.output)
