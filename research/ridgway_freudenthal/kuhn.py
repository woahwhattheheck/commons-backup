"""Exact Freudenthal/Kuhn cube geometry. Not a mesh-uniform inf-sup proof."""

from __future__ import annotations

from itertools import permutations
from typing import Sequence

Vertex = tuple[int, int, int]
Tet = tuple[Vertex, Vertex, Vertex, Vertex]


def tet_volume_times_6(tet: Sequence[Sequence[int]]) -> int:
    """Signed 6*volume of a tetrahedron with integer vertices."""
    a, b, c, d = (tuple(p) for p in tet)
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    w = (d[0] - a[0], d[1] - a[1], d[2] - a[2])
    return (
        u[0] * (v[1] * w[2] - v[2] * w[1])
        - u[1] * (v[0] * w[2] - v[2] * w[0])
        + u[2] * (v[0] * w[1] - v[1] * w[0])
    )


def _oriented_kuhn_tets() -> tuple[Tet, ...]:
    tets: list[Tet] = []
    for perm in permutations((0, 1, 2)):
        acc = [0, 0, 0]
        verts: list[Vertex] = [(0, 0, 0)]
        for axis in perm:
            acc[axis] = 1
            verts.append((acc[0], acc[1], acc[2]))
        if tet_volume_times_6(verts) < 0:
            verts[1], verts[2] = verts[2], verts[1]
        tet = (verts[0], verts[1], verts[2], verts[3])
        if tet_volume_times_6(tet) != 1:
            raise RuntimeError("Kuhn tet failed positive unit 6-volume")
        tets.append(tet)
    if len(tets) != 6:
        raise RuntimeError("Kuhn cube must have six tets")
    return tuple(tets)


KUHN_TETS: tuple[Tet, ...] = _oriented_kuhn_tets()


def kuhn_tets() -> tuple[Tet, ...]:
    return KUHN_TETS


def refine_n(n: int) -> int:
    """Number of Kuhn tets in the affine n x n x n grid of the unit cube."""
    if n < 1:
        raise ValueError("n must be >= 1")
    return 6 * n * n * n
