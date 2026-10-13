from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

TASK_ID = "fc-8432eac9-erdos891-erdos-891-f7c029a9da-formalized-v1"
TASK_COMMITMENT = "sha256:f27b7e330416cb7906fe33072ed51ac3014c29e6ca3b8d66cba9338147745501"
SOURCE_TYPE_SHA256 = "3114dca122af84199da3e5a5680ee5f110455c698328c16ce9954ae0f4de74de"


def first_primes(count: int) -> list[int]:
    if count < 0:
        raise ValueError("count must be nonnegative")
    if count == 0:
        return []
    # Rosser-style bound is unnecessary at these tiny counts; grow deterministically.
    bound = 16
    while True:
        sieve = bytearray(b"\x01") * (bound + 1)
        sieve[0:2] = b"\x00\x00"
        p = 2
        while p * p <= bound:
            if sieve[p]:
                start = p * p
                sieve[start : bound + 1 : p] = b"\x00" * (((bound - start) // p) + 1)
            p += 1
        values = [n for n in range(2, bound + 1) if sieve[n]]
        if len(values) >= count:
            return values[:count]
        bound *= 2


def primorials(count: int) -> list[int]:
    """Return P_r = product of the first r primes for r=0..count."""
    if count < 0:
        raise ValueError("count must be nonnegative")
    ps = first_primes(count)
    out = [1]
    acc = 1
    for p in ps:
        acc *= p
        out.append(acc)
    return out


def omega_sieve(limit: int) -> bytearray:
    """Exact number of distinct prime divisors for every 0 <= n <= limit."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    omega = bytearray(limit + 1)
    for p in range(2, limit + 1):
        if omega[p] == 0:  # prime: no smaller prime divisor ever incremented it
            for multiple in range(p, limit + 1, p):
                omega[multiple] += 1
    return omega


def distinct_prime_factor_count(n: int) -> int:
    if n < 1:
        raise ValueError("n must be positive")
    x = n
    count = 0
    p = 2
    while p * p <= x:
        if x % p == 0:
            count += 1
            while x % p == 0:
                x //= p
        p = 3 if p == 2 else p + 2
    if x > 1:
        count += 1
    return count


def build_receipt(limit: int = 1_000_000, max_r: int = 13) -> dict[str, object]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if max_r < 1:
        raise ValueError("max_r must be positive")

    ps = first_primes(max_r)
    prods = primorials(max_r)
    omega = omega_sieve(limit)
    stream = hashlib.sha256()
    minima: dict[int, int] = {}
    equality_cases: list[int] = []
    max_seen = 0

    for m in range(1, limit + 1):
        r = int(omega[m])
        if r > max_r:
            raise RuntimeError(f"max_r={max_r} too small for omega({m})={r}")
        lower = prods[r]
        if lower > m:
            raise RuntimeError(f"primorial lower bound failed at m={m}: P_{r}={lower}")
        if r not in minima:
            minima[r] = m
        if lower == m:
            equality_cases.append(m)
        if r > max_seen:
            max_seen = r
        stream.update(f"{m}:{r}:{lower}:{m-lower}\n".encode("ascii"))

    expected_minima = {r: prods[r] for r in range(max_seen + 1)}
    observed_minima = {r: minima[r] for r in range(max_seen + 1)}
    if observed_minima != expected_minima:
        raise RuntimeError(
            f"sharpness controls failed: observed={observed_minima}, expected={expected_minima}"
        )

    payload: dict[str, object] = {
        "schema": "erdos891-primorial-lower-bound-v1",
        "task_id": TASK_ID,
        "task_commitment": TASK_COMMITMENT,
        "source_type_sha256": SOURCE_TYPE_SHA256,
        "theorem": (
            "For m>0, if m has r distinct prime factors then the product of the first r primes "
            "is <= m. Hence k < omega(m) implies product(first k+1 primes) <= m."
        ),
        "limit": limit,
        "cases_checked": limit,
        "max_distinct_prime_factors_seen": max_seen,
        "first_primes": ps,
        "primorials_r_0_through_max_r": prods,
        "observed_minimum_m_by_exact_omega": {str(k): v for k, v in observed_minima.items()},
        "equality_cases_within_scan": equality_cases,
        "records_sha256": stream.hexdigest(),
        "evidence_ceiling": (
            "Exact finite regression only. The general primorial bound is justified by the paper proof in README.md; "
            "no Lean-kernel or sponsor-acceptance claim is made by this receipt."
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1_000_000)
    parser.add_argument("--max-r", type=int, default=13)
    parser.add_argument("--write-receipt", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    receipt = build_receipt(args.limit, args.max_r)
    text = json.dumps(receipt, sort_keys=True, indent=2 if args.pretty else None)
    if args.write_receipt is not None:
        args.write_receipt.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
