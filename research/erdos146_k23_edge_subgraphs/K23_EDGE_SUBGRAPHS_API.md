# Finite K₂,₃-free edge-subgraph index

This package answers exact finite questions about simple labelled graphs on vertices 0 through 5. Every graph is a subset of the fifteen supplied unordered edges. It retains the entire K₂,₃-free family and, for every possible host graph H, the polynomial
P_H(z) = sum over K₂,₃-free T contained in H of z^{|T|}.
It then navigates edge deletions and conditioned members from saved records. No graph is identified up to isomorphism.

The actual construction has 21,856 free graphs. Their counts by edge cardinality 0 through 15 are
[1,15,105,455,1365,3003,4945,5895,4500,1500,72,0,0,0,0,0].
The largest free graphs have ten edges, with 72 labelled maximizers. These are exact finite-host results. They are not presented as new extremal values, an asymptotic theorem or a record.

## Source and scope

The fully observed FormalConjectures source was
https://api.github.com/repos/google-deepmind/formal-conjectures/contents/FormalConjectures/ErdosProblems/146.lean .
Its complete 2,519-byte text has computed Git blob identity 384b2f11aeec3303ccfa9d74b81b357142981ee2 and is copied unchanged as FORMAL146_OBSERVED.lean with its Apache license header. The read used the provider's default ref, so no immutable source-repository commit is asserted.

That source asks whether a bipartite r-degenerate forbidden graph always has extremal number O(n^{2-1/r}). The observed main assertion is answer(False), category research solved. A connected bipartite 2-degenerate counterexample variant is also marked research solved, and the local theorem bodies remain sorry. The source's linked external proof was not opened or reviewed. Those annotations are source status, not a proof verification in this package.

Füredi and Simonovits, The history of degenerate (bipartite) extremal graph problems, arXiv:1306.5167v2 (29 June 2013), printed page 4, define the extremal number by exclusion of a not necessarily induced subgraph:
https://arxiv.org/pdf/1306.5167 .
The bounded primary read supplies that convention only; no table, example, construction, bound or proof was imported.

Here the forbidden graph is explicitly K₂,₃. Five distinct vertices are split into a two-vertex side and a three-vertex side; all six cross-edges must occur. Additional edges within or outside these parts do not prevent the copy. The host need not be bipartite. K₂,₃ is bipartite and 2-degenerate: remove the three vertices on its size-three side first, each then having degree at most two, and remove the other two afterward. This elementary specialization does not reproduce the source's general counterexample.

Earlier #31834 classified K₂,₂,₂-free graphs; #31870 studied triangle-free edge partitions; #31710 studied regular induced subsets. Their predicates and results were not replayed. No C4, Singer, finite-field or accepted chromatic computation was invoked. This input is the explicit fifteen-edge labelled universe in input.json.

## Representation and exact construction

Bit i of an integer mask records edge i in input.edges. Masks range from 0 to 32767. The ordering is numerical mask order, not an isomorphism ordering. Vertices remain present when all their incident edges are removed.

For each two-vertex side there are four choices of a three-vertex subset of the remaining four vertices. The compiler retains all sixty forbidden masks, each with its two sides. It classifies every host mask by testing whether any forbidden mask is contained in it; the first witness is retained, or -1 if none exists.

The row for host H is:
[edge_count, first_forbidden_pattern_or_minus_one, maximum_free_edges, coefficients_0_through_15].

Initially coefficient k at H is one exactly when H is free and has k edges. For each edge bit b, every row containing b adds the complete coefficient vector at H without b. After all fifteen passes, each free subset T of H has contributed exactly once, in coefficient |T|. This is the ranked subset zeta transform. Counts are ordinary sets of edges; no multiset or ordered-copy multiplicity enters the coefficient.

All values in these arrays are nonnegative integers at most 32768, so JavaScript Number and Uint32Array arithmetic are exact here. The compiler is deliberately bounded to this six-vertex, fifteen-edge input contract. It is exponential finite preprocessing, not a scalable or novel extremal-graph algorithm.

Actual once-only work:
- 60 forbidden masks and 360 edge-label lookups.
- 32,768 classifications and 1,549,892 forbidden-mask tests.
- 32,767 size recurrence steps.
- 524,288 coefficient cells and 3,932,160 zeta additions.
- 32,768 profile insertions, producing 28 (host size, maximum kept size) buckets.
- Zero calls to prior graph-property calculations.

The constructor took 455 ms in this one connected V8 observation. That is neither a benchmark nor an end-to-end performance claim.

## Why the deletion APIs are exact

Deleting D from H leaves T = H minus D. Thus a minimum deletion set is the complement in H of a maximum-cardinality free T contained in H. The saved polynomial degree gives the minimum deletion number |H| minus degree(P_H), and the top coefficient gives its number of distinct deletion sets.

Inclusion-minimal is different from minimum-cardinality. A deletion set is inclusion-minimal exactly when its complementary free T cannot accept any single omitted edge of H. If a larger free extension existed, its one-edge intermediate extension would be free, because this forbidden-subgraph property is hereditary under edge removal. The reader checks those one-edge flags in the saved classification table; it does not retest forbidden copies.

For the full fifteen-edge host, the saved reader reports:
- Minimum deletion size five, attained by 72 sets.
- 852 inclusion-minimal deletion sets: 72 of size five and 780 of size six.

For the other selected hosts:

| Host | Edge mask | Edges | Minimum deletions | Minimum sets |
|---|---:|---:|---:|---:|
| Empty | 0 | 0 | 0 | 1 |
| One K₂,₃ | 476 | 6 | 1 | 6 |
| Six-cycle | 21041 | 6 | 0 | 1 |
| K₅ and an isolated vertex | 5871 | 10 | 3 | 80 |
| K₃,₃ | 4060 | 9 | 2 | 18 |
| Complete six-vertex host | 32767 | 15 | 5 | 72 |

These finite outputs are not a statement about every n or about the asymptotic conjecture.

## Opening and querying the saved index

The reusable implementation is k23_edge_subgraphs.cjs. Its compile(input) entry point made this certificate once. A reader should call openIndex on the saved assembled certificate and must not call compile merely to load or navigate it.

Four host_rows_NN.json shards each contain 8,192 consecutive host rows. certificate_manifest.json contains their exact start masks, lengths and byte/blob identities, plus all remaining snapshot fields. load_saved_index.cjs exports assemble(manifest, parsedShards); pass the four parsed arrays in their documented order. Concatenating them with the retained metadata reproduces the full 1,911,280-byte JSON certificate exactly, including its trailing newline:
03668419188249258d52cfa72d63e234fca27de3.
That assembly was checked as byte identity only, with no classifier, transform or query replay.

Example using already loaded JSON values:

~~~javascript
const {assemble} = require('./load_saved_index.cjs');
const {openIndex} = require('./k23_edge_subgraphs.cjs');
const saved = assemble(manifest, [rows00, rows01, rows02, rows03]);
const reader = openIndex(saved);
const c = reader.condition({host: 32767, size: 10});
const member = reader.select(c.key, 0);
const back = reader.rank(c.key, member.mask);
~~~

API details:
- summary() returns the retained global counts.
- patterns() returns all sixty labelled copies.
- witness(H) returns the saved first forbidden copy, or a free flag.
- minimum(H) returns the stored polynomial, maximum kept size, minimum deletion size and optimum count.
- condition({host,include,exclude,size}) scans saved free masks. Defaults are the full host, no forced edges and unrestricted cardinality. Include and exclude must be disjoint subsets of host. The returned key identifies a cached sorted member list and coefficient vector.
- select(key, rank), rank(key, mask), and page(key, start, limit) navigate that cached list. Ranks are zero-based. A nonmember rank lookup returns null. Selecting from an empty family is an error. Pages are bounded to 1,000 records.
- optimal(H) creates or reuses a condition at the saved maximum cardinality.
- deletion(H, rank) returns complementary kept and removed masks and both edge lists. deletionRank(H, D) is its inverse for a minimum deletion. The ordering is increasing KEPT mask, so it is not increasing removed-mask order.
- minimal(H) returns the count and deletion-size histogram of inclusion-minimal deletions. minimalSelect(H, rank) follows increasing kept-mask order in that family.
- profile(hostSize, maximumKept) and hostSelect(...) navigate saved host buckets.
- exportCaches() returns actual complete query caches. work() reports only work done by that reader instance.

Opening performs structural checks, not an independent mathematical validation of an arbitrary supplied certificate. The reader trusts the saved classification and coefficient data. Its saved responses and inverse comparisons are evidence for this consumer, not a proof of arbitrary input provenance.

## Actual reader interruption and continuation

The original driver and its exact source are preserved as reader_driver_original.cjs. It used a helper that erroneously retained rank zero when a family count was zero. Query 77 correctly found that requiring all six edges of a K₂,₃ leaves zero admissible graphs. Query 78 then attempted select(empty, 0), and the index correctly raised RangeError("rank").

All 77 preceding complete responses were banked immediately as saved_reader_interrupted.json. Twenty select/rank or deletion/inverse pairs among those complete responses agree. The constructor was not rerun, no response was invented, and the failed selection was not retried.

The first reader closure's unexported cache objects and aggregate work counters are unavailable. This is an explicit custody gap. Its complete response records remain available. A planned page containing all 72 global maxima depended on a lost earlier cache and was omitted rather than reconstructed. The full mathematical family remains present in the construction table; this package does not claim that the omitted page was executed.

reader_continuation.cjs implements a corrected count-zero guard and executes only five previously unasked conditions and the remaining host-profile queries. Its 47 complete responses, fifteen matching inverse pairs, all five new caches and exact work counters are saved in saved_reader_continuation.json. No completed query or lost cache was reconstructed.

The five new conditioned family sizes are:
- Avoid all edges of the first forbidden copy: 512.
- Require edge bits 0 and 1, exclude bit 2, and keep eight edges: 639.
- Require the five-edge star at vertex 0 and keep nine edges: 70.
- Require the triangle on vertices 0,1,2 and keep nine edges: 279.
- Inside K₅ plus an isolated vertex, require bit 0, exclude bit 1, keep seven edges: 18.

Continuation work: 32,768 structural rows read; 5,045 saved-row lookups; 109,280 saved-free-mask scans; 1,518 conditional coefficient additions; 113 binary-search comparisons; 225 edge-label inspections; fifteen selected records; zero new pattern tests or zeta additions. No aggregate counter is claimed for the unavailable first reader instance.

There are 124 complete retained query responses in total and 35 matching inverse comparisons. They are split across the interrupted and continuation packets so their different evidence boundaries remain visible.

## Public checkpoints and provenance

Before construction, native Git create_blob acknowledgements in woahwhattheheck/commons confirmed:
- Source: df814541df81c311fd68c94945785437c95e0a8e (9,135 bytes).
- Input: c5cd5193beed16e0c36fb9f5b593b8f39946865f (2,005 bytes).
- Plan: c5f4468c50a71d5d4a7af6cfa51e81f9e922ac13 (1,128 bytes).

Before the reader, the full constructor result was acknowledged as 03668419188249258d52cfa72d63e234fca27de3. Reader plan dc5163503f0414adf3b27a561f8d649630d013fd and original driver f43af9e795f699ec10358c88c479b73271d04578 were also acknowledged.

After the interruption, the complete available response packet was acknowledged as 3db22a429b79ed55bece734f3179a524384d8cc0 (22,231 bytes). The continuation source was acknowledged as bf42791c08504ef7a0a4815c4a9ff2df3b778b3a, and its complete result as 343590aa7e81c3a8402b132e79b42fdaa75c2e75 (24,644 bytes).

These are actual native public blob acknowledgements, distinct from merely computed identities. Private provider envelopes, Slack records and journals are not public package contents. Native acknowledgements checkpoint bytes; branch, merge and final readback claims belong to the publication receipt.

The prior E241 data-loss disposition is unrelated to this computation and remains protected. No missing E241 source or result was reconstructed to produce this package.
