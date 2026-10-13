# Simultaneous rational extensions of a fixed well-separated prefix

This package consumes exact saved output from [Commons #31397](https://github.com/woahwhattheheck/commons/pull/31397). It answers a new finite question: which of its selected individual extensions can be adjoined simultaneously, and which compatible subsets optimize cardinality or added reciprocal sum?

There are **19,008 compatible subsets** of the declared 17 candidates. The maximum cardinality is **11**, attained by **40 subsets**. The exact added reciprocal objective has a unique optimum at cardinality 11 for this input. The API keeps these objectives separate; it does not assume that a largest subset maximizes an arbitrary weight.

## Exact input and source boundary

The inherited prefix is [5,7,12,17,32]/2. Candidate labels 0 through 15 have numerators

```text
38,53,58,82,87,88,93,117,122,123,138,142,158,163,172,173
```

Label 16 is the exact huge numerator in input.json, copied from /retained_consumer/selected of the predecessor. Every candidate has denominator 2. Input order is fixed and strictly increasing. The predecessor data are complete blob 48d645fb1542516cdd9736d38dbcb79268890f72 (582,171 UTF-8 bytes), at merge 8ec65a111535d96b69ee67cac4c48d4962d6fc5a, path research/ppl014_erdos143_grid_extensions/rational_prefix_extensions.json. Its guide is c349d05ebe13d68662f2398dd792d777a04b3463 (22,525 bytes). Both were independently matched on acquisition.

Individual compatibility with the prefix is an input premise. The saved 87/2,88/2 obstruction is likewise an inherited edge. No old membership, prefix pair, residue, CRT join, huge-rank selection or proof was repeated. The new calculation covers only the remaining 135 candidate pairs.

The full FormalConjectures/ErdosProblems/143.lean file, requested at main, returned blob bcefb3101e1f6fdb87665ecd4dc0a1cfa532d58d. Its ordered-pair condition is |kx-y| >= 1 for all distinct elements and all positive integers k; its complete set definition is countably infinite and contained in (1,infinity). This API addresses a finite selection, so it does not instantiate that infinite-set hypothesis.

The intake [PPL014](https://prizeproblems.org/problems/014/) and formal file have open labels. The predecessor guide separately records the dated Koukoulopoulos–Lamzouri–Lichtman (2025) logarithmic-density theorem attribution and its lower-natural-density consequence. That attribution is inherited without reviewing its external proof here. The general reciprocal-log convergence question remains distinct. No current prize, novelty or general resolution is claimed. See SOURCE_QUALIFICATION.md for the precise read and interpretation boundary.

## New pair reduction

For positive ascending numerators a<b, write b=qa+r with 0<=r<a. Since q>=1, q and q+1 are valid positive multipliers. The minimum forward scaled distance is min(r,a-r). In the reverse direction the minimum is b-a at multiplier 1, and the forward minimum is no larger. Consequently the pair is a conflict exactly when min(r,a-r)<2. A scaled distance of 2 is allowed, corresponding to distance 1 before scaling.

Each new pair row stores its quotient, remainder, nearest multiplier and scaled distance as exact decimal integers. When the two nearest multipliers tie, the floor multiplier q is retained. The inherited 87/88 row deliberately has no newly calculated quotient or remainder.

The eight conflict edges are:

| Labels | Numerators | Provenance |
| --- | --- | --- |
| 1,12 | 53,158 | New |
| 2,7 | 58,117 | New |
| 2,15 | 58,173 | New |
| 3,13 | 82,163 | New |
| 4,5 | 87,88 | Inherited |
| 4,15 | 87,173 | New |
| 8,9 | 122,123 | New |
| 14,15 | 172,173 | New |

An independent subset of this graph is precisely a simultaneous addition to the fixed prefix, conditional on the inherited memberships.

## Family and objective certificate

For each available-label mask M, the saved DAG branches at its least label v. The exclusion child is M without v; the inclusion child also removes all neighbors of v. These are disjoint and exhaustive alternatives. The empty mask has one subset of size zero.

For every cardinality k, each node retains:

- counts[k]: number of independent subsets of size k.
- best[k]: maximum exact scaled reciprocal weight, or null if no such subset exists.
- ties[k]: number of subsets attaining that optimum.

The common denominator D is the product of the 17 candidate numerators, computed once. The weight of label i is 2D/a_i, an integer. A saved weight W therefore means the exact added reciprocal sum W/D. Fractions are deliberately not reduced. This is the sum over added candidates only; the prefix's constant contribution is not included.

The constructor's root coefficient vector, for k=0 through 11, is:

```json
[1,17,128,565,1628,3221,4472,4363,2935,1298,340,40]
```

Each fixed-cardinality optimum is unique. Their label sets, in increasing cardinality, are saved completely in saved_reader.json. The unrestricted optimum has labels

```json
[0,1,2,3,4,6,8,10,11,14,16]
```

The huge candidate has no conflict in this declared graph. Requiring it leaves 9,504 subsets and all 40 size-11 maxima; excluding it leaves 9,504 subsets with maximum size 10 and 40 maxima. These are actual saved query results, not a claim about other large candidates.

## Reader API

```javascript
const {createReader} = require("./simultaneous_extensions.cjs");
const certificate = require("./certificate.json");
const reader = createReader(certificate);

// Arguments below describe new consumer calls; the publication's actual
// completed calls are already saved and need not be replayed.
reader.condition(16, 0); // require label 4; exclude none
reader.select({required:0, excluded:0, size:11, rank:0});
reader.rank({required:0, excluded:0, size:11, mask:/* selected mask */ 0});
reader.page({required:0, excluded:0, size:11, start:0, limit:10000});
reader.marginals({required:0, excluded:0, size:11});
```

Masks are nonnegative safe integers below 2^17. Required and excluded labels must be supplied as masks. A required conflict or required/excluded overlap defines an empty family and returns an explicit reason. Required labels remove their neighbors from the remaining graph. Excluding every label yields the singleton empty-subset family.

Cardinality is always the total number of selected candidates, including required labels. Rank is zero-based within that cardinality and condition. Ordering is lexicographic on the full input-label incidence vector, with 0 before 1. This is not increasing numeric mask order. Forced bits are identical in every member of a condition, so omitting them from recursive branching preserves this order.

select returns FOUND or OUT_OF_RANGE. rank returns FOUND or NOT_IN_FAMILY. The optional optimal:true restricts navigation to subsets attaining the maximum weight at that specified cardinality; it does not mean maximum cardinality or unrestricted optimum across all sizes. page is bounded by a limit at most 10,000. marginals returns, for each label, the number of size-k members containing it and the corresponding number among the original condition's size-k optimum family.

Returned rows retain mask, labels, exact numerator list and unreduced added reciprocal sum. summary exposes the full condition; condition returns its entire cardinality, optimum and tie vectors. snapshot returns all currently saved states and conditions. The reader trusts the identified certificate after a schema-tag check; it is not an adversarial certificate verifier.

## Actual retained consumer

The completed reader produced **182 full responses**, with **72 rank/select inverses, all matching**. It exported all **40 maximum-cardinality subsets** and all **12 fixed-cardinality optimum pages**. Every request was retained before invocation, and every response plus latest caches/work immediately afterward. There were no failed queries or lost responses.

Ten explicitly requested conditions gave:

| Condition | Subsets | Largest size | Largest-size count |
| --- | ---: | ---: | ---: |
| Full | 19,008 | 11 | 40 |
| Require 87/2 | 5,184 | 11 | 16 |
| Require 88/2 | 6,912 | 11 | 24 |
| Require both 87/2 and 88/2 | 0 | None | 0 |
| Require huge candidate | 9,504 | 11 | 40 |
| Exclude huge candidate | 9,504 | 10 | 40 |
| Require 38/2, exclude 53/2 | 6,336 | 11 | 20 |
| Exclude all candidates | 1 | 0 | 1 |
| Required/excluded overlap | 0 | None | 0 |
| Require 117/2 | 6,912 | 11 | 24 |

Two complete marginal vectors are also retained. Marginal queries create additional conditions, so the final cache contains 38 distinct conditions rather than only the ten named rows.

The constructor retained 87 DAG states and 641 coefficient cells, with 135 new pair distances, one inherited witness, 17 product factors and 17 exact weight divisions. The reader used those saved states and added 432 conditional states and 3,336 coefficient cells, for 519 retained states in its final snapshot. Additional actual reader counters are:

```json
{
  "newNodes": 432,
  "savedNodeHits": 8099,
  "coefficientCells": 3336,
  "conditionsBuilt": 38,
  "conditionHits": 243,
  "requiredAdjacencyReads": 51,
  "requiredWeightAdds": 51,
  "selectionBranches": 1628,
  "rankingBranches": 916,
  "rowsMaterialized": 124,
  "marginalConditions": 34,
  "newPairDistances": 0,
  "newWeightProducts": 0
}
```

These counters describe the named implementation operations, not elapsed performance or all JavaScript arithmetic. The query phase performed no pair-distance or base weight-product reconstruction. It did carry out new conditional recurrence arithmetic, required-weight additions, navigation and output materialization.

## Files and recovery

- simultaneous_extensions.cjs: constructor and saved-data reader.
- input.json: exact inherited candidate selection, obstruction and lineage.
- construction_plan.json and SOURCE_QUALIFICATION.md: declared scope before production.
- certificate.json: all 136 pair records, adjacency, exact weights and complete base DAG.
- reader_consumer.cjs and reader_plan.json: frozen actual consumer and plan.
- saved_reader.json: all 182 responses, complete exports, inverse comparisons, final caches and work.
- public_checkpoints.json: acknowledged source, result, reader-plan and reader manifests.
- README.md: entry point and bounded result.

Source/input/plan were native-blob checkpointed before the once-only constructor. Its complete result was checkpointed before the reader, and reader source/plan before the first query. The complete reader was checkpointed before documentation and publication. The later frozen-spec manifest is reported with the release; its omission from its own file set avoids recursive content identities. Public manifests contain eligible public artifacts and lineage, not private provider envelopes or private journal locators.

The certificate is 107,840 bytes with Git blob 28f21e220b6d9bce2d612643646b1afdbbdc8259. The complete reader is 743,511 bytes with Git blob eb58c939e5f5107742256e5c8f7086a2c182432a. These are full outputs, not samples or hashes standing in for missing data.

The finite graph and its navigation do not establish density, convergence, infinitude, a new extremal bound or sponsor acceptance.
