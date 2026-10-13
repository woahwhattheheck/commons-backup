"""Protected P4/P5 interior-vertex lifts on an eight-cube Kuhn patch.

The complete 24-cell vertex tuple has an exact 18-dimensional source image.
Compose its explicit first-derivative lift with the existing protected edge
operators and retained quartic grid mean repair. All arithmetic is rational.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import sys

try:
    from . import axial_edge_lift as axial
    from . import body_diagonal_transport as body
    from . import face_diagonal_lift as face
    from . import face_diagonal_transport as face_transport
    from .p4_grid_mean_repair import grid, repair as repair_means
    from .p4_mean_repair import indices, gradients
except ImportError:
    import axial_edge_lift as axial
    import body_diagonal_transport as body
    import face_diagonal_lift as face
    import face_diagonal_transport as face_transport
    from p4_grid_mean_repair import grid, repair as repair_means
    from p4_mean_repair import indices, gradients

SHAPE, CENTER = (2, 2, 2), (1, 1, 1)
STAR = (0, 1, 2, 3, 4, 5, 6, 8, 13, 16, 18, 19,
        27, 29, 32, 33, 40, 41, 42, 43, 44, 45, 46, 47)
FREE_CELLS = (0, 1, 2, 3, 4, 5, 6, 13, 18, 19, 27, 32, 33, 40, 41, 42, 43, 45)
# Each dependent q is the indicated combination of independent q values.
DEPENDENT = {
    8: ((4, -1), (5, 1), (6, 1)),
    16: ((2, -1), (3, 1), (13, 1)),
    29: ((0, -1), (1, 1), (27, 1)),
    44: ((40, -1), (41, 1), (42, 1)),
    46: ((32, -1), (33, 1), (43, 1)),
    47: ((18, -1), (19, 1), (45, 1)),
}
# Nonzero rows of the inverse of the determinant-minus-one vertex-jet minor.
# Entry (direction, component, terms) gives k*a_direction[component].
RAW_ROWS = (
    ((-1, -1, -1), 0, ((0, -1), (27, 1), (43, -1))),
    ((-1, -1, -1), 1, ((2, -1), (13, 1), (45, -1))),
    ((-1, -1, -1), 2, ((4, -1), (6, 1))),
    ((-1, -1, 0), 0, ((6, -1), (32, 1), (43, -1))),
    ((-1, -1, 0), 1, ((4, 1), (5, -1), (6, -1), (18, 1), (45, -1))),
    ((-1, 0, -1), 0, ((13, -1), (40, 1), (42, -1), (45, 1))),
    ((-1, 0, -1), 2, ((2, 1), (3, -1), (13, -1), (18, 1))),
    ((-1, 0, 0), 0, ((18, -1), (45, 1))),
    ((0, -1, -1), 1, ((27, -1), (40, 1), (42, -1), (43, 1))),
    ((0, -1, -1), 2, ((0, 1), (1, -1), (27, -1), (32, 1))),
    ((0, -1, 0), 1, ((32, -1), (43, 1))),
    ((0, 0, -1), 2, ((40, -1), (42, 1))),
    ((0, 0, 1), 0, ((32, 1), (33, -1), (43, -1))),
    ((0, 0, 1), 1, ((18, 1), (19, -1), (45, -1))),
    ((0, 1, 0), 0, ((40, 1), (41, -1), (42, -1), (45, 1))),
    ((0, 1, 0), 1, ((45, 1),)),
    ((1, 0, 0), 0, ((43, 1),)),
    ((1, 0, 0), 1, ((42, -1), (43, 1))),
)


def zero_rows(width):
    return [[F(0)]*width for _ in range(3)]


def point(cell, alpha):
    return tuple(sum(alpha[i]*cell[i][j] for i in range(4)) for j in range(3))


def source_basis():
    """Complete star values from the eighteen independent cell values."""
    free = {cell: i for i, cell in enumerate(FREE_CELLS)}
    result = []
    for cell in STAR:
        row = [0]*len(FREE_CELLS)
        for item, value in DEPENDENT.get(cell, ((cell, 1),)):
            row[free[item]] = value
        result.append(row)
    return result


def exact_values(values, count, name):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError(f"{name} must contain {count} exact integers/rational strings")
    return [face_transport.rational(value, name) for value in values]


def compatible_trace(values):
    target = exact_values(values, len(STAR), "trace")
    by_cell = dict(zip(STAR, target))
    for cell, terms in DEPENDENT.items():
        residual = by_cell[cell]-sum(sign*by_cell[other] for other, sign in terms)
        if residual:
            raise ValueError(f"incompatible vertex source trace at dependent cell {cell}: residual {residual}")
    return target


def trace_from_free(values):
    free = exact_values(values, len(FREE_CELLS), "free trace")
    return [sum(v*free[j] for j, v in enumerate(row)) for row in source_basis()]


def divergence_row(field, cell, beta, degree, width, grad=None):
    """One divergence Bernstein row, across every input-basis column."""
    grad = gradients(cell) if grad is None else grad
    result = [F(0)]*width
    for i in range(4):
        alpha = list(beta)
        alpha[i] += 1
        rows = field.get(point(cell, alpha))
        if rows is None:
            continue
        for component in range(3):
            factor = degree*grad[i][component]
            if factor:
                for j, value in enumerate(rows[component]):
                    if value:
                        result[j] += factor*value
    return result


def raw_vertex(degree, cells):
    width = len(FREE_CELLS)
    free = {cell: i for i, cell in enumerate(FREE_CELLS)}
    field = {}
    for direction, component, terms in RAW_ROWS:
        node = tuple(degree*CENTER[j]+direction[j] for j in range(3))
        rows = field.setdefault(node, zero_rows(width))
        for cell, sign in terms:
            rows[component][free[cell]] = F(sign, degree)
    expected = source_basis()
    for index, cell_id in enumerate(STAR):
        cell = cells[cell_id]
        beta = [0]*4
        beta[cell.index(CENTER)] = degree-1
        if divergence_row(field, cell, beta, degree, width) != expected[index]:
            raise ArithmeticError("Explicit vertex inverse does not reproduce its complete source basis")
    return field


def edge_operators(degree, mean_repair):
    """Place the six axial, six face-diagonal and two body-diagonal patches."""
    axial_reference = axial.construct_reference(degree)
    for axis_id, axis in enumerate("xyz"):
        for side in (-1, 1):
            origin = [0, 0, 0]
            origin[axis_id] = 1 if side > 0 else 0
            yield "axial", axial.transport(axial_reference, axis, origin)
    face_reference = face.construct(degree, mean_repair=mean_repair)
    for axis_id, axis in enumerate("xyz"):
        for side in (-1, 1):
            origin = [int(side > 0 and j != axis_id) for j in range(3)]
            yield "face_diagonal", face_transport.transport(face_reference, axis, origin)
    body_reference = body.reference_operator(degree)
    yield "body_diagonal", body.transport(body_reference, "+x", (0, 0, 0))
    yield "body_diagonal", body.transport(body_reference, "-x", (1, 1, 1))


def subtract_edge(field, raw, operator, degree, width, cell_ids):
    cells = [tuple(tuple(F(v) for v in p) for p in cell) for cell in operator["cells"]]
    if any(tuple(sorted(cell)) not in cell_ids for cell in cells):
        raise ArithmeticError("An edge correction patch leaves the eight-cube vertex patch")
    trace = [divergence_row(raw, cells[label["cell"]], label["beta"], degree, width)
             for label in operator["target_coordinates"]]
    free_indices = operator.get("free_coordinate_indices", range(operator["source_dimension"]))
    free = [trace[i] for i in free_indices]
    for expected, row in zip(trace, operator["source_basis"]):
        if expected != [sum(F(v)*free[i][j] for i, v in enumerate(row) if v)
                        for j in range(width)]:
            raise ArithmeticError("A raw vertex edge trace violates its exact edge source image")
    nodes = [tuple(F(v) for v in p) for p in operator["nodes_times_degree"]]
    for row, column, value in operator["basis"]:
        target = field.setdefault(nodes[row//3], zero_rows(width))[row % 3]
        factor = F(value)
        for j, coefficient in enumerate(free[column]):
            if coefficient:
                target[j] -= factor*coefficient
    return {
        "target_edge": operator["target_edge"],
        "incident_cells": sorted({cell_ids[tuple(sorted(cells[label["cell"]]))]
                                  for label in operator["target_coordinates"]}),
        "source_dimension": operator["source_dimension"],
        "target_coordinate_count": len(trace),
    }


def remove_means(cells, nodes, field, degree, width, shape=SHAPE):
    betas = indices(degree-1)
    means = []
    for cell in cells:
        grad, total = gradients(cell), [F(0)]*width
        for beta in betas:
            for j, value in enumerate(divergence_row(field, cell, beta, degree, width, grad)):
                total[j] += value
        means.append([value/len(betas) for value in total])
    if any(sum(row[j] for row in means) for j in range(width)):
        raise ArithmeticError("Zero-boundary vertex/edge composition has nonzero total divergence")
    quartic, repaired_columns, patches = {}, 0, 0
    for column in range(width):
        target = [row[column] for row in means]
        if not any(target):
            continue
        correction = repair_means({"shape": list(shape), "cell_means": [str(v) for v in target]})
        repaired_columns += 1
        patches += sum(correction["patches_by_axis"].values())
        for node, vector in zip(correction["nodes_times_four"], correction["velocity_coefficients"]):
            rows = quartic.setdefault(tuple(node), zero_rows(width))
            for component, value in enumerate(vector):
                rows[component][column] += F(value)
    if degree == 4:
        for node, rows in quartic.items():
            target = field.setdefault(node, zero_rows(width))
            for component in range(3):
                for j, value in enumerate(rows[component]):
                    target[component][j] -= value
    else:
        elevated = axial.elevate_quartic(cells, nodes, quartic, width)
        for node_id, node in enumerate(nodes):
            target = field.setdefault(node, zero_rows(width))
            for component in range(3):
                for j, value in enumerate(elevated[3*node_id+component]):
                    target[component][j] -= value
    return {"repaired_columns": repaired_columns, "two_cube_patch_applications": patches,
            "degree_elevated": degree == 5}


def construct_reference(degree=4):
    """Construct the protected vertex map on [0,2]^3 with center (1,1,1)."""
    if type(degree) is not int or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    cells, width = grid(SHAPE)[1], len(FREE_CELLS)
    if tuple(i for i, cell in enumerate(cells) if CENTER in cell) != STAR:
        raise ArithmeticError("Kuhn cell ordering differs from the explicit vertex source convention")
    neighbors = sorted({tuple(p[j]-CENTER[j] for j in range(3))
                        for cell_id in STAR for p in cells[cell_id] if p != CENTER})
    if len(neighbors) != 14:
        raise ArithmeticError("Interior vertex star must have fourteen incident edges")
    nodes = sorted({point(cell, alpha) for cell in cells for alpha in indices(degree)
                    if all(0 < value < 2*degree for value in point(cell, alpha))})
    cell_ids = {tuple(sorted(cell)): i for i, cell in enumerate(cells)}
    path = Path(__file__).with_name("p4_mean_repair_basis.json")
    data = path.read_bytes()
    mean_repair = json.loads(data)
    if (mean_repair.get("schema") != "freudenthal-p4-mean-repair/v1"
            or mean_repair.get("status") != "CONSTRUCTED"
            or mean_repair.get("basis_shape") != [189, 11]):
        raise ValueError("retained mean repair must be the constructed two-cube 189-by-11 operator")
    raw = raw_vertex(degree, cells)
    field = {node: [row[:] for row in rows] for node, rows in raw.items()}
    corrections = []
    seen_edges = set()
    for kind, operator in edge_operators(degree, mean_repair):
        edge = tuple(tuple(F(v) for v in p) for p in operator["target_edge"])
        if CENTER not in edge:
            raise ArithmeticError("Edge correction is not incident to the central vertex")
        other = edge[1] if edge[0] == CENTER else edge[0]
        direction = tuple(other[j]-CENTER[j] for j in range(3))
        if direction not in neighbors or direction in seen_edges:
            raise ArithmeticError("Vertex edge correction is duplicated or outside the source star")
        seen_edges.add(direction)
        corrections.append({"kind": kind, **subtract_edge(field, raw, operator, degree, width, cell_ids)})
    if seen_edges != set(neighbors):
        raise ArithmeticError("Vertex composition omitted an incident edge")
    mean_info = remove_means(cells, nodes, field, degree, width)
    lookup = {node: i for i, node in enumerate(nodes)}
    if any(node not in lookup and any(any(row) for row in rows) for node, rows in field.items()):
        raise ArithmeticError("Vertex composition produced a coefficient outside its interior node set")
    sparse, maximum = [], F(0)
    for node in nodes:
        for component, row in enumerate(field.get(node, zero_rows(width))):
            maximum = max(maximum, sum(value*value for value in row))
            sparse.extend([3*lookup[node]+component, j, str(value)]
                          for j, value in enumerate(row) if value)
    labels = []
    for cell_id in STAR:
        beta = [0]*4
        beta[cells[cell_id].index(CENTER)] = degree-1
        labels.append({"cell": cell_id, "beta": beta})
    result = {
        "schema": "freudenthal-interior-vertex-lift/v1", "status": "CONSTRUCTED",
        "degree": degree, "shape": list(SHAPE), "cells": cells,
        "target_vertex": CENTER, "incident_cells": list(STAR),
        "incident_edge_directions": neighbors, "target_coordinates": labels,
        "target_coordinate_count": len(STAR), "source_dimension": width,
        "source_basis": source_basis(),
        "source_relations": [{"dependent_cell": cell, "terms": list(terms)}
                             for cell, terms in DEPENDENT.items()],
        "free_cell_ids": list(FREE_CELLS),
        "free_coordinate_indices": [STAR.index(cell) for cell in FREE_CELLS],
        "raw_jet_unknowns": 42, "raw_jet_rank": width,
        "nodes_times_degree": nodes, "unknowns": 3*len(nodes),
        "edge_rows": len(cells)*(4+6*(degree-2)), "zero_mean_rows": len(cells),
        "basis_shape": [3*len(nodes), width], "basis": sparse,
        "edge_corrections": corrections, "mean_correction": mean_info,
        "retained_mean_repair": {"file": path.name, "sha256": sha256(data).hexdigest(),
                                 "basis_shape": [189, 11], "mean_solver_called": False},
        "maximum_squared_coefficient_row_norm": str(maximum),
        "h1_squared_bound_from_target_l2": str(576*degree*degree*maximum),
        "coefficient_semantics":
            "continuous vector Bernstein coefficients; omitted boundary coefficients are zero",
        "ordering_semantics":
            "grid((2,2,2)) cell and local vertex order; complete trace follows incident_cells",
    }
    result["physical_identity_check"] = face_transport.check_physical_operator(result)
    return result


def transport(operator, vertex=(0, 0, 0), scale=1):
    """Map reference center to vertex, with x=vertex+h*(reference-(1,1,1))."""
    _, vertex, scale = face_transport.parameters("x", vertex, scale)
    if (not isinstance(operator, dict)
            or operator.get("schema") != "freudenthal-interior-vertex-lift/v1"
            or operator.get("status") != "CONSTRUCTED"):
        raise ValueError("operator must be a constructed interior-vertex reference")
    degree = operator["degree"]

    def mapped(p, multiplier=1):
        return [str(multiplier*vertex[j]+scale*(F(p[j])-multiplier*CENTER[j]))
                for j in range(3)]

    result = deepcopy(operator)
    result.pop("requested_trace", None)
    result.pop("velocity_coefficients", None)
    result.update({
        "schema": "freudenthal-interior-vertex-transport/v1",
        "status": "TRANSPORTED_AND_CHECKED",
        "reference_schema": operator["schema"],
        "vertex": [str(v) for v in vertex], "scale": str(scale),
        "target_vertex": [str(v) for v in vertex],
        "cells": [[mapped(p) for p in cell] for cell in operator["cells"]],
        "nodes_times_degree": [mapped(p, degree) for p in operator["nodes_times_degree"]],
        "basis": [[row, column, str(scale*F(value))] for row, column, value in operator["basis"]],
        "edge_corrections": [{**item, "target_edge": [mapped(p) for p in item["target_edge"]]}
                             for item in operator["edge_corrections"]],
        "reference_maximum_squared_coefficient_row_norm":
            operator["maximum_squared_coefficient_row_norm"],
        "maximum_squared_coefficient_row_norm":
            str(scale**2*F(operator["maximum_squared_coefficient_row_norm"])),
        "reference_h1_squared_bound_from_target_l2": operator["h1_squared_bound_from_target_l2"],
        "h1_squared_bound_from_target_l2": str(scale**3*F(operator["h1_squared_bound_from_target_l2"])),
        "coordinate_semantics":
            "vertex is the physical center; patch is vertex+[-scale,scale]^3; "
            "divide nodes_times_degree by degree",
    })
    result["physical_identity_check"] = face_transport.check_physical_operator(result)
    return result


def apply(operator, trace):
    if (not isinstance(operator, dict)
            or operator.get("schema") not in ("freudenthal-interior-vertex-lift/v1",
                                               "freudenthal-interior-vertex-transport/v1")
            or operator.get("status") not in ("CONSTRUCTED", "TRANSPORTED_AND_CHECKED")):
        raise ValueError("operator must be a constructed or transported interior-vertex lift")
    target = compatible_trace(trace)
    free = [target[i] for i in operator["free_coordinate_indices"]]
    values = [F(0)]*operator["unknowns"]
    for row, column, value in operator["basis"]:
        values[row] += F(value)*free[column]
    return [[str(value) for value in values[i:i+3]] for i in range(0, len(values), 3)]


def construct(degree=4, vertex=(0, 0, 0), scale=1):
    face_transport.parameters("x", vertex, scale)
    return transport(construct_reference(degree), vertex, scale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    parser.add_argument("--vertex", default="0,0,0", help="Physical central vertex, three comma-separated exact values")
    parser.add_argument("--scale", default="1", help="Positive exact isotropic scale")
    trace_args = parser.add_mutually_exclusive_group()
    trace_args.add_argument("--trace", help="24 comma-separated central divergence values in incident_cells order")
    trace_args.add_argument("--free-trace", help="18 comma-separated values in free_cell_ids order")
    parser.add_argument("--output", type=Path, help="Create a new JSON file; default stdout")
    args = parser.parse_args()
    try:
        target = (compatible_trace(args.trace.split(",")) if args.trace is not None else
                  trace_from_free(args.free_trace.split(",")) if args.free_trace is not None else None)
        result = construct(args.degree, args.vertex.split(","), args.scale)
        if target is not None:
            result["requested_trace"] = [str(value) for value in target]
            result["velocity_coefficients"] = apply(result, target)
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(data)
        else:
            print(data, end="")
        print(f"TRANSPORTED_AND_CHECKED: degree {args.degree}, source dimension 18/24, "
              f"14 edge corrections, 48 zero cell means, {len(result['basis'])} nonzero coefficients",
              file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError, TypeError) as exc:
        print(f"interior_vertex_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
