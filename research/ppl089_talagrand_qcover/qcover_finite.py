#!/usr/bin/env python3
"""Exact finite verifier for Talagrand's simple-combinatorics q-cover problem.

Families on 2^[N] are encoded as Python integers: bit x is one iff the subset
encoded by the N-bit mask x belongs to the family. All arithmetic used in the
certification path is exact fractions.Fraction arithmetic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from functools import lru_cache
from typing import Iterable

HALF = Fraction(1, 2)


class CertificateError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise CertificateError(message)


def frac_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def family_members(family: int, n: int) -> tuple[int, ...]:
    require(isinstance(n, int) and 0 <= n <= 8, "unsupported n")
    require(isinstance(family, int) and family >= 0, "bad family bitset")
    limit = 1 << (1 << n)
    require(family < limit, "family bitset out of range")
    return tuple(x for x in range(1 << n) if (family >> x) & 1)


@lru_cache(maxsize=None)
def downsets(n: int) -> tuple[int, ...]:
    """Enumerate every down-class on an n-element ground set exactly once."""
    require(isinstance(n, int) and 0 <= n <= 5, "downset census supports n <= 5")
    if n == 0:
        return (0, 1)
    prev = downsets(n - 1)
    half = 1 << (n - 1)
    out: list[int] = []
    for d0 in prev:
        for d1 in prev:
            if d1 & ~d0 == 0:
                out.append(d0 | (d1 << half))
    return tuple(sorted(out))


def is_downset(family: int, n: int) -> bool:
    for x in family_members(family, n):
        sub = x
        while True:
            if not ((family >> sub) & 1):
                return False
            if sub == 0:
                break
            sub = (sub - 1) & x
    return True


def down_closure(family: int, n: int) -> int:
    out = 0
    for x in family_members(family, n):
        sub = x
        while True:
            out |= 1 << sub
            if sub == 0:
                break
            sub = (sub - 1) & x
    return out


def product_measure(family: int, n: int, p: Fraction) -> Fraction:
    require(Fraction(0) <= p <= Fraction(1), "p outside [0,1]")
    q = 1 - p
    total = Fraction(0)
    for x in family_members(family, n):
        k = x.bit_count()
        total += p**k * q ** (n - k)
    return total


def q_coverable(family: int, n: int, q: int) -> int:
    """Return subsets coverable by q repetition-allowed members of family."""
    require(isinstance(q, int) and q >= 1, "q must be positive")
    elems = family_members(family, n)
    if not elems:
        return 0
    unions = {0}
    for _ in range(q):
        unions = {u | d for u in unions for d in elems}
    covered = 0
    for union in unions:
        sub = union
        while True:
            covered |= 1 << sub
            if sub == 0:
                break
            sub = (sub - 1) & union
    return covered


def d_q(family: int, n: int, q: int) -> int:
    """Talagrand D^(q): subsets not coverable by q members of D."""
    all_family = (1 << (1 << n)) - 1
    return all_family ^ q_coverable(family, n, q)


def minimal_elements(up_family: int, n: int) -> tuple[int, ...]:
    """Minimal elements of an up-class; fail if supplied family is not upward."""
    mins: list[int] = []
    for x in family_members(up_family, n):
        immediate = [x & ~(1 << i) for i in range(n) if x & (1 << i)]
        if all(not ((up_family >> y) & 1) for y in immediate):
            mins.append(x)
    rebuilt = 0
    for x in range(1 << n):
        if any(m & ~x == 0 for m in mins):
            rebuilt |= 1 << x
    require(rebuilt == up_family, "family is not an up-class")
    return tuple(mins)


def minimum_p_small_cover(
    up_family: int, n: int, p: Fraction
) -> tuple[Fraction, tuple[int, ...]]:
    """Exact minimum sum p^|I| over principal-upset covers of an up-class."""
    require(Fraction(0) <= p <= HALF, "certifier is scoped to p in [0,1/2]")
    if up_family == 0:
        return Fraction(0), ()
    mins = minimal_elements(up_family, n)
    m = len(mins)
    full = (1 << m) - 1
    candidates: list[tuple[int, int, Fraction]] = []
    for generator in range(1 << n):
        mask = 0
        for j, x in enumerate(mins):
            if generator & ~x == 0:
                mask |= 1 << j
        if mask:
            candidates.append((generator, mask, p ** generator.bit_count()))

    costs: list[Fraction | None] = [None] * (1 << m)
    previous: list[tuple[int, int] | None] = [None] * (1 << m)
    costs[0] = Fraction(0)
    for mask in range(1 << m):
        base = costs[mask]
        if base is None:
            continue
        for generator, covered, price in candidates:
            new_mask = mask | covered
            new_cost = base + price
            if costs[new_mask] is None or new_cost < costs[new_mask]:
                costs[new_mask] = new_cost
                previous[new_mask] = (mask, generator)

    require(costs[full] is not None, "no principal-upset cover found")
    generators: list[int] = []
    cursor = full
    while cursor:
        step = previous[cursor]
        require(step is not None, "broken cover traceback")
        cursor, generator = step
        generators.append(generator)
    return costs[full], tuple(generators)


def q2_sanity_witness() -> dict[str, object]:
    """Known/implicit sanity witness showing universal q=2 cannot work."""
    n = 2
    p = Fraction(7, 25)
    family = 1
    target = d_q(family, n, 2)
    cost, generators = minimum_p_small_cover(target, n, p)
    measure = product_measure(family, n, p)
    require(measure >= HALF, "q=2 witness misses measure threshold")
    require(cost > HALF, "q=2 witness unexpectedly p-small")
    require(target == 0b1110, "q=2 witness D^(2) should be all nonempty subsets")
    return {
        "n": n,
        "q": 2,
        "p": frac_text(p),
        "D_bitset_hex": f"0x{family:x}",
        "measure_D": frac_text(measure),
        "threshold": "1/2",
        "Dq_bitset_hex": f"0x{target:x}",
        "minimum_p_small_cost": frac_text(cost),
        "optimal_generators": [f"0b{x:0{n}b}" for x in generators],
        "consequence": "q=2 is not a universal witness for the p-small formulation",
        "novelty": (
            "sanity lemma implicit in Talagrand's A={empty} discussion; "
            "no novelty claimed"
        ),
    }


def certify_downset_q3(
    family: int, n: int, max_bisections: int = 80
) -> dict[str, object]:
    """Certify q=3 for one down-class for every p in (0,1/2]."""
    require(is_downset(family, n), "family is not a down-class")
    threshold = Fraction(2, 3)
    if family == 0:
        return {
            "status": "ineligible",
            "reason": "empty family never reaches measure 2/3",
        }

    target = d_q(family, n, 3)
    if target == 0:
        return {
            "status": "certified",
            "reason": "Dq_empty",
            "p_hi": "1/2",
            "cost_hi": "0/1",
        }

    cost_half, _ = minimum_p_small_cover(target, n, HALF)
    if cost_half <= HALF:
        return {
            "status": "certified",
            "reason": "cost_at_half",
            "p_hi": "1/2",
            "cost_hi": frac_text(cost_half),
        }

    mu_half = product_measure(family, n, HALF)
    if mu_half >= threshold:
        return {
            "status": "counterexample",
            "reason": "qualifies_at_half_but_cost_exceeds_half",
            "p": "1/2",
            "measure": frac_text(mu_half),
            "cost": frac_text(cost_half),
        }

    lo, hi = Fraction(0), HALF
    require(
        product_measure(family, n, lo) >= threshold,
        "nonempty down-class must qualify at p=0",
    )
    for step in range(1, max_bisections + 1):
        mid = (lo + hi) / 2
        if product_measure(family, n, mid) >= threshold:
            lo = mid
        else:
            hi = mid

        cost_hi, _ = minimum_p_small_cover(target, n, hi)
        if cost_hi <= HALF:
            return {
                "status": "certified",
                "reason": "upper_bracket",
                "bisections": step,
                "p_lo": frac_text(lo),
                "p_hi": frac_text(hi),
                "mu_lo": frac_text(product_measure(family, n, lo)),
                "mu_hi": frac_text(product_measure(family, n, hi)),
                "cost_hi": frac_text(cost_hi),
            }

        cost_lo, _ = minimum_p_small_cover(target, n, lo)
        if lo > 0 and cost_lo > HALF:
            return {
                "status": "counterexample",
                "reason": "eligible_lower_bracket_cost_exceeds_half",
                "bisections": step,
                "p": frac_text(lo),
                "measure": frac_text(product_measure(family, n, lo)),
                "cost": frac_text(cost_lo),
            }

    return {
        "status": "unresolved",
        "reason": "bisection_limit",
        "p_lo": frac_text(lo),
        "p_hi": frac_text(hi),
    }


def census(n: int = 5) -> dict[str, object]:
    """Exact q=3 continuum census over every down-class on <= n coordinates."""
    require(1 <= n <= 5, "census supports 1 <= n <= 5")
    rows: list[str] = []
    counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    by_n: dict[str, dict[str, int]] = {}
    counterexamples: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []

    for dim in range(1, n + 1):
        dim_counts: dict[str, int] = {}
        for family in downsets(dim):
            result = certify_downset_q3(family, dim)
            status = str(result["status"])
            reason = str(result["reason"])
            counts[status] = counts.get(status, 0) + 1
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            dim_counts[status] = dim_counts.get(status, 0) + 1
            p_hi = str(result.get("p_hi", "-"))
            cost_hi = str(result.get("cost_hi", result.get("cost", "-")))
            rows.append(
                f"{dim}\t{family:x}\t{status}\t{reason}\t{p_hi}\t{cost_hi}\n"
            )
            if status == "counterexample":
                counterexamples.append(
                    {"n": dim, "family_hex": f"0x{family:x}", **result}
                )
            elif status == "unresolved":
                unresolved.append(
                    {"n": dim, "family_hex": f"0x{family:x}", **result}
                )
        by_n[str(dim)] = dim_counts

    payload = "".join(rows).encode("ascii")
    return {
        "schema": "talagrand-qcover-finite-v1",
        "scope": {
            "q": 3,
            "max_n": n,
            "p_interval": "(0,1/2]",
            "measure_threshold": "2/3",
            "arithmetic": "exact Fraction / dyadic rational brackets",
            "reduction": (
                "arbitrary D -> down-closure; D^(q) unchanged and product "
                "measure does not decrease"
            ),
        },
        "counts": counts,
        "reason_counts": reason_counts,
        "by_n": by_n,
        "downsets_at_max_n": len(downsets(n)),
        "census_rows": len(rows),
        "census_sha256": hashlib.sha256(payload).hexdigest(),
        "counterexamples": counterexamples,
        "unresolved": unresolved,
        "q2_sanity_witness": q2_sanity_witness(),
        "claim": (
            f"For every family D on N <= {n} and every p in (0,1/2], "
            "if mu_p(D) >= 2/3 then D^(3) is p-small."
        ),
        "evidence_ceiling": (
            "finite theorem for N<=5 only; not a solution of the "
            "dimension-free prize problem"
        ),
    }


def receipt() -> dict[str, object]:
    out = census(5)
    out["sources"] = {
        "sponsor_problem": "https://michel.talagrand.net/prizes/combinatorics.pdf",
        "sponsor_general_rules": "https://michel.talagrand.net/prizes/prizes.pdf",
        "primary_discussion": "https://michel.talagrand.net/preprints/small.pdf",
        "prize_ledger": "https://prizeproblems.org/problems/089/",
    }
    out["reward"] = {
        "listed_usd": 1000,
        "status": (
            "verified open by Prize Problem Ledger 2026-07-27; "
            "no submission or award claimed here"
        ),
    }
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("q2-witness")
    verify = sub.add_parser("verify")
    verify.add_argument("--max-n", type=int, default=5)
    sub.add_parser("receipt")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "q2-witness":
        print(json.dumps(q2_sanity_witness(), indent=2, sort_keys=True))
        return 0
    if args.command == "verify":
        print(json.dumps(census(args.max_n), indent=2, sort_keys=True))
        return 0
    if args.command == "receipt":
        print(json.dumps(receipt(), indent=2, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
