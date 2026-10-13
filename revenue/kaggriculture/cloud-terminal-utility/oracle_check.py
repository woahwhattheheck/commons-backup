# SPDX-License-Identifier: Apache-2.0
"""Optional test-only SciPy comparison; production has no SciPy dependency."""
import argparse
from fractions import Fraction
import importlib.util
import itertools
import json
from pathlib import Path

from terminal_utility import build_table, solve_terminal


def run(solver_file):
    import scipy
    from scipy.optimize import linprog
    spec = importlib.util.spec_from_file_location("terminal_objective_existing_solver", solver_file)
    existing = importlib.util.module_from_spec(spec); spec.loader.exec_module(existing)
    constant_count = variable_count = 0
    largest_error = 0.0
    for flat in itertools.product((-1, 0, 1), repeat=6):
        rows = [list(flat[i:i+2]) for i in (0, 2, 4)]
        document = {"baseline": "base", "plan_ids": ["base", "a", "b"], "scenario_ids": ["x", "y"],
                    "receipts": [{"plan": p, "scenario": s, "own_cash": 100 + rows[i][j],
                                  "rival_cash": 100, "done": True}
                                 for i, p in enumerate(("base", "a", "b"))
                                 for j, s in enumerate(("x", "y"))]}
        table = build_table(document)
        result = solve_terminal(table, existing.solve_table)
        if rows[0][0] != rows[0][1]:
            assert result["status"] == "absolute_matrix_solver_needed"
            assert result["solver_called"] is False
            variable_count += 1
            continue
        lp = linprog([0, 0, 0, -1],
                     A_ub=[[-rows[i][j] for i in range(3)] + [1] for j in range(2)],
                     b_ub=[0, 0], A_eq=[[1, 1, 1, 0]], b_eq=[1],
                     bounds=[(0, None)]*3 + [(None, None)], method="highs")
        assert lp.success, lp.message
        exact = 2 * Fraction(result["worst_expected_win_points"]) - 1
        error = abs(float(exact) - float(lp.x[-1]))
        largest_error = max(largest_error, error)
        assert error < 1e-9, (rows, result, lp.x.tolist())
        constant_count += 1
    return {"constant_baseline_absolute_lp_comparisons": constant_count,
            "varying_baseline_interface_checks": variable_count,
            "largest_absolute_lp_difference": largest_error,
            "scipy_version": scipy.__version__, "production_scipy_dependency": False,
            "new_engine_transitions": 0, "new_full_games": 0}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--solver-file", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); result = run(a.solver_file)
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
