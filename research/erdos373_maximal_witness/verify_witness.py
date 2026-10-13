#!/usr/bin/env python3
"""Exact finite verifier for the concrete witness in Conjectures.io Erdős 373.

This checks only the first conjunct of the sponsor target:
    (16, [14, 5, 2]) ∈ Erdos373.S
It deliberately makes no claim about the open universal maximality conjunct.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, asdict
from functools import reduce
from operator import mul
from typing import Sequence

TASK_ID = "fc-8432eac9-variants-maximal-solution-2295ce32e4-formalized-v1"
TASK_COMMITMENT = "sha256:8cdafab211b9528d7196f9ab9cb6ad481f4004d1934579830920bbab392fc71a"
SOURCE_TYPE_SHA256 = "24d8815c2d3cdfaca28adabc9026afd5908201fdfe41c6ca3c51e408b42cde9f"
FORMAL_TARGET = "(16, [14, 5, 2]) ∈ Erdos373.S ∧ ∀ s ∈ Erdos373.S, s.1 ≤ 16"
SPONSOR_URL = "https://conjectures.io/problems/erdos373-erdos-373-variants-maximal-solution"


@dataclass(frozen=True)
class WitnessReceipt:
    n: int
    factors: tuple[int, ...]
    n_factorial: int
    factor_factorials: tuple[int, ...]
    rhs_product: int
    factorial_identity: bool
    pairwise_nonincreasing: bool
    head_below_n_minus_one: bool
    all_entries_gt_one: bool
    member_of_S: bool
    task_id: str
    task_commitment: str
    source_type_sha256: str
    formal_target_sha256: str
    evidence_scope: str


def pairwise_nonincreasing(xs: Sequence[int]) -> bool:
    return all(a >= b for a, b in zip(xs, xs[1:]))


def verify_member(n: int, factors: Sequence[int]) -> WitnessReceipt:
    factor_tuple = tuple(factors)
    facs = tuple(math.factorial(x) for x in factor_tuple)
    rhs = reduce(mul, facs, 1)
    nfac = math.factorial(n)
    factorial_identity = nfac == rhs
    descending = pairwise_nonincreasing(factor_tuple)
    head = factor_tuple[0] if factor_tuple else 0
    head_bound = head < max(n - 1, 0)
    gt_one = all(1 < x for x in factor_tuple)
    member = factorial_identity and descending and head_bound and gt_one
    return WitnessReceipt(
        n=n,
        factors=factor_tuple,
        n_factorial=nfac,
        factor_factorials=facs,
        rhs_product=rhs,
        factorial_identity=factorial_identity,
        pairwise_nonincreasing=descending,
        head_below_n_minus_one=head_bound,
        all_entries_gt_one=gt_one,
        member_of_S=member,
        task_id=TASK_ID,
        task_commitment=TASK_COMMITMENT,
        source_type_sha256=SOURCE_TYPE_SHA256,
        formal_target_sha256=hashlib.sha256(FORMAL_TARGET.encode("utf-8")).hexdigest(),
        evidence_scope="FIRST_CONJUNCT_ONLY_NO_UNIVERSAL_MAXIMALITY_CLAIM",
    )


def canonical_json(receipt: WitnessReceipt) -> str:
    return json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    receipt = verify_member(16, [14, 5, 2])
    print(json.dumps(asdict(receipt), indent=2, sort_keys=True, ensure_ascii=False))
    if not receipt.member_of_S:
        return 1
    print("receipt_sha256=" + hashlib.sha256(canonical_json(receipt).encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
