# SPDX-License-Identifier: Apache-2.0
"""Reject deliberately inaccurate AFTERCARE oracle variants by assertions.

These are oracle/report/instrumentation defects, NOT SECONDHELP policy mutations.
Successful baseline required. Errors, skips and child infrastructure failures do
not count as mutation kills. The parent's normal/-O mode is kept in each child.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

FAULTS = {
    "care_replaced_by_pass": ('out["farmer"] = ["CARE"]', 'out["farmer"] = ["PASS"]'),
    "rewrite_productive_first_feed": ('out["hands"][0] = ["CARE"]', 'out["farmer"] = ["CARE"]'),
    "ignore_rival_cash": ('"delta_margin": delta_own-delta_rival', '"delta_margin": delta_own'),
    "suppress_real_unit_execution": ('result = original_unit(farm, private, idx, row, *args, **kwargs)', 'result = None'),
    "skip_reference_content_authentication": ('if not path.is_file() or git_blob(path.read_bytes()) != wanted:', 'if not path.is_file():'),
    "split_public_alias": ('return copy.deepcopy(self)', 'new = copy.deepcopy(self)\n        new.state[1].observation.farms = copy.deepcopy(new.state[0].observation.farms)\n        return new'),
    "invent_realized_sale": ('sold_products[world_index] += 1', 'sold_products[world_index] += 2'),
}
CHILD = r'''
import io,json,sys,unittest
import check_aftercare_engine
suite=unittest.defaultTestLoader.loadTestsFromModule(check_aftercare_engine)
buffer=io.StringIO()
r=unittest.TextTestRunner(stream=buffer,verbosity=2).run(suite)
print(json.dumps(dict(tests=r.testsRun, failures=len(r.failures), errors=len(r.errors),
                     skips=len(r.skipped), expected_failures=len(r.expectedFailures),
                     unexpected_successes=len(r.unexpectedSuccesses), log=buffer.getvalue())))
'''


def run(root: Path, output: Path, only: list[str] | None = None):
    source = (root / "aftercare_engine.py").read_text()
    test = (root / "check_aftercare_engine.py").read_text()
    modes = ["-O"] if sys.flags.optimize else []
    results = {}
    for name, patch in [("baseline", None), *((name, patch) for name, patch in FAULTS.items() if only is None or name in only)]:
        candidate = source
        if patch:
            old, new = patch
            if candidate.count(old) != 1:
                raise ValueError(f"Nonunique mutation anchor: {name}")
            candidate = candidate.replace(old, new)
        with tempfile.TemporaryDirectory(prefix="aftercare-fault-") as directory:
            path = Path(directory)
            (path / "aftercare_engine.py").write_text(candidate)
            (path / "check_aftercare_engine.py").write_text(test)
            process = subprocess.run([sys.executable, *modes, "-B", "-c", CHILD], cwd=path,
                                     text=True, capture_output=True, timeout=30)
            if process.returncode:
                raise RuntimeError(f"Child infrastructure failure {name}: {process.stderr}")
            result = json.loads(process.stdout)
            result["stderr"] = process.stderr
            if name == "baseline":
                valid = result["tests"] == 22 and all(result[k] == 0 for k in (
                    "failures", "errors", "skips", "expected_failures", "unexpected_successes"))
            else:
                valid = result["tests"] == 22 and result["failures"] > 0 and all(result[k] == 0 for k in (
                    "errors", "skips", "expected_failures", "unexpected_successes"))
            result["assertion_verified"] = valid
            results[name] = result
            print(f'{name}: {result["tests"]} tests, {result["failures"]} assertion failures, {result["errors"]} errors', flush=True)
            if not valid:
                output.write_text(json.dumps(results, indent=2)+"\n")
                raise RuntimeError(f"Invalid control outcome: {name}")
    output.write_text(json.dumps({"optimized": bool(sys.flags.optimize), "results": results}, indent=2)+"\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--only", nargs="+", choices=sorted(FAULTS))
    args = p.parse_args()
    run(Path(__file__).resolve().parent, args.output, args.only)
