# Finite B₂[2] family navigator

This index classifies every subset of the positive interval [1,19] for which each integer has at most two representations a+b with a<=b and both summands in the subset. Repeated summands are allowed: (a,a) is one representation. Swapping an off-diagonal pair is not another representation.

The complete finite family has **78,736 members**. Its maximum cardinality is **9**, attained by **224 subsets**. All 224 maximizers are exported in the saved reader packet. This is an exact finite-host classification and navigation result, not an infinite-density construction or a claim of a new extremal record.

## Sources and status boundary

Gang Yu, *An upper bound for B₂[g] sets*, Journal of Number Theory 122 (2007), 211–220, DOI 10.1016/j.jnt.2006.04.008, gives the finite positive-host definition in the opening section of the [author paper](https://www.math.kent.edu/~yu/research/sidon.pdf). The direct text rendered the ordering glyph poorly; the indexed primary excerpt supplied a<=b, and the independently read formal source explicitly agrees. There was no visual inspection or proof, example, table or quantitative-bound review.

The fully read [FormalConjectures Erdős 158 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/158.lean) had observed blob 7371ea0e0792ed0d17aa338946f245c177a0270a, 4032 UTF-8 bytes. It defines B2(g,A) by at most g solutions (a,b) with a<=b. Its main question is about every infinite B₂[2] subset of the naturals and a liminf counting expression over A intersect {m:m<N}. The positive finite host here is an explicit choice, not an assertion that the formal ambient naturals exclude zero. The main theorem is research-open with a local placeholder. The Sidon variants have separate solved annotations; one corollary has local proof text. The source was read as a statement, not executed or independently audited.

The cited Erdős–Sárközy–Sós paper, *On Sum Sets of Sidon Sets, I*, JNT 47(3) (1994), 329–347, DOI 10.1006/jnth.1994.1040, was bibliographically identified at [its institutional record](https://real.mtak.hu/110604/). Its linked scan returned 19 pages but zero text lines. That route is held as unusable statement text; no alternate copy, screenshot, OCR or retry was used. The usable independent convention source is Yu, not an asserted full reading of that scan. No current-frontier or prize claim is inferred.

## Actual input, files and bounds

The production input is N=19, g=2. The source is deliberately limited to g=2 and N in 3..24. It stops if more than 300,000 residual states or 3,000,000 cardinality-coefficient cells would be built. No cap was reached, and the host was not expanded.

The nine delivered files are:

| File | Role |
|---|---|
| b2_two_families.cjs | Constructor and saved family reader |
| B2_TWO_FAMILIES_API.md | This contract and finite correctness argument |
| snapshot_manifest.json | Full non-node data, shard map and complete-snapshot identity |
| nodes_00.json | Nodes 0..2047 |
| nodes_01.json | Nodes 2048..4095 |
| nodes_02.json | Nodes 4096..6143 |
| nodes_03.json | Nodes 6144..6422 |
| saved_reader_queries.json | All 37 actual requests and complete responses |
| README.md | Entry point and finite scope |

Source and input were banked before the one production call:

- Source blob 3194b314fe4f393637df865b9da0d733eb4d9fba, 10367 bytes.
- Input blob 755761b12636099a01235ceb3ccc644055ba69d9, 448 bytes.
- Complete constructor snapshot blob f9b551bf2f8d67f29fc5e764866b1e6797cbf3e1, 1437975 bytes.
- Complete reader packet blob 7831d3e9552e3c3025e6449f5e1543a41ee1a34a, 106190 bytes.

This numerical input is new. No earlier B3, Sidon, sum-product, field, pair-sum or subset-family computation was consumed or rerun. The residual-constraint DAG and saved cardinality-reader technique reuse established implementation structure; the pair fibers, obstructions, nodes and coefficients below were formed once for this different input.

## Pair fibers and exact obstructions

The constructor visits each host pair 1<=a<=b<=N exactly once and groups it by a+b. It retains the pair and the bit mask of its participating elements. For a diagonal pair the mask has one bit, while its representation count remains one.

For every sum fiber, it selects every triple of distinct pair records and records the union of their element supports. A chosen set violates B₂[2] exactly when it contains at least one such union:

1. Containing a recorded support realizes the corresponding three distinct unordered pairs of one sum, so the multiplicity exceeds two.
2. If a set has multiplicity at least three, choose any three of those pair records. Their support was recorded by the complete triple loop and is contained in the set.

This equivalence includes diagonal pairs and does not require six distinct summand values. The empty set and every set with fewer than three representations in each fiber remain allowed. All original obstruction witnesses are retained even though the DAG uses deduplicated support masks. In this actual input all 960 support masks are distinct.

For example, {1,2,3,4,5} is rejected at sum 6 by the three pairs (1,5), (2,4), (3,3). This saved query explicitly demonstrates why diagonal representations cannot be discarded.

## Residual-constraint DAG and polynomial recurrence

Variables are the integers 1..N in increasing order. At a state, each residual mask is the set of still-undecided elements needed to complete a forbidden support.

- Excluding a variable makes every obstruction containing it impossible; those residual masks are discarded.
- Including it removes its bit from every residual mask. An empty residual mask rejects that branch.
- Repeated residual masks are deduplicated. State memoization uses the variable position and the sorted complete residual-mask list.

The accepting terminal represents the one empty suffix choice; the rejecting terminal represents no choice. Nodes retain low/exclude and high/include successors. A node with rejecting high successor is suppressed, as in a zero-suppressed decision diagram. A skipped variable is therefore absent, not an unconstrained choice. Distinct low/high nodes are shared by their (variable,low,high) key; equal low and high pointers are not incorrectly merged as though this were an ordinary Boolean BDD.

The saved cardinality polynomial satisfies
\[
P_v(z)=P_{\mathrm{low}}(z)+zP_{\mathrm{high}}(z),\quad
P_{\mathrm{reject}}=0,\quad P_{\mathrm{accept}}=1.
\]
The branches are disjoint by the selected status of the current element, so coefficients count each subset once. All coefficients are exact BigInts serialized as decimal strings. The last nonzero coefficient identifies the largest cardinality and its number of members.

The production counters are:

| Operation or retained object | Count |
|---|---:|
| Unordered pair sums | 190 |
| Diagonal pair records | 19 |
| Triple-representation witnesses | 960 |
| Distinct forbidden support masks | 960 |
| Residual states | 15195 |
| State memo hits | 9567 |
| Nonterminal DAG nodes | 6421 |
| Total nodes, including two terminals | 6423 |
| Cardinality coefficient cells | 28315 |
| Unique-node hits | 3146 |
| Rejecting-high reductions | 5627 |

The constructor does not enumerate all 2^19 subsets into individual records. The saved DAG represents the complete qualifying family. Its cardinality coefficients are:

| Size | Count |
|---:|---:|
| 0 | 1 |
| 1 | 19 |
| 2 | 171 |
| 3 | 969 |
| 4 | 3876 |
| 5 | 11424 |
| 6 | 23644 |
| 7 | 27830 |
| 8 | 10578 |
| 9 | 224 |

There are no larger members. The sum of these coefficients is 78736.

## Loading the complete saved index

The snapshot is distributed in one manifest and four complete node shards. The manifest's snapshot object contains every other original field and a null nodes slot. Concatenating the shard node arrays in manifest order and replacing that slot reconstructs the exact original 1437975-byte snapshot serialization.

All node IDs, outgoing arcs and coefficient vectors are present. Splitting did not discard a proof layer or require family regeneration. The performed reconstruction check compared full serialization bytes and the Git blob identity only; it did not reevaluate pair sums, constraints, recursion or coefficients.

Example consumer syntax, provided for users and not another execution here:

```javascript
const fs = require('node:fs');
const path = require('node:path');
const { openIndex } = require('./b2_two_families.cjs');
const manifest = JSON.parse(fs.readFileSync('snapshot_manifest.json', 'utf8'));
const nodes = manifest.node_shards.flatMap(part =>
  JSON.parse(fs.readFileSync(path.join('.', part.path), 'utf8')).nodes);
const snapshot = { ...manifest.snapshot, nodes };
const reader = openIndex(snapshot);
reader.query({op:'family', size:9});
reader.query({op:'select', size:9, rank:'223'});
reader.query({op:'classify', values:[1,2,3,4,5]});
```

The manifest records each shard path, first node ID, row count, byte count and blob identity. Source custody should bind these files before they are passed to the reader. openIndex clones the supplied snapshot and checks schema, variable permutation, integer coefficient encoding and the DAG's forward variable/backward ID order. These structural checks do not independently prove the saved coefficients or certify adversarial input. The trusted object is the identified complete production artifact.

## Query API and ordering

The module exports compile(input) and openIndex(snapshot). The actual reader called only openIndex on the banked snapshot. Its object exposes query(request) and work().

A condition has optional required and forbidden arrays of distinct labels in 1..N. They must be disjoint. At most 16 distinct conditions are cached per reader. The reader may form up to 500000 new conditional coefficient cells, cumulatively. It prunes impossible required labels skipped by a suppressed node and reuses saved polynomial suffixes after the last restriction. Fresh conditional arithmetic is counted below.

A size field optionally fixes cardinality. Family coefficients and maximum fields still describe all cardinalities under the condition; the count field alone uses a requested size. Every rank is zero-based and supplied as a decimal string.

Ordering is lexicographic on the increasing-label decision bit vector, with exclude/0 before include/1. It is **not** lexicographic on the displayed increasing element lists. The ordering is fixed before conditioning; conditions select a subsequence of that same order.

| Operation | Fields and result |
|---|---|
| summary | Complete family totals, size optimum, work and object counts |
| family | Optional condition and size; full conditional coefficient vector and selected count |
| select | Rank string, optional condition and size; the corresponding increasing element list |
| rank | Values, optional condition and size; membership and inverse rank |
| page | Offset string, limit<=256, optional condition and size; consecutive selected members |
| classify | Values; active saved pair fibers, maximum multiplicity and first three-pair violation |
| extensions | Values; admissibility, every allowed added host element and rejection witness for each disallowed one |
| fiber | Sum in 2..2N; complete original host pair fiber |
| obstruction | Witness ID; sum, three pairs, support mask and elements |
| node | Node ID; full stored arc and coefficient row |
| conditions | All cached conditions and their complete coefficient descriptions |

The extensions result examines additions from the entire original host, regardless of whether the values came from a conditioned family. Inclusion-maximal means no omitted host element can be added while preserving B₂[2]; maximum_cardinality means its size equals the global optimum for this host. These are different properties. Invalid starting values return the original violation and no extension classification.

## Actual first reader use

All 37 complete requests and responses were stored individually before the next query and then banked as one packet. There was no failed query, lost response or reconstruction retry.

The consumer includes nine select/rank inverse pairs: three size-nine ranks, three all-size ranks, and one maximum-size rank in each of three nonempty restricted families. All nine match. It also exports **all 224 size-nine members** in one page, not merely representative witnesses.

In the declared order the first maximum is [2,6,7,10,11,16,17,18,19]; the last is [1,2,3,4,6,8,13,16,19].

All five queried conditions have complete saved coefficient outputs:

| Required | Forbidden | Total | Largest size | Number at that size |
|---|---|---:|---:|---:|
| none | none | 78736 | 9 | 224 |
| 1,19 | none | 10482 | 9 | 156 |
| 1,2,3,4,5 | none | 0 | none | 0 |
| none | 1,2,3,4,5 | 6611 | 8 | 14 |
| 2,4,6,8 | 10 | 445 | 9 | 4 |

Five extension queries classify 60 candidate additions and preserve each disallowed addition's explicit three-pair collision. In particular [6,9,10,12,13,17,18,19] is an inclusion-maximal size-eight member in the full host, although the host has size-nine members. The empty set permits every single host element as an addition.

Fresh reader work:

| Operation | Count |
|---|---:|
| Queries | 37 |
| Cached conditions | 5 |
| Condition cache hits | 20 |
| New conditional DAG nodes evaluated | 3368 |
| New conditional coefficient cells | 13631 |
| Saved-polynomial suffix uses | 3469 |
| Skipped-required rejections | 190 |
| Selection steps | 3665 |
| Rank steps | 141 |
| Saved-pair membership checks | 12730 |
| Full fiber reads | 1 |
| Extension candidates | 60 |
| New constructor states, pair sums, obstructions, base coefficients | 0 each |

The pair-membership checks filter saved pairs; they do not recalculate a+b or rebuild pair fibers. New conditional polynomials are explicitly query work, not hidden as zero-cost lookup. No earlier accepted numerical construction or proof was repeated.

## Scope and delivery

The finite-host classification certifies what it states for all subsets of [1,19], with repeated summands and unlabelled pair order handled exactly. It does not quantify over arbitrary infinite sets, establish the liminf assertion, or identify a new asymptotic bound. Historical and current source annotations are kept separate from proof verification.

Before activity, bounded exact-number Slack, all-state PR and code searches returned no carrier. This is coordination evidence rather than a global absence or exclusive-ownership claim. Guarded publication and complete native readbacks bind the delivered bytes, not runtime deployment, sponsor acceptance or a prize result.
