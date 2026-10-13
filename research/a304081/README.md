# OEIS A304081 exact search

This directory contains a dependency-free finite verifier/search tool for
[OEIS A304081](https://oeis.org/A304081).

The sequence counts representations

`n = p + 2^k + (1 + (n mod 2)) * 5^m`

where `p` is an odd prime and the non-prime offset is squarefree. OEIS states
the conjecture `a(n) > 0` for every `n > 7`, reports verification through
`2*10^10`, and records a $2,500 prize for the first proof and $250 for the
first explicit counterexample.

## Shared parity catalog API

[The shared offset catalog](offset_catalog.cjs) prepares exact squarefree base
offsets once for consumers working with both parities. It preserves every
exponent pair, including pairs with equal numeric offsets, and returns the
corresponding odd prime candidates without evaluating their primality. Its
inclusive `max_n` is bounded at `10^12`.

See [PARITY_CATALOG.md](PARITY_CATALOG.md) for the attributed parity reduction,
API, integer and multiplicity conventions, and actual source-example use.
[The complete base catalog](base_offset_catalog_20261004.json) retains the
366 computed exponent-pair rows through the documented bound for later
consumers. Candidate counts from this API are not the sequence values `a(n)`.

## Exact point counter API

[The representation counter](representation_counter.cjs) consumes the shared
catalog and evaluates every distinct prime candidate by exact trial division,
while preserving every successful exponent pair. Its reusable preparation is
bounded by the same inclusive `10^12` maximum.

See [REPRESENTATION_COUNTER.md](REPRESENTATION_COUNTER.md) for usage, integer
and result contracts, and the two actual point counts `a(20050000001)=27` and
`a(20050000002)=30`. [Complete point data](point_counts_20261004.json) retains
every candidate pair and classification. These individual counts do not
represent a replay or a new scan of the historical search interval.

## Build

```bash
g++ -O3 -std=c++20 -Wall -Wextra -pedantic a304081_search.cpp -o a304081_search
./a304081_search self-test
```

## Modes

```bash
./a304081_search count N
./a304081_search scan LO HI
./a304081_search verify-range LO HI
./a304081_search random TRIALS LO HI SEED [SKIP]
./a304081_search sample TRIALS LO HI SEED [SKIP]
```

- `count` enumerates every admissible `(k,m)` representation for one `n`.
- `scan` exhaustively counts every representation for every integer in an inclusive interval.
- `verify-range` exhaustively checks every integer in an inclusive interval but short-circuits after its first representation; it is intended for exact frontier extension.
- `random` uses deterministic SplitMix64 samples (with replacement) and stops
  at the first exact zero; it short-circuits after the first representation.
- `sample` computes full representation counts for deterministic samples and
  reports a count histogram.
- `SKIP` advances to a disjoint deterministic suffix of the same SplitMix64
  stream without replaying the prefix.

Primality is deterministic Miller-Rabin for unsigned 64-bit integers. The
squarefree offset table is exact: it sieves primes through the square root of
the maximum search value and rejects any offset divisible by a prime square.

The current implementation intentionally caps the squarefree sieve root at
20,000,000 to keep accidental searches from consuming unbounded memory. That
supports maximum `n` values up to roughly `4e14`.

## Correctness note: k = 0

The OEIS definition allows nonnegative `k`, but `k=0` cannot yield an odd
prime `p`:

- if `n` is even, `1 + 5^m` is even, so `p = n - offset` is even;
- if `n` is odd, `1 + 2*5^m` is odd, so `p` is again even.

Since the required prime is odd, the implementation starts at `k=1`.
The self-test checks OEIS examples including `a(6)=1`, `a(91)=1`, and
`a(6447154629)=2`.

## Research boundary

Finite searches are evidence only. A null search does not prove the conjecture.
A candidate counterexample is valid only if `count N` exhaustively returns
zero and an independent implementation/reviewer confirms the arithmetic.
