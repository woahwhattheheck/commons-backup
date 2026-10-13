from __future__ import annotations
import hashlib, json


def sigma(n: int) -> int:
    if n < 1:
        raise ValueError('n must be positive')
    x = n
    total = 1
    p = 2
    while p * p <= x:
        if x % p == 0:
            term = 1
            power = 1
            while x % p == 0:
                x //= p
                power *= p
                term += power
            total *= term
        p += 1 if p == 2 else 2
    if x > 1:
        total *= 1 + x
    return total


def iterate_sigma(n: int, k: int) -> int:
    if k < 0:
        raise ValueError('k must be nonnegative')
    for _ in range(k):
        n = sigma(n)
    return n


def sigma_sieve(limit: int) -> list[int]:
    out = [0] * (limit + 1)
    for d in range(1, limit + 1):
        for m in range(d, limit + 1, d):
            out[m] += d
    return out


def build_receipt(limit: int = 10000, orbit_seed_limit: int = 256, orbit_steps: int = 8) -> dict:
    sums = sigma_sieve(limit)
    strict_failures = [n for n in range(2, limit + 1) if not n < sums[n]]
    records: list[dict] = []
    orbit_failures: list[dict] = []
    for n in range(2, orbit_seed_limit + 1):
        cur = n
        for k in range(orbit_steps):
            nxt = sigma(cur)
            rec = {'seed': n, 'step': k, 'value': cur, 'next': nxt}
            records.append(rec)
            if not cur < nxt:
                orbit_failures.append(rec)
            cur = nxt
    stream = ''.join(json.dumps(r, sort_keys=True, separators=(',', ':')) + '\n' for r in records).encode()
    return {
        'statement': 'For every integer n >= 2, n < sigma(n); sampled iterates are therefore strictly increasing.',
        'proof_basis': '1 and n are distinct positive divisors of n when n>=2, so sigma(n) >= 1+n > n.',
        'strict_growth_limit': limit,
        'strict_growth_cases': max(0, limit - 1),
        'strict_growth_failures': strict_failures,
        'orbit_seed_limit': orbit_seed_limit,
        'orbit_steps': orbit_steps,
        'orbit_transition_cases': len(records),
        'orbit_failures': orbit_failures,
        'orbit_stream_sha256': hashlib.sha256(stream).hexdigest(),
    }


if __name__ == '__main__':
    print(json.dumps(build_receipt(), indent=2, sort_keys=True))
