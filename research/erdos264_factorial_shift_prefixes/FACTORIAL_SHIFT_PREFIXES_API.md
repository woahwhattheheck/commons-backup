# Factorial-shift prefix and enclosure navigator

This package studies the positive-index series
\[
\sum_{n\ge1}\frac{1}{n!+b_n}
\]
under one explicit restricted model: b_1=1; b_n is either 1 or 2 for n=2,...,24; b_n=2 for n=25,...,48; and every later b_n is independently either 1 or 2.

It represents **8,388,608 finite prefixes** through n=48 without enumerating them. Every infinite continuation in this alphabet lies in its prefix's exact rational enclosure. All these enclosures are disjoint. This does not mean that every point of an enclosure is attained, and it does not establish irrationality of any or all continuations.

## Source convention and scope

Kovač and Tao, *On several irrationality problems for Ahmes series*, arXiv:2406.17593v4 (14 July 2025), Acta Mathematica Hungarica 175 (2025), 572–608, define Type 3 irrationality sequences using **additive** bounded integer shifts in [§2.1.3](https://arxiv.org/html/2406.17593v4#S2.SS1.SSS3). Their positive-index convention starts at n=1. It requires every shift and every shifted denominator to be nonzero. Negative shifts are permitted subject to these exclusions; restricting to positive shifts is a narrower model. Footnote 3 explicitly says that the nonzero-shift requirement was not stated in the cited original sources and is added there to make the power-of-two question meaningful. That convention is credited to Kovač–Tao and the formal source, not represented as a literal original Erdős statement.

The fully read [FormalConjectures Erdős 264 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/264.lean) had observed blob 4d26bcf33756075c26e76a424e3866bdeb53eb17, 3452 UTF-8 bytes, from the contents endpoint without an explicit ref. Its factorial variant has a research-open annotation and local placeholder. The power-of-two counterexample and other variants have separate solved annotations and placeholders. No proof was executed or independently reviewed.

The formal sum is indexed over the naturals, while this API deliberately adopts the primary paper's n>=1 convention. No zero-th summand is imported or silently identified. The actual alphabet {1,2} is much narrower than all bounded nonzero integer perturbations. Prefix counts, gap certificates and tail enclosures do not settle the universal irrationality assertion.

## Exact input lineage

The only reused numerical data are factorials 1! through 49! from released [Commons #31740](https://github.com/woahwhattheheck/commons/pull/31740):

- Immutable commit fe60096bb154e555893d6c89e166363dbd492fd9.
- Path research/erdos252_factorial_series_enclosures/k5_cutoff128_index.json.
- Blob 9f72f44c3df1c0e14f7210e08e53e6f2fa7890df.
- Consumed field: factorials[1..49], copied literally into this new input.

No divisor-power rows, previous series queries, factorial recurrence or prior irrationality argument was reused as a new computation. The factorial values are explicit identified premises. The new constructor checks their encoding, consecutive row labels, positivity and the first value 1!=1; it does not replay their factorial recurrence.

The new source and input were banked before the one production call:

| Item | Blob | Bytes |
|---|---|---:|
| Source | a15b9c669a6d7c24d20e54cfb67ee948e6d781b2 | 11027 |
| Input | 5a71a69583abc4553987734312ac5b6b71c5ef82 | 4310 |
| Complete index | 367ce2ab98a95405b813b58286d680f19231ac56 | 168728 |
| Complete reader packet | 6b8c6bfc3d6c6d1cad290638f2f42d9577daf2dc | 684816 |

Generic bounds are cutoff M in 2..128 and variable end K in 2..min(M,48). The actual values M=48 and K=24 were fixed before execution. Input integer strings and query rational components are capped at 100000 characters. The reader caps radix requests at 256 fractional places and pages at 32 records.

## Common denominator and binary prefix weights

Write F_n=n!. Use the all-two choice at variable positions as the finite baseline:
\[
P_0=\frac12+\sum_{n=2}^{M}\frac1{F_n+2}.
\]
Changing a variable shift from 2 to 1 adds
\[
w_n=\frac1{F_n+1}-\frac1{F_n+2}
=\frac1{(F_n+1)(F_n+2)}.
\]

The constructor forms a common denominator D as the lcm of 2, every F_n+2 for 2<=n<=M, and every F_n+1 for 2<=n<=K. Consecutive F_n+1 and F_n+2 are coprime, so their product divides D. Exact quotient guards retain this condition. The baseline numerator B and integer weights W_n=D w_n then give each finite prefix as
\[
P_\varepsilon=\frac{B+\sum_{n=2}^{K}\varepsilon_n W_n}{D},
\qquad \varepsilon_n=0\ \text{for }b_n=2,\quad
\varepsilon_n=1\ \text{for }b_n=1.
\]
No prefix family is enumerated. The actual common denominator has 1446 decimal digits; its complete value and all integer weights are saved.

Suffix sums and margins are retained:
\[
T_i^{\mathrm{weights}}=\sum_{j>i}W_j,\qquad
m_i=W_i-T_i^{\mathrm{weights}}.
\]
The constructor checks each m_i>0 using the new exact integer weights. Consequently the weights are superincreasing, every bit vector gives a different finite prefix, and numeric prefix order is ordinary lexicographic bit order with 0 before 1, starting from n=2.

A short factorial explanation is also available: for n>=2 and F=n!>=2,
\[
\frac{w_{n+1}}{w_n}
=\frac{(F+1)(F+2)}{((n+1)F+1)((n+1)F+2)}
<\frac{3}{(n+1)^2}\le\frac13.
\]
Here (F+1)(F+2)<=3F^2 follows from (2F+1)(F-2)>=0. Thus later weights cannot cancel an earlier one. The production certificate nevertheless retains each actual finite margin, rather than relying on a rounded estimate.

## Uniform tail enclosure

For every allowed continuation, the terms after M are positive and
\[
0<\sum_{n>M}\frac1{n!+b_n}
<\sum_{n>M}\frac1{n!}
\le \frac{1}{(M+1)!}\frac{1}{1-1/(M+2)}
=\frac{M+2}{(M+1)(M+1)!}.
\]
The factorial ratio after the first omitted term is at most 1/(M+2). This bound uses the already supplied (M+1)! as an input, not a recomputed factorial.

The saved API uses the conservative **closed** interval
\[
I_\varepsilon=[P_\varepsilon,P_\varepsilon+U_M].
\]
The endpoints are bounds; in particular the lower endpoint is not an attained infinite sum in this positive-tail model. An enclosure hit is not an existence proof for an exact real value.

For M=48 the retained upper tail bound reduces to
\[
U_{48}=
\frac1{596116226753582209654807120054869469349801774751626035200000000}.
\]

When binary rank increments, a zero bit at position i changes to one and all following one bits change to zero. The finite-prefix increment is exactly m_i/D. That carry type occurs 2^i times, since all earlier bits are free. There are 23 saved gap types, with multiplicities summing to 2^23-1.

The constructor computes the corresponding enclosure gap
\[
m_i/D-U_M
\]
for every type. All 23 are strictly positive in this actual input, proving that all 8,388,608 enclosures are pairwise disjoint. The generic API records whether this check succeeds; it does not silently assume disjointness at every supported M,K.

The one construction performed 71 lcm updates, 23 exact weight quotients, 48 baseline terms, 23 suffix additions, 23 margin rows and 23 gap-type rows. It performed zero factorial recurrence steps and enumerated zero prefixes.

## Saved-reader API

The module exports compile(input) and openIndex(saved). The actual fresh reader used only the banked saved index. Opening clones the input and checks shape, row labels and integer/rational encodings. It trusts the identified saved margins, blocks and arithmetic certificate; it does not rebuild or independently re-prove them.

The reader exposes query(request) and work(). Rank and all large integers are decimal strings. Ranks run from 0 to 8388607 in this input. A complete choice array lists b_2,...,b_24, each entry 1 or 2. A leading choice block may be shorter.

| Operation | Result |
|---|---|
| summary | Model, family size, endpoint prefixes, tail bound, disjointness and saved construction counters |
| select | Rank to bit vector, complete shift choices, exact finite prefix and tail enclosure |
| rank | Complete shift choices to the inverse numeric-prefix rank |
| weight | One variable's exact integer weight, suffix margin and gap type |
| gap_types | All saved carry-gap fractions and their multiplicities |
| gap | Rank and next rank, both enclosures, and their saved carry-gap witness |
| count | Number of finite prefix values <= a rational threshold, or < it when strict:true |
| window | Prefix values inside a closed rational window, or enclosures intersecting it when intersects:true |
| locate | Enclosures containing one rational point, with first/last records if any |
| block | A leading shift-choice block, its consecutive rank interval, size and outer span |
| page | Up to 32 consecutive rank records |
| digits | A radix prefix shared by every allowed tail for one selected prefix, or undecided |

A rational is an object with signed decimal numerator and positive decimal denominator. For count and locate these two fields are directly on the request. Window uses lower and upper rational objects. The outer span returned by block may include internal gaps; it is not a claim that all span points occur.

Counting uses the saved superincreasing weights. At a position, if the remaining integer threshold is below zero, no suffix is counted; if it reaches the saved suffix sum, the entire block is counted. Otherwise a threshold at least the current weight admits every low-branch suffix and continues down the high branch; a smaller threshold continues only down low. Thus a count visits at most the number of variable positions and never scans all prefixes.

Rational thresholds are converted exactly to integer numerator cutoffs. Non-strict counting uses floor((aD-Bb)/b); strict counting uses floor((aD-Bb-1)/b), since aD-Bb is integral. Signed floor division is implemented explicitly rather than using BigInt's truncation toward zero.

For a closed window [a,b], finite prefixes inside it are counted by count_le(b)-count_lt(a). Enclosures intersecting it are counted by count_le(b)-count_lt(a-U_M). These are counts of prefix records/enclosures; for a generic overlapping case they are not a deduplicated count of real points.

The digits operation scales both interval endpoints by base^places and compares their floors. Equal floors certify the same **truncated**, not rounded, radix prefix for every allowed continuation. Unequal floors return undecided. It never chooses a tail or asserts that an arbitrary point in the interval occurs.

Example consumer syntax, provided for users and not another execution here:

```javascript
const fs = require('node:fs');
const { openIndex } = require('./factorial_shift_prefixes.cjs');
const saved = JSON.parse(fs.readFileSync('cutoff48_variable24_index.json','utf8'));
const reader = openIndex(saved);
reader.query({op:'select', rank:'3141592'});
reader.query({op:'count', numerator:'1', denominator:'1'});
reader.query({op:'digits', rank:'3141592', base:10, places:40});
```

## Actual first reader use

All 44 actual requests and complete responses were stored individually before the next query and then banked as one packet. There was no failed query, lost output or continuation repair.

Six select/rank inverse pairs match at ranks 0, 1, 3141592, 4194304, 8388606 and 8388607. Three independently requested strict/non-strict threshold pairs at selected exact finite prefixes give respectively rank and rank+1. Exactly 4,194,304 finite prefix values are <=1; this count is explicitly about finite prefix values.

The reader retains three adjacent-gap witnesses and a rational point strictly inside the central certified gap, for which locate returns zero enclosures. A window from the left enclosure's upper endpoint to the right enclosure's lower endpoint intersects two closed enclosures at its endpoints, while containing only the right finite prefix. The selected rank-3141592 enclosure's midpoint and lower endpoint each locate that one enclosure. These examples preserve the difference between containment in a bounding interval and attainability as an infinite sum.

The leading shift block [1,2,1,2] contains 524288 prefixes, ranks 5242880 through 5767167. Its outer span query intersects exactly those 524288 enclosures. First and last four-record pages are retained.

Three selected decimal requests certify 40 fractional places, uniformly for every allowed tail:

| Rank | Certified truncated prefix |
|---:|---|
| 0 | 0.9232694942782664154010022804979422336518 |
| 3141592 | 0.9411963396015359486247856342823618826776 |
| 8388607 | 1.0260681344733308247780472251624384054497 |

All three 80-place decimal requests are undecided. Rank 3141592 also certifies 128 binary fractional places. These are finite enclosure outputs, not irrationality evidence.

Fresh reader arithmetic is reported without hiding it as free lookup:

| Reader work | Count |
|---|---:|
| Queries | 44 |
| Selected bit visits | 713 |
| Selected weight additions | 373 |
| Rank/leading-block bits read | 142 |
| Threshold count steps | 268 |
| Exact threshold floor divisions | 21 |
| Query rational reductions | 98 |
| New radix powers | 7 |
| Radix floor divisions | 14 |
| New factorial steps, lcm updates, weights, suffix sums, gap types | 0 each |

Two query inputs were newly formed as exact rational midpoints of retained response endpoints. Their preparation is separately recorded: each used four integer multiplications and one addition, with no reduction required before the request. This is fresh query-input arithmetic, not part of the saved construction and not a repeated query.

## Files, custody and limits

The five files are factorial_shift_prefixes.cjs, this guide, cutoff48_variable24_index.json, saved_reader_queries.json and README.md. The complete index contains all 49 copied factorial premises, the 1446-digit common denominator, baseline, every weight/suffix/margin/block row, all 23 gap types and the exact tail bound. No hidden table or earlier calculation is required by the reader.

Bounded exact-number Slack, all-state PR and code checks returned empty before activity. That is coordination evidence, not a guarantee of global uniqueness or exclusive authority. Publication checks bind native file identities and recorded outputs; they do not assert deployment, external acceptance or formal verification.

Every selected prefix represents a class of infinitely many allowed continuations. The finite record count is not a count of all infinite sequences. Disjoint enclosures distinguish those prefix classes but do not make the classes singletons. The general problem quantifies over every bounded nonzero integer perturbation, including alphabets and signs outside this API. No universal irrationality conclusion, solution claim, novelty priority or prize result follows from this finite construction.
