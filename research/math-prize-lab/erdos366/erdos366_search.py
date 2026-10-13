#!/usr/bin/env python3
"""Exact bounded search for Conjectures.io / Erdős problem 366.

Target orientation:
    exists n > 0 with n 2-full and n+1 3-full.

The search is exhaustive up to an inclusive successor bound B:
it enumerates every 3-full m <= B by prime factorization, then tests n=m-1
for 2-fullness.  A negative finite search is computational evidence only,
not a proof of global nonexistence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Sequence

VERSION = "erdos366-search-v1"

OEIS_A060355_SUCCESSOR_OBSTRUCTIONS = ((8, 3), (288, 17), (675, 2), (9800, 11), (12167, 3), (235224, 5), (332928, 577), (465124, 61), (1825200, 7), (11309768, 3), (384199200, 17), (592192224, 5), (4931691075, 2), (5425069447, 26041), (13051463048, 3), (221322261600, 9601), (443365544448, 665857), (865363202000, 41), (8192480787000, 7), (11968683934831, 7841), (13325427460800, 97), (15061377048200, 11), (28821995554247, 13), (48689748233307, 2), (511643454094368, 17), (1558709801289000, 19), (17050177433963583, 29), (17380816062160328, 3), (36005300067391875, 2), (208241673295152024, 5), (590436102659356800, 97), (1402766523033033600, 2543), (1610006506595061124, 17), (20057446674355970888, 3), (97286307456665386800, 7), (117725514040791821024, 3), (161461422688535037152, 1553), (681362750825443653408, 17), (3887785221910670811499, 2))


def integer_nth_root(n: int, k: int) -> int:
    if n < 0 or k <= 0:
        raise ValueError("need n >= 0 and k > 0")
    if n < 2:
        return n
    lo, hi = 0, 2
    while pow(hi, k) <= n:
        hi *= 2
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if pow(mid, k) <= n:
            lo = mid
        else:
            hi = mid
    return lo


def primes_upto(limit: int) -> list[int]:
    if limit < 2:
        return []
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    p = 2
    while p * p <= limit:
        if sieve[p]:
            start = p * p
            sieve[start : limit + 1 : p] = b"\x00" * (
                ((limit - start) // p) + 1
            )
        p += 1
    return [i for i in range(2, limit + 1) if sieve[i]]


@dataclass(frozen=True)
class FullCheck:
    is_full: bool
    factors_seen: tuple[tuple[int, int], ...]
    rejecting_prime: int | None = None
    rejecting_exponent: int | None = None


def check_k_full(n: int, k: int, primes: Sequence[int]) -> FullCheck:
    """Exactly decide k-fullness by trial division.

    `primes` must include every prime <= sqrt(n).  The search command builds
    such a table from its declared bound.  For n=1 the defining universal
    condition is vacuous; our target separately requires n>0.
    """
    if n <= 0:
        return FullCheck(False, ())
    if n == 1:
        return FullCheck(True, ())
    x = n
    factors: list[tuple[int, int]] = []
    for p in primes:
        if p * p > x:
            break
        if x % p:
            continue
        e = 0
        while x % p == 0:
            x //= p
            e += 1
        factors.append((p, e))
        if e < k:
            return FullCheck(False, tuple(factors), p, e)
    if x > 1:
        # Because p*p > x at loop exit, x is prime and occurs to exponent 1.
        factors.append((x, 1))
        if k > 1:
            return FullCheck(False, tuple(factors), x, 1)
    return FullCheck(True, tuple(factors))


def enumerate_k_full(bound: int, k: int) -> list[tuple[int, tuple[tuple[int, int], ...]]]:
    """Enumerate every k-full integer in [2,bound], exactly once.

    Canonical construction: choose prime factors in strictly increasing order
    and give each selected prime an exponent e>=k.  Every k-full factorization
    has exactly one such ordered representation.
    """
    if bound < 2:
        return []
    primes = primes_upto(integer_nth_root(bound, k))
    out: list[tuple[int, tuple[tuple[int, int], ...]]] = []

    def rec(start: int, current: int, fs: tuple[tuple[int, int], ...]) -> None:
        for i in range(start, len(primes)):
            p = primes[i]
            pk = pow(p, k)
            if current * pk > bound:
                break
            value = current * pk
            e = k
            while value <= bound:
                next_fs = fs + ((p, e),)
                out.append((value, next_fs))
                rec(i + 1, value, next_fs)
                value *= p
                e += 1

    rec(0, 1, ())
    out.sort(key=lambda item: item[0])
    return out


def factors_product(fs: Iterable[tuple[int, int]]) -> int:
    out = 1
    for p, e in fs:
        out *= pow(p, e)
    return out


def factors_text(fs: Iterable[tuple[int, int]]) -> str:
    return "*".join(f"{p}^{e}" for p, e in fs) or "1"


def search(bound: int) -> dict:
    if bound < 2:
        raise ValueError("bound must be >= 2")
    successors = enumerate_k_full(bound, 3)
    trial_primes = primes_upto(integer_nth_root(bound, 2))
    h = hashlib.sha256()
    witnesses: list[dict] = []

    for m, m_factors in successors:
        assert factors_product(m_factors) == m
        assert all(e >= 3 for _, e in m_factors)
        n = m - 1
        chk = check_k_full(n, 2, trial_primes)
        if chk.is_full:
            # Complete factorization has been recovered when the check succeeds.
            witnesses.append(
                {
                    "n": n,
                    "n_factors": list(chk.factors_seen),
                    "n_plus_1": m,
                    "n_plus_1_factors": list(m_factors),
                }
            )
            record = (
                f"W|{n}|{factors_text(chk.factors_seen)}|"
                f"{m}|{factors_text(m_factors)}\n"
            )
        else:
            assert chk.rejecting_prime is not None
            assert chk.rejecting_exponent is not None
            p = chk.rejecting_prime
            e = chk.rejecting_exponent
            assert n % pow(p, e) == 0
            assert n % pow(p, e + 1) != 0
            record = (
                f"R|{n}|{p}^{e}|{m}|{factors_text(m_factors)}\n"
            )
        h.update(record.encode("ascii"))

    return {
        "schema_version": 1,
        "engine": VERSION,
        "target": "exists n>0: Nat.Full 2 n and Nat.Full 3 (n+1)",
        "successor_bound_inclusive": bound,
        "enumerated_3full_successors": len(successors),
        "witness_count": len(witnesses),
        "witnesses": witnesses,
        "record_digest_sha256": h.hexdigest(),
        "interpretation": (
            "Exhaustive only for n+1 <= successor_bound_inclusive; "
            "zero witnesses is not a global nonexistence proof."
        ),
    }


def check_oeis_baseline() -> dict:
    """Verify explicit orientation obstructions for the first 39 OEIS entries.

    This deliberately does *not* claim that the OEIS list is complete, nor
    does it need to factor the large entries.  For each listed pair-start n,
    the embedded prime p is checked to satisfy p^2 || (n+1), which alone
    proves that this successor is not 3-full.
    """
    rows = []
    h = hashlib.sha256()
    for n, p in OEIS_A060355_SUCCESSOR_OBSTRUCTIONS:
        m = n + 1
        assert m % (p * p) == 0
        assert m % (p * p * p) != 0
        row = {
            "n": n,
            "successor": m,
            "successor_rejecting_prime_for_3full": p,
            "successor_rejecting_exponent": 2,
        }
        rows.append(row)
        h.update(f"{n}|{m}|{p}^2\n".encode("ascii"))
    return {
        "source": "OEIS A060355 b-file, first 39 listed terms",
        "claim_scope": (
            "Orientation check for the listed terms only.  It verifies an "
            "explicit p^2 || (n+1) obstruction for each successor; it does "
            "not certify OEIS-list completeness below any bound."
        ),
        "listed_terms_checked": len(rows),
        "none_has_3full_successor": True,
        "row_digest_sha256": h.hexdigest(),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bound", type=int, default=1_000_000_000_000)
    parser.add_argument("--oeis-baseline", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    payload = {
        "search": search(args.bound),
    }
    if args.oeis_baseline:
        payload["oeis_baseline"] = check_oeis_baseline()
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
