# Binomial prime-valuation and exception navigator

This package retains the complete prime-exponent factorization of every binomial coefficient C(n,k) with **2 ≤ n ≤ 256** and **1 ≤ k ≤ floor(n/2)**. Its 16,384 rows support least-prime queries, exact threshold-exception families, squarefree and valuation conditions, ranks, selections, and requested exact or modular integer products.

The finite triangle has **13** pairs with least prime factor greater than max(floor(n/k),k). All thirteen are exported with complete factors. This is an exact finite classification, not a proof that the unrestricted exception set is finite or a claimed new search frontier.

## Statement, source and input

The complete actually read [FormalConjectures/ErdosProblems/1094.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/1094.lean) has Git blob identity
`66906baa450cf432bbde82d6506fe4c400e92a70` (1,098 bytes). The request used the default branch without an immutable commit ref; the content identity does not assert a repository commit. Its theorem is the finiteness of

```text
{ (n,k) in Nat × Nat :
  0 < k and 2*k <= n and
  minFac(C(n,k)) > max(n / k, k) }.
```

Division in this Lean expression is natural-number floor division. The inequality is strict. The source is annotated research open and has a local `sorry`; no proof was executed or reviewed. The earlier semantic-audit receipt in the public thread is preserved as prior work, not repeated here. This package makes no current platform bounty or award assertion.

Gennady Eremin's author preprint [“Legendre's formula and p-adic analysis,” arXiv:1907.11902v1](https://arxiv.org/abs/1907.11902), submitted 27 July 2019, states in its abstract the classical Legendre formula

```text
v_p(n!) = sum over j >= 1 of floor(n / p^j).
```

The abstract defines the factorial prime exponent and identifies binomial valuations as an application. Only that abstract and its metadata were read, not the PDF, proofs or examples. The formula is credited to Legendre; no journal publication or independent original Erdős statement was inferred from the abstract. The exact E1094 statement conventions come from the complete formal source above.

For this API the factorial-quotient specialization is

```text
v_p(C(n,k)) = v_p(n!) - v_p(k!) - v_p((n-k)!).
```

This is the elementary translation used by the implementation, not a separate displayed formula claimed to have been quoted from the abstract.

The exact input is `input256.json`, Git blob
`522485b25d27bf7c37b0042dea6339fd4dea15d8` (1,973 bytes).
Its complete prime prefix consists of the first 54 primes, from 2 through 251; 257 is the supplied next-prime boundary. The literal values were transferred from the saved `primes` field of [PR #31726](https://github.com/woahwhattheheck/commons/pull/31726), merge
`e04374c3650c68ff5ed22c8997f6805eb5b31c85`, path
`research/erdos238_consecutive_prime_blocks/prime_prefix1900_blocks.json`,
blob `0224dfb74525d7d18b6e5aba20f01e1784a0c8f2`.
Only indices 0..53 and boundary index 54 were consumed. No old gap, least-factor, sieve or binomial calculation was read as a production input or rerun.

The prime values and their completeness are inherited premises. The constructor checks their shape and order and that the boundary exceeds the declared maximum; it does not reprove primality or completeness. Every prime dividing C(n,k) divides n!, hence is at most n. The complete prefix through 256 is therefore enough for every row of this input.

## Construction and finite conclusion

For each of the 54 primes p and each n from 0 through 256, the constructor saves the Legendre factorial exponent. The entry for 0! is zero. For positive n it repeatedly takes q = floor(q/p), beginning with q = n, adds positive quotients and stops at zero. These successive quotients equal floor(n/p^j), so no factorial integer or large power of p is required.

Each binomial row subtracts the two denominator factorial exponents from the numerator exponent for all supplied primes. Positive exponents are retained as sparse pairs [prime index, exponent]. The first positive exponent gives the least prime factor. Since the domain has 1 ≤ k ≤ n/2 and n ≥ 2, every coefficient exceeds one and must have a positive exponent; a missing divisor is treated as an error.

The constructor also saves the threshold max(floor(n/k),k), the strict exception bit, total prime exponent, squarefree bit, row offsets, per-n counts and least-prime histogram. It does not construct the binomial coefficient as an integer. These facts completely determine the factorization and the displayed predicates under the complete-prime premise.

The complete exception list is:

| n | k | Least prime factor | Threshold |
| ---: | ---: | ---: | ---: |
| 7 | 3 | 5 | 3 |
| 13 | 4 | 5 | 4 |
| 14 | 4 | 7 | 4 |
| 23 | 5 | 7 | 5 |
| 44 | 8 | 11 | 8 |
| 46 | 10 | 11 | 10 |
| 47 | 10 | 11 | 10 |
| 47 | 11 | 13 | 11 |
| 62 | 6 | 19 | 10 |
| 74 | 10 | 11 | 10 |
| 94 | 10 | 11 | 10 |
| 95 | 10 | 11 | 10 |
| 241 | 16 | 17 | 16 |

All thirteen happen to be squarefree in this finite triangle, as their complete saved exponents show. This observation is not asserted for all exceptions beyond the input bound. The row count is sum from n=2 to 256 of floor(n/2), namely 16,384.

Other saved-reader family counts are:

| Condition | Exact count |
| --- | ---: |
| All rows | 16,384 |
| Strict threshold exceptions | 13 |
| Squarefree binomial coefficients | 1,264 |
| Nonsquarefree binomial coefficients | 15,120 |
| Least prime factor at least 5 | 638 |
| Both 2-adic and 3-adic valuations zero | 638 |
| n ≥ 200, k ≥ 2, squarefree | 422 |
| n = 256, valuation at 2 at least 7 | 96 |
| Exceptional and nonsquarefree | 0 |

These count pairs (n,k), not distinct numerical binomial values. Equal coefficients at different pairs remain different rows. Symmetric upper-half pairs are outside the declared domain and are not silently counted a second time.

## Files and exact assembly

The construction snapshot is 2,672,079 bytes in compact JSON plus one newline, with Git blob
`620aa1a9ab5fe8df21647b6895b4f285c8d5782d`.
It is retained through `triangle256_manifest.json` and eight complete row shards `rows_00.json` through `rows_07.json`. Each shard contains 2,048 consecutive rows. The manifest carries the complete non-row snapshot data, including every factorial valuation, offsets and histogram.

To reconstruct the snapshot, concatenate each shard's `rows` array in the manifest order and replace the manifest snapshot's `rows: null` field with that array. Preserve the existing property order. `JSON.stringify(snapshot) + "\n"` is the exact original serialization. The recorded assembly compared those bytes and their Git blob identity; it did not invoke the constructor, reader, Legendre sums or exponent subtraction.

```javascript
const fs = require("node:fs");
const { open } = require("./binomial_valuation_index.cjs");
const manifest = JSON.parse(fs.readFileSync("./triangle256_manifest.json", "utf8"));
const rows = manifest.shards.flatMap(({file}) =>
  JSON.parse(fs.readFileSync(file, "utf8")).rows
);
const snapshot = Object.assign({}, manifest.snapshot, { rows });
const api = open(snapshot);
const exceptions = api.page("0", 200, { exceptional: true });
```

This is a loading example, not a second execution performed while writing the guide. The module exports `SCHEMA`, `construct(input)` and `open(snapshot)`. Consume the published input by loading its saved snapshot; a new constructor invocation is for a genuinely new input.

The snapshot's `row_fields` defines each compact row:

1. n.
2. k.
3. Least-prime index into `primes`.
4. The integer threshold.
5. Exception bit.
6. Total prime exponent, counting multiplicities.
7. Squarefree bit.
8. Positive factors as [prime index, exponent] pairs.

The public reader expands factors into named records, retaining both index and prime value. `open` checks the snapshot schema and basic lengths. It does not independently verify every arithmetic cell, the prime premise or this derivation; this is not a standalone proof checker.

## Reader API

All ranks are zero-based decimal strings in increasing n, then increasing k. A conditional family retains this same order. n, k and prime indices are ordinary bounded integers; exact products, ranks and moduli use decimal strings where documented.

| Method | Result |
| --- | --- |
| `summary()` | Domain, prime premises, exception IDs, least-prime histogram and construction counters |
| `family(options)` | Exact count of a compiled condition |
| `select(rank, options)` | One row and its complete factorization |
| `rank(n, k, options)` | Membership and rank, or a nonmember result |
| `page(start, limit, options)` | Up to 200 rows with complete factors |
| `row(n,k)` | One saved row and complete factors |
| `valuation(n,k,primeIndex)` | Saved prime exponent, including zero when absent |
| `factorial(n,primeIndex)` | One saved factorial exponent; n=0 is permitted |
| `integer(n,k)` | A newly multiplied exact integer from the saved factors |
| `modulo(n,k,modulus)` | A newly computed residue from the saved factors |
| `byN(n)` | Saved row offsets, count and exception count for one n |
| `caches()` | Complete conditions compiled by this reader instance |
| `work()` | Cumulative named-operation counters |

Options support `min_n`, `max_n`, `min_k`, `max_k`, `least_prime_min`, `least_prime_max`, `exceptional`, `squarefree`, `min_distinct_factors` and `max_distinct_factors`. The optional `valuations` array contains records `{prime_index, min, max}`; omitted bounds default to 0 and the input maximum n. Duplicate prime indices or contradictory intervals are rejected. Exceptional and squarefree restrictions are optional Boolean values.

Conditions scan the saved rows once and save the complete increasing list of matching row IDs. Subsequent calls with the same normalized condition reuse that list. Rank uses binary search in the saved list; selection uses its indexed entry. Valuation conditions binary-search a row's saved sparse factors. None of these operations recomputes factorial or binomial valuations.

`integer` and `modulo` multiply the saved prime powers using repeated squaring. They are explicit new arithmetic. Modulus must be a positive decimal integer; no primality assumption is needed, and modulus one returns zero. The module does not factor arbitrary query moduli.

The published `saved_condition_caches.json` contains all nine conditions and 34,575 row-ID entries created by the actual reader. The current API keeps cache state within one `open` object and does not import an exported cache into another instance. A new instance's condition compilation is new query work and should be reported as such.

## Actual reader and arithmetic

The fresh reader ran after source, exact input and complete construction output were banked. All **62** query responses are retained in `saved_reader_queries.json`, Git blob
`68df33768328c1c26d14169eb7f113bb4d8311ee` (141,354 bytes).
The cache packet has Git blob
`d971c1926a3c8ca6c98be99fefb6c9e6670af56e` (501,635 bytes).

The reader exports all 13 exceptional rows and performs 13 corresponding inverse-rank queries. Three full-family and six additional condition selections add nine more inverse pairs. All **22** match. It also records complete family counts, saved factorial and binomial valuation lookups, four exact products, four modular products and one deliberate nonmember result.

For example, the newly requested exact product C(241,16) is
3720625555021727122496771, with 13 distinct prime factors and least prime 17, exceeding threshold 16. The reader's C(256,128) residue modulo 1000000007 is 240734056. These products and residues were computed from the retained factors; they are not claimed as independent arithmetic verification or a replay of the construction.

| Reader counter | Value |
| --- | ---: |
| Queries | 62 |
| Conditions compiled / cache hits | 9 / 33 |
| Saved-row scans | 147,456 |
| Valuation-filter checks | 19,537 |
| Sparse-factor binary-search probes | 90,719 |
| Conditional row-ID entries | 34,575 |
| Rank binary-search probes | 152 |
| Row / factorial lookups | 65 / 3 |
| Factor output pairs | 217 |
| Exact-power squarings / multiplies | 8 / 75 |
| Exact factor products | 74 |
| Modular-power squarings / multiplies | 8 / 113 |
| Modular factor products | 112 |
| Modular reductions | 461 |

Request preparation additionally performed seven BigInt midpoint divisions and one BigInt last-rank subtraction. Ordinary loop, array and validation operations are not claimed as a complete arithmetic-cost census. There were no failed or unavailable reader responses. Every result was banked immediately.

Reader counters for constructor calls, new factorial cells, new binomial valuation cells, primality tests and sieve steps are all zero. This does not mean the reader performed no computation: its condition scans and integer/modular arithmetic are counted above.

## Construction work, bounds and limits

The executed source `binomial_valuation_index.cjs` has Git blob
`659fef01d6cebd4cc1c9cce79338aa7076ff6b08` (11,451 bytes).
It was banked before its one constructor invocation and was not modified or rerun afterward.

| Construction counter | Value |
| --- | ---: |
| Factorial-valuation cells | 13,878 |
| Legendre floor divisions | 24,376 |
| Legendre additions | 10,552 |
| Binomial rows | 16,384 |
| Binomial valuation cells | 884,736 |
| Valuation subtractions | 1,769,472 |
| Positive factor pairs retained | 335,595 |
| Threshold floor divisions | 16,384 |
| Least-prime histogram additions | 16,384 |
| Exception index entries | 13 |
| Primality tests / sieve steps / binomial integer products | 0 / 0 / 0 |

The generic maximum n is 4,096, subject to predeclared caps. The actual input allows at most 200,000 rows, 250,000 factorial cells, 3,000,000 binomial valuation cells and 1,000,000 positive factor pairs. Row, factorial and valuation caps are checked before production; the factor cap is checked during construction. A cap error yields no complete snapshot and is not reclassified as a result. This input completed within all caps.

The observations concern the complete declared finite triangle and its exact query conditions. They establish no global finiteness theorem, no new numerical frontier, no general squarefree-exception statement and no mathematical priority or award claim. Source status, inherited prime completeness and the finite arithmetic are kept distinct.
