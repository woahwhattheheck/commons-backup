"""Protected Dirichlet boundary-vertex lifts for degree four and five.

Five reference classes cover 26 face, crease and corner orientations.
Their complete source dimensions are 8, 5, 0, 3 and 0. Exact first-derivative
inverses compose retained edge and mean operators on fixed patches.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from math import prod
from pathlib import Path
import sys

try:
    from . import interior_vertex_lift as shared
    from . import axial_edge_lift as axial
    from . import body_diagonal_transport as body
    from . import face_diagonal_lift as face
    from . import face_diagonal_transport as coordinates
    from .p4_grid_mean_repair import grid
    from .p4_mean_repair import indices, gradients
except ImportError:
    import interior_vertex_lift as shared
    import axial_edge_lift as axial
    import body_diagonal_transport as body
    import face_diagonal_lift as face
    import face_diagonal_transport as coordinates
    from p4_grid_mean_repair import grid
    from p4_mean_repair import indices, gradients

CONFIGURATIONS = {
    "face": {"shape": (1, 2, 2), "center": (0, 1, 1), "boundary": ((0, 0),)},
    "crease_same": {"shape": (1, 1, 2), "center": (0, 0, 1),
                    "boundary": ((0, 0), (1, 0))},
    "crease_mixed": {"shape": (1, 1, 2), "center": (0, 1, 1),
                     "boundary": ((0, 0), (1, 1))},
    "corner_same": {"shape": (2, 1, 1), "center": (0, 0, 0),
                    "boundary": ((0, 0), (1, 0), (2, 0))},
    "corner_mixed": {"shape": (2, 1, 1), "center": (0, 0, 1),
                     "boundary": ((0, 0), (1, 0), (2, 1))},
}
# Each row gives (neighbor displacement, component, terms of k*a_component).
INVERSES = {
    "face": {
        "star": [3,5,8,9,16,17,18,19,20,21,22,23],
        "neighbors": [[1,0,0],[1,0,1],[1,1,0],[1,1,1]],
        "free_cells": [3,8,9,16,17,20,21,22],
        "rows": [
            [[1,0,0],0,[[3,1]]],
            [[1,0,0],1,[[3,1],[16,-1]]],
            [[1,0,0],2,[[3,1],[8,-1]]],
            [[1,0,1],0,[[9,1]]],
            [[1,0,1],1,[[9,1],[22,-1]]],
            [[1,1,0],0,[[17,1]]],
            [[1,1,0],2,[[17,1],[20,-1]]],
            [[1,1,1],0,[[21,1]]]
        ]
    },
    "crease_same": {
        "star": [4,5,6,7,8,9,10,11],
        "neighbors": [[1,1,0],[1,1,1]],
        "free_cells": [4,5,6,7,9],
        "rows": [
            [[1,1,0],0,[[5,1]]],
            [[1,1,0],1,[[4,1]]],
            [[1,1,0],2,[[4,1],[6,-1]]],
            [[1,1,1],0,[[9,1]]],
            [[1,1,1],1,[[7,1]]]
        ]
    },
    "crease_mixed": {
        "star": [3,5,8,9],
        "neighbors": [],
        "free_cells": [],
        "rows": []
    },
    "corner_same": {
        "star": [0,1,2,3,4,5],
        "neighbors": [[1,1,1]],
        "free_cells": [0,1,3],
        "rows": [
            [[1,1,1],0,[[3,1]]],
            [[1,1,1],1,[[1,1]]],
            [[1,1,1],2,[[0,1]]]
        ]
    },
    "corner_mixed": {
        "star": [4,5],
        "neighbors": [],
        "free_cells": [],
        "rows": []
    }
}


def orientation_table():
    result = {}
    for kind, configuration in CONFIGURATIONS.items():
        axes = ("x",) if kind == "corner_same" else tuple("xyz")
        for axis in axes:
            permutation = coordinates.PERMUTATIONS[axis]
            for sign in (1, -1):
                sides = sorted((permutation[i], side if sign > 0 else 1-side)
                               for i, side in configuration["boundary"])
                group = {1: "face", 2: "crease", 3: "corner"}[len(sides)]
                key = group+"-"+"-".join("xyz"[i]+"-"+("upper" if side else "lower")
                                        for i, side in sides)
                if key in result:
                    raise ArithmeticError("Duplicate coordinate boundary-vertex orientation")
                result[key] = {"class": kind, "axis": axis, "sign": sign,
                               "boundary_faces": [{"axis": "xyz"[i], "side": "upper" if side else "lower"}
                                                  for i, side in sides]}
    if len(result) != 26:
        raise ArithmeticError("Boundary-vertex orientation census must contain 26 entries")
    return result


ORIENTATIONS = orientation_table()


def scalar(value):
    value = F(value)
    return int(value) if value.denominator == 1 else str(value)


def source_operator(kind, degree, cells):
    configuration, inverse = CONFIGURATIONS[kind], INVERSES[kind]
    center, shape = configuration["center"], configuration["shape"]
    star = [i for i, cell in enumerate(cells) if center in cell]
    if star != inverse["star"]:
        raise ArithmeticError("Kuhn cell ordering differs from the boundary-vertex source convention")
    neighbors = sorted({tuple(p[j]-center[j] for j in range(3))
                        for cell_id in star for p in cells[cell_id] if p != center
                        and all(0 < (degree-1)*center[j]+p[j] < degree*shape[j] for j in range(3))})
    if neighbors != [tuple(p) for p in inverse["neighbors"]]:
        raise ArithmeticError("Dirichlet edge-near source variables differ from the explicit convention")
    free_cells, width = inverse["free_cells"], len(inverse["free_cells"])
    free_index = {cell: i for i, cell in enumerate(free_cells)}
    raw = {}
    for direction, component, terms in inverse["rows"]:
        node = tuple(degree*center[j]+direction[j] for j in range(3))
        if tuple(direction) not in neighbors:
            raise ArithmeticError("An explicit jet coefficient violates the boundary trace")
        rows = raw.setdefault(node, shared.zero_rows(width))
        for cell_id, value in terms:
            rows[component][free_index[cell_id]] += F(value, degree)
    labels, source_basis, jets = [], [], []
    neighbor_ids = {p: i for i, p in enumerate(neighbors)}
    for cell_id in star:
        cell, beta = cells[cell_id], [0]*4
        beta[cell.index(center)] = degree-1
        labels.append({"cell": cell_id, "beta": beta})
        source_basis.append(shared.divergence_row(raw, cell, beta, degree, width))
        row, grad = [F(0)]*(3*len(neighbors)), gradients(cell)
        for i, point in enumerate(cell):
            direction = tuple(point[j]-center[j] for j in range(3))
            if direction in neighbor_ids:
                for component in range(3):
                    row[3*neighbor_ids[direction]+component] = degree*grad[i][component]
        jets.append(row)
    free_rows = [star.index(cell) for cell in free_cells]
    for j, row_index in enumerate(free_rows):
        if source_basis[row_index] != [int(i == j) for i in range(width)]:
            raise ArithmeticError("Boundary-vertex inverse does not reproduce the free source rows")
    # Necessity: every unrestricted Dirichlet source jet has these relations.
    # Sufficiency: the explicit compact field realizes all independent values.
    for row, coefficients in zip(jets, source_basis):
        if row != [sum(coefficients[j]*jets[free_rows[j]][column] for j in range(width))
                   for column in range(3*len(neighbors))]:
            raise ArithmeticError("Explicit boundary source image omits a Dirichlet first derivative")
    relations = [{"cell": cell, "terms": [[free_cells[j], scalar(value)]
                                         for j, value in enumerate(source_basis[i]) if value]}
                 for i, cell in enumerate(star) if cell not in free_index]
    return raw, labels, source_basis, neighbors, free_rows, relations


def reference_cache(degree):
    path = Path(__file__).with_name("p4_mean_repair_basis.json")
    data = path.read_bytes()
    operator = json.loads(data)
    if (operator.get("schema") != "freudenthal-p4-mean-repair/v1"
            or operator.get("status") != "CONSTRUCTED"
            or operator.get("basis_shape") != [189, 11]):
        raise ValueError("retained mean repair must be the constructed two-cube 189-by-11 operator")
    return {"degree": degree, "mean": operator,
            "mean_source": {"file": path.name, "sha256": sha256(data).hexdigest(),
                            "basis_shape": [189, 11], "mean_solver_called": False}}


def edge_reference(cache, kind):
    if kind not in cache:
        degree = cache["degree"]
        if kind == "axial":
            cache[kind] = axial.construct_reference(degree)
        elif kind == "face":
            cache[kind] = face.construct(degree, mean_repair=cache["mean"])
        elif kind == "body":
            cache[kind] = body.reference_operator(degree)
        else:
            raise ValueError("unknown edge class")
    return cache[kind]


def edge_operators(kind, cache):
    if kind == "face":
        yield "axial", axial.transport(edge_reference(cache, "axial"), "x", (0, 0, 0))
        yield "face_diagonal", coordinates.transport(edge_reference(cache, "face"), "y", (0, 0, 1))
        yield "face_diagonal", coordinates.transport(edge_reference(cache, "face"), "z", (0, 1, 0))
        yield "body_diagonal", body.transport(edge_reference(cache, "body"), "-y", (0, 1, 1))
    elif kind == "crease_same":
        yield "face_diagonal", coordinates.transport(edge_reference(cache, "face"), "z", (0, 0, 0))
        yield "body_diagonal", body.transport(edge_reference(cache, "body"), "-z", (0, 0, 1))
    elif kind == "corner_same":
        yield "body_diagonal", body.transport(edge_reference(cache, "body"), "+x", (0, 0, 0))


def check(operator):
    # The shared checker accepts exact numeric source rows; output JSON also
    # permits rational strings should a future explicit source image need them.
    return coordinates.check_physical_operator({
        **operator, "source_basis": [[F(value) for value in row] for row in operator["source_basis"]]})


def construct_reference(degree=4, kind="face", cache=None):
    if type(degree) is not int or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    if kind not in CONFIGURATIONS:
        raise ValueError("unknown boundary-vertex reference class")
    cache = reference_cache(degree) if cache is None else cache
    if cache["degree"] != degree:
        raise ValueError("edge reference cache degree does not match")
    configuration = CONFIGURATIONS[kind]
    shape, center = configuration["shape"], configuration["center"]
    cells = grid(shape)[1]
    raw, labels, source_basis, neighbors, free_rows, relations = source_operator(kind, degree, cells)
    width = len(free_rows)
    nodes = (sorted({shared.point(cell, alpha) for cell in cells for alpha in indices(degree)
                     if all(0 < value < degree*shape[j]
                            for j, value in enumerate(shared.point(cell, alpha)))}) if width else [])
    field = {node: [row[:] for row in rows] for node, rows in raw.items()}
    cell_ids = {tuple(sorted(cell)): i for i, cell in enumerate(cells)}
    corrections, seen_edges = [], set()
    for edge_kind, operator in edge_operators(kind, cache):
        edge = tuple(tuple(F(v) for v in p) for p in operator["target_edge"])
        if center not in edge:
            raise ArithmeticError("Boundary-vertex correction misses its central endpoint")
        other = edge[1] if edge[0] == center else edge[0]
        direction = tuple(other[j]-center[j] for j in range(3))
        if direction not in neighbors or direction in seen_edges:
            raise ArithmeticError("Boundary-vertex edge correction is duplicated or leaves the source star")
        seen_edges.add(direction)
        corrections.append({"kind": edge_kind, **shared.subtract_edge(
            field, raw, operator, degree, width, cell_ids)})
    if seen_edges != set(neighbors):
        raise ArithmeticError("Boundary-vertex composition omitted an interior incident edge")
    mean_info = (shared.remove_means(cells, nodes, field, degree, width, shape=shape) if width else
                 {"repaired_columns": 0, "two_cube_patch_applications": 0, "degree_elevated": False})
    lookup = {node: i for i, node in enumerate(nodes)}
    if any(node not in lookup and any(any(row) for row in rows) for node, rows in field.items()):
        raise ArithmeticError("Boundary-vertex composition produced a coefficient outside its patch")
    sparse, maximum = [], F(0)
    for node in nodes:
        for component, row in enumerate(field.get(node, shared.zero_rows(width))):
            maximum = max(maximum, sum(value*value for value in row))
            sparse.extend([3*lookup[node]+component, j, str(value)]
                          for j, value in enumerate(row) if value)
    result = {
        "schema": "freudenthal-boundary-vertex-lift/v1", "status": "CONSTRUCTED",
        "degree": degree, "class": kind, "shape": list(shape), "cells": cells,
        "target_vertex": center, "incident_cells": [label["cell"] for label in labels],
        "interior_incident_edge_directions": neighbors,
        "reference_boundary_faces": [{"axis": "xyz"[i], "side": "upper" if side else "lower"}
                                     for i, side in configuration["boundary"]],
        "target_coordinates": labels, "target_coordinate_count": len(labels),
        "source_dimension": width, "source_jet_unknowns": 3*len(neighbors),
        "source_basis": [[scalar(value) for value in row] for row in source_basis],
        "source_relations": relations, "free_cell_ids": INVERSES[kind]["free_cells"],
        "free_coordinate_indices": free_rows,
        "nodes_times_degree": nodes, "unknowns": 3*len(nodes),
        "basis_shape": [3*len(nodes), width], "basis": sparse,
        "edge_rows": len(cells)*(4+6*(degree-2)), "zero_mean_rows": len(cells),
        "edge_corrections": corrections, "mean_correction": mean_info,
        "retained_mean_repair": cache["mean_source"],
        "maximum_squared_coefficient_row_norm": str(maximum),
        "h1_squared_bound_from_target_l2": str(prod(shape)*72*degree*degree*maximum),
        "coefficient_semantics":
            "continuous vector Bernstein coefficients; all omitted coefficients are zero",
        "ordering_semantics":
            "reference grid cell/local-vertex order; complete trace follows incident_cells",
        "patch_scope":
            "four cubes for face vertices; two cubes for crease/corner vertices; "
            "corner patch is extended along its reference x axis",
    }
    result["physical_identity_check"] = check(result)
    return result


def transport(operator, orientation="face-x-lower", vertex=(0, 0, 0), scale=1):
    if orientation not in ORIENTATIONS:
        raise ValueError("unknown coordinate boundary-vertex orientation")
    metadata = ORIENTATIONS[orientation]
    permutation, vertex, scale = coordinates.parameters(metadata["axis"], vertex, scale)
    sign = metadata["sign"]
    if (not isinstance(operator, dict)
            or operator.get("schema") != "freudenthal-boundary-vertex-lift/v1"
            or operator.get("status") != "CONSTRUCTED"
            or operator.get("class") != metadata["class"]):
        raise ValueError("reference class does not match the requested boundary orientation")
    degree, center = operator["degree"], CONFIGURATIONS[operator["class"]]["center"]
    vertex_order = (0, 1, 2, 3) if sign > 0 else (0, 2, 1, 3)

    def mapped(p, multiplier=1):
        values = [multiplier*v for v in vertex]
        for old, new in enumerate(permutation):
            values[new] += scale*sign*(F(p[old])-multiplier*center[old])
        return [str(value) for value in values]

    shape = [0]*3
    for old, new in enumerate(permutation):
        shape[new] = operator["shape"][old]
    result = deepcopy(operator)
    result.pop("requested_trace", None)
    result.pop("velocity_coefficients", None)
    result.update({
        "schema": "freudenthal-boundary-vertex-transport/v1",
        "status": "TRANSPORTED_AND_CHECKED", "reference_schema": operator["schema"],
        "orientation": orientation, "boundary_faces": metadata["boundary_faces"],
        "vertex": [str(value) for value in vertex], "target_vertex": [str(value) for value in vertex],
        "scale": str(scale), "reference_shape": operator["shape"], "shape": shape,
        "reference_to_physical_component": list(permutation), "component_sign": sign,
        "physical_vertex_to_reference_vertex": list(vertex_order),
        "cells": [[mapped(cell[old]) for old in vertex_order] for cell in operator["cells"]],
        "nodes_times_degree": [mapped(p, degree) for p in operator["nodes_times_degree"]],
        "target_coordinates": [{**label, "beta": [label["beta"][old] for old in vertex_order]}
                               for label in operator["target_coordinates"]],
        "basis": sorted([[3*(row//3)+permutation[row % 3], column, str(scale*sign*F(value))]
                         for row, column, value in operator["basis"]]),
        "edge_corrections": [{**item, "target_edge": [mapped(p) for p in item["target_edge"]]}
                             for item in operator["edge_corrections"]],
        "reference_maximum_squared_coefficient_row_norm":
            operator["maximum_squared_coefficient_row_norm"],
        "maximum_squared_coefficient_row_norm":
            str(scale**2*F(operator["maximum_squared_coefficient_row_norm"])),
        "reference_h1_squared_bound_from_target_l2": operator["h1_squared_bound_from_target_l2"],
        "h1_squared_bound_from_target_l2": str(scale**3*F(operator["h1_squared_bound_from_target_l2"])),
        "coordinate_semantics":
            "vertex is the physical central vertex; boundary_faces name the planes through it; "
            "cells give the complete patch; divide nodes_times_degree by degree",
        "ordering_semantics":
            "reference cell/node/trace order is inherited; a negative component sign swaps "
            "local vertices 1/2 and their beta entries; vector components are permuted",
    })
    def mapped_direction(direction):
        result = [0]*3
        for old, new in enumerate(permutation):
            result[new] = sign*direction[old]
        return result

    result["reference_interior_incident_edge_directions"] = operator["interior_incident_edge_directions"]
    result["interior_incident_edge_directions"] = [
        mapped_direction(direction) for direction in operator["interior_incident_edge_directions"]]
    result["physical_identity_check"] = check(result)
    return result


def compatible_trace(operator, values):
    target = shared.exact_values(values, operator["target_coordinate_count"], "trace")
    free = [target[i] for i in operator["free_coordinate_indices"]]
    for i, row in enumerate(operator["source_basis"]):
        residual = target[i]-sum(F(value)*free[j] for j, value in enumerate(row))
        if residual:
            cell = operator["incident_cells"][i]
            raise ValueError(f"incompatible {operator['class']} vertex source trace at cell {cell}: residual {residual}")
    return target


def trace_from_free(operator, values):
    free = shared.exact_values(values, operator["source_dimension"], "free trace")
    return [sum(F(value)*free[j] for j, value in enumerate(row)) for row in operator["source_basis"]]


def apply(operator, trace):
    if (not isinstance(operator, dict)
            or operator.get("schema") not in ("freudenthal-boundary-vertex-lift/v1",
                                               "freudenthal-boundary-vertex-transport/v1")
            or operator.get("status") not in ("CONSTRUCTED", "TRANSPORTED_AND_CHECKED")):
        raise ValueError("operator must be a constructed or transported boundary-vertex lift")
    target = compatible_trace(operator, trace)
    free = [target[i] for i in operator["free_coordinate_indices"]]
    values = [F(0)]*operator["unknowns"]
    for row, column, value in operator["basis"]:
        values[row] += F(value)*free[column]
    return [[str(value) for value in values[i:i+3]] for i in range(0, len(values), 3)]


def construct(degree=4, orientation="face-x-lower", vertex=(0, 0, 0), scale=1):
    if orientation not in ORIENTATIONS:
        raise ValueError("unknown coordinate boundary-vertex orientation")
    coordinates.parameters(ORIENTATIONS[orientation]["axis"], vertex, scale)
    return transport(construct_reference(degree, ORIENTATIONS[orientation]["class"]),
                     orientation, vertex, scale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument("--orientation", choices=tuple(ORIENTATIONS), default="face-x-lower")
    selected.add_argument("--all-orientations", action="store_true",
                          help="Reuse five references for the complete 26-orientation boundary census")
    parser.add_argument("--vertex", default="0,0,0", help="Physical center, three comma-separated exact values")
    parser.add_argument("--scale", default="1", help="Positive exact isotropic scale")
    traces = parser.add_mutually_exclusive_group()
    traces.add_argument("--trace", help="Comma-separated complete source tuple for one orientation")
    traces.add_argument("--free-trace", help="Comma-separated independent source values for one orientation")
    parser.add_argument("--output", type=Path, help="Create a new JSON file; default stdout")
    args = parser.parse_args()
    try:
        if args.all_orientations and (args.trace is not None or args.free_trace is not None):
            raise ValueError("select one orientation when supplying a complete or free trace")
        _, vertex, scale = coordinates.parameters("x", args.vertex.split(","), args.scale)
        cache, references, operators = reference_cache(args.degree), {}, {}
        selected_orientations = ORIENTATIONS if args.all_orientations else (args.orientation,)
        for orientation in selected_orientations:
            kind = ORIENTATIONS[orientation]["class"]
            if kind not in references:
                references[kind] = construct_reference(args.degree, kind, cache)
            operator = transport(references[kind], orientation, vertex, scale)
            target = (compatible_trace(operator, args.trace.split(",")) if args.trace is not None else
                      trace_from_free(operator, args.free_trace.split(",")) if args.free_trace is not None else None)
            if target is not None:
                operator["requested_trace"] = [str(value) for value in target]
                operator["velocity_coefficients"] = apply(operator, target)
            operators[orientation] = operator
        result = ({"schema": "freudenthal-boundary-vertex-batch/v1", "status": "TRANSPORTED_AND_CHECKED",
                   "degree": args.degree, "operators": operators} if args.all_orientations else
                  operators[args.orientation])
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(data)
        else:
            print(data, end="")
        print(f"TRANSPORTED_AND_CHECKED: degree {args.degree}, {len(operators)} boundary orientations, "
              f"source dimensions {sorted({item['source_dimension'] for item in operators.values()})}",
              file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError, TypeError) as exc:
        print(f"boundary_vertex_lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
