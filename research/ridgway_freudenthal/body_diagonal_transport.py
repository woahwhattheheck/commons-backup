"""Transport protected P4/P5 body-diagonal lifts to all six cube neighbors.

The origin is the central cube's lower corner for every neighbor choice.
Exact physical reconstruction checks every target/protected edge row and mean.
This is one local edge class, not the complete mesh-uniform theorem.
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
    from . import p4_body_diagonal_lift as p4
    from . import p5_body_diagonal_lift as p5
    from .face_diagonal_transport import PERMUTATIONS, parameters, rational, check_physical_operator
except ImportError:
    import p4_body_diagonal_lift as p4
    import p5_body_diagonal_lift as p5
    from face_diagonal_transport import PERMUTATIONS, parameters, rational, check_physical_operator

NEIGHBORS = ("+x", "-x", "+y", "-y", "+z", "-z")
SCHEMAS = {4: "freudenthal-p4-body-diagonal-lift/v1",
           5: "freudenthal-p5-body-diagonal-lift/v1"}
NODE_KEYS = {4: "nodes_times_four", 5: "nodes_times_five"}


def transform_parameters(neighbor, origin, scale):
    if not isinstance(neighbor, str) or neighbor not in NEIGHBORS:
        raise ValueError("neighbor must be +x, -x, +y, -y, +z or -z")
    permutation, origin, scale = parameters(neighbor[1], origin, scale)
    sign = 1 if neighbor[0] == "+" else -1
    return permutation, sign, origin, scale


def reference_operator(degree=4):
    """Compose with the retained eleven-column mean basis, without its old solve."""
    if degree not in SCHEMAS:
        raise ValueError("degree must be 4 or 5")
    path = Path(__file__).with_name("p4_mean_repair_basis.json")
    data = path.read_bytes()
    mean_repair = json.loads(data)
    if (mean_repair.get("schema") != "freudenthal-p4-mean-repair/v1"
            or mean_repair.get("status") != "CONSTRUCTED"
            or mean_repair.get("basis_shape") != [189, 11]):
        raise ValueError("retained mean repair must be the constructed two-cube 189-by-11 operator")
    result = (p4 if degree == 4 else p5).construct(mean_repair=mean_repair)
    result["retained_mean_repair"] = {
        "file": path.name, "sha256": sha256(data).hexdigest(), "basis_shape": [189, 11],
        "construction": "reused retained coefficients; mean solver was not called"}
    return result


def transport(operator, neighbor="+x", origin=(0, 0, 0), scale=1):
    """Transport an accepted body-diagonal reference, preserving its column order."""
    permutation, sign, origin, scale = transform_parameters(neighbor, origin, scale)
    if not isinstance(operator, dict):
        raise ValueError("operator must be a constructed P4 or P5 body-diagonal reference")
    degree = next((k for k, schema in SCHEMAS.items() if operator.get("schema") == schema), None)
    if degree is None or operator.get("status") != "CONSTRUCTED":
        raise ValueError("operator must be a constructed P4 or P5 body-diagonal reference")
    width = 6*(degree-2)
    if operator.get("target_dimension") != width:
        raise ValueError("reference target dimension does not match its degree")
    # F(xi) = a + h*b + h*s*P*xi, b=0 for positive and (1,1,1) for negative.
    # Both signs map the reference first cube to the same central physical cube.
    zero_image = tuple(value + (scale if sign < 0 else 0) for value in origin)
    vertex_order = (0, 1, 2, 3) if sign > 0 else (0, 2, 1, 3)

    def mapped(point, multiplier=1):
        result = [multiplier*value for value in zero_image]
        for old, new in enumerate(permutation):
            result[new] += scale*sign*F(point[old])
        return [str(value) for value in result]

    result = deepcopy(operator)
    reference_nodes = result.pop(NODE_KEYS[degree])
    result.pop("requested_trace", None)
    result.pop("velocity_coefficients", None)
    labels = [{**label, "beta": [label["beta"][old] for old in vertex_order]}
              for label in operator["target_coordinates"]]
    result.update({
        "schema": "freudenthal-body-diagonal-transport/v1",
        "status": "TRANSPORTED_AND_CHECKED",
        "reference_schema": operator["schema"],
        "degree": degree, "source_dimension": width,
        "source_basis": [[int(i == j) for j in range(width)] for i in range(width)],
        "neighbor": neighbor,
        "origin": [str(value) for value in origin],
        "scale": str(scale),
        "reference_zero_image": [str(value) for value in zero_image],
        "reference_to_physical_component": list(permutation),
        "component_sign": sign,
        "physical_vertex_to_reference_vertex": list(vertex_order),
        "cells": [[mapped(cell[old]) for old in vertex_order] for cell in operator["cells"]],
        "nodes_times_degree": [mapped(point, degree) for point in reference_nodes],
        "target_coordinates": labels,
        "target_edge": [mapped(point) for point in operator["target_edge"]],
        "basis": sorted([[3*(row//3)+permutation[row%3], column, str(scale*sign*F(value))]
                         for row, column, value in operator["basis"]]),
        "reference_h1_squared_bound_from_target_l2": operator["h1_squared_bound_from_target_l2"],
        "h1_squared_bound_from_target_l2": str(scale**3*F(operator["h1_squared_bound_from_target_l2"])),
        "coordinate_semantics":
            "origin is the central cube's lower corner; divide nodes_times_degree by degree",
        "coefficient_semantics":
            "continuous vector Bernstein coefficients; omitted boundary coefficients are zero",
        "ordering_semantics":
            "reference cell, node, target and endpoint order is inherited; negative directions "
            "swap local vertices 1/2 and their beta entries; high_endpoint_power refers to "
            "the second inherited target endpoint, including when it is physically lower"
    })
    result["physical_identity_check"] = check_physical_operator(result)
    return result


def apply(operator, trace):
    """Apply in the inherited cell-major, reference-endpoint trace ordering."""
    degree = operator.get("degree")
    if (operator.get("schema") != "freudenthal-body-diagonal-transport/v1"
            or operator.get("status") != "TRANSPORTED_AND_CHECKED" or degree not in SCHEMAS):
        raise ValueError("operator must be a checked P4 or P5 body-diagonal transport")
    return (p4 if degree == 4 else p5).apply(operator, trace)


def construct(degree=4, neighbor="+x", origin=(0, 0, 0), scale=1):
    """Compose one reference with the retained mean basis, then transport it."""
    transform_parameters(neighbor, origin, scale)
    return transport(reference_operator(degree), neighbor, origin, scale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, choices=(4, 5), default=4)
    orientation = parser.add_mutually_exclusive_group()
    orientation.add_argument("--neighbor", choices=NEIGHBORS, default="+x")
    orientation.add_argument("--all-neighbors", action="store_true",
                             help="Compose one reference and reuse it for all six neighbors")
    parser.add_argument("--origin", default="0,0,0",
                        help="Central cube lower corner; three comma-separated exact coordinates")
    parser.add_argument("--scale", default="1", help="Positive exact rational isotropic scale")
    parser.add_argument("--reference", type=Path,
                        help="Reuse a saved constructed reference JSON instead of composing one")
    parser.add_argument("--trace", help="Comma-separated exact coefficients: 12 for P4, 18 for P5")
    parser.add_argument("--output", type=Path, help="Create a new JSON file; default stdout")
    args = parser.parse_args()
    try:
        _, _, origin, scale = transform_parameters(args.neighbor, args.origin.split(","), args.scale)
        if args.reference:
            reference = json.loads(args.reference.read_bytes())
            if not isinstance(reference, dict) or reference.get("schema") != SCHEMAS[args.degree]:
                raise ValueError("saved reference schema does not match --degree")
        else:
            reference = reference_operator(args.degree)
        trace = None if args.trace is None else args.trace.split(",")
        if trace is not None:
            (p4 if args.degree == 4 else p5).apply(reference, trace)
        neighbors = NEIGHBORS if args.all_neighbors else (args.neighbor,)
        operators = {}
        for neighbor in neighbors:
            operator = transport(reference, neighbor, origin, scale)
            if trace is not None:
                operator["requested_trace"] = [str(rational(value, "trace coefficient")) for value in trace]
                operator["velocity_coefficients"] = apply(operator, trace)
            operators[neighbor] = operator
        result = ({"schema": "freudenthal-body-diagonal-transport-batch/v1",
                   "status": "TRANSPORTED_AND_CHECKED", "degree": args.degree,
                   "operators": operators} if args.all_neighbors else operators[args.neighbor])
        data = json.dumps(result, indent=2)+"\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(data)
        else:
            print(data, end="")
        print(f"TRANSPORTED_AND_CHECKED: degree {args.degree}, neighbors {','.join(neighbors)}, "
              f"target dimension {6*(args.degree-2)}; exact physical residuals 0", file=sys.stderr)
        return 0
    except (ValueError, ArithmeticError, OSError, KeyError, TypeError) as exc:
        print(f"body_diagonal_transport: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
