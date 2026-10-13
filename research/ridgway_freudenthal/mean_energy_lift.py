"""Exact minimum-H1-energy cell-mean lift on a uniform Kuhn cube grid.

Continuous P1 vectors plus normal cubic face bubbles supply the velocity.
A dual-tree parameterization removes mean constraints; all remaining variables
are minimized by exact LDL^T. The returned P4/P5 Bernstein field matches means,
not the entire supplied piecewise-constant pressure pointwise.
"""
from __future__ import annotations

import argparse
from collections import deque
from fractions import Fraction as F
import json
from math import factorial, gcd, prod
from pathlib import Path
import sys

try:
    from .kuhn import kuhn_tets
    from .p4_mean_repair import cross, gradients, indices
    from .cell_bubble_lift import rational, physical_gradients, bernstein_gram_entry
except ImportError:
    from kuhn import kuhn_tets
    from p4_mean_repair import cross, gradients, indices
    from cell_bubble_lift import rational, physical_gradients, bernstein_gram_entry

VOLUME = F(1, 6)
SCHEMA = "freudenthal-minimum-energy-mean-lift/v1"


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def point(cell, alpha):
    return tuple(sum(alpha[i]*cell[i][j] for i in range(4)) for j in range(3))


def grid(subdivisions):
    if type(subdivisions) is not int or subdivisions < 1:
        raise ValueError("subdivisions must be a positive integer")
    n = subdivisions
    return [tuple(tuple(p[j]+shift[j] for j in range(3)) for p in cell)
            for shift in ((x, y, z) for x in range(n) for y in range(n) for z in range(n))
            for cell in kuhn_tets()]


def primitive_normal(face):
    u = tuple(face[1][j]-face[0][j] for j in range(3))
    v = tuple(face[2][j]-face[0][j] for j in range(3))
    normal = cross(u, v)
    divisor = gcd(gcd(abs(normal[0]), abs(normal[1])), abs(normal[2]))
    if not divisor:
        raise ArithmeticError("degenerate mesh face")
    normal = tuple(value//divisor for value in normal)
    if next(value for value in normal if value) < 0:
        normal = tuple(-value for value in normal)
    return normal


def add_symmetric(matrix, row, column, value):
    if not value:
        return
    matrix[row][column] = matrix[row].get(column, F(0))+value
    if row != column:
        matrix[column][row] = matrix[column].get(row, F(0))+value


def sparse_action(matrix, vector):
    return [sum(value*vector[column] for column, value in row.items()) for row in matrix]


def ldlt(matrix):
    """Exact positive-definite factorization, without square roots or pivot guesses."""
    size = len(matrix)
    lower = [[F(int(i == j)) for j in range(size)] for i in range(size)]
    diagonal = []
    for i in range(size):
        value = matrix[i][i]-sum(lower[i][k]**2*diagonal[k] for k in range(i))
        if value <= 0:
            raise ArithmeticError(f"reduced energy is not positive definite at column {i}")
        diagonal.append(value)
        for j in range(i+1, size):
            lower[j][i] = (matrix[j][i]-sum(
                lower[j][k]*lower[i][k]*diagonal[k] for k in range(i)))/value
    return lower, diagonal


def solve_ldlt(factor, rhs):
    lower, diagonal = factor
    size = len(diagonal)
    intermediate = []
    for i in range(size):
        intermediate.append(rhs[i]-sum(lower[i][j]*intermediate[j] for j in range(i)))
    answer = [value/divisor for value, divisor in zip(intermediate, diagonal)]
    for i in reversed(range(size)):
        answer[i] -= sum(lower[j][i]*answer[j] for j in range(i+1, size))
    return answer


def tree_flux(assembly, residual):
    if sum(residual):
        raise ArithmeticError("dual-tree residual must have zero total integral")
    subtotal = [F(value) for value in residual]
    flux = [F(0)]*len(assembly["faces"])
    for cell in reversed(assembly["tree_order"][1:]):
        parent, face_id = assembly["parent"][cell]
        sign = assembly["faces"][face_id]["sign_by_cell"][cell]
        flux[face_id] = sign*subtotal[cell]
        subtotal[parent] += subtotal[cell]
    if subtotal[0]:
        raise ArithmeticError("dual-tree root retained a nonzero residual")
    return flux


def assemble(subdivisions=2):
    """Build/factor once on [0,n]^3; reuse this object for further mean vectors."""
    cells = grid(subdivisions)
    n = subdivisions
    cell_gradients = [gradients(cell) for cell in cells]
    interior_vertices = sorted({p for cell in cells for p in cell
                                if all(0 < value < n for value in p)})
    vertex_ids = {p: i for i, p in enumerate(interior_vertices)}
    face_owners = {}
    for cell_id, cell in enumerate(cells):
        for opposite in range(4):
            face = tuple(sorted(p for i, p in enumerate(cell) if i != opposite))
            face_owners.setdefault(face, []).append((cell_id, opposite))
    if any(len(owners) not in (1, 2) for owners in face_owners.values()):
        raise ArithmeticError("mesh face has invalid incidence")
    face_keys = sorted(face for face, owners in face_owners.items() if len(owners) == 2)
    node_dofs = 3*len(interior_vertices)
    faces = []
    cell_faces = [[None]*4 for _ in cells]
    adjacency = [[] for _ in cells]
    for face_id, key in enumerate(face_keys):
        owners = face_owners[key]
        normal = primitive_normal(key)
        gammas, signs = [], {}
        for cell_id, opposite in owners:
            value = dot(normal, cell_gradients[cell_id][opposite])
            if not value:
                raise ArithmeticError("chosen face normal is tangential")
            gammas.append(VOLUME*abs(value)/20)
            signs[cell_id] = -1 if value > 0 else 1
            cell_faces[cell_id][opposite] = face_id
        if gammas[0] != gammas[1] or sum(signs.values()):
            raise ArithmeticError("normalized shared-face flux does not agree")
        faces.append({"vertices": key, "normal": normal, "gamma": gammas[0],
                      "owners": owners, "sign_by_cell": signs,
                      "dof": node_dofs+face_id})
        left, right = owners[0][0], owners[1][0]
        adjacency[left].append((right, face_id))
        adjacency[right].append((left, face_id))
    unknowns = node_dofs+len(faces)
    stiffness = [{} for _ in range(unknowns)]
    constraints = [{} for _ in cells]
    for cell_id, cell in enumerate(cells):
        grad = cell_gradients[cell_id]
        local_nodes = [(i, vertex_ids[p]) for i, p in enumerate(cell) if p in vertex_ids]
        local_faces = [(opposite, face_id) for opposite, face_id
                       in enumerate(cell_faces[cell_id]) if face_id is not None]
        for local, vertex_id in local_nodes:
            for component in range(3):
                value = VOLUME*grad[local][component]
                if value:
                    constraints[cell_id][3*vertex_id+component] = value
        for opposite, face_id in local_faces:
            face = faces[face_id]
            constraints[cell_id][face["dof"]] = F(face["sign_by_cell"][cell_id])
        for index, (local, vertex_id) in enumerate(local_nodes):
            for other, other_vertex in local_nodes[index:]:
                value = VOLUME*dot(grad[local], grad[other])
                for component in range(3):
                    add_symmetric(stiffness, 3*vertex_id+component,
                                  3*other_vertex+component, value)
            for opposite, face_id in local_faces:
                face = faces[face_id]
                factor = -VOLUME*dot(grad[local], grad[opposite])/(20*face["gamma"])
                for component in range(3):
                    add_symmetric(stiffness, 3*vertex_id+component,
                                  face["dof"], factor*face["normal"][component])
        for index, (opposite, face_id) in enumerate(local_faces):
            face = faces[face_id]
            for other_opposite, other_face_id in local_faces[index:]:
                other_face = faces[other_face_id]
                integral = F(0)
                for i in range(4):
                    if i == opposite:
                        continue
                    beta = tuple(1-int(r == opposite)-int(r == i) for r in range(4))
                    for j in range(4):
                        if j == other_opposite:
                            continue
                        other_beta = tuple(1-int(r == other_opposite)-int(r == j)
                                           for r in range(4))
                        moment = F(prod(factorial(a+b) for a, b in zip(beta, other_beta)), 5040)
                        integral += dot(grad[i], grad[j])*moment
                value = (dot(face["normal"], other_face["normal"])*integral
                         /(face["gamma"]*other_face["gamma"]))
                add_symmetric(stiffness, face["dof"], other_face["dof"], value)
    totals = [F(0)]*unknowns
    for row in constraints:
        for column, value in row.items():
            totals[column] += value
    if any(totals):
        raise ArithmeticError("a boundary-zero basis field has nonzero total divergence")
    parent = [None]*len(cells)
    parent[0] = (-1, -1)
    order = [0]
    queue = deque([0])
    while queue:
        cell = queue.popleft()
        for neighbor, face_id in sorted(adjacency[cell], key=lambda item: (item[1], item[0])):
            if parent[neighbor] is None:
                parent[neighbor] = (cell, face_id)
                order.append(neighbor)
                queue.append(neighbor)
    if len(order) != len(cells):
        raise ArithmeticError("tetrahedron dual graph is disconnected")
    tree_faces = {face_id for _, face_id in parent[1:]}
    chords = [face_id for face_id in range(len(faces)) if face_id not in tree_faces]
    free_dofs = list(range(node_dofs))+[node_dofs+face_id for face_id in chords]
    dimension = len(free_dofs)
    expected_dimension = 9*n**3-15*n**2+9*n-2
    if (len(cells) != 6*n**3 or len(faces) != 12*n**3-6*n**2
            or node_dofs != 3*(n-1)**3 or dimension != expected_dimension):
        raise ArithmeticError("uniform-grid dimension formulas do not match incidence")
    assembly = {"subdivisions": n, "cells": cells, "cell_gradients": cell_gradients,
                "interior_vertices": interior_vertices, "vertex_ids": vertex_ids,
                "faces": faces, "cell_faces": cell_faces, "node_dofs": node_dofs,
                "unknowns": unknowns, "stiffness": stiffness, "constraints": constraints,
                "parent": parent, "tree_order": order, "tree_faces": tree_faces,
                "chords": chords, "free_dofs": free_dofs, "reduced_dimension": dimension}
    kernel_columns = []
    for dof in free_dofs:
        residual = [-row.get(dof, F(0)) for row in constraints]
        flux = tree_flux(assembly, residual)
        column = [F(0)]*unknowns
        column[dof] = F(1)
        for face_id in tree_faces:
            column[node_dofs+face_id] = flux[face_id]
        if any(sparse_action(constraints, column)):
            raise ArithmeticError("dual-tree parameterization has a nonzero constraint residual")
        kernel_columns.append(column)
    kernel = [list(row) for row in zip(*kernel_columns)]
    stiffness_kernel = [[sum(value*kernel[j][column] for j, value in row.items())
                         for column in range(dimension)] for row in stiffness]
    reduced = [[F(0)]*dimension for _ in range(dimension)]
    for i in range(dimension):
        for j in range(i, dimension):
            value = sum(kernel[row][i]*stiffness_kernel[row][j] for row in range(unknowns))
            reduced[i][j] = reduced[j][i] = value
    assembly["kernel"] = kernel
    assembly["factor"] = ldlt(reduced)
    assembly["stiffness_nonzeros"] = sum(sum(bool(value) for value in row.values())
                                         for row in stiffness)
    assembly["reduced_nonzeros"] = sum(bool(value) for row in reduced for value in row)
    return assembly


def validate_means(subdivisions, means):
    if type(subdivisions) is not int or subdivisions < 1:
        raise ValueError("subdivisions must be a positive integer")
    count = 6*subdivisions**3
    if not isinstance(means, (list, tuple)) or len(means) != count:
        raise ValueError(f"cell_means must contain exactly {count} coefficients")
    values = [rational(value, "cell mean") for value in means]
    total = sum(values)
    if total:
        raise ValueError(f"cell means must have zero sum on this equal-volume grid; residual {total}")
    return values


def minimize(assembly, cell_means):
    means = validate_means(assembly["subdivisions"], cell_means)
    integrals = [VOLUME*value for value in means]
    flux = tree_flux(assembly, integrals)
    particular = [F(0)]*assembly["node_dofs"]+flux
    if sparse_action(assembly["constraints"], particular) != integrals:
        raise ArithmeticError("particular mean lift does not match every cell integral")
    action = sparse_action(assembly["stiffness"], particular)
    kernel = assembly["kernel"]
    dimension = assembly["reduced_dimension"]
    rhs = [-sum(kernel[row][column]*action[row] for row in range(assembly["unknowns"]))
           for column in range(dimension)]
    free = solve_ldlt(assembly["factor"], rhs)
    velocity = [value+dot(row, free) for value, row in zip(particular, kernel)]
    if sparse_action(assembly["constraints"], velocity) != integrals:
        raise ArithmeticError("minimum-energy field does not match every cell integral")
    final_action = sparse_action(assembly["stiffness"], velocity)
    if any(sum(kernel[row][column]*final_action[row] for row in range(assembly["unknowns"]))
           for column in range(dimension)):
        raise ArithmeticError("minimum-energy stationarity is not exact")
    energy = dot(velocity, final_action)
    particular_energy = dot(particular, action)
    if energy < 0 or energy > particular_energy:
        raise ArithmeticError("energy minimization increased the feasible tree field's energy")
    return {"cell_means": means, "velocity": velocity, "free": free,
            "reference_energy": energy, "reference_tree_energy": particular_energy}


def local_coefficient(assembly, solved, degree, cell_id, alpha):
    cell = assembly["cells"][cell_id]
    result = [F(0)]*3
    values = solved["velocity"]
    for local, vertex in enumerate(cell):
        vertex_id = assembly["vertex_ids"].get(vertex)
        if vertex_id is not None:
            for component in range(3):
                result[component] += F(alpha[local], degree)*values[3*vertex_id+component]
    divisor = degree*(degree-1)*(degree-2)
    for opposite, face_id in enumerate(assembly["cell_faces"][cell_id]):
        if face_id is None:
            continue
        product = prod(alpha[i] for i in range(4) if i != opposite)
        if not product:
            continue
        face = assembly["faces"][face_id]
        multiplier = values[face["dof"]]*F(product, divisor)/face["gamma"]
        for component in range(3):
            result[component] += multiplier*face["normal"][component]
    return tuple(result)


def cubic_energy(assembly, solved):
    """Integrate the actual cubic field's nine gradient components exactly."""
    betas = indices(2)
    beta_ids = {beta: i for i, beta in enumerate(betas)}
    gram = [[bernstein_gram_entry(a, b) for b in betas] for a in betas]
    total = F(0)
    for cell_id, cell in enumerate(assembly["cells"]):
        grad = assembly["cell_gradients"][cell_id]
        constant = [F(0)]*9
        for local, vertex in enumerate(cell):
            vertex_id = assembly["vertex_ids"].get(vertex)
            if vertex_id is None:
                continue
            for component in range(3):
                value = solved["velocity"][3*vertex_id+component]
                for axis in range(3):
                    constant[3*component+axis] += value*grad[local][axis]
        derivatives = [constant[:] for _ in betas]
        for opposite, face_id in enumerate(assembly["cell_faces"][cell_id]):
            if face_id is None:
                continue
            face = assembly["faces"][face_id]
            factor = solved["velocity"][face["dof"]]/(2*face["gamma"])
            for i in range(4):
                if i == opposite:
                    continue
                beta = tuple(1-int(r == opposite)-int(r == i) for r in range(4))
                row = derivatives[beta_ids[beta]]
                for component in range(3):
                    for axis in range(3):
                        row[3*component+axis] += factor*face["normal"][component]*grad[i][axis]
        for i, row in enumerate(derivatives):
            for j in range(i, len(derivatives)):
                total += (1 if i == j else 2)*gram[i][j]*dot(row, derivatives[j])
    if total != solved["reference_energy"]:
        raise ArithmeticError("integrated cubic-field energy differs from assembled stiffness energy")
    return total


def placement(subdivisions, origin, cell_size):
    if not isinstance(origin, (tuple, list)) or len(origin) != 3:
        raise ValueError("origin must contain three exact coordinates")
    origin = tuple(rational(value, "origin coordinate") for value in origin)
    h = F(1, subdivisions) if cell_size is None else rational(cell_size, "cell_size")
    if h <= 0:
        raise ValueError("cell_size must be positive")
    return origin, h


def reconstruct_physical_means(degree, cells, nodes, coefficients, expected_means):
    lookup = {tuple(point): tuple(vector) for point, vector in zip(nodes, coefficients)}
    betas = indices(degree-1)
    divergence_coefficients = []
    for cell_id, cell in enumerate(cells):
        gradients_here = physical_gradients(cell)
        values = []
        for beta in betas:
            value = F(0)
            for i in range(4):
                alpha = list(beta)
                alpha[i] += 1
                vector = lookup.get(point(cell, alpha))
                if vector is not None:
                    value += degree*dot(gradients_here[i], vector)
            values.append(value)
        mean = sum(values)/len(betas)
        if mean != expected_means[cell_id]:
            raise ArithmeticError(f"physical cell mean differs in cell {cell_id}")
        divergence_coefficients.append(values)
    return divergence_coefficients


def embed(assembly, solved, degree=4, origin=(0, 0, 0), cell_size=None):
    if type(degree) is not int or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    n = assembly["subdivisions"]
    origin, h = placement(n, origin, cell_size)
    values_by_node = {}
    boundary_nodes = set()
    shared_incidences = 0
    for cell_id, cell in enumerate(assembly["cells"]):
        for alpha in indices(degree):
            node = point(cell, alpha)
            vector = local_coefficient(assembly, solved, degree, cell_id, alpha)
            if node in values_by_node:
                if values_by_node[node] != vector:
                    raise ArithmeticError("adjacent cells disagree on a shared Bernstein coefficient")
                shared_incidences += 1
            else:
                values_by_node[node] = vector
            if any(value in (0, n*degree) for value in node):
                boundary_nodes.add(node)
                if any(vector):
                    raise ArithmeticError("a physical Dirichlet boundary coefficient is nonzero")
    reference_nodes = sorted(node for node, vector in values_by_node.items() if any(vector))
    if any(node in boundary_nodes for node in reference_nodes):
        raise ArithmeticError("nonzero velocity node appears on the boundary")
    cells = [[tuple(origin[j]+h*F(p[j]) for j in range(3)) for p in cell]
             for cell in assembly["cells"]]
    nodes = [tuple(degree*origin[j]+h*F(node[j]) for j in range(3))
             for node in reference_nodes]
    coefficients = [tuple(h*value for value in values_by_node[node]) for node in reference_nodes]
    divergence = reconstruct_physical_means(degree, cells, nodes, coefficients, solved["cell_means"])
    reference_energy = cubic_energy(assembly, solved)
    energy = h**3*reference_energy
    data_l2_squared = h**3*VOLUME*sum(value**2 for value in solved["cell_means"])
    return {
        "schema": SCHEMA,
        "status": "CONSTRUCTED",
        "degree": degree,
        "polynomial_source_degree": 3,
        "subdivisions": n,
        "origin": [str(value) for value in origin],
        "cell_size": str(h),
        "box_side_length": str(n*h),
        "cell_order": "cube x, then y, then z; then the six positive kuhn_tets entries",
        "cells": [[[str(value) for value in p] for p in cell] for cell in cells],
        "cell_means": [str(value) for value in solved["cell_means"]],
        "cell_mean_integrals": [str(h**3*VOLUME*value) for value in solved["cell_means"]],
        "pressure_indices": [list(beta) for beta in indices(degree-1)],
        "cell_divergence_coefficients": [[str(value) for value in row] for row in divergence],
        "coefficient_convention": "normalized Bernstein coefficients, not point values",
        "nodes_times_degree": [[str(value) for value in node] for node in nodes],
        "velocity_coefficients": [[str(value) for value in vector] for vector in coefficients],
        "omitted_velocity_coefficients": "zero",
        "interior_nodal_values": [
            {"vertex": [str(origin[j]+h*F(vertex[j])) for j in range(3)],
             "velocity": [str(h*solved["velocity"][3*i+j]) for j in range(3)]}
            for i, vertex in enumerate(assembly["interior_vertices"])],
        "oriented_interior_face_fluxes": [
            {"vertices": [[str(origin[j]+h*F(p[j])) for j in range(3)] for p in face["vertices"]],
             "reference_normal": list(face["normal"]),
             "integral_flux": str(h**3*solved["velocity"][face["dof"]])}
            for face in assembly["faces"]],
        "energy": {
            "seminorm_squared": str(energy),
            "reference_seminorm_squared": str(reference_energy),
            "feasible_tree_seminorm_squared": str(h**3*solved["reference_tree_energy"]),
            "piecewise_constant_mean_data_l2_squared": str(data_l2_squared),
            "observed_energy_to_mean_data_l2_ratio": (
                str(energy/data_l2_squared) if data_l2_squared else None),
            "minimum_scope": "the full continuous P1 vector plus normal cubic face-bubble space",
            "uniform_bound": "proved in MEAN_ENERGY_LIFT.md via a bounded feasible field; no numeric sharp constant",
        },
        "solver": {
            "arithmetic": "exact rational",
            "method": "dual-tree constraint elimination and complete-kernel LDL^T energy minimization",
            "velocity_unknowns": assembly["unknowns"],
            "interior_nodal_unknowns": assembly["node_dofs"],
            "interior_face_unknowns": len(assembly["faces"]),
            "cell_mean_constraints": len(assembly["cells"]),
            "independent_mean_constraints": len(assembly["cells"])-1,
            "tree_faces": len(assembly["tree_faces"]),
            "chord_faces": len(assembly["chords"]),
            "reduced_dimension": assembly["reduced_dimension"],
            "full_saddle_dimension_avoided": assembly["unknowns"]+len(assembly["cells"])-1,
            "stiffness_nonzeros": assembly["stiffness_nonzeros"],
            "reduced_nonzeros": assembly["reduced_nonzeros"],
            "ldlt_pivots": [str(value) for value in assembly["factor"][1]],
            "free_coordinate_values": [str(value) for value in solved["free"]],
            "cost": "dense reduced O(d^3) rational field operations and O(d^2) storage, plus integer bit growth",
        },
        "exact_identities": {
            "cell_mean_rows": len(cells),
            "reconstructed_pressure_rows": len(cells)*len(indices(degree-1)),
            "cell_mean_residual_max": "0",
            "stationarity_residual_max": "0",
            "energy_integration_residual": "0",
            "shared_coefficient_incidences": shared_incidences,
            "zero_boundary_coefficient_nodes": len(boundary_nodes),
            "boundary_velocity": "zero on every domain boundary face",
        },
        "scope": "cell-mean matching; vertex and edge divergence are generally changed",
    }


def construct(cell_means, degree=4, subdivisions=2, origin=(0, 0, 0),
              cell_size=None, assembly=None):
    """Construct one mean lift; an assembly object reuses geometry and factorization."""
    means = validate_means(subdivisions, cell_means)
    if type(degree) is not int or degree not in (4, 5):
        raise ValueError("degree must be 4 or 5")
    placement(subdivisions, origin, cell_size)
    if assembly is None:
        assembly = assemble(subdivisions)
    elif not isinstance(assembly, dict) or assembly.get("subdivisions") != subdivisions:
        raise ValueError("assembly must match the requested subdivisions")
    return embed(assembly, minimize(assembly, means), degree, origin, cell_size)


def csv_values(text, name):
    parts = text.split(",")
    if not parts or any(not part.strip() for part in parts):
        raise ValueError(f"{name} must be comma-separated exact numbers")
    return [rational(part.strip(), name) for part in parts]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subdivisions", type=int, default=2)
    degrees = parser.add_mutually_exclusive_group()
    degrees.add_argument("--degree", type=int, choices=(4, 5), default=4)
    degrees.add_argument("--both-degrees", action="store_true",
                         help="solve once and embed the same field in P4 and P5")
    parser.add_argument("--means", help="all cell means in the documented order, comma-separated")
    parser.add_argument("--origin", default="0,0,0", help="three comma-separated exact coordinates")
    parser.add_argument("--cell-size", help="positive exact cube size; default 1/subdivisions")
    parser.add_argument("--output", type=Path, help="create a new JSON file")
    args = parser.parse_args()
    try:
        if args.subdivisions < 1:
            raise ValueError("subdivisions must be a positive integer")
        means = ([1]+[0]*(6*args.subdivisions**3-2)+[-1]
                 if args.means is None else csv_values(args.means, "cell mean"))
        means = validate_means(args.subdivisions, means)
        origin = csv_values(args.origin, "origin")
        placement(args.subdivisions, origin, args.cell_size)
        assembly = assemble(args.subdivisions)
        solved = minimize(assembly, means)
        if args.both_degrees:
            result = {
                "schema": "freudenthal-minimum-energy-mean-batch/v1",
                "status": "CONSTRUCTED",
                "shared_factorizations": 1,
                "shared_mean_solves": 1,
                "operators": [embed(assembly, solved, degree, origin, args.cell_size)
                              for degree in (4, 5)],
            }
        else:
            result = embed(assembly, solved, args.degree, origin, args.cell_size)
        output = json.dumps(result, indent=2, sort_keys=True)+"\n"
        if args.output is None:
            print(output, end="")
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(output)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError, TypeError) as exc:
        print(f"minimum-energy mean lift: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
