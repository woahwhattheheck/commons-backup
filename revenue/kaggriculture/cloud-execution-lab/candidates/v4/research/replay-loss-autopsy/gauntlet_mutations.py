#!/usr/bin/env python3
"""Repeatable semantic negative controls for gauntlet_audit (no games run)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

# Each mutation removes one behavior, not syntax or imports. A kill requires an
# assertion failure with zero test errors, so import failures do not count.
MUTATIONS = [
    ("own_cash_only", '"delta_margin": own-rival', '"delta_margin": own',
     "test_paired_margin_not_own_bank_gain"),
    ("always_seat_zero", 'seat = cell["seat"]', 'seat = 0',
     "test_paired_margin_not_own_bank_gain"),
    ("duplicate_last_wins", 'require((cid, arm) not in games, f"duplicate result',
     'require(True, f"duplicate result', "test_duplicate_result_is_error_not_last_wins"),
    ("ignore_agent_identity", '== artifacts[arm],', 'is not None,',
     "test_source_and_coordinate_drift_rejected"),
    ("missing_counts_as_covered", '"coverage_complete": not missing and not failed,',
     '"coverage_complete": True,', "test_missing_row_blocks_coverage"),
    ("fallback_counts_as_clean", '"runtime_clean": not missing and not failed and not fallback,',
     '"runtime_clean": not missing and not failed,',
     "test_fallbacks_retained_in_economics_but_not_runtime_green"),
    ("pool_mirror", '(r for r in groups if r["kind"] != "mirror")',
     '(r for r in groups)', "test_summary_rank_not_three_losers"),
    ("leak_holdout_seed", 'require(not train & hold, "tuning/holdout seed overlap")',
     'require(True, "tuning/holdout seed overlap")', "test_cross_opponent_seed_leakage_rejected"),
    ("trust_declared_totals", 'integer(declared.get(key), key, 0) == value',
     'integer(declared.get(key), key, 0) >= 0', "test_summary_totals_must_reconcile"),
]
DRIVER = '''import json, sys, unittest
loader = unittest.TestLoader()
suite = loader.loadTestsFromName(sys.argv[1])
r = unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({"tests":r.testsRun,"failures":len(r.failures),"errors":len(r.errors),
"skips":len(r.skipped),"expected_failures":len(r.expectedFailures),
"unexpected_successes":len(r.unexpectedSuccesses)}))
'''


def run(source: bytes, tests: bytes, optimize: bool, selector: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="gauntlet-negative-") as folder:
        root = Path(folder)
        (root / "gauntlet_audit.py").write_bytes(source)
        (root / "test_gauntlet_audit.py").write_bytes(tests)
        command = [sys.executable] + (["-O"] if optimize else []) + ["-c", DRIVER, selector]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"test driver failure: {result.stderr}")
        counts = json.loads(result.stdout.splitlines()[-1])
        return {**counts, "stdout": result.stdout, "stderr": result.stderr}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source = (root / "gauntlet_audit.py").read_bytes()
    tests = (root / "test_gauntlet_audit.py").read_bytes()
    report = {"schema": "titan.gauntlet.negative-controls.v1", "scope": "synthetic analyzer contracts, not gameplay",
              "source_sha256": hashlib.sha256(source).hexdigest(),
              "tests_sha256": hashlib.sha256(tests).hexdigest(), "modes": []}
    all_ok = True
    for optimize in (False, True):
        control = run(source, tests, optimize, "test_gauntlet_audit")
        clean = (control["tests"] > 0 and all(control[k] == 0 for k in
                 ("failures", "errors", "skips", "expected_failures", "unexpected_successes")))
        mode = {"optimized": optimize, "control": control, "mutations": []}
        all_ok &= clean
        if clean:
            for name, old, new, test in MUTATIONS:
                decoded = source.decode("utf-8")
                if decoded.count(old) != 1:
                    raise RuntimeError(f"mutation {name} preimage not unique")
                changed = decoded.replace(old, new).encode("utf-8")
                result = run(changed, tests, optimize, "test_gauntlet_audit.AuditTests." + test)
                killed = (result["tests"] > 0 and result["failures"] > 0 and all(result[k] == 0 for k in
                          ("errors", "skips", "expected_failures", "unexpected_successes")))
                mode["mutations"].append({"name": name, "test": test, "killed": killed, **result})
                all_ok &= killed
        report["modes"].append(mode)
    report["passed"] = all_ok
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": all_ok, "modes": [{"optimized": r["optimized"],
          "control_tests": r["control"]["tests"], "killed": sum(m["killed"] for m in r["mutations"]),
          "total": len(r["mutations"])} for r in report["modes"]]}))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
