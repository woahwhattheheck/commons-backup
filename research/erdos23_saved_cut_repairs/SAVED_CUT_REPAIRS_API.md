# Canonical cuts from an accepted occupancy index

This package consumes the saved occupancy rows of the accepted five-part C5 blow-up, with six labelled vertices per part. It adds an exact cut and deletion-family index without rebuilding the old occupancy enumeration, induced-edge products, binomial table or sparse-half results.

The new index represents all 536,870,912 cuts with vertex 0 on the selected side. Its 14,406 canonical occupancy rows form 60 deletion-cost buckets. The maximum cut has 144 edges, so the minimum number of deleted edges is 36. There are exactly 315 distinct minimum deletion sets. The entire canonical vertex-side family for those 315 repairs is exported by the saved reader.

The bound 36 is the classical balanced-C5 sharpness value for this known host, not a newly discovered extremal bound. The new deliverable is complete canonical cut/deletion navigation and its retained actual query evidence. It does not prove the conjecture for every triangle-free graph.

## Definitions and primary source

Balogh, Clemen and Lidický, *Max Cuts in Triangle-free Graphs*, arXiv:2103.14179v1 (25 March 2021), define D2(G) as the minimum number of edges removed to make G bipartite. Their introduction attributes the n²/25 conjecture to Erdős and gives the balanced C5 blow-up as the sharpness example. The same paper describes blow-up edges between cyclically consecutive classes. The inspected introductory passages supplied these conventions and attribution, not a proof, numerical table or current-frontier audit.

Primary manuscript: https://arxiv.org/pdf/2103.14179

For a vertex subset S, its cut contains the edges with one endpoint in S and one outside. Deleting every within-side edge leaves that cut as a bipartite spanning graph. Conversely, any bipartite spanning subgraph has a two-coloring and is contained in the corresponding cut. Therefore D2(G) equals |E(G)| minus the maximum cut size. This is the elementary interpretation used here, not a separately attributed theorem number.

There is no equal-side-size requirement in edge bipartization. A half-size condition is an optional, different restriction in this API. Vertices are retained; only edges are deleted.

The complete FormalConjectures23 source was read at identity `7154c171998f17e8a251be3522927674e2ff3185`, 5,111 bytes:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/23.lean

It asks whether every triangle-free graph on 5n vertices can be made bipartite by deleting at most n² edges, and annotates the main question as research open. It also records finite variants, including a solved annotation for 25 vertices, the classical C5 blow-up definition and local placeholders. Reading this source is not a verification of its external references or an execution of its included Lean material. No general-status conclusion is inferred from the finite consumer.

## Exact accepted input lineage

The source premise is the complete occupancy/Pascal result released in Commons #31636:
https://github.com/woahwhattheheck/commons/pull/31636

Its merge is `20e7ca9188726f97019dd82380dd095608d79097`; its original constructor is `317025a36896e4d030232fd0318d582f43c3bf25`. The prior directory is `research/erdos128_blowup_subsets/`.

| Accepted input file | Blob identity |
| --- | --- |
| cycle5_size6_index.json | 444f907b1e45eb2a989b3ad8740730d193dc426a |
| occupancy_rows_00000_04095.json | 103d1dbd0f08b8c6564453c7826f8c06f21efb5c |
| occupancy_rows_04096_08191.json | e3539c013dcbb9ef2d7e03f5a73e0d19d4347e33 |
| occupancy_rows_08192_12287.json | be49ac00d5876618d5df19f04ac3b014a3d5dbe3 |
| occupancy_rows_12288_16383.json | 60bfb5c4a54a51083fb29ce4c92b0e1e6ae45efc |
| occupancy_rows_16384_16806.json | 69333babc2751dfb5574c2dfd0fdbc131f8a34f8 |

These exact texts were already retained and were consumed directly. No accepted constructor or accepted reader was invoked. Text identities, parsing and concatenating the complete shards are source custody operations, not a replay of the mathematical enumeration.

Part p has labels 6p through 6p+5. Each part is independent. Consecutive parts around C5 are completely joined, using base edges (0,1), (0,4), (1,2), (2,3), (3,4). The accepted host has 30 vertices and 180 edges, and every vertex has degree 12.

For occupancy x=(x0,...,x4), each xi ranges from 0 through 6. Its original code is x0+7x1+7²x2+7³x3+7⁴x4. Each accepted row is [subset size, induced-edge count, labelled multiplicity], with multiplicity the product of binomial(6,xi). All 16,807 original rows and the old Pascal table are identified input premises. Their validity is not reproved by this package.

The complete new compiler input, including the literal accepted rows and source pins, was banked as `cd1fb76e0ce4a0c17cfa9e8414af5cd19204df15`, 254,899 bytes. The new snapshot records the source lineage and retains the old Pascal entries unchanged.

## New finite derivation

In a d-regular graph, summing degrees over S gives d|S|=2e(S)+e(S,V minus S). Thus the saved size k and internal-edge count e determine this host's cut size:

crossing = 12k - 2e,  
deleted = 180 - crossing.

No occupancy edge products need to be recomputed.

Every unordered vertex bipartition has exactly one orientation containing vertex 0. For an old occupancy row with x0=0, that orientation is absent. For x0>0, its number of label selections containing vertex 0 is

binomial(5,x0-1) · product over p=1,...,4 of binomial(6,xp)
= oldWeight · x0/6.

The compiler computes this new canonical multiplicity from the saved weight and checks integrality. It does not rebuild the binomial factors. All canonical cuts, including the all-vertex selected side, are represented exactly once. The total is 2^29.

Rows are grouped by deleted-edge count. The minimum group gives every maximum cut. Minimum edge-deletion sets that make the graph bipartite are exactly the complements of maximum cuts: if a minimum deletion set removed a crossing edge under a two-coloring of the retained graph, restoring that edge would preserve bipartiteness and contradict minimality.

There is also no duplication among the canonical cut edge sets in this connected host. If two colorings have the same crossing/noncrossing status on every edge, their color differences are constant along every edge and hence across the connected graph. They differ only by a global swap. Fixing vertex 0 removes that swap. Consequently the 315 canonical maximum cuts correspond to 315 distinct minimum deletion sets.

For nonminimum buckets, the API indexes deletion sets consisting of all within-side edges for a bipartition. These are valid bipartizing deletions, but they are not an enumeration of every possible deletion set that leaves a bipartite subgraph; arbitrary extra deletions of crossing edges are outside this family.

## Files and executed identities

| File | Role |
| --- | --- |
| `saved_cut_repairs.cjs` | New compiler and saved cut/repair reader |
| `cycle5_size6_cut_index.json` | All canonical rows, cost groups, prefixes and source lineage |
| `saved_reader_queries.json` | All 33 actual outputs, complete minimum family and eight conditions |
| `SAVED_CUT_REPAIRS_API.md` | Derivation, API, old-input boundary and finite results |
| `README.md` | Entry point |

Executed source: `c7af3c35f8d7b38686a504979bf099cddaf585a0`, 9,573 bytes. Complete compact snapshot: `e1fc0e47b68376bc335b8ab5f1f12a64cd4cd995`, 517,253 bytes. Complete compact reader packet: `87fe625499b17bd2880b69b26d7d6ea8e492f4ef`, 501,197 bytes. Each JSON text ends with a newline.

The source and complete input were banked before the new compiler ran once. The snapshot was banked before a fresh reader opened it. Every reader response was banked before the next query.

## Compiler and data contract

`compileCuts(input)` accepts a supplied complete C5 blow-up occupancy result for five equal parts of size b, with 1 <= b <= 12. It requires the complete (b+1)^5 row array, a saved Pascal table through b, and the identified total-edge premise. Its mathematical contract requires those inputs to describe the stated balanced C5 blow-up. The implementation checks bounds, row shapes used by the compiler and derived weight integrality; it is not an independent verifier of the accepted occupancy table, graph identity or Pascal values.

The source size-six instance satisfies that contract through its exact accepted lineage. The generic formula uses regular degree 2b. Source rows with x0=0 are read and skipped. Every retained new row has shape:

[old occupancy code, selected-side size, deleted edges, canonical multiplicity].

All retained rows remain in increasing old code order. A bucket stores its `deleted` value, total decimal `count`, row IDs in increasing code order and cumulative decimal `prefixes`. Buckets are sorted by increasing deleted-edge count. The snapshot also retains `source`, `part_size`, `vertices`, `total_edges`, `regular_degree`, copied `pascal`, `summary` and `work`. Format is `saved-c5-canonical-cut-index-v1`.

The actual compiler performed:

| Counter | Actual |
| --- | ---: |
| source_rows_read | 16,807 |
| canonical_rows | 14,406 |
| cut_cost_evaluations | 14,406 |
| canonical_weight_products | 14,406 |
| canonical_weight_divisions | 14,406 |
| bucket_additions | 14,406 |
| old_occupancies_built | 0 |
| old_edge_products | 0 |
| pascal_cells_built | 0 |

The multiplication in the new cut formula and the new canonical-weight operation are counted separately from the accepted induced-edge products that were not rerun.

## Saved reader and condition semantics

`openIndex(snapshot)` returns `{query, stats}`. It checks format and row count, indexes the saved rows by code, and loads the saved Pascal entries. It trusts the identified output; it is not a full certificate checker. It does not call the compiler or any old constructor.

A condition is passed as `filter` and may contain only:

| Field | Meaning |
| --- | --- |
| `min_deleted, max_deleted` | Inclusive deleted-edge bounds, default 0 through total edges |
| `min_size, max_size` | Inclusive selected-side sizes, default 0 through vertex count |
| `required` | Labels required on the canonical side containing 0 |
| `excluded` | Labels forbidden on that canonical side |

Bounds must be integers in range and in increasing order. Label arrays must have distinct valid integers. Vertex 0 is always implicitly required. Requiring and excluding a label, or excluding vertex 0, creates an empty family rather than silently changing the orientation.

Conditions are cached by their normalized bounds and sorted labels, with a cap of 24 distinct conditions per reader. When there are no explicit label restrictions, the reader uses the saved canonical multiplicities. With restrictions, it reads a retained occupancy and multiplies saved binomial coefficients for the remaining free labels in each part. These are new conditional products, explicitly counted as reader work. They do not rebuild old occupancy rows or the old Pascal table.

Every condition retains all admitted row IDs, their new weights, cumulative prefixes, fixed labels and free-label pools. The `conditions` operation exports these complete records. The actual packet includes all eight created conditions. Opening a snapshot does not import an exported condition cache; a new reader creates conditions when queried.

Family order is: deleted-edge count ascending, then old occupancy code ascending, then lexicographic combinations within each part. Part 0's local combination rank is the most significant component of the product order. Ranks are not increasing bit-mask or global sorted-vertex-list order.

Within each part, required labels are fixed and free labels are selected in lexicographic combination order using the saved Pascal entries. Selection and inverse ranking use that same convention. All returned cuts have vertex 0 on the selected side.

## Operations

| Operation | Fields | Result |
| --- | --- | --- |
| `summary` | none | Saved finite sizes, optimum and count |
| `distribution` | none | Every deleted-edge cost, count and occupancy-row count |
| `family` | optional `filter` | Exact condition summary and canonical-cut count |
| `select` | `rank`, optional `filter` | One canonical selected side with occupancy and local ranks |
| `page` | `start, limit`, optional `filter` | A bounded sequence of selected cuts |
| `classify` | `vertices` | Canonical orientation and saved row/cut/deletion information |
| `rank` | `vertices`, optional `filter` | Rank in the conditioned canonical family, or null with reason |
| `repair` | `rank`, optional `filter` | Selected cut plus explicit deleted and kept edge lists |
| `conditions` | none | Complete current condition cache |

Ranks and starts are canonical nonnegative decimal strings of at most 4,096 characters. Page limits are integers from 0 through 1,000. Selection rejects ranks outside its family. A page at the family count is empty; a larger start is rejected.

`classify` and `rank` accept either orientation of a vertex bipartition. If the supplied side omits vertex 0, they replace it by its complement and report `input_complemented: true`. All size, required and excluded conditions apply to that canonical side, not the originally supplied orientation. A rank request outside the selected family returns null with a label or cost/size reason.

The `repair` operation materializes the declared host's edges for the requested cut, separates within-side deleted edges from crossing kept edges, and checks their lengths against the saved counts. This is fresh query witness materialization. It is not reconstruction of the occupancy table or recompilation of the cut distribution. It reports whether the selected deletion count equals the saved global minimum.

Example usage, assuming the saved JSON has been parsed as `snapshot`:

```javascript
const {openIndex} = require("./saved_cut_repairs.cjs");
const reader = openIndex(snapshot);
const minimum = {min_deleted: 36, max_deleted: 36};
reader.query({op: "family", filter: minimum});
reader.query({op: "select", filter: minimum, rank: "157"});
reader.query({op: "repair", filter: minimum, rank: "0"});
```

These snippets document the interface. The actual execution is retained in the reader file.

## Actual finite families and witnesses

| Condition on canonical side | Cuts | Occupancy rows |
| --- | ---: | ---: |
| All cuts | 536,870,912 | 14,406 |
| Minimum deletion count 36 | 315 | 35 |
| Side size 15 | 77,558,760 | 1,271 |
| Minimum deletions and side size 15 | 100 | 6 |
| Minimum deletions and label 6 required | 63 | 11 |
| Minimum deletions and label 6 excluded | 252 | 29 |
| Minimum deletions and labels 6,12 required | 0 | 0 |
| Minimum deletions and label 0 excluded | 0 | 0 |

The 100 equal-size minimum cuts are a restricted part of the full 315-family. Balanced sides are not imposed on the general bipartization problem.

Selected minimum repairs have:

| Rank | Old occupancy code | Occupancies | Canonical side size |
| ---: | ---: | --- | ---: |
| 0 | 300 | [6,0,6,0,0] | 12 |
| 157 | 2106 | [6,6,0,6,0] | 18 |
| 314 | 14706 | [6,0,6,0,6] | 18 |

All have 36 deleted and 144 kept edges. Three complete requested edge witnesses are retained. The full minimum-family page exports all 315 canonical selected sides, which determine their deletion sets uniquely by the proved connectedness argument. It does not materialize all 315 edge lists.

The first minimum cut's complementary input side ranks back to zero and is explicitly marked complemented. Empty and full input sides classify to the same canonical all-vertex side. The last rank in the unrestricted family is 536870911, with old code 16806 and all 180 edges deleted. The last equal-size minimum rank is 99, with code 14703.

## Actual reader work and limits

The fresh reader retained 33 complete outputs and seven exact rank comparisons: three minimum-family selections, the complement normalization, two unrestricted selections and one equal-size minimum selection. Its final counters were:

| Counter | Actual |
| --- | ---: |
| queries | 33 |
| rows_indexed | 14,406 |
| condition_rows_scanned | 29,022 |
| occupancies_decoded | 429 |
| binomial_lookups | 7,199 |
| conditional_products | 341 |
| prefix_additions | 15,758 |
| conditions_created | 8 |
| cache_hits | 19 |
| combination_steps | 5,203 |
| rank_search_steps | 16,190 |
| repair_edge_visits | 540 |
| old_occupancies_built | 0 |
| old_edge_products | 0 |
| pascal_cells_built | 0 |

The 540 edge visits are the three requested 180-edge materializations. Counters measure their named paths, not all arithmetic or copying. Rank searches and condition scans are genuine fresh query work; the no-replay claim concerns the old constructors and the new cut compiler, not an absence of all reader computation.

The complete snapshot, source lineage and saved conditions bound the evidence. They establish this finite cut/deletion family for the identified graph. They establish no universal triangle-free graph theorem, no new sharpness construction, no source-proof validation and no prize entitlement.
