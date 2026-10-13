# SPDX-License-Identifier: Apache-2.0
"""Reject four behavioral mutations using the independent component suite."""
import io
import json
import unittest

import test_exec_pace_recovery as checks


def main():
    raw = checks.members()["r04_exec_adaptive.py"]
    repaired = checks.repair(raw)
    mutants = {
        "original_duplicate_reset": raw,
        "duplicate_appends": repaired.replace(b"        if step == _last_step[0]:\n            return\n", b""),
        "backward_no_reset": repaired.replace(b"        if step < _last_step[0]:\n            _phist.clear()\n", b""),
        "threshold_changed": repaired.replace(b"SLOPE_THRESHOLD = 0.03", b"SLOPE_THRESHOLD = 0.05"),
    }
    names = [
        "test_predecessor_duplicate_falsifier", "test_duplicate_every_step_all_goods",
        "test_backward_step_reset_parity", "test_threshold_and_each_good",
    ]
    results = []
    original_repair = checks.repair
    try:
        for label, source in mutants.items():
            if source == repaired:
                raise RuntimeError("mutation did not change candidate")
            checks.repair = lambda unused, value=source: value
            suite = unittest.TestSuite(checks.Recovery(name) for name in names)
            output = io.StringIO()
            result = unittest.TextTestRunner(stream=output).run(suite)
            results.append({"mutation": label, "tests_run": result.testsRun,
                            "failures": len(result.failures), "errors": len(result.errors),
                            "rejected": bool(result.failures) and not result.errors})
    finally:
        checks.repair = original_repair
    print(json.dumps(results, indent=2))
    return 0 if all(row["rejected"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
