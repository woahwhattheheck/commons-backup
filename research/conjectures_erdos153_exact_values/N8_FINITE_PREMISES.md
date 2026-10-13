# Erdős 153: the eight-element finite premise

The new finite search gives

\[
\min_{\substack{A\subseteq\{0,\ldots,42\}\\|A|=8\\A\text{ Sidon}}}
\frac{1}{|A+A|}\sum_i(s_{i+1}-s_i)^2=\frac{11}{2},
\qquad A+A=\{s_1<\cdots<s_t\}.
\]

The computation supplies the finite premises for
`Erdos153.f 8 = 11 / 2` through the already-accepted
`Contribution.Erdos153Gaps.f_eq_of_search` interface. It is an exact finite
computational extension, not a new Lean elaboration receipt or an asymptotic result.

[The complete output](n8_finite_premises.json) retains the initial candidate,
full search accounting, energy histogram, all 32 minimizers, the first minimizer's
sumset and gaps, the cutoff calculation and the seven progress batches.
[The public implementation](sidon_gap_search.cjs) runs directly in a connected
JavaScript V8 context.

## Sources and conventions

The accepted reduction is in
[contribution d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b](https://github.com/conjectures-io/conjectures-contribution/tree/main/contributions/erdos-153/d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b),
script Git blob `546fb3a40683a5e33956262b2a46ca55bace0218`.
Its exact declaration signature and `gapEnergy` definition were read as the
interface consumed here. The preceding proof bodies and finite computations
were not rechecked.

The [formal problem source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/153.lean)
uses finite sets of natural numbers, permitting zero. The ordinary sumset
includes diagonal sums `a+a`. Sidon means that distinct unordered index pairs
give distinct sums, so an eight-element Sidon set has `t=36` sumset elements.
The energy divides by 36, with 35 consecutive gaps.

[Commons #16049](https://github.com/woahwhattheheck/commons/pull/16049) supplies
the accepted five-, six- and seven-element carrier rows. Their code, receipt and
results are preserved and were not run again. Original source and submission
ownership are retained.

The [canonical page](https://conjectures.io/problems/erdos153-erdos-153), observed
October 4, 2026, lists task
`fc-6a786f99-erdos153-erdos-153-b10f059e19-formalized-v1`,
commitment `27538820f3d70876a72e898f3be5611f2e9837883f6a7f217ab5c1d8ee764ac3`,
and source-type hash
`b35a9b51e1956e50dac187c15f5e0fd861c1ae3dcaaceb7941a1ce9bfd770316`.
These are a dated source observation, not a replacement for the historical pins
in the original carrier. The source intake found no exact value beyond seven
in the retrieved material; this is not a worldwide priority claim.

## The initial bound and the accepted cutoff

The explicit starting candidate is

\[
A_0=\{0,1,4,9,15,22,32,34\}.
\]

The public exact objective returns Sidon status, 36 distinct sums and squared-gap
sum 204, hence energy `204/36=17/3`. For `n=8`, the accepted cutoff condition is

\[
t(t-1)v\le4(D+1)^2.
\]

With `D=42` and `v=17/3`, the two sides are 7,140 and 7,396. This fixes a
sufficient finite search domain before the search begins.

The completed minimum is `v=11/2`. Its corresponding inequality is

\[
36\cdot35\cdot\frac{11}{2}=6930\le7396=4\cdot43^2.
\]

The output also stores the exact denominator-cleared comparison
`13860 <= 14792`. The original cutoff remains sufficient; no second scan at a
smaller cutoff was performed.

The accepted theorem requires `n>=2`, this cutoff inequality, the lower bound
for every Sidon `n`-set in the finite window, and one realizing Sidon set.
The new computation supplies exactly those numerical/combinatorial premises.
Turning them into a new checked Lean declaration remains a separate formal task.

## Exact finite coverage

The search visits increasing prefixes of sets. A prefix is Sidon exactly when
all its positive differences are distinct: a repeated difference gives an
unequal unordered-pair-sum collision, and such a collision gives a repeated
positive difference. Diagonal collisions are included in this equivalence.

On inserting a new largest value `x`, the new differences `x-a` are mutually
distinct. The implementation checks them against the existing difference flags.
A collision discards only an already-invalid prefix. Every extension of that
prefix has the same collision.

If the rejected prefix has length `k`, the number of full `n`-subsets it represents
is exactly

\[
\binom{D-x}{n-k}.
\]

These discarded subtrees are disjoint because a full non-Sidon set has one first
rejected prefix in the traversal. Valid full leaves are evaluated individually.
At completion the code requires the sum of those two counts to equal the full
binomial domain.

| Quantity | Exact observed value |
| --- | ---: |
| Full domain `C(43,8)` | 145,008,513 |
| Prefix-extension attempts | 6,537,676 |
| Rejected prefixes | 5,113,226 |
| Full non-Sidon subsets covered by rejected prefixes | 144,997,603 |
| Sidon sets evaluated | 10,910 |
| Accounted subsets | 145,008,513 |
| Distinct squared-gap totals in the histogram | 140 |
| Minimum squared-gap total | 198 |
| Minimum energy | 11/2 |
| Minimizers retained | 32 |

This is one complete traversal, advanced in seven batches with a limit of one
million extension attempts each. A batch continues the same in-memory traversal.
It does not restart or recalculate the preceding cases.

For Sidon leaves the denominator is constant, so comparing integer squared-gap
totals compares the energies exactly. Search coordinates lie in `[0,512]` at the
API limit; all search sums and squared-gap totals are therefore safe integers.
Combinatorial counts use `BigInt`. The separate public objective uses `BigInt`
for the full sumset, gaps and rational value.

## Minimizers

All 32 minimizing sets in this finite window are the following four rows,
translated by each integer `u=0,1,...,7`:

| Normalized row | Values |
| --- | --- |
| 1 | `{0,2,5,16,22,23,31,35}` |
| 2 | `{0,2,10,11,16,28,31,35}` |
| 3 | `{0,4,7,19,24,25,33,35}` |
| 4 | `{0,4,12,13,19,30,33,35}` |

The JSON includes all 32 expanded sets in traversal order, with no truncation.
The first row's public-objective call returns its full 36-element
sumset and 35 gaps, with squared-gap total 198 and reduced energy `11/2`.
Here “public-objective call” identifies the API operation; it is not an external
review or a formal-kernel claim.

## Public API

The module has no imports, I/O, process, network or host-specific dependencies.
It exports `evaluateSidonGapSet`, `createSidonGapSearch` and `limits`.

### `evaluateSidonGapSet(values)`

Supply 2 through 256 distinct natural numbers in an array. Each item may be a
BigInt, a safe integer number, or a canonical decimal integer string. Negative
values and duplicates are rejected. Canonical strings allow `"0"` and ordinary
decimal digits with an optional minus sign before a nonzero leading digit;
negative parsed values are then rejected by the natural-number contract.
Leading zeroes, plus signs, whitespace, fractions, exponents and `"-0"` are
invalid. Numeric negative zero becomes zero.

The function sorts a copy. A Sidon result includes the sorted values, full
diagonal-inclusive sumset, gaps, squared-gap sum and reduced rational energy.
A `NOT_SIDON` result gives two distinct unordered index pairs with the same sum.
Those indices refer to the returned sorted values, and a diagonal pair repeats
its index. All objective values, sums, gaps and rational parts are decimal strings.

Invalid shapes or integer representations cause `TypeError`. Invalid cardinality,
negative values or repeated elements cause `RangeError`. Integer digit length
continues to affect BigInt work; the cardinality bound is not a uniform time bound.

### `createSidonGapSearch(options)`

Required safe-integer options are `n` and `cutoff`. Optional
`max_saved_minimizers` controls output retention.

| Limit | Value |
| --- | ---: |
| Search cardinality | 2 through 12 |
| Cutoff | 0 through 512 |
| Extension attempts per `advance` call | 1 through 1,000,000 |
| Default saved-minimizer limit | 4,096 |
| Largest saved-minimizer limit | 65,536 |

Unknown option keys cause `TypeError`; invalid ranges cause `RangeError`.
The result is an object exposing `advance(budget)` and `describe()`.
Both return fresh JSON-safe snapshots; `describe` performs no traversal.

`IN_PROGRESS` reports a partial traversal and may have only an incumbent.
`COMPLETE` reports the finished finite domain. If no Sidon set exists in the
chosen window, the minimum is `null`. If the saved-minimizer limit is reached,
the total minimizer count remains exact while `minimizers_truncated` is true.
A completed value and a complete minimizer list are distinct output properties.

Counts and exact rational parts are decimal strings. Bounded cardinalities,
depths, cutoffs and minimizing-set elements are ordinary safe integer numbers.
The energy histogram gives each integer squared-gap sum and its exact count.

Continue by calling `advance` on the same search object. Snapshots are output
data, not serialized restore tokens; this API does not accept an external search
state or independently authenticate a caller's saved result. Each call has a
count bound, not a wall-clock guarantee.

## Connected runtime use

Read the complete module source through the connected repository reader and
evaluate it in one JavaScript context:

```javascript
const moduleBox = {exports: {}};
new Function("module", "exports", completeSource)(
  moduleBox,
  moduleBox.exports
);
const search = moduleBox.exports.createSidonGapSearch({n: 8, cutoff: 42});
let result;
for (let round = 0; round < 8; round += 1) {
  result = search.advance(1000000);
  if (result.status === "COMPLETE") break;
}
text(result);
```

An ordinary CommonJS host can use `require("./sidon_gap_search.cjs")`.
The retained JSON already contains the completed eight-element result; callers
who only need that result can consume it directly.

This delivery adds no new Lean file, native workflow, sponsor submission or
claim that `f(n)` tends to infinity. The numerical equality proposed for `f(8)`
is bounded by the stated finite computation and accepted reduction.
