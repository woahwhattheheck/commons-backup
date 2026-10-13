#!/usr/bin/env python3
"""Exact algebraic certificate for the strong-boundary Scott–Vogelius jet obstruction.

No third-party dependencies. All determinant/rank arithmetic uses fractions.Fraction.
This complements penalty_threshold.py: it studies the strong Dirichlet first-jet
constraint, not Nitsche coercivity.
"""
from __future__ import annotations

from fractions import Fraction
from typing import List, Tuple

Q = Fraction
Vector = Tuple[Q, Q]
Matrix = List[List[Q]]


def cross(a: Vector, b: Vector) -> Q:
    return a[0] * b[1] - a[1] * b[0]


def strong_constraint_matrix(t1: Vector, t2: Vector, s: Vector) -> Matrix:
    """First-jet constraints for two boundary triangles.

    Unknowns are (a,b,c,d,e,f,g,h) for
    A1=[[a,b],[c,d]], A2=[[e,f],[g,h]]. Rows encode
    tr(A1)=tr(A2)=0, A1*t1=0, A2*t2=0, and A1*s=A2*s.
    """
    u, v = t1
    p, q = t2
    r, w = s
    return [
        [Q(1), 0, 0, Q(1), 0, 0, 0, 0],
        [0, 0, 0, 0, Q(1), 0, 0, Q(1)],
        [u, v, 0, 0, 0, 0, 0, 0],
        [0, 0, u, v, 0, 0, 0, 0],
        [0, 0, 0, 0, p, q, 0, 0],
        [0, 0, 0, 0, 0, 0, p, q],
        [r, w, 0, 0, -r, -w, 0, 0],
        [0, 0, r, w, 0, 0, -r, -w],
    ]


def weak_constraint_matrix(s: Vector) -> Matrix:
    """Constraints remaining when strong boundary trace equations are removed."""
    r, w = s
    return [
        [Q(1), 0, 0, Q(1), 0, 0, 0, 0],
        [0, 0, 0, 0, Q(1), 0, 0, Q(1)],
        [r, w, 0, 0, -r, -w, 0, 0],
        [0, 0, r, w, 0, 0, -r, -w],
    ]


def determinant(a: Matrix) -> Q:
    n = len(a)
    if any(len(row) != n for row in a):
        raise ValueError("determinant requires a square matrix")
    m = [list(map(Q, row)) for row in a]
    det = Q(1)
    for col in range(n):
        pivot = next((r for r in range(col, n) if m[r][col]), None)
        if pivot is None:
            return Q(0)
        if pivot != col:
            m[col], m[pivot] = m[pivot], m[col]
            det = -det
        pv = m[col][col]
        det *= pv
        for j in range(col, n):
            m[col][j] /= pv
        for r in range(col + 1, n):
            factor = m[r][col]
            if factor:
                for j in range(col, n):
                    m[r][j] -= factor * m[col][j]
    return det


def rank(a: Matrix) -> int:
    if not a:
        return 0
    m = [list(map(Q, row)) for row in a]
    rows, cols = len(m), len(m[0])
    rr = cc = 0
    while rr < rows and cc < cols:
        pivot = next((r for r in range(rr, rows) if m[r][cc]), None)
        if pivot is None:
            cc += 1
            continue
        m[rr], m[pivot] = m[pivot], m[rr]
        pv = m[rr][cc]
        m[rr] = [x / pv for x in m[rr]]
        for r in range(rows):
            if r == rr:
                continue
            factor = m[r][cc]
            if factor:
                m[r] = [x - factor * y for x, y in zip(m[r], m[rr])]
        rr += 1
        cc += 1
    return rr


def predicted_strong_determinant(t1: Vector, t2: Vector, s: Vector) -> Q:
    """Closed form for the chosen row ordering."""
    return cross(t2, s) * cross(t2, t1) * cross(s, t1)


def manufactured_gradient(x: Q, y: Q) -> Matrix:
    """Gradient on r=1 of u=(1-r^-2)(-y,x)."""
    if x * x + y * y != 1:
        raise ValueError("boundary identity requires x^2+y^2=1")
    return [[-2 * x * y, -2 * y * y], [2 * x * x, 2 * x * y]]


def frobenius_sq(a: Matrix) -> Q:
    return sum((x * x for row in a for x in row), Q(0))


def certificate() -> dict:
    samples = [
        ((Q(1), Q(0)), (Q(0), Q(1)), (Q(1), Q(1))),
        ((Q(2), Q(1)), (Q(-1), Q(3)), (Q(1), Q(2))),
        ((Q(1), Q(2)), (Q(3), Q(-1)), (Q(2), Q(3))),
    ]
    det_checks = []
    for t1, t2, s in samples:
        actual = determinant(strong_constraint_matrix(t1, t2, s))
        expected = predicted_strong_determinant(t1, t2, s)
        if actual != expected or actual == 0:
            raise AssertionError((t1, t2, s, actual, expected))
        if rank(strong_constraint_matrix(t1, t2, s)) != 8:
            raise AssertionError("strong constraint matrix lost full rank")
        if rank(weak_constraint_matrix(s)) != 4:
            raise AssertionError("weak constraint rank changed")
        det_checks.append((str(actual), str(expected)))

    grad_norm_sq = []
    for x, y in [(Q(1), Q(0)), (Q(0), Q(1)), (Q(3, 5), Q(4, 5))]:
        g = manufactured_gradient(x, y)
        if frobenius_sq(g) != 4 or g[0][0] + g[1][1] != 0:
            raise AssertionError((x, y, g))
        grad_norm_sq.append(str(frobenius_sq(g)))

    return {
        "strong_rank": 8,
        "strong_nullity": 0,
        "weak_rank": 4,
        "weak_nullity": 4,
        "determinant_formula": "cross(t2,s)*cross(t2,t1)*cross(s,t1)",
        "determinant_checks": det_checks,
        "manufactured_boundary_gradient_frobenius_sq": grad_norm_sq,
        "evidence_ceiling": "exact first-jet certificate plus conditional H1 lower-bound theorem; not Nitsche prize proof",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(certificate(), indent=2, sort_keys=True))
