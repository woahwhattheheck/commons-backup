# Shared squarefree offset catalog

[offset_catalog.cjs](offset_catalog.cjs) prepares squarefree offsets for [OEIS A304081](https://oeis.org/A304081). It implements the normalized construction documented by Zhi-Wei Sun in that entry (May 6, 2018) and [A304122](https://oeis.org/A304122) (May 7, 2018). The construction is existing source mathematics; this module makes it available as a reusable exact catalog.

A304081 counts exponent-pair representations

`n = p + 2^k + (1 + (n mod 2)) * 5^m`,

where `p` is an odd prime, `k,m >= 0`, and the complete non-prime offset is squarefree. The API stops before primality evaluation.

## API and integer bounds

`createOffsetCatalog(max_n)` accepts a nonnegative canonical decimal string, a `BigInt`, or a nonnegative safe integer. The inclusive maximum supported value is `1000000000000` (`10^12`). Decimal strings use `0` or a nonzero digit followed by decimal digits; signs, whitespace, leading zeroes and exponent notation are not canonical. Fractional and unsafe Number inputs are not exact integer inputs.

The catalog schema is `commons.a304081.offset_catalog/v1`. The returned object exposes its inclusive `max_n`, `base_bound = max(0, max_n - 3)`, construction `statistics`, and two methods:

- `listBaseOffsets()` returns fresh JSON-safe rows `{j, m, base_offset}` through `base_bound`, subject to `j >= 1`, `m >= 0`, and squarefreeness. Rows are ordered by numeric base offset, then `j`, then `m`. Bounds below the smallest base offset produce no rows.
- `candidatesFor(n)` uses the same integer input formats and requires `0 <= n <= max_n`. It returns schema `commons.a304081.prime_candidates/v1`, the target `n`, its `coefficient`, `prime_status`, `coverage`, `exponent_pair_count`, `distinct_offset_count` and `candidates`. Each candidate row contains `prime_candidate`, `offset`, `base_offset`, `j`, `k` and `m`.

Large integer values are decimal strings in the JSON-safe output. The small exponent indices and parity coefficient identify how to reconstruct the original expression. The result explicitly reports `prime_status: "not_evaluated"`: its row counts are candidate counts, not the sequence value `a(n)`.

For a base row `s = 2^j + 5^m`, selection uses:

| Target | Coefficient `c` | Original exponent `k` | Actual offset | Candidate |
| --- | --- | --- | --- | --- |
| even `n` | 1 | `j` | `s` | `n - s` |
| odd `n` | 2 | `j + 1` | `2*s` | `n - 2*s` |

Only rows with `prime_candidate >= 3` are returned. Parity already makes these candidates odd. It does not make them prime. The coverage record sets `complete_offsets_for_n: true`, repeats the inclusive `catalog_max_n`, and records `minimum_prime_candidate: "3"`; this is offset coverage, not primality coverage.

## Why one base catalog covers both parities

For `k = 0`, the original offset has the same parity as `n`, so the remaining `p` is even and cannot be the required odd prime. For even `n`, all remaining cases have `k >= 1`; put `j = k`.

For odd `n`, `k = 1` gives `2 + 2*5^m`, which is divisible by 4 and therefore not squarefree. For `k >= 2`, put `j = k - 1`. The offset is then `2*(2^j + 5^m) = 2*s`. Every such `s` is odd, so `2*s` is squarefree exactly when `s` is squarefree.

Consequently each admissible exponent pair has one normalized row, with the inverse exponent mapping in the table. Since `p >= 3`, any needed base satisfies `c*s <= n - 3`, and hence `s <= max_n - 3`. The shared catalog bound therefore covers every permitted target; the odd-target filter usually selects a smaller part of it.

## Preserve exponent-pair multiplicity

A304122 enumerates distinct squarefree values in the family `2^j + 5^m`. Its published program deduplicates values. A304081 instead increments its count for each qualifying exponent pair.

For example, `33 = 2^3 + 5^2 = 2^5 + 5^0` is squarefree. The catalog retains both `(j=3,m=2)` and `(j=5,m=0)`. For an even target they have the same offset 33; for an odd target they have the same offset 66 and original exponents 4 and 6. They are two pair rows but one distinct offset. If their shared prime candidate later passes primality evaluation, both count toward A304081.

Do not deduplicate the candidate array to compute a representation count. A consumer interested only in existence may choose to evaluate a repeated prime candidate once while retaining the pair multiplicity separately.

## Construction and reuse

Construction enumerates bounded integer powers and classifies squarefreeness once per distinct numeric base value. A bounded prime sieve supplies trial divisors; the squarefreeness result is cached for every exponent pair producing that value. The resulting classification is also reused by the even and odd queries; the parity equivalence above removes the need to factor `2*s` separately.

All power, offset and bound decisions use exact integer arithmetic. Querying an existing catalog applies the target bound and exponent mapping; it does not repeat construction or run a primality test. The cap limits this implementation's preparation domain and does not replace the separate C++ search bound. No measured speedup is asserted.

A CommonJS caller in this directory can prepare one catalog and reuse it for multiple targets:

```javascript
const {createOffsetCatalog} = require('./offset_catalog.cjs');
const catalog = createOffsetCatalog('6229207682');
const evenCandidates = catalog.candidatesFor('6229207682');
const oddCandidates = catalog.candidatesFor('9574899');
const baseOffsets = catalog.listBaseOffsets();
```

The dependency-free module also works through the existing connected runtime's in-memory module loader; the October 4 use below followed that route. Preserve the full base rows, schema, bounds and statistics when exporting a catalog for another consumer. A saved array contains reusable data; it is not by itself a reconstructed API object.

## First connected-runtime use

On October 4, 2026, the complete API source at Git blob `4eb31cfe376c74e9d1e3a56de15dce4e0dbcd362` was loaded in the connected V8 runtime. One constructor call prepared `max_n = 6229207682` and `base_bound = 6229207679`. Its observed statistics were:

| Statistic | Observed value |
| --- | ---: |
| `base_exponent_pairs_considered` | 474 |
| `distinct_base_values_examined` | 470 |
| `squarefree_base_exponent_pairs` | 366 |
| `distinct_squarefree_base_values` | 363 |
| `rejected_base_exponent_pairs` | 108 |
| `squarefree_classifications` | 470 |
| `factor_sieve_limit` | 78925 |
| `factor_primes` | 7741 |

`candidatesFor` was called once for each target:

| Target `n` | Coefficient | Exponent-pair candidates | Distinct offsets | Prime status |
| --- | ---: | ---: | ---: | --- |
| `6229207682` | 1 | 366 | 363 | `not_evaluated` |
| `9574899` | 2 | 171 | 168 | `not_evaluated` |

The even result contains `(j=3,k=3,m=10)`, base and offset `9765633`, candidate `6219442049`. The odd result contains `(j=18,k=19,m=0)`, base `262145`, offset `524290`, candidate `9050609`. The first target is related to the restrictive example in [A304031](https://oeis.org/A304031), and the second to [A303949](https://oeis.org/A303949); A304081 also records the latter representation. Their source-reported primality and restrictive uniqueness were not rechecked.

The related entries impose a limit of three distinct prime factors on their stated `2^j + 5^m` term. A304031 permits the prime 2; A303949 permits base exponent 0 and places its squarefreeness condition on the inner term. This API keeps A304081's odd-prime and complete-offset squarefreeness conventions. The source targets therefore exercise both parities without identifying those different representation sets.

`listBaseOffsets()` was called once. The resulting complete 366-row catalog is preserved in [base_offset_catalog_20261004.json](base_offset_catalog_20261004.json) as compact tuples with columns `[j, m, squarefree_base_offset]`, together with the API source blob pin and catalog metadata. It retains both rows for 33. This file is reusable input data, not a primality certificate or a replay of an old search.

## Relation to the existing C++ tool

The API's `max_n` is an inclusive query limit. The unchanged C++ `SearchSpace` constructor uses an exclusive internal offset bound; its command-line `count N` and interval modes compensate by constructing `SearchSpace(N + 1)` or `SearchSpace(HI + 1)`. Do not copy that internal off-by-one convention into calls to `createOffsetCatalog`.

The C++ tool performs primality evaluation and can count verified representations. This catalog only prepares the squarefree-offset candidate set. The old code, recorded executions and self-tests are unchanged and are not rerun by catalog construction.

The universal positivity statement remains a conjecture. Candidate preparation, a finite target query or a saved catalog is neither a proof nor a new verified search frontier; it also makes no prize or submission claim.
