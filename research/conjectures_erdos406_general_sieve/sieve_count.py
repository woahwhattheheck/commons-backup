#!/usr/bin/env python3
"""Exact finite checks for the all-m survivor count behind Erdős 406 (digits 1,2).

For m >= 1 let T_m = 2*3^(m-1). The published contribution
55f755c7... proves the sieve engine and checks, only for m <= 5, that exactly
2^m exponent classes r modulo T_m have no zero among the first m base-3
positions of 2^r mod 3^m.

This module independently checks the exact finite objects used by the general
mathematical proof:

* 2 has full order T_m modulo 3^m (checked by a permutation of units);
* the sieve survivors map bijectively onto the residues whose m base-3 digits
  are all in {1,2};
* therefore the survivor count is exactly 2^m.

The executable checks are finite evidence, not a substitute for the all-m proof.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import argparse
import hashlib
import json
from typing import Iterable, Iterator


def period(m: int) -> int:
    if m < 1:
        raise ValueError("m must be >= 1")
    return 2 * 3 ** (m - 1)


def modulus(m: int) -> int:
    if m < 1:
        raise ValueError("m must be >= 1")
    return 3**m


def ternary_digits_fixed(n: int, m: int) -> tuple[int, ...]:
    """Return the first exactly m base-3 digits, least significant first."""
    if m < 0:
        raise ValueError("m must be >= 0")
    if n < 0:
        raise ValueError("n must be >= 0")
    out: list[int] = []
    for _ in range(m):
        out.append(n % 3)
        n //= 3
    return tuple(out)


def is_digit_residue(n: int, m: int) -> bool:
    """Whether 0 <= n < 3^m and every one of its m ternary digits is 1 or 2."""
    if not (0 <= n < modulus(m)):
        return False
    return all(d in (1, 2) for d in ternary_digits_fixed(n, m))


def is_survivor(r: int, m: int) -> bool:
    """Published sieve predicate for exponent residue r at depth m."""
    q = modulus(m)
    a = pow(2, r, q)
    return all(((a // (3**i)) % 3) != 0 for i in range(m))


def exponent_residues(m: int) -> Iterator[tuple[int, int]]:
    """Yield (r, 2^r mod 3^m) for the full exponent period, exactly once each r."""
    q = modulus(m)
    a = 1
    for r in range(period(m)):
        yield r, a
        a = (2 * a) % q


def expected_digit_residues(m: int) -> set[int]:
    """All m-place base-3 words over {1,2}, represented as integers."""
    values = {0}
    place = 1
    for _ in range(m):
        values = {v + d * place for v in values for d in (1, 2)}
        place *= 3
    return values


def v3(n: int) -> int:
    if n <= 0:
        raise ValueError("v3 expects a positive integer")
    e = 0
    while n % 3 == 0:
        e += 1
        n //= 3
    return e


def primitive_root_lift_residue(m: int) -> int:
    """2^(2*3^(m-1)) modulo 3^(m+1), for the lifting congruence."""
    if m < 1:
        raise ValueError("m must be >= 1")
    return pow(2, period(m), 3 ** (m + 1))


@dataclass(frozen=True)
class Row:
    m: int
    modulus: int
    period: int
    survivor_count: int
    expected_count: int
    unit_image_count: int
    expected_unit_count: int
    lift_residue_mod_next_power: int
    lift_expected: int
    survivor_digest: str
    image_digest: str


def _digest_ints(values: Iterable[int]) -> str:
    h = hashlib.sha256()
    for value in values:
        h.update(f"{value}\n".encode())
    return h.hexdigest()


def check_depth(m: int) -> Row:
    q = modulus(m)
    t = period(m)
    pairs = list(exponent_residues(m))
    image = [a for _, a in pairs]
    image_set = set(image)

    # Full-order check: powers of 2 traverse every unit residue exactly once.
    expected_units = {a for a in range(q) if a % 3 != 0}
    if len(image) != t or len(image_set) != t or image_set != expected_units:
        raise AssertionError(f"2 does not enumerate units at m={m}")

    survivors = [r for r, a in pairs if all(d != 0 for d in ternary_digits_fixed(a, m))]
    survivor_images = {pow(2, r, q) for r in survivors}
    digit_residues = expected_digit_residues(m)
    if survivor_images != digit_residues:
        raise AssertionError(f"survivor image mismatch at m={m}")
    if len(survivors) != 2**m:
        raise AssertionError(f"survivor count mismatch at m={m}")

    # Strong lifting congruence supporting the proof that ord_{3^m}(2)=T_m:
    # 2^T_m == 1 + 3^m (mod 3^(m+1)).
    lift = primitive_root_lift_residue(m)
    lift_expected = 1 + q
    if lift != lift_expected:
        raise AssertionError(f"primitive-root lift congruence mismatch at m={m}")
    # Equivalent LTE sanity check.
    if v3(2**t - 1) != m:
        raise AssertionError(f"v3 identity mismatch at m={m}")

    return Row(
        m=m,
        modulus=q,
        period=t,
        survivor_count=len(survivors),
        expected_count=2**m,
        unit_image_count=len(image_set),
        expected_unit_count=2 * 3 ** (m - 1),
        lift_residue_mod_next_power=lift,
        lift_expected=lift_expected,
        survivor_digest=_digest_ints(survivors),
        image_digest=_digest_ints(sorted(survivor_images)),
    )


def build_receipt(max_m: int) -> dict:
    if max_m < 1:
        raise ValueError("max_m must be >= 1")
    rows = [asdict(check_depth(m)) for m in range(1, max_m + 1)]
    payload = {
        "schema": "erdos406-general-sieve-count-v1",
        "claim": "finite regression for the all-m theorem; not a proof of the open conjecture",
        "theorem_checked_finitely": (
            "for each checked m>=1, powers 2^r for 0<=r<2*3^(m-1) enumerate all units mod 3^m, "
            "and the sieve survivor image is exactly the 2^m residues with m ternary digits in {1,2}"
        ),
        "max_m": max_m,
        "rows": rows,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {"payload": payload, "payload_sha256": hashlib.sha256(canonical).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-m", type=int, default=12)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    receipt = build_receipt(args.max_m)
    print(json.dumps(receipt, sort_keys=True, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
