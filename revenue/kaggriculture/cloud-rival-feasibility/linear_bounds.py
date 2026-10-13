# SPDX-License-Identifier: MIT
"""Bounded exact real-linear feasibility with independently checkable rejection.

Real feasibility is a relaxation of integer inventory feasibility.  A possible
result is NOT an inventory estimate.  Budget exhaustion returns unknown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from time import monotonic
from typing import Mapping


def rational(value: int | str | Fraction) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, str, Fraction)):
        raise TypeError("Use integer, rational string, or Fraction; not float")
    return Fraction(value)


@dataclass(frozen=True)
class Constraint:
    coefficients: Mapping[str, Fraction]
    bound: Fraction
    name: str

    @classmethod
    def make(cls, coefficients, bound, name):
        if not isinstance(name, str) or not name:
            raise ValueError("Constraint name must be nonempty")
        clean = {str(k): rational(v) for k, v in coefficients.items() if rational(v)}
        return cls(clean, rational(bound), name)


@dataclass(frozen=True)
class Limits:
    max_rows: int = 2048
    max_combinations: int = 8192
    max_bits: int = 2048
    seconds: float = 0.025


@dataclass(frozen=True)
class Result:
    status: str  # possible | infeasible | unknown
    reason: str
    certificate: Mapping[str, Fraction] = field(default_factory=dict)
    combinations: int = 0

    def as_dict(self):
        return {"status": self.status, "reason": self.reason,
                "certificate": {k: str(v) for k, v in self.certificate.items()},
                "combinations": self.combinations}


@dataclass
class _Row:
    a: dict[str, Fraction]
    b: Fraction
    proof: dict[str, Fraction]


def verify_certificate(constraints, certificate) -> bool:
    """Verify a nonnegative sum of original rows yields 0 <= a negative value."""
    source = {c.name: c for c in constraints}
    if len(source) != len(constraints) or not certificate:
        return False
    coefficients: dict[str, Fraction] = {}
    bound = Fraction(0)
    try:
        for name, raw_weight in certificate.items():
            weight = rational(raw_weight)
            if weight < 0 or name not in source:
                return False
            row = source[name]
            bound += weight * row.bound
            for variable, coefficient in row.coefficients.items():
                coefficients[variable] = coefficients.get(variable, Fraction(0)) + weight * coefficient
    except (ValueError, TypeError, ZeroDivisionError):
        return False
    return all(v == 0 for v in coefficients.values()) and bound < 0


def solve(constraints: list[Constraint], limits: Limits = Limits()) -> Result:
    """Fourier-Motzkin elimination. Only a verified contradiction rejects.

    One-sided variables may be eliminated because all variable domains are
    explicit constraints. Constraint deduplication uses only positive scaling.
    """
    if len({c.name for c in constraints}) != len(constraints):
        raise ValueError("Constraint names must be unique")
    if (limits.max_rows < 1 or limits.max_combinations < 0 or
            limits.max_bits < 1 or limits.seconds <= 0):
        return Result("unknown", "budget")
    deadline = monotonic() + limits.seconds
    combinations = 0

    def exhausted(rows):
        if len(rows) > limits.max_rows or monotonic() >= deadline:
            return True
        for row in rows:
            for value in (*row.a.values(), row.b, *row.proof.values()):
                if max(value.numerator.bit_length(), value.denominator.bit_length()) > limits.max_bits:
                    return True
        return False

    def reduce(rows):
        unique = {}
        for row in rows:
            row.a = {k: v for k, v in row.a.items() if v}
            if not row.a:
                if row.b < 0:
                    if verify_certificate(constraints, row.proof):
                        return [], Result("infeasible", "certified_contradiction", row.proof, combinations)
                    return [], Result("unknown", "certificate_verification_failed", combinations=combinations)
                continue
            scale = abs(row.a[min(row.a)])
            a = {k: v / scale for k, v in row.a.items()}
            b = row.b / scale
            key = tuple(sorted(a.items()))
            prior = unique.get(key)
            if prior is None or b < prior.b:
                unique[key] = _Row(a, b, {k: v / scale for k, v in row.proof.items() if v})
        return list(unique.values()), None

    rows = [_Row(dict(c.coefficients), c.bound, {c.name: Fraction(1)}) for c in constraints]
    if exhausted(rows):
        return Result("unknown", "budget", combinations=combinations)
    rows, terminal = reduce(rows)
    while not terminal:
        if exhausted(rows):
            return Result("unknown", "budget", combinations=combinations)
        variables = set().union(*(r.a for r in rows)) if rows else set()
        if not variables:
            return Result("possible", "real_relaxation", combinations=combinations)
        counts = {v: (sum(r.a.get(v, 0) > 0 for r in rows),
                      sum(r.a.get(v, 0) < 0 for r in rows)) for v in variables}
        variable = min(variables, key=lambda v: (counts[v][0] * counts[v][1], v))
        positive = [r for r in rows if r.a.get(variable, 0) > 0]
        negative = [r for r in rows if r.a.get(variable, 0) < 0]
        output = [r for r in rows if not r.a.get(variable, 0)]
        extra = len(positive) * len(negative)
        if combinations + extra > limits.max_combinations or len(output) + extra > limits.max_rows:
            return Result("unknown", "budget", combinations=combinations)
        for p in positive:
            for n in negative:
                if monotonic() >= deadline:
                    return Result("unknown", "budget", combinations=combinations)
                wp, wn = -n.a[variable], p.a[variable]
                keys = p.a.keys() | n.a.keys()
                a = {k: wp * p.a.get(k, 0) + wn * n.a.get(k, 0) for k in keys if k != variable}
                proof = {k: wp * p.proof.get(k, 0) + wn * n.proof.get(k, 0)
                         for k in p.proof.keys() | n.proof.keys()}
                output.append(_Row(a, wp * p.b + wn * n.b, proof))
                combinations += 1
        rows, terminal = reduce(output)
    return terminal
