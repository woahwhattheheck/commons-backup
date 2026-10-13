# Distinct-distance supports of subsets of a saved rational-circle host

This package classifies all 65,536 subsets of sixteen specified points from the saved rational-circle metric in [Commons #31706](https://github.com/woahwhattheheck/commons/pull/31706). It records the set of positive distance values determined by each subset, the complete joint cardinality/distance-count histogram, every fixed-cardinality minimum and its multiplicity, and the maximum number of vertices retained under each distinct-distance budget.

The declared host has 52 distance values across its 120 unordered pairs. Its eight-point subsets require at least nine distinct values, with exactly one attaining subset. All 189 fixed-cardinality minimizers across cardinalities 0 through 16 are exported in the first reader result. These are minima within this host only.

## Problem and source boundary

[PPL071](https://prizeproblems.org/problems/071/) binds this lane to Erdős #89. The fully read FormalConjectures statement, native and independently matched blob 710a3ea77cbbbab5a72b91537deb0791c0dec6e5 at requested main, is:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/89.lean

Its main conjecture asks for a uniform asymptotic lower bound of order n/sqrt(log n) on the least number of distinct distances among n planar points. It marks that question research open. Its n/log n lower-bound and grid upper-bound variants are marked research solved, while the local statements retain placeholders. Those source annotations are not a new proof or an independent audit of the literature. The file's implication proof was not used or replayed.

Guth and Katz, *On the Erdős distinct distance problem in the plane*, Section 2, printed page 5, defines d(P) as the set of nonzero distances between different points:
https://arxiv.org/pdf/1011.4105

Only this definition was used. It counts positive numerical values globally across pairs, not pair multiplicity or a fixed-vertex distance count. Reversing a pair cannot add a value. The retrieval header says arXiv 1011.4105v3, 28 June 2011; the extracted title page says 26 November 2024. The discrepancy is retained, not silently reconciled. No bound, proof, lattice construction, example or numerical table was imported.

The new package gives no lower bound for arbitrary planar configurations, no global extremal classification, no asymptotic result and no prize or novelty claim. It is a finite consumer of an identified earlier metric.

## Exact inherited metric and new host

The prior merge is e6199b8c226d938f56568887bf3ad03fd34acb5b. Its complete saved data and guide were acquired once and independently matched:

| Prior file | Git blob | UTF-8 bytes |
|---|---|---:|
| research/erdos212_rational_circle_polygons/farey10_anchored8_index.json | 230a6cb0c00631b1eccc15d01eaf550fdf343efb | 122,898 |
| research/erdos212_rational_circle_polygons/RATIONAL_CIRCLE_POLYGONS_API.md | 7bd547d2eab1aa954858ddd6bc9308efd04bd112 | 15,170 |

That record supplies 64 points, 2,016 exact chord lengths and 757 positive distance classes, sorted by rational length. Its coordinates, pair distances, class construction, anchored eight-vertex perimeter optimum, suffix recurrence and old reader outputs are inherited. The old implementation was not invoked. Reading its schema does not constitute a new proof of its metric.

The new host uses original vertex IDs

    [0,4,8,12,16,20,24,28,32,36,40,44,48,52,56,60].

Local bit i denotes original ID 4*i. This map remains fixed for every query; there is no quotient by rotation, reflection, isometry or graph isomorphism. The input includes the complete saved point records for provenance, but the compiler does not evaluate their coordinates.

Every local unordered pair i<j copies its source pair rank, source class ID and rational chord. For original IDs a<b in the 64-point record, the flat offset a*(128-a-1)/2+b-a-1 is used only to address a saved record. No chord formula is evaluated. Equal distances are inherited source-class equality, without new rational comparison or normalization.

The 52 used source IDs are sorted numerically and assigned local class bits 0 through 51. Source IDs already encode exact rational-distance order; this remapping is injective and retains each reverse source locator and its copied distance. Class records include every realizing pair of local vertices in this host. The shortest host class is source ID 61, length 552/2125, with local pairs [1,2] and [14,15]. Source class 0 exists in the original metric but is absent from this host.

## Complete subset recurrence

For a local vertex mask m, let S(m) be its set of realized local distance classes. Empty and singleton subsets have S(m)=empty; diagonal distance zero never enters the positive-distance alphabet.

For nonzero m, let v be its least set bit and r=m without v. Then

    S(m) = S(r) union { class(v,u) : u is in r }.

Every pair in m either avoids v and is already in S(r), or contains v and is added by the displayed loop. These alternatives cover all pairs. Boolean union collapses repeated values, so a class realized by several pairs contributes one support bit. Since r<m, increasing numeric mask order makes each prerequisite row available.

Each of the 65,536 rows stores

    [cardinality, distinct_distance_count, decimal_local_distance_support].

The row index is the vertex mask. Supports use BigInt and serialize as decimal strings; no 32-bit distance-mask truncation is possible. Vertex masks are safe 16-bit integers. Popcount gives the number of distance values. The joint histogram H[k][d] counts labelled vertex subsets with k points and d positive distances.

For every k, scanning the nonzero histogram entries gives the smallest d and the full number of ties. For a budget b, the largest k with sum_(d<=b) H[k][d]>0 is the maximum retained cardinality. Removing the complement needs 16-k vertex deletions. Its multiplicity counts all maximum-cardinality retained subsets with at most b distinct values; it is not restricted to those with exactly b. Taking complements is a bijection to the corresponding deletion sets.

A “distance budget” counts values. It is neither a bound on Euclidean length nor a selection of independently removable chord edges. All pairs induced by the chosen vertices remain present.

## Complete minima for this fixed host

| Retained cardinality | Minimum distinct distances | Number of attaining labelled subsets |
|---:|---:|---:|
| 0 | 0 | 1 |
| 1 | 0 | 16 |
| 2 | 1 | 120 |
| 3 | 2 | 18 |
| 4 | 3 | 7 |
| 5 | 4 | 2 |
| 6 | 5 | 1 |
| 7 | 9 | 9 |
| 8 | 9 | 1 |
| 9 | 13 | 1 |
| 10 | 18 | 5 |
| 11 | 22 | 1 |
| 12 | 24 | 1 |
| 13 | 34 | 2 |
| 14 | 37 | 2 |
| 15 | 48 | 1 |
| 16 | 52 | 1 |

The unique eight-point minimizer has mask 21397 and original IDs [0,8,16,28,32,36,48,56]. Its nine source distance classes are [138,179,279,322,458,494,593,631,756]. The complete reader also exports every tie at every other cardinality; the total across the seventeen minimum families is 189.

Examples of the saved distance-budget frontier:

| Budget | Maximum retained cardinality | Minimum deletions | Maximum-cardinality subsets within budget |
|---:|---:|---:|---:|
| 0 | 1 | 15 | 16 |
| 1 | 2 | 14 | 120 |
| 5 | 6 | 10 | 1 |
| 8 | 6 | 10 | 28 |
| 9 | 8 | 8 | 1 |
| 12 | 8 | 8 | 11 |
| 13 | 9 | 7 | 1 |
| 51 | 15 | 1 | 10 |
| 52 | 16 | 0 | 1 |

All budgets 0 through 52 are stored, including their complete optimum multiplicities. A negative budget is infeasible even for the empty subset, which has zero distances. A budget above 52 admits the same full family as 52; the reader reports both the requested and effective budget.

## Saved-certificate assembly and reader interface

The certificate is stored in sixteen consecutive row shards, each containing 4,096 rows, plus certificate_manifest.json. The manifest retains every non-row field and the exact original property order. Reconstruct without running the compiler:

```javascript
const {createReader} = require("./subset_distance_supports.cjs");
const manifest = require("./certificate_manifest.json");
const input = require("./input.json");
const fs = require("node:fs");
const path = require("node:path");

const rows = manifest.row_shards.flatMap(s =>
  JSON.parse(fs.readFileSync(path.join(__dirname, path.basename(s.path)), "utf8")).rows
);
const certificate = {};
for (const key of manifest.certificate_property_order) {
  certificate[key] = key === "rows" ? rows : manifest.certificate_header[key];
}
const reader = createReader(certificate, input.source_distance_class_count);
```

This snippet documents loading; it was not invoked as a second computation. The actual retained shard assembly was compared byte-for-byte to the original complete JSON serialization and matched its independently computed Git blob 173bf641180e38147934e798adb88d97e2bc557f (1,701,899 bytes). That full identity is computed, not an acknowledgement of a separately uploaded whole-certificate blob. Each shard and its assembly manifest has a native acknowledgement.

The reader trusts the identified certificate. Its schema check is not a hostile-input validator or proof checker. Callers must treat returned cached objects as immutable. source_distance_class_count must be the declared original count, 757.

All vertex constraints use local IDs 0..15. Distance constraints use source IDs 0..756 from the original metric. A required valid source ID absent from the selected host makes the family empty; an absent forbidden class removes nothing. IDs outside these domains are invalid. Duplicate constraint IDs are normalized to sets.

Inclusive min_cardinality/max_cardinality and min_distances/max_distances are safe integers. Lower bounds clip to zero; upper bounds clip to the fixed host dimensions. Reversed or disjoint ranges give empty families. Required/forbidden overlap is infeasible. A required distance means at least one selected realizing pair; forbidding it excludes every such pair among the selected vertices.

| Method | Contract |
|---|---|
| summary() | Returns fixed-host sizes, every cardinality minimum and complete budget frontier. |
| condition(q) | Returns exact family count, cardinality and distance-count marginals, maximum cardinality and minimum distance count. Saved internal masks remain in numeric order. |
| select({...q,rank}) | Returns the zero-based numeric-mask selection, original vertex IDs, local/source distance IDs and copied rational values. rank>=count gives OUT_OF_RANGE. |
| rank({...q,mask}) | Binary-searches saved eligible masks; returns FOUND with rank or NOT_IN_CONDITION. |
| page({...q,start,limit}) | Returns up to 256 consecutive materializations. start=count is an empty OK page; start>count gives OUT_OF_RANGE. |
| materialize({mask}) | Expands one saved row. It does not recompute pairs or distances. |
| marginals(q) | Counts admitted subsets containing each vertex or each distance class once. A class realized by several pairs still contributes one occurrence per subset. |
| distanceBudget({budget}) | Looks up the stored global fixed-host optimum. Negative budgets are INFEASIBLE; values above 52 use the final frontier row while retaining requested_budget. |
| snapshot(), work() | Return complete condition summaries/eligible-mask caches and reader counters. |

Count and rank outputs use decimal strings. Input ranks/page starts are canonical nonnegative decimal strings of at most 64 characters. Vertex masks are integers from 0 through 65,535. Numeric-mask order is not lexicographic vertex-list order or cardinality order. Filtering preserves numeric order.

The condition summary's minimum_distances is over the whole admitted family. To obtain a minimum at a prescribed size, restrict both cardinality bounds to that size. maximum_cardinality and minimum_distances are null for empty families.

## First actual reader use

The reader source and plan were native checkpointed before its one execution. Every actual request, response, latest caches and counters were retained before the next call. The complete result contains 223 responses, 32 cached conditions, 62 selection/rank comparisons with every comparison matched, and three complete vertex/distance marginal tables.

Each of the seventeen minimum families was exported in full, yielding all 189 attaining subsets. The other fifteen conditions were:

| Condition | Subset count | Maximum cardinality | Minimum distance count |
|---|---:|---:|---:|
| full | 65536 | 16 | 0 |
| requireVertex0 | 32768 | 16 | 0 |
| forbidVertex0 | 32768 | 15 | 0 |
| requireShortestHostClass | 28672 | 16 | 1 |
| forbidShortestHostClass | 36864 | 14 | 0 |
| requireLongestHostClass | 37888 | 16 | 1 |
| requireBothExtremeClasses | 20224 | 16 | 3 |
| allEightVertexSubsets | 12870 | 8 | 9 |
| distanceBudget9 | 4179 | 8 | 0 |
| requireOriginal0And32 | 16384 | 16 | 1 |
| absentRequiredClass | 0 | none | none |
| conflictingVertices | 0 | none | none |
| conflictingDistances | 0 | none | none |
| reversedCardinality | 0 | none | none |
| negativeDistanceBudget | 0 | none | none |

The complete-family vertex marginals are 32,768 for each of the sixteen vertices. The shortest-host-class condition has 28,672 subsets; its marginals count class presence once despite two realizing pairs. The minimum-distance eight-point condition has one member and its vertex marginals identify that subset.

The driver additionally requested eleven stored budget rows, including negative and overlarge inputs. An empty mask ranked against the eight-point family returned NOT_IN_CONDITION. Page start 12,870 returned an empty OK page, while 12,871 returned OUT_OF_RANGE. These are actual saved responses. No separate synthetic malformed-input suite was executed.

Constructor work:

```json
{
  "savedPairCopies": 120,
  "localClassAssignments": 120,
  "subsetRows": 65536,
  "supportUnions": 458753,
  "supportPopcountSteps": 1547392,
  "histogramUpdates": 65536,
  "budgetCells": 24327,
  "newCoordinates": 0,
  "newChordLengths": 0,
  "rationalComparisons": 0,
  "oldPerimeterStates": 0
}
```

Reader work:

```json
{
  "conditionsBuilt": 32,
  "conditionHits": 179,
  "rowsScanned": 1769472,
  "supportReads": 356353,
  "selectedRows": 288342,
  "rankComparisons": 548,
  "materializedRows": 251,
  "marginalRows": 94209,
  "marginalVertexChecks": 1507344,
  "marginalDistanceChecks": 4898868,
  "budgetLookups": 11,
  "newSubsetSupports": 0,
  "newCoordinates": 0,
  "newChordLengths": 0,
  "oldPerimeterStates": 0
}
```

The 458,753 support unions and 1,547,392 support-popcount steps are new subset work. The reader's 1,769,472 row scans build conditions from those saved rows, and its 251 materializations comprise 189 full optimum-page members plus 62 selections. Marginals scan 94,209 admitted rows across three queries. These counters describe instrumented paths, not every instruction, allocation or serialization.

No reader call creates a subset support, coordinate or chord length, or visits an old perimeter recurrence. No accepted E212 query, PPL149 rectangular-grid fiber computation, E97/E107 geometry or known lattice example is replayed.

## Files and public checkpoint provenance

- subset_distance_supports.cjs, input.json, construction_plan.json, SOURCE_QUALIFICATION.md: new code, exact copied input and scope.
- distance_rows_00.json through distance_rows_15.json plus certificate_manifest.json: complete construction.
- reader_consumer.cjs and reader_plan.json: prepared first consumer.
- saved_reader.part00.txt through saved_reader.part04.txt plus saved_reader_manifest.json: lossless exact text of all reader responses and caches.
- public_checkpoints.json: native acknowledged source/result/reader manifest chain.
- README.md: entry point.

Concatenate the five reader parts in listed order without separators, then parse JSON. That assembly was byte-identical to the complete 2,011,618-byte reader, blob 35cf678b241d0af727bd7b3c75d4758ea21b924c. Unlike the whole constructor identity, this whole-reader blob was directly acknowledged before packaging; the publication parts preserve those bytes and do not rerun queries.

Source/input/plan manifest: f363195677a9ad4f61841afd919f65fac4ed765b.
Complete constructor-shard checkpoint: 7c676a82ae3f5d23f3174ab2ad137f2371cebc7b.
Prepared-reader manifest: db54a8ace92345de1f8e2a683f18959db99eb0ee.
Complete-reader manifest: 2da03f6d97934fc1a0c855a86d549e65107aa7ae.

The final publication spec is frozen and native checkpointed separately after these files are prepared. Its later manifest cannot be embedded in its own files. Public checkpoints exclude private provider journals; native acknowledgement is not a promise of indefinite blob retention. All source and result identities distinguish copied premises, new calculations, native acknowledgements and mere computed assembly hashes.

The output is an exhaustive labelled subset classification for the sixteen declared points. Its extrema answer deletion and conditioning questions for that host. They do not determine the minimal number of distances among all planar configurations, establish the Erdős asymptotic conjecture, audit a solved variant, or claim sponsor acceptance or a prize.
