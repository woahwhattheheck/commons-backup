# E366: exact fresh range 10^12 < m <= 2*10^12

This note documents the fixed-range CommonJS consumer in `erdos366_range_shards.cjs`, its mathematical enumeration and predecessor decision, and the completed four-shard production result. It is an interval extension of the existing E366 work, not a replay of the accepted search through 10^12. The target predicate is that m is 3-full and m-1 is 2-full: every prime exponent of m is at least 3, and every prime exponent of m-1 is at least 2.

All paths below are relative to `research/math-prize-lab/erdos366/`.

## Frozen inputs and provenance

| Artifact | Git blob SHA | UTF-8 bytes |
| --- | --- | ---: |
| `erdos366_range_shards.cjs` | `594d3ff2125db500e7886b2fe2587858ed3ad207` | 21,010 |
| `range_1e12_2e12_input.json` | `ada2b1bbcf61155e19423c3e58a0060a3b92a0d0` | 10,515 |
| `range_1e12_2e12_plan.json` | `a20deff1779173e688a520122d3be55e891872d0` | 433,507 |
| `range_1e12_2e12_manifest.json` | `b3246b4101d7c0bc8531cfc63160ae07a31bffb7` | 217,374 |

The source and input were banked before production. The plan was built once, then banked before the four separate shard runs. Each shard consumed that saved plan once. The source's native bank SHA matched its independent Git blob identity. This note was authored from the frozen source contract and the operator's retained results; authoring it did not invoke the engine or revalidate candidate arithmetic.

The input supplies the already accepted literal prefix of 1,900 primes, from 2 through 16,381, taken from [Commons #31726](https://github.com/woahwhattheheck/commons/pull/31726). Its source is `research/erdos238_consecutive_prime_blocks/prime_prefix1900_blocks.json` in `woahwhattheheck/commons` at commit `e04374c3650c68ff5ed22c8997f6805eb5b31c85`, blob `0224dfb74525d7d18b6e5aba20f01e1784a0c8f2` (790,007 UTF-8 bytes). The input's `prime_source` object preserves that provenance. This consumer checks the declared count, endpoints and strict ascending integer shape. It does not run a sieve or re-prove primality or completeness. Those properties remain attributed to the accepted prefix.

Problem-definition provenance also includes the fully supplied [Formal366 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/366.lean), observed at the default ref with blob `9c10934c0afa65761927ad4a292e2ddd42ae5b3e` (2,009 UTF-8 bytes). No fixed commit was established for that observation. The direct erdosproblems.com/366 request returned 403 and remains held; no successful direct-page acquisition or alternate recovery is claimed.

The original Commons #16008 bounded search and #16019 test-entrypoint repair retain their own source and evidence. The original source and test files are unchanged by this packet. The existing README receives only a pointer to this new range deliverable.

## Canonical enumeration and its proof

A positive integer m is 3-full precisely when every nonzero prime exponent e in m is at least 3. For each such exponent there is one of three cases:

- If e is congruent to 0 modulo 3, write e=3k and place p^k in a.
- If e is congruent to 1 modulo 3, then e>=4. Write e=3k+4, place p^k in a and one p in b.
- If e is congruent to 2 modulo 3, then e>=5. Write e=3k+5, place p^k in a and one p in c.

Thus every 3-full m has a representation

$$m=a^3 b^4 c^5,$$

where a>=1, b and c are squarefree, and gcd(b,c)=1. Conversely, any such representation is 3-full: a prime occurs with exponent 3k, 3k+4 or 3k+5, and every positive exponent is at least 3. The primes in a need not be coprime to b or c.

This representation is unique. The exponent modulo 3 decides whether the prime belongs to neither coefficient, to b, or to c; subtraction of 0, 4 or 5 then determines its exponent in a. Squarefreeness and disjointness of b and c exclude alternative coefficient assignments. Consequently distinct coefficient/a rows cannot represent the same m.

The plan constructs one squarefree list through floor(U^(1/4)) from increasing subsets of the accepted primes, using each prime at most once. Strictly increasing factor lists give each squarefree value once. The list is sorted numerically. The c values reuse its prefix through floor(U^(1/5)); no second squarefree enumeration is performed. Coprimality is decided by intersecting the already stored factor lists.

These coefficient bounds are sufficient because a,b,c>=1: a candidate with m<=U must satisfy b^4<=U and c^5<=U. The plan considers every squarefree, coprime coefficient pair with q=b^4*c^5<=U. It retains the exact b/c factors and powers needed to bind later candidate records to their coefficient.

## Strict lower bound and disjoint shards

For a fixed coefficient q, the permitted positive integers a satisfy

$$L<a^3q\le U.$$

Exact integer arithmetic gives

$$a_{\min}=\left\lfloor\sqrt[3]{\left\lfloor L/q\right\rfloor}\right\rfloor+1,\qquad a_{\max}=\left\lfloor\sqrt[3]{\left\lfloor U/q\right\rfloor}\right\rfloor.$$

The integer cube roots are computed with BigInt comparisons. These formulas directly select the strict lower interval; the runner does not enumerate candidates at or below L and discard them afterward. A coefficient for which a_max<a_min is retained with count zero. The runner also checks each emitted m against the fresh interval before testing m-1.

Coefficient order is c ascending, then b ascending, with zero-based ordinals. Ordinal modulo 4 assigns every coefficient to exactly one shard. Inside a coefficient, a is increasing. The four shards therefore partition the plan without overlaps or gaps, including its empty coefficient ranges. Candidate order is deterministic within each shard; it is not a claim that concatenating shard files produces globally increasing m.

The plan computes coefficient powers, exact a bounds and prime cubes once. A shard parses those saved values and performs its assigned candidate and predecessor work; it does not rebuild the coefficient plan. Structural plan checks do not authenticate saved data. The caller must preserve and identify the exact banked plan rather than mutate or reconstruct it.

## Exact predecessor decision and certificates

For n=m-1, the runner strips primes in increasing order. For a prime that divides the remaining value, it removes the full power and records the exponent. An exponent of exactly 1 proves that n is not 2-full and stops that candidate. An exponent of at least 2 is compatible with 2-fullness.

At the start of the next prime p, every smaller prime has been exhausted. If p^3 is greater than the remaining value r, then r has at most two prime factors counted with multiplicity: three factors would each be at least p and would force r>=p^3. The runner then computes the exact integer square root.

- If r is a square, its prime exponents are all even. Together with the removed powers, whose exponents are at least 2 on this path, this proves n is 2-full. The case r=1 is included.
- If r>1 is not a square, the bound on the number of remaining prime factors means r is either a prime or a product of two distinct primes. At least one exponent is 1, so n is not 2-full.

The accepted prefix extends past the cube-root boundary of U: its last prime cube exceeds U. Since r<=m-1<U and never increases, a valid run cannot exhaust the prefix before reaching a decision.

This is a new certificate format, not the legacy `FullCheck` record. Each candidate stores its coefficient ordinal, a, m and the predecessor decision. The plan holds the b/c factor lists, so they are not duplicated in every candidate. Predecessor certificates have these forms:

| Certificate type | Retained evidence | Meaning |
| --- | --- | --- |
| `prime_exponent_one` | Removed prime powers, rejecting prime and exponent, residual, tested-prefix count | A fully stripped prime exponent is exactly 1. |
| `square_tail` | Removed prime powers, residual, exact square-tail root, tested-prefix count, next prime and its cube | The residual is a square after all smaller primes have been exhausted. |
| `nonsquare_tail` | Removed prime powers, residual, tested-prefix count, next prime and its cube | The residual is nonsquare and below the next-prime cube. |

The square-tail root is not claimed to be fully factored. A nonsquare-tail certificate likewise does not pretend to supply the missing residual prime factorization. Both decisions use the stated exhausted-prefix and cube-bound argument.

## Fixed API and work limits

The module is pure CommonJS with no filesystem, network or CLI behavior. Its public functions are `buildRangePlan(input)` and `runRangeShard(plan,index,record?)`; it also exports `RangeWorkError`. Large arithmetic values are represented as decimal strings in returned JSON data.

~~~js
const plan = buildRangePlan({
  lower_exclusive: "1000000000000",
  upper_inclusive: "2000000000000",
  shards: 4,
  primes: acceptedLiteralPrimePrefix,
  prime_source: acceptedPrefixProvenance
});
// Bank and identify this exact plan before any shard call.
const shard = runRangeShard(plan, shardIndex);
~~~

This example specifies the API; it is not a request to rerun the completed production. Reuse is scoped to the saved coefficient-plan/shard contract. This version rejects different bounds or shard counts and does not offer automatic resume, extension or cap restarts.

| Limit | Exact scope |
| --- | --- |
| U=2,000,000,000,000 | Fixed upper bound; L is fixed at 1,000,000,000,000. |
| 10,000 coefficient pairs | Pairs with q<=U counted before their coprimality test; larger-q loop-bound probes are separately counted. |
| 100,000 candidates | Total candidate count reserved by the plan before predecessor work. |
| 2,500,000 trial steps per shard | Each predecessor divisibility modulus attempt counts as one step and is checked before execution. |
| 10,000,000 combined trial steps | Conservative sum of the four fixed shard caps; unused capacity is not redistributed. |

Other counters distinguish plan generation, root comparisons, coefficient ranges, candidate starts/completions, prime visits, factor divisions, tail decisions and optional callback activity. They are operation counts with their stated meanings, not elapsed time or an exhaustive CPU-instruction count.

A cap or other error throws `RangeWorkError`, whose `partial` field retains completed records, work counters, coefficient-range progress and active state. During factor stripping, that state includes the current residual, removed powers and the current prime/exponent. The original cause is also retained. A caller should bank the partial record and stop; the API performs no retry or automatic restart.

The optional record callback must be synchronous and receives a copy of each completed candidate record. The internal record is appended before the callback. This production omitted the callback entirely: callback success/failure, thenable rejection and other error/cap paths remain unexecuted.

## Completed production result

The once-built plan contains 723 squarefree values through 1,189, reusing their prefix through 288 for c. It retains 1,786 coefficient rows, 573 empty coefficient ranges and 11,077 fresh candidates. All four shard results report complete.

| Shard | Candidates | Trial steps | Nonsquare-tail rejections | Exponent-one rejections | Witnesses |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 4,173 | 515,020 | 295 | 3,878 | 0 |
| 1 | 2,570 | 584,565 | 417 | 2,153 | 0 |
| 2 | 1,694 | 453,008 | 348 | 1,346 | 0 |
| 3 | 2,640 | 635,085 | 475 | 2,165 | 0 |
| Total | 11,077 | 2,187,678 | 1,535 | 9,542 | 0 |

No shard reported a square tail or invoked a callback. No cap was reached. The reported totals also include 18,424 factor divisions and 35,330 Newton iterations/divisions under the source's counter definitions. Every fresh candidate was retained with its predecessor certificate; the search did not retain only failures of a screening heuristic or only potential witnesses.

Subject to the accepted prime-prefix premise and the stated engine/certificate argument, these completed outputs establish that this exact interval contains no m with m 3-full and m-1 2-full. They do not establish global nonexistence, a new best-known literature bound, an award, or acceptance of a prize claim. No separate test/fixture suite, accepted-baseline replay, timing benchmark, cluster run, external submission, account action or payment action was performed for this deliverable.

## Saved records and exact reassembly

The complete shard outputs were banked before storage splitting:

| Shard | Complete output Git blob SHA | UTF-8 bytes |
| ---: | --- | ---: |
| 0 | `2c601349e1ce01d3acdbc977ca5a798d7cdd93dc` | 1,328,169 |
| 1 | `0e0627ee06a4e67f7d416e1e827142e90eec51ee` | 832,974 |
| 2 | `34ee3532aa1da063b36f0a0b7abdaf76687aeaad` | 576,259 |
| 3 | `2d19f729fe56921008c1857eeabefa6487526255` | 861,950 |

For publication, each records array is split into two valid JSON arrays: `range_1e12_2e12_shard{0..3}_records{0..1}.json`. The manifest is `range_1e12_2e12_manifest.json`. For each shard it preserves an `output_header` with `records:null` at the original property position, ordered part maps, and the complete output's SHA and byte count. The published manifest records the exact part identities and ordering; filenames alone are not an integrity check.

Reassembly uses the ordered arrays as data. It does not regenerate candidates, run factor tests, rebuild the plan or infer omitted records:

~~~js
const records = orderedPartArrays.flat();
const output = Object.assign({}, output_header, {records});
const bytesAsText = JSON.stringify(output) + "\n";
~~~

Replacing the existing records property preserves its original insertion position. Using the saved header without reordering its keys and retaining each part's record order allows the compact serialization plus final LF to reproduce the banked whole-output bytes. Compare the complete UTF-8 byte count and Git blob identity with the manifest. This is a byte-identity operation, not another execution or mathematical validation of the search.

The operator performed this serialization/byte-identity check on all four outputs after splitting: each reconstructed its original full-output SHA and byte count exactly. All eight published record-array files are valid JSON arrays smaller than 638,000 UTF-8 bytes. This check did not repeat candidate arithmetic.

The full original outputs, the manifest, part maps and all observed production limits remain separate evidence from any future reader or reuse. No second production run is needed to publish, reassemble or read these saved artifacts.
