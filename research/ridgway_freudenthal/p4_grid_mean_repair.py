"""Assemble a quartic divergence-mean repair on a rectangular Kuhn grid.

Consumes the existing exact two-cube operator; never recomputes that operator.
The face-tree construction is linear, but no mesh-uniform norm is claimed.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import sys
from typing import Any

try:
    from .kuhn import kuhn_tets
    from .p4_mean_repair import apply, gradients, indices
except ImportError:
    from kuhn import kuhn_tets
    from p4_mean_repair import apply, gradients, indices

Node = tuple[int, int, int]
Cell = tuple[Node, ...]
Field = dict[Node, list[F]]


def rational(value: Any, name: str) -> F:
    if isinstance(value, bool) or not isinstance(value, (int, str, F)):
        raise ValueError(f"{name} must be an integer or exact rational string")
    return F(value)


def grid(shape: tuple[int, int, int]) -> tuple[list[Node], list[Cell]]:
    cubes = list(product(*(range(n) for n in shape)))
    cells = [tuple(tuple(p[j]+cube[j] for j in range(3)) for p in tet)
             for cube in cubes for tet in kuhn_tets()]
    return cubes, cells


def add_patch(operator: dict, a: Node, b: Node, targets: dict[int, F],
              cell_ids: dict[Cell, int], field: Field) -> int:
    """Transport cell identities, coordinates, and vector components together."""
    differences = [i for i in range(3) if a[i] != b[i]]
    if len(differences) != 1 or abs(a[differences[0]]-b[differences[0]]) != 1:
        raise ValueError("A repair patch must contain two face-adjacent cubes")
    axis = differences[0]
    permutation = (axis,)+tuple(i for i in range(3) if i != axis)
    base = tuple(min(a[i], b[i]) for i in range(3))

    def transport(point, scale):
        mapped = [0, 0, 0]
        for old, new in enumerate(permutation):
            mapped[new] = point[old]+scale*base[new]
        return tuple(mapped)

    means = [targets.get(cell_ids[tuple(sorted(transport(v, 1) for v in tet))], F(0))
             for tet in operator["cells"]]
    values = apply(operator, means)
    for node, value in zip(operator["nodes_times_four"], values):
        point = transport(node, 4)
        for old, new in enumerate(permutation):
            coefficient = F(value[old])
            if coefficient:
                field.setdefault(point, [F(0), F(0), F(0)])[new] += coefficient
    return axis


def check_field(cells: list[Cell], field: Field, means: list[F],
                shape: tuple[int, int, int]) -> None:
    """Check the assembled output itself before it can leave the program."""
    for point, value in field.items():
        if any(value) and any(not 0 < point[j] < 4*shape[j] for j in range(3)):
            raise ArithmeticError(f"Nonzero boundary coefficient at {point}")
    betas = indices(3)
    zero = (F(0), F(0), F(0))
    for cell_id, tet in enumerate(cells):
        grad = gradients(tet)
        total = F(0)
        for beta in betas:
            divergence = F(0)
            for i in range(4):
                alpha = list(beta)
                alpha[i] += 1
                node = tuple(sum(alpha[k]*tet[k][j] for k in range(4)) for j in range(3))
                coefficient = field.get(node, zero)
                divergence += 4*sum(grad[i][j]*coefficient[j] for j in range(3))
            if sum(n > 0 for n in beta) <= 2 and divergence:
                raise ArithmeticError(f"Nonzero edge divergence in cell {cell_id}, beta {beta}")
            total += divergence
        if total/20 != means[cell_id]:
            raise ArithmeticError(f"Wrong mean in cell {cell_id}: {total/20}, wanted {means[cell_id]}")


def repair(document: dict) -> dict:
    """Return sparse continuous Bernstein coefficients for exact cell means."""
    if not isinstance(document, dict):
        raise ValueError("The input must be a JSON object")
    dimensions = document.get("shape")
    if (not isinstance(dimensions, list) or len(dimensions) != 3
            or any(type(n) is not int or n < 1 for n in dimensions)):
        raise ValueError("shape must contain three positive integers")
    shape = tuple(dimensions)
    count = shape[0]*shape[1]*shape[2]
    if count < 2:
        raise ValueError("This assembly requires at least two cubes")
    raw = document.get("cell_means")
    if not isinstance(raw, list) or len(raw) != 6*count:
        raise ValueError(f"cell_means must contain exactly {6*count} entries")
    means = [rational(v, "cell mean") for v in raw]
    if sum(means):
        raise ValueError("The cell means must sum to zero")
    size = rational(document.get("cell_size", 1), "cell_size")
    if size <= 0:
        raise ValueError("cell_size must be positive")
    origin_raw = document.get("origin", [0, 0, 0])
    if not isinstance(origin_raw, list) or len(origin_raw) != 3:
        raise ValueError("origin must contain three coordinates")
    origin = [rational(v, "origin coordinate") for v in origin_raw]
    with Path(__file__).with_name("p4_mean_repair_basis.json").open(encoding="utf-8") as source:
        operator = json.load(source)
    if operator.get("schema") != "freudenthal-p4-mean-repair/v1":
        raise ValueError("Unsupported installed two-cube operator schema")
    cubes, cells = grid(shape)
    cube_ids = {cube: i for i, cube in enumerate(cubes)}
    cell_ids = {tuple(sorted(tet)): i for i, tet in enumerate(cells)}
    remaining = [means[6*i:6*i+6] for i in range(count)]
    field: Field = {}
    patches = [0, 0, 0]
    # Decreasing lexicographic order visits every child before its parent.
    for cube in reversed(cubes[1:]):
        child_id = cube_ids[cube]
        residual = remaining[child_id]
        parent = list(cube)
        direction = next(j for j in range(3) if parent[j])
        parent[direction] -= 1
        parent = tuple(parent)
        parent_id = cube_ids[parent]
        transfer = sum(residual)
        if any(residual):
            target = {6*child_id+j: residual[j] for j in range(6)}
            target[6*parent_id] = -transfer
            axis = add_patch(operator, cube, parent, target, cell_ids, field)
            patches[axis] += 1
        remaining[parent_id][0] += transfer
        remaining[child_id] = [F(0)]*6
    # The root's residual has zero sum, but its individual cell means may not vanish.
    if sum(remaining[0]):
        raise ArithmeticError("Face-tree elimination lost the global zero-sum invariant")
    if any(remaining[0]):
        neighbor = [0, 0, 0]
        neighbor[next(j for j in range(3) if shape[j] > 1)] = 1
        axis = add_patch(operator, cubes[0], tuple(neighbor),
                         dict(enumerate(remaining[0])), cell_ids, field)
        patches[axis] += 1
    field = {p: v for p, v in field.items() if any(v)}
    check_field(cells, field, means, shape)
    nodes = sorted(field)
    return {"schema": "freudenthal-p4-grid-mean-repair/v1", "status": "CONSTRUCTED",
            "shape": list(shape), "origin": [str(v) for v in origin], "cell_size": str(size),
            "cells_grid_coordinates": cells, "cell_means": [str(v) for v in means],
            "nodes_times_four": nodes,
            "velocity_coefficients": [[str(size*v) for v in field[p]] for p in nodes],
            "coefficient_semantics": "continuous quartic Bernstein coefficients; omitted nodes are zero",
            "coordinate_semantics": "physical point = origin + cell_size * grid_coordinate",
            "patches_by_axis": dict(zip(("x", "y", "z"), patches)),
            "edge_residual_max": "0", "mean_residual_max": "0",
            "norm_scope": "finite grid only; no mesh-uniform bound claimed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON with shape and 6*product(shape) exact cell_means")
    parser.add_argument("--output", type=Path, help="Create a new output file, otherwise print JSON")
    args = parser.parse_args()
    try:
        with args.input.open(encoding="utf-8") as source:
            result = repair(json.load(source))
        text = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(text)
        else:
            print(text, end="")
        print(f"CONSTRUCTED: {len(result['cell_means'])} cells, "
              f"{len(result['nodes_times_four'])} nonzero nodes, "
              f"patches {result['patches_by_axis']}; exact residuals 0", file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError, IndexError, TypeError) as exc:
        print(f"p4_grid_mean_repair: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
