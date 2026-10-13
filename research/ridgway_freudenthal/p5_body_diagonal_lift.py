"""Construct the exact mean-preserving quintic body-diagonal edge lift.

Degree-elevates the existing quartic mean correction; no replacement mean solver.
One local class on a fixed two-cube patch, not the full mesh-uniform theorem.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import sys

try:
    from .p4_body_diagonal_lift import raw_geometry, right_inverse
    from .p4_mean_repair import indices, gradients, geometry as quartic_geometry, construct as mean_operator
except ImportError:
    from p4_body_diagonal_lift import raw_geometry, right_inverse
    from p4_mean_repair import indices, gradients, geometry as quartic_geometry, construct as mean_operator


def geometry():
    cells = quartic_geometry()[0]
    point = lambda t, a: tuple(sum(a[i]*t[i][j] for i in range(4)) for j in range(3))
    inside = lambda p: 0 < p[0] < 10 and 0 < p[1] < 5 and 0 < p[2] < 5
    nodes = sorted({point(t, a) for t in cells for a in indices(5) if inside(point(t, a))})
    lookup = {p: i for i, p in enumerate(nodes)}
    edges, means, labels = [], [], []
    for cell_id, cell in enumerate(cells):
        grads, total = gradients(cell), {}
        for beta in indices(4):
            row = {}
            for i in range(4):
                alpha = list(beta)
                alpha[i] += 1
                p = point(cell, alpha)
                if p not in lookup:
                    continue
                for c in range(3):
                    col = 3*lookup[p]+c
                    row[col] = row.get(col, 0)+5*grads[i][c]
            row = {c: v for c, v in row.items() if v}
            for c, v in row.items():
                total[c] = total.get(c, 0)+v
            if sum(v > 0 for v in beta) <= 2:
                edges.append(row)
                labels.append({"cell": cell_id, "beta": beta})
        # The 35 degree-four Bernstein coefficients have equal mean weight 1/35.
        means.append({c: F(v, 35) for c, v in total.items() if v})
    return cells, nodes, edges, means, labels


def elevate(cells, nodes, quartic):
    """Elevate the eleven-column P4 correction to shared P5 coefficients exactly."""
    old_nodes = {tuple(p): i for i, p in enumerate(quartic["nodes_times_four"])}
    old = [[F(0)]*11 for _ in range(quartic["unknowns"])]
    for i, j, value in quartic["basis"]:
        old[i][j] = F(value)
    lookup = {p: i for i, p in enumerate(nodes)}
    elevated = [None]*(3*len(nodes))
    for cell in cells:
        for alpha in indices(5):
            node = tuple(sum(alpha[i]*cell[i][j] for i in range(4)) for j in range(3))
            if node not in lookup:
                continue
            for component in range(3):
                row = [F(0)]*11
                for i in range(4):
                    if not alpha[i]:
                        continue
                    beta = list(alpha)
                    beta[i] -= 1
                    old_node = tuple(sum(beta[n]*cell[n][j] for n in range(4)) for j in range(3))
                    if old_node in old_nodes:
                        values = old[3*old_nodes[old_node]+component]
                        for j in range(11):
                            row[j] += F(alpha[i], 5)*values[j]
                index = 3*lookup[node]+component
                if elevated[index] is not None and elevated[index] != row:
                    raise ArithmeticError("Degree elevation broke shared-face continuity")
                elevated[index] = row
    if any(row is None for row in elevated):
        raise ArithmeticError("Degree elevation omitted a quintic interior coefficient")
    return elevated


def construct(mean_repair=None):
    """Build the lift, optionally reusing a retained exact quartic mean repair."""
    _, raw_nodes, protected, target, labels = raw_geometry(5)
    raw, rank_protected, rank_combined = right_inverse(protected, target, 3*len(raw_nodes))
    cells, nodes, edges, means, edge_labels = geometry()
    lookup = {p: i for i, p in enumerate(nodes)}
    matrix = [[F(0)]*18 for _ in range(3*len(nodes))]
    for old, point in enumerate(raw_nodes):
        for component in range(3):
            matrix[3*lookup[point]+component] = list(raw[3*old+component])
    raw_means = [[sum(v*matrix[c][j] for c, v in row.items()) for j in range(18)] for row in means]
    if any(sum(row[j] for row in raw_means) for j in range(18)):
        raise ArithmeticError("Zero-boundary raw field has nonzero total mean")
    quartic = mean_operator() if mean_repair is None else mean_repair
    if (quartic["status"] != "CONSTRUCTED"
            or [tuple(tuple(p) for p in cell) for cell in quartic["cells"]] != cells):
        raise ArithmeticError("Incompatible quartic mean-repair operator")
    correction = elevate(cells, nodes, quartic)
    for i, row in enumerate(correction):
        for j in range(18):
            matrix[i][j] -= sum(v*raw_means[mean_index][j] for mean_index, v in enumerate(row) if v)
    label_to_target = {(x["cell"], tuple(x["beta"])): j for j, x in enumerate(labels)}
    for row, label in zip(edges, edge_labels):
        target_index = label_to_target.get((label["cell"], tuple(label["beta"])))
        for j in range(18):
            if sum(v*matrix[c][j] for c, v in row.items()) != int(j == target_index):
                raise ArithmeticError("Combined quintic edge reproduction/protection failed")
    if any(sum(v*matrix[c][j] for c, v in row.items()) for row in means for j in range(18)):
        raise ArithmeticError("Combined quintic zero-mean identity failed")
    maximum_row_squared_norm = max(sum(v*v for v in row) for row in matrix)
    return {"schema": "freudenthal-p5-body-diagonal-lift/v1", "status": "CONSTRUCTED",
            "cells": cells, "nodes_times_five": nodes, "target_coordinates": labels,
            "target_edge": [[0, 0, 0], [1, 1, 1]], "target_dimension": 18,
            "raw_unknowns": 3*len(raw_nodes), "raw_protected_rows": len(protected),
            "raw_protected_rank": rank_protected, "raw_combined_rank": rank_combined,
            "unknowns": len(matrix), "edge_rows": len(edges), "zero_mean_rows": len(means),
            "basis_shape": [len(matrix), 18],
            "basis": [[i, j, str(v)] for i, row in enumerate(matrix) for j, v in enumerate(row) if v],
            "h1_squared_bound_from_target_l2": str(2*3*25*6*4*maximum_row_squared_norm)}


def apply(operator, trace):
    if not isinstance(trace, list) or len(trace) != 18 or any(
            isinstance(v, bool) or not isinstance(v, (str, int, F)) for v in trace):
        raise ValueError("trace must contain eighteen integers or exact rational strings")
    values, target = [F(0)]*operator["unknowns"], [F(v) for v in trace]
    for i, j, coefficient in operator["basis"]:
        values[i] += F(coefficient)*target[j]
    return [[str(v) for v in values[i:i+3]] for i in range(0, len(values), 3)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", nargs=18, help="Cell-major interior quartic Bernstein edge coefficients, j=1,2,3")
    parser.add_argument("--output", type=Path, help="Create a new JSON file; default stdout")
    args = parser.parse_args()
    try:
        result = construct()
        if args.trace:
            result["requested_trace"] = args.trace
            result["velocity_coefficients"] = apply(result, args.trace)
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as out:
                out.write(data)
        else:
            print(data, end="")
        print(f"CONSTRUCTED: target dimension 18, {result['unknowns']} unknowns, "
              f"{len(result['basis'])} nonzero coefficients", file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        print(f"p5_body_diagonal_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
