# Exact colorings after edge deletion

This module indexes how the proper colorings of a supplied finite graph change when edges are deleted. A canonical partition into at most q classes determines exactly which original edges must be removed. Grouping partitions by those required edge masks supports exact coloring count/rank/select, and joint navigation over a coloring and an edge-deletion set of a fixed cardinality. It does not enumerate all pairs in that joint family.

The actual input is the established 11-vertex Mycielski graph with 20 edges, with q=3. The once-only construction contains 29,525 canonical partitions and 23,114 distinct required-deletion masks. Every single-edge deletion admits three-colorings: seven canonical partitions for each of the five original cycle edges, five for each of the other fifteen edges. Consequently this graph is not an example of the one-edge robustness requested by the general existence problem. The original graph's chromatic number four and vertex criticality are imported from identified saved coefficient rows, not recomputed here.

## Mathematical objects and source boundaries

The vertex set is labelled 0 through n−1. The graph is simple and undirected; its supplied edge list fixes edge IDs. Deletion means removing a subset R of these edges while retaining all vertices. A coloring is proper precisely when the endpoints of every surviving edge have different colors. Extra deletion of an already bichromatic edge is allowed.

Martinsson and Steiner, *Vertex-critical graphs far from edge-criticality*, Combinatorics, Probability and Computing 34(1) (2025), 151–157, DOI 10.1017/S0963548324000324, published online October 11, 2024, define vertex criticality by χ(G)=k and χ(G−v)=k−1 for every vertex. Their spanning-subgraph formulation asks that χ(G−R)=k for every edge set of cardinality at most r. This is not restricted to inclusion-minimal deletion sets. If the term “inclusion-minimal lowering set” is used, it means no proper subset lowers χ; that property differs from minimum cardinality.

Direct primary source:
https://www.cambridge.org/core/services/aop-cambridge-core/content/view/183F811E2F0885A536C8FD1E1652C36B/S0963548324000324a.pdf/vertex-critical-graphs-far-from-edge-criticality.pdf

The bounded source inspection used the definitions and introductory formulation, not its proofs or numerical examples. An extracted single-edge equality on page 151 conflicts with the surrounding lowering convention; this guide uses the unambiguous spanning-deletion formulation and does not repeat that equality.

The complete separately read FormalConjectures source is:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/944.lean
at blob 949a83637303be3ff2616d823419e853041dfed4. It marks the all-k≥4, all-r≥1 assertion research open, the r=1 Dirac variant research solved, and the large-k-for-each-r variant solved. Local proofs remain placeholders. The linked external Lean proof was not opened or reviewed. These are source annotations, not an independently audited global theorem or status census.

The Mycielski construction is prior mathematics, credited to Jan Mycielski (1955). The precise graph and coefficient rows come from the accepted artifact identified below. The new result is finite response navigation; it makes no general critical-graph construction, novelty, extremal record, prize or sponsor-submission claim.

## Identified input and old work not replayed

The input was extracted from #31550, merge 885f220385cc6cc933622e59e5e71d156c3bae29:

- Path: research/ppl062_cochromatic_partitions/mycielski_partition_polynomials.json.
- Complete accepted blob: 0402c8ebcdab1a1d48209fa46a887e071aadd1f4.
- Fields consumed: constructor.snapshot.graph, and the original/full and eleven single-vertex-deleted rows of constructor.snapshot.modes.independent.minima and .coefficients.
- Graph provenance there points to #31448's original canonical edge list. Base vertices are 0..4, twins 5..9, apex 10.

The imported full-graph coefficient row is [0,0,0,0,520,4265,8938,7171,2590,445,35,1], with minimum four. Every imported vertex-deleted minimum is three: the coefficient of three is 12 for each base vertex, 5 for each twin and 20 for the apex. All twelve complete rows are retained in the new input and manifest. They remain explicit accepted premises. No graph generation, cut/component calculation, induced-subgraph partition coefficient computation or chromatic proof was replayed.

The new partition kernel includes colorings that are improper on the original graph, because their required deletions are precisely the new indexed object. Enumerating those canonical assignments is different from rerunning the old proper-partition recursion.

The supplied edge-ID list is:
0:(0,1), 1:(0,4), 2:(0,6), 3:(0,9), 4:(1,2),
5:(1,5), 6:(1,7), 7:(2,3), 8:(2,6), 9:(2,8),
10:(3,4), 11:(3,7), 12:(3,9), 13:(4,5), 14:(4,8),
15:(5,10), 16:(6,10), 17:(7,10), 18:(8,10), 19:(9,10).

## Canonical partitions and exact kernel argument

A restricted-growth string c has c[0]=0 and
0 ≤ c[v] ≤ min(q−1, 1+max(c[0],...,c[v−1])).
Its nonempty blocks are ordered by their least vertex. There is exactly one such string for each partition into at most q nonempty blocks. Color names are not distinct objects in the canonical family; labelled vertices remain distinct.

For a partition c, let M(c) be the set of original edges whose endpoints have the same c-value. The remaining graph G−R is properly colored by c if and only if M(c)⊆R. Necessity follows from any surviving monochromatic edge; sufficiency follows because every surviving edge then has differently colored endpoints. Thus a saved M(c) completely determines the deletion response of that partition. No future edge comparison is needed.

The compiler assigns vertices in increasing order. When assigning v it checks only original edges whose higher endpoint is v. That evaluates each edge at the stage where both endpoint colors are known, accumulates its required bit, and visits every restricted-growth string once. Rows are in lexicographic string order. The required masks are grouped without identifying different partitions that share a mask.

For j nonempty canonical blocks, the number of injective assignments of q named colors is the falling factorial (q)_j. Multiplying each canonical contribution by this factor gives named-color counts. With canonical fixed-color conditions, this counts all name lifts of the selected canonical partitions; it does not reinterpret the fixed integers as names in a separate labelled-color model. This distinction is explicit in the long output field name.

For a deletion budget h, a partition with s required edges permits C(m−s,h−s) deletion sets. Impossible binomial arguments contribute zero. Summing over saved required-size/block-count buckets produces the complete budget spectrum.

For conditional joint navigation, I is a mask of mandatory deletions and K a mask of mandatory retained edges. Reject a partition when M(c) meets K, or I meets K. Set B=M(c)∪I and F=E\(B∪K). There are C(|F|,h−|B|) admitted deletion sets for this partition, represented by choosing the extra deleted edges in F. An exact-deletion query instead gives weight one when its supplied R satisfies all constraints and contains M(c), and zero otherwise. Conditions on block count and canonical vertex colors filter the partition rows before weighting.

The cumulative row weights give count/rank/select. Within one row, increasing edge-ID combinations are ranked lexicographically using saved binomial values. Distinct partitions with the same deletion set are separate incidences. Counts of these pairs are not counts of distinct deleted-edge sets, and division by a common coloring multiplicity is generally invalid.

## Once-only construction and exact finite outcomes

The source and input were banked before execution. One build retained:

| Quantity | Value |
|---|---:|
| Canonical partitions into at most three blocks | 29,525 |
| Distinct required-edge masks | 23,114 |
| Search nodes | 44,293 |
| New endpoint-color comparisons | 177,136 |
| Saved binomial cells | 231 |
| Budget-spectrum coefficient additions | 337 |
| Minimum number of required edge deletions | 1 |

All rows and kernel member lists are retained. Work counters describe performed operations; they do not assert that every transient comparison event was stored as a separate record.

For singleton deletions, edge IDs 0,1,4,7,10 each admit seven canonical three-block colorings; every other edge admits five. Their named three-color counts are respectively 42 and 30. There are 110 total (single deleted edge, canonical coloring) pairs and 660 named-color pairs.

Because every singleton edge deletion is three-colorable, every nonempty deletion set is also three-colorable by retaining the coloring of any one contained singleton. Combined with the inherited original χ=4 premise, only the empty deletion set retains χ=4. This observation concerns this graph, not every vertex-critical graph. The index does not claim it as a new construction.

Selected complete spectrum entries:

| Deleted edges | Canonical partition/deletion incidences | Named three-color incidences |
|---:|---:|---:|
| 0 | 0 | 0 |
| 1 | 110 | 660 |
| 2 | 2,555 | 15,330 |
| 4 | 203,345 | 1,220,070 |
| 10 | 96,931,792 | 581,590,752 |
| 20 | 29,525 | 177,147 |

At budget four, exactly five incidences use two nonempty blocks. The saved page contains all five. This finite slice is not an old bipartization calculation replay; it is a query of the new kernel.

The module is bounded to 1≤n≤12, 1≤q≤3, at most 24 distinct simple edges and at most 100,000 partition rows. The actual 11-vertex q=3 consumer is the only compiler execution here. Other admitted inputs, including q=1, q=2 and small edgeless cases, were source-inspected only; no larger or duplicate calculation was added.

## Saved reader and actual queries

A separate fresh module instance opened the serialized manifest, all eight row files and all six class files. It did not call buildIndex. Thirty-three responses were banked individually, including the complete ten-condition cache response. No response was lost.

The reader exported all 110 budget-one incidences in pages of 64 and 46. Rank 55 has row 15769, canonical colors [0,1,0,2,2,0,1,0,1,1,2], and deletes only edge 10. Its inverse rank and row lookup are retained. The two exact singleton examples exported all seven and all five colorings.

Budget ten represents 96,931,792 incidences in 28,488 partition rows. First, middle and last selection/inverse-rank pairs are saved. Middle rank 48,465,896 has row 15671, colors [0,1,0,2,1,2,2,2,2,2,0], and deletion mask 204197, i.e. edge IDs [0,2,5,7,8,10,11,12,16,17].

The conditional budget-ten query requires edge 0 deleted, edge 1 retained, canonical color 0 at vertex 0 and canonical color 2 at vertex 10. It has 6,787,557 incidences in 6,429 partition rows; its middle selection and inverse are retained. These fixed integers refer to canonical block order.

Deleting all five apex edges, mask 1015808, gives 60 canonical partitions; its first 32 were exported, not all 60. Empty-family responses include no deletions, contradictory delete/keep masks, and an empty allowed block-count list.

Reader work:
295,250 saved-row scans; 19,849 partition-code decodes; 66,701 saved-binomial lookups; 1,050 cumulative-selection binary steps; 67 combination-ranking steps; 46,825 member checks for inverse ranks. New partitions, endpoint-color comparisons, kernel classes and binomial cells were all zero. These are fresh query operations on saved data, not a claim of zero arithmetic or constant-time queries.

The complete cache contains 35,104 member records across ten conditions. Its nine shard files retain every record, including zero-weight-family metadata in the reader manifest. They permit external use of the saved responses. openIndex itself starts an empty query cache; it does not automatically restore these condition caches or promise to skip scans for a new condition. Equal repeated conditions in one reader instance reuse its cache.

## API

The CommonJS module has no dependencies or I/O:
buildIndex(input), openIndex(index,rowShards), SCHEMA, SHARD, LIMITS.

Input fields are vertex_count, max_blocks, edges, provenance and optional inherited metadata. Provenance is required and is not mathematically authenticated by the module. Edge IDs follow input order; duplicate edges, loops and unordered endpoint pairs are rejected.

To open the published files, parse the manifest and assemble:

const assembled = {
  ...manifest.index,
  classes: manifest.class_files.flatMap(ref => parsedFiles[ref.file].classes)
};
const reader = openIndex(
  assembled,
  manifest.row_files.map(ref => parsedFiles[ref.file])
);

The caller supplies complete parsed files. The module performs structural row-order, range, shard, class-membership and coefficient-shape checks. It does not recompute masks, binomial arithmetic or complete partition coverage. It does not verify file hashes itself, and loading arbitrary JSON does not certify mathematical provenance.

Reader methods:

- summary(): graph/kernel summary, imported premises, complete singleton and budget spectra.
- row(id): canonical code, block count, required mask and decoded color string.
- rowForColors(colors): find a canonical restricted-growth string; arbitrary renamed colorings must first be normalized by the caller.
- kernel(id): full member row list for a required-deletion class.
- condition(spec): create or reuse a condition, returning its numeric ID, total decimal count, named-color-lift count and number of represented rows.
- select(conditionID,rank): select one canonical coloring/deletion incidence.
- rank(conditionID,rowID,deletedMask): inverse rank, or null if that row/mask is not admitted.
- page(conditionID,start,count): up to 64 consecutive selected incidences.
- caches(): full current condition caches, including cumulative row weights.
- work(): current operation counters; it does not increment query count.

A condition must supply exactly one of deleted (an exact edge mask) or budget (an exact integer cardinality). Optional must_delete and must_keep are masks; blocks is a list of distinct allowed block counts; fixed is a list of distinct [vertex,canonicalColor] constraints. Contradictory deletion/retention constraints and an empty blocks list are valid empty-family queries. Repeated fixed vertices are rejected rather than silently resolved.

All masks and row/condition IDs are bounded JavaScript safe integers. Counts, cumulative sums and ranks use canonical nonnegative decimal strings and BigInt arithmetic. Ranks accept at most 100 digits and are zero-based. A page may begin exactly at the count and be empty. select rejects an out-of-range rank; rank returns null for a structurally valid but nonmember pair.

A reader admits at most twelve distinct conditions and 300,000 cached member records. It scans all saved rows once per uncached condition. Fixed canonical-color filters decode candidate rows; these are counted. Cache capacity failures do not invalidate the original immutable index.

Rows are [base-q code, nonempty block count, required edge mask, required edge count, class ID]. Class order is numeric required mask. Condition members are [row ID, forced deletion base mask, free-edge mask, number of extra deletions, decimal weight, decimal cumulative weight]. Published condition shards prepend the condition ID to each member. Concatenate shards in start order and distribute by that first ID to recover the complete saved caches; no query execution is needed.

## Files, provenance and custody

Executed source: 84d36859e139ec26d655e2ac9b6d272c6decb877, 12286 bytes.
Input checkpoint: 7e78f2671f560809f25b48d2c661506c3f02b39d, 4953 bytes.
Complete once-only production checkpoint: 2b6d13e0eda77873d5c626f5fe26c0342313ced2.
Published construction manifest: 8e9ecfe98596ba8a63e4d949f11015f6cdde74ee.
Initial full reader checkpoint: 72713cb0763232e40d03b1c16d4b7bc0fbb419f9.
Published compact reader manifest: 1a405fa4ba0519aad751206bccc3789ac20a7c8d.

One local serialization attempt ended with ReferenceError “copy is not defined” before any provider call. The corrected step serialized the unchanged retained result. Neither buildIndex nor a reader query was rerun. All resulting file blobs were banked before publication. Source, complete construction and each reader response have distinct retained identities.

The two manifests name and pin their shards. Complete published data-file identities:

| File | Git blob |
|---|---|
| `partition_rows_00000_04095.json` | `d0cfdf038bf13c697c865dc70b70b81f74a4380e` |
| `partition_rows_04096_08191.json` | `573517192e1e5f69a91ab1b3e705e55d3f99c93a` |
| `partition_rows_08192_12287.json` | `d46e959d14b034fc27aa407f7e0718b1c1ffe0b0` |
| `partition_rows_12288_16383.json` | `91569beadd63bb4b80411b7e01b5ce4a00fe5937` |
| `partition_rows_16384_20479.json` | `0a3541145614565a29fae31e75af436ca9df29af` |
| `partition_rows_20480_24575.json` | `b74a912a88fcbd0cd4a21312aac80766d0602749` |
| `partition_rows_24576_28671.json` | `99ee09011bcad45356e089bbee41fa51b79ecb4b` |
| `partition_rows_28672_29524.json` | `0b6546e5678a24d4cf3dc9e9ed4bcf7c7f5d6525` |
| `kernel_classes_00000_04095.json` | `d5a30364327e4dbef3549e2251e1618c9a23a1b4` |
| `kernel_classes_04096_08191.json` | `ad563849861feaf22db8c53d87034ec0329beee0` |
| `kernel_classes_08192_12287.json` | `d331516cb59563d0154154c807d51147f09e6049` |
| `kernel_classes_12288_16383.json` | `3d7837cb312e6bdcfa8cebc91aa166839baff129` |
| `kernel_classes_16384_20479.json` | `0f349238d66a837c4e8311deeca0780de02759c2` |
| `kernel_classes_20480_23113.json` | `ce387b535c6750a0543694c2d39802aefa9bcf67` |
| `mycielski_coloring_deletions.json` | `8e9ecfe98596ba8a63e4d949f11015f6cdde74ee` |
| `condition_members_00000_04095.json` | `2336fd0b313a170f660bc56a0cabaa95f3e2fffc` |
| `condition_members_04096_08191.json` | `336c25f92f8119b1cae90fcb075c0ed1be2b3760` |
| `condition_members_08192_12287.json` | `a68dfb1139bc92878f78ee22cf7a00ead0e08e51` |
| `condition_members_12288_16383.json` | `80e0c9d73e426686d0651601d42b1c75f7e310b4` |
| `condition_members_16384_20479.json` | `643eb050cc732b3747176f637d3684cb26708c87` |
| `condition_members_20480_24575.json` | `09bc8b8747b2cefac56aafe07c664b1d0e16a274` |
| `condition_members_24576_28671.json` | `60cb996f6f78a1466ca25038e7ec14e6569965c3` |
| `condition_members_28672_32767.json` | `ffe38a14e53050684a1d0575d91bcb1c0e39f474` |
| `condition_members_32768_35103.json` | `458d462c18e3589d6deaa77d41fd814348b5b016` |
| `saved_reader_queries.json` | `1a405fa4ba0519aad751206bccc3789ac20a7c8d` |

The original graph and coefficient premises, current finite computation and source-status annotations have separate lineages. No linked proof, accepted graph calculation, sponsor communication, or prize submission was performed.
