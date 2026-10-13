from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import gcd
from typing import Iterable
import json

TASK_ID = "fc-8432eac9-erdos672-erdos-672-713e8186eb-formalized-v1"
TASK_COMMITMENT = "sha256:9319c919b34ffc4e079f87512387799fde189e458faa517513b0d7ae0d13bc04"
SOURCE_TYPE_SHA256 = "sha256:c445617cb40577954b07647947103591146b81f79e29b214a02745fc58e09a1a"
SOURCE_METADATA_BLOB = "8b03cd5015157cac05c13544d02faeec9a0db0bd"
CHALLENGE_BLOB = "907bce40689b31892ef9504125cfefb0f28cd925"


def _is_prime(n: int) -> bool:
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


def smallest_prime_divisor(n: int) -> int:
    """Return the least prime divisor of n. Requires n > 1."""
    if n <= 1:
        raise ValueError("n must be > 1")
    if n % 2 == 0:
        return 2
    d = 3
    while d * d <= n:
        if n % d == 0:
            return d
        d += 2
    return n


@dataclass(frozen=True)
class PrimeExponentReduction:
    original_exponent: int
    prime_exponent: int
    cofactor: int
    original_base: int
    reduced_base: int

    def verify(self) -> bool:
        l = self.original_exponent
        p = self.prime_exponent
        m = self.cofactor
        q = self.original_base
        return (
            l > 1
            and p > 1
            and _is_prime(p)
            and m > 0
            and l == p * m
            and self.reduced_base == q**m
            and q**l == self.reduced_base**p
        )


def reduce_power_exponent(q: int, l: int) -> PrimeExponentReduction:
    """Reduce q^l, l>1, to a power with prime exponent p | l exactly."""
    if q < 0:
        raise ValueError("q must be a natural number")
    if l <= 1:
        raise ValueError("l must be > 1")
    p = smallest_prime_divisor(l)
    m = l // p
    cert = PrimeExponentReduction(l, p, m, q, q**m)
    if not cert.verify():
        raise AssertionError("internal prime-exponent reduction failure")
    return cert


def factor_exponents(n: int) -> dict[int, int]:
    if n <= 0:
        raise ValueError("n must be positive")
    out: dict[int, int] = {}
    while n % 2 == 0:
        out[2] = out.get(2, 0) + 1
        n //= 2
    d = 3
    while d * d <= n:
        while n % d == 0:
            out[d] = out.get(d, 0) + 1
            n //= d
        d += 2
    if n > 1:
        out[n] = out.get(n, 0) + 1
    return out


@dataclass(frozen=True)
class PerfectPowerCertificate:
    value: int
    prime_exponent: int
    root: int

    def verify(self) -> bool:
        return (
            self.value > 0
            and _is_prime(self.prime_exponent)
            and self.root >= 0
            and self.root ** self.prime_exponent == self.value
        )


def perfect_power_certificate(n: int) -> PerfectPowerCertificate | None:
    """Return a prime-exponent certificate iff positive n is a nontrivial perfect power.

    For n>1, write n=prod p_i^e_i. Then n is a perfect power iff
    gcd(e_i)>1. Choosing any prime divisor of that gcd yields a prime
    exponent certificate. n=1 is 1^2.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if n == 1:
        return PerfectPowerCertificate(1, 2, 1)
    exps = factor_exponents(n)
    g = 0
    for e in exps.values():
        g = gcd(g, e)
    if g <= 1:
        return None
    p = smallest_prime_divisor(g)
    root = 1
    for prime, e in exps.items():
        root *= prime ** (e // p)
    cert = PerfectPowerCertificate(n, p, root)
    if not cert.verify():
        raise AssertionError("internal perfect-power certificate failure")
    return cert


def ap_terms(k: int, n: int, d: int) -> tuple[int, ...]:
    if k < 1 or n < 1 or d < 1:
        raise ValueError("k,n,d must be positive")
    return tuple(n + j * d for j in range(k))


def ap_product(k: int, n: int, d: int) -> int:
    out = 1
    for x in ap_terms(k, n, d):
        out *= x
    return out


def exponent_gcd_of_product(values: Iterable[int]) -> int:
    total: dict[int, int] = {}
    for value in values:
        for p, e in factor_exponents(value).items():
            total[p] = total.get(p, 0) + e
    g = 0
    for e in total.values():
        g = gcd(g, e)
    return g


def scan_exponent_reductions(max_l: int = 10_000) -> dict[str, object]:
    if max_l < 2:
        raise ValueError("max_l must be >= 2")
    h = sha256()
    rows = 0
    for l in range(2, max_l + 1):
        p = smallest_prime_divisor(l)
        m = l // p
        if not (_is_prime(p) and l == p * m and m > 0):
            raise AssertionError((l, p, m))
        h.update(f"{l},{p},{m}\n".encode())
        rows += 1
    return {"max_l": max_l, "rows": rows, "sha256": h.hexdigest()}


def scan_ap_window(
    *, max_n: int = 256, max_d: int = 256, k_min: int = 4, k_max: int = 8
) -> dict[str, object]:
    if min(max_n, max_d, k_min) < 1 or k_max < k_min:
        raise ValueError("invalid bounds")
    h = sha256()
    candidates = 0
    perfect_powers: list[dict[str, int]] = []
    for k in range(k_min, k_max + 1):
        for n in range(1, max_n + 1):
            for d in range(1, max_d + 1):
                if gcd(n, d) != 1:
                    continue
                candidates += 1
                terms = ap_terms(k, n, d)
                g = exponent_gcd_of_product(terms)
                h.update(f"{k},{n},{d},{g}\n".encode())
                if g > 1:
                    value = 1
                    for x in terms:
                        value *= x
                    cert = perfect_power_certificate(value)
                    if cert is None:
                        raise AssertionError("gcd>1 without certificate")
                    perfect_powers.append({
                        "k": k,
                        "n": n,
                        "d": d,
                        "prime_exponent": cert.prime_exponent,
                        "root": cert.root,
                    })
    return {
        "max_n": max_n,
        "max_d": max_d,
        "k_min": k_min,
        "k_max": k_max,
        "coprime_ap_candidates": candidates,
        "perfect_power_hits": perfect_powers,
        "perfect_power_hit_count": len(perfect_powers),
        "stream_sha256": h.hexdigest(),
    }


def build_receipt() -> dict[str, object]:
    return {
        "schema": "erdos672-prime-exponent-reduction-receipt-v1",
        "claim": "bounded computational evidence plus an elementary general prime-exponent reduction",
        "evidence_ceiling": (
            "The prime-divisor exponent reduction is a general arithmetic implication. "
            "The AP search is finite only and is not a proof of Erdos 672. "
            "No Lean elaboration or sponsor acceptance is claimed."
        ),
        "task": {
            "task_id": TASK_ID,
            "task_commitment": TASK_COMMITMENT,
            "source_type_sha256": SOURCE_TYPE_SHA256,
            "source_metadata_blob": SOURCE_METADATA_BLOB,
            "challenge_blob": CHALLENGE_BLOB,
        },
        "exponent_reduction_regression": scan_exponent_reductions(),
        "ap_search": scan_ap_window(),
    }


def canonical_receipt_json(receipt: dict[str, object]) -> str:
    return json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def main() -> None:
    receipt = build_receipt()
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("receipt_sha256=" + sha256(canonical_receipt_json(receipt).encode()).hexdigest())


if __name__ == "__main__":
    main()
