# Complete minimum Q4 deletion families

This package completes a finite navigation capability left open by [Commons #31442](https://github.com/woahwhattheheck/commons/pull/31442). That accepted package established the Q4 optimum and saved one minimum eight-edge deletion cover. Its branch-and-bound search could prune equal-size alternatives. This consumer takes its topology and optimum as premises and constructs the entire minimum-deletion family, without rerunning the cube constructor, optimizer, or earlier proof checks.

The result is exactly **eight labelled deletion sets**, each deleting two edges in each of four directions. All eight are exported below and in the reader packet. Every one is a perfect matching of the sixteen vertices, as shown by its saved degree record. Every original edge occurs in exactly two deletion sets. These are finite results for this identified cube; no new optimum, priority, asymptotic bound, prize claim, or sponsor submission is asserted.

## Mathematical objects and attribution

Q_n has vertex set {0,1}^n, with two vertices adjacent exactly when they differ in one coordinate. David Conlon's author institutional abstract for [An Extremal Theorem in the Hypercube](https://authors.library.caltech.edu/records/pw80h-jdy02), Electronic Journal of Combinatorics 17 (2010), R111, supplies this convention and defines ex(Q_n,H) using subgraphs with no copy of H. This is ordinary subgraph containment. Retaining the full vertex set, including isolated vertices, does not change the edge objective or C4-freeness. The source passage used here is the abstract only; no numerical table, example construction, or proof was imported. A distinct Lidický PDF request returned 403 and remains an access gap.

The current [FormalConjectures Erdős86 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/86.lean) was returned in full at its default ref. The observed 1,993 UTF-8 bytes have Git blob identity `9893cdbc1cc5534dd0c912c63693c98642d0a249`. The statement quantifies over every fixed positive epsilon and all sufficiently large dimensions: enough edges above half the cube's edge count force a C4. Its research annotation is open and its local theorem body is `sorry`. No Lean execution or external proof review occurred; a default-ref text identity is not an independently pinned source commit.

The old package attributes standard cube/layer and baseline conventions to Rahil Baber, [Turán densities of hypercubes](https://arxiv.org/pdf/1201.3587), arXiv:1201.3587v2. That attribution is preserved as input provenance. The earlier alternating-layer construction is not part of the new calculation.

## Exact input custody

The only old mathematical records consumed are the supplied vertices, edges, square incidences, capacity metadata, optimum values, and the one old witness used in a new ranking query. They come from `/fresh_reader/snapshot/topology` and `/finding` in:

- Repository: `woahwhattheheck/commons`.
- Commit: `75fd12017ee73d130d660f557d074cdf47b6b5d6`.
- Path: `research/ppl033_erdos86_cube_square_cover/q4_square_cover.json`.
- Complete source artifact: 709,298 UTF-8 bytes, blob `b7dc617c15974b63a31eb4e950ad710a026d08c4`.
- New isolated input: `input_q4.json`, 18032 bytes, blob `8371e9d8d5e536a447f7da5365f5b8fe4ff37de3`.

The complete old artifact was acquired as an input and its byte identity matched. No old search node, greedy gain table, packing bound, optimization recurrence, or original reader query was replayed. The new input carries the old result as a premise: 32 edges, 24 coordinate squares, three incident squares per edge, minimum deletion size 8, and maximum kept size 24. Semantic agreement of the two supplied incidence views and the square/C4 reduction are inherited. Structural input checks do not independently authenticate those mathematical premises.

Vertex labels are binary integers 0 through 15, bit zero least significant. Edge IDs run first by direction and then by the increasing endpoint with that direction bit zero. Square IDs run first by the pair of directions and then by their increasing zero-bit base. Deletion sets are ordinary subsets of these 32 fixed edge labels. Their complements are maximum kept-edge subgraphs on all sixteen vertices. There is no graph-isomorphism quotient.

## Why an exact-cover index is complete

Invoke the inherited optimum 8 and the inherited three-square incidence count. Any minimum deletion cover has eight edges and therefore 24 edge-square incidences. It covers all 24 squares, so each square is hit exactly once. Conversely, a collection of edges whose square-incidence sets partition all 24 squares has exactly eight edges, hence is a minimum deletion cover under the inherited premise.

The new compiler memoizes the remaining-square mask. At each nonempty state it chooses the least uncovered square. Each outgoing arc selects one incident edge whose entire three-square mask is still uncovered, and removes that mask. Arc order is increasing edge ID. The empty mask has one completion. A nonempty state with no viable arc has zero completions.

Every exact cover has exactly one edge meeting the chosen square, so the outgoing branches partition the complete family without overlap. Recursion removes three squares per step and terminates. Induction on the number of remaining squares proves the saved sum of child counts is exact. A profile coefficient records the four numbers of selected edges by direction; an arc increments its edge's coordinate. Child profile counts add. This is the new family-counting argument; it does not redo the prior optimization search.

All nodes, including zero-completion nodes and every computed arc, are retained. Counts use BigInt arithmetic and decimal strings in JSON. Square masks use exact JavaScript integers with at most 30 bits. The reusable compiler accepts at most 52 edge labels, constant incidence arity, and an explicit exact-capacity premise; this invocation uses only the supplied Q4 input. Caps are 100,000 states and 1,000,000 profile cells. A cap throws; no partial result is advertised as complete or automatically retried.

## Actual construction

| Quantity | Actual value |
|---|---:|
| Saved exact-cover states | 212 |
| Arc candidates / incidence-subset checks | 844 |
| Retained arcs | 236 |
| Saved direction-profile cells | 46 |
| Profile additions | 52 |
| Minimum deletion sets | 8 |
| Root profile | (2, 2, 2, 2), count 8 |
| Old topology / optimizer / proof work | 0 / 0 / 0 |

The complete source and input were banked before the one compiler call. The output was banked before the separate reader was opened. The constructor and reader both completed without an exception; no execution was repeated.

| Rank | Deleted edge IDs |
|---:|---|
| 0 | 0, 7, 10, 13, 19, 20, 26, 29 |
| 1 | 0, 7, 11, 12, 18, 21, 27, 28 |
| 2 | 1, 6, 10, 13, 17, 22, 24, 31 |
| 3 | 1, 6, 11, 12, 16, 23, 25, 30 |
| 4 | 2, 5, 8, 15, 19, 20, 25, 30 |
| 5 | 3, 4, 8, 15, 17, 22, 27, 28 |
| 6 | 2, 5, 9, 14, 18, 21, 24, 31 |
| 7 | 3, 4, 9, 14, 16, 23, 26, 29 |

The rank is recursive branch order, not numerical edge-mask order, lexicographic order of sorted edge lists, or an isomorphism rank. The saved old witness is rank 0 under this new ordering. The complete eight-member export has degree one at every vertex for every deletion set, proving the stated finite perfect-matching description within this exhaustive family. This is not a theorem about arbitrary dimensions.

## Reader API

```js
const fs = require('node:fs');
const {openIndex} = require('./minimum_cube_deletion_index.cjs');
const data = JSON.parse(fs.readFileSync('q4_minimum_deletion_index.json', 'utf8'));
const reader = openIndex(data);
const all = reader.page('0', 8);
const family = reader.count({require: [0, 7]}); // two
const first = reader.select('0', {forbid: data.input.old_witness_ids});
const inverse = reader.rank(first.deleted_edge_ids, {forbid: data.input.old_witness_ids});
```

This is a reusable Node/CommonJS example, not a claim that a Node CLI or filesystem command was executed for this delivery. The actual invocation loaded unchanged CommonJS source in V8.

| Method | Contract |
|---|---|
| `compile(input, limits?)` | Construct the new exact-cover DAG from identified incidence premises. |
| `openIndex(data, caches?)` | Open saved data and optional complete condition caches; no base recurrence. |
| `summary()` | Saved total, optimum premises, and direction-profile coefficients. |
| `count(options)` | Exact count satisfying required/forbidden edge IDs and optional full direction profile. |
| `select(rank, options)` | Zero-based selection, branch trace, deleted/kept IDs, profile, degrees, and square assignments. |
| `rank(edgeIds, options)` | Membership and inverse rank; nonmembers carry a reason. |
| `page(start, limit, options)` | Consecutive ranks, at most 1,000 records; next is null at the end. |
| `edge(id)`, `square(id)`, `node(id)` | Copy identified saved records. |
| `caches()`, `work()` | Full condition memo records and fresh reader work counters. |

Options use distinct valid edge-ID arrays `require` and `forbid`, with no imposed input order. Their intersection gives an empty family. `profile` is a four-entry nonnegative integer vector for the full deletion set. An unattainable profile gives zero. Ranks are exact BigInt-compatible inputs; decimal strings are recommended. Negative or out-of-range selection ranks and pages are rejected. A caller must treat supplied index/cache records as trusted retained data; opening is not independent certificate verification.

A conditional memo key is (saved node, still-required edge mask, remaining profile), with one cache per normalized option set. A selected arc clears its required edge and decrements its direction coordinate. Forbidden arcs are omitted. At the terminal node all requirements and profile coordinates must be exhausted. Unrestricted counts and profiles are read directly. This query recurrence visits only saved arcs: it constructs no incidence, base DAG, or base profile coefficient.

`select` additionally constructs the requested output record from the literal saved edge endpoints and square IDs. Degree increments and square-assignment writes are new query work. They are not reconstruction of the old cube or independent replay of its square-cover proof.

## Retained first reader

`saved_reader_queries.json` contains all **61 complete responses**. It exports all eight covers and ranks them back; supplies all 32 single-edge participation counts; ranks the old witness; and answers eight additional conditions plus selected first witnesses and saved-record lookups. The twelve selected/ranked pairs match exactly. There were 41 normalized condition-cache entries, all retained in `saved_condition_caches.json`; empty memo entries are also preserved.

| Restriction | Count |
|---|---:|
| Require each individual edge, separately | 2 for all 32 edges |
| Require edges 0 and 1 | 0 |
| Require edges 0 and 7 | 2 |
| Require all eight old-witness edges | 1 |
| Forbid all eight old-witness edges | 3 |
| Require 0 and forbid 7 | 0 |
| Profile (2,2,2,2) | 8 |
| Profile (8,0,0,0) | 0 |
| Require and forbid 0 | 0 |

| Fresh reader work | Actual value |
|---|---:|
| Conditional memo states | 7,059 |
| Conditional arc visits | 7,887 |
| Saved base-count / profile reads | 475 / 28 |
| Memo hits | 642 |
| Selection / ranking arc steps | 142 / 154 |
| Materialized deleted-edge records | 96 |
| Square assignments | 288 |
| Vertex-degree increments | 192 |
| New incidence / base-DAG / base-profile work | 0 / 0 / 0 |

The counters measure their named operations, not every JavaScript instruction or structural check. No timing or complexity improvement is claimed. Conditional query work is explicitly separate from the once-only compilation.

## Complete artifact custody

| Artifact | Bytes | Git blob identity |
|---|---:|---|
| `minimum_cube_deletion_index.cjs` | 9627 | `1ba30f4977d4760a683d8e340177b3596b456e19` |
| `input_q4.json` | 18032 | `8371e9d8d5e536a447f7da5365f5b8fe4ff37de3` |
| `q4_minimum_deletion_index.json` | 73126 | `5dfd18cfeb9bd7a77cb16c5305589b87be1cc90d` |
| `saved_reader_queries.json` | 76458 | `d73d0f95f058a212bb7893dbcb930c7f3bad944b` |
| `saved_condition_caches.json` | 373145 | `1323e2f672f6be68f342d2999373a04c74ffd19f` |

The mathematical data and actual outputs are complete, not sampled. Byte/blob comparisons are custody checks, not mathematical recomputation. The scope is this labelled Q4 minimum family and the declared saved-reader conditions. It does not supply an asymptotic Erdős86 result, a new finite optimum, a current exhaustive literature survey, or a general classification of higher-dimensional minimizers.
