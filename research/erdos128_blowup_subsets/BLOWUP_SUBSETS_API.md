# Labelled subsets of a finite graph blow-up

This package indexes every labelled vertex subset of a finite blow-up of a supplied simple graph by subset size and induced-edge count. Occupancy patterns replace explicit enumeration of vertex subsets; binomial multiplicities retain every label choice. Saved conditional families support exact rank, select and page operations, including required and excluded vertices.

The actual input is the classical uniform blow-up of C5 with five independent parts of size six: 30 vertices and 180 edges. Its 16,807 occupancy patterns represent all 1,073,741,824 labelled subsets. Among the 155,117,520 subsets of size 15, exactly 200 have the minimum of 18 induced edges. These are finite distribution and navigation results for this graph.

## Primary question and prior construction

Sergey Norin and Liana Yepremyan, *Sparse halves in dense triangle-free graphs*, arXiv:1311.5818v2 (February 10, 2015), state the sparse-half question in Conjecture 1.1: a triangle-free graph on n vertices should have a set of floor(n/2) vertices spanning at most n^2/50 edges. Their introduction attributes the conjecture to Erdős in 1975. It also describes the classical uniform C5 blow-up as the sharpness family: replace the cycle vertices by equal independent parts and cycle edges by complete bipartite graphs. That family and its sharpness credit are prior mathematics.

Primary account: https://arxiv.org/pdf/1311.5818

The fully read FormalConjectures file `FormalConjectures/ErdosProblems/128.lean`, blob `e6e5f1eff326ebb4db84ced00d848b1a975d4e37`, states the contrapositive-style question using all induced vertex sets V' with 2|V'|+1>=n, requiring strictly more than n^2/50 edges. For integer sizes this is |V'|>=floor(n/2). Its research-open annotation and local placeholder were retained without proof review. Neither that annotation nor the 2015 source is presented as an exhaustive current literature survey.

In a finite graph, an induced subset of size larger than floor(n/2) contains a subset of exactly that size with no more internal edges. Thus a sparse set of exactly half size suffices to refute the strict all-large-subsets premise for that particular graph. The present n=30 input attains the classical threshold 30^2/50=18, so it supplies no counterexample to the conjecture. No general triangle-free theorem, new sharpness construction or award claim is made.

## Declared finite graph

Parts are numbered 0 through 4. Part p contains the six labels 6p,...,6p+5. The base edges are the unordered pairs

```json
[[0,1],[1,2],[2,3],[3,4],[0,4]]
```

There are no edges within a part. Every base edge contributes all edges between its two parts. Hence there are five times 36, or 180, graph edges. The compiler inspected the ten triples of base vertices and retained no base triangle. Any triangle in the blow-up would need three different parts whose base vertices form a triangle, so the blow-up is triangle-free. The graph's individual 180 edges need not be enumerated.

The source family permits the choice of this finite size; the literal part size six is the declared consumer parameter. Earlier Mycielski, cut, partition and graph computations were not imported or repeated.

Input blob: `dbd71b5548b4c7670ed702d0056bafdcc198e28e` (939 UTF-8 bytes). The complete input is embedded in the index envelope.

## Complete occupancy representation

For part sizes w_0,...,w_(m-1), every labelled vertex subset has a unique occupancy vector x with 0<=x_i<=w_i. It has

```text
size(x) = sum_i x_i
edges(x) = sum_{base edge {i,j}} x_i*x_j
multiplicity(x) = product_i binomial(w_i,x_i).
```

The edge formula follows because each selected vertex in one endpoint part joins every selected vertex in the other, and the simple base-edge list counts each unordered graph edge once. The multiplicity independently chooses the selected labels inside each part.

Every admissible occupancy vector is stored exactly once, in mixed-radix code order:

```text
code(x) = sum_i x_i * product_{j<i}(w_j+1).
```

Part 0 is the least significant occupancy digit. The complete row sequence is split into contiguous shards, and each row records [size, edges, decimal multiplicity]. The occupancy vector is recoverable from its position/code and the saved radices; it is not necessary to repeat all vector entries in every row.

Summing multiplicities by (size,edges) gives the complete coefficient array of

```text
sum_x product_i binomial(w_i,x_i) * z^size(x) * y^edges(x).
```

This identity partitions all labelled subsets, including the empty and full subsets. Labels are not identified under graph automorphisms, cycle rotations, reflections or graph isomorphism. Equal occupancy or edge counts do not merge their individual label choices.

The saved size profiles give the minimum and maximum induced-edge count, each optimum's labelled multiplicity and number of occupancy patterns, and the total labelled count for every size. Their coverage follows from the complete occupancy enumeration, rather than a claim to enumerate every vertex subset.

## Construction and complete files

Executed source: `317025a36896e4d030232fd0318d582f43c3bf25` (13,184 bytes).
Index envelope: `444f907b1e45eb2a989b3ad8740730d193dc426a` (64,466 bytes).

| Occupancy codes | File | Blob | Bytes |
|:---|:---|:---|---:|
| 0–4095 | `occupancy_rows_00000_04095.json` | `103d1dbd0f08b8c6564453c7826f8c06f21efb5c` | 186076 |
| 4096–8191 | `occupancy_rows_04096_08191.json` | `e3539c013dcbb9ef2d7e03f5a73e0d19d4347e33` | 189968 |
| 8192–12287 | `occupancy_rows_08192_12287.json` | `be49ac00d5876618d5df19f04ac3b014a3d5dbe3` | 191071 |
| 12288–16383 | `occupancy_rows_12288_16383.json` | `60bfb5c4a54a51083fb29ce4c92b0e1e6ae45efc` | 188709 |
| 16384–16806 | `occupancy_rows_16384_16806.json` | `69333babc2751dfb5574c2dfd0fdbc131f8a34f8` | 19191 |

The source and input were inspected, syntax-parsed and banked before the one production construction. The complete result was stored, all five shards banked, and the index envelope then bound their names and exact identities. No occupancy enumeration was repeated to create the reader.

The compiler processed 16,807 occupancies, 84,035 occupancy coordinates, 84,035 edge products and 84,035 binomial factors. There were 16,807 histogram additions, producing 477 nonempty size/edge buckets. The complete distribution represents 2^30 labelled subsets.

At half size 15:

| Statistic | Exact value |
|:---|---:|
| Occupancy patterns | 1451 |
| Labelled subsets | 155117520 |
| Minimum induced edges | 18 |
| Minimum occupancy patterns | 10 |
| Labelled minimizers | 200 |
| Maximum induced edges | 54 |
| Maximum occupancy patterns | 30 |
| Labelled maximizers | 2000 |

All 200 minimum half-subsets were exported by the saved reader. Their first and last members use the order described below, not increasing whole-subset bitmask order:

```text
first: [0,1,2,3,4,5,12,13,14,15,16,17,18,19,20]
last:  [6,7,8,9,10,11,21,22,23,24,25,26,27,28,29]
```

Their occupancy codes are 1329 and 15477, respectively, with vectors [6,0,6,3,0] and [0,6,0,3,6]. Each minimum occupancy permits choosing three of six labels in one part, giving 20 subsets; ten such occupancies account for the 200 members. This is a finite multiplicity description of the saved family, not a new general sharpness proof.

## Conditions and family order

A query can restrict inclusive subset-size and edge-count ranges, and prescribe required or excluded vertex labels. Required and excluded lists are sets: duplicate labels in one list are rejected. If the two lists intersect, the family is empty.

For an occupancy x, let r_i be the required labels in part i and let f_i be the number of labels that are neither required nor excluded. The conditional multiplicity is

```text
product_i binomial(f_i, x_i-r_i),
```

with a binomial coefficient equal to zero outside its ordinary range. This counts every compatible labelled subset once. Conditional queries scan saved row attributes, decode relevant occupancies when required, and use the saved Pascal coefficients; they do not rebuild induced-edge products or the base histogram. Their new scans and products are counted explicitly.

The order first increases numerical occupancy code. Inside one occupancy, selected free labels within each part are ordered lexicographically as increasing tuples. The Cartesian combination of the part choices uses part 0 as its most significant inner rank. Required labels are inserted afterwards. The least-significant occupancy digit and most-significant inner part rank are separate conventions.

Each cached condition retains all admitted occupancy codes, exact multiplicities and cumulative counts. Selecting a rank first binary-searches those cumulative counts, then decomposes its within-occupancy rank across the part choices and un-ranks the combinations using saved binomial coefficients. Ranking reverses those steps. These ranks identify labelled subsets, not occupancy patterns alone.

## Reusable API

The dependency-free CommonJS module exports `SCHEMA`, `SHARD`, `LIMITS`, `buildIndex` and `openIndex`.

`buildIndex(partSizes, baseEdges)` accepts:

- Two through eight parts.
- Each part size from one through twelve.
- At most 60 total vertices.
- At most 100,000 occupancy patterns, the product of (part size+1).
- A simple undirected base graph: endpoint pairs in range, with no loops or duplicate edges. Pair orientation is normalized.

It returns `{index,shards}`. Generic inputs need not be triangle-free; all base triangles are reported. Calling the resulting blow-up triangle-free requires the empty-triangle premise and the stated argument. Only the present five-by-six input was executed; other branches within the declared caps were source-inspected.

`openIndex(index,shards)` requires every shard in the saved order. It clones the data and checks schemas, part and row counts, contiguous shard positions, row ranges, coefficient syntax, label partitioning and basic summary shape. It does not recompute occupancy sizes or edge counts, prove saved binomial identities, rebuild the histogram, or independently certify altered external data. Structural opening and construction provenance are distinct.

| Reader method | Result |
|:---|:---|
| `summary()` | Graph parameters, family totals and construction work |
| `profiles()` | Complete min/max/count profile for every subset size |
| `distribution(size)` | Every nonempty edge-count bucket at that size |
| `occupancy(code)` | Decoded vector and its saved attributes |
| `classify(vertices)` | Occupancy code and saved size/edge/multiplicity record |
| `family(condition={})` | Exact count, occupancy count and canonical condition |
| `select(condition,rank)` | Labelled subset and complete part-rank decomposition |
| `rank(condition,vertices)` | Rank and decomposition, or null with exclusion reason |
| `page(condition,start=0,limit=8)` | Consecutive selected subset records |
| `conditions()` | All cached complete conditional occupancy-prefix records |
| `work()` | Saved-index and new-query counters |

A condition accepts only `min_size`, `max_size`, `min_edges`, `max_edges`, `required` and `excluded`. Defaults cover the full graph. Bounds are inclusive and must be in range and correctly ordered. Vertex arguments are sorted, with duplicates rejected. At most 32 distinct conditions are cached. Page limits are at most 64; a page may start at the family size and return empty. A selection rank must be smaller than the count. Ranks accept nonnegative BigInt values, safe integers, or canonical decimal strings of at most 100 digits. Counts are serialized as strings.

The compiler's work grows with the product of the occupancy radices, not merely with the number of parts. This remains an exponential finite preprocessing method in general. Saved navigation is not a polynomial-time solution of the arbitrary-graph optimization problem.

## Actual reader queries

The fresh reader opened all five banked shards and retained 34 complete responses, seven complete condition records and work counters. Saved reader blob:

`2216fb1e698da4107ba40f94eeebaca865925383` (482,163 bytes).

| Condition | Labelled count | Occupancies |
|:---|---:|---:|
| Size 15, unrestricted edges | 155117520 | 1451 |
| Size 15, exactly 18 edges | 200 | 10 |
| Size 15, exactly 54 edges | 2000 | 30 |
| Size 15, at most 20 edges | 2000 | 30 |
| Size 15, 18 edges, require 0 and 12, exclude 6 and 18 | 40 | 3 |
| Size 15, 18 edges, require and exclude 0 | 0 | 0 |
| Size 14, at most 18 edges | 9615 | 60 |

Four pages export all 200 minimum half-subsets. Another page exports the complete 40-member forced-label family. Saved responses include minimum first/last select and rank, the middle and last full-half-family selections, rank 100,000,000, empty-family handling, and occupancy classification.

The middle full-half rank 77,558,760 has occupancy [3,3,3,3,3], code 8403, and 45 induced edges. Its selected labels are:

```json
[1,2,3,6,7,8,12,13,14,18,19,20,24,25,26]
```

The reader indexed 16,807 saved rows and 28 Pascal cells. New query work comprised 117,649 saved-row scans, 262 occupancy decodes, 5,478 binomial lookups, 28 conditional products, 1,584 cumulative-count additions, seven condition creations, 260 cache hits, 873 binary-search steps and 4,195 combination steps. Counters for occupancy-row construction, edge products and histogram-cell construction are all zero. The condition weights and combination arithmetic are new query work and are not described as precomputed results.

## Usage

This example shows opening saved files, rather than an additional execution:

```javascript
const fs = require('node:fs');
const path = require('node:path');
const { openIndex } = require('./blowup_subsets.cjs');
const envelope = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'cycle5_size6_index.json'), 'utf8'
));
const shards = envelope.shard_files.map(file =>
  JSON.parse(fs.readFileSync(path.join(__dirname, file.name), 'utf8'))
);
const index = openIndex(envelope.index, shards);
const minimumHalves = {
  min_size: 15, max_size: 15, min_edges: 18, max_edges: 18
};
index.family(minimumHalves);       // 200 labelled subsets
index.select(minimumHalves, '199');
index.page({ ...minimumHalves, required:[0,12], excluded:[6,18] }, 0, 64);
```

The package contains the source, this guide, the index envelope, all five complete occupancy shards, the saved reader responses and a README. Exact file identities in the index envelope bind the shard inputs. No graph or occupancy regeneration is needed for navigation.

These results classify subsets of one explicit labelled finite graph. They preserve the known C5 sharpness example and do not establish the conjecture for all triangle-free graphs, contradict its threshold, assert a new extremal record, or claim a current sponsor reward. No sponsor contact or submission occurred.
