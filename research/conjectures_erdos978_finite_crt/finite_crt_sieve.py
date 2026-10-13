#!/usr/bin/env python3
"""Finite CRT sieve evidence for Erdős 978(iii): n^4 + 2 squarefree infinitely often.

This module deliberately proves/checks only a finite-prime statement.
For a finite set P of distinct odd primes, the residue classes modulo
M = product(p^2, p in P) that avoid every p^2 | n^4+2 factor exactly factor
as the product of the corresponding local good-class counts by CRT.

The existing sponsor contribution already proves the local Hensel facts and
<=4 bad classes per prime.  This file independently checks the arithmetic and
packages the finite product identity; it does NOT control the infinite prime
tail and therefore does not prove the conjecture.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from fractions import Fraction
import argparse
import hashlib
import json
import math
from typing import Sequence

TASK_ID = "fc-8432eac9-parts-iii-778ca9541c-formalized-v1"
TASK_COMMITMENT = "sha256:b80bef9dde235afd4e086e4500d7be4747b878494fb94a14589c639decefc67a"
SOURCE_TYPE_SHA256 = "3e683925ba54f309a76278d99386826c87b151bb5cb1df828d0e3643f0e240fa"
EXISTING_CONTRIBUTION_ID = "9a9241fd706f8b096cd34d40d7d6ba62d230f954361dd8d648e3fb21591f0d0b"
EXISTING_SCRIPT_GIT_BLOB = "8c2962f14f9dfce9ee59b00479d891800f6a7666"


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    d = 3
    while d * d <= n:
        if n % d == 0:
            return False
        d += 2
    return True


def primes_upto(limit: int) -> list[int]:
    return [n for n in range(2, limit + 1) if is_prime(n)]


def bad_residues_mod_p2(p: int) -> tuple[int, ...]:
    if not is_prime(p):
        raise ValueError("p must be prime")
    q = p * p
    return tuple(r for r in range(q) if (pow(r, 4, q) + 2) % q == 0)


def roots_mod_p(p: int) -> tuple[int, ...]:
    if not is_prime(p):
        raise ValueError("p must be prime")
    return tuple(r for r in range(p) if (pow(r, 4, p) + 2) % p == 0)


def egcd(a: int, b: int) -> tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    g, x1, y1 = egcd(b, a % b)
    return g, y1, x1 - (a // b) * y1


def crt_pair(a: int, m: int, b: int, n: int) -> tuple[int, int]:
    """Return unique x mod mn with x=a mod m, x=b mod n, for coprime m,n."""
    if m <= 0 or n <= 0:
        raise ValueError("moduli must be positive")
    g, s, _ = egcd(m, n)
    if g != 1:
        raise ValueError("moduli must be coprime")
    k = ((b - a) * s) % n
    mod = m * n
    return (a + m * k) % mod, mod


def crt(residues: Sequence[int], moduli: Sequence[int]) -> tuple[int, int]:
    if len(residues) != len(moduli):
        raise ValueError("residue/modulus length mismatch")
    x, mod = 0, 1
    for a, m in zip(residues, moduli):
        x, mod = crt_pair(x, mod, a % m, m)
    return x, mod


@dataclass(frozen=True)
class PrimeRecord:
    p: int
    p_mod_8: int
    roots_mod_p: tuple[int, ...]
    bad_mod_p2: tuple[int, ...]

    @property
    def bad_count(self) -> int:
        return len(self.bad_mod_p2)

    @property
    def good_count(self) -> int:
        return self.p * self.p - self.bad_count

    def json_obj(self) -> dict:
        d = asdict(self)
        d["roots_mod_p"] = list(self.roots_mod_p)
        d["bad_mod_p2"] = list(self.bad_mod_p2)
        d["bad_count"] = self.bad_count
        d["good_count"] = self.good_count
        return d


def prime_record(p: int) -> PrimeRecord:
    if p == 2:
        # 4 never divides n^4+2, so local bad set is empty.
        return PrimeRecord(2, 2, tuple(), tuple())
    return PrimeRecord(p, p % 8, roots_mod_p(p), bad_residues_mod_p2(p))


def assert_local_contract(rec: PrimeRecord) -> None:
    p = rec.p
    if p == 2:
        assert rec.bad_count == 0
        return
    # Reduction p^2 -> p must biject roots in this simple-root polynomial.
    reduced = tuple(sorted(r % p for r in rec.bad_mod_p2))
    assert reduced == tuple(sorted(rec.roots_mod_p))
    assert len(set(reduced)) == len(reduced)
    assert rec.bad_count <= 4
    if p % 8 not in (1, 3):
        assert rec.bad_count == 0
    if p % 8 == 3:
        assert rec.bad_count == 2
    if p % 8 == 1:
        assert rec.bad_count in (0, 4)


def finite_sieve_formula(primes: Sequence[int]) -> dict:
    ps = list(primes)
    if len(set(ps)) != len(ps):
        raise ValueError("primes must be distinct")
    if any(not is_prime(p) for p in ps):
        raise ValueError("all entries must be prime")
    records = [prime_record(p) for p in ps]
    for rec in records:
        assert_local_contract(rec)
    moduli = [p * p for p in ps]
    period = math.prod(moduli)
    good_count = math.prod(rec.good_count for rec in records)
    lower_bound = math.prod(max(p * p - 4, 0) for p in ps if p != 2)
    if 2 in ps:
        # p=2 has all 4 classes good, while the generic p^2-4 bound would be 0.
        lower_bound *= 4
    density = Fraction(good_count, period) if period else Fraction(1, 1)
    return {
        "primes": ps,
        "period": period,
        "good_count": good_count,
        "generic_lower_bound": lower_bound,
        "density_num": density.numerator,
        "density_den": density.denominator,
        "records": [r.json_obj() for r in records],
    }


def direct_good_count(primes: Sequence[int]) -> tuple[int, int]:
    """Exhaustively count good classes mod product(p^2). Intended for small P."""
    ps = list(primes)
    if len(set(ps)) != len(ps) or any(not is_prime(p) for p in ps):
        raise ValueError("need distinct primes")
    period = math.prod(p * p for p in ps)
    good = 0
    for n in range(period):
        value = n**4 + 2
        if all(value % (p * p) != 0 for p in ps):
            good += 1
    return period, good


def construct_good_class(local_good_residues: Sequence[int], primes: Sequence[int]) -> tuple[int, int]:
    """Construct one global good residue from a tuple of local good residues."""
    ps = list(primes)
    if len(local_good_residues) != len(ps):
        raise ValueError("length mismatch")
    moduli = [p * p for p in ps]
    x, period = crt(local_good_residues, moduli)
    for a, p in zip(local_good_residues, ps):
        q = p * p
        if (a**4 + 2) % q == 0:
            raise ValueError("input residue is locally bad")
        assert x % q == a % q
        assert (x**4 + 2) % q != 0
    return x, period


def canonical_json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def build_receipt(prime_limit: int = 251, exhaustive_primes: Sequence[int] = (3, 11, 19)) -> dict:
    if prime_limit < 3:
        raise ValueError("prime_limit must be >= 3")
    records = [prime_record(p) for p in primes_upto(prime_limit)]
    for rec in records:
        assert_local_contract(rec)

    local_rows = [r.json_obj() for r in records]
    local_digest = hashlib.sha256(canonical_json_bytes(local_rows)).hexdigest()

    formula = finite_sieve_formula(exhaustive_primes)
    direct_period, direct_count = direct_good_count(exhaustive_primes)
    assert direct_period == formula["period"]
    assert direct_count == formula["good_count"]

    active = [r for r in records if r.bad_count]
    no_bad_outside = all(r.p_mod_8 in (1, 3) for r in active)
    max_bad = max(r.bad_count for r in records)

    receipt = {
        "schema": "erdos978-finite-crt-sieve-receipt-v1",
        "task": {
            "task_id": TASK_ID,
            "task_commitment": TASK_COMMITMENT,
            "source_type_sha256": SOURCE_TYPE_SHA256,
        },
        "existing_piece_deconfliction": {
            "contribution_id": EXISTING_CONTRIBUTION_ID,
            "script_git_blob": EXISTING_SCRIPT_GIT_BLOB,
            "owns": "per-prime Hensel correspondence, p mod 8 restriction, <=4 local bad classes",
            "this_receipt_adds": "finite CRT product composition and exact periodic finite-sieve counts",
        },
        "prime_scan": {
            "limit": prime_limit,
            "prime_count": len(records),
            "active_prime_count": len(active),
            "max_bad_classes": max_bad,
            "all_active_primes_mod8_1_or_3": no_bad_outside,
            "records_sha256": local_digest,
        },
        "exhaustive_crt_control": {
            "primes": list(exhaustive_primes),
            "period": direct_period,
            "direct_good_count": direct_count,
            "product_good_count": formula["good_count"],
            "generic_lower_bound": formula["generic_lower_bound"],
            "density_num": formula["density_num"],
            "density_den": formula["density_den"],
        },
        "evidence_ceiling": "finite-prime CRT sieve only; the unbounded prime-square tail remains uncontrolled; not a proof of infinitely many squarefree n^4+2",
    }
    payload = canonical_json_bytes(receipt)
    receipt["receipt_payload_sha256"] = hashlib.sha256(payload).hexdigest()
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prime-limit", type=int, default=251)
    ap.add_argument("--receipt", action="store_true", help="emit canonical receipt JSON")
    ns = ap.parse_args()
    receipt = build_receipt(ns.prime_limit)
    if ns.receipt:
        print(json.dumps(receipt, sort_keys=True, indent=2))
    else:
        c = receipt["exhaustive_crt_control"]
        print(f"PASS primes<= {ns.prime_limit}; CRT control period={c['period']} good={c['direct_good_count']}; sha={receipt['receipt_payload_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
