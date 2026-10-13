"""Exact modular-obstruction and exponent-cover experiments for A303656."""

from __future__ import annotations

from hashlib import sha256
from typing import Iterable


def _mask_limit(modulus: int) -> int:
    if modulus < 2:
        raise ValueError("modulus must be at least 2")
    return (1 << modulus) - 1


def _rotate(mask: int, shift: int, modulus: int) -> int:
    shift %= modulus
    limit = _mask_limit(modulus)
    mask &= limit
    if shift == 0:
        return mask
    return ((mask << shift) | (mask >> (modulus - shift))) & limit


def _bits(mask: int) -> Iterable[int]:
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


def _sumset(left: int, right: int, modulus: int) -> int:
    # Iterate the sparser side; rotation performs the full cyclic translation.
    if left.bit_count() < right.bit_count():
        left, right = right, left
    result = 0
    limit = _mask_limit(modulus)
    for shift in _bits(right):
        result |= _rotate(left, shift, modulus)
        if result == limit:
            break
    return result


def power_residue_mask(base: int, modulus: int) -> int:
    """Residues attained by base^e (mod modulus) for all e>=0."""
    _mask_limit(modulus)
    seen: set[int] = set()
    value = 1 % modulus
    while value not in seen:
        seen.add(value)
        value = value * base % modulus
    return sum(1 << residue for residue in seen)


def square_residue_mask(modulus: int) -> int:
    _mask_limit(modulus)
    return sum(1 << residue for residue in {(x * x) % modulus for x in range(modulus)})


def a303656_coverage_mask(modulus: int) -> int:
    """Residues locally represented by x^2+y^2+3^c+5^d modulo modulus."""
    squares = square_residue_mask(modulus)
    two_squares = _sumset(squares, squares, modulus)
    shifts = _sumset(
        power_residue_mask(3, modulus),
        power_residue_mask(5, modulus),
        modulus,
    )
    return _sumset(two_squares, shifts, modulus)


def missing_residues(modulus: int) -> tuple[int, ...]:
    coverage = a303656_coverage_mask(modulus)
    return tuple(r for r in range(modulus) if not (coverage >> r) & 1)


def primes_below(limit: int) -> tuple[int, ...]:
    if limit <= 2:
        return ()
    sieve = bytearray(b"\x01") * limit
    sieve[0:2] = b"\x00\x00"
    for p in range(2, int((limit - 1) ** 0.5) + 1):
        if sieve[p]:
            start = p * p
            sieve[start:limit:p] = b"\x00" * (((limit - 1 - start) // p) + 1)
    return tuple(i for i, flag in enumerate(sieve) if flag)


def greedy_congruence_cover(
    c_limit: int = 160,
    d_limit: int = 110,
    prime_limit: int = 5000,
) -> dict[str, object]:
    """Try one CRT residue per 3 mod 4 prime; report, never overclaim, coverage.

    For each prime p in ascending order, choose the residue n mod p that covers
    the largest number of *currently uncovered* exponent pairs through
    p | n - 3^c - 5^d.  Such divisibility is only a necessary ingredient for a
    counterexample certificate: odd p-adic valuation would still be required.
    """
    if min(c_limit, d_limit) <= 0 or prime_limit <= 3:
        raise ValueError("limits must be positive")
    primes = tuple(
        p for p in primes_below(prime_limit) if p % 4 == 3 and p != 3
    )
    width = d_limit
    uncovered = set(range(c_limit * d_limit))
    choices: list[tuple[int, int, int]] = []
    for p in primes:
        powers3 = [pow(3, c, p) for c in range(c_limit)]
        powers5 = [pow(5, d, p) for d in range(d_limit)]
        buckets: dict[int, list[int]] = {}
        for index in uncovered:
            c, d = divmod(index, width)
            residue = (powers3[c] + powers5[d]) % p
            buckets.setdefault(residue, []).append(index)
        if not buckets:
            break
        residue, covered = min(
            buckets.items(), key=lambda item: (-len(item[1]), item[0])
        )
        uncovered.difference_update(covered)
        choices.append((p, residue, len(covered)))

    coordinates = tuple(divmod(index, width) for index in sorted(uncovered))
    digest = sha256(
        "\n".join(f"{c},{d}" for c, d in coordinates).encode("ascii")
    ).hexdigest()
    return {
        "cLimit": c_limit,
        "dLimit": d_limit,
        "pairCount": c_limit * d_limit,
        "primeLimitExclusive": prime_limit,
        "eligiblePrimeCount": len(primes),
        "usedPrimeCount": len(choices),
        "coveredPairCount": c_limit * d_limit - len(coordinates),
        "uncoveredPairCount": len(coordinates),
        "uncoveredCoordinatesSha256": digest,
        "firstChoices": [list(item) for item in choices[:12]],
        "lastChoices": [list(item) for item in choices[-12:]],
    }


def local_census(moduli: Iterable[int]) -> dict[str, object]:
    values = tuple(sorted(set(moduli)))
    obstructed: dict[str, list[int]] = {}
    for modulus in values:
        missing = missing_residues(modulus)
        if missing:
            obstructed[str(modulus)] = list(missing)
    return {
        "modulusCount": len(values),
        "minimumModulus": min(values) if values else None,
        "maximumModulus": max(values) if values else None,
        "obstructed": obstructed,
        "allLocallyCovered": not obstructed,
    }
