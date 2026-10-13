"""Protected Dirichlet boundary face-diagonal lifts in degrees four and five.

The source velocity vanishes on the boundary plane; its two incident divergence
traces must agree. Construct the exact protected lift, remove cell means with
the accepted local basis, and transport it to all six coordinate-face directions.
This is one boundary class, not a complete census or global stability theorem.
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
    from .p4_mean_repair import geometry as quartic_geometry, indices, gradients
    from .p5_body_diagonal_lift import geometry as quintic_geometry, elevate
    from .face_diagonal_transport import check_physical_operator, parameters, rational
except ImportError:
    from p4_body_diagonal_lift import right_inverse
    from p4_mean_repair import geometry as quartic_geometry, indices, gradients
    from p5_body_diagonal_lift import geometry as quintic_geometry, elevate
    from face_diagonal_transport import check_physical_operator, parameters, rational

LOW, HIGH = (0, 0, 0), (0, 1, 1)
FACES = tuple(f"{axis}-{side}" for axis in ("x", "y", "z")
              for side in ("lower", "upper"))


def point(cell, alpha):
    return tuple(sum(alpha[i]*cell[i][j] for i in range(4)) for j in range(3))


def dirichlet_source_identity(cells, degree, labels):
    """Reconstruct the source rows with only the plane x=0 velocity removed."""
    incident = sorted({label["cell"] for label in labels})
    modes = degree-2
    if len(incident) != 2 or len(labels) != 2*modes:
        raise ArithmeticError("Expected two incident Dirichlet-face source cells")
    nodes = sorted({point(cells[c], alpha) for c in incident for alpha in indices(degree)
                    if point(cells[c], alpha)[0] != 0})
    lookup = {p: i for i, p in enumerate(nodes)}
    rows = []
    for label in labels:
        cell, beta = cells[label["cell"]], label["beta"]
        grad, row = gradients(cell), {}
        for i in range(4):
            alpha = list(beta)
            alpha[i] += 1
            node = lookup.get(point(cell, alpha))
            if node is None:
                continue  # Dirichlet face Bernstein coefficients vanish.
            for component in range(3):
                column = 3*node+component
                row[column] = row.get(column, 0)+degree*grad[i][component]
        rows.append({c: v for c, v in row.items() if v})
    for mode in range(modes):
        if rows[mode] != rows[modes+mode]:
            raise ArithmeticError("Dirichlet source rows do not have the required trace equality")
    return 3*len(nodes)


def construct_reference(degree=4):
    if type(degree) is not int or degree not in (4, 5):
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
            target = {**label, "high_endpoint_power": beta[cell.index(HIGH)]}
            targets.append((target, row))
        else:
            protected.append(row)
    targets.sort(key=lambda pair: (pair[0]["cell"], pair[0]["high_endpoint_power"]))
    target_labels, target_rows = [x[0] for x in targets], [x[1] for x in targets]
    source_unknowns = dirichlet_source_identity(cells, degree, target_labels)
    width = degree-2
    source_basis = [[int(i % width == j) for j in range(width)] for i in range(2*width)]
    matrix, rank_protected, rank_combined = right_inverse(
        protected, target_rows, 3*len(nodes), source_basis)
    raw_means = [[sum(v*matrix[c][j] for c, v in row.items())
                  for j in range(width)] for row in means]
    if any(sum(row[j] for row in raw_means) for j in range(width)):
        raise ArithmeticError("Raw zero-boundary lift has nonzero total divergence mean")

    # Consume the existing exact eleven-column basis, without another mean solve.
    with Path(__file__).with_name("p4_mean_repair_basis.json").open(encoding="utf-8") as source:
        quartic = json.load(source)
    frozen_cells = lambda value: tuple(tuple(tuple(p) for p in cell) for cell in value)
    if (quartic.get("schema") != "freudenthal-p4-mean-repair/v1"
            or quartic.get("status") != "CONSTRUCTED"
            or frozen_cells(quartic["cells"]) != frozen_cells(cells)):
        raise ValueError("Installed mean-repair basis is incompatible with the reference patch")
    if degree == 4:
        if [tuple(p) for p in quartic["nodes_times_four"]] != nodes:
            raise ValueError("Installed mean-repair nodes use a different ordering")
        correction = [[F(0)]*11 for _ in range(len(matrix))]
        for row, column, value in quartic["basis"]:
            correction[row][column] = F(value)
    else:
        correction = elevate(cells, nodes, quartic)
    for row, values in enumerate(correction):
        for column in range(width):
            matrix[row][column] -= sum(value*raw_means[m][column]
                                       for m, value in enumerate(values) if value)
    maximum_row_squared = max(sum(v*v for v in row) for row in matrix)
    result = {
        "schema": "freudenthal-boundary-face-diagonal-lift/v1", "status": "CONSTRUCTED",
        "degree": degree, "cells": cells, "nodes_times_degree": nodes,
        "target_edge": [LOW, HIGH], "target_coordinates": target_labels,
        "incident_cells": sorted({label["cell"] for label in target_labels}),
        "dirichlet_face": {"axis": "x", "coordinate": "0", "interior_side": "positive"},
        "source_boundary_condition":
            "zero velocity on reference plane x=0; source-star outer boundaries otherwise unrestricted",
        "target_coordinate_count": len(target_rows), "source_dimension": width,
        "source_unknowns": source_unknowns, "equality_signs": [1, -1],
        "source_identity_rows": width, "source_basis": source_basis,
        "free_coordinate_indices": list(range(width)), "unknowns": len(matrix),
        "protected_rows": len(protected), "protected_rank": rank_protected,
        "combined_rank": rank_combined, "edge_rows": len(edges), "zero_mean_rows": len(means),
        "basis_shape": [len(matrix), width],
        "basis": [[i, j, str(v)] for i, row in enumerate(matrix)
                  for j, v in enumerate(row) if v],
        "maximum_squared_coefficient_row_norm": str(maximum_row_squared),
        "h1_squared_bound_from_free_l2": str(144*degree*degree*maximum_row_squared),
        # Compatible complete traces are [z,z], so their squared norm is 2|z|^2.
        "h1_squared_bound_from_target_l2": str(72*degree*degree*maximum_row_squared)
    }
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def apply(operator, trace):
    if not isinstance(trace, list) or len(trace) != operator["target_coordinate_count"]:
        raise ValueError(f"trace must contain {operator['target_coordinate_count']} exact coefficients")
    target = [rational(v, "trace coefficient") for v in trace]
    width = operator["source_dimension"]
    for mode in range(width):
        residual = target[mode]-target[width+mode]
        if residual:
            raise ValueError(f"incompatible Dirichlet source trace: mode {mode+1} has residual {residual}")
    values = [F(0)]*operator["unknowns"]
    for row, column, value in operator["basis"]:
        values[row] += F(value)*target[column]
    return [[str(v) for v in values[i:i+3]] for i in range(0, len(values), 3)]


def transform_parameters(normal_axis, side, origin, scale):
    permutation, origin, scale = parameters(normal_axis, origin, scale)
    if side not in ("lower", "upper"):
        raise ValueError("side must be lower or upper")
    return permutation, 1 if side == "lower" else -1, origin, scale


def transport(operator, normal_axis="x", side="lower", origin=(0, 0, 0), scale=1):
    permutation, sign, origin, scale = transform_parameters(normal_axis, side, origin, scale)
    if (not isinstance(operator, dict)
            or operator.get("schema") != "freudenthal-boundary-face-diagonal-lift/v1"
            or operator.get("status") != "CONSTRUCTED"):
        raise ValueError("operator must be a constructed reference boundary-face lift")
    degree = operator["degree"]
    # Full inversion preserves the underlying Kuhn triangulation. Its negative
    # determinant requires the same local relabelling of vertices and beta.
    vertices = (0, 1, 2, 3) if sign == 1 else (0, 2, 1, 3)

    def mapped(point, multiplier=1):
        values = [multiplier*v for v in origin]
        for old, new in enumerate(permutation):
            values[new] += sign*scale*F(point[old])
        return [str(v) for v in values]

    result = deepcopy(operator)
    result.pop("requested_trace", None)
    result.pop("velocity_coefficients", None)
    result.update({
        "schema": "freudenthal-boundary-face-diagonal-transport/v1",
        "status": "TRANSPORTED_AND_CHECKED",
        "reference_schema": operator["schema"],
        "normal_axis": normal_axis, "side": side, "coordinate_sign": sign,
        "reference_to_physical_component": list(permutation),
        "physical_vertex_to_reference_vertex": list(vertices),
        "origin": [str(v) for v in origin], "scale": str(scale),
        "cells": [[mapped(cell[i]) for i in vertices] for cell in operator["cells"]],
        "nodes_times_degree": [mapped(point, degree) for point in operator["nodes_times_degree"]],
        "target_edge": [mapped(point) for point in operator["target_edge"]],
        "target_coordinates": [{**label, "beta": [label["beta"][i] for i in vertices]}
                               for label in operator["target_coordinates"]],
        "dirichlet_face": {"axis": normal_axis, "coordinate": str(origin["xyz".index(normal_axis)]),
                           "interior_side": "positive" if sign == 1 else "negative"},
        "reference_source_boundary_condition": operator["source_boundary_condition"],
        "source_boundary_condition":
            "zero velocity on the specified physical Dirichlet face; other source-star boundaries unrestricted",
        "basis": sorted([[3*(row//3)+permutation[row%3], column, str(sign*scale*F(value))]
                         for row, column, value in operator["basis"]]),
        "reference_maximum_squared_coefficient_row_norm":
            operator["maximum_squared_coefficient_row_norm"],
        "maximum_squared_coefficient_row_norm":
            str(scale**2*F(operator["maximum_squared_coefficient_row_norm"])),
        "reference_h1_squared_bound_from_free_l2": operator["h1_squared_bound_from_free_l2"],
        "h1_squared_bound_from_free_l2": str(scale**3*F(operator["h1_squared_bound_from_free_l2"])),
        "reference_h1_squared_bound_from_target_l2": operator["h1_squared_bound_from_target_l2"],
        "h1_squared_bound_from_target_l2": str(scale**3*F(operator["h1_squared_bound_from_target_l2"])),
        "coordinate_semantics":
            "cells and target_edge are physical; divide nodes_times_degree by degree",
        "coefficient_semantics":
            "continuous vector Bernstein coefficients; omitted boundary coefficients are zero",
        "ordering_semantics":
            "cell, node, target-row and ordered-edge-endpoint order is inherited; upper faces relabel both vertices and beta"
    })
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def construct(degree=4, normal_axis="x", side="lower", origin=(0, 0, 0), scale=1):
    transform_parameters(normal_axis, side, origin, scale)
    return transport(construct_reference(degree), normal_axis, side, origin, scale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--face", choices=FACES, default="x-lower")
    selection.add_argument("--all-faces", action="store_true",
                           help="Reuse one reference construction for all six coordinate-face directions")
    parser.add_argument("--origin", default="0,0,0",
                        help="Exact translation triple; use --origin=-2,1/3,0 for a negative first coordinate")
    parser.add_argument("--scale", default="1", help="Positive exact rational isotropic scale")
    parser.add_argument("--trace", help="One comma-separated vector of four or six exact coefficients")
    parser.add_argument("--output", type=Path, help="Create a new JSON output file; default stdout")
    args = parser.parse_args()
    try:
        normal_axis, side = args.face.split("-")
        _, _, origin, scale = transform_parameters(normal_axis, side, args.origin.split(","), args.scale)
        trace = None if args.trace is None else args.trace.split(",")
        reference = construct_reference(args.degree)
        if trace is not None:
            apply(reference, trace)
        faces = FACES if args.all_faces else (args.face,)
        operators = {}
        for face in faces:
            axis, side = face.split("-")
            operator = transport(reference, axis, side, origin, scale)
            if trace is not None:
                operator["requested_trace"] = [str(rational(v, "trace coefficient")) for v in trace]
                operator["velocity_coefficients"] = apply(operator, trace)
            operators[face] = operator
        result = ({"schema": "freudenthal-boundary-face-diagonal-batch/v1",
                   "status": "TRANSPORTED_AND_CHECKED", "degree": args.degree,
                   "operators": operators} if args.all_faces else operators[args.face])
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(data)
        else:
            print(data, end="")
        print(f"TRANSPORTED_AND_CHECKED: degree {args.degree}, faces {','.join(faces)}, "
              f"source dimension {reference['source_dimension']}, "
              f"{len(reference['basis'])} nonzero coefficients; exact physical residuals 0",
              file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        print(f"boundary_face_diagonal_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
