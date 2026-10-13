#!/usr/bin/env python3
"""Exact finite proof-support tools for Sun's A308734 conjecture.

This module deliberately proves only finite local statements.  It does not
claim to prove A308734.  The key local obstruction comes from Fermat's
sum-of-two-squares theorem: a prime p == 3 (mod 4) may not occur to an odd
valuation in a global sum of two squares.  Modulo p^2 we can detect the
first odd case exactly, v_p(m) == 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from itertools import product
from math import gcd, isqrt, prod
from pathlib import Path
from typing import Iterable, Sequence

SCHEMA_VERSION = 1
DEFAULT_PRIMES = (3, 7, 11, 19, 23)
KNOWN_FAILED_EXTENSION_PRIME = 31


@dataclass(frozen=True)
class Candidate:
    a: int
    b: int
    c: int
    d: int
    shift: int

    @classmethod
    def from_exponents(cls, a: int, b: int, c: int, d: int) -> "Candidate":
        for name, value in (("a", a), ("b", b), ("c", c), ("d", d)):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        shift = (4**a) * (9**b) + (4**c) * (25**d)
        return cls(a=a, b=b, c=c, d=d, shift=shift)


@dataclass(frozen=True)
class SunWitness:
    x: int
    y: int
    a: int
    b: int
    c: int
    d: int


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    f = 3
    while f * f <= n:
        if n % f == 0:
            return False
        f += 2
    return True


def validate_obstruction_primes(primes: Sequence[int]) -> tuple[int, ...]:
    result = tuple(primes)
    if not result:
        raise ValueError("at least one obstruction prime is required")
    if len(set(result)) != len(result):
        raise ValueError("obstruction primes must be distinct")
    for p in result:
        if not isinstance(p, int) or not _is_prime(p) or p % 4 != 3:
            raise ValueError(f"{p!r} is not a prime congruent to 3 mod 4")
    return result


def small_exponent_candidates() -> tuple[Candidate, ...]:
    """All distinct shifts with a,b,c,d in {0,1}, canonicalized by shift.

    There are 16 exponent tuples but one duplicate shift, so this yields 15
    candidates.  The first tuple in lexicographic product order owns a
    duplicate shift.
    """

    by_shift: dict[int, Candidate] = {}
    for a, b, c, d in product((0, 1), repeat=4):
        candidate = Candidate.from_exponents(a, b, c, d)
        by_shift.setdefault(candidate.shift, candidate)
    return tuple(by_shift.values())


def is_exact_v1_mod_p2(n_residue: int, shift: int, p: int) -> bool:
    """Whether n-shift has p-adic valuation exactly 1, known from mod p^2."""

    pp = p * p
    r = (n_residue - shift) % pp
    return r % p == 0 and r != 0


def bad_mask(p: int, n_residue: int, candidates: Sequence[Candidate]) -> int:
    mask = 0
    for i, candidate in enumerate(candidates):
        if is_exact_v1_mod_p2(n_residue, candidate.shift, p):
            mask |= 1 << i
    return mask


def maximal_bad_masks(
    p: int, candidates: Sequence[Candidate]
) -> tuple[tuple[int, int], ...]:
    """Return inclusion-maximal bad masks with a deterministic residue witness.

    A mask bit i is set when candidate i leaves a residual whose p-adic
    valuation is exactly 1.  For adversarial coverage, a mask contained in
    another mask is never stronger and can be discarded without changing the
    existence of a global CRT adversary.
    """

    first_witness: dict[int, int] = {}
    for residue in range(p * p):
        first_witness.setdefault(bad_mask(p, residue, candidates), residue)

    ordered = sorted(first_witness, key=lambda m: (-m.bit_count(), m))
    maximal: list[tuple[int, int]] = []
    for mask in ordered:
        if any((mask | existing) == existing for existing, _ in maximal):
            continue
        maximal.append((mask, first_witness[mask]))
    return tuple(maximal)


def crt_pairwise(residues: Sequence[int], moduli: Sequence[int]) -> tuple[int, int]:
    if len(residues) != len(moduli) or not residues:
        raise ValueError("residues and moduli must have equal nonzero length")
    for i, m in enumerate(moduli):
        if m <= 0:
            raise ValueError("moduli must be positive")
        for other in moduli[:i]:
            if gcd(m, other) != 1:
                raise ValueError("moduli must be pairwise coprime")
    modulus = prod(moduli)
    value = 0
    for residue, m in zip(residues, moduli):
        Mi = modulus // m
        value = (value + (residue % m) * Mi * pow(Mi, -1, m)) % modulus
    return value, modulus


def find_adversarial_assignment(
    primes: Sequence[int], candidates: Sequence[Candidate]
) -> dict[str, object] | None:
    """Find a CRT assignment making every candidate locally bad somewhere.

    For each selected p, an adversary chooses n mod p^2.  Candidate i is
    killed if at least one chosen residue gives v_p(n-shift_i) == 1.  Because
    the p^2 moduli are pairwise coprime, CRT realizes every tuple of local
    choices by an integer n.  Therefore absence of a full-mask assignment is
    an exact finite local-cover certificate.
    """

    primes = validate_obstruction_primes(primes)
    if not candidates:
        raise ValueError("at least one candidate is required")
    full_mask = (1 << len(candidates)) - 1
    options = [maximal_bad_masks(p, candidates) for p in primes]

    def visit(index: int, union_mask: int, residues: list[int]) -> list[int] | None:
        if union_mask == full_mask:
            # Remaining primes can take residue zero; the current prefix is
            # already enough to kill every candidate.
            return residues + [0] * (len(primes) - index)
        if index == len(primes):
            return None
        for local_mask, residue in options[index]:
            found = visit(index + 1, union_mask | local_mask, residues + [residue])
            if found is not None:
                return found
        return None

    residues = visit(0, 0, [])
    if residues is None:
        return None
    value, modulus = crt_pairwise(residues, [p * p for p in primes])
    killed_by: list[list[int]] = []
    for candidate in candidates:
        bad_primes = [
            p
            for p in primes
            if is_exact_v1_mod_p2(value % (p * p), candidate.shift, p)
        ]
        if not bad_primes:
            raise AssertionError("constructed adversary failed to kill a candidate")
        killed_by.append(bad_primes)
    return {
        "residues": dict(zip((str(p) for p in primes), residues)),
        "crt_residue": value,
        "crt_modulus": modulus,
        "killed_by": killed_by,
    }


def first_obstruction_primes(count: int) -> tuple[int, ...]:
    """Return the first ``count`` primes congruent to 3 modulo 4."""

    if not isinstance(count, int) or count < 0:
        raise ValueError("count must be a nonnegative integer")
    result: list[int] = []
    n = 3
    while len(result) < count:
        if n % 4 == 3 and _is_prime(n):
            result.append(n)
        n += 4
    return tuple(result)


def fixed_shift_crt_killer(shifts: Sequence[int]) -> dict[str, object]:
    """Construct infinitely many n that defeat any *fixed finite* shift list.

    For distinct shifts s_i choose distinct primes p_i == 3 (mod 4) and impose
    n == s_i + p_i (mod p_i^2).  Then v_{p_i}(n-s_i) == 1, so n-s_i
    cannot be a sum of two squares.  CRT gives one residue class modulo the
    product of p_i^2; every sufficiently large integer in that progression
    defeats the whole fixed list.

    This is a structural barrier for proof strategies, not a counterexample to
    A308734: the conjecture's available smooth-square shifts grow with n.
    """

    shifts = tuple(int(s) for s in shifts)
    if not shifts:
        raise ValueError("at least one shift is required")
    if any(s < 0 for s in shifts):
        raise ValueError("shifts must be nonnegative")
    if len(set(shifts)) != len(shifts):
        raise ValueError("shifts must be distinct")
    primes = first_obstruction_primes(len(shifts))
    moduli = [p * p for p in primes]
    residues = [(s + p) % (p * p) for s, p in zip(shifts, primes)]
    value, modulus = crt_pairwise(residues, moduli)
    if value <= max(shifts):
        value += ((max(shifts) - value) // modulus + 1) * modulus
    assignments = []
    for shift, prime, residue in zip(shifts, primes, residues):
        difference = value - shift
        if difference <= 0 or difference % prime != 0 or difference % (prime * prime) == 0:
            raise AssertionError("CRT killer construction invariant failed")
        assignments.append(
            {
                "shift": shift,
                "prime": prime,
                "n_mod_p2": residue,
                "difference_mod_p2": difference % (prime * prime),
            }
        )
    return {
        "crt_residue": value % modulus,
        "crt_modulus": modulus,
        "positive_representative": value,
        "assignments": assignments,
        "statement": (
            "Every n congruent to crt_residue modulo crt_modulus, once larger "
            "than all shifts, leaves a two-square obstruction for every shift."
        ),
    }


def _canonical_json(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest_payload(payload: dict[str, object]) -> str:
    unsigned = dict(payload)
    unsigned.pop("sha256", None)
    return hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def build_certificate(
    primes: Sequence[int] = DEFAULT_PRIMES,
    candidates: Sequence[Candidate] | None = None,
) -> dict[str, object]:
    primes = validate_obstruction_primes(primes)
    candidates = tuple(candidates or small_exponent_candidates())
    local = []
    for p in primes:
        masks = maximal_bad_masks(p, candidates)
        local.append(
            {
                "prime": p,
                "modulus": p * p,
                "maximal_bad_masks": [
                    {
                        "mask_hex": hex(mask),
                        "popcount": mask.bit_count(),
                        "residue_witness": residue,
                    }
                    for mask, residue in masks
                ],
            }
        )
    adversary = find_adversarial_assignment(primes, candidates)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "statement": (
            "For every integer n, at least one listed shift s makes n-s avoid "
            "p-adic valuation exactly 1 for every listed obstruction prime p."
        ),
        "evidence_ceiling": (
            "Finite p^2-local coverage only; this does not prove that n-s is a "
            "global sum of two squares and does not prove OEIS A308734."
        ),
        "primes": list(primes),
        "candidates": [asdict(candidate) for candidate in candidates],
        "local": local,
        "status": "LOCAL_COVER_CERTIFIED" if adversary is None else "LOCAL_COVER_FAIL",
        "adversary": adversary,
    }
    payload["sha256"] = _digest_payload(payload)
    return payload


def verify_certificate(payload: dict[str, object]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema version")
    supplied_digest = payload.get("sha256")
    if not isinstance(supplied_digest, str) or supplied_digest != _digest_payload(payload):
        raise ValueError("certificate digest mismatch")

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("certificate has no candidates")
    candidates: list[Candidate] = []
    seen_shifts: set[int] = set()
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            raise ValueError("invalid candidate record")
        candidate = Candidate.from_exponents(
            int(raw["a"]), int(raw["b"]), int(raw["c"]), int(raw["d"])
        )
        if int(raw["shift"]) != candidate.shift:
            raise ValueError("candidate shift does not match exponents")
        if candidate.shift in seen_shifts:
            raise ValueError("candidate shifts must be unique")
        seen_shifts.add(candidate.shift)
        candidates.append(candidate)

    primes_raw = payload.get("primes")
    if not isinstance(primes_raw, list):
        raise ValueError("invalid prime list")
    primes = validate_obstruction_primes(tuple(int(p) for p in primes_raw))

    expected_local = []
    for p in primes:
        expected_local.append(
            {
                "prime": p,
                "modulus": p * p,
                "maximal_bad_masks": [
                    {
                        "mask_hex": hex(mask),
                        "popcount": mask.bit_count(),
                        "residue_witness": residue,
                    }
                    for mask, residue in maximal_bad_masks(p, candidates)
                ],
            }
        )
    if payload.get("local") != expected_local:
        raise ValueError("local mask table mismatch")

    adversary = find_adversarial_assignment(primes, candidates)
    expected_status = "LOCAL_COVER_CERTIFIED" if adversary is None else "LOCAL_COVER_FAIL"
    if payload.get("status") != expected_status or payload.get("adversary") != adversary:
        raise ValueError("certificate status/adversary mismatch")


def write_certificate(path: Path, primes: Sequence[int] = DEFAULT_PRIMES) -> dict[str, object]:
    payload = build_certificate(primes)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def four_adic_core(n: int) -> tuple[int, int]:
    if not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive integer")
    q = 0
    while n % 4 == 0:
        n //= 4
        q += 1
    return n, q


def check_sun_witness(n: int, witness: SunWitness) -> bool:
    fields = asdict(witness)
    if any(not isinstance(v, int) or v < 0 for v in fields.values()):
        return False
    return n == (
        witness.x * witness.x
        + witness.y * witness.y
        + (2**witness.a * 3**witness.b) ** 2
        + (2**witness.c * 5**witness.d) ** 2
    )


def lift_witness_by_four(witness: SunWitness, q: int) -> SunWitness:
    if not isinstance(q, int) or q < 0:
        raise ValueError("q must be a nonnegative integer")
    scale = 2**q
    return SunWitness(
        x=witness.x * scale,
        y=witness.y * scale,
        a=witness.a + q,
        b=witness.b,
        c=witness.c + q,
        d=witness.d,
    )


def two_square_witness(m: int) -> tuple[int, int] | None:
    if m < 0:
        return None
    for x in range(isqrt(m) + 1):
        y2 = m - x * x
        y = isqrt(y2)
        if y * y == y2:
            return x, y
    return None


def small_family_witness(n: int) -> tuple[Candidate, tuple[int, int]] | None:
    for candidate in small_exponent_candidates():
        remainder = n - candidate.shift
        pair = two_square_witness(remainder)
        if pair is not None:
            return candidate, pair
    return None


def first_small_family_failure(limit: int, primitive_only: bool = True) -> int | None:
    if limit < 2:
        return None
    for n in range(2, limit + 1):
        if primitive_only and n % 4 == 0:
            continue
        if small_family_witness(n) is None:
            return n
    return None


def _restricted_values(limit: int, odd_base: int) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    a = 0
    while 4**a <= limit:
        b = 0
        while (4**a) * (odd_base * odd_base) ** b <= limit:
            out.append(((4**a) * (odd_base * odd_base) ** b, a, b))
            b += 1
        a += 1
    return out


def brute_sun_witness(n: int) -> SunWitness | None:
    if n < 2:
        return None
    left = _restricted_values(n, 3)
    right = _restricted_values(n, 5)
    for left_value, a, b in left:
        for right_value, c, d in right:
            pair = two_square_witness(n - left_value - right_value)
            if pair is not None:
                return SunWitness(pair[0], pair[1], a, b, c, d)
    return None


def _cmd_emit(args: argparse.Namespace) -> int:
    payload = write_certificate(Path(args.path))
    print(json.dumps({"status": payload["status"], "sha256": payload["sha256"]}, sort_keys=True))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
    verify_certificate(payload)
    print(json.dumps({"status": "VERIFIED", "sha256": payload["sha256"]}, sort_keys=True))
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    primes = DEFAULT_PRIMES + (args.prime,)
    candidates = small_exponent_candidates()
    adversary = find_adversarial_assignment(primes, candidates)
    print(json.dumps({"primes": primes, "adversary": adversary}, indent=2, sort_keys=True))
    return 1 if adversary is not None else 0


def _cmd_scout(args: argparse.Namespace) -> int:
    failure = first_small_family_failure(args.limit, primitive_only=True)
    report: dict[str, object] = {"limit": args.limit, "first_primitive_small_family_failure": failure}
    if failure is not None:
        witness = brute_sun_witness(failure)
        report["full_conjecture_witness"] = asdict(witness) if witness else None
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    emit = sub.add_parser("emit", help="emit the default local-cover certificate")
    emit.add_argument("path")
    emit.set_defaults(func=_cmd_emit)
    verify = sub.add_parser("verify", help="independently recompute and verify a certificate")
    verify.add_argument("path")
    verify.set_defaults(func=_cmd_verify)
    probe = sub.add_parser("probe-extension", help="try extending the default prime band")
    probe.add_argument("prime", type=int)
    probe.set_defaults(func=_cmd_probe)
    scout = sub.add_parser("scout", help="find a counterexample to the small-exponent global hypothesis")
    scout.add_argument("--limit", type=int, default=1000)
    scout.set_defaults(func=_cmd_scout)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
