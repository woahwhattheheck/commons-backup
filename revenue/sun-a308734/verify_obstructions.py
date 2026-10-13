"""Exact finite support for OBSTRUCTIONS.md; not a proof of A308734.

Run from any directory: python verify_obstructions.py [certificate.json].
No third-party modules, network, assertions, or floating-point arithmetic.
"""
from __future__ import annotations

import argparse
import itertools
import json
from math import isqrt
from pathlib import Path
from typing import Any

FAMILIES = ((3, 3943, 15772, 96, 147), (5, 599, 2396, 39, 65))
WITNESSES = {3: [5, 11, 0, 0, 0, 3], 5: [19, 45, 0, 1, 0, 0]}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def natural(value: Any, name: str, maximum: int) -> int:
    require(type(value) is int and 0 <= value <= maximum, f"invalid {name}")
    return value


def powers(base: int, bound: int) -> list[int]:
    require(type(base) is int and base >= 2, "invalid power base")
    require(type(bound) is int and bound >= 0, "invalid power bound")
    result, value = [], 1
    while value <= bound:
        result.append(value)
        value *= base
    return result


def two_square_witness(n: int) -> tuple[int, int] | None:
    require(type(n) is int and n >= 0, "invalid two-square target")
    for x in range(isqrt(n) + 1):
        y = isqrt(n - x * x)
        if x * x + y * y == n:
            return x, y
    return None


def is_prime(n: int) -> bool:
    return type(n) is int and n >= 2 and all(n % d for d in range(2, isqrt(n) + 1))


def valuation(n: int, p: int) -> int:
    require(type(n) is int and n > 0 and is_prime(p), "invalid valuation")
    count = 0
    while n % p == 0:
        n //= p
        count += 1
    return count


def reduced_cases(p: int, core: int, seed: int) -> list[tuple[int, int, int]]:
    """All (target, first restricted square, second square) after parity."""
    result = []
    for q in powers(p * p, core):
        for first, second in ((1, q), (1, 4 * q), (4, q)):
            if first + second <= core:
                result.append((core, first, second))
    for q in powers(p * p, seed):
        if 1 + q <= seed:
            result.append((seed, 1, q))
    return result


def check_modular_lemmas() -> int:
    checked = 0
    for coords in itertools.product(range(8), repeat=4):
        total = sum(x * x for x in coords)
        if total % 8 == 0:
            require(all(x % 2 == 0 for x in coords), "mod-8 descent fails")
        if total % 4 == 0:
            require(len({x % 2 for x in coords}) == 1, "mod-4 parity fails")
        checked += 1
    for a, b, x, y in itertools.product(range(3), range(3), range(8), range(8)):
        if (x * x + y * y + 4**a + 4**b) % 8 == 7:
            require((a, b) in ((0, 0), (0, 1), (1, 0)), "core reduction fails")
    return checked


def exhaustive_pairs(p: int, n: int) -> int:
    """Independent full exponent enumeration, not the reduced-case proof."""
    count = 0
    for first in powers(4, n):
        for scale in powers(4, n):
            for odd_square in powers(p * p, n):
                if first + scale * odd_square <= n:
                    residual = n - first - scale * odd_square
                    require(two_square_witness(residual) is None, "specialized representation found")
                    count += 1
    return count


def verify(data: Any) -> dict[str, Any]:
    require(type(data) is dict and set(data) == {"schema", "families"}, "invalid root")
    require(data["schema"] == "sun-pure-prime-obstructions-v1", "invalid schema")
    families = data["families"]
    require(type(families) is list and len(families) == 2, "invalid families")
    summary = []
    total_rows = 0
    unique_residuals = set()
    for family, expected in zip(families, FAMILIES):
        p, core, seed, core_count, seed_count = expected
        require(type(family) is dict and set(family) == {"p", "core", "seed", "rows", "original_witness"}, "invalid family")
        require([natural(family[k], k, seed) for k in ("p", "core", "seed")] == [p, core, seed], "wrong family identity")
        require(core % 8 == 7 and seed == 4 * core, "invalid family relation")
        rows = family["rows"]
        cases = reduced_cases(p, core, seed)
        require(type(rows) is list and len(rows) == len(cases), "incomplete certificate coverage")
        for row, case in zip(rows, cases):
            require(type(row) is list and len(row) == 6, "invalid certificate row")
            n, first, second, residual, prime, exponent = [natural(v, "row value", seed) for v in row]
            require((n, first, second) == case, "wrong or reordered case")
            require(residual == n - first - second and residual > 0, "wrong residual")
            require(is_prime(prime) and prime % 4 == 3, "not a 3-mod-4 prime")
            require(exponent > 0 and exponent % 2 == 1 and valuation(residual, prime) == exponent, "not an odd exact valuation")
            unique_residuals.add((p, n, residual))
            total_rows += 1
        witness = family["original_witness"]
        require(type(witness) is list and len(witness) == 6, "invalid original witness")
        x, y, a, b, c, d = [natural(v, "witness", seed) for v in witness]
        require(witness == WITNESSES[p], "wrong original witness")
        require(x * x + y * y + 4**a * 9**b + 4**c * 25**d == seed, "original witness does not reconstruct")
        actual = [exhaustive_pairs(p, core), exhaustive_pairs(p, seed)]
        require(actual == [core_count, seed_count], "incomplete full enumeration")
        summary.append({"prime": p, "core": core, "seed": seed, "full_pair_counts": actual})
    return {"result": "VERIFIED_FINITE_SUPPORT", "families": summary,
            "certificate_rows": total_rows, "unique_obstructions": len(unique_residuals),
            "mod8_coordinate_tuples": check_modular_lemmas(),
            "infinite_step": "elementary descent proof in OBSTRUCTIONS.md",
            "a308734_proved": False, "prize_claimed": False}


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_certificate(path: Path) -> Any:
    raw = path.read_bytes()
    require(len(raw) <= 32768, "certificate too large")
    return json.loads(raw, object_pairs_hook=unique_object)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certificate", nargs="?", type=Path,
                        default=Path(__file__).with_name("obstruction_certificate.json"))
    args = parser.parse_args()
    try:
        result = verify(load_certificate(args.certificate))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"INVALID: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
