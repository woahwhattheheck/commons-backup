# Exact nonprimitive residue refinement for Erdős 1142

The accepted primitive-root tail leaves 465,335 arithmetic candidates in
`(4109, 2^44]`. Applying parity and the six nonprimitive primes already recorded
in this carrier reduces that set to **10,618 candidates**, with a proper-divisor
witness for each of the **454,717 exclusions**. The complete surviving integers
are in [residual_candidates.json](residual_candidates.json), ready for a later
refinement without rerunning this one.

The later [residual completion](RESIDUAL_COMPLETION.md) provides explicit
factorizations excluding all 10,618 of these saved candidates. The result and
dataset on this page remain the inputs to that continuation; neither earlier
sieve was rerun.

[residue_refinement.cjs](residue_refinement.cjs) supplies a reusable exact API for
this operation. It works directly in the connected JavaScript runtime, as well
as through CommonJS. Surviving its selected filters does not establish primality
or the Erdős property.

## Mathematical scope and attribution

Let `E(n)` mean that `n > 2` and every `n - 2^k` with `k >= 1` and
`2^k < n` is prime, the property described by
[OEIS A039669](https://oeis.org/A039669).

The covering-congruence mechanism predates this carrier. Imran Ghory's and Chris
Nash's original discussion on [Prime Puzzles, Problem 3](https://www.primepuzzles.net/problems/prob_003.htm)
develops the primitive-root divisibility argument; Nash also explicitly explains
how the three powers modulo 7 can reject candidates even though 2 is not a
primitive root there. That mechanism is credited here, not claimed as new.

The published contribution `8b087102…` supplies the general covering theorem and
the p = 3, 5, 11, 13, 19 instances. [Commons #16080](https://github.com/woahwhattheheck/commons/pull/16080)
supplies the p = 29, 37 continuation, the four input intervals, and the
nonprimitive orders used below. This continuation consumes those accepted
results. Its deliverables are the downstream implementation, exact refined
candidate set, and the derivation connecting them.

## Proper-divisor criterion

For any integer `m >= 2`, not necessarily prime, suppose

```text
k >= 1,
n ≡ 2^k (mod m),
n - 2^k > m.
```

Then `n - 2^k = m*q` for an integer `q >= 2`. The difference is composite,
and `2^k < n` automatically holds. Thus this is a valid exclusion from `E(n)`.

The strict inequality matters. Merely finding `n - 2^k = p` for a prime
`p` is not an exclusion. Nor may an exponent with `2^k >= n` disqualify a
candidate. The implementation checks the actual difference against the
configured divisor, rather than using a blanket threshold.

### The earliest exponent is enough

Fix a modulus and a residue reached by the configured exponents
`1, …, K`. Let `k0` be the least exponent reaching it. If a later matching
exponent `k` gives a proper-divisor witness, then

```text
n - 2^k0 >= n - 2^k > m.
```

So the earliest matching exponent also gives a witness. Conversely, its witness
is one of the configured possibilities. Retaining only that exponent for each
residue is therefore exact for this finite family of divisor checks; it neither
loses a configured proper-divisor exclusion nor invents one.

### Full cyclic subgroup and thresholds

For an odd prime `p`, put `d = ord_p(2)` and
`H_p = {2^1, …, 2^d} mod p`. Its size is `d`. If `n > 2^d + p`,
every residue in `H_p` has an eligible proper-divisor witness. Consequently

```text
E(n) and n > 2^d + p  =>  n mod p is outside H_p.
```

This leaves `p-d` allowed residue classes, including zero. It forces
`p | n` only in the primitive-root case `d=p-1`.

The following orders are the accepted values in
[receipt.json](receipt.json), blob
`3fc08f7d88ffcfa123708da8155675c7f85cc827`:

| p | d | Full-subgroup threshold `2^d+p` | Allowed residues once above it |
|---:|---:|---:|---:|
| 7 | 3 | 15 | 4 |
| 17 | 8 | 273 | 9 |
| 23 | 11 | 2,071 | 12 |
| 31 | 5 | 63 | 26 |
| 41 | 20 | 1,048,617 | 21 |
| 43 | 14 | 16,427 | 29 |

The actual API also uses any eligible earliest-exponent witness below these
uniform thresholds. For example, its first p = 41 exclusion in the supplied
ranges is

```text
143715 - 2^8 = 143459 = 41 * 3499,
```

although 143,715 is below 1,048,617. Parity is handled by the same proper-divisor
criterion with `m=2, K=1`: every even `n>4` is excluded.

## Exact result on the accepted intervals

The input is the four `tail_intervals` rows in the existing receipt. No original
primitive-root computation or predecessor test suite is rerun. On October 4,
2026, the public `refineIntervals` API ran in the connected V8 runtime on those
retained rows, with filters ordered as
`2, 7, 17, 23, 31, 41, 43` and exponent limits
`1, 3, 8, 11, 5, 20, 14`.

| Lower exclusive | Upper inclusive | Required divisor | Input candidates | Excluded | Survivors |
|---:|---:|---:|---:|---:|---:|
| 4,109 | 262,163 | 2,145 | 121 | 119 | 2 |
| 262,163 | 268,435,485 | 40,755 | 6,580 | 6,430 | 150 |
| 268,435,485 | 68,719,476,773 | 1,181,895 | 57,916 | 56,614 | 1,302 |
| 68,719,476,773 | 17,592,186,044,416 | 43,730,115 | 400,718 | 391,554 | 9,164 |
| **Total** | | | **465,335** | **454,717** | **10,618** |

This is a further reduction by approximately **43.8 times**. The first two
survivors are 92,235 and 109,395; both lie in the first interval. The last survivor
is 17,591,269,630,935. All 10,618 values, ordered increasingly, are stored in
[residual_candidates.json](residual_candidates.json).

An explicit reason not to treat this as a list of solutions is

```text
92235 - 2^12 = 88139 = 53 * 1663.
```

The prime 53 is outside this run's filter set. The API can use such partial
power cycles in subsequent work, even when the full primitive-root threshold
for the prime lies above the range being searched.

### Exact periodic proportion

Above 1,048,617, all six complete subgroups and parity are active. The Chinese
remainder theorem gives

```text
M = 2 * 7 * 17 * 23 * 31 * 41 * 43 = 299170522,
A = 1 * 4 * 9 * 12 * 26 * 21 * 29 = 6840288
```

allowed residue classes modulo `M`. Hence the exact proportion for these
filters is

```text
A/M = 488592/21369323.
```

Each required divisor in the four intervals is coprime to `M`, since it is a
product of the distinct primitive-root primes recorded by the predecessor.
For `n=D*j`, multiplication by `D` permutes the residues modulo `M`.
Thus every complete block of `M` consecutive multipliers whose candidates are
above the threshold contains exactly `A` survivors of these filters.

This is a count of allowed congruence classes, not a density or infinitude
claim for true solutions. The table above is the exact interval result,
including incomplete periods and the lower-threshold cases; it is not obtained
by multiplying interval lengths by `A/M`.

## Public API

```javascript
const {createPowerDifferenceSieve} = require('./residue_refinement.cjs');
const predecessor = require('./receipt.json');

const filters = [
  {modulus: 2, max_exponent: 1},
  ...predecessor.payload.nonprimitive_rows
    .filter(row => row.p !== 2)
    .map(row => ({
      modulus: row.p,
      max_exponent: row.order_two_mod_p,
    })),
];

const sieve = createPowerDifferenceSieve(filters);
const report = sieve.refineIntervals(
  predecessor.payload.tail_intervals,
  {include_survivors: true},
);
```

The snippet shows how the recorded dataset was produced. Downstream work should
load the saved candidate data instead of rebuilding an already accepted result:

```javascript
const residual = require('./residual_candidates.json');
const nextSieve = createPowerDifferenceSieve([
  {modulus: 53, max_exponent: 12},
]);
const classification = nextSieve.classify(residual.candidates[0]);
```

In a connected runtime, obtain the complete source through the native file
reader, retain its observed Git blob SHA, and evaluate the source without a
filesystem import:

```javascript
const moduleBox = {exports: {}};
new Function('module', 'exports', completeSource)(
  moduleBox, moduleBox.exports,
);
const sieve = moduleBox.exports.createPowerDifferenceSieve(filters);
const report = sieve.refineIntervals(retainedIntervals);
```

`classify(n)` returns either `EXCLUDED` with an explicit witness
`{filter_index, n, exponent, power, difference, divisor, cofactor}`, or
`SURVIVES_FILTERS` with a null witness. It does not classify primality.

`refineIntervals(intervals, options)` accepts ordered, nonoverlapping integer
ranges `(lower_exclusive, upper_inclusive]`, each restricted to multiples of its
`required_divisor`. It reads those three fields and tolerates the predecessor's
additional row metadata. The empty list and empty ranges are valid.

The result includes per-interval counts, first and last survivors, and exclusion
counts for each configured filter. Global filter summaries include one actual
first witness when that filter excludes anything. Exclusions are attributed to
the first matching filter in caller order, so those per-filter counts depend on
order; the surviving set does not. The default omits the full survivor array;
`include_survivors: true` adds it.

All candidate values and interval endpoints must be safe JavaScript integers
between zero and `Number.MAX_SAFE_INTEGER`. Required divisors are positive safe
integers. Filter moduli lie between 2 and
`floor(Number.MAX_SAFE_INTEGER/2)`, which covers every possible proper divisor
of a positive difference in this numeric domain. Exponent limits are integers
from 1 through 52; larger powers cannot be eligible below the maximum safe
candidate. Invalid values raise descriptive `TypeError` or `RangeError`
exceptions. The API accepts composite moduli too; no primality or multiplicative
order oracle is assumed internally.

Preparation takes time proportional to the sum of the exponent limits. A scan
takes time proportional to the candidate count times the number of filters.
Without the optional survivor array, storage is proportional to the compiled
residues and interval summaries. There are no network calls, imports, native
processes, or primality tests.

## Formalization handoff

This JavaScript execution is not Lean kernel elaboration or a sponsor
submission. The earlier [Lean handoff](LEAN_HANDOFF.md) and its historical
September task pins remain intact.

The [canonical problem page](https://conjectures.io/problems/erdos1142-erdos-1142)
retrieved on October 4, 2026 identifies task
`fc-6a786f99-erdos1142-erdos-1142-101c528ef8-formalized-v1`, commitment
`e5a0e8aec576159e7563e569fb912108f3234dfa6005906efb7e0a1a8cfb3456`.
Its displayed source-type SHA-256 remains
`140c4194bf440ed9095b2b1a1f8cb6b534b1f4738ee1c9d78a89ec890ed38632`.
The current pinned bundle was not executed in this continuation. A later
formalization should select the then-current bundle, preserve the existing
contribution's ownership, and formalize the proper-divisor and earliest-exponent
lemmas before consuming the finite candidate data.
