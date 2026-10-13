"""Construct an exact two-cube quartic divergence-mean repair, or an obstruction.

All arithmetic is rational. Coefficients are Bernstein coefficients, not point
values. The existing positive-volume Kuhn generator supplies the twelve cells.
This program does not certify a mesh-uniform inf-sup theorem.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import sys

try:
    from .kuhn import kuhn_tets
except ImportError:
    from kuhn import kuhn_tets


def indices(degree):
    return [(a, b, c, degree-a-b-c)
            for a in range(degree+1)
            for b in range(degree-a+1)
            for c in range(degree-a-b+1)]


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def gradients(tet):
    a = tet[0]
    u, v, w = [tuple(p[i]-a[i] for i in range(3)) for p in tet[1:]]
    det = sum(u[i]*cross(v, w)[i] for i in range(3))
    if det != 1:
        raise ValueError("Expected a positively oriented unit-volume-times-six cell")
    g = [cross(v, w), cross(w, u), cross(u, v)]
    return [tuple(-sum(q[i] for q in g) for i in range(3))] + g


def geometry():
    cells = [tuple((p[0]+shift, p[1], p[2]) for p in t)
             for shift in (0, 1) for t in kuhn_tets()]
    alphas, betas = indices(4), indices(3)
    point = lambda tet, alpha: tuple(sum(alpha[i]*tet[i][j] for i in range(4))
                                    for j in range(3))
    interior = lambda p: 0 < p[0] < 8 and 0 < p[1] < 4 and 0 < p[2] < 4
    nodes = sorted({point(t, a) for t in cells for a in alphas if interior(point(t, a))})
    node_id = {p: i for i, p in enumerate(nodes)}
    edge, means, row_names = [], [], []
    # Rows below encode one quarter of divergence and five times cell mean.
    # Degree-three coefficients average with weight 1/20 on every cell.
    for cell_id, tet in enumerate(cells):
        grad = gradients(tet)
        total = {}
        for beta in betas:
            row = {}
            for i in range(4):
                alpha = list(beta)
                alpha[i] += 1
                p = point(tet, alpha)
                if p not in node_id:
                    continue
                for component in range(3):
                    value = grad[i][component]
                    if value:
                        col = 3*node_id[p]+component
                        row[col] = row.get(col, 0)+value
            row = {c: v for c, v in row.items() if v}
            for col, value in row.items():
                total[col] = total.get(col, 0)+value
            if sum(v > 0 for v in beta) <= 2:
                edge.append(row)
                row_names.append({"cell": cell_id, "beta": beta})
        means.append({c: v for c, v in total.items() if v})
    return cells, nodes, edge, means, row_names


def exact_basis(edge, means, ncols):
    """Sparse rational elimination with row-combination provenance.

    Return a right inverse of all eleven elementary zero-sum mean targets,
    or one exact linear identity disproving that requested surjectivity.
    """
    rows = edge+means
    pivots = {}
    rank_edge = None
    for index, original in enumerate(rows):
        row = {c: F(v) for c, v in original.items()}
        rhs = [F(0)]*11
        if index >= len(edge):
            cell = index-len(edge)
            rhs = [F(5*(int(cell == j)-int(cell == 11))) for j in range(11)]
        combo = {index: F(1)}
        while row:
            p = min(row)
            if p not in pivots:
                factor = row[p]
                pivots[p] = ({c: v/factor for c, v in row.items()},
                             [v/factor for v in rhs],
                             {c: v/factor for c, v in combo.items()})
                break
            prev, target, provenance = pivots[p]
            factor = row[p]
            for c, v in prev.items():
                row[c] = row.get(c, F(0))-factor*v
                if not row[c]:
                    del row[c]
            rhs = [v-factor*t for v, t in zip(rhs, target)]
            for c, v in provenance.items():
                combo[c] = combo.get(c, F(0))-factor*v
                if not combo[c]:
                    del combo[c]
        if not row and any(rhs):
            return {"status": "OBSTRUCTION", "rank_edge": rank_edge,
                    "rank_so_far": len(pivots), "row_identity": combo,
                    "target_residual": rhs, "first_failed_cell": index-len(edge)}
        if index+1 == len(edge):
            rank_edge = len(pivots)
    coefficients = [[F(0)]*11 for _ in range(ncols)]
    for p in sorted(pivots, reverse=True):
        row, rhs, _ = pivots[p]
        coefficients[p] = [rhs[j]-sum(v*coefficients[c][j]
                                      for c, v in row.items() if c != p)
                           for j in range(11)]
    # Check the constructed mathematical object before returning it.
    for i, row in enumerate(rows):
        for j in range(11):
            expected = 0 if i < len(edge) else 5*(int(i-len(edge) == j)-int(i-len(edge) == 11))
            if sum(v*coefficients[c][j] for c, v in row.items()) != expected:
                raise ArithmeticError("Exact reconstructed operator identity failed")
    return {"status": "CONSTRUCTED", "rank_edge": rank_edge,
            "rank_combined": len(pivots), "coefficients": coefficients}


def construct():
    cells, nodes, edge, means, row_names = geometry()
    result = exact_basis(edge, means, 3*len(nodes))
    result.update({"schema": "freudenthal-p4-mean-repair/v1", "cells": cells,
                   "nodes_times_four": nodes, "edge_rows": len(edge),
                   "unknowns": 3*len(nodes), "mean_rows": len(means)})
    if result["status"] == "OBSTRUCTION":
        combination = result["row_identity"]
        if any(sum(combination.get(i, F(0))*row.get(c, 0)
                   for i, row in enumerate(edge+means)) for c in range(3*len(nodes))):
            raise ArithmeticError("Obstruction is not an exact left-kernel identity")
        result["row_identity"] = [{"index": i, "coefficient": str(v),
                                   "row": row_names[i] if i < len(edge)
                                   else {"mean_cell": i-len(edge)}}
                                  for i, v in sorted(combination.items())]
        result["target_residual"] = [str(v) for v in result["target_residual"]]
    else:
        matrix = result.pop("coefficients")
        result["basis"] = [[i, j, str(v)] for i, row in enumerate(matrix)
                           for j, v in enumerate(row) if v]
        result["basis_shape"] = [3*len(nodes), 11]
    return result


def apply(operator, means):
    if operator["status"] != "CONSTRUCTED":
        raise ValueError("A full mean right inverse does not exist for the reconstructed system")
    if len(means) != 12 or any(isinstance(m, bool) or not isinstance(m, (str, int, F)) for m in means):
        raise ValueError("Supply exactly twelve integers or exact rational strings")
    m = [F(v) for v in means]
    if sum(m):
        raise ValueError("Cell means must sum to zero")
    values = [F(0)]*operator["unknowns"]
    for i, j, value in operator["basis"]:
        values[i] += F(value)*m[j]
    return [[str(x) for x in values[3*i:3*i+3]] for i in range(len(operator["nodes_times_four"]))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--means", nargs=12, help="Twelve exact cell means; quoted fractions accepted")
    parser.add_argument("--output", type=Path, help="Create a new JSON output; otherwise print to stdout")
    args = parser.parse_args()
    try:
        result = construct()
        if args.means:
            result["requested_means"] = args.means
            if result["status"] == "CONSTRUCTED":
                result["velocity_coefficients"] = apply(result, args.means)
        text = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as out:
                out.write(text)
        else:
            print(text, end="")
        print(f"{result['status']}: {result['unknowns']} unknowns, {result['edge_rows']} edge rows", file=sys.stderr)
        return 0 if result["status"] == "CONSTRUCTED" else 2
    except (ValueError, ArithmeticError, OSError) as exc:
        print(f"p4_mean_repair: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
