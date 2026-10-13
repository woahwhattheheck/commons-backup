"""Exact element-bubble inverse for edge-zero, mean-zero P3/P4 pressure.

The velocity has zero trace on every tetrahedron face. This is an element-local
operator and bound; it does not assert the complete mesh-uniform theorem.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction as F
import json
from math import factorial
from pathlib import Path
import sys

try:
    from .kuhn import kuhn_tets
    from .p4_mean_repair import cross, indices
except ImportError:
    from kuhn import kuhn_tets
    from p4_mean_repair import cross, indices

SCHEMA = "freudenthal-cell-bubble-lift/v1"


def rational(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, str, F)):
        raise ValueError(f"{name} must be an integer or exact rational string")
    try:
        return F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{name} must be a finite exact rational") from exc


def parameters(degree, cell_index, origin, scale):
    if isinstance(degree, bool) or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    if isinstance(cell_index, bool) or not isinstance(cell_index, int) or not 0 <= cell_index < 6:
        raise ValueError("cell_index must be an integer from 0 through 5")
    if not isinstance(origin, (tuple, list)) or len(origin) != 3:
        raise ValueError("origin must contain three exact coordinates")
    origin = tuple(rational(v, "origin coordinate") for v in origin)
    scale = rational(scale, "scale")
    if scale <= 0:
        raise ValueError("scale must be positive")
    return degree, cell_index, origin, scale


def point(cell, alpha):
    return tuple(sum(alpha[i]*cell[i][j] for i in range(4)) for j in range(3))


def physical_gradients(cell):
    a = cell[0]
    u, v, w = [tuple(p[j]-a[j] for j in range(3)) for p in cell[1:]]
    determinant = sum(u[j]*cross(v, w)[j] for j in range(3))
    if determinant <= 0:
        raise ArithmeticError("cell must have positive orientation")
    tail = [tuple(value/determinant for value in row)
            for row in (cross(v, w), cross(w, u), cross(u, v))]
    return [tuple(-sum(row[j] for row in tail) for j in range(3))]+tail


def source_data(degree):
    betas = indices(degree-1)
    residual = [i for i, beta in enumerate(betas) if sum(v > 0 for v in beta) >= 3]
    dependent = betas.index((0, 1, 1, 1) if degree == 4 else (1, 1, 1, 1))
    free = [i for i in residual if i != dependent]
    basis = [[int(i == row)-int(i == dependent) for row in free]
             for i in range(len(betas))]
    return betas, residual, dependent, free, basis


def bernstein_gram_entry(alpha, beta):
    n = sum(alpha)
    if sum(beta) != n:
        raise ArithmeticError("Bernstein degrees differ")
    value = F(factorial(n)**2, factorial(2*n+3))
    for a, b in zip(alpha, beta):
        value *= F(factorial(a+b), factorial(a)*factorial(b))
    return value


def inverse_matrix(matrix):
    size = len(matrix)
    rows = [[F(value) for value in row]+[F(int(i == j)) for j in range(size)]
            for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = next((i for i in range(column, size) if rows[i][column]), None)
        if pivot is None:
            raise ArithmeticError("independent pressure Gram matrix is singular")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value/divisor for value in rows[column]]
        for i in range(size):
            if i == column or not rows[i][column]:
                continue
            factor = rows[i][column]
            rows[i] = [a-factor*b for a, b in zip(rows[i], rows[column])]
    return [row[size:] for row in rows]


def local_bounds(degree, cell, matrix, betas, dependent, free):
    dep = betas[dependent]
    gram = [[bernstein_gram_entry(betas[a], betas[b])
             - bernstein_gram_entry(betas[a], dep)
             - bernstein_gram_entry(dep, betas[b])
             + bernstein_gram_entry(dep, dep) for b in free] for a in free]
    inverse = inverse_matrix(gram)
    gamma = max(sum(abs(value) for value in row) for row in inverse)
    maximum_row_norm_squared = max(sum(value*value for value in row) for row in matrix)
    gradients = physical_gradients(cell)
    gradient_square_sum = sum(value*value for row in gradients for value in row)
    # Jensen in the lower-degree Bernstein basis, then Cauchy-Schwarz over
    # four barycentric gradients, three velocity components and volume 1/6.
    coefficient_bound = F(1, 6)*3*degree**2*4*gradient_square_sum*maximum_row_norm_squared
    return {
        "reference_volume": "1/6",
        "maximum_scalar_row_norm_squared": str(maximum_row_norm_squared),
        "barycentric_gradient_square_sum": str(gradient_square_sum),
        "reference_seminorm_squared_per_free_coordinate_norm_squared": str(coefficient_bound),
        "physical_seminorm_squared_per_free_coordinate_norm_squared": str(coefficient_bound),
        "reference_pressure_gram_in_free_coordinates": [[str(v) for v in row] for row in gram],
        "reference_inverse_pressure_gram": [[str(v) for v in row] for row in inverse],
        "reference_inverse_gram_absolute_row_sum_bound": str(gamma),
        "physical_inverse_gram_absolute_row_sum_bound": str(gamma),
        "seminorm_squared_per_pressure_l2_squared": str(coefficient_bound*gamma),
        "scale_independent_pressure_bound": True,
        "sharpness": "conservative bound, not an optimal generalized eigenvalue",
        "derivation": "CELL_BUBBLE_LIFT.md",
    }


def check_operator(operator):
    """Reconstruct every physical pressure row, including all face interiors."""
    degree = operator["degree"]
    width = operator["source_dimension"]
    betas, residual, dependent, free, source_basis = source_data(degree)
    if operator["pressure_indices"] != [list(beta) for beta in betas]:
        raise ArithmeticError("pressure coefficient order changed")
    if (operator["free_source_indices"] != free
            or operator["dependent_source_index"] != dependent
            or operator["source_basis"] != source_basis):
        raise ArithmeticError("pressure source image changed")
    cell = [tuple(F(v) for v in p) for p in operator["cells"][0]]
    alphas = [alpha for alpha in indices(degree) if all(alpha)]
    nodes = [tuple(F(v) for v in p) for p in operator["nodes_times_degree"]]
    if (nodes != [point(cell, alpha) for alpha in alphas]
            or operator["velocity_indices"] != [list(alpha) for alpha in alphas]
            or operator["unknowns"] != 3*len(nodes)
            or width != len(free)):
        raise ArithmeticError("strictly interior velocity coefficient indexing changed")
    if len(set(nodes)) != len(nodes):
        raise ArithmeticError("velocity coefficient nodes are not distinct")
    matrix = [[F(0)]*width for _ in range(3*len(nodes))]
    for row, column, value in operator["basis"]:
        if not 0 <= row < len(matrix) or not 0 <= column < width:
            raise ArithmeticError("sparse operator index is outside its declared shape")
        matrix[row][column] += F(value)
    lookup = {alpha: i for i, alpha in enumerate(alphas)}
    gradients = physical_gradients(cell)
    total = [F(0)]*width
    for pressure_row, beta in enumerate(betas):
        divergence = [F(0)]*width
        for i in range(4):
            alpha = list(beta)
            alpha[i] += 1
            node = lookup.get(tuple(alpha))
            if node is None:
                continue
            for component in range(3):
                factor = degree*gradients[i][component]
                for column, value in enumerate(matrix[3*node+component]):
                    divergence[column] += factor*value
        if divergence != source_basis[pressure_row]:
            raise ArithmeticError(f"pressure reconstruction failed at beta {beta}")
        total = [a+b for a, b in zip(total, divergence)]
    if any(total):
        raise ArithmeticError("constructed divergence has nonzero cell mean")
    return {
        "arithmetic": "exact rational",
        "basis_columns": width,
        "pressure_rows": len(betas),
        "residual_rows": len(residual),
        "protected_vertex_edge_rows": len(betas)-len(residual),
        "zero_mean_rows": 1,
        "pressure_residual_max": "0",
        "mean_residual_max": "0",
        "velocity_face_trace": "zero on all four faces; only strictly positive alpha are present",
    }


def construct_reference(degree=4, cell_index=0):
    degree, cell_index, _, _ = parameters(degree, cell_index, (0, 0, 0), 1)
    cell = tuple(tuple(F(v) for v in p) for p in kuhn_tets()[cell_index])
    betas, residual, dependent, free, source_basis = source_data(degree)
    alphas = [alpha for alpha in indices(degree) if all(alpha)]
    lookup = {alpha: i for i, alpha in enumerate(alphas)}
    width = len(free)
    matrix = [[F(0)]*width for _ in range(3*len(alphas))]
    for column, pressure_row in enumerate(free):
        beta = betas[pressure_row]
        missing = beta.index(0)
        doubled = 0 if degree == 4 else beta.index(2)
        alpha = tuple(1+int(i == doubled and degree == 5) for i in range(4))
        node = lookup[alpha]
        for component in range(3):
            matrix[3*node+component][column] = (
                cell[missing][component]-cell[doubled][component])/degree
    sparse = [[row, column, str(value)]
              for row, values in enumerate(matrix)
              for column, value in enumerate(values) if value]
    operator = {
        "schema": SCHEMA,
        "status": "CONSTRUCTED",
        "degree": degree,
        "pressure_degree": degree-1,
        "kuhn_cell_index": cell_index,
        "cells": [[[str(v) for v in p] for p in cell]],
        "origin": ["0", "0", "0"],
        "scale": "1",
        "coefficient_convention": "normalized Bernstein coefficients, not point values",
        "pressure_indices": [list(beta) for beta in betas],
        "residual_source_indices": residual,
        "free_source_indices": free,
        "dependent_source_index": dependent,
        "source_dimension": width,
        "source_basis": source_basis,
        "source_relation": "all vertex/edge coefficients are zero; sum of all cell coefficients is zero",
        "velocity_indices": [list(alpha) for alpha in alphas],
        "nodes_times_degree": [[str(v) for v in point(cell, alpha)] for alpha in alphas],
        "velocity_component_order": "x,y,z at each displayed coefficient node",
        "unknowns": len(matrix),
        "basis": sparse,
        "nonzero_operator_entries": len(sparse),
        "bounds": local_bounds(degree, cell, matrix, betas, dependent, free),
        "scope": "element-local residual isomorphism; global assembly is separate",
    }
    operator["exact_identities"] = check_operator(operator)
    return operator


def transport(operator, origin=(0, 0, 0), scale=1):
    """Translate and scale a reference operator, including one read from JSON."""
    if not isinstance(operator, dict) or operator.get("schema") != SCHEMA:
        raise ValueError("operator must be a cell-bubble reference lift")
    degree, cell_index, origin, scale = parameters(
        operator.get("degree"), operator.get("kuhn_cell_index"), origin, scale)
    expected = [[tuple(F(v) for v in p) for p in kuhn_tets()[cell_index]]]
    actual = [[tuple(F(v) for v in p) for p in cell] for cell in operator["cells"]]
    if (actual != expected or operator.get("origin") != ["0", "0", "0"]
            or F(operator.get("scale", "0")) != 1):
        raise ValueError("transport requires a unit reference operator")
    result = deepcopy(operator)
    result["origin"] = [str(v) for v in origin]
    result["scale"] = str(scale)
    result["cells"] = [[[str(origin[j]+scale*F(p[j])) for j in range(3)]
                        for p in cell] for cell in operator["cells"]]
    result["nodes_times_degree"] = [
        [str(degree*origin[j]+scale*F(p[j])) for j in range(3)]
        for p in operator["nodes_times_degree"]]
    result["basis"] = [[row, column, str(scale*F(value))]
                       for row, column, value in operator["basis"]]
    bounds = result["bounds"]
    bounds["physical_seminorm_squared_per_free_coordinate_norm_squared"] = str(
        scale**3*F(bounds["reference_seminorm_squared_per_free_coordinate_norm_squared"]))
    bounds["physical_inverse_gram_absolute_row_sum_bound"] = str(
        F(bounds["reference_inverse_gram_absolute_row_sum_bound"])/scale**3)
    bounds["physical_volume"] = str(scale**3/6)
    result["exact_identities"] = check_operator(result)
    return result


def construct(degree=4, cell_index=0, origin=(0, 0, 0), scale=1):
    degree, cell_index, origin, scale = parameters(degree, cell_index, origin, scale)
    return transport(construct_reference(degree, cell_index), origin, scale)


def trace_from_free(operator, values):
    width = operator["source_dimension"]
    if not isinstance(values, (tuple, list)) or len(values) != width:
        raise ValueError(f"free trace must contain {width} coefficients")
    free = [rational(value, "free pressure coefficient") for value in values]
    return [sum(F(entry)*value for entry, value in zip(row, free))
            for row in operator["source_basis"]]


def apply(operator, trace):
    """Apply a constructed or JSON-loaded operator to the full pressure array."""
    if not isinstance(operator, dict) or operator.get("schema") != SCHEMA:
        raise ValueError("operator must be a constructed cell-bubble lift")
    degree = operator["degree"]
    betas, residual, dependent, free_rows, _ = source_data(degree)
    if not isinstance(trace, (tuple, list)) or len(trace) != len(betas):
        raise ValueError(f"complete trace must contain all {len(betas)} pressure coefficients")
    values = [rational(value, "pressure coefficient") for value in trace]
    for row, beta in enumerate(betas):
        if sum(value > 0 for value in beta) <= 2 and values[row]:
            raise ValueError(f"pressure coefficient at beta {beta} must be zero on vertices/edges")
    total = sum(values)
    if total:
        raise ValueError(f"cell pressure coefficient sum must be zero; residual {total}")
    free = [values[row] for row in free_rows]
    expected = trace_from_free(operator, free)
    if values != expected:
        raise ValueError("pressure coefficients are outside the displayed source image")
    coefficients = [[F(0)]*3 for _ in operator["nodes_times_degree"]]
    for row, column, value in operator["basis"]:
        coefficients[row//3][row % 3] += F(value)*free[column]
    reference_gram = [[F(value) for value in row]
                      for row in operator["bounds"]["reference_pressure_gram_in_free_coordinates"]]
    pressure_l2_squared = F(operator["scale"])**3*sum(
        free[i]*reference_gram[i][j]*free[j]
        for i in range(len(free)) for j in range(len(free)))
    coordinate_norm_squared = sum(value*value for value in free)
    bounds = operator["bounds"]
    return {
        "status": "APPLIED",
        "pressure_coefficients": [str(value) for value in values],
        "free_pressure_coefficients": [str(value) for value in free],
        "velocity_coefficients": [[str(value) for value in row] for row in coefficients],
        "cell_mean": "0",
        "pressure_l2_squared": str(pressure_l2_squared),
        "seminorm_squared_upper_bound_from_free_coordinates": str(
            F(bounds["physical_seminorm_squared_per_free_coordinate_norm_squared"])*coordinate_norm_squared),
        "seminorm_squared_upper_bound_from_pressure_l2": str(
            F(bounds["seminorm_squared_per_pressure_l2_squared"])*pressure_l2_squared),
    }


def csv_values(value, name):
    parts = value.split(",")
    if not parts or any(not part.strip() for part in parts):
        raise ValueError(f"{name} must be a comma-separated list of exact numbers")
    return [rational(part.strip(), name) for part in parts]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cell", type=int, choices=range(6), default=0)
    group.add_argument("--all-cells", action="store_true")
    parser.add_argument("--origin", default="0,0,0", help="three comma-separated exact coordinates")
    parser.add_argument("--scale", default="1", help="positive exact isotropic scale")
    data = parser.add_mutually_exclusive_group()
    data.add_argument("--trace", help="complete pressure array in native Bernstein order, comma-separated")
    data.add_argument("--free-trace", help="independent pressure coefficients in native order, comma-separated")
    parser.add_argument("--output", type=Path, help="create a new JSON file; existing paths are refused")
    args = parser.parse_args()
    try:
        origin = csv_values(args.origin, "origin")
        _, _, origin, scale = parameters(args.degree, args.cell, origin, args.scale)
        if args.all_cells and (args.trace is not None or args.free_trace is not None):
            raise ValueError("explicit trace data requires a single --cell")
        trace = None if args.trace is None else csv_values(args.trace, "trace")
        free = None if args.free_trace is None else csv_values(args.free_trace, "free trace")
        operators = []
        for cell_index in range(6) if args.all_cells else (args.cell,):
            operator = construct(args.degree, cell_index, origin, scale)
            if trace is None:
                values = free if free is not None else [
                    (-1)**i*(i+1) for i in range(operator["source_dimension"])]
                complete = trace_from_free(operator, values)
            else:
                complete = trace
            operator["applied"] = apply(operator, complete)
            operators.append(operator)
        result = ({"schema": "freudenthal-cell-bubble-batch/v1", "status": "CONSTRUCTED",
                   "degree": args.degree, "operators": operators}
                  if args.all_cells else operators[0])
        output = json.dumps(result, indent=2, sort_keys=True)+"\n"
        if args.output is None:
            print(output, end="")
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(output)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError, TypeError) as exc:
        print(f"cell-bubble lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
