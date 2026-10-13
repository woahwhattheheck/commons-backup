# Exact interval product covers and saved family navigation

## Delivered result

For
\[
A=\{9,14,24,35,41,53,57,60\},\qquad
I=\{10^{12}+1,\ldots,10^{12}+60\},
\]
the minimum number of distinct interval elements whose product is divisible by
\[
P=\prod_{a\in A}a=786566894400
 =2^6 3^5 5^2 7^2\cdot19\cdot41\cdot53
\]
is **6**. There are **44** minimum subsets. Every minimum subset contains the elements at offsets **23, 37 and 50**.

The implementation retains the complete suffix and forward tables, all 44 minimum witnesses and all 60 participation counts. A fresh reader also answered queries for the interval with offset
\[
x'=10^{12}+P\,10^{50},
\]
using the same tables. That query produced a selected product with 372 digits. No target factorization, interval valuation or dynamic-programming table was recomputed by the reader.

This is an exact finite result for the stated input and its proved period translates. It is not a worst-case bound for all sets of this size or a resolution of the general question associated with Erdős problem 708.

| File | Content |
|---|---|
| [interval_product_cover.cjs](interval_product_cover.cjs) | Pure CommonJS/BigInt compiler and saved-index reader |
| [retained_set_interval60_cover.json](retained_set_interval60_cover.json) | Identified input premises, complete encoded tables, construction accounting and every reader response |
| [README.md](README.md) | Entry point and result summary |

The executed source has Git blob `c4c9fa37b0e08d5caa676ce33a37ab714da0a800`. The complete data file has Git blob `3f2cfd8bf2794b96cce0bfef224c7747cd7feee5`. The source was not changed after the consumer.

## Source and cardinality convention

The source is Paul Erdős, [“Some of my Forgotten Problems in Number Theory,” *Hardy–Ramanujan Journal* 15 (1992), 34–50](https://hrj.episciences.org/125/pdf), opening pages 34–35. It specifies increasing distinct integers \(1<a_1<\cdots<a_n\), an integer \(x\ge0\), and the positive interval \(x+1,\ldots,x+a_n\). It credits Erdős and Surányi, *Remarks on a problem of a mathematical competition*, *Mat. Lapok* 10 (1959), 39–48.

The original prose says to find \(g(n)\) integers. Its adjacent extracted formula is corrupt, and this package does not claim that “at most” is a verified literal quotation. Instead, the public interface defines a finite minimum and exposes separate at-most and exact-cardinality questions. That convention is sufficient for this computational task without deciding how a disputed or abbreviated global formulation should be interpreted. The bounded source lookup did not establish a current general bound or an exhaustive literature frontier.

For the API, let \(A\) be a nonempty set of distinct integers at least 2, set \(M=\max A\), and let \(x\ge0\) be an integer. A cover is a subset \(B\) of the **distinct** integers
\[
I_x=\{x+1,\ldots,x+M\}
\]
such that \(P=\prod A\) divides \(\prod B\). The minimum cardinality is denoted \(m(A,x)\). Repeated input records for \(A\) are deduplicated; they do not add extra factors to \(P\). The interval includes both displayed endpoints. Its values are positive, so no zero-product shortcut occurs.

A cover always exists. Because \(A\subseteq\{1,\ldots,M\}\), its product divides \(M!\), while
\[
\prod_{r=1}^{M}(x+r)=M!\binom{x+M}{M}.
\]
Thus the complete interval is a cover, and \(1\le m(A,x)\le M\). If \(m=m(A,x)\), a cover with **exactly** \(h\) members exists precisely when \(m\le h\le M\): add unused elements to any minimum cover. An **at-most** budget \(h\) succeeds precisely when \(m\le h\), including when \(h>M\). The API supplies counts for minimum covers only. Its padding operation produces one larger cover, not the count or complete family at that larger size.

## Identified input premises

The set is taken from the accepted finite artifact in Commons [#31157](https://github.com/woahwhattheheck/commons/pull/31157):

- Source path: `research/conjectures_erdos153_exact_values/n10_finite_premises.json`.
- Merge: `c8c12c19ba5733c7ad7314c6590c2135afad673f`.
- Blob: `60a1aabeb9b1e04e4dba9423ff0f57933d9e82ae`.
- Field: `search.minimizer_families[0].normalized_values`.
- Retained values: `[0,1,9,14,24,35,41,53,57,60]`; this consumer keeps precisely the values at least 2.

No property from the earlier additive-set search is needed to justify this product-cover calculation. That set supplies reproducible input selection; the original search was not rerun.

Factoring the small members of \(A\) uses the identified prime/least-factor basis from Commons [#31426](https://github.com/woahwhattheheck/commons/pull/31426):

- Source path: `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json`.
- Merge: `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8`.
- Blob: `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd`.
- Field: `snapshot.basis`, with `primes` and `least_factor_by_integer`.
- The source limit is 16,384; only the prefix through 60 is retained here. Entry 0 is 0 and entry 1 is 1.

The new operation performs 18 exact factor steps on \(A\). It does not regenerate the sieve, certify those supplied prime labels independently, or replay the earlier row computation. Every factor step is retained as `[before, prime, after]`. Correct interpretation of the prime coordinates is conditional on this explicitly identified source premise.

## Reduction to capped prime deficits

Write \(P=\prod_j p_j^{E_j}\). For an interval offset \(r\), retain
\[
v_{rj}=\min\bigl(v_{p_j}(x+r),E_j\bigr).
\]
For any selected subset \(B\), divisibility is equivalent to
\[
\sum_{x+r\in B}v_{rj}\ge E_j\quad\text{for every }j.
\]
Capping loses no information: exceeding a target exponent never needs to be distinguished from reaching it.

Only these target primes are used. The compiler does not attempt a complete factorization of the 60 large interval integers. For each target prime and candidate it retains the capped exponent, the quotient after those divisions, and a nonzero next remainder when the cap has not been reached. At the cap, `next_remainder` is null because no further valuation claim is required. In this input there were 525 remainder tests and 113 successful divisions.

A state is the remaining deficit vector \(d=(d_j)\), with \(0\le d_j\le E_j\). Selecting offset \(r\) changes it to
\[
\tau_r(d)_j=\max(0,d_j-v_{rj}).
\]
Mixed-radix coding uses the first prime as the fastest coordinate:
\[
\operatorname{code}(d)=\sum_j d_j\prod_{t<j}(E_t+1).
\]
Here the axes are primes \(2,3,5,7,19,41,53\), with exponents \(6,5,2,2,1,1,1\). There are
\[
7\cdot6\cdot3\cdot3\cdot2\cdot2\cdot2=3024
\]
states. The full deficit is code 3023; zero deficit is code 0.

Candidates with the same capped valuation vector share one transition map. This input uses 33 such patterns for 60 candidates. The cache changes the cost of preparing transitions, not the selected-subset semantics: different interval positions remain different choices even if their arithmetic profiles coincide.

## Complete minimum counts

Let \(D_i(d)\) be the minimum number of selected offsets from \(i+1,\ldots,M\) needed to discharge \(d\), after the first \(i\) offsets have been processed. Let \(R_i(d)\) count the subsets achieving that minimum.

At the terminal stage,
\[
D_M(0)=0,\quad R_M(0)=1,
\]
and every nonzero deficit is unreachable, with count zero. For \(i<M\), compare
\[
\text{skip}=D_{i+1}(d),\qquad
\text{take}=1+D_{i+1}(\tau_{i+1}(d)).
\]
Their minimum is \(D_i(d)\). The count \(R_i(d)\) is the sum of the child counts from exactly the branches attaining that minimum. Unreachable branches contribute zero. Include and exclude families are disjoint, so equal transition states do not create double counting.

Induction on the remaining interval proves that these rows cover every subset and count precisely every minimum subset. The reported answer is
\[
D_0(E)=6,\qquad R_0(E)=44.
\]
A product/quotient witness by itself establishes feasibility. The minimum and complete count rely on this exhaustive recurrence, its retained tables and the identified arithmetic premises.

The compiler also retains forward optimal-prefix counts \(F_i(d)\). It starts with one empty prefix at \(F_0(E)\) and propagates only along the suffix-optimal branches just described. Along such a path, the number already selected is \(D_0(E)-D_i(d)\), so a separate prefix-cardinality coordinate is unnecessary. Every globally minimum subset has one such path.

The number of minimum subsets containing offset \(i+1\) is
\[
\sum_{\substack{d:\ \text{include is optimal}}}
F_i(d)\,R_{i+1}(\tau_{i+1}(d)).
\]
Each product combines one prefix with one suffix, and different paths yield different subsets. As a construction invariant, the terminal forward count equals the root suffix count, and the sum of all participation counts equals \(mR_0(E)\). Here the latter is 264. A participation count of 44 means forced membership; zero means that the candidate occurs in no minimum cover.

Offsets 23 and 37 are the only candidates supplying primes 41 and 53, respectively. Offset 50 is also forced in the minimum family, but it is not the only multiple of 19: offsets 12 and 31 also supply that prime. Its forced status is the combined minimum-cover conclusion from the complete counts.

## Rank, select and witnesses

All ranks are zero-based. A subset is represented by its increasing list of interval offsets. Among fixed-cardinality increasing lists, the branch including the earliest available offset precedes the branch excluding it. Selection therefore uses the retained include-branch count to decide whether to descend into that branch or subtract its size and skip. Ranking adds those same skipped include-branch sizes.

The reader checks the local cost/count branch identity on each queried path. It does not enumerate all subsets to answer a rank or select request. The complete 44-row page was nevertheless exported for this particular small family, so every minimum solution has a retained explicit product witness.

| Rank | Selected offsets |
|---:|---|
| 0 | 2, 8, 23, 34, 37, 50 |
| 22 | 17, 23, 32, 34, 37, 50 |
| 43 | 23, 37, 41, 44, 48, 50 |

Every witness includes the selected integer values, their exact product, the integer quotient by \(P\), and the capped prime-coverage sums. For example, rank 0 has quotient
\[
1271347684823181645475882871075805218887945232336236521427063.
\]
Its capped sums equal the required exponents in every coordinate.

The saved exact-size-16 example starts from rank 22 and adds offsets 1 through 10. It records all 16 values and the exact product/quotient. This demonstrates padding and the distinction between minimum navigation and larger-cardinality feasibility.

## A proved period with a saved implementation

For each \(p^E\Vert P\), the capped valuation \(\min(v_p(y),E)\) depends only on \(y\bmod p^E\). Since \(p^E\) divides \(P\), replacing \(x\) by \(x+P\) preserves every candidate vector. Therefore every fixed subset of offsets has the same feasibility, and translation gives a bijection of the entire minimum families. Their costs, ranks and participation counts are unchanged.

Thus \(P\) is a valid offset period. No least-period claim is made. The saved reader accepts any nonnegative offset congruent to its original offset modulo \(P\), subject to its decimal-digit cap. A negative period multiplier is allowed if the resulting offset is still nonnegative.

A translated candidate response distinguishes the new value from its `origin_witness`. Quotients and remainders in that original witness are not mislabeled as fresh arithmetic for the translated value. Selected translated subsets do receive a newly calculated exact product and quotient. This fresh query arithmetic is separate from target factorization, valuation-table construction and dynamic programming.

The actual translated view used multiplier \(10^{50}\), returned minimum 6 and count 44, and selected rank 43. Ranking the resulting values returned 43. Its six-term product has 372 digits; the complete integer is retained in the data file.

## Public API

The module exports `compileIntervalProductCover`, `openRetainedIntervalProductCover` and `PRODUCT_COVER_LIMITS`. It has no I/O, dependencies or ambient runtime hooks. Supplied source and data texts can be used directly in a connected V8 context:

```js
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);
const artifact = JSON.parse(datasetText);
const index = loaded.exports.openRetainedIntervalProductCover(artifact.snapshot);

index.summary();
index.page(0, 44);                 // all 44 minimum witnesses
index.participationPage(0, 60);    // all interval positions
index.budget(16);                 // at-most and exact-size feasibility
index.padToSize(16, 22);          // one larger witness
const translated = index.viewAtOffset(
  (1000000000000n + 786566894400n * 10n ** 50n).toString()
);
translated.select(43);
```

These are ordinary public calls; the complete recorded responses are already in the artifact. Loading that artifact does not invoke the compiler.

For a genuinely new finite input, the compiler accepts:

```js
{
  values: [/* set entries, each between 2 and 64 */],
  offset: "canonical nonnegative decimal integer",
  factor_basis: {
    limit: 64,
    primes: [/* identified increasing prime premise */],
    least_factor_by_integer: [/* entries 0 through at least max(values) */],
    provenance: "source path, identity and field"
  }
}
```

The basis need not end at 64; supported source limits extend through 16,384. The compiler copies only the prefix required by this interval. Supplied labels, membership and exact factor steps receive structural checks, but these checks are not a replacement for the prime-source premise.

| Operation | Meaning |
|---|---|
| `summary()` / `count()` | Current interval, period, minimum and complete minimum-family count |
| `select(rank)` | One minimum subset with an exact product witness |
| `rank(values)` | Rank of a supplied minimum subset; values are normalized as a set |
| `page(start,count)` | Consecutive minimum ranks, at most 64 per call |
| `participationPage(start,count)` | Frequencies for zero-based pages of interval positions |
| `candidate(offset)` | One-based offset, view value, capped profile and original arithmetic witness |
| `budget(h)` | Separate at-most and exact-cardinality feasibility |
| `padToSize(h,rank)` | One minimum witness padded with the smallest unused offsets |
| `state(stage,deficits)` | Retained suffix minimum/count and forward optimal-prefix count |
| `viewAtOffset(x)` | Congruent nonnegative offset view using the same tables |
| `snapshot()` / `work()` | Detached retained source snapshot / current reader accounting |

Minimum ranks are decimal strings in returned JSON. Large integers accept BigInt, safe integer Numbers or canonical decimal strings; unsafe Numbers are refused. Returned objects are detached from the internal index. Different period views share the same reader counters.

## Persistence and execution bounds

The snapshot stores all 61 suffix and all 61 forward rows, each of length 3024. Runs are encoded with unsigned LEB128 integers and standard base64. A suffix run stores a positive run length, one cost byte and an exact unsigned count. A forward run stores a positive run length and an exact unsigned count. Cost 255 denotes unreachable; reachable costs are at most the interval length. Counts are BigInt throughout.

The loader requires complete row coverage, canonical encoding, valid dimensions, terminal and zero-deficit boundary rows, forward endpoints and consistent participation summaries. It performs structural and selected-path checks. It does not independently establish the source prime labels, authenticate the whole computation or reevaluate every recurrence. That distinction is recorded in both the API result and data provenance.

Hard limits are 64 interval elements, 256 input records before deduplication, 4096 deficit states, 80 decimal digits for an offset, 6000 digits for an explicitly multiplied product, 64 page rows, 8,000,000 snapshot characters and 100,000 encoded characters per row. Basis arrays have their own finite source bounds. A target exceeding the state cap is refused before the table construction. Empty input sets and entries below 2 are outside this contract.

Arithmetic indices and small factor steps stay in bounded exact Number ranges. Target products, interval values, subset counts and product witnesses use BigInt. If \(s\) is the number of target primes, \(N=\prod_j(E_j+1)\) is the state count and \(t\) is the number of distinct candidate profiles, transition preparation uses \(O(tNs)\) small-coordinate work, followed by \(O(MN)\) suffix work and bounded forward propagation. Full retained storage is \(O(MN)\) entries before run compression. No \(2^M\)-subset table is built.

## Recorded work and practical limits

| Activity | Recorded work |
|---|---:|
| Target factor steps | 18 |
| Candidate remainder tests / divisions | 525 / 113 |
| Shared transition profiles | 33 |
| Transition coordinate cells | 698,544 |
| Suffix state updates | 181,440 |
| Active forward states / edges | 757 / 800 |
| Marginal products | 135 |
| Encoded suffix cells / prefix cells | 184,464 / 184,464 |
| Fresh reader decoded runs | 86,628 |
| Fresh reader responses | 12 |
| Exported minimum witnesses | 44 |
| All reader product witnesses, including padding and translation | 46 |
| Reader product terms / local branch checks | 286 / 2,880 |
| Reader factor or DP constructions | 0 / 0 |

The unformatted snapshot occupies 395,683 characters. The complete formatted artifact is 586,661 bytes, including premises and every query result. In this observation compilation took 195 ms, the fresh load 103 ms and the query sequence 14 ms. These are individual observations, not a statistical benchmark.

One new compiler input and one fresh saved-reader load were executed. Other inputs, the larger caps and refusal branches were source-inspected rather than exercised in a synthetic suite. The artifact does not replay the accepted source search or sieve, the historical \(g(3)\) result, or another interval computation. Its finite optimum, complete family navigation and proved period reuse are the delivered scope.
