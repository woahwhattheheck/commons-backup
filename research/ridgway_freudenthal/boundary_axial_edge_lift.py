"""Protected Dirichlet boundary axial-edge lifts in degrees four and five.

Reconstruct the full continuous source image, build a protected right inverse,
compose the accepted local mean repair, and transport the result to twelve
ordered tangent/normal face orientations. One boundary class, not a global
Scott-Vogelius stability theorem.
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
    from .face_diagonal_transport import check_physical_operator, rational
except ImportError:
    from p4_body_diagonal_lift import right_inverse
    from p4_mean_repair import geometry as quartic_geometry, indices, gradients
    from p5_body_diagonal_lift import geometry as quintic_geometry, elevate
    from face_diagonal_transport import check_physical_operator, rational

LOW, HIGH = (1, 0, 0), (1, 1, 0)
AXES = ("x", "y", "z")
ORIENTATIONS = tuple(f"{tangent}-{normal}-{side}"
                     for tangent in AXES for normal in AXES if tangent != normal
                     for side in ("lower", "upper"))


def point(cell, alpha):
    return tuple(sum(alpha[i]*cell[i][j] for i in range(4)) for j in range(3))


def source_characterization(cells, degree, labels):
    """Reconstruct the source star with only its z=0 velocity trace removed."""
    incident = sorted({label["cell"] for label in labels})
    if len(incident) != 3 or len(labels) != 3*(degree-2):
        raise ArithmeticError("Expected three incident boundary axial source cells")
    nodes = sorted({point(cells[c], alpha)
                    for c in incident for alpha in indices(degree)
                    if point(cells[c], alpha)[2] != 0})
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
                continue  # The omitted Bernstein coefficient lies on z=0.
            for component in range(3):
                column = 3*node+component
                row[column] = row.get(column, 0)+degree*grad[i][component]
        rows.append({c: v for c, v in row.items() if v})
    # This is the new source map, not a restricted patch map or a pressure guess.
    # The shared solver verifies every column of its exact source right inverse.
    _, _, rank = right_inverse([], rows, 3*len(nodes))
    recorded_rows = [
        {"cell": label["cell"], "beta": label["beta"],
         "high_endpoint_power": label["high_endpoint_power"],
         "terms": [{"node_times_degree": nodes[column//3],
                    "component": AXES[column % 3], "coefficient": str(value)}
                   for column, value in sorted(row.items())]}
        for label, row in zip(labels, rows)
    ]
    return len(nodes), rank, recorded_rows


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
    source_nodes, source_rank, source_rows = source_characterization(cells, degree, target_labels)
    width = len(target_rows)
    source_basis = [[int(i == j) for j in range(width)] for i in range(width)]
    matrix, rank_protected, rank_combined = right_inverse(
        protected, target_rows, 3*len(nodes), source_basis)
    raw_means = [[sum(v*matrix[c][j] for c, v in row.items())
                  for j in range(width)] for row in means]
    if any(sum(row[j] for row in raw_means) for j in range(width)):
        raise ArithmeticError("Raw zero-boundary lift has nonzero total divergence mean")

    # Reuse the accepted eleven-column basis without reconstructing its proof.
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
        "schema": "freudenthal-boundary-axial-edge-lift/v1", "status": "CONSTRUCTED",
        "degree": degree, "shape": [2, 1, 1], "cells": cells,
        "nodes_times_degree": nodes, "target_edge": [LOW, HIGH],
        "target_coordinates": target_labels,
        "incident_cells": sorted({label["cell"] for label in target_labels}),
        "dirichlet_face": {"axis": "z", "coordinate": "0", "interior_side": "positive"},
        "source_boundary_condition":
            "zero velocity on reference plane z=0; source-star outer boundaries otherwise unrestricted",
        "source_node_count": source_nodes, "source_unknowns": 3*source_nodes,
        "source_rank": source_rank, "source_dimension": width,
        "target_coordinate_count": width, "compatibility_relations": [],
        "reference_source_rows": source_rows,
        "source_identity_check": {
            "arithmetic": "exact rational", "source_rows": width, "basis_columns": width,
            "source_rank": source_rank, "right_inverse_residual_max": "0",
            "coordinate_semantics": "reference source-star rows with degree-scaled nodes"},
        "source_basis": source_basis, "free_coordinate_indices": list(range(width)),
        "unknowns": len(matrix), "protected_rows": len(protected),
        "protected_rank": rank_protected, "combined_rank": rank_combined,
        "edge_rows": len(edges), "zero_mean_rows": len(means),
        "raw_mean_columns_nonzero":
            sum(any(row[j] for row in raw_means) for j in range(width)),
        "mean_repair_basis_columns": 11, "basis_shape": [len(matrix), width],
        "basis": [[i, j, str(v)] for i, row in enumerate(matrix)
                  for j, v in enumerate(row) if v],
        "maximum_squared_coefficient_row_norm": str(maximum_row_squared),
        "h1_squared_bound_from_target_l2": str(144*degree*degree*maximum_row_squared)
    }
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def apply(operator, trace):
    if not isinstance(trace, list) or len(trace) != operator["target_coordinate_count"]:
        raise ValueError(f"trace must contain {operator['target_coordinate_count']} exact coefficients")
    target = [rational(v, "trace coefficient") for v in trace]
    values = [F(0)]*operator["unknowns"]
    for row, column, value in operator["basis"]:
        values[row] += F(value)*target[column]
    return [[str(v) for v in values[i:i+3]] for i in range(0, len(values), 3)]


def transform_parameters(tangent_axis, normal_axis, side, origin, scale):
    if tangent_axis not in AXES or normal_axis not in AXES or tangent_axis == normal_axis:
        raise ValueError("tangent_axis and normal_axis must be distinct members of x, y, z")
    if side not in ("lower", "upper"):
        raise ValueError("side must be lower or upper")
    if not isinstance(origin, (tuple, list)) or len(origin) != 3:
        raise ValueError("origin must contain three exact coordinates")
    origin = tuple(rational(v, "origin coordinate") for v in origin)
    scale = rational(scale, "scale")
    if scale <= 0:
        raise ValueError("scale must be positive")
    tangent, normal = AXES.index(tangent_axis), AXES.index(normal_axis)
    remaining = next(i for i in range(3) if i not in (tangent, normal))
    permutation = (remaining, tangent, normal)
    inversions = sum(permutation[i] > permutation[j] for i in range(3) for j in range(i+1, 3))
    parity = -1 if inversions % 2 else 1
    return permutation, parity, 1 if side == "lower" else -1, origin, scale


def transport(operator, tangent_axis="y", normal_axis="z", side="lower",
              origin=(0, 0, 0), scale=1):
    permutation, parity, sign, origin, scale = transform_parameters(
        tangent_axis, normal_axis, side, origin, scale)
    if (not isinstance(operator, dict)
            or operator.get("schema") != "freudenthal-boundary-axial-edge-lift/v1"
            or operator.get("status") != "CONSTRUCTED"):
        raise ValueError("operator must be a constructed reference boundary axial-edge lift")
    degree = operator["degree"]
    vertices = (0, 1, 2, 3) if sign*parity == 1 else (0, 2, 1, 3)

    def mapped(point, multiplier=1):
        values = [multiplier*v for v in origin]
        for old, new in enumerate(permutation):
            values[new] += sign*scale*F(point[old])
        return [str(v) for v in values]

    shape = [0, 0, 0]
    for old, new in enumerate(permutation):
        shape[new] = operator["shape"][old]
    result = deepcopy(operator)
    result.pop("requested_trace", None)
    result.pop("velocity_coefficients", None)
    result.update({
        "schema": "freudenthal-boundary-axial-edge-transport/v1",
        "status": "TRANSPORTED_AND_CHECKED", "reference_schema": operator["schema"],
        "orientation": f"{tangent_axis}-{normal_axis}-{side}",
        "tangent_axis": tangent_axis, "normal_axis": normal_axis, "side": side,
        "coordinate_sign": sign, "permutation_determinant": parity,
        "orthogonal_determinant": sign*parity,
        "reference_to_physical_component": list(permutation),
        "physical_vertex_to_reference_vertex": list(vertices),
        "origin": [str(v) for v in origin], "scale": str(scale),
        "reference_shape": list(operator["shape"]), "shape": shape,
        "cells": [[mapped(cell[i]) for i in vertices] for cell in operator["cells"]],
        "nodes_times_degree": [mapped(point, degree) for point in operator["nodes_times_degree"]],
        "target_edge": [mapped(point) for point in operator["target_edge"]],
        "target_coordinates": [{**label, "beta": [label["beta"][i] for i in vertices]}
                               for label in operator["target_coordinates"]],
        "dirichlet_face": {"axis": normal_axis, "coordinate": str(origin[AXES.index(normal_axis)]),
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
        "reference_h1_squared_bound_from_target_l2": operator["h1_squared_bound_from_target_l2"],
        "h1_squared_bound_from_target_l2": str(scale**3*F(operator["h1_squared_bound_from_target_l2"])),
        "coordinate_semantics":
            "cells and target_edge are physical; divide nodes_times_degree by degree; shape counts cubes",
        "coefficient_semantics":
            "continuous vector Bernstein coefficients; omitted boundary coefficients are zero",
        "ordering_semantics":
            "cell, node, target-row and ordered-edge-endpoint order is inherited; negative orientation relabels vertices and beta"
    })
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def construct(degree=4, tangent_axis="y", normal_axis="z", side="lower",
              origin=(0, 0, 0), scale=1):
    transform_parameters(tangent_axis, normal_axis, side, origin, scale)
    return transport(construct_reference(degree), tangent_axis, normal_axis, side, origin, scale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--orientation", choices=ORIENTATIONS, default="y-z-lower",
                           help="Tangent axis, normal axis, and face side")
    selection.add_argument("--all-orientations", action="store_true",
                           help="Reuse one reference construction for all twelve tangent/normal/side choices")
    parser.add_argument("--origin", default="0,0,0",
                        help="Exact translation triple; use --origin=-2,1/3,0 for a negative first coordinate")
    parser.add_argument("--scale", default="1", help="Positive exact rational isotropic scale")
    parser.add_argument("--trace", help="One comma-separated vector of six or nine exact coefficients")
    parser.add_argument("--output", type=Path, help="Create a new JSON output file; default stdout")
    args = parser.parse_args()
    try:
        tangent, normal, side = args.orientation.split("-")
        _, _, _, origin, scale = transform_parameters(
            tangent, normal, side, args.origin.split(","), args.scale)
        trace = None if args.trace is None else args.trace.split(",")
        reference = construct_reference(args.degree)
        if trace is not None:
            apply(reference, trace)
        selected = ORIENTATIONS if args.all_orientations else (args.orientation,)
        operators = {}
        for orientation in selected:
            tangent, normal, side = orientation.split("-")
            operator = transport(reference, tangent, normal, side, origin, scale)
            if trace is not None:
                operator["requested_trace"] = [str(rational(v, "trace coefficient")) for v in trace]
                operator["velocity_coefficients"] = apply(operator, trace)
            operators[orientation] = operator
        result = ({"schema": "freudenthal-boundary-axial-edge-batch/v1",
                   "status": "TRANSPORTED_AND_CHECKED", "degree": args.degree,
                   "operators": operators} if args.all_orientations else operators[args.orientation])
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(data)
        else:
            print(data, end="")
        print(f"TRANSPORTED_AND_CHECKED: degree {args.degree}, {len(selected)} orientations, "
              f"source dimension {reference['source_dimension']}, "
              f"{len(reference['basis'])} nonzero coefficients; exact physical residuals 0",
              file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        print(f"boundary_axial_edge_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
