"""Exact count-normalization checks for the arXiv:2606.04744 source audit.

This module does not prove or refute Theorem 1.3.  It checks the representation-
count conventions used in the audit with dependency-free integer arithmetic.
"""
from __future__ import annotations

import argparse
import json
from math import isqrt
from typing import Any


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def natural(value: Any, name: str, maximum: int = 100_000) -> int:
    require(type(value) is int and 0 <= value <= maximum, f"invalid {name}")
    return value


def nonnegative_representations(m: int) -> list[tuple[int, int, int]]:
    """Ordered triples in N_0^3 with x^2+y^2+z^2=m."""
    m = natural(m, "m")
    bound = isqrt(m)
    rows: list[tuple[int, int, int]] = []
    for x in range(bound + 1):
        x2 = x * x
        for y in range(bound + 1):
            rem = m - x2 - y * y
            if rem < 0:
                break
            z = isqrt(rem)
            if z * z == rem:
                rows.append((x, y, z))
    return rows


def signed_representations(m: int) -> int:
    """Number of ordered triples in Z^3 with x^2+y^2+z^2=m."""
    rows = nonnegative_representations(m)
    return sum(1 << sum(coordinate != 0 for coordinate in row) for row in rows)


def nonnegative_count(m: int) -> int:
    return len(nonnegative_representations(m))


def signed_by_direct_enumeration(m: int) -> int:
    """Independent small-input oracle, intentionally slower than orbit weighting."""
    m = natural(m, "m", 10_000)
    bound = isqrt(m)
    count = 0
    for x in range(-bound, bound + 1):
        x2 = x * x
        for y in range(-bound, bound + 1):
            rem = m - x2 - y * y
            if rem < 0:
                continue
            z = isqrt(rem)
            if z * z != rem:
                continue
            count += 1 if z == 0 else 2
    return count


def square_residues_mod8() -> set[int]:
    return {x * x % 8 for x in range(8)}


def verify(limit: int = 512) -> dict[str, Any]:
    limit = natural(limit, "limit", 4096)
    require(limit >= 64, "limit must be at least 64")
    require(square_residues_mod8() == {0, 1, 4}, "unexpected square residues mod 8")

    for m in range(limit + 1):
        weighted = signed_representations(m)
        if m <= 256:
            require(weighted == signed_by_direct_enumeration(m), "signed orbit identity failed")
        if m % 8 == 3:
            rows = nonnegative_representations(m)
            require(all(all(coordinate & 1 for coordinate in row) for row in rows),
                    "3 mod 8 representation has an even coordinate")
            require(weighted == 8 * len(rows), "3 mod 8 octant factor is not 8")

    powers = []
    value = 1
    k = 0
    while value <= limit:
        nonnegative = nonnegative_count(value)
        signed = signed_representations(value)
        require(nonnegative == 3, "r3(4^k) nonnegative normalization changed")
        require(signed == 6, "signed 4^k count changed")
        powers.append({"k": k, "m": value, "nonnegative": nonnegative, "signed": signed})
        value *= 4
        k += 1

    examples = []
    for m in range(3, min(limit, 99) + 1, 8):
        nonnegative = nonnegative_count(m)
        signed = signed_representations(m)
        require(signed == 8 * nonnegative, "example ratio failed")
        examples.append({"m": m, "nonnegative": nonnegative, "signed": signed})

    return {
        "result": "CONFIRMED_COUNT_CONVENTION_GAP",
        "arxiv_version": "2606.04744v1",
        "verified_through": limit,
        "square_residues_mod8": sorted(square_residues_mod8()),
        "power4_counts": powers,
        "mod8_eq_3_examples": examples,
        "paper_theorem_refuted": False,
        "normalization_repair_requires_proof_recheck": True,
    }


def self_test() -> dict[str, Any]:
    """Run regression controls without unittest or assertion statements."""
    require(square_residues_mod8() == {0, 1, 4}, "square residue regression")
    for k in range(8):
        m = 4**k
        require(nonnegative_count(m) == 3, "power-four nonnegative regression")
        require(signed_representations(m) == 6, "power-four signed regression")
    for m in range(3, 300, 8):
        rows = nonnegative_representations(m)
        require(all(all(c % 2 == 1 for c in row) for row in rows), "parity regression")
        require(signed_representations(m) == 8 * len(rows), "free-sign regression")
    for m in range(129):
        require(signed_representations(m) == signed_by_direct_enumeration(m),
                "direct signed-oracle regression")
    require((nonnegative_count(3), signed_representations(3)) == (1, 8), "m=3 regression")
    require((nonnegative_count(11), signed_representations(11)) == (3, 24), "m=11 regression")
    require((nonnegative_count(27), signed_representations(27)) == (4, 32), "m=27 regression")
    full = verify(512)
    require(full["verified_through"] == 512, "full verifier regression")
    return {"result": "SELF_TEST_PASS", "checks": 8, "verified_through": 512,
            "paper_theorem_refuted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=512)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        result = self_test() if args.self_test else verify(args.limit)
    except (ValueError, OverflowError) as exc:
        parser.exit(1, f"INVALID: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
