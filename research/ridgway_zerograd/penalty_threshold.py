#!/usr/bin/env python3
"""Reference-triangle Nitsche penalty threshold for divergence-free P_k vector polynomials.

On K={(x,y): x>=0,y>=0,x+y<=1}, edge e={y=0}, outward n=(0,-1),
compute the smallest edge-scaled penalty mu such that

 A_mu(v,v)=1/2 int_K D(v):D(v) - 2 int_e d_n v . v + mu int_e |v|^2 >= 0

for every exactly divergence-free vector polynomial v in [P_k(K)]^2.
The space is parameterized exactly as curl(P_{k+1}/R).

Matrix assembly uses exact Fraction arithmetic. Generalized eigenvalues use SciPy if
available; that dependency is isolated to threshold extraction.

This is a local coercivity diagnostic, NOT a global Scott-Vogelius convergence proof.
"""
from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from typing import Dict, List, Tuple

Monomial = Tuple[int, int]
Poly = Dict[Monomial, Fraction]
Vec = Tuple[Poly, Poly]


def _add(a: Poly, b: Poly, scale: Fraction = Fraction(1)) -> Poly:
    out = dict(a)
    for monomial, coefficient in b.items():
        out[monomial] = out.get(monomial, Fraction(0)) + scale * coefficient
        if out[monomial] == 0:
            del out[monomial]
    return out


def _mul(a: Poly, b: Poly) -> Poly:
    out: Poly = {}
    for (i, j), c in a.items():
        for (p, q), d in b.items():
            monomial = (i + p, j + q)
            out[monomial] = out.get(monomial, Fraction(0)) + c * d
    return {m: c for m, c in out.items() if c}


def _diff(a: Poly, axis: int) -> Poly:
    out: Poly = {}
    for (i, j), c in a.items():
        exponent = i if axis == 0 else j
        if exponent:
            monomial = (i - 1, j) if axis == 0 else (i, j - 1)
            out[monomial] = out.get(monomial, Fraction(0)) + c * exponent
    return out


def _tri_int(a: Poly) -> Fraction:
    # Integral x^i y^j over reference right triangle = i!j!/(i+j+2)!.
    total = Fraction(0)
    for (i, j), c in a.items():
        total += c * Fraction(math.factorial(i) * math.factorial(j), math.factorial(i + j + 2))
    return total


def _edge_int(a: Poly) -> Fraction:
    # y=0, x in [0,1].
    return sum((c * Fraction(1, i + 1) for (i, j), c in a.items() if j == 0), Fraction(0))


def stream_basis(k: int) -> List[Vec]:
    """Exact basis of [P_k]^2 intersect ker(div) as curls of P_{k+1}/constants."""
    if k < 1:
        raise ValueError("k must be >= 1")
    basis: List[Vec] = []
    for degree in range(1, k + 2):
        for i in range(degree + 1):
            j = degree - i
            psi = {(i, j): Fraction(1)}
            basis.append((_diff(psi, 1), {m: -c for m, c in _diff(psi, 0).items()}))
    return basis


def _dot(a: Vec, b: Vec) -> Poly:
    return _add(_mul(a[0], b[0]), _mul(a[1], b[1]))


def _normal_derivative(v: Vec) -> Vec:
    # n=(0,-1), so partial_n = -partial_y.
    return (
        {m: -c for m, c in _diff(v[0], 1).items()},
        {m: -c for m, c in _diff(v[1], 1).items()},
    )


def _symmetric_gradient_components(v: Vec):
    # Store D11, D12, D22; D12 occurs twice in D:D.
    vx, vy = v
    dxx = _diff(vx, 0)
    dxy = _diff(vx, 1)
    dyx = _diff(vy, 0)
    dyy = _diff(vy, 1)
    return (
        {m: 2 * c for m, c in dxx.items()},
        _add(dxy, dyx),
        {m: 2 * c for m, c in dyy.items()},
    )


def assemble(k: int):
    """Return exact rational matrices A0, B, V.

    A0 is the volume-plus-consistency matrix with zero penalty.
    B is boundary L2 mass.
    V is the diagnostic norm matrix 1/2||D||^2 + ||v||_e^2.
    """
    vectors = stream_basis(k)
    n = len(vectors)
    a0 = [[Fraction(0) for _ in range(n)] for _ in range(n)]
    boundary = [[Fraction(0) for _ in range(n)] for _ in range(n)]
    norm = [[Fraction(0) for _ in range(n)] for _ in range(n)]
    gradients = [_symmetric_gradient_components(v) for v in vectors]
    normal_derivatives = [_normal_derivative(v) for v in vectors]

    for i in range(n):
        for j in range(i, n):
            gi, gj = gradients[i], gradients[j]
            volume = Fraction(1, 2) * (
                _tri_int(_mul(gi[0], gj[0]))
                + 2 * _tri_int(_mul(gi[1], gj[1]))
                + _tri_int(_mul(gi[2], gj[2]))
            )
            b = _edge_int(_dot(vectors[i], vectors[j]))
            cross = -_edge_int(
                _add(
                    _dot(normal_derivatives[i], vectors[j]),
                    _dot(vectors[i], normal_derivatives[j]),
                )
            )
            value = volume + cross
            a0[i][j] = a0[j][i] = value
            boundary[i][j] = boundary[j][i] = b
            norm[i][j] = norm[j][i] = volume + b
    return a0, boundary, norm


def threshold(k: int):
    """Generalized-eigenvalue threshold in edge and triangle-diameter conventions."""
    try:
        import numpy as np
        from scipy.linalg import eig
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "threshold extraction requires numpy+scipy; exact matrix assembly itself is stdlib-only"
        ) from exc

    a0, boundary, norm = assemble(k)
    af = np.array([[float(x) for x in row] for row in a0], dtype=float)
    bf = np.array([[float(x) for x in row] for row in boundary], dtype=float)
    values = eig(-af, bf, right=False)
    finite = [z.real for z in values if np.isfinite(z.real) and abs(z.imag) < 1e-8]
    if not finite:
        raise RuntimeError("no finite generalized eigenvalues")
    edge_scaled = max(finite)
    # Reference triangle diameter h_K=sqrt(2); A uses mu_edge*int_e|v|^2.
    # If written mu_diam/h_K, then mu_diam = mu_edge*h_K.
    diameter_scaled = edge_scaled * math.sqrt(2.0)
    return edge_scaled, diameter_scaled, a0, boundary, norm


def normalized_min_eig(a0, boundary, norm, mu_edge: float) -> float:
    import numpy as np
    from scipy.linalg import eig

    af = np.array([[float(x) for x in row] for row in a0], dtype=float)
    bf = np.array([[float(x) for x in row] for row in boundary], dtype=float)
    vf = np.array([[float(x) for x in row] for row in norm], dtype=float)
    values = eig(af + mu_edge * bf, vf, right=False)
    finite = [z.real for z in values if np.isfinite(z.real) and abs(z.imag) < 1e-8]
    return min(finite)


def global_mu_requirement(local_mu_edge: float, h_global_over_h_edge: float) -> float:
    """Convert local mu/h_e threshold to a global mu/h_global convention."""
    if h_global_over_h_edge <= 0:
        raise ValueError("h_global_over_h_edge must be positive")
    return local_mu_edge * h_global_over_h_edge


def record(k: int):
    edge, diameter, a0, boundary, norm = threshold(k)
    factors = (0, 0.25, 0.5, 0.75, 1, 1.25, 2, 4, 10)
    return {
        "degree": k,
        "basis_dimension": len(a0),
        "reference_triangle": "(0,0),(1,0),(0,1)",
        "boundary_edge": "y=0",
        "edge_scaled_threshold": edge,
        "diameter_scaled_threshold": diameter,
        "normalized_smallest_eigenvalue_by_threshold_factor": [
            {
                "factor": factor,
                "mu_edge": edge * factor,
                "lambda_min": normalized_min_eig(a0, boundary, norm, edge * factor),
            }
            for factor in factors
        ],
        "scope": "local divergence-free polynomial coercivity diagnostic; not a global Scott-Vogelius convergence theorem",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-k", type=int, default=1)
    parser.add_argument("--max-k", type=int, default=5)
    args = parser.parse_args(argv)
    if args.min_k < 1 or args.max_k < args.min_k:
        parser.error("require 1 <= min-k <= max-k")
    print(json.dumps({"records": [record(k) for k in range(args.min_k, args.max_k + 1)]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
