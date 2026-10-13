#!/usr/bin/env python3
"""Exact pressure-trace consistency counterexamples for Commons #14998.

This module is deliberately dependency-free. It does not solve the prize theorem.
It certifies three narrow algebraic facts:

1. On a fully weak boundary, u=0, p=x, f=(1,0) and the constant
   divergence-free test v=(1,0) expose missing pressure-normal work.
2. On one boundary triangle with two zero-extension edges and one weak edge,
   a compactly supported P3 divergence-free velocity (hence admissible in a
   full P4 velocity space) exposes the same defect exactly.
3. On a square annulus the phenomenon survives strong-outer/weak-inner
   topology with an exact polynomial stream-function witness.

The local P3 witness is the degree-relevant result. The annulus witness remains
useful as an independent mixed-boundary topology sanity check, but its velocity
has degree 8 and is not itself a P4 membership claim.
"""
from __future__ import annotations

from fractions import Fraction
from math import comb, factorial
import json
from typing import Dict, Tuple

Q = Fraction
Monomial = Tuple[int, int]
Poly = Dict[Monomial, Q]
Poly1 = Dict[int, Q]


class CertificateError(RuntimeError):
    """A claimed exact witness failed a theorem-critical runtime check."""


def require_certificate(condition: bool, message: str) -> None:
    if not condition:
        raise CertificateError(message)


def clean(p: Poly) -> Poly:
    return {m: Q(c) for m, c in p.items() if c}


def add(*polys: Poly) -> Poly:
    out: Poly = {}
    for p in polys:
        for m, c in p.items():
            out[m] = out.get(m, Q(0)) + c
    return clean(out)


def scale(p: Poly, a: Q | int) -> Poly:
    a = Q(a)
    return clean({m: a * c for m, c in p.items()})


def mul(*polys: Poly) -> Poly:
    out: Poly = {(0, 0): Q(1)}
    for b in polys:
        nxt: Poly = {}
        for (i, j), ca in out.items():
            for (k, ell), cb in b.items():
                m = (i + k, j + ell)
                nxt[m] = nxt.get(m, Q(0)) + ca * cb
        out = clean(nxt)
    return out


def derivative(p: Poly, axis: str) -> Poly:
    out: Poly = {}
    for (i, j), c in p.items():
        if axis == "x" and i:
            out[(i - 1, j)] = out.get((i - 1, j), Q(0)) + c * i
        elif axis == "y" and j:
            out[(i, j - 1)] = out.get((i, j - 1), Q(0)) + c * j
        elif axis not in {"x", "y"}:
            raise ValueError("axis must be x or y")
    return clean(out)


def integrate_rect(p: Poly, xa: int, xb: int, ya: int, yb: int) -> Q:
    total = Q(0)
    for (i, j), c in p.items():
        ix = Q(xb ** (i + 1) - xa ** (i + 1), i + 1)
        iy = Q(yb ** (j + 1) - ya ** (j + 1), j + 1)
        total += c * ix * iy
    return total


def integrate_reference_triangle(p: Poly) -> Q:
    """Integrate exactly over x>=0, y>=0, x+y<=1."""
    return sum(
        (
            c * Q(factorial(i) * factorial(j), factorial(i + j + 2))
            for (i, j), c in p.items()
        ),
        Q(0),
    )


def restrict_x(p: Poly, x0: int) -> Poly1:
    out: Poly1 = {}
    for (i, j), c in p.items():
        out[j] = out.get(j, Q(0)) + c * (Q(x0) ** i)
    return {j: c for j, c in out.items() if c}


def restrict_y(p: Poly, y0: int) -> Poly1:
    out: Poly1 = {}
    for (i, j), c in p.items():
        out[i] = out.get(i, Q(0)) + c * (Q(y0) ** j)
    return {i: c for i, c in out.items() if c}


def restrict_y_one_minus_x(p: Poly) -> Poly1:
    """Restrict a 2D polynomial to the reference hypotenuse y=1-x."""
    out: Poly1 = {}
    for (i, j), c in p.items():
        for r in range(j + 1):
            degree = i + r
            out[degree] = out.get(degree, Q(0)) + c * comb(j, r) * ((-1) ** r)
    return {degree: c for degree, c in out.items() if c}


def integrate_1d(p: Poly1, a: int, b: int) -> Q:
    return sum(
        (
            c * Q(b ** (degree + 1) - a ** (degree + 1), degree + 1)
            for degree, c in p.items()
        ),
        Q(0),
    )


def degree(p: Poly) -> int:
    return max((i + j for (i, j) in p), default=-1)


ONE: Poly = {(0, 0): Q(1)}
X: Poly = {(1, 0): Q(1)}
Y: Poly = {(0, 1): Q(1)}


def _certify_local_p4_velocity(vx: Poly, vy: Poly) -> dict:
    """Derive and enforce all machine-readable claims for the local witness."""
    div_v = add(derivative(vx, "x"), derivative(vy, "y"))
    x_trace_zero = (
        not restrict_x(vx, 0)
        and not restrict_x(vy, 0)
    )
    y_trace_zero = (
        not restrict_y(vx, 0)
        and not restrict_y(vy, 0)
    )
    trace_zero = x_trace_zero and y_trace_zero
    velocity_degree = max(degree(vx), degree(vy))
    contained_in_p4 = velocity_degree <= 4

    forcing_pairing = integrate_reference_triangle(vx)
    # On x+y=1, outward n=(1,1)/sqrt(2), ds=sqrt(2) dx, so
    # p v.n ds = x * (vx+vy) dx for p=x.
    pressure_flux_poly = restrict_y_one_minus_x(mul(X, add(vx, vy)))
    pressure_boundary_flux = integrate_1d(pressure_flux_poly, 0, 1)
    pressure_volume_pairing = integrate_reference_triangle(mul(X, div_v))

    require_certificate(not div_v, "local P4 witness is not divergence-free")
    require_certificate(
        trace_zero,
        "local P4 witness does not have zero vector trace on both extension edges",
    )
    require_certificate(
        velocity_degree == 3 and contained_in_p4,
        "local witness is not the claimed P3 subset of full P4",
    )
    require_certificate(
        forcing_pairing == Q(1, 30),
        "local witness forcing pairing changed",
    )
    require_certificate(
        pressure_boundary_flux == forcing_pairing,
        "local witness pressure boundary work no longer matches forcing",
    )
    require_certificate(
        pressure_volume_pairing == 0,
        "local witness volume pressure pairing is nonzero",
    )

    return {
        "velocity_degree": velocity_degree,
        "contained_in_full_P4_velocity_space": contained_in_p4,
        "divergence_polynomial": {
            f"{i},{j}": str(coefficient)
            for (i, j), coefficient in sorted(div_v.items())
        },
        "zero_extension_trace_zero": trace_zero,
        "forcing_pairing": str(forcing_pairing),
        "pressure_volume_pairing": str(pressure_volume_pairing),
        "pressure_boundary_flux": str(pressure_boundary_flux),
        "pressure_free_kernel_lhs_at_u_zero": "0",
        "consistency_defect_lhs_minus_rhs": str(-forcing_pairing),
    }


def local_p4_boundary_triangle_witness() -> dict:
    """A P3 velocity supported on one weak-boundary triangle.

    Reference triangle K has vertices (0,0),(1,0),(0,1). The legs x=0 and
    y=0 are zero-extension edges; the hypotenuse x+y=1 is the weak boundary.
    psi=x^2 y^2 has a double zero on both zero-extension edges, so
    v=curl(psi) has zero vector trace there and may be extended by zero across
    neighboring elements while remaining continuous. Since v is P3, it lies
    in every full P4 velocity space.
    """
    psi = mul(X, X, Y, Y)
    vx = derivative(psi, "y")
    vy = scale(derivative(psi, "x"), -1)
    proof = _certify_local_p4_velocity(vx, vy)

    return {
        "domain": "reference triangle x>=0,y>=0,x+y<=1",
        "zero_extension_edges": ["x=0", "y=0"],
        "weak_boundary_edge": "x+y=1",
        "pressure": "p=x",
        "forcing": "f=(1,0)",
        "stream_function": "psi=x^2 y^2",
        "velocity": "v=(2*x^2*y,-2*x*y^2)",
        **proof,
        "scope": (
            "exact local P3/P4-compatible weak-boundary consistency witness; "
            "extendable by zero across the two non-weak edges"
        ),
    }

def square_annulus_witness() -> dict:
    # Omega = [-2,2]^2 \ [-1,1]^2.
    # psi has a double zero on every outer edge, so both components of
    # v=curl(psi) vanish there. The (1+y) factor prevents cancellation
    # of the weak-inner-boundary pressure work.
    fx = mul(
        add(scale(ONE, 4), scale(mul(X, X), -1)),
        add(scale(ONE, 4), scale(mul(X, X), -1)),
    )
    fy = mul(
        add(scale(ONE, 4), scale(mul(Y, Y), -1)),
        add(scale(ONE, 4), scale(mul(Y, Y), -1)),
    )
    psi = mul(fx, fy, add(ONE, Y))
    vx = derivative(psi, "y")
    vy = scale(derivative(psi, "x"), -1)
    div_v = add(derivative(vx, "x"), derivative(vy, "y"))
    outer_trace_zero = all(
        not trace
        for trace in (
            *(restrict_x(component, x0) for x0 in (-2, 2) for component in (vx, vy)),
            *(restrict_y(component, y0) for y0 in (-2, 2) for component in (vx, vy)),
        )
    )
    velocity_degree = max(degree(vx), degree(vy))

    forcing_pairing = (
        integrate_rect(vx, -2, 2, -2, 2)
        - integrate_rect(vx, -1, 1, -1, 1)
    )
    p_div_v = mul(X, div_v)
    pressure_volume_pairing = (
        integrate_rect(p_div_v, -2, 2, -2, 2)
        - integrate_rect(p_div_v, -1, 1, -1, 1)
    )

    p_vx = mul(X, vx)
    p_vy = mul(X, vy)
    edge_flux = {
        "inner_right_x=1": -integrate_1d(restrict_x(p_vx, 1), -1, 1),
        "inner_left_x=-1": integrate_1d(restrict_x(p_vx, -1), -1, 1),
        "inner_top_y=1": -integrate_1d(restrict_y(p_vy, 1), -1, 1),
        "inner_bottom_y=-1": integrate_1d(restrict_y(p_vy, -1), -1, 1),
    }
    pressure_boundary_flux = sum(edge_flux.values(), Q(0))

    require_certificate(not div_v, "annulus witness is not divergence-free")
    require_certificate(outer_trace_zero, "annulus witness strong outer trace is nonzero")
    require_certificate(velocity_degree == 8, "annulus witness degree changed")
    require_certificate(forcing_pairing == Q(-2436, 5), "annulus forcing pairing changed")
    require_certificate(
        pressure_boundary_flux == forcing_pairing,
        "annulus pressure boundary work no longer matches forcing",
    )
    require_certificate(
        pressure_volume_pairing == 0,
        "annulus volume pressure pairing is nonzero",
    )

    return {
        "domain": "[-2,2]^2 minus [-1,1]^2",
        "strong_boundary": "outer square",
        "weak_boundary": "inner square",
        "pressure": "p=x",
        "forcing": "f=(1,0)",
        "stream_function": "(4-x^2)^2(4-y^2)^2(1+y)",
        "velocity": "v=(d_y psi,-d_x psi)",
        "velocity_degree": velocity_degree,
        "divergence_polynomial": {
            f"{i},{j}": str(coefficient)
            for (i, j), coefficient in sorted(div_v.items())
        },
        "strong_outer_trace_zero": outer_trace_zero,
        "forcing_pairing": str(forcing_pairing),
        "pressure_volume_pairing": str(pressure_volume_pairing),
        "pressure_boundary_flux": str(pressure_boundary_flux),
        "inner_edge_fluxes": {k: str(v) for k, v in edge_flux.items()},
        "pressure_free_kernel_lhs_at_u_zero": "0",
        "consistency_defect_lhs_minus_rhs": str(-forcing_pairing),
        "scope": (
            "mixed-boundary topology witness; velocity degree 8, retained as an "
            "independent sanity check rather than a P4 membership claim"
        ),
    }


def fully_weak_low_degree_witness() -> dict:
    return {
        "domain": "[0,1]^2",
        "boundary": "fully weak",
        "pressure": "p=x",
        "forcing": "f=(1,0)",
        "test_velocity": "v=(1,0)",
        "velocity_degree": 0,
        "divergence": "0",
        "forcing_pairing": "1",
        "pressure_volume_pairing": "0",
        "pressure_boundary_flux": "1",
        "pressure_free_kernel_lhs_at_u_zero": "0",
        "consistency_defect_lhs_minus_rhs": "-1",
        "scope": "exact low-degree fully-weak consistency witness",
    }


def certificate() -> dict:
    return {
        "schema": "commons.ridgway-zerograd-pressure-trace-counterexample/v2",
        "fully_weak_low_degree": fully_weak_low_degree_witness(),
        "local_p4_boundary_triangle": local_p4_boundary_triangle_witness(),
        "strong_outer_weak_inner": square_annulus_witness(),
        "theorem_ceiling": (
            "proves a pressure-normal consistency defect including an exact "
            "P3 velocity witness contained in a full P4 weak-boundary space; "
            "does not prove the full prize convergence theorem, sponsor-specific "
            "curved-domain error lower bound, publication, or prize entitlement"
        ),
    }


if __name__ == "__main__":
    print(json.dumps(certificate(), indent=2, sort_keys=True))
