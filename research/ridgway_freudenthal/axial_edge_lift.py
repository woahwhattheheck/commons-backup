"""Protected interior axial-edge lifts on a four-cube Kuhn patch.

Construct all endpoint-zero degree-four/five divergence-edge targets, then remove
cell means with the accepted rectangular-grid quartic repair. All arithmetic is
rational. One interior class is covered; no complete census or global theorem.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import sys

try:
    from .p4_body_diagonal_lift import right_inverse
    from .p4_mean_repair import indices, gradients
    from .p4_grid_mean_repair import grid, repair as repair_means
    from .face_diagonal_transport import check_physical_operator, parameters, rational
except ImportError:
    from p4_body_diagonal_lift import right_inverse
    from p4_mean_repair import indices, gradients
    from p4_grid_mean_repair import grid, repair as repair_means
    from face_diagonal_transport import check_physical_operator, parameters, rational

SHAPE = (1, 2, 2)
LOW, HIGH = (0, 1, 1), (1, 1, 1)


def point(cell, alpha):
    return tuple(sum(alpha[i]*cell[i][j] for i in range(4)) for j in range(3))


def geometry(degree):
    cells = grid(SHAPE)[1]
    inside = lambda p: all(0 < p[j] < degree*SHAPE[j] for j in range(3))
    nodes = sorted({point(cell, alpha) for cell in cells for alpha in indices(degree)
                    if inside(point(cell, alpha))})
    lookup = {p: i for i, p in enumerate(nodes)}
    protected, targets, means = [], [], []
    betas = indices(degree-1)
    for cell_id, cell in enumerate(cells):
        grad, total = gradients(cell), {}
        incident = LOW in cell and HIGH in cell
        for beta in betas:
            row = {}
            for i in range(4):
                alpha = list(beta)
                alpha[i] += 1
                node = lookup.get(point(cell, alpha))
                if node is None:
                    continue
                for component in range(3):
                    column = 3*node+component
                    row[column] = row.get(column, 0)+degree*grad[i][component]
            row = {c: v for c, v in row.items() if v}
            for c, v in row.items():
                total[c] = total.get(c, 0)+v
            if sum(v > 0 for v in beta) > 2:
                continue
            if incident and beta[cell.index(LOW)] and beta[cell.index(HIGH)]:
                label = {"cell": cell_id, "beta": beta,
                         "high_endpoint_power": beta[cell.index(HIGH)]}
                targets.append((label, row))
            else:
                protected.append(row)
        means.append({c: F(v, len(betas)) for c, v in total.items() if v})
    targets.sort(key=lambda pair: (pair[0]["cell"], pair[0]["high_endpoint_power"]))
    return cells, nodes, protected, [r for _, r in targets], [l for l, _ in targets], means


def elevate_quartic(cells, nodes, coefficients, width):
    """Represent a matrix of continuous quartic fields in the quintic basis."""
    lookup = {p: i for i, p in enumerate(nodes)}
    elevated = [None]*(3*len(nodes))
    zero = [[F(0)]*width for _ in range(3)]
    for cell in cells:
        for alpha in indices(5):
            node = lookup.get(point(cell, alpha))
            if node is None:
                continue
            rows = [[F(0)]*width for _ in range(3)]
            for i in range(4):
                if not alpha[i]:
                    continue
                beta = list(alpha)
                beta[i] -= 1
                old = coefficients.get(point(cell, beta), zero)
                factor = F(alpha[i], 5)
                for component in range(3):
                    for column, value in enumerate(old[component]):
                        if value:
                            rows[component][column] += factor*value
            for component in range(3):
                index = 3*node+component
                if elevated[index] is not None and elevated[index] != rows[component]:
                    raise ArithmeticError("Quartic correction elevation broke shared-face continuity")
                elevated[index] = rows[component]
    if any(row is None for row in elevated):
        raise ArithmeticError("Quartic correction elevation omitted an interior node")
    return elevated


def construct_reference(degree=4):
    """Construct a full-target right inverse on [0,1] x [0,2]^2 over Q."""
    if type(degree) is not int or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    cells, nodes, protected, target_rows, labels, means = geometry(degree)
    width = len(target_rows)
    matrix, rank_protected, rank_combined = right_inverse(
        protected, target_rows, 3*len(nodes))
    raw_means = [[sum(v*matrix[c][j] for c, v in row.items())
                  for j in range(width)] for row in means]
    if any(sum(row[j] for row in raw_means) for j in range(width)):
        raise ArithmeticError("Raw zero-boundary lift has nonzero total divergence mean")

    # Assemble all quartic correction columns with the accepted grid solver.
    # It consumes the installed two-cube basis; there is no new mean elimination.
    quartic = {}
    repaired_columns, patch_applications = 0, 0
    for column in range(width):
        targets = [row[column] for row in raw_means]
        if not any(targets):
            continue
        correction = repair_means({"shape": list(SHAPE), "cell_means": targets})
        repaired_columns += 1
        patch_applications += sum(correction["patches_by_axis"].values())
        for node, vector in zip(correction["nodes_times_four"],
                                correction["velocity_coefficients"]):
            rows = quartic.setdefault(tuple(node), [[F(0)]*width for _ in range(3)])
            for component in range(3):
                rows[component][column] += F(vector[component])
    if degree == 4:
        lookup = {p: i for i, p in enumerate(nodes)}
        for node, rows in quartic.items():
            for component in range(3):
                for column, value in enumerate(rows[component]):
                    matrix[3*lookup[node]+component][column] -= value
    else:
        correction = elevate_quartic(cells, nodes, quartic, width)
        for row, values in enumerate(correction):
            for column, value in enumerate(values):
                matrix[row][column] -= value

    maximum_row_squared = max(sum(v*v for v in row) for row in matrix)
    result = {
        "schema": "freudenthal-axial-edge-lift/v1", "status": "CONSTRUCTED",
        "degree": degree, "shape": list(SHAPE), "cells": cells,
        "nodes_times_degree": nodes, "target_edge": [LOW, HIGH],
        "incident_cells": sorted({label["cell"] for label in labels}),
        "target_coordinates": labels, "target_coordinate_count": width,
        "source_dimension": width,
        "source_basis": [[int(i == j) for j in range(width)] for i in range(width)],
        "free_coordinate_indices": list(range(width)),
        "source_characterization": "all endpoint-zero target trace coordinates are independently realizable",
        "unknowns": len(matrix), "protected_rows": len(protected),
        "protected_rank": rank_protected, "combined_rank": rank_combined,
        "edge_rows": len(protected)+width, "zero_mean_rows": len(means),
        "basis_shape": [len(matrix), width],
        "basis": [[i, j, str(v)] for i, row in enumerate(matrix)
                  for j, v in enumerate(row) if v],
        "quartic_mean_repair_columns": repaired_columns,
        "quartic_mean_repair_patch_applications": patch_applications,
        "maximum_squared_coefficient_row_norm": str(maximum_row_squared),
        "h1_squared_bound_from_target_l2": str(288*degree*degree*maximum_row_squared)
    }
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def apply(operator, trace):
    if not isinstance(trace, list) or len(trace) != operator["target_coordinate_count"]:
        raise ValueError(f"trace must contain {operator['target_coordinate_count']} exact coefficients")
    values = [F(0)]*operator["unknowns"]
    target = [rational(v, "trace coefficient") for v in trace]
    for row, column, value in operator["basis"]:
        values[row] += F(value)*target[column]
    return [[str(v) for v in values[i:i+3]] for i in range(0, len(values), 3)]


def transport(operator, axis="x", origin=(0, 0, 0), scale=1):
    """Transport a constructed reference axial lift, preserving trace ordering."""
    permutation, origin, scale = parameters(axis, origin, scale)
    if (not isinstance(operator, dict)
            or operator.get("schema") != "freudenthal-axial-edge-lift/v1"
            or operator.get("status") != "CONSTRUCTED"):
        raise ValueError("operator must be a constructed reference axial-edge lift")
    degree = operator["degree"]

    def mapped(point, multiplier=1):
        values = [multiplier*v for v in origin]
        for old, new in enumerate(permutation):
            values[new] += scale*F(point[old])
        return [str(v) for v in values]

    shape = [0, 0, 0]
    for old, new in enumerate(permutation):
        shape[new] = operator["shape"][old]
    result = deepcopy(operator)
    result.pop("requested_trace", None)
    result.pop("velocity_coefficients", None)
    result.update({
        "schema": "freudenthal-axial-edge-transport/v1",
        "status": "TRANSPORTED_AND_CHECKED",
        "reference_schema": operator["schema"],
        "axis": axis, "reference_to_physical_component": list(permutation),
        "origin": [str(v) for v in origin], "scale": str(scale),
        "reference_shape": list(operator["shape"]), "shape": shape,
        "cells": [[mapped(point) for point in cell] for cell in operator["cells"]],
        "nodes_times_degree": [mapped(point, degree) for point in operator["nodes_times_degree"]],
        "target_edge": [mapped(point) for point in operator["target_edge"]],
        "basis": sorted([[3*(row//3)+permutation[row%3], column, str(scale*F(value))]
                         for row, column, value in operator["basis"]]),
        "reference_maximum_squared_coefficient_row_norm":
            operator["maximum_squared_coefficient_row_norm"],
        "maximum_squared_coefficient_row_norm":
            str(scale**2*F(operator["maximum_squared_coefficient_row_norm"])),
        "reference_h1_squared_bound_from_target_l2":
            operator["h1_squared_bound_from_target_l2"],
        "h1_squared_bound_from_target_l2":
            str(scale**3*F(operator["h1_squared_bound_from_target_l2"])),
        "coordinate_semantics":
            "cells and target_edge are physical; divide nodes_times_degree by degree; shape counts cubes per physical axis",
        "coefficient_semantics":
            "continuous vector Bernstein coefficients; omitted boundary coefficients are zero",
        "ordering_semantics":
            "reference cell, vertex, node and target trace order is inherited; vector components are permuted"
    })
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def construct(degree=4, axis="x", origin=(0, 0, 0), scale=1):
    """Construct the local lift in one requested coordinate orientation."""
    parameters(axis, origin, scale)
    return transport(construct_reference(degree), axis, origin, scale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    orientation = parser.add_mutually_exclusive_group()
    orientation.add_argument("--axis", choices=("x", "y", "z"), default="x")
    orientation.add_argument("--all-axes", action="store_true",
                             help="Reuse one reference construction for all three axial directions")
    parser.add_argument("--origin", default="0,0,0",
                        help="Comma-separated exact translation; use --origin=-2,1/3,0 for a negative first component")
    parser.add_argument("--scale", default="1", help="Positive exact rational isotropic scale")
    parser.add_argument("--trace", help="One comma-separated vector of all 12 or 18 exact target coefficients")
    parser.add_argument("--output", type=Path, help="Create a new JSON output file; default stdout")
    args = parser.parse_args()
    try:
        _, origin, scale = parameters(args.axis, args.origin.split(","), args.scale)
        trace = None if args.trace is None else args.trace.split(",")
        reference = construct_reference(args.degree)
        if trace is not None:
            apply(reference, trace)
        axes = ("x", "y", "z") if args.all_axes else (args.axis,)
        operators = {}
        for axis in axes:
            operator = transport(reference, axis, origin, scale)
            if trace is not None:
                operator["requested_trace"] = [str(rational(v, "trace coefficient")) for v in trace]
                operator["velocity_coefficients"] = apply(operator, trace)
            operators[axis] = operator
        result = ({"schema": "freudenthal-axial-edge-batch/v1",
                   "status": "TRANSPORTED_AND_CHECKED", "degree": args.degree,
                   "operators": operators} if args.all_axes else operators[args.axis])
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(data)
        else:
            print(data, end="")
        print(f"TRANSPORTED_AND_CHECKED: degree {args.degree}, axes {','.join(axes)}, "
              f"full target dimension {reference['target_coordinate_count']}, "
              f"{len(reference['basis'])} nonzero coefficients; exact physical residuals 0",
              file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        print(f"axial_edge_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
