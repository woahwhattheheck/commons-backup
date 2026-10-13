"""Protected box-edge lifts at two Dirichlet planes in degrees four and five.

The two-cell same-side source has full interior edge image. The one-cell
mixed-side source has zero image. Reconstruct both source maps, build their
protected zero-mean operators, and transport them to all twelve box edges.
This is a finite boundary classification, not a global stability theorem.
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
    from .boundary_axial_edge_lift import AXES, point, transform_parameters
except ImportError:
    from p4_body_diagonal_lift import right_inverse
    from p4_mean_repair import geometry as quartic_geometry, indices, gradients
    from p5_body_diagonal_lift import geometry as quintic_geometry, elevate
    from face_diagonal_transport import check_physical_operator, rational
    from boundary_axial_edge_lift import AXES, point, transform_parameters

SIDES = ("lower", "upper")
CLASSES = {
    "same": {"low": (0, 0, 0), "high": (0, 1, 0), "z": 0, "incident_count": 2},
    "mixed": {"low": (0, 0, 1), "high": (0, 1, 1), "z": 1, "incident_count": 1},
}
EDGE_SPECS = {}
for _tangent in AXES:
    _normals = [axis for axis in AXES if axis != _tangent]
    for _first in SIDES:
        for _second in SIDES:
            _name = f"{_tangent}-{_normals[0]}-{_first}-{_normals[1]}-{_second}"
            EDGE_SPECS[_name] = (_tangent, _first, _second)


def source_characterization(cells, degree, labels, edge_class):
    """Retain every source coefficient except those on either Dirichlet plane."""
    spec = CLASSES[edge_class]
    incident = sorted({label["cell"] for label in labels})
    if (len(incident) != spec["incident_count"]
            or len(labels) != spec["incident_count"]*(degree-2)):
        raise ArithmeticError("Unexpected box-edge source-star geometry")
    nodes = sorted({point(cells[c], alpha)
                    for c in incident for alpha in indices(degree)
                    if point(cells[c], alpha)[0] != 0
                    and point(cells[c], alpha)[2] != degree*spec["z"]})
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
                continue
            for component in range(3):
                column = 3*node+component
                row[column] = row.get(column, 0)+degree*grad[i][component]
        rows.append({column: value for column, value in row.items() if value})
    if edge_class == "same":
        _, _, rank = right_inverse([], rows, 3*len(nodes))
        basis = [[int(i == j) for j in range(len(rows))] for i in range(len(rows))]
        identity_kind = "full exact source right inverse"
    else:
        if any(rows):
            raise ArithmeticError("Mixed-side Dirichlet source rows are not identically zero")
        rank, basis = 0, [[] for _ in rows]
        identity_kind = "every source row is identically zero"
    recorded = [
        {"cell": label["cell"], "beta": label["beta"],
         "high_endpoint_power": label["high_endpoint_power"],
         "terms": [{"node_times_degree": nodes[column//3],
                    "component": AXES[column % 3], "coefficient": str(value)}
                   for column, value in sorted(row.items())]}
        for label, row in zip(labels, rows)
    ]
    return len(nodes), rank, basis, recorded, identity_kind


def construct_reference(degree=4, edge_class="same"):
    if type(degree) is not int or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    if not isinstance(edge_class, str) or edge_class not in CLASSES:
        raise ValueError("edge_class must be same or mixed")
    spec = CLASSES[edge_class]
    if degree == 4:
        cells, nodes, edges, means, labels = quartic_geometry()
        edges = [{c: 4*v for c, v in row.items()} for row in edges]
        means = [{c: F(v, 5) for c, v in row.items()} for row in means]
    else:
        cells, nodes, edges, means, labels = quintic_geometry()
    protected, targets = [], []
    low, high = spec["low"], spec["high"]
    for row, label in zip(edges, labels):
        cell, beta = cells[label["cell"]], label["beta"]
        if low in cell and high in cell and beta[cell.index(low)] and beta[cell.index(high)]:
            target = {**label, "high_endpoint_power": beta[cell.index(high)]}
            targets.append((target, row))
        else:
            protected.append(row)
    targets.sort(key=lambda pair: (pair[0]["cell"], pair[0]["high_endpoint_power"]))
    target_labels, target_rows = [x[0] for x in targets], [x[1] for x in targets]
    source_nodes, source_rank, source_basis, source_rows, identity_kind = source_characterization(
        cells, degree, target_labels, edge_class)
    width = len(source_basis[0])
    matrix, protected_rank, combined_rank = right_inverse(
        protected, target_rows, 3*len(nodes), source_basis)
    raw_means = [[sum(v*matrix[c][j] for c, v in row.items())
                  for j in range(width)] for row in means]
    if any(sum(row[j] for row in raw_means) for j in range(width)):
        raise ArithmeticError("Raw zero-boundary lift has nonzero total divergence mean")

    # A zero-dimensional source returns the zero operator without a mean solve
    # or degree elevation. The nonzero source reuses the accepted stored basis.
    if width:
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

    rho = max(sum(value*value for value in row) for row in matrix)
    target_count = len(target_rows)
    result = {
        "schema": "freudenthal-boundary-crease-edge-lift/v1", "status": "CONSTRUCTED",
        "degree": degree, "edge_class": edge_class, "shape": [2, 1, 1],
        "cells": cells, "nodes_times_degree": nodes, "target_edge": [low, high],
        "target_coordinates": target_labels,
        "incident_cells": sorted({label["cell"] for label in target_labels}),
        "dirichlet_faces": [
            {"axis": "x", "coordinate": "0", "interior_side": "positive"},
            {"axis": "z", "coordinate": str(spec["z"]),
             "interior_side": "positive" if spec["z"] == 0 else "negative"}],
        "source_boundary_condition":
            f"zero velocity on reference planes x=0 and z={spec['z']}; other source-star boundaries unrestricted",
        "source_node_count": source_nodes, "source_unknowns": 3*source_nodes,
        "source_rank": source_rank, "source_dimension": width,
        "target_coordinate_count": target_count,
        "source_basis": source_basis, "free_coordinate_indices": list(range(width)),
        "compatibility_relations":
            [] if width else [[int(i == j) for j in range(target_count)] for i in range(target_count)],
        "reference_source_rows": source_rows,
        "source_identity_check": {
            "arithmetic": "exact rational", "kind": identity_kind,
            "source_rows": target_count, "basis_columns": width,
            "source_rank": source_rank, "residual_max": "0",
            "coordinate_semantics": "reference source-star rows with degree-scaled nodes"},
        "unknowns": len(matrix), "protected_rows": len(protected),
        "protected_rank": protected_rank, "combined_rank": combined_rank,
        "edge_rows": len(edges), "zero_mean_rows": len(means),
        "raw_mean_columns_nonzero":
            sum(any(row[j] for row in raw_means) for j in range(width)),
        "mean_repair_basis_columns": 11 if width else 0,
        "basis_shape": [len(matrix), width],
        "basis": [[i, j, str(value)] for i, row in enumerate(matrix)
                  for j, value in enumerate(row) if value],
        "maximum_squared_coefficient_row_norm": str(rho),
        "h1_squared_bound_from_target_l2": str(144*degree*degree*rho)
    }
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def apply(operator, trace):
    if not isinstance(trace, list) or len(trace) != operator["target_coordinate_count"]:
        raise ValueError(f"trace must contain {operator['target_coordinate_count']} exact coefficients")
    target = [rational(value, "trace coefficient") for value in trace]
    if operator["source_dimension"] == 0 and any(target):
        raise ValueError("the mixed-side box edge admits only a zero divergence trace")
    values = [F(0)]*operator["unknowns"]
    for row, column, value in operator["basis"]:
        values[row] += F(value)*target[column]
    return [[str(value) for value in values[i:i+3]] for i in range(0, len(values), 3)]


def edge_parameters(tangent_axis, side_first, side_second, origin, scale):
    if tangent_axis not in AXES:
        raise ValueError("tangent_axis must be x, y or z")
    if side_first not in SIDES or side_second not in SIDES:
        raise ValueError("each Dirichlet side must be lower or upper")
    normals = tuple(axis for axis in AXES if axis != tangent_axis)
    permutation, parity, sign, origin, scale = transform_parameters(
        tangent_axis, normals[1], side_first, origin, scale)
    edge_class = "same" if side_first == side_second else "mixed"
    name = f"{tangent_axis}-{normals[0]}-{side_first}-{normals[1]}-{side_second}"
    return edge_class, normals, permutation, parity, sign, origin, scale, name


def transport(operator, tangent_axis="y", side_first="lower", side_second="lower",
              origin=(0, 0, 0), scale=1):
    edge_class, normals, permutation, parity, sign, origin, scale, name = edge_parameters(
        tangent_axis, side_first, side_second, origin, scale)
    if (not isinstance(operator, dict)
            or operator.get("schema") != "freudenthal-boundary-crease-edge-lift/v1"
            or operator.get("status") != "CONSTRUCTED"
            or operator.get("edge_class") != edge_class):
        raise ValueError("operator must be a constructed reference matching the requested same/mixed sides")
    degree = operator["degree"]
    vertices = (0, 1, 2, 3) if sign*parity == 1 else (0, 2, 1, 3)

    def mapped(point, multiplier=1):
        values = [multiplier*value for value in origin]
        for old, new in enumerate(permutation):
            values[new] += sign*scale*F(point[old])
        return [str(value) for value in values]

    faces = []
    for face in operator["dirichlet_faces"]:
        new_axis = permutation[AXES.index(face["axis"])]
        old_inside = 1 if face["interior_side"] == "positive" else -1
        faces.append({"axis": AXES[new_axis],
                      "coordinate": str(origin[new_axis]+sign*scale*F(face["coordinate"])),
                      "interior_side": "positive" if sign*old_inside == 1 else "negative"})
    shape = [0, 0, 0]
    for old, new in enumerate(permutation):
        shape[new] = operator["shape"][old]
    result = deepcopy(operator)
    result.pop("requested_trace", None)
    result.pop("velocity_coefficients", None)
    result.update({
        "schema": "freudenthal-boundary-crease-edge-transport/v1",
        "status": "TRANSPORTED_AND_CHECKED", "reference_schema": operator["schema"],
        "orientation": name, "tangent_axis": tangent_axis, "normal_axes": list(normals),
        "dirichlet_sides": [side_first, side_second],
        "coordinate_sign": sign, "permutation_determinant": parity,
        "orthogonal_determinant": sign*parity,
        "reference_to_physical_component": list(permutation),
        "physical_vertex_to_reference_vertex": list(vertices),
        "origin": [str(value) for value in origin], "scale": str(scale),
        "reference_shape": list(operator["shape"]), "shape": shape,
        "cells": [[mapped(cell[i]) for i in vertices] for cell in operator["cells"]],
        "nodes_times_degree": [mapped(point, degree) for point in operator["nodes_times_degree"]],
        "target_edge": [mapped(point) for point in operator["target_edge"]],
        "target_coordinates": [{**label, "beta": [label["beta"][i] for i in vertices]}
                               for label in operator["target_coordinates"]],
        "reference_dirichlet_faces": deepcopy(operator["dirichlet_faces"]),
        "dirichlet_faces": faces,
        "reference_source_boundary_condition": operator["source_boundary_condition"],
        "source_boundary_condition":
            "zero velocity on both specified physical Dirichlet faces; other source-star boundaries unrestricted",
        "basis": sorted([[3*(row//3)+permutation[row % 3], column, str(sign*scale*F(value))]
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


def construct(degree=4, tangent_axis="y", side_first="lower", side_second="lower",
              origin=(0, 0, 0), scale=1):
    edge_class, _, _, _, _, _, _, _ = edge_parameters(
        tangent_axis, side_first, side_second, origin, scale)
    return transport(construct_reference(degree, edge_class),
                     tangent_axis, side_first, side_second, origin, scale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--edge", choices=tuple(EDGE_SPECS), default="y-x-lower-z-lower",
                           help="Tangent axis followed by the two named Dirichlet face sides")
    selection.add_argument("--all-edges", action="store_true",
                           help="Construct each source class once and return all twelve box-edge orientations")
    parser.add_argument("--origin", default="0,0,0",
                        help="Exact translation triple; use --origin=-2,1/3,0 for a negative first coordinate")
    parser.add_argument("--scale", default="1", help="Positive exact rational isotropic scale")
    parser.add_argument("--trace", help="One comma-separated complete trace for a single selected edge")
    parser.add_argument("--same-trace", help="With --all-edges: complete trace for the same-side source class")
    parser.add_argument("--mixed-trace", help="With --all-edges: complete zero trace for the mixed-side source class")
    parser.add_argument("--output", type=Path, help="Create a new JSON output file; default stdout")
    args = parser.parse_args()
    try:
        tangent, first, second = EDGE_SPECS[args.edge]
        edge_class, _, _, _, _, origin, scale, _ = edge_parameters(
            tangent, first, second, args.origin.split(","), args.scale)
        if args.all_edges:
            if args.trace is not None:
                raise ValueError("use --same-trace and --mixed-trace with --all-edges")
            references = {name: construct_reference(args.degree, name) for name in CLASSES}
            traces = {"same": None if args.same_trace is None else args.same_trace.split(","),
                      "mixed": None if args.mixed_trace is None else args.mixed_trace.split(",")}
            selected = tuple(EDGE_SPECS)
        else:
            if args.same_trace is not None or args.mixed_trace is not None:
                raise ValueError("--same-trace and --mixed-trace require --all-edges")
            references = {edge_class: construct_reference(args.degree, edge_class)}
            traces = {edge_class: None if args.trace is None else args.trace.split(",")}
            selected = (args.edge,)
        for name, trace in traces.items():
            if trace is not None:
                apply(references[name], trace)
        operators = {}
        for name in selected:
            tangent, first, second = EDGE_SPECS[name]
            source_class = "same" if first == second else "mixed"
            operator = transport(references[source_class], tangent, first, second, origin, scale)
            trace = traces[source_class]
            if trace is not None:
                operator["requested_trace"] = [str(rational(value, "trace coefficient")) for value in trace]
                operator["velocity_coefficients"] = apply(operator, trace)
            operators[name] = operator
        result = ({"schema": "freudenthal-boundary-crease-edge-batch/v1",
                   "status": "TRANSPORTED_AND_CHECKED", "degree": args.degree,
                   "operators": operators} if args.all_edges else operators[args.edge])
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(data)
        else:
            print(data, end="")
        dimensions = ",".join(f"{name}:{operator['source_dimension']}"
                              for name, operator in references.items())
        print(f"TRANSPORTED_AND_CHECKED: degree {args.degree}, {len(selected)} box-edge orientations, "
              f"source dimensions {dimensions}; exact physical residuals 0", file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        print(f"boundary_crease_edge_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
