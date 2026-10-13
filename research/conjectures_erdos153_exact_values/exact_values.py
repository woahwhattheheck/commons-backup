#!/usr/bin/env python3
"""Exact finite certificates for the next small values of Erdős 153's f(n).

This module deliberately mirrors the finite-search interface already published for
Erdős 153 without claiming to re-prove that Lean interface.  It checks the finite
premises needed by that interface using exact integer/rational arithmetic only.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
from functools import lru_cache
import argparse
import json
from math import comb
from pathlib import Path
from typing import Sequence

TASKS_COMMIT = "d9a67b509c5a8b220ba262c1c7ce26f61f52763a"
FORMAL_REPOSITORY_COMMIT = "8432eac998110a563e03df65a28c117e97c8c142"
CONTRIBUTION_COMMIT = "f22e02d120e9b9e12a41848f74087934a922790e"
EXISTING_CONTRIBUTION_ID = "d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b"
TARGET_TYPE_HASH = "sha256:b35a9b51e1956e50dac187c15f5e0fd861c1ae3dcaaceb7941a1ce9bfd770316"
TARGET = "fc-target:Erdos153.erdos_153"


@dataclass(frozen=True)
class Case:
    n: int
    cutoff: int
    expected_num: int
    expected_den: int
    witness: tuple[int, ...]

    @property
    def expected(self) -> Fraction:
        return Fraction(self.expected_num, self.expected_den)


CASES = (
    Case(5, 12, 14, 5, (0, 1, 4, 9, 11)),
    Case(6, 19, 74, 21, (0, 1, 4, 10, 15, 17)),
    Case(7, 29, 9, 2, (0, 1, 4, 10, 18, 23, 25)),
)


def unordered_pair_sums(values: Sequence[int]) -> tuple[int, ...]:
    """Return all a_i+a_j for i<=j, preserving multiplicity before sorting."""
    return tuple(sorted(values[i] + values[j]
                        for i in range(len(values))
                        for j in range(i, len(values))))


def is_sidon(values: Sequence[int]) -> bool:
    """Formal-Conjectures IsSidon condition specialized to a finite Nat set.

    Commutativity is quotiented by using unordered index pairs i<=j; the set is
    Sidon iff all resulting sums are distinct.
    """
    sums = unordered_pair_sums(values)
    return len(sums) == len(set(sums))


def sumset(values: Sequence[int]) -> tuple[int, ...]:
    """Sorted A+A with duplicates removed."""
    return tuple(sorted({a + b for a in values for b in values}))


def gap_energy(values: Sequence[int]) -> Fraction:
    """(1/t) * sum_i (s[i+1]-s[i])^2, exactly over Q."""
    ss = sumset(values)
    if not ss:
        raise ValueError("empty set has no useful Erdős-153 gap energy")
    numerator = sum((b - a) ** 2 for a, b in zip(ss, ss[1:]))
    return Fraction(numerator, len(ss))


def cutoff_holds(case: Case) -> bool:
    """Finite-search cutoff premise from the published f_eq_of_search interface."""
    t = comb(case.n + 1, 2)
    return Fraction(t * (t - 1)) * case.expected <= 4 * (case.cutoff + 1) ** 2


def cutoff_is_minimal(case: Case) -> bool:
    if case.cutoff == 0:
        return cutoff_holds(case)
    t = comb(case.n + 1, 2)
    lhs = Fraction(t * (t - 1)) * case.expected
    return 4 * case.cutoff**2 < lhs <= 4 * (case.cutoff + 1) ** 2


def _record(values: tuple[int, ...], e: Fraction) -> str:
    return json.dumps(
        {"set": values, "energy": [e.numerator, e.denominator]},
        sort_keys=True,
        separators=(",", ":"),
    )


@lru_cache(maxsize=None)
def scan(case: Case) -> dict:
    """Exhaustively check every n-subset of [0,D], not only normalized sets."""
    count = 0
    sidon_count = 0
    minimum: Fraction | None = None
    minimizers: list[tuple[int, ...]] = []
    digest = sha256()

    for values in combinations(range(case.cutoff + 1), case.n):
        count += 1
        if not is_sidon(values):
            continue
        sidon_count += 1
        e = gap_energy(values)
        digest.update((_record(values, e) + "\n").encode())
        if minimum is None or e < minimum:
            minimum = e
            minimizers = [values]
        elif e == minimum:
            minimizers.append(values)

    witness_energy = gap_energy(case.witness)
    witness_sidon = is_sidon(case.witness)
    lower_bound_ok = minimum is None or minimum >= case.expected
    witness_ok = witness_sidon and witness_energy == case.expected
    exact = cutoff_holds(case) and lower_bound_ok and witness_ok

    return {
        "n": case.n,
        "cutoff_D": case.cutoff,
        "subsets_checked": count,
        "expected_subsets": comb(case.cutoff + 1, case.n),
        "sidon_subsets": sidon_count,
        "minimum_in_window": None if minimum is None else [minimum.numerator, minimum.denominator],
        "minimizers_in_window": [list(x) for x in minimizers],
        "witness": list(case.witness),
        "witness_energy": [witness_energy.numerator, witness_energy.denominator],
        "cutoff_holds": cutoff_holds(case),
        "cutoff_is_minimal_integer_D": cutoff_is_minimal(case),
        "finite_lower_bound_holds": lower_bound_ok,
        "witness_realizes_value": witness_ok,
        "finite_premises_establish_exact_value_via_published_f_eq_of_search": exact,
        "sidon_record_sha256": digest.hexdigest(),
    }


@lru_cache(maxsize=1)
def make_receipt() -> dict:
    results = [scan(case) for case in CASES]
    payload = {
        "schema_version": 1,
        "target": TARGET,
        "target_type_hash": TARGET_TYPE_HASH,
        "tasks_main_commit": TASKS_COMMIT,
        "formal_repository_commit_pinned_by_task": FORMAL_REPOSITORY_COMMIT,
        "contribution_main_commit": CONTRIBUTION_COMMIT,
        "existing_interface_contribution_id": EXISTING_CONTRIBUTION_ID,
        "method": "exhaustive exact scan of every n-subset of Finset.range(D+1); integer Sidon check; Fraction gap energy",
        "evidence_ceiling": (
            "Finite-premise certificate against the already-published f_eq_of_search interface. "
            "It is not itself a Lean proof, not a proof of Tendsto f atTop atTop, and not a sponsor submission."
        ),
        "results": results,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["receipt_sha256"] = sha256(canonical).hexdigest()
    return payload


def validate_receipt(receipt: dict) -> None:
    expected = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    actual = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected != actual:
        raise AssertionError(f"receipt digest mismatch: {expected} != {actual}")
    for result in receipt["results"]:
        if not result["finite_premises_establish_exact_value_via_published_f_eq_of_search"]:
            raise AssertionError(f"case n={result['n']} did not close its finite premises")
        if result["subsets_checked"] != result["expected_subsets"]:
            raise AssertionError(f"case n={result['n']} incomplete enumeration")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-receipt", type=Path)
    args = parser.parse_args()
    receipt = make_receipt()
    validate_receipt(receipt)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.write_receipt:
        args.write_receipt.write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
