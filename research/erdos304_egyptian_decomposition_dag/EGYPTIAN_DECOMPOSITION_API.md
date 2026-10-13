# Exact finite Egyptian-fraction decomposition DAG

This package completely indexes representations of **7/19** by exactly one through four distinct unit fractions, with denominators greater than one and **no denominator cap**.

| Exact number of terms | Complete representation count |
|---:|---:|
| 1 | 0 |
| 2 | 0 |
| 3 | 5 |
| 4 | 202 |

The minimum number of terms for this supplied rational is therefore **three**. This is a statement about 7/19, not the worst case over all numerators with denominator 19 or an asymptotic upper bound.

All five minimal representations are:
```
[3, 29, 1653]
[3, 30, 570]
[3, 33, 209]
[3, 38, 114]
[5, 6, 570]
```
Each list means the sum of reciprocal denominators. The full 202 four-term representations are also exported by the saved reader. The first and last in numeric-denominator lexicographic order are [3,29,1654,2734062] and [6,7,17,13566].

## Source conventions and limitations

Gérald Tenenbaum and Hisashi Yokota, *Length and Denominators of Egyptian Fractions, III*, Journal of Number Theory 35 (1990), 150–156, [author-hosted PDF](https://tenenb.perso.math.cnrs.fr/PPP/Egyptian.pdf), take positive proper rationals and strictly increasing positive denominators. Their introduction distinguishes minimizing the number of terms from minimizing the largest denominator; its minima range over all admissible expansions. These are separate objectives. The displayed reciprocal equality was omitted by the text extraction, so the exact equality and denominator-greater-than-one contract here are bound to the completely read formal source below. Denominator one is also incompatible with a positive proper rational represented by positive unit terms.

The paper cites Vose's *Egyptian fractions*, Bull. London Math. Soc. 17 (1985), 21–24. Vose's metadata was identified, but his full text was not read. No algorithm, proof, numerical example or table from either paper is imported or replayed.

The [FormalConjectures Erdős 304 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/304.lean) was fully read through the contents API without an explicit ref. Its observed independent UTF-8 blob is `b42723cefd917f23410555bdc94bcdbf260ca6c8` (7,207 bytes). It requires a finite set of denominators strictly greater than one, defines the minimum term count N(a,b), and then takes the worst case over 1≤a<b. It records the log-log upper-bound question as research open and earlier upper/lower bounds as solved, with local placeholders. Its embedded proofs/examples and linked external proof were not executed or audited.

The present 7/19 result is a new finite API consumer, not a replay of the formal source's 2/15 example. It computes no N(b) worst case, proves no asymptotic upper bound, supplies no greedy algorithm claim and makes no prize or novelty assertion. The proper-positive input restriction also avoids importing the formal library's totalized division-by-zero conventions.

## Frozen input

The new request was banked before production with blob `dc52f3d360fa56dd36121f6dab92482f8f18c3b2`, 832 bytes:
```json
{
  "numerator": "7",
  "denominator": "19",
  "max_terms": 4,
  "min_denominator": "2",
  "limits": {
    "max_input_denominator": 1000,
    "max_terms": 5,
    "max_nodes": 20000,
    "max_prefix_candidates": 100000,
    "max_trial_divisions": 500000,
    "max_divisor_cells": 1000000,
    "max_two_term_candidates": 200000
  },
  "provenance": {
    "input": "New explicitly supplied proper rational; no published numerical example imported.",
    "formal_blob": "b42723cefd917f23410555bdc94bcdbf260ca6c8",
    "primary": "https://tenenb.perso.math.cnrs.fr/PPP/Egyptian.pdf",
    "conventions": "Tenenbaum–Yokota length versus largest-denominator objectives; Formal304 exact distinct-unit-fraction sum and denominators>1.",
    "scope": "Complete finite exact-term families1..4, no denominator cap; no asymptotic bound."
  }
}
```

The denominator input cap of 1,000 bounds the supplied rational's denominator, not any denominator in its expansions. The actual maximum term count is four; the generic source accepts up to five. Work caps abort on exhaustion and never silently truncate a family.

## Complete finite search argument

A state contains a positive reduced residual a/b, a minimum permitted next denominator d and an exact remaining term count r. All denominators must increase strictly.

With one term, the only possible denominator is b/a. The state is accepted exactly when this is an integer at least d.

With at least two terms, positivity of all remaining terms implies 1/x < a/b for the first denominator x. Also all r unit terms are at most 1/x, so a/b ≤ r/x. Consequently every possible x lies in the finite necessary range
`max(d, floor(b/a)+1) ≤ x ≤ floor(r·b/a)`.
Keeping the upper endpoint is harmless even where strict distinctness makes equality impossible. If this range is empty, the state has no representation.

For r≥3, the compiler visits every x in this entire range and recurses on the exactly reduced residual
`(a·x−b)/(b·x)`
with minimum x+1 and r−1 remaining terms. It retains every candidate, including children of count zero. The lower bound makes the residual numerator positive. Each increasing representation has exactly one first denominator and hence exactly one recursive branch.

For r=2, the exact equation
`a/b = 1/x + 1/y`
is equivalent to
`(a·x−b)(a·y−b)=b²`.
Both factors are positive; x<y is equivalent to the first factor t being less than b. Thus it suffices to consider every positive divisor t of b² with t<b, set
`x=(b+t)/a` and `y=(b+b²/t)/a`,
and require integral denominators with d≤x<y. Every two-term representation occurs once, and every accepted divisor yields one.

The source factors b once per distinct denominator, doubles the prime exponents to generate the complete divisor set of b², and stores all of it. It records every t<b candidate's complementary factor, integrality remainders, resulting denominators when integral and acceptance/rejection reason. Factors t≥b are excluded by the proved strict-order criterion, not a heuristic cutoff.

Induction on r therefore establishes completeness for every saved root within the successful run. No arbitrary largest-denominator bound is used. The zero counts for one and two terms, together with a nonempty three-term root, establish the exact minimum for this rational.

## Saved state and branch representation

Nodes are keyed by the reduced residual, minimum denominator and remaining term count. Children have fewer terms and are stored before parents. Memoization is available; this actual run had zero memo hits. It is not claimed to have achieved sharing that did not occur.

Each node retains:
- a, b, minimum denominator and remaining terms;
- the necessary first-denominator range, where applicable;
- all candidate and rejection records;
- accepted branches, with one leading denominator for a recursive branch or the full final one/two denominators at a terminal branch;
- complete cumulative branch counts and the total count.

Every denominator and count is an exact decimal BigInt string. Branches are ordered by increasing first denominator. Fixed-length representation tuples consequently have ordinary lexicographic order using numeric denominator comparison; they are not ordered by the largest denominator, string comparison or sum of denominators.

The factorization cache retains complete prime-exponent records and the sorted divisor list of each squared residual denominator. It is newly computed production data, not an imported table or a revalidation of an earlier prime source.

## Bounded production and work

Input validation occurs before search: 0<a<b≤1000, canonical decimal inputs, minimum denominator exactly two and 1≤K≤5. The exact request caps are 20,000 states, 100,000 prefix candidates, 500,000 factor trial divisions, 1,000,000 divisor cells and 200,000 final-two candidates. Arithmetic is exact; no floating-point residual or rounding decides a branch.

Actual once-only work:
| Item | Count |
|---|---:|
| States / retained nodes | 125 / 125 |
| Memo hits | 0 |
| GCD remainder steps | 605 |
| Prefix candidates | 121 |
| One-term decisions | 1 |
| Final-two candidates / accepted pairs | 3,270 / 207 |
| Cached factorizations / cache hits | 86 / 22 |
| Factor trial divisions | 744 |
| Exact factor divisions | 252 |
| Complete squared-denominator divisor cells | 5,310 |
| Divisor power products | 676 |
| Accepted branch-prefix additions | 247 |
| Replayed old input calculations | 0 |

The four roots have node IDs 0, 1, 8 and 124. The total across the four exact-term families is 207. Each term count is a separate family. The source did not enumerate all full tuples during construction; it formed the bounded search states, final-two choices and branch counts. A later reader explicitly exported the requested full families.

No cap was reached, no constructor/query failed, and no output was lost. A capped future invocation throws and does not establish completeness.

## Files, shards and exact assembly

The complete original snapshot is 1062274 bytes with Git blob `e9bb4b942d5f079184cf35f76090167f50af4b26`. The manifest retains all 86 factorization/divisor caches, roots, frozen input, counts and work. Its `nodes` field is null, and five complete node shards supply IDs 0–124.

| Shard | IDs | Git blob |
|---|---|---|
| nodes_00.json | 0–24 | 7d79d71f768706d335b445b18f38ddb90cac78b4 |
| nodes_01.json | 25–49 | 06ceff80de90ca91299875611bd5626331d47912 |
| nodes_02.json | 50–74 | b8a6bd44606ad5844fb85863f6cff9e20766126e |
| nodes_03.json | 75–99 | 3dac2ed1ef53cab70000d633e828ff0e96e26f10 |
| nodes_04.json | 100–124 | 4bed5af5cda8d54aee5c0180b3ae96b98f254060 |

Replacing the manifest's null field with the concatenated shard arrays reproduces the complete original serialization byte-for-byte and the same independent Git blob identity. This is data assembly only; no residual, factor, divisor, branch or count computation is replayed.

```js
const fs = require("node:fs");
const { openIndex } = require("./egyptian_decomposition_dag.cjs");
const read = name => JSON.parse(fs.readFileSync(name, "utf8"));
const manifest = read("snapshot_manifest.json");
const nodes = manifest.node_shards.flatMap(row => read(row.path).nodes);
const reader = openIndex({ ...manifest.snapshot, nodes });
reader.query({ op: "family", terms: 3 });
reader.query({ op: "page", terms: 3, offset: "0", limit: 128 });
reader.query({ op: "prefix", terms: 4, denominators: ["3","29"] });
```

Opening checks node IDs, child order and remaining-term decrement, positive denominator shapes and stored prefix order. It parses saved counts but does not recalculate residuals, factorization, divisor completeness or prefix sums. These structural checks are not a theorem checker for arbitrary untrusted payloads.

## Reader contract

The term count must be specified for family, rank, selection, prefix and page queries. Ranks are zero-based decimal strings. Denominator inputs are canonical decimal strings in strictly increasing numeric order. Counts refer to distinct tuples, so permutations or repeated denominators do not create additional representations.

| Operation | Result |
|---|---|
| summary | Input, reduced target, all roots, exact minimum found, total and production work. |
| family | Saved root and count for one exact term count. |
| select | A rank's complete tuple and saved branch path. |
| rank | Member status and rank of a full increasing tuple, with saved path if accepted. |
| prefix | Completion count and first global rank of an increasing prefix; may expose a forced suffix inside a saved terminal branch. |
| page | At most 128 consecutive tuples, plus next rank cursor. |
| node | Complete saved positive/negative branch record by ID. |
| factorization | Complete cached factor and divisor record by ID. |

A prefix's completions form one contiguous rank interval in the fixed-length lexicographic order. An empty prefix returns the full family. A prefix that matches no branch returns zero; it is not silently normalized to a different tuple. Prefix rank is measured in the whole exact-term family, not a new local ranking.

The reader performs navigation and stored-count arithmetic. It does not recompute any reciprocal sums, residual fractions, gcds, factorizations or divisors. A returned saved branch path provides the identified production evidence for the tuple.

## Actual fresh reader

All **36 responses** were banked individually and are retained in `saved_reader_queries.json`. They include all five three-term representations, all 202 four-term representations in two pages, six exact select/rank inverse matches, eight prefix queries, a nonmember and complete positive/negative node and factor records.

Representative prefix counts in the four-term family:
| Prefix | Completions | First global rank |
|---|---:|---:|
| empty | 202 | 0 |
| [3] | 134 | 0 |
| [4] | 23 | 134 |
| [2] | 0 | none |
| [3,29] | 13 | 0 |
| [3,29,1654] | 1 | 0 |

The last prefix has forced final denominator 2734062. In the three-term family, [3,29] has forced final denominator 1653. The queried increasing tuple [3,38,115] is not a member; this result came from saved branch matching, not a fresh sum calculation.

Fresh reader work is 2,323 branch comparisons, 631 selection-node visits, 17 rank-node visits, 13 prefix-node visits, five complete node reads, two factorization reads and 27 stored-rank additions. New residual arithmetic, gcd, factorization, divisor construction and constructor nodes all have count zero. Full tuple export is explicitly reader work and is not described as zero enumeration.

## Provenance boundary

Production source: `240f4affe8d1a13520cac59395c7b8d86fe1f007` (11011 bytes).
Complete original snapshot: `e9bb4b942d5f079184cf35f76090167f50af4b26`.
Complete saved reader responses: `f1c9c7457cceebc05b5a55abe83dd03c2dcdcd0d` (146754 bytes).

The input, exact source, complete production result, transport shards and reader responses were banked before guarded publication. This finite rational result is independent of any unreviewed solved variants, historical bounds or prize claim.
