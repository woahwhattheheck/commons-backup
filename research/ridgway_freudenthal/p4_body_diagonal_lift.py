"""Exact protected quartic body-diagonal lift with zero tetrahedral cell means.

One six-tetrahedron Kuhn cube supplies the raw lift. The existing two-cube
operator removes means without changing any edge trace. This is one local class,
not the complete Freudenthal catalogue or a mesh-uniform global theorem.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import sys

try:
    from .kuhn import kuhn_tets
    from .p4_mean_repair import indices, gradients, geometry, construct as mean_operator
except ImportError:
    from kuhn import kuhn_tets
    from p4_mean_repair import indices, gradients, geometry, construct as mean_operator


def raw_geometry(degree=4):
    cells = kuhn_tets()
    point = lambda t, a: tuple(sum(a[i]*t[i][j] for i in range(4)) for j in range(3))
    nodes = sorted({point(t, a) for t in cells for a in indices(degree)
                    if all(0 < v < degree for v in point(t, a))})
    node_id = {p: i for i, p in enumerate(nodes)}
    protected, target, labels = [], [], []
    for cell_id, cell in enumerate(cells):
        grads = gradients(cell)
        low, high = cell.index((0, 0, 0)), cell.index((1, 1, 1))
        for beta in indices(degree-1):
            if sum(v > 0 for v in beta) > 2:
                continue
            row = {}
            for i in range(4):
                alpha = list(beta)
                alpha[i] += 1
                p = point(cell, alpha)
                if p not in node_id:
                    continue
                for component in range(3):
                    col = 3*node_id[p]+component
                    row[col] = row.get(col, 0)+degree*grads[i][component]
            row = {c: v for c, v in row.items() if v}
            if beta[low] and beta[high]:
                target.append(row)
                labels.append({"cell": cell_id, "beta": beta, "high_endpoint_power": beta[high]})
            else:
                protected.append(row)
    # Explicit public order: cell order, then high-endpoint power 1..degree-2.
    order = sorted(range(len(target)), key=lambda i: (labels[i]["cell"], labels[i]["high_endpoint_power"]))
    return cells, nodes, protected, [target[i] for i in order], [labels[i] for i in order]


def right_inverse(protected, target, ncols, target_basis=None):
    """Solve all target columns at once over Q; other edges stay zero."""
    if target_basis is None:
        target_basis = [[int(i == j) for j in range(len(target))] for i in range(len(target))]
    rows, width = protected+target, len(target_basis[0])
    pivots = {}
    protected_rank = None
    for index, original in enumerate(rows):
        row = {c: F(v) for c, v in original.items()}
        rhs = ([F(v) for v in target_basis[index-len(protected)]]
               if index >= len(protected) else [F(0)]*width)
        while row:
            p = min(row)
            if p not in pivots:
                factor = row[p]
                pivots[p] = ({c: v/factor for c, v in row.items()}, [v/factor for v in rhs])
                break
            previous, previous_rhs = pivots[p]
            factor = row[p]
            for c, v in previous.items():
                row[c] = row.get(c, F(0))-factor*v
                if not row[c]:
                    del row[c]
            rhs = [v-factor*w for v, w in zip(rhs, previous_rhs)]
        if not row and any(rhs):
            raise ArithmeticError(f"Requested target basis is not realizable at row {index}")
        if index+1 == len(protected):
            protected_rank = len(pivots)
    matrix = [[F(0)]*width for _ in range(ncols)]
    for p in sorted(pivots, reverse=True):
        row, rhs = pivots[p]
        matrix[p] = [rhs[j]-sum(v*matrix[c][j] for c, v in row.items() if c != p)
                     for j in range(width)]
    for index, row in enumerate(rows):
        for j in range(width):
            expected = target_basis[index-len(protected)][j] if index >= len(protected) else 0
            if sum(v*matrix[c][j] for c, v in row.items()) != expected:
                raise ArithmeticError("Constructed raw protected-map identity failed")
    return matrix, protected_rank, len(pivots)


def construct(mean_repair=None):
    """Build the lift, optionally reusing a retained exact mean-repair operator."""
    _, raw_nodes, protected, target, labels = raw_geometry()
    raw, rank_protected, rank_combined = right_inverse(protected, target, 3*len(raw_nodes))
    cells, nodes, edges, means, edge_labels = geometry()
    lookup = {tuple(p): i for i, p in enumerate(nodes)}
    matrix = [[F(0)]*12 for _ in range(3*len(nodes))]
    for old, point in enumerate(raw_nodes):
        for c in range(3):
            matrix[3*lookup[point]+c] = list(raw[3*old+c])
    raw_means = [[sum(v*matrix[c][j] for c, v in row.items())/5 for j in range(12)]
                 for row in means]
    if any(sum(row[j] for row in raw_means) for j in range(12)):
        raise ArithmeticError("Zero-boundary raw field has nonzero total divergence mean")
    # A retained operator follows the same composition path without another mean solve.
    correction = mean_operator() if mean_repair is None else mean_repair
    if (correction["status"] != "CONSTRUCTED"
            or [tuple(p) for p in correction["nodes_times_four"]] != nodes
            or [tuple(tuple(p) for p in cell) for cell in correction["cells"]] != cells):
        raise ArithmeticError("Incompatible two-cube mean-repair operator")
    for i, mean_index, coefficient in correction["basis"]:
        for j in range(12):
            matrix[i][j] -= F(coefficient)*raw_means[mean_index][j]
    label_to_target = {(x["cell"], tuple(x["beta"])): j for j, x in enumerate(labels)}
    # Verify the final combined polynomial field, not only the separate operators.
    for row, label in zip(edges, edge_labels):
        target_index = label_to_target.get((label["cell"], tuple(label["beta"])))
        for j in range(12):
            actual = 4*sum(v*matrix[c][j] for c, v in row.items())
            if actual != int(j == target_index):
                raise ArithmeticError("Combined-field edge reproduction/protection failed")
    if any(sum(v*matrix[c][j] for c, v in row.items()) for row in means for j in range(12)):
        raise ArithmeticError("Combined-field zero-mean identity failed")
    maximum_row_squared_norm = max(sum(v*v for v in row) for row in matrix)
    # Volume 2; three components; k^2=16; sum_i |grad(lambda_i)|^2=6;
    # four coefficients per derivative sum. Jensen + Cauchy-Schwarz.
    h1_bound = 2*3*16*6*4*maximum_row_squared_norm
    return {"schema": "freudenthal-p4-body-diagonal-lift/v1", "status": "CONSTRUCTED",
            "cells": cells, "nodes_times_four": nodes, "target_coordinates": labels,
            "target_edge": [[0, 0, 0], [1, 1, 1]], "target_dimension": 12,
            "raw_unknowns": 3*len(raw_nodes), "raw_protected_rows": len(protected),
            "raw_protected_rank": rank_protected, "raw_combined_rank": rank_combined,
            "unknowns": len(matrix), "edge_rows": len(edges), "zero_mean_rows": len(means),
            "basis_shape": [len(matrix), 12],
            "basis": [[i, j, str(v)] for i, row in enumerate(matrix) for j, v in enumerate(row) if v],
            "h1_squared_bound_from_target_l2": str(h1_bound)}


def apply(operator, trace):
    if not isinstance(trace, list) or len(trace) != 12 or any(
            isinstance(v, bool) or not isinstance(v, (str, int, F)) for v in trace):
        raise ValueError("trace must contain twelve integers or exact rational strings")
    target = [F(v) for v in trace]
    values = [F(0)]*operator["unknowns"]
    for i, j, coefficient in operator["basis"]:
        values[i] += F(coefficient)*target[j]
    return [[str(v) for v in values[i:i+3]] for i in range(0, len(values), 3)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", nargs=12, help="Cell-major interior cubic Bernstein edge coefficients, j=1,2")
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
        print(f"CONSTRUCTED: target dimension 12, {result['unknowns']} unknowns, "
              f"{len(result['basis'])} nonzero coefficients", file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        print(f"p4_body_diagonal_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
