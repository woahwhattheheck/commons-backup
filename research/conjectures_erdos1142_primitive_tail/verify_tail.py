#!/usr/bin/env python3
"""Exact finite certificates for the Erdős 1142 primitive-root tail sieve.

This module does not claim to solve Erdős 1142.  It verifies the finite
premises needed to extend the already-published covering-congruence sieve
from p = 3,5,11,13,19 to the only two further primitive-root primes whose
direct thresholds can affect the Mientka-Weitzenkamp range n <= 2^44:
p = 29 and p = 37.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

MW_BOUND = 1 << 44
TASK_ID = "fc-8432eac9-erdos1142-erdos-1142-a29719d6af-formalized-v1"
TASK_COMMITMENT = "60a1381809a9c064c907712012dcc037343ee3d39486f392c00e34a42dda7b4d"
SOURCE_TYPE_SHA256 = "140c4194bf440ed9095b2b1a1f8cb6b534b1f4738ee1c9d78a89ec890ed38632"

# The prior published piece already owns these five instances.
PUBLISHED_PRIMITIVE_ROOT_PRIMES = (3, 5, 11, 13, 19)
# This carrier adds exactly these two direct instances.
NEW_PRIMITIVE_ROOT_PRIMES = (29, 37)
EXPECTED_PRIMITIVE_ROOT_PRIMES = PUBLISHED_PRIMITIVE_ROOT_PRIMES + NEW_PRIMITIVE_ROOT_PRIMES


def primes_upto(n: int) -> list[int]:
    out: list[int] = []
    for x in range(2, n + 1):
        if all(x % d for d in range(2, int(x**0.5) + 1)):
            out.append(x)
    return out


def order_two_mod_prime(p: int) -> int:
    if p <= 2:
        raise ValueError("order_two_mod_prime expects an odd prime")
    x = 1
    for k in range(1, p):
        x = (x * 2) % p
        if x == 1:
            return k
    raise AssertionError("Fermat order bound failed")


def covering_witnesses(p: int) -> dict[int, int]:
    """Return the least exponent 1<=k<=p-1 hitting each nonzero residue."""
    witnesses: dict[int, int] = {}
    x = 1
    for k in range(1, p):
        x = (x * 2) % p
        witnesses.setdefault(x, k)
    return {r: witnesses[r] for r in sorted(witnesses) if r != 0}


def is_primitive_root_prime_for_two(p: int) -> bool:
    return p > 2 and order_two_mod_prime(p) == p - 1


def relevant_primitive_root_primes() -> list[int]:
    """All p for which the direct threshold can affect n<=2^44."""
    # If p >= 47 then 2^(p-1)+p > 2^44, so such an instance is irrelevant
    # to the Mientka-Weitzenkamp range.
    return [p for p in primes_upto(45) if p > 2 and is_primitive_root_prime_for_two(p)]


def threshold(p: int) -> int:
    return (1 << (p - 1)) + p


def coverage_sha256(p: int) -> str:
    payload = ";".join(f"{r}:{k}" for r, k in covering_witnesses(p).items()).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Interval:
    lower_exclusive: int
    upper_inclusive: int
    required_divisor: int

    @property
    def candidate_count(self) -> int:
        return self.upper_inclusive // self.required_divisor - self.lower_exclusive // self.required_divisor

    @property
    def first_candidate(self) -> int:
        q = self.lower_exclusive // self.required_divisor + 1
        return q * self.required_divisor

    @property
    def last_candidate(self) -> int:
        return (self.upper_inclusive // self.required_divisor) * self.required_divisor


def tail_intervals() -> list[Interval]:
    """Piecewise residual ranges after the published p<=19 sieve."""
    return [
        # continuity with the published sharp residual:
        Interval(4109, 262163, 2145),
        # published p=19 applies:
        Interval(262163, threshold(29), 40755),
        # new p=29 applies:
        Interval(threshold(29), threshold(37), 1181895),
        # new p=37 applies through 2^44:
        Interval(threshold(37), MW_BOUND, 43730115),
    ]


def build_payload() -> dict:
    primes = primes_upto(45)
    rows = []
    cumulative = 1
    for p in EXPECTED_PRIMITIVE_ROOT_PRIMES:
        cumulative *= p
        rows.append(
            {
                "p": p,
                "order_two_mod_p": order_two_mod_prime(p),
                "threshold": threshold(p),
                "cumulative_product": cumulative,
                "coverage_sha256": coverage_sha256(p),
                "new_in_this_carrier": p in NEW_PRIMITIVE_ROOT_PRIMES,
            }
        )

    nonprimitive = []
    for p in primes:
        if p == 2:
            nonprimitive.append({"p": p, "reason": "powers_of_two_are_zero_mod_2_for_k_ge_1"})
        elif p not in EXPECTED_PRIMITIVE_ROOT_PRIMES:
            w = covering_witnesses(p)
            missing = [r for r in range(1, p) if r not in w]
            nonprimitive.append(
                {
                    "p": p,
                    "order_two_mod_p": order_two_mod_prime(p),
                    "missing_nonzero_residue_count": len(missing),
                    "first_missing_residue": missing[0],
                }
            )

    intervals = [
        {
            "lower_exclusive": i.lower_exclusive,
            "upper_inclusive": i.upper_inclusive,
            "required_divisor": i.required_divisor,
            "candidate_count": i.candidate_count,
            "first_candidate": i.first_candidate,
            "last_candidate": i.last_candidate,
        }
        for i in tail_intervals()
    ]
    existing_sharp_count = 121 + MW_BOUND // 40755 - 262163 // 40755
    refined_count = sum(i["candidate_count"] for i in intervals)

    return {
        "schema": "erdos1142-primitive-root-tail-v1",
        "task_id": TASK_ID,
        "task_commitment_sha256": TASK_COMMITMENT,
        "source_type_sha256": SOURCE_TYPE_SHA256,
        "mw_bound": MW_BOUND,
        "prime_scan_max": 45,
        "all_primes_scanned": primes,
        "primitive_root_primes": list(EXPECTED_PRIMITIVE_ROOT_PRIMES),
        "published_primitive_root_primes": list(PUBLISHED_PRIMITIVE_ROOT_PRIMES),
        "new_primitive_root_primes": list(NEW_PRIMITIVE_ROOT_PRIMES),
        "primitive_root_rows": rows,
        "nonprimitive_rows": nonprimitive,
        "tail_intervals": intervals,
        "existing_sharp_residual_candidate_count": existing_sharp_count,
        "refined_residual_candidate_count": refined_count,
        "candidate_reduction_numerator": existing_sharp_count,
        "candidate_reduction_denominator": refined_count,
        "evidence_ceiling": (
            "Finite exact certificate for primitive-root classification, covering witnesses, "
            "threshold arithmetic, and residual counts only; not a proof of infinitude, "
            "not a proof of the Mientka-Weitzenkamp classification through 2^44, and not "
            "a sponsor-accepted Lean contribution."
        ),
    }


def canonical_json_bytes(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def build_receipt() -> dict:
    payload = build_payload()
    return {
        "payload": payload,
        "payload_sha256": hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    }


def main() -> int:
    print(json.dumps(build_receipt(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
