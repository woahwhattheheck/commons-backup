"""Exact contained-patch planner for every vertex and edge of a Kuhn cube mesh.

The planner imports geometry only. It describes how to call the accepted local
lifts; it never constructs or checks their coefficient operators. This is a
patch-embedding and incidence census, not a global inf-sup theorem.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction as F
from itertools import combinations, product
import json
from pathlib import Path
import sys

try:
    from .kuhn import kuhn_tets, tet_volume_times_6
except ImportError:
    from kuhn import kuhn_tets, tet_volume_times_6

SCHEMA = "freudenthal-global-patch-plan/v1"
AXES = "xyz"
CYCLIC = {"x": (0, 1, 2), "y": (1, 2, 0), "z": (2, 0, 1)}
IDENTITY = (0, 1, 2)

# Geometry from boundary_vertex_lift.py CONFIGURATIONS and orientation_table.
# Keeping these geometry-only values avoids importing any local-lift solver.
BOUNDARY_VERTEX_CONFIGURATIONS = {
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


def rational(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, str, F)):
        raise ValueError(f"{name} must be an integer or exact rational string")
    try:
        return F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{name} must be a finite exact rational") from exc


def triple(values, name):
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"{name} must contain three exact coordinates")
    return tuple(rational(value, name) for value in values)


def permute(point, permutation):
    values = [0, 0, 0]
    for old, new in enumerate(permutation):
        values[new] = point[old]
    return tuple(values)


def parity(permutation):
    return -1 if sum(permutation[i] > permutation[j]
                     for i in range(3) for j in range(i + 1, 3)) % 2 else 1


def difference(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def boundary_sides(point, n):
    return tuple((i, "lower" if value == 0 else "upper")
                 for i, value in enumerate(point) if value in (0, n))


def boundary_vertex_orientations():
    result = {}
    for kind, configuration in BOUNDARY_VERTEX_CONFIGURATIONS.items():
        axes = ("x",) if kind == "corner_same" else tuple(AXES)
        for axis in axes:
            permutation = CYCLIC[axis]
            for sign in (1, -1):
                sides = sorted((permutation[i], side if sign > 0 else 1 - side)
                               for i, side in configuration["boundary"])
                group = {1: "face", 2: "crease", 3: "corner"}[len(sides)]
                key = group + "-" + "-".join(
                    AXES[i] + "-" + ("upper" if side else "lower")
                    for i, side in sides)
                if key in result:
                    raise ArithmeticError("duplicate boundary-vertex orientation")
                result[key] = {"class": kind, "axis": axis, "sign": sign}
    if len(result) != 26:
        raise ArithmeticError("expected 26 boundary-vertex orientations")
    return result


BOUNDARY_VERTEX_ORIENTATIONS = boundary_vertex_orientations()


def grid(shape):
    """Same cube-major, positive Kuhn order as p4_grid_mean_repair.grid."""
    cubes = list(product(*(range(size) for size in shape)))
    cells = [tuple(tuple(point[j] + cube[j] for j in range(3)) for point in tet)
             for cube in cubes for tet in kuhn_tets()]
    return cubes, cells


def specification(kind, module, shape, target, zero, permutation=IDENTITY,
                  sign=1, parameters=None, cli=None, anchor=None,
                  zero_source_image=False, orientation=None):
    return {
        "class": kind, "module": module, "shape": tuple(shape),
        "reference_target": tuple(target), "zero": tuple(zero),
        "permutation": tuple(permutation), "sign": sign,
        "parameters": dict(parameters or {}), "cli": dict(cli or {}),
        "anchor": anchor, "zero_source_image": zero_source_image,
        "orientation": orientation,
    }


def vertex_specification(vertex, n):
    sides = boundary_sides(vertex, n)
    if not sides:
        return specification(
            "interior", "interior_vertex_lift", (2, 2, 2), ((1, 1, 1),),
            difference(vertex, (1, 1, 1)), anchor=("vertex", vertex),
            orientation="interior")
    group = {1: "face", 2: "crease", 3: "corner"}[len(sides)]
    orientation = group + "-" + "-".join(AXES[i] + "-" + side for i, side in sides)
    metadata = BOUNDARY_VERTEX_ORIENTATIONS[orientation]
    kind, sign = metadata["class"], metadata["sign"]
    configuration = BOUNDARY_VERTEX_CONFIGURATIONS[kind]
    permutation = CYCLIC[metadata["axis"]]
    center = configuration["center"]
    zero = difference(vertex, tuple(sign * value for value in permute(center, permutation)))
    return specification(
        kind, "boundary_vertex_lift", configuration["shape"], (center,), zero,
        permutation, sign, {"orientation": orientation},
        {"orientation": orientation}, ("vertex", vertex),
        zero_source_image=kind in ("crease_mixed", "corner_mixed"),
        orientation=orientation)


def edge_specification(low, high, n):
    displacement = difference(high, low)
    if any(value not in (0, 1) for value in displacement) or not any(displacement):
        raise ArithmeticError(f"non-Kuhn edge displacement: {displacement}")
    moving = tuple(i for i, value in enumerate(displacement) if value)
    if len(moving) == 3:
        neighbor = "+x" if low[0] < n - 1 else "-x"
        sign = 1 if neighbor == "+x" else -1
        zero = low if sign > 0 else tuple(value + 1 for value in low)
        return specification(
            "body_diagonal", "body_diagonal_transport", (2, 1, 1),
            ((0, 0, 0), (1, 1, 1)), zero, sign=sign,
            parameters={"neighbor": neighbor}, cli={"neighbor": neighbor},
            anchor=("origin", low), orientation=neighbor)
    if len(moving) == 2:
        normal = next(i for i in range(3) if not displacement[i])
        axis = AXES[normal]
        permutation = CYCLIC[axis]
        if low[normal] not in (0, n):
            zero = tuple(low[i] - (i == normal) for i in range(3))
            return specification(
                "interior_face_diagonal", "face_diagonal_transport", (2, 1, 1),
                ((1, 0, 0), (1, 1, 1)), zero, permutation,
                parameters={"normal_axis": axis}, cli={"normal-axis": axis},
                anchor=("origin", zero), orientation=axis)
        side = "lower" if low[normal] == 0 else "upper"
        sign = 1 if side == "lower" else -1
        first = low if sign > 0 else high
        orientation = axis + "-" + side
        return specification(
            "boundary_face_diagonal", "boundary_face_diagonal_lift", (2, 1, 1),
            ((0, 0, 0), (0, 1, 1)), first, permutation, sign,
            {"normal_axis": axis, "side": side}, {"face": orientation},
            ("origin", first), orientation=orientation)
    tangent = moving[0]
    normals = tuple(i for i in range(3) if i != tangent)
    sides = tuple((i, "lower" if low[i] == 0 else "upper")
                  for i in normals if low[i] in (0, n))
    axis = AXES[tangent]
    if not sides:
        zero = tuple(low[i] - (i != tangent) for i in range(3))
        return specification(
            "interior_axial", "axial_edge_lift", (1, 2, 2),
            ((0, 1, 1), (1, 1, 1)), zero, CYCLIC[axis],
            parameters={"axis": axis}, cli={"axis": axis},
            anchor=("origin", zero), orientation=axis)
    if len(sides) == 1:
        normal, side = sides[0]
        remaining = next(i for i in normals if i != normal)
        permutation = (remaining, tangent, normal)
        sign = 1 if side == "lower" else -1
        first = low if sign > 0 else high
        offset = permute((1, 0, 0), permutation)
        zero = difference(first, tuple(sign * value for value in offset))
        orientation = f"{axis}-{AXES[normal]}-{side}"
        return specification(
            "boundary_axial", "boundary_axial_edge_lift", (2, 1, 1),
            ((1, 0, 0), (1, 1, 0)), zero, permutation, sign,
            {"tangent_axis": axis, "normal_axis": AXES[normal], "side": side},
            {"orientation": orientation}, ("origin", zero),
            orientation=orientation)
    first_side, second_side = sides[0][1], sides[1][1]
    same = first_side == second_side
    sign = 1 if first_side == "lower" else -1
    permutation = (normals[0], tangent, normals[1])
    z = 0 if same else 1
    reference_low, reference_high = (0, 0, z), (0, 1, z)
    first = low if sign > 0 else high
    zero = difference(first, tuple(sign * value
                                  for value in permute(reference_low, permutation)))
    orientation = f"{axis}-{AXES[normals[0]]}-{first_side}-{AXES[normals[1]]}-{second_side}"
    return specification(
        "boundary_crease_same" if same else "boundary_crease_mixed",
        "boundary_crease_edge_lift", (2, 1, 1), (reference_low, reference_high),
        zero, permutation, sign,
        {"tangent_axis": axis, "side_first": first_side, "side_second": second_side},
        {"edge": orientation}, ("origin", zero),
        zero_source_image=not same, orientation=orientation)


def map_beta(patch, local_cell, beta):
    """Map an existing transported operator's cell/Bernstein label to the mesh."""
    if type(local_cell) is not int or not 0 <= local_cell < len(patch["local_cell_to_global_cell"]):
        raise ValueError("local_cell is outside the planned patch")
    if (not isinstance(beta, (list, tuple)) or len(beta) != 4
            or any(type(value) is not int or value < 0 for value in beta)):
        raise ValueError("beta must contain four nonnegative integers")
    positions = patch["local_vertex_to_global_vertex_position"][local_cell]
    global_beta = [0, 0, 0, 0]
    for local_vertex, global_position in enumerate(positions):
        global_beta[global_position] = beta[local_vertex]
    return patch["local_cell_to_global_cell"][local_cell], tuple(global_beta)


def construct(n, degree=4, origin=(0, 0, 0), cell_size=None):
    """Return the full exact mesh, every target patch, and executable call data."""
    if type(n) is not int or n < 2:
        raise ValueError("n must be an integer at least 2")
    if type(degree) is not int or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    origin = triple(origin, "origin")
    size = F(1, n) if cell_size is None else rational(cell_size, "cell_size")
    if size <= 0:
        raise ValueError("cell_size must be positive")

    def physical(point):
        return [str(origin[i] + size * point[i]) for i in range(3)]

    lattice_vertices = list(product(range(n + 1), repeat=3))
    vertex_ids = {point: i for i, point in enumerate(lattice_vertices)}
    cubes, global_cells = grid((n, n, n))
    cells = [[vertex_ids[point] for point in cell] for cell in global_cells]
    cell_ids = {tuple(sorted(cell)): i for i, cell in enumerate(cells)}
    if len(cell_ids) != 6 * n**3:
        raise ArithmeticError("global cells are not unique")
    vertex_incidence = [[] for _ in lattice_vertices]
    edge_incidence = {}
    for cell_id, cell in enumerate(cells):
        if tet_volume_times_6(global_cells[cell_id]) != 1:
            raise ArithmeticError("global Kuhn cell lost positive orientation")
        for vertex in cell:
            vertex_incidence[vertex].append(cell_id)
        for a, b in combinations(cell, 2):
            edge = tuple(sorted((a, b)))
            edge_incidence.setdefault(edge, []).append(cell_id)
    edges = sorted(edge_incidence)
    templates = {}
    template_geometry = {}

    def template(shape):
        key = "x".join(map(str, shape))
        if key not in templates:
            points = list(product(*(range(length + 1) for length in shape)))
            point_ids = {point: i for i, point in enumerate(points)}
            reference_cubes, reference_cells = grid(shape)
            templates[key] = {
                "shape": list(shape), "lattice_vertices": [list(point) for point in points],
                "cells": [[point_ids[point] for point in cell] for cell in reference_cells],
                "cube_origins": [list(cube) for cube in reference_cubes],
            }
            template_geometry[key] = (points, reference_cells)
        return key, template_geometry[key]

    def embed(spec, target_id, target_vertices, actual_incidence):
        shape, permutation, sign = spec["shape"], spec["permutation"], spec["sign"]
        zero, reference_target = spec["zero"], spec["reference_target"]
        template_key, (reference_vertices, reference_cells) = template(shape)

        def mapped(point):
            moved = permute(point, permutation)
            return tuple(zero[i] + sign * moved[i] for i in range(3))

        mapped_vertices = [mapped(point) for point in reference_vertices]
        if any(any(value < 0 or value > n for value in point) for point in mapped_vertices):
            raise ArithmeticError(f"patch leaves mesh: {spec['class']} target {target_id}")
        patch_vertex_ids = [vertex_ids[point] for point in mapped_vertices]
        canonical_points = tuple(lattice_vertices[i] for i in target_vertices)
        transported_target = tuple(mapped(point) for point in reference_target)
        if set(transported_target) != set(canonical_points):
            raise ArithmeticError("reference target does not map to the requested mesh target")
        endpoint_order = [canonical_points.index(point) for point in transported_target]
        determinant = sign * parity(permutation)
        vertex_order = (0, 1, 2, 3) if determinant > 0 else (0, 2, 1, 3)
        local_to_global, position_maps = [], []
        transported_cells = []
        for local_cell, reference_cell in enumerate(reference_cells):
            transformed = tuple(mapped(reference_cell[i]) for i in vertex_order)
            if tet_volume_times_6(transformed) != 1:
                raise ArithmeticError("transported local cell is not positively oriented")
            transformed_ids = tuple(vertex_ids[point] for point in transformed)
            global_cell_id = cell_ids.get(tuple(sorted(transformed_ids)))
            if global_cell_id is None:
                raise ArithmeticError(f"local cell {local_cell} is not a global Kuhn tetrahedron")
            global_cell = cells[global_cell_id]
            positions = [global_cell.index(vertex) for vertex in transformed_ids]
            if sorted(positions) != [0, 1, 2, 3]:
                raise ArithmeticError("local-to-global cell vertex map is not a permutation")
            local_to_global.append(global_cell_id)
            position_maps.append(positions)
            transported_cells.append(transformed)
        if len(set(local_to_global)) != len(local_to_global):
            raise ArithmeticError("a patch maps two local cells to one global cell")
        incident_local = [i for i, cell in enumerate(reference_cells)
                          if all(point in cell for point in reference_target)]
        incident_global = [local_to_global[i] for i in incident_local]
        if set(incident_global) != set(actual_incidence):
            missing = sorted(set(actual_incidence) - set(incident_global))
            extra = sorted(set(incident_global) - set(actual_incidence))
            raise ArithmeticError(f"incomplete target star: missing={missing}, extra={extra}")
        incident_positions = [
            [transported_cells[i].index(point) for point in transported_target]
            for i in incident_local]
        parameters = {"degree": degree, **spec["parameters"], "scale": str(size)}
        anchor_name, anchor = spec["anchor"]
        parameters[anchor_name] = physical(anchor)
        argv = ["python3", f"research/ridgway_freudenthal/{spec['module']}.py",
                f"--degree={degree}"]
        argv.extend(f"--{key}={value}" for key, value in spec["cli"].items())
        argv.extend([f"--{anchor_name}=" + ",".join(parameters[anchor_name]),
                     f"--scale={size}"])
        sides = [(axis, side) for axis, side in boundary_sides(canonical_points[0], n)
                 if all(point[axis] == canonical_points[0][axis] for point in canonical_points)]
        return {
            "target_id": target_id, "class": spec["class"],
            "orientation": spec["orientation"],
            "target_global_vertex_ids": list(target_vertices),
            "target_lattice_vertices": [list(point) for point in canonical_points],
            "boundary_faces": [{"axis": AXES[axis], "side": side} for axis, side in sides],
            "zero_source_image": spec["zero_source_image"],
            "constructor": {
                "module": f"research.ridgway_freudenthal.{spec['module']}",
                "function": "construct", "kwargs": parameters,
            },
            "constructor_argv": argv,
            "transport": {
                "module": f"research.ridgway_freudenthal.{spec['module']}",
                "function": "transport",
                "kwargs": {key: value for key, value in parameters.items() if key != "degree"},
            },
            "reference_patch": template_key,
            "reference_target": [list(point) for point in reference_target],
            "reference_target_to_canonical_target": endpoint_order,
            "reference_zero_lattice": list(zero),
            "reference_zero_physical": physical(zero),
            "reference_to_global_component": list(permutation),
            "coordinate_sign": sign, "orthogonal_determinant": determinant,
            "physical_vertex_to_reference_vertex": list(vertex_order),
            "patch_vertex_to_global_vertex": patch_vertex_ids,
            "local_cell_to_global_cell": local_to_global,
            "local_vertex_to_global_vertex_position": position_maps,
            "incident_local_cells": incident_local,
            "incident_global_cells": incident_global,
            "global_incident_cells": list(actual_incidence),
            "target_vertex_positions_in_incident_local_cells": incident_positions,
            "target_vertex_positions_in_incident_global_cells": [
                [position_maps[cell][position] for position in positions]
                for cell, positions in zip(incident_local, incident_positions)],
        }

    vertex_patches = [
        embed(vertex_specification(point, n), vertex, (vertex,), vertex_incidence[vertex])
        for vertex, point in enumerate(lattice_vertices)]
    edge_patches = [
        embed(edge_specification(lattice_vertices[edge[0]], lattice_vertices[edge[1]], n),
              edge_id, edge, edge_incidence[edge])
        for edge_id, edge in enumerate(edges)]
    vertex_counts = Counter(patch["class"] for patch in vertex_patches)
    edge_counts = Counter(patch["class"] for patch in edge_patches)
    expected_vertices = {
        "interior": (n - 1)**3, "face": 6 * (n - 1)**2,
        "crease_same": 6 * (n - 1), "crease_mixed": 6 * (n - 1),
        "corner_same": 2, "corner_mixed": 6,
    }
    expected_edges = {
        "body_diagonal": n**3,
        "interior_face_diagonal": 3 * n**2 * (n - 1),
        "boundary_face_diagonal": 6 * n**2,
        "interior_axial": 3 * n * (n - 1)**2,
        "boundary_axial": 12 * n * (n - 1),
        "boundary_crease_same": 6 * n, "boundary_crease_mixed": 6 * n,
    }
    if dict(vertex_counts) != expected_vertices or dict(edge_counts) != expected_edges:
        raise ArithmeticError("global vertex/edge class census is incomplete")
    if len(lattice_vertices) != (n + 1)**3 or len(edges) != 7*n**3 + 9*n**2 + 3*n:
        raise ArithmeticError("global mesh vertex/edge counts are inconsistent")
    boundary_orientations = sorted({patch["orientation"] for patch in vertex_patches
                                    if patch["class"] != "interior"})
    if boundary_orientations != sorted(BOUNDARY_VERTEX_ORIENTATIONS):
        raise ArithmeticError("global boundary-vertex orientation census is incomplete")
    all_patches = vertex_patches + edge_patches
    return {
        "schema": SCHEMA, "status": "PLANNED", "n": n, "degree": degree,
        "origin": [str(value) for value in origin], "cell_size": str(size),
        "mesh": {
            "vertex_order": "lexicographic lattice coordinates",
            "cell_order": "lexicographic cube origins, then kuhn_tets() order",
            "edge_order": "lexicographic componentwise-low/high global vertex ID pairs",
            "lattice_vertices": [list(point) for point in lattice_vertices],
            "physical_vertices": [physical(point) for point in lattice_vertices],
            "cube_origins": [list(cube) for cube in cubes], "cells": cells,
            "edges": [list(edge) for edge in edges],
        },
        "reference_patches": templates,
        "vertex_patches": vertex_patches, "edge_patches": edge_patches,
        "census": {
            "cubes": len(cubes), "cells": len(cells), "vertices": len(lattice_vertices),
            "edges": len(edges), "vertex_classes": dict(sorted(vertex_counts.items())),
            "edge_classes": dict(sorted(edge_counts.items())),
            "boundary_vertex_orientations": boundary_orientations,
            "patches": len(all_patches),
            "maximum_patch_cells": max(len(patch["local_cell_to_global_cell"])
                                       for patch in all_patches),
            "all_patch_cells_in_mesh": True, "all_target_stars_complete": True,
        },
        "semantics": {
            "cell_maps": "local indices use the existing transported operator's positive cell order",
            "vertex_positions": "row c maps each transported local cell vertex to its global cell position",
            "reference_vertices": "patch_vertex_to_global_vertex follows the reference template vertex list",
            "target_order": "reference target order is inherited, even when inversion reverses canonical endpoints",
            "physical_map": "origin + cell_size * lattice; all physical numbers are exact rational strings",
            "scope": "patch embeddings and full target-star census; no local lift execution or global norm claim",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, required=True, help="Cubes per axis; at least two")
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    parser.add_argument("--origin", default="0,0,0", help="Three exact physical mesh-origin coordinates")
    parser.add_argument("--cell-size", help="Positive exact cube size; default 1/n")
    parser.add_argument("--output", type=Path, help="Create a new complete JSON plan; default stdout")
    args = parser.parse_args()
    try:
        result = construct(args.n, args.degree, args.origin.split(","), args.cell_size)
        if args.output is None:
            json.dump(result, sys.stdout, separators=(",", ":"))
            sys.stdout.write("\n")
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, separators=(",", ":"))
                stream.write("\n")
            print(json.dumps({
                "schema": SCHEMA, "status": result["status"], "n": args.n,
                "degree": args.degree, "output": str(args.output),
                "origin": result["origin"], "cell_size": result["cell_size"],
                "census": result["census"],
            }, sort_keys=True))
        return 0
    except (ValueError, ArithmeticError, OSError) as exc:
        print(f"global_patch_plan: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
