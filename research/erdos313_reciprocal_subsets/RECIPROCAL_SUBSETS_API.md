# Exact reciprocal-subset navigation from an identified prime list

This package indexes sums of reciprocals of subsets of a supplied finite prime set. It saves two sorted half-subset tables and uses them for exact rational interval counts, increasing-sum ranks, selection, required/excluded-prime conditions, and membership at the target 1−1/m. It stores the half tables rather than every complete subset sum.

The actual input is the identified list of 24 primes through 89. Its two 4,096-row tables represent 16,777,216 distinct sums. Exactly 10,262,454 are below 1, none equals 1, and 6,514,762 are above 1. The first saved reader made 33 queries, including complete interval cutoffs and seven inverse rank checks. These are finite results for this specified universe.

## 1. Sources and scope

The complete [FormalConjectures statement of Erdős 313](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/313.lean) was read at Git blob `50a8309d009740ad2cf50e441ebaf23d61818b3f` (3,991 bytes). It asks about infinitely many pairs (m,P), where m≥2 is an integer and P is a nonempty finite set of distinct primes satisfying

$
\sum_{p\in P}\frac1p=1-\frac1m.
$

Its infinitude declarations carry research-open annotations and local placeholders. The file also contains known examples and proof text; none was executed or audited here. This inspection does not certify the current external literature frontier.

John Machacek, [*Egyptian Fractions and Prime Power Divisors*, Journal of Integer Sequences 21 (2018), Article 18.3.7](https://cs.uwaterloo.ca/journals/JIS/VOL21/Machacek/mach4.pdf), printed page 2, defines a primary pseudoperfect integer n>1 by

$
\sum_{p\mid n}\frac1p+\frac1n=1.
$

There is one term for each distinct prime divisor. Machacek credits Butske, Jaje and Mayernik with the definition, and separately names the prime-power-divisor generalization. We use the distinct-prime convention. The original AMS article route returned 403; it was not retried or replaced with another copy. Machacek's successfully read independent paper supplies the definition used here. No examples, tables, proofs or contemporary bounds were evaluated.

The formal pair convention and the usual number definition agree by elementary arithmetic. Put Q=∏P. Multiplying the displayed equality by Q shows Q/m is an integer, so m divides Q. If a prime p∈P did not divide m, reduction modulo p would make every term except Q/p vanish, a contradiction. Thus m contains every prime of Q, and m=Q. This is an explanation of the interface's interpretation, not a new primary-pseudoperfect theorem.

The API admits the empty subset as the first navigation record, with sum 0. It is not a solution of Formal313 because it would give m=1. Each prime can be selected at most once. Selecting a prime power is not an additional option.

This finite chosen-prime model is not an exhaustive search over arbitrary prime sets and makes no assertion of infinitely many primary pseudoperfect numbers. A failed target query is only a failure inside the supplied universe. No prize, sponsor acceptance, new extremal record or mathematical priority is claimed.

## 2. Exact input custody

The input is the literal selected prime list already published in Commons #31434:

```text
2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37,
41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89
```

| Item | Identity |
| --- | --- |
| Carrier | [Commons #31434](https://github.com/woahwhattheheck/commons/pull/31434) |
| Immutable head | `6f30f2378e3816318cea54197103cc0269b089b8` |
| Source path | `research/ppl133_erdos1052_unitary_divisors/UNITARY_DIVISOR_API.md` |
| Complete guide blob | `50793e90b56697a36a5b39c5fea44f3d61ef15c8` |
| Guide size | 26,983 UTF-8 bytes |
| Selected field | “Accepted prime premise”, literal selected list |
| New frozen input blob | `5cd2e9a7f4bc225db7a9a49ce90a44d79f11b5c3` |

The prior local input locator was unavailable. One native PR-files response supplied the complete added-file guide diff. Removing the diff's added-line prefixes and restoring its terminal newline produced the exact provider-reported Git blob. This is byte-level recovery, not recalculation of the old example. Only the literal selected list is consumed.

The guide identifies its upstream premise as #31426, `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json`, merge `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8`, blob `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd`, field `.snapshot.basis.primes[0..23]`. That complete prime basis was not recomputed or fetched anew for this consumer. Primality and the identity of the supplied prime list remain identified premises.

The old factorial valuation, unitary products, prefix products, queries and module were not executed. The new common denominator is the product of distinct primes, not 89!.

## 3. Mathematical representation and uniqueness

Let the supplied distinct primes be p₀,…,pₖ₋₁, and set

$
D=\prod_i p_i,\qquad w_i=D/p_i.
$

A subset I has reciprocal sum

$
s(I)=\frac{z(I)}D,\qquad z(I)=\sum_{i\in I}w_i.
$

All weights and half sums are exact integers. If two subsets have equal sums, multiply their equality by D and reduce modulo each pᵢ. Every term except the coefficient of D/pᵢ vanishes; that coefficient belongs to {−1,0,1}, while D/pᵢ is invertible modulo pᵢ. Therefore the two membership bits agree for every i. All full sums, and all sums within either half, are distinct.

This argument depends on the distinct-prime premise. The module checks basic shape and order, not primality. Supplying composite values is outside its mathematical contract even if the shape checks happen to pass.

Split the k indices at floor(k/2). Each half begins with the empty subset and doubles its rows when a new weight is added. A row stores its local mask and integer sum. After sorting each half by sum, every complete subset is represented by exactly one pair of rows. For k=24, two tables of 4,096 rows represent 4,096² complete subsets.

Actual common denominator:

```text
23768741896345550770650537601358310
```

Actual maximum numerator, attained by the full subset:

```text
42605658161771733665696611824842057
```

The saved construction includes all 24 weights, all 25 common-product prefixes, both complete sorted tables, input provenance and actual work counters.

## 4. Counts, ranks and selected witnesses

For a chosen condition, let L and R be the surviving sorted left and right rows. A bound x on the rational sum corresponds to an integer threshold z. The number of complete sums at most z/D is

$
C(z)=\sum_{i=0}^{|L|-1}\#\{j:L_i+R_j\le z\}.
$

As i increases, the largest admissible right index cannot increase. A single decreasing right pointer therefore counts the complete pair family in comparison work proportional to |L|+|R|. A requested frontier saves every left-row cutoff, including zero cutoffs after the pointer is exhausted, and both lists of original table indices.

For an inclusive rational interval [a/b,c/d], the integer bounds are

$
\ell=\left\lceil Da/b\right\rceil,\qquad
u=\left\lfloor Dc/d\right\rfloor.
$

The answer is C(u)−C(ℓ−1). Exact signed floor and ceiling handle bounds below zero. Intervals containing no possible integer numerator return zero.

Numerical rank is zero-based and refers to increasing reciprocal sum, not mask order. The rank of an identified subset is C(z−1). Selection bisects the exact integer range between the smallest and largest conditioned pair sums, seeking the least z with C(z)>r. Distinctness makes that z the unique selected value. The record retains every midpoint and count, followed by the two saved row identities.

A selected witness includes its 24-bit full mask, selected prime indices and values, cardinality, original half-row indices, numerator over D, reduced sum, and reduced gap 1−s(I). GCD reduction and two-row additions are fresh reader arithmetic; the reader does not regenerate all selected weights or half tables.

The target query asks whether s(I)=1−1/m for a supplied integer m≥2. Since that target is reduced with denominator m, m must divide D. If it does not, the query rejects immediately. Otherwise it searches for numerator D−D/m in the conditioned pair table. This is one finite membership query, not a classification of every possible m.

## 5. Required and excluded primes

Conditions use zero-based indices into the supplied prime list. A condition independently filters both halves by mask bits. The retained row order is unchanged, so the same count and selection methods apply. Duplicate indices are collapsed; required/excluded overlap gives an empty family.

The default includes all subsets. Fixing indices 0 and 1 as required and index 2 as excluded means requiring primes 2 and 3 while excluding 5. It leaves 512 left rows and all 4,096 right rows, or 2,097,152 complete subsets.

The reader caches at most 16 distinct normalized conditions. Each condition keeps at most 512 threshold counts, evicting the oldest when necessary. Exported condition records contain the surviving row indices and the currently retained threshold cache. Those exports are diagnostic saved outputs: `openIndex` reads the base snapshot and does not import a prior reader's caches.

## 6. Module and API

`reciprocal_subsets.cjs` is dependency-free CommonJS with no I/O. It exports:

| Export | Result |
| --- | --- |
| `compile(input)` | Complete serializable base snapshot |
| `openIndex(snapshot)` | Saved reader with `query(request)` and `stats()` |

Construction input:

```javascript
{
  primes: ["2", "3", "..."],
  provenance: { /* the actual identified source premise */ }
}
```

The list must contain 1–24 strictly increasing supplied primes, each at most 1,000,000. Decimal fields use canonical strings. Query integer strings are bounded to 2,048 characters. The source performs no primality tests; callers must supply the stated prime premise.

A rational is represented by `{n:"signed numerator",d:"positive denominator"}`. It need not arrive reduced. A condition is `{required:[indices],excluded:[indices]}`; both lists default to empty. Ranks are safe integer numbers, bounded by the selected family's size, which is at most 2²⁴.

| Operation | Request fields | Result |
| --- | --- | --- |
| `summary` | none | Input, count, exact maximum and construction counters |
| `half` | side 0 or 1; optional start, limit≤100 | Saved half rows |
| `family` | optional filter | Conditioned half lengths and full count |
| `range` | lower, upper rationals; optional filter, frontier | Inclusive count and two prefix records |
| `locate` | value rational; optional filter | Counts below/equal/above and an equality witness |
| `rank` | selected indices; optional filter | Rank and witness, or outside-filter disposition |
| `select` | rank; optional filter | Witness and complete integer bisection trace |
| `target` | m string; optional filter | Membership at 1−1/m or a bounded reason for absence |
| `conditions` | none | Complete currently cached condition records |

`half` defaults to start 0 and limit 20. A zero-length slice is allowed. Selecting from an empty family or outside the available rank range throws. `rank` identifies each supplied subset by its unique index set; repeated index entries do not add repeated prime terms.

Treat returned objects as read-only records. Serialize retained outputs if they must be independently mutated. Shape checks do not authenticate arbitrary external provenance or prove every saved arithmetic identity.

### Open the published snapshot

```javascript
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);
const reader = loaded.exports.openIndex(JSON.parse(indexText));

const nearby = reader.query({
  op: "range",
  lower: { n: "999", d: "1000" },
  upper: { n: "1", d: "1" },
  frontier: true
});
const chosen = reader.query({ op: "select", rank: 10262453 });
const rank = reader.query({ op: "rank", indices: chosen.indices });
```

The snapshot's source identities refer to the actual immutable construction. The JSON outputs are complete records, not a recipe to reconstruct lost query results.

## 7. What reopening checks

Opening parses saved decimal integers and verifies:

- supported schema, dimensions, supplied-prime ordering and count;
- canonical half split and complete declared subset counts;
- one occurrence of every local mask in each half;
- strict numerical half-row ordering;
- empty and full half endpoints;
- the saved maximum against the sum of the two full-half values.

It builds row-by-mask lookup arrays and loads 8,192 rows. It does not run the constructor, multiply the prime list again, recompute weights, regenerate half sums, sort the tables, verify primality, redo factorial valuations or reopen the old product module. Individual saved mask-to-sum identities and the prime source remain identified premises. Structural opening is not a second construction proof.

## 8. Actual construction and reader evidence

Only one construction was executed. Its source was frozen before execution, and both its source and input were banked before the run. The complete data snapshot was banked before the fresh reader opened it. Each of the 33 reader responses was individually retained and banked; the aggregate packet includes every request, response, rank comparison and final counter. There were no failed reader calls, unavailable responses or corrective reruns.

| Construction operation | Count |
| --- | ---: |
| Common-denominator multiplications | 24 |
| Weight divisions | 24 |
| Half-subset additions | 8,190 |
| Sort comparisons | 89,063 |
| Primality tests | 0 |
| Old factorial valuation work | 0 |
| Old product-table work | 0 |

### Actual finite counts

| Family or interval | Count |
| --- | ---: |
| All subsets | 16,777,216 |
| Sum below 1 | 10,262,454 |
| Sum equal to 1 | 0 |
| Sum above 1 | 6,514,762 |
| Sum in [999/1000,1] | 17,404 |
| Sum in [1,1001/1000] | 17,439 |
| Require 2,3; exclude 5 | 2,097,152 |
| That condition and sum in [999/1000,1001/1000] | 2,707 |
| Require and exclude prime 2 | 0 |

The nearest sum below 1 has global rank 10,262,453 and selected prime indices

```text
[0,3,5,7,8,9,10,11,12,13,16,20,22]
```

Its reduced sum and positive gap are

$
\frac{1667322045398221903}{1667322140323256326},
\qquad
\frac{94925034423}{1667322140323256326}.
$

The nearest sum above 1 has rank 10,262,454 and indices

```text
[0,2,5,7,8,11,12,13,18,19,22,23]
```

Its reduced sum and negative gap are

$
\frac{130220719006727003}{130220715148702490},
\qquad
-\frac{3858024513}{130220715148702490}.
$

These are exact nearest neighbors within this fixed finite family. They are not universal rational-approximation bounds.

Seven selections were followed by rank queries: global ranks 0, 16,777,215, 8,388,608, 1,234,567, 10,262,453 and 10,262,454, plus conditioned rank 1,048,576. All returned their original rank.

The actual target queries m=97, m=510510 and m=D were absent in this universe. The first fails the necessary denominator-divisibility condition; the latter two have no saved row pair at their target. No known primary-pseudoperfect example was recomputed as a separate test. A separate equality query at 1/3 found the singleton prime 3, at rank 750,408.

### Reader work, separate from construction

| Counter | Count |
| --- | ---: |
| Public queries | 33 |
| Rows loaded | 8,192 |
| Condition rows scanned | 4,096 |
| Conditions created | 3 |
| Condition cache hits | 24 |
| Threshold scans | 780 |
| Left rows visited during thresholds | 1,464,529 |
| Pair-sum comparisons | 4,203,106 |
| Threshold cache hits | 42 |
| Selection bisection steps | 805 |
| Pair-location steps | 50,206 |
| Witness pair additions | 15 |
| Rank pair additions | 7 |
| Returned witnesses | 15 |
| Threshold entries remaining across conditions | 628 |

The counters name selected algorithm operations; they are not a complete accounting of every integer addition, GCD step, rational scaling, allocation or serialization cost. Comparisons use arbitrary-precision arithmetic and are not constant-time bit operations. These observations are not a runtime benchmark or complexity improvement over prior literature.

The reader's construction and old-work counters are all zero. The memory reduction concerns representation of the family: it stores 8,192 half rows instead of 16,777,216 complete sums. Query work is still real arithmetic and is reported above.

## 9. Files and immutable identities

| File | Purpose | Git blob |
| --- | --- | --- |
| `reciprocal_subsets.cjs` | Constructor and saved reader | `aab865ee972f0dc33b2675cfc93c40e4341706af` |
| `primes89_reciprocal_index.json` | Complete base snapshot | `4e7757ed95695d0e273ebfceccbc34b091bf3273` |
| `saved_reader_queries.json` | All 33 reader outputs and counters | `8b30b4f495fbb3d2e2182e3d29a72ca3ed057215` |
| `RECIPROCAL_SUBSETS_API.md` | This guide | Bound by publication receipt |
| `README.md` | Entry point | Bound by publication receipt |

The index is 364,258 bytes and the complete reader packet is 511,826 bytes, each compact JSON with one terminal newline. Git identities bind exact bytes, not mathematical correctness or external source authenticity.

The package provides a finite reusable arithmetic interface. It neither searches all possible primes nor resolves Erdős 313's infinitude question.
