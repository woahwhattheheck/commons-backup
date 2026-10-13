"""Exact local divergence [P_k]^3 -> P_{k-1} on one tetrahedron.

Continuity, boundary vanishing, and singular-vertex constraints are excluded.
This is not a mesh-uniform inf-sup certificate.
"""

from __future__ import annotations

from fractions import Fraction
from math import comb


def dim_pk(k: int) -> int:
    """dim P_k(R^3) = binom(k+3, 3)."""
    if k < 0:
        return 0
    return comb(k + 3, 3)


def monomials(k: int) -> list[tuple[int, int, int]]:
    mons: list[tuple[int, int, int]] = []
    for a in range(k + 1):
        for b in range(k + 1 - a):
            for c in range(k + 1 - a - b):
                mons.append((a, b, c))
    if len(mons) != dim_pk(k):
        raise RuntimeError("monomial count != binom(k+3,3)")
    return mons


def _rank_over_q(matrix: list[list[Fraction]]) -> int:
    if not matrix:
        return 0
    rows = len(matrix)
    cols = len(matrix[0])
    data = [row[:] for row in matrix]
    rank = 0
    row = 0
    for col in range(cols):
        pivot = None
        for r in range(row, rows):
            if data[r][col] != 0:
                pivot = r
                break
        if pivot is None:
            continue
        data[row], data[pivot] = data[pivot], data[row]
        piv = data[row][col]
        inv = Fraction(1, 1) / piv
        for c in range(col, cols):
            data[row][c] *= inv
        for r in range(rows):
            if r == row or data[r][col] == 0:
                continue
            factor = data[r][col]
            for c in range(col, cols):
                data[r][c] -= factor * data[row][c]
        rank += 1
        row += 1
        if row == rows:
            break
    return rank


def local_div_matrix(k: int) -> list[list[Fraction]]:
    """Rows: P_{k-1} monomials. Cols: 3 copies of P_k monomials (u, v, w)."""
    src = monomials(k)
    dst = monomials(k - 1)
    dst_index = {m: i for i, m in enumerate(dst)}
    cols = 3 * len(src)
    matrix = [[Fraction(0) for _ in range(cols)] for _ in dst]
    for j, (a, b, c) in enumerate(src):
        if a:
            matrix[dst_index[(a - 1, b, c)]][j] = Fraction(a)
        if b:
            matrix[dst_index[(a, b - 1, c)]][len(src) + j] = Fraction(b)
        if c:
            matrix[dst_index[(a, b, c - 1)]][2 * len(src) + j] = Fraction(c)
    return matrix


def local_div_qrank(k: int) -> int:
    if k < 1:
        raise ValueError("k must be >= 1")
    return _rank_over_q(local_div_matrix(k))
