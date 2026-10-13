# SPDX-License-Identifier: MIT
"""Independent development-only LP cross-check; SciPy is not a runtime dependency."""
import argparse
import json
from pathlib import Path
import random

from linear_bounds import Constraint, Limits, solve, verify_certificate


def run():
    import scipy
    from scipy.optimize import linprog
    # This RNG generates algebraic test systems, not game/evaluation seeds.
    rng = random.Random(0)
    cases = []
    for index in range(160):
        n = 1 + index % 4
        a, b = [], []
        for axis in range(n):
            row = [0] * n
            row[axis] = 1
            a.extend([row, [-v for v in row]])
            b.extend([4, 0])
        for _ in range(6):
            a.append([rng.randint(-3, 3) for _ in range(n)])
            b.append(rng.randint(-5, 15))
        rows = [Constraint.make({f"x{j}": v for j, v in enumerate(row)}, bound, f"r{i}")
                for i, (row, bound) in enumerate(zip(a, b))]
        actual = solve(rows, Limits(seconds=2.0, max_rows=8192, max_combinations=32768))
        oracle = linprog([0] * n, A_ub=a, b_ub=b, bounds=[(None, None)] * n, method="highs")
        expected = {0: "possible", 2: "infeasible"}.get(oracle.status)
        if expected is None or actual.status != expected:
            raise AssertionError((index, actual.as_dict(), oracle.message))
        if actual.status == "infeasible" and not verify_certificate(rows, actual.certificate):
            raise AssertionError("Invalid exact rejection certificate")
        cases.append({"index": index, "a": a, "b": b,
                      "status": actual.status, "certificate": {k: str(v) for k, v in actual.certificate.items()}})
    return {"cases_checked": len(cases), "scipy_version": scipy.__version__,
            "agreement": len(cases), "possible": sum(c["status"] == "possible" for c in cases),
            "infeasible": sum(c["status"] == "infeasible" for c in cases),
            "cases": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    report = run()
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
