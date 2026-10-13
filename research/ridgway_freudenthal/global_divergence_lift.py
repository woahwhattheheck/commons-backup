"""Exact global divergence lift on a uniform Kuhn cube, for degrees four and five.

Apply retained local matrices in mean, vertex, edge and cell-bubble order.
The output is a shared continuous Dirichlet velocity whose full Bernstein
divergence equals the supplied pressure. See GLOBAL_DIVERGENCE_LIFT.md.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import sys

import global_patch_plan as patches
import mean_energy_lift as mean_lift
from cell_bubble_lift import bernstein_gram_entry, physical_gradients, rational, source_data
from p4_mean_repair import indices

SCHEMA = "freudenthal-global-divergence-lift/v1"
BUNDLE_SCHEMA = "freudenthal-global-lift-operators/v1"
VERTEX_CLASSES = ("interior", "face", "crease_same", "crease_mixed",
                  "corner_same", "corner_mixed")
EDGE_CLASSES = ("body_diagonal", "interior_face_diagonal",
                "boundary_face_diagonal", "interior_axial", "boundary_axial",
                "boundary_crease_same", "boundary_crease_mixed")
ZERO = (F(0), F(0), F(0))


def integer(value, name):
    number = rational(value, name)
    if number.denominator != 1:
        raise ValueError(f"{name} must be an integer")
    return number.numerator


def triple(values, name, integral=False):
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(f"{name} must contain three coordinates")
    convert = integer if integral else rational
    return tuple(convert(value, name) for value in values)


def parameters(n, degree, origin, cell_size):
    if type(n) is not int or n < 2:
        raise ValueError("n must be an integer at least two; local patches require two cubes")
    if type(degree) is not int or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    origin = triple(origin, "origin")
    size = F(1, n) if cell_size is None else rational(cell_size, "cell_size")
    if size <= 0:
        raise ValueError("cell_size must be positive")
    return n, degree, origin, size


def point(cell, alpha):
    return tuple(sum(alpha[i]*cell[i][j] for i in range(4)) for j in range(3))


def blob_sha(data):
    return sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


def load_operators(path=None):
    """Load the production matrix asset and retain the exact byte provenance."""
    path = Path(path) if path is not None else Path(__file__).with_name("global_lift_operators.json")
    data = path.read_bytes()
    value = json.loads(data)
    if not isinstance(value, dict) or value.get("schema") != BUNDLE_SCHEMA:
        raise ValueError("operator asset has an unsupported schema")
    return {"data": value, "provenance": {
        "file": path.name, "bytes": len(data),
        "sha256": sha256(data).hexdigest(), "git_blob": blob_sha(data)}}


def normalize_operator(entry, degree, name):
    if not isinstance(entry, dict) or entry.get("degree") != degree:
        raise ValueError(f"{name}: retained operator degree differs")
    cells = [tuple(triple(p, f"{name} reference vertex", True) for p in cell)
             for cell in entry["cells"]]
    if not cells or any(len(cell) != 4 for cell in cells):
        raise ValueError(f"{name}: invalid reference tetrahedra")
    nodes = [triple(node, f"{name} coefficient node", True)
             for node in entry["nodes_times_degree"]]
    if len(set(nodes)) != len(nodes):
        raise ValueError(f"{name}: duplicate coefficient node")
    labels = []
    for label in entry["target_coordinates"]:
        cell = label["cell"]
        beta = tuple(label["beta"])
        if (type(cell) is not int or not 0 <= cell < len(cells)
                or len(beta) != 4 or any(type(v) is not int or v < 0 for v in beta)
                or sum(beta) != degree-1):
            raise ValueError(f"{name}: invalid target coordinate")
        labels.append((cell, beta))
    free = list(entry["free_coordinate_indices"])
    if (len(set(free)) != len(free)
            or any(type(i) is not int or not 0 <= i < len(labels) for i in free)):
        raise ValueError(f"{name}: invalid free-coordinate list")
    source = [tuple(rational(v, f"{name} source coefficient") for v in row)
              for row in entry["source_basis"]]
    width = len(free)
    if len(source) != len(labels) or any(len(row) != width for row in source):
        raise ValueError(f"{name}: source matrix dimensions differ")
    for j, row in enumerate(free):
        if source[row] != tuple(F(int(i == j)) for i in range(width)):
            raise ValueError(f"{name}: free rows do not select the retained source coordinates")
    basis, seen = [], set()
    for row, column, value in entry["basis"]:
        if (type(row) is not int or not 0 <= row < 3*len(nodes)
                or type(column) is not int or not 0 <= column < width
                or (row, column) in seen):
            raise ValueError(f"{name}: invalid or repeated sparse matrix position")
        seen.add((row, column))
        coefficient = rational(value, f"{name} velocity coefficient")
        if coefficient:
            basis.append((row, column, coefficient))
    bound = rational(entry["h1_squared_bound_from_target_l2"], f"{name} H1 bound")
    if bound < 0:
        raise ValueError(f"{name}: negative squared-norm bound")
    return {"name": name, "cells": cells, "nodes": nodes, "labels": labels,
            "free": free, "source": source, "basis": basis, "bound": bound,
            "provenance": entry.get("provenance", {})}


def bind_patch(prepared, patch, operator, stage):
    """Bind retained reference rows to the planner's transported positive cells."""
    plan = prepared["plan"]
    template = plan["reference_patches"][patch["reference_patch"]]
    vertices = [tuple(p) for p in template["lattice_vertices"]]
    expected_cells = [tuple(vertices[i] for i in cell) for cell in template["cells"]]
    if operator["cells"] != expected_cells:
        raise ValueError(f"{stage} {patch['target_id']}: retained reference cell order differs")
    order = patch["physical_vertex_to_reference_vertex"]
    labels = []
    for local_cell, beta in operator["labels"]:
        moved_beta = tuple(beta[reference] for reference in order)
        cell, global_beta = patches.map_beta(patch, local_cell, moved_beta)
        labels.append((cell, prepared["beta_lookup"][global_beta]))
    expected = set()
    target = patch["target_global_vertex_ids"]
    pressure_degree = prepared["degree"]-1
    for cell in patch["global_incident_cells"]:
        mesh_cell = plan["mesh"]["cells"][cell]
        positions = [mesh_cell.index(vertex) for vertex in target]
        if stage == "vertex":
            beta = [0]*4
            beta[positions[0]] = pressure_degree
            expected.add((cell, prepared["beta_lookup"][tuple(beta)]))
        else:
            for power in range(1, pressure_degree):
                beta = [0]*4
                beta[positions[0]] = pressure_degree-power
                beta[positions[1]] = power
                expected.add((cell, prepared["beta_lookup"][tuple(beta)]))
    if len(labels) != len(expected) or set(labels) != expected:
        raise ValueError(f"{stage} {patch['target_id']}: target coordinate star is incomplete")
    permutation = tuple(patch["reference_to_global_component"])
    sign = patch["coordinate_sign"]
    zero = tuple(patch["reference_zero_lattice"])
    degree = prepared["degree"]
    mapped_nodes = []
    for node in operator["nodes"]:
        mapped = [degree*value for value in zero]
        for old, new in enumerate(permutation):
            mapped[new] += sign*node[old]
        node = tuple(mapped)
        if node not in prepared["node_set"]:
            raise ValueError(f"{stage} {patch['target_id']}: coefficient node is outside the mesh")
        mapped_nodes.append(node)
    return {"patch": patch, "operator": operator, "labels": labels,
            "nodes": mapped_nodes, "permutation": permutation, "sign": sign}


def prepare(n=2, degree=4, origin=(0, 0, 0), cell_size=None,
            operators=None, plan=None):
    """Prepare geometry, fixed local matrices and reusable mean-solve storage."""
    n, degree, origin, size = parameters(n, degree, origin, cell_size)
    if operators is None:
        operators = load_operators()
    if (not isinstance(operators, dict) or not isinstance(operators.get("data"), dict)
            or operators["data"].get("schema") != BUNDLE_SCHEMA):
        raise ValueError("operators must be the result of load_operators")
    if plan is None:
        plan = patches.construct(n, degree, origin, size)
    if (not isinstance(plan, dict) or plan.get("schema") != patches.SCHEMA
            or plan.get("status") != "PLANNED" or plan.get("n") != n
            or plan.get("degree") != degree
            or tuple(F(v) for v in plan.get("origin", ())) != origin
            or F(plan.get("cell_size", 0)) != size):
        raise ValueError("plan must match n, degree and the exact physical placement")
    lattice = [tuple(p) for p in plan["mesh"]["lattice_vertices"]]
    cells = [tuple(lattice[i] for i in cell) for cell in plan["mesh"]["cells"]]
    if cells != mean_lift.grid(n):
        raise ValueError("planned global cells differ from the mean solver's positive Kuhn order")
    betas, alphas = indices(degree-1), indices(degree)
    node_set = {point(cell, alpha) for cell in cells for alpha in alphas}
    gradients = [tuple(tuple(integer(v, "unit barycentric gradient") for v in row)
                       for row in physical_gradients(tuple(tuple(F(v) for v in p) for p in cell))) for cell in cells]
    prepared = {"n": n, "degree": degree, "origin": origin, "size": size,
                "plan": plan, "cells": cells, "betas": betas, "alphas": alphas,
                "beta_lookup": {beta: i for i, beta in enumerate(betas)},
                "node_set": node_set, "gradients": gradients,
                "operators_provenance": operators["provenance"],
                "mean_assembly": None, "gram": None}
    degree_data = operators["data"]["degrees"].get(str(degree))
    if not isinstance(degree_data, dict):
        raise ValueError("operator asset is missing the requested degree")
    for stage, family, classes in (("vertex", "vertices", VERTEX_CLASSES),
                                    ("edge", "edges", EDGE_CLASSES)):
        entries = degree_data.get(family)
        if not isinstance(entries, dict) or set(entries) != set(classes):
            raise ValueError(f"operator asset does not contain every {stage} class")
        normalized = {kind: normalize_operator(entries[kind], degree, stage+"-"+kind)
                      for kind in classes}
        prepared[stage+"_bindings"] = [
            bind_patch(prepared, patch, normalized[patch["class"]], stage)
            for patch in plan[stage+"_patches"]]
    return prepared


def pressure_values(values, prepared):
    rows, width = len(prepared["cells"]), len(prepared["betas"])
    if not isinstance(values, (list, tuple)) or len(values) != rows:
        raise ValueError(f"pressure must contain all {rows} tetrahedron arrays")
    result = []
    for cell, row in enumerate(values):
        if not isinstance(row, (list, tuple)) or len(row) != width:
            raise ValueError(f"pressure cell {cell} must contain all {width} Bernstein coefficients")
        result.append([rational(value, "pressure coefficient") for value in row])
    return result


def means(values):
    return [sum(row)/len(row) for row in values]


def add_field(target, source):
    for node, vector in source.items():
        previous = target.get(node, ZERO)
        result = tuple(previous[j]+vector[j] for j in range(3))
        if any(result):
            target[node] = result
        else:
            target.pop(node, None)


def assert_field(field, prepared):
    limit = prepared["n"]*prepared["degree"]
    for node, vector in field.items():
        if node not in prepared["node_set"]:
            raise ArithmeticError("assembled coefficient lies outside the global mesh")
        if any(value in (0, limit) for value in node) and any(vector):
            raise ArithmeticError("assembled velocity has nonzero Dirichlet boundary trace")


def divergence(field, prepared):
    degree = prepared["degree"]
    values = []
    for cell, gradients in zip(prepared["cells"], prepared["gradients"]):
        row = []
        for beta in prepared["betas"]:
            value = F(0)
            for i, gradient in enumerate(gradients):
                alpha = list(beta)
                alpha[i] += 1
                vector = field.get(point(cell, alpha), ZERO)
                value += degree*sum(gradient[j]*vector[j] for j in range(3))
            row.append(value)
        values.append(row)
    return values


def subtract(left, right):
    return [[a-b for a, b in zip(row_a, row_b)] for row_a, row_b in zip(left, right)]


def require_zero_means(values, stage):
    for cell, value in enumerate(means(values)):
        if value:
            raise ArithmeticError(f"{stage}: residual cell mean {cell} is {value}")


def require_zero_support(values, prepared, maximum, stage):
    selected = [i for i, beta in enumerate(prepared["betas"])
                if sum(value > 0 for value in beta) <= maximum]
    for cell, row in enumerate(values):
        for i in selected:
            if row[i]:
                raise ArithmeticError(f"{stage}: protected residual at cell {cell}, beta "
                                      f"{prepared['betas'][i]} is {row[i]}")


def apply_binding(binding, residual):
    operator = binding["operator"]
    trace = [residual[cell][row] for cell, row in binding["labels"]]
    free = [trace[i] for i in operator["free"]]
    for i, row in enumerate(operator["source"]):
        difference = trace[i]-sum(value*free[j] for j, value in enumerate(row))
        if difference:
            patch = binding["patch"]
            raise ValueError(f"incompatible {operator['name']} source at target "
                             f"{patch['target_id']} ({patch['orientation']}), "
                             f"coordinate {i}: residual {difference}")
    norm_squared = sum(value*value for value in trace)
    if not norm_squared:
        return {}, norm_squared
    values = [[F(0)]*3 for _ in operator["nodes"]]
    for row, column, coefficient in operator["basis"]:
        values[row//3][row % 3] += coefficient*free[column]
    field = {}
    for node, vector in zip(binding["nodes"], values):
        moved = [F(0)]*3
        for old, new in enumerate(binding["permutation"]):
            moved[new] = binding["sign"]*vector[old]
        if any(moved):
            field[node] = tuple(moved)
    return field, norm_squared


def patch_stage(residual, prepared, stage):
    field, applications, total_bound = {}, [], F(0)
    for binding in prepared[stage+"_bindings"]:
        local, norm_squared = apply_binding(binding, residual)
        add_field(field, local)
        bound = binding["operator"]["bound"]*norm_squared
        total_bound += bound
        patch = binding["patch"]
        applications.append({"target_id": patch["target_id"], "class": patch["class"],
                             "orientation": patch["orientation"],
                             "target_coordinates": len(binding["labels"]),
                             "nonzero_trace": bool(norm_squared),
                             "trace_coordinate_norm_squared": str(norm_squared),
                             "reference_local_h1_squared_upper_bound": str(bound)})
    assert_field(field, prepared)
    produced = divergence(field, prepared)
    following = subtract(residual, produced)
    require_zero_means(following, stage)
    require_zero_support(following, prepared, 1 if stage == "vertex" else 2, stage)
    if stage == "vertex":
        edge_rows = [i for i, beta in enumerate(prepared["betas"])
                     if sum(value > 0 for value in beta) == 2]
        for cell, row in enumerate(produced):
            if any(row[i] for i in edge_rows):
                raise ArithmeticError("vertex stage changed an edge-interior pressure coefficient")
    overlap = 64 if stage == "vertex" else 448
    return field, following, {
        "stage": stage, "patches": len(applications),
        "nonzero_patches": sum(item["nonzero_trace"] for item in applications),
        "full_target_coordinates": sum(item["target_coordinates"] for item in applications),
        "nonzero_velocity_nodes": len(field), "patch_overlap_upper_bound": overlap,
        "reference_h1_squared_upper_bound": str(overlap*total_bound),
        "physical_h1_squared_upper_bound": str(prepared["size"]**3*overlap*total_bound),
        "remaining_nonzero_pressure_coefficients": sum(bool(v) for row in following for v in row),
        "zero_cell_mean_rows": len(following), "applications": applications}


def cell_stage(residual, prepared):
    """Apply the explicit accepted cell-bubble inverse, without constructing its matrix."""
    degree, cells = prepared["degree"], prepared["cells"]
    betas, _, _, free, _ = source_data(degree)
    require_zero_means(residual, "cell-bubble input")
    require_zero_support(residual, prepared, 2, "cell-bubble input")
    field, total_norm, active = {}, F(0), 0
    for cell, row in zip(cells, residual):
        coordinate_norm = sum(row[i]*row[i] for i in free)
        total_norm += coordinate_norm
        active += bool(coordinate_norm)
        for pressure_row in free:
            value = row[pressure_row]
            if not value:
                continue
            beta = betas[pressure_row]
            missing = beta.index(0)
            doubled = 0 if degree == 4 else beta.index(2)
            alpha = tuple(1+int(degree == 5 and i == doubled) for i in range(4))
            node = point(cell, alpha)
            vector = tuple(value*(cell[missing][j]-cell[doubled][j])/degree for j in range(3))
            add_field(field, {node: vector})
    assert_field(field, prepared)
    following = subtract(residual, divergence(field, prepared))
    for cell, row in enumerate(following):
        if any(row):
            index = next(i for i, value in enumerate(row) if value)
            raise ArithmeticError(f"cell-bubble residual at cell {cell}, beta {betas[index]}: {row[index]}")
    bound = 36*total_norm
    return field, following, {
        "stage": "cell_bubble", "cells": len(cells), "nonzero_cells": active,
        "free_coordinates_per_cell": len(free), "nonzero_velocity_nodes": len(field),
        "reference_h1_squared_upper_bound": str(bound),
        "physical_h1_squared_upper_bound": str(prepared["size"]**3*bound),
        "remaining_nonzero_pressure_coefficients": 0, "full_pressure_residual_max": "0"}


def gram_entries(prepared):
    if prepared["gram"] is None:
        betas = prepared["betas"]
        prepared["gram"] = [
            (i, j, bernstein_gram_entry(betas[i], betas[j])*(1 if i == j else 2))
            for i in range(len(betas)) for j in range(i+1)]
    return prepared["gram"]


def pressure_l2_squared(values, prepared):
    return sum(coefficient*row[i]*row[j]
               for row in values for i, j, coefficient in gram_entries(prepared))


def energy(field, prepared):
    """Integrate all nine physical-gradient components on the unit lattice."""
    degree = prepared["degree"]
    result = F(0)
    for cell, gradients in zip(prepared["cells"], prepared["gradients"]):
        derivatives = []
        for beta in prepared["betas"]:
            values = [F(0)]*9
            for i, gradient in enumerate(gradients):
                alpha = list(beta)
                alpha[i] += 1
                vector = field.get(point(cell, alpha), ZERO)
                for component, value in enumerate(vector):
                    if value:
                        for axis, factor in enumerate(gradient):
                            if factor:
                                values[3*component+axis] += degree*factor*value
            derivatives.append(values)
        for i, j, coefficient in gram_entries(prepared):
            product = sum(a*b for a, b in zip(derivatives[i], derivatives[j]) if a and b)
            if product:
                result += coefficient*product
    return result


def physical_reconstruction(field, prepared):
    """Recompute every divergence row after the final physical transport."""
    origin, size, degree = prepared["origin"], prepared["size"], prepared["degree"]
    cells = [tuple(tuple(origin[j]+size*p[j] for j in range(3)) for p in cell)
             for cell in prepared["cells"]]
    physical_field = {
        tuple(degree*origin[j]+size*node[j] for j in range(3)):
        tuple(size*value for value in vector) for node, vector in field.items()}
    values = []
    for cell in cells:
        gradients = physical_gradients(cell)
        row = []
        for beta in prepared["betas"]:
            value = F(0)
            for i, gradient in enumerate(gradients):
                alpha = list(beta)
                alpha[i] += 1
                vector = physical_field.get(point(cell, alpha), ZERO)
                value += degree*sum(gradient[j]*vector[j] for j in range(3))
            row.append(value)
        values.append(row)
    return cells, physical_field, values


def construct(pressure, n=2, degree=4, origin=(0, 0, 0), cell_size=None,
              prepared=None, integrate_energy=False):
    """Return a complete exact right inverse for one compatible pressure."""
    n, degree, origin, size = parameters(n, degree, origin, cell_size)
    if prepared is None:
        prepared = prepare(n, degree, origin, size)
    elif (not isinstance(prepared, dict) or prepared.get("n") != n
          or prepared.get("degree") != degree or prepared.get("origin") != origin
          or prepared.get("size") != size):
        raise ValueError("prepared geometry must match the requested mesh and placement")
    original = pressure_values(pressure, prepared)
    cell_means = mean_lift.validate_means(n, means(original))
    if prepared["mean_assembly"] is None:
        prepared["mean_assembly"] = mean_lift.assemble(n)
    mean = mean_lift.construct(cell_means, degree=degree, subdivisions=n,
                              origin=(0, 0, 0), cell_size=1,
                              assembly=prepared["mean_assembly"])
    mean_field = {triple(node, "mean coefficient node", True):
                  tuple(F(value) for value in vector)
                  for node, vector in zip(mean["nodes_times_degree"], mean["velocity_coefficients"])}
    assert_field(mean_field, prepared)
    residual = subtract(original, [[F(v) for v in row]
                                   for row in mean["cell_divergence_coefficients"]])
    require_zero_means(residual, "mean")
    assembled = dict(mean_field)
    mean_energy = F(mean["energy"]["reference_seminorm_squared"])
    stages = [{
        "stage": "mean", "cell_mean_rows": len(original),
        "nonzero_velocity_nodes": len(mean_field),
        "reference_h1_squared_upper_bound": str(mean_energy),
        "physical_h1_squared_upper_bound": str(size**3*mean_energy),
        "energy_is_exact": True,
        "mean_solver": {key: mean["solver"][key] for key in
                        ("velocity_unknowns", "independent_mean_constraints", "reduced_dimension")},
        "remaining_nonzero_pressure_coefficients": sum(bool(v) for row in residual for v in row),
        "cell_mean_residual_max": "0"}]
    for stage in ("vertex", "edge"):
        field, residual, report = patch_stage(residual, prepared, stage)
        add_field(assembled, field)
        stages.append(report)
    field, residual, report = cell_stage(residual, prepared)
    add_field(assembled, field)
    stages.append(report)
    assert_field(assembled, prepared)
    reconstructed = divergence(assembled, prepared)
    if reconstructed != original:
        raise ArithmeticError("the assembled reference velocity does not reproduce the full pressure")
    physical_cells, physical_field, physical_pressure = physical_reconstruction(assembled, prepared)
    if physical_pressure != original:
        raise ArithmeticError("the physically transported velocity does not reproduce the full pressure")
    reference_bound = 4*sum(F(stage["reference_h1_squared_upper_bound"]) for stage in stages)
    reference_pressure_l2 = pressure_l2_squared(original, prepared)
    energy_info = {
        "pressure_l2_squared": str(size**3*reference_pressure_l2),
        "h1_seminorm_squared_upper_bound": str(size**3*reference_bound),
        "upper_bound_method": "four times the sum of the four component bounds; local patch overlap 64/448",
        "uniform_bound_reference": "GLOBAL_DIVERGENCE_BOUND.md",
        "exact_energy_computed": bool(integrate_energy)}
    if integrate_energy:
        exact = energy(assembled, prepared)
        if exact > reference_bound:
            raise ArithmeticError("integrated H1 energy exceeds the composed component bound")
        energy_info.update({
            "h1_seminorm_squared": str(size**3*exact),
            "observed_energy_to_pressure_l2_ratio": (
                str(exact/reference_pressure_l2) if reference_pressure_l2 else None)})
    nodes = sorted(physical_field)
    boundary_count = sum(any(value in (0, n*degree) for value in node)
                         for node in prepared["node_set"])
    return {
        "schema": SCHEMA, "status": "CONSTRUCTED", "n": n, "degree": degree,
        "pressure_degree": degree-1, "origin": [str(v) for v in origin],
        "cell_size": str(size), "box_side_length": str(n*size),
        "cell_order": "cube x, then y, then z; then six positive kuhn_tets entries",
        "cells": [[[str(v) for v in p] for p in cell] for cell in physical_cells],
        "pressure_indices": [list(beta) for beta in prepared["betas"]],
        "pressure_coefficients": [[str(v) for v in row] for row in original],
        "cell_divergence_coefficients": [[str(v) for v in row] for row in physical_pressure],
        "cell_means": [str(v) for v in cell_means],
        "nodes_times_degree": [[str(v) for v in node] for node in nodes],
        "velocity_coefficients": [[str(v) for v in physical_field[node]] for node in nodes],
        "coefficient_convention": "normalized Bernstein coefficients, not point values",
        "omitted_velocity_coefficients": "zero",
        "continuity": "one shared vector coefficient per global Bernstein node",
        "boundary_velocity": "zero on every exterior face",
        "stages": stages, "energy": energy_info,
        "operator_asset": prepared["operators_provenance"],
        "mesh_census": prepared["plan"]["census"],
        "exact_identities": {
            "arithmetic": "exact rational",
            "full_physical_pressure_rows": len(original)*len(prepared["betas"]),
            "full_physical_pressure_residual_max": "0",
            "full_reference_pressure_residual_max": "0",
            "zero_boundary_coefficient_nodes": boundary_count,
            "mean_compatibility_residual": "0",
            "vertex_source_compatibility": "all complete source tuples accepted",
            "edge_source_compatibility": "all complete source tuples accepted",
            "cell_bubble_residual_max": "0"},
        "scope": "global divergence right inverse for degrees four/five and n at least two; theorem derivation is separate from finite execution",
    }


def field_from_velocity(value, prepared):
    """Read shared physical coefficients and return the corresponding unit-lattice field."""
    if not isinstance(value, dict):
        raise ValueError("velocity input must be a JSON object")
    nodes, coefficients = value.get("nodes_times_degree"), value.get("velocity_coefficients")
    if (not isinstance(nodes, list) or not isinstance(coefficients, list)
            or len(nodes) != len(coefficients)):
        raise ValueError("velocity input needs equally sized nodes_times_degree and velocity_coefficients arrays")
    origin, size, degree = prepared["origin"], prepared["size"], prepared["degree"]
    field, seen = {}, set()
    for node, vector in zip(nodes, coefficients):
        physical = triple(node, "velocity coefficient node")
        reference = tuple(integer((physical[j]-degree*origin[j])/size,
                                  "unit-lattice velocity node") for j in range(3))
        if reference in seen:
            raise ValueError("velocity input contains a repeated global coefficient node")
        seen.add(reference)
        if reference not in prepared["node_set"]:
            raise ValueError("velocity input coefficient node is outside the specified Kuhn mesh")
        vector = tuple(v/size for v in triple(vector, "velocity coefficient"))
        if any(vector):
            field[reference] = vector
    assert_field(field, prepared)
    return field


def pressure_from_velocity(value, prepared):
    """Compute a valid pressure input from an existing shared Dirichlet velocity."""
    field = field_from_velocity(value, prepared)
    values = divergence(field, prepared)
    return {
        "schema": "freudenthal-global-pressure/v1",
        "n": prepared["n"], "degree": prepared["degree"],
        "origin": [str(v) for v in prepared["origin"]],
        "cell_size": str(prepared["size"]),
        "pressure_coefficients": [[str(v) for v in row] for row in values],
        "derivation": "complete divergence of the supplied shared zero-boundary velocity",
        "velocity_input_nonzero_nodes": len(field),
    }


def write_exclusive(path, value):
    """Remove only this call's own partial file if output writing fails."""
    identity = None
    try:
        with path.open("x", encoding="utf-8") as stream:
            stat = os.fstat(stream.fileno())
            identity = (stat.st_dev, stat.st_ino)
            json.dump(value, stream, separators=(",", ":"))
            stream.write("\n")
    except BaseException:
        if identity is not None:
            try:
                stat = path.lstat()
                if (stat.st_dev, stat.st_ino) == identity:
                    path.unlink()
            except OSError:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Complete pressure JSON or, with --from-velocity, shared velocity JSON")
    parser.add_argument("--from-velocity", action="store_true",
                        help="first compute pressure from the supplied continuous Dirichlet coefficients")
    parser.add_argument("--energy", action="store_true",
                        help="also integrate the assembled field's exact H1 energy")
    parser.add_argument("--output", type=Path, help="create a new complete JSON output; default stdout")
    args = parser.parse_args()
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        n = value.get("n", value.get("subdivisions"))
        degree = value.get("degree")
        origin = value.get("origin", (0, 0, 0))
        size = value.get("cell_size")
        n, degree, origin, size = parameters(n, degree, origin, size)
        prepared = prepare(n, degree, origin, size)
        if args.from_velocity:
            derived = pressure_from_velocity(value, prepared)
            pressure = derived["pressure_coefficients"]
        else:
            pressure = value.get("pressure_coefficients", value.get("cell_divergence_coefficients"))
        result = construct(pressure, n, degree, origin, size, prepared, args.energy)
        if args.from_velocity:
            result["input_derivation"] = {
                "mode": "divergence of supplied shared Dirichlet velocity",
                "velocity_input_nonzero_nodes": derived["velocity_input_nonzero_nodes"]}
        if args.output is None:
            json.dump(result, sys.stdout, separators=(",", ":"))
            sys.stdout.write("\n")
        else:
            write_exclusive(args.output, result)
            print(json.dumps({
                "schema": SCHEMA, "status": result["status"], "n": n, "degree": degree,
                "output": str(args.output),
                "nonzero_velocity_nodes": len(result["nodes_times_degree"]),
                "full_physical_pressure_rows": result["exact_identities"]["full_physical_pressure_rows"],
                "full_physical_pressure_residual_max": "0",
                "nonzero_vertex_patches": result["stages"][1]["nonzero_patches"],
                "nonzero_edge_patches": result["stages"][2]["nonzero_patches"],
                "nonzero_cell_bubbles": result["stages"][3]["nonzero_cells"],
                "exact_energy_computed": result["energy"]["exact_energy_computed"],
                "operator_asset": result["operator_asset"],
            }, sort_keys=True))
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError, TypeError) as exc:
        print(f"global divergence lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
