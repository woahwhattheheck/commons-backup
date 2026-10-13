# Weak vertex colors of a retained six-vertex hypergraph

This package counts and navigates weak vertex colorings of one declared three-uniform hypergraph and all its edge-deleted subhosts. Its selected ten-edge host needs three colors, while every proper edge-deleted subhost admits two. The data retain all 1,024 subhosts and 7,168 partition coefficients. This is an exact finite instance result, not a characterization of the obligatory hypergraphs in Erdős 593.

## Source, input and limits

The observed [Formal593 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/593.lean) asks which finite three-uniform hypergraphs appear in every three-uniform hypergraph whose chromatic cardinal exceeds aleph-zero. Its main statement was annotated research open and contained a local placeholder. It also mentioned a claimed 2026 resolution; that paper, claim and proof were not reviewed here. FORMAL593_OBSERVED.lean is the exact observed 11,001-byte text, Git blob 6cc3add95776e0b6a298380dc9fe0dc8baa5688e. The retrieval used the provider default ref; no immutable source commit was established. Its known common-pair example and proofs are not rerun.

Wang, Duan, Gerbner and Karim, [On the largest chromatic number of F-free hypergraphs](https://arxiv.org/abs/2604.21551), arXiv:2604.21551v1, 23 April 2026, distinguish weak coloring (no monochromatic hyperedge) from strong coloring (every hyperedge rainbow). Only their abstract definitions were consumed. This API uses the weak condition: at least two colors on every triple, with no requirement that all three colors differ. No source theorem or current-resolution claim is supplied by this finite calculation.

The input is copied from [Commons #31875](https://github.com/woahwhattheheck/commons/pull/31875), immutable merge 893679c58fefb9f078b2b4c42d11071b8ac93336:

| Retained input | Bytes | Git blob |
|---|---:|---|
| research/erdos564_complementary_colorings/input_source_zdd.json | 73,553 | 757074345d97912fd223987f279199bdf91bd5db |
| research/erdos564_complementary_colorings/reader_outputs_00.json | 183,507 | 39f7dd787065375681d877dcd976d247df8642ea |

Both complete provider contents and independent Git blob identities matched before new work. Saved reader record 23 selects the size-ten red member at rank 19,162: mask 520961 and source triple indices [0,8,9,12,13,14,15,16,17,18]. Record 23 is read as input, not recomputed. The old red/blue edge-coloring classification, source ZDD, K4-free census and rank operation are not invoked.

Vertices remain labelled 0 through 5. Local edge labels 0 through 9 are the following copied triples, in order:

| Edge | Vertices |
|---:|---|
| 0 | 0,1,2 |
| 1 | 0,3,5 |
| 2 | 0,4,5 |
| 3 | 1,2,5 |
| 4 | 1,3,4 |
| 5 | 1,3,5 |
| 6 | 1,4,5 |
| 7 | 2,3,4 |
| 8 | 2,3,5 |
| 9 | 2,4,5 |

A subhost mask selects retained edges and keeps all six vertices. Mask 0 therefore has chromatic number 1, not 0. Property B here means the existence of a map into two labelled colors; unused labels are permitted. Partitions consist of nonempty, unlabelled vertex classes. Labelled palette colorings and partitions are different counted objects.

The original intake activity was claimed and read back before construction. Its Slack ownership lookup returned only that intake. The exact Commons PR query returned a secondary 403 and was held without retry or alternate acquisition; PR ownership coverage is incomplete. The claim is not an assurance of global absence of related work.

## Construction and direct counting argument

Every partition of the labelled vertex set has one restricted-growth string: start at 0 and number each new block at its first occurrence. The compiler enumerates these strings once and records the corresponding blocks. For each partition pi it forms B(pi), the mask of input triples that are monochromatic, and A(pi), the complementary allowed-edge mask.

For a selected subhost H, pi is a proper weak coloring partition exactly when H is a subset of A(pi), equivalently H & B(pi) = 0. Initializing one coefficient at (A(pi), number of blocks) for each partition, followed by a superset zeta transform over the ten edge bits, consequently gives

    c(H,k) = number of proper partitions of the six vertices into k nonempty classes.

This establishes all coefficients without enumerating separately for every H. A proper coloring with labels 0,...,q-1 determines one such partition, and each k-block partition has exactly (q)_k injective assignments of labels to its canonical blocks. Therefore

    P_H(q) = sum_k c(H,k) (q)_k.

Repeated labels within a block are allowed; distinct blocks receive distinct labels. Empty palette q=0 admits no coloring because the vertex set is nonempty. These are direct finite counting arguments for the declared implementation, not source-attributed new theorems.

The one construction retained 203 partitions, 2,030 monochromatic-edge checks, 203 initial coefficient increments, 7,168 coefficient cells, 35,840 zeta additions and 1,023 size recurrences. Its prior edge-coloring call counter is zero. The compiler supports declared inputs with 1 to 8 vertices and at most 16 distinct increasing triples; this saved input uses six and ten. This is exponential preprocessing in the edge count, not a general efficient hypergraph-coloring claim.

## Exact results

For the full host the coefficient vector, indexed by k=0,...,6, is

    [0, 0, 0, 45, 55, 15, 1].

Thus its weak chromatic number is 3. It has 116 proper unlabelled partitions in total, 45 minimum partitions, and 270 colorings with a labelled palette of size 3. Its palette polynomial in the falling-factorial basis is

    45(q)_3 + 55(q)_4 + 15(q)_5 + (q)_6.

All 1,023 proper edge-deleted subhosts are two-colorable. The empty subhost has chromatic number 1; every nonempty proper subhost has chromatic number 2. This is a finite inclusion-minimal failure of Property B for the specified host, with no novelty or general classification claim.

Deleting local edge 0,1,...,9 leaves respectively 6,2,2,2,4,2,2,4,2,2 labelled two-colorings. The saved first three-color assignment is [0,0,1,0,1,2]; it is reader output, not an imported published example.

The seven retained partition conditions have 116,45,23,93,0,1,26 members. They include equal-color and different-color requirements, an impossible request that makes edge {0,1,2} monochromatic, and the one-block partition of the empty subhost. Four edge-subhost conditions have 1,023,10,70,0 members. The final empty condition requires the full host to have chromatic number at most 2.

## Saved API and ordering

Use the saved loader without invoking compile:

```javascript
const {loadSavedIndex} = require('./load_saved_index.cjs');
const index = loadSavedIndex();
const family = index.condition({blocks: 3});
const first = index.partitionSelect(family.key, 0);
const rank = index.partitionRank(family.key, first.rgs);
const paletteCount = index.conditionedCount(family.key, '3');
```

The example explains the API; the committed evidence is saved_reader.json. Loading performs structural setup, not a replay of the construction proof. The reader trusts the identified certificate's mathematics.

| Method | Result |
|---|---|
| summary() | Saved input summary and full-host row |
| row(mask) | Saved size, chromatic number, two-coloring count and coefficients |
| count(mask,q) | Exact labelled palette count from saved coefficients |
| condition(filter) | Cached proper-partition family and counts by block number |
| partitionSelect(key,rank) | Partition at zero-based rank |
| partitionRank(key,rgs) | Its rank, or null if absent |
| conditionedCount(key,q) | Exact labelled palette count for the condition |
| coloringSelect(key,q,rank) | Labelled vertex colors, canonical partition and block labels |
| coloringRank(key,q,colors) | Coloring rank, or null if it fails the condition |
| subhostCondition(filter) | Cached family of edge masks |
| subhostSelect(key,rank) / subhostRank(key,mask) | Navigation of that family |
| exportCaches() / work() | Complete current caches and query-work accounting |

Partition filters are available (edge mask, default 1023), blocks (optional exact count), together (vertex pairs required equal), and apart (pairs required different). Contradictory equality/difference conditions produce empty families. Partition-only order is the restricted-growth order inherited from the compiler. A partition RGS must be canonical; arbitrary renamings belong in coloringRank, which canonicalizes actual color labels.

Palette colorings are ordered by increasing number of blocks, then the retained restricted-growth partition order at that block count, then lexicographic injections of distinct palette labels into canonical blocks. This is not lexicographic order of the six-entry color vector. Counts, palette sizes, ranks and color labels may use arbitrarily large nonnegative integer strings; large outputs are decimal strings. Unsafe numeric inputs are rejected. The production consumer uses palette 10^30+7 and first/middle/last valid ranks without enumerating that palette.

Injection selection chooses each unused label by its rank among remaining labels. Its block size is the falling factorial for the remaining choices. The inverse counts unused labels below each chosen label and adds the same blocks. These are the usual quotient/remainder and prefix-count inverse operations. Rank/select on an empty family is not scheduled by the consumer; selecting an out-of-range rank throws.

Subhost filters are available, include, exclude, size, max_chromatic. Included/excluded edges must belong to available and cannot overlap. The order is increasing integer edge mask. The condition refers to the saved full six-vertex subhost; it is not a vertex deletion filter.

## Production evidence and recovery

The source, input, construction plan and observed Formal text were independently hashed and acknowledged by native Git create_blob calls before construction. The complete 300,350-byte result was acknowledged as 2d6e21db80da226d94850ded7614b2507afc8212 before reader use. The reader source and plan were also checkpointed before execution. Every reader request was retained before invocation; every complete response, cache state and work state was retained immediately afterward.

The reader finished with 140 complete responses and 39 inverse comparisons, all matching. Its complete 112,241-byte evidence was acknowledged as f8d5215f38c71c7e5063dd9798551aecdea4032f. No reader failure occurred. Seven partition caches, four subhost caches and five palette falling-factorial caches are included, not merely query summaries.

Fresh reader work comprises 1,024 structural rows, 1,421 saved partition scans, 805 pair-constraint checks, 38 saved row lookups, 4,096 subhost scans, 114 falling-factorial multiplications, 340 palette products, 322 additions, 175 rank comparisons and 64 injection steps. It generated no new partitions, performed no monochromatic-edge classification and ran no zeta transform. These are actual counters for the one consumer, not timing or asymptotic benchmarks.

public_checkpoints.json contains public acknowledged identities and input lineage. It omits private provider and Slack envelopes. A computed identity is not itself a claim that a blob was stored; the manifest marks acknowledgements separately. Full native journals and the publication receipt stay with the operational custody record.

The finite coefficients and rank examples neither resolve the uncountable-chromatic problem nor verify any external claimed proof. The source status, exact fixed input and finite query evidence delimit this contribution.
