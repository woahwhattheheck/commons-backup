"""Transport the protected face-diagonal lift to three Kuhn face orientations.

Exact rational translations and positive isotropic scales preserve the inherited
divergence trace coordinates. This covers one interior face-diagonal class,
not the complete Freudenthal census or a mesh-uniform stability theorem.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import sys

try:
    from .face_diagonal_lift import construct as reference_operator, apply
    from .p4_mean_repair import cross, indices
except ImportError:
    from face_diagonal_lift import construct as reference_operator, apply
    from p4_mean_repair import cross, indices

# Reference component i becomes physical component PERMUTATIONS[axis][i].
# These cyclic permutations have determinant +1 and preserve vertex ordering.
PERMUTATIONS = {"x": (0, 1, 2), "y": (1, 2, 0), "z": (2, 0, 1)}


def rational(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, str, F)):
        raise ValueError(f"{name} must be an integer or exact rational string")
    try:
        return F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{name} must be a finite exact rational") from exc


def parameters(normal_axis, origin, scale):
    if not isinstance(normal_axis, str) or normal_axis not in PERMUTATIONS:
        raise ValueError("normal_axis must be x, y or z")
    if not isinstance(origin, (tuple, list)) or len(origin) != 3:
        raise ValueError("origin must contain three exact coordinates")
    origin = tuple(rational(v, "origin coordinate") for v in origin)
    scale = rational(scale, "scale")
    if scale <= 0:
        raise ValueError("scale must be positive")
    return PERMUTATIONS[normal_axis], origin, scale


def physical_gradients(cell):
    """Barycentric gradients in physical coordinates, including volume scaling."""
    a = cell[0]
    u, v, w = [tuple(p[j]-a[j] for j in range(3)) for p in cell[1:]]
    determinant = sum(u[j]*cross(v, w)[j] for j in range(3))
    if determinant <= 0:
        raise ArithmeticError("Transported cell lost positive orientation")
    tail = [tuple(value/determinant for value in row)
            for row in (cross(v, w), cross(w, u), cross(u, v))]
    return [tuple(-sum(row[j] for row in tail) for j in range(3))]+tail


def check_physical_operator(operator):
    """Rebuild every physical divergence row for every returned basis column."""
    degree, width = operator["degree"], operator["source_dimension"]
    cells = [[tuple(F(v) for v in point) for point in cell]
             for cell in operator["cells"]]
    nodes = [tuple(F(v) for v in point) for point in operator["nodes_times_degree"]]
    lookup = {point: i for i, point in enumerate(nodes)}
    if len(lookup) != len(nodes) or 3*len(nodes) != operator["unknowns"]:
        raise ArithmeticError("Transported coefficient-node indexing is inconsistent")
    lower = [degree*min(p[j] for cell in cells for p in cell) for j in range(3)]
    upper = [degree*max(p[j] for cell in cells for p in cell) for j in range(3)]
    if any(not all(lower[j] < point[j] < upper[j] for j in range(3))
           for point in nodes):
        raise ArithmeticError("A transported velocity coefficient lies on the patch boundary")

    matrix = [[F(0)]*width for _ in range(operator["unknowns"])]
    for row, column, value in operator["basis"]:
        matrix[row][column] += F(value)
    targets = {(item["cell"], tuple(item["beta"])): i
               for i, item in enumerate(operator["target_coordinates"])}
    betas = indices(degree-1)
    edges, seen_targets, means = 0, set(), 0
    for cell_id, cell in enumerate(cells):
        gradients = physical_gradients(cell)
        total = [F(0)]*width
        for beta in betas:
            divergence = [F(0)]*width
            for i in range(4):
                alpha = list(beta)
                alpha[i] += 1
                point = tuple(sum(alpha[n]*cell[n][j] for n in range(4))
                              for j in range(3))
                node = lookup.get(point)
                if node is None:
                    continue  # Omitted boundary Bernstein coefficients are zero.
                for component in range(3):
                    factor = degree*gradients[i][component]
                    if not factor:
                        continue
                    for column, value in enumerate(matrix[3*node+component]):
                        if value:
                            divergence[column] += factor*value
            for column, value in enumerate(divergence):
                total[column] += value
            if sum(v > 0 for v in beta) <= 2:
                edges += 1
                label = (cell_id, tuple(beta))
                target = targets.get(label)
                if target is not None:
                    seen_targets.add(label)
                expected = operator["source_basis"][target] if target is not None else [0]*width
                if divergence != expected:
                    raise ArithmeticError(
                        f"Physical edge reproduction/protection failed in cell {cell_id}, beta {beta}")
        # Every degree-(k-1) Bernstein polynomial has the same cell average.
        if any(value/len(betas) for value in total):
            raise ArithmeticError(f"Physical divergence mean is nonzero in cell {cell_id}")
        means += 1
    if (edges != operator["edge_rows"] or means != operator["zero_mean_rows"]
            or seen_targets != set(targets)):
        raise ArithmeticError("Physical identity reconstruction omitted an expected row")
    return {"arithmetic": "exact rational", "basis_columns": width,
            "edge_rows": edges, "target_rows": len(seen_targets),
            "protected_rows": edges-len(seen_targets), "zero_mean_rows": means,
            "edge_residual_max": "0", "mean_residual_max": "0",
            "boundary_trace": "zero; all boundary velocity coefficients are omitted"}


def transport(operator, normal_axis="x", origin=(0, 0, 0), scale=1):
    """Transport an accepted reference construct(degree) result without mutating it."""
    permutation, origin, scale = parameters(normal_axis, origin, scale)
    if (not isinstance(operator, dict)
            or operator.get("schema") != "freudenthal-face-diagonal-lift/v1"
            or operator.get("status") != "CONSTRUCTED"
            or operator.get("degree") not in (4, 5)):
        raise ValueError("operator must be a constructed degree-four or degree-five reference lift")
    degree = operator["degree"]

    def mapped(point, coordinate_multiplier=1):
        result = [coordinate_multiplier*v for v in origin]
        for old, new in enumerate(permutation):
            result[new] += scale*F(point[old])
        return [str(v) for v in result]

    result = deepcopy(operator)
    # Application-specific fields from a saved reference CLI output are not a
    # transported application; this function always returns a reusable operator.
    result.pop("requested_trace", None)
    result.pop("velocity_coefficients", None)
    result.update({
        "schema": "freudenthal-face-diagonal-transport/v1",
        "status": "TRANSPORTED_AND_CHECKED",
        "reference_schema": operator["schema"],
        "normal_axis": normal_axis,
        "reference_to_physical_component": list(permutation),
        "origin": [str(v) for v in origin],
        "scale": str(scale),
        "cells": [[mapped(point) for point in cell] for cell in operator["cells"]],
        "nodes_times_degree": [mapped(point, degree) for point in operator["nodes_times_degree"]],
        "target_edge": [mapped(point) for point in operator["target_edge"]],
        "basis": sorted([[3*(row//3)+permutation[row%3], column, str(scale*F(value))]
                         for row, column, value in operator["basis"]]),
        "reference_h1_squared_bound_from_target_l2":
            operator["h1_squared_bound_from_target_l2"],
        "h1_squared_bound_from_target_l2":
            str(scale**3*F(operator["h1_squared_bound_from_target_l2"])),
        "coordinate_semantics":
            "cells and target_edge are physical coordinates; divide nodes_times_degree by degree",
        "coefficient_semantics":
            "continuous vector Bernstein coefficients; omitted boundary coefficients are zero",
        "ordering_semantics":
            "reference cell, vertex, node and trace order is inherited; vector components are permuted"
    })
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def construct(degree=4, normal_axis="x", origin=(0, 0, 0), scale=1):
    """Build one reference lift and return its requested physical transport."""
    # Reject invalid transform arguments before the exact reference solve.
    parameters(normal_axis, origin, scale)
    return transport(reference_operator(degree), normal_axis, origin, scale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    orientation = parser.add_mutually_exclusive_group()
    orientation.add_argument("--normal-axis", choices=tuple(PERMUTATIONS), default="x")
    orientation.add_argument("--all-axes", action="store_true",
                             help="Reuse one reference solve for all three coordinate orientations")
    parser.add_argument("--origin", default="0,0,0",
                        help="Comma-separated exact coordinates; use --origin=-2,1/3,0 for a negative first coordinate")
    parser.add_argument("--scale", default="1", help="Positive exact rational isotropic scale")
    parser.add_argument("--trace", help="One comma-separated compatible exact trace vector")
    parser.add_argument("--output", type=Path, help="Create a new JSON file; default stdout")
    args = parser.parse_args()
    try:
        origin = args.origin.split(",")
        _, origin, scale = parameters(args.normal_axis, origin, args.scale)
        trace = None if args.trace is None else args.trace.split(",")
        reference = reference_operator(args.degree)
        # Check input compatibility once before constructing any physical output.
        if trace is not None:
            apply(reference, trace)
        axes = tuple(PERMUTATIONS) if args.all_axes else (args.normal_axis,)
        operators = {}
        for axis in axes:
            operator = transport(reference, axis, origin, scale)
            if trace is not None:
                operator["requested_trace"] = [str(rational(v, "trace coefficient")) for v in trace]
                operator["velocity_coefficients"] = apply(operator, trace)
            operators[axis] = operator
        result = ({"schema": "freudenthal-face-diagonal-transport-batch/v1",
                   "status": "TRANSPORTED_AND_CHECKED", "degree": args.degree,
                   "operators": operators} if args.all_axes else operators[args.normal_axis])
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(data)
        else:
            print(data, end="")
        print(f"TRANSPORTED_AND_CHECKED: degree {args.degree}, axes {','.join(axes)}, "
              f"source dimension {reference['source_dimension']}; exact physical residuals 0",
              file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        print(f"face_diagonal_transport: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
