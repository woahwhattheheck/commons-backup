"""Exact protected interior face-diagonal lift on a fixed two-cube Kuhn patch.

Reconstructs the actual checkerboard source relation for degree four or five.
This is one local class, not the complete Freudenthal census or global theorem.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import sys

try:
    from .p4_body_diagonal_lift import right_inverse
    from .p4_mean_repair import geometry as quartic_geometry, indices, gradients, construct as mean_operator
    from .p5_body_diagonal_lift import geometry as quintic_geometry, elevate
except ImportError:
    from p4_body_diagonal_lift import right_inverse
    from p4_mean_repair import geometry as quartic_geometry, indices, gradients, construct as mean_operator
    from p5_body_diagonal_lift import geometry as quintic_geometry, elevate

LOW, HIGH = (1, 0, 0), (1, 1, 1)


def source_signs(cells, degree, target_labels):
    """Find a checkerboard identity on the full continuous source star.

    No outer boundary coefficients or source endpoint constraints are removed.
    Thus the identity remains necessary for every actual global source restriction.
    """
    incident = sorted({x["cell"] for x in target_labels})
    point = lambda cell, a: tuple(sum(a[i]*cell[i][j] for i in range(4)) for j in range(3))
    nodes = sorted({point(cells[c], a) for c in incident for a in indices(degree)})
    lookup = {p: i for i, p in enumerate(nodes)}
    rows = []
    for label in target_labels:
        cell, beta = cells[label["cell"]], label["beta"]
        grads, row = gradients(cell), {}
        for i in range(4):
            alpha = list(beta)
            alpha[i] += 1
            node = lookup[point(cell, alpha)]
            for component in range(3):
                col = 3*node+component
                row[col] = row.get(col, 0)+degree*grads[i][component]
        rows.append({c: v for c, v in row.items() if v})
    modes, matches = degree-2, []
    for remainder in product((-1, 1), repeat=3):
        signs = (1, *remainder)
        identities = []
        for j in range(modes):
            combination = {}
            for cell in range(4):
                for col, value in rows[cell*modes+j].items():
                    combination[col] = combination.get(col, 0)+signs[cell]*value
            identities.append(not any(combination.values()))
        if all(identities):
            matches.append(signs)
    if len(incident) != 4 or len(matches) != 1:
        raise ArithmeticError("Source geometry did not yield one checkerboard identity")
    return matches[0], len(nodes)*3


def construct(degree=4, mean_repair=None):
    if degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    if degree == 4:
        cells, nodes, edges, means, labels = quartic_geometry()
        edges = [{c: 4*v for c, v in row.items()} for row in edges]
        means = [{c: F(v, 5) for c, v in row.items()} for row in means]
    else:
        cells, nodes, edges, means, labels = quintic_geometry()
    protected, targets = [], []
    for row, label in zip(edges, labels):
        cell, beta = cells[label["cell"]], label["beta"]
        if LOW in cell and HIGH in cell and beta[cell.index(LOW)] and beta[cell.index(HIGH)]:
            targets.append((label["cell"], beta[cell.index(HIGH)], row, label))
        else:
            protected.append(row)
    targets.sort(key=lambda item: item[:2])
    target_rows = [x[2] for x in targets]
    target_labels = [{**x[3], "high_endpoint_power": x[1]} for x in targets]
    signs, source_unknowns = source_signs(cells, degree, target_labels)
    modes, dimension = degree-2, 3*(degree-2)
    # First three incident-cell traces are free; the fourth is fixed by H y = 0.
    basis = [[int(i == j) for j in range(dimension)] for i in range(4*modes)]
    for j in range(modes):
        for cell in range(3):
            basis[3*modes+j][cell*modes+j] = -signs[cell]*signs[3]
    matrix, rank_protected, rank_combined = right_inverse(protected, target_rows, 3*len(nodes), basis)
    raw_means = [[sum(v*matrix[c][j] for c, v in row.items()) for j in range(dimension)] for row in means]
    if any(sum(row[j] for row in raw_means) for j in range(dimension)):
        raise ArithmeticError("Raw zero-boundary field has nonzero total divergence mean")
    quartic = mean_operator() if mean_repair is None else mean_repair
    saved_cells = [tuple(tuple(point) for point in cell) for cell in quartic["cells"]]
    if quartic["status"] != "CONSTRUCTED" or saved_cells != cells:
        raise ArithmeticError("Incompatible local mean correction")
    if degree == 4:
        correction = [[F(0)]*11 for _ in range(3*len(nodes))]
        for i, j, value in quartic["basis"]:
            correction[i][j] = F(value)
    else:
        correction = elevate(cells, nodes, quartic)
    for i, row in enumerate(correction):
        for j in range(dimension):
            matrix[i][j] -= sum(v*raw_means[k][j] for k, v in enumerate(row) if v)
    targets_by_label = {(x["cell"], tuple(x["beta"])): i for i, x in enumerate(target_labels)}
    for row, label in zip(edges, labels):
        index = targets_by_label.get((label["cell"], tuple(label["beta"])))
        for j in range(dimension):
            expected = basis[index][j] if index is not None else 0
            if sum(v*matrix[c][j] for c, v in row.items()) != expected:
                raise ArithmeticError("Combined face-diagonal edge identity failed")
    if any(sum(v*matrix[c][j] for c, v in row.items()) for row in means for j in range(dimension)):
        raise ArithmeticError("Combined face-diagonal cell-mean identity failed")
    max_row_squared = max(sum(v*v for v in row) for row in matrix)
    return {"schema": "freudenthal-face-diagonal-lift/v1", "status": "CONSTRUCTED", "degree": degree,
            "cells": cells, "nodes_times_degree": nodes, "target_edge": [LOW, HIGH],
            "target_coordinates": target_labels, "target_coordinate_count": len(target_rows),
            "source_dimension": dimension, "source_unknowns": source_unknowns,
            "checkerboard_signs": signs, "free_coordinate_indices": list(range(dimension)),
            "source_basis": basis, "unknowns": len(matrix), "protected_rows": len(protected),
            "protected_rank": rank_protected, "combined_rank": rank_combined,
            "edge_rows": len(edges), "zero_mean_rows": len(means),
            "basis_shape": [len(matrix), dimension],
            "basis": [[i, j, str(v)] for i, row in enumerate(matrix) for j, v in enumerate(row) if v],
            "h1_squared_bound_from_target_l2": str(2*3*degree*degree*6*4*max_row_squared)}


def apply(operator, trace):
    if not isinstance(trace, list) or len(trace) != operator["target_coordinate_count"] or any(
            isinstance(v, bool) or not isinstance(v, (str, int, F)) for v in trace):
        raise ValueError(f"trace must contain {operator['target_coordinate_count']} exact integers/rational strings")
    target, modes = [F(v) for v in trace], operator["degree"]-2
    for j in range(modes):
        residual = sum(s*target[cell*modes+j] for cell, s in enumerate(operator["checkerboard_signs"]))
        if residual:
            raise ValueError(f"incompatible source trace: checkerboard mode {j+1} has residual {residual}")
    values = [F(0)]*operator["unknowns"]
    free = [target[i] for i in operator["free_coordinate_indices"]]
    for i, j, coefficient in operator["basis"]:
        values[i] += F(coefficient)*free[j]
    return [[str(v) for v in values[i:i+3]] for i in range(0, len(values), 3)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    parser.add_argument("--trace", nargs="+", help="Cell-major endpoint-zero Bernstein edge trace coefficients")
    parser.add_argument("--output", type=Path, help="Create a new JSON file; default stdout")
    args = parser.parse_args()
    try:
        result = construct(args.degree)
        if args.trace is not None:
            result["requested_trace"] = args.trace
            result["velocity_coefficients"] = apply(result, args.trace)
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as out:
                out.write(data)
        else:
            print(data, end="")
        print(f"CONSTRUCTED: degree {args.degree}, source dimension {result['source_dimension']}, "
              f"{len(result['basis'])} nonzero coefficients", file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        print(f"face_diagonal_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
