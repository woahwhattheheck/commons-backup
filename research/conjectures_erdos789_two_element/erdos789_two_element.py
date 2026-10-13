"""Exact finite verifier for the two-element Erdős 789 separating-subset lemma.

This module is evidence/support code, not a proof of the asymptotic conjecture.
"""
from __future__ import annotations
from itertools import combinations
from hashlib import sha256
import json

def nonempty_subsets(values: tuple[int, ...]):
    for r in range(1, len(values)+1):
        yield from combinations(values, r)

def is_separating(values) -> bool:
    """True iff equal sums of nonempty subsets always have equal cardinality."""
    vals = tuple(sorted(values))
    seen: dict[int, int] = {}
    for subset in nonempty_subsets(vals):
        s = sum(subset)
        k = len(subset)
        old = seen.get(s)
        if old is not None and old != k:
            return False
        seen[s] = k
    return True

def choose_two_nonzero(values) -> tuple[int, int]:
    """Canonical witness for |A|>=3: the two smallest nonzero members."""
    vals = tuple(sorted(set(values)))
    nz = tuple(x for x in vals if x != 0)
    if len(vals) < 3:
        raise ValueError("need at least three distinct integers")
    if len(nz) < 2:
        raise AssertionError("a set of >=3 distinct integers has >=2 nonzero members")
    return nz[0], nz[1]

def theorem_witness(values) -> tuple[int, int]:
    """Return B witnessing the universal m=2 lower bound for a finite input A."""
    vals = tuple(sorted(set(values)))
    b = choose_two_nonzero(vals)
    assert set(b).issubset(vals)
    assert len(b) == 2
    assert is_separating(b)
    return b

def max_separating_subset_size(values) -> int:
    vals = tuple(sorted(set(values)))
    best = 0
    for r in range(len(vals)+1):
        for sub in combinations(vals, r):
            if r == 0 or is_separating(sub):
                best = max(best, r)
    return best

UPPER_BOUND_WITNESSES = {
    1: (0,),
    2: (0, 1),
    3: (1, 2, 3),
    4: (-1, 0, 1, 2),
}

def make_receipt(radius: int = 6, max_n: int = 8) -> dict:
    universe = tuple(range(-radius, radius+1))
    h = sha256()
    cases = 0
    by_n: dict[str, int] = {}
    for n in range(3, min(max_n, len(universe))+1):
        n_cases = 0
        for A in combinations(universe, n):
            B = theorem_witness(A)
            record = {"A": A, "B": B}
            h.update((json.dumps(record, separators=(",", ":"), sort_keys=True)+"\n").encode())
            cases += 1
            n_cases += 1
        by_n[str(n)] = n_cases
    exact_controls = {}
    for n, A in UPPER_BOUND_WITNESSES.items():
        exact_controls[str(n)] = {
            "A": list(A),
            "max_separating_subset_size": max_separating_subset_size(A),
        }
    return {
        "claim": "finite regression for n>=3 universal two-nonzero construction; exact small-n upper controls",
        "radius": radius,
        "max_n": max_n,
        "universe_size": len(universe),
        "bounded_construction_cases": cases,
        "cases_by_n": by_n,
        "case_stream_sha256": h.hexdigest(),
        "exact_small_n_controls": exact_controls,
        "evidence_ceiling": "bounded executable regression only; general lemma is justified separately by the mathematical argument",
    }

if __name__ == "__main__":
    print(json.dumps(make_receipt(), indent=2, sort_keys=True))
