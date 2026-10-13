"""Exact arithmetic helpers for the k=5 window of Erdős problem 686.

For P(x)=(x+1)(x+2)(x+3)(x+4)(x+5), centering at t=x+3 gives

    P(x) = t(t^2-1)(t^2-4) = t^5 - 5t^3 + 4t.

Thus P(m)=4P(n) is equivalent to Q(m+3)=4Q(n+3).
All routines use Python integers only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def window5(x: int) -> int:
    if x < 0:
        raise ValueError("x must be nonnegative")
    return (x + 1) * (x + 2) * (x + 3) * (x + 4) * (x + 5)


def centered_quintic(t: int) -> int:
    return t**5 - 5 * t**3 + 4 * t


def centered_identity(x: int) -> bool:
    if x < 0:
        raise ValueError("x must be nonnegative")
    return window5(x) == centered_quintic(x + 3)


def eligible_len5_witness(n: int, m: int) -> bool:
    if n < 0 or m < 0:
        return False
    return m >= n + 5 and window5(m) == 4 * window5(n)


@dataclass(frozen=True)
class CandidateResult:
    n: int
    m: int | None
    comparisons: int


def find_len5_candidate(n: int) -> CandidateResult:
    """Return the unique eligible m if it exists, otherwise None.

    P(x)=window5(x) is strictly increasing on nonnegative integers.
    Any eligible witness has m>=n+5. Also
      P(2n+10) > 2^5 P(n) > 4P(n),
    since 2n+10+i > 2(n+i) for i=1,...,5.
    Hence [n+5, 2n+10] is an exhaustive finite bracket.
    """
    if n < 0:
        raise ValueError("n must be nonnegative")
    target = 4 * window5(n)
    lo, hi = n + 5, 2 * n + 10
    comparisons = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        value = window5(mid)
        comparisons += 1
        if value == target:
            return CandidateResult(n, mid, comparisons)
        if value < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return CandidateResult(n, None, comparisons)


def scan_len5(limit: int) -> dict[str, int | str | None]:
    """Exhaustively check n=0..limit and hash the exact candidate stream."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    h = hashlib.sha256()
    comparisons = 0
    witnesses = 0
    first_witness: tuple[int, int] | None = None
    for n in range(limit + 1):
        result = find_len5_candidate(n)
        comparisons += result.comparisons
        m_text = "-" if result.m is None else str(result.m)
        h.update(f"{n}:{m_text}:{result.comparisons}\n".encode())
        if result.m is not None:
            witnesses += 1
            if first_witness is None:
                first_witness = (n, result.m)
    return {
        "n_min": 0,
        "n_max": limit,
        "n_count": limit + 1,
        "comparisons": comparisons,
        "witnesses": witnesses,
        "first_witness": None if first_witness is None else f"{first_witness[0]},{first_witness[1]}",
        "stream_sha256": h.hexdigest(),
    }


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Exact k=5 scan for Erdős 686/four")
    parser.add_argument("--limit", type=int, default=1_000_000)
    args = parser.parse_args()
    print(json.dumps(scan_len5(args.limit), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
