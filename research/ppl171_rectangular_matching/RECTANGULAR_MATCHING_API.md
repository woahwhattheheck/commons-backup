# Exact rectangular bottlenecks for two fixed point clouds

This package provides exact joint bottleneck counts and navigation for the two declared nine-point clouds in the unit square. A matching is a labelled permutation: X row i is paired with Y column pi[i]. The API retains all 362,880 matchings through 512 suffix states rather than enumerating every permutation.

For a matching pi, its signature is the pair
\[
(b_x,b_y)=\left(\max_i |X_i^x-Y_{\pi(i)}^x|,\ \max_i |X_i^y-Y_{\pi(i)}^y|\right).
\]
All stored coordinates and bounds are integer numerators with common denominator 37. A condition (maxX,maxY) uses inclusive comparisons in both coordinates. The complete joint histogram has 403 signatures. Separate coordinate marginals would discard the correlation necessary to answer a rectangular query.

## Input and source boundary

The point labels in each cloud are independently 0 through 8. The coordinates below are integer numerators; divide each by 37.

| Label | X | Y |
|---|---|---|
| 0 | (1,4) | (2,26) |
| 1 | (4,31) | (6,7) |
| 2 | (8,13) | (10,35) |
| 3 | (12,22) | (14,15) |
| 4 | (17,3) | (18,29) |
| 5 | (21,35) | (23,2) |
| 6 | (26,18) | (27,24) |
| 7 | (30,9) | (31,12) |
| 8 | (35,28) | (36,19) |

These are declared deterministic inputs. They are not a random or i.i.d. sample, and no published numerical example was imported.

Michel Talagrand's [official matching statement](https://michel.talagrand.net/prizes/matchings.pdf) concerns independent uniform point sequences and a universal probabilistic bound on coordinate errors. Its printed indexing is inconsistent between the sequence and permutation; the finite indexing above is explicit. This tool supplies only fixed-cloud bottleneck navigation. It does not establish the source's exponential-moment bounds, a random-sample probability, a simultaneous asymptotic theorem, or the ultimate matching conjecture. The [PPL 171 card](https://prizeproblems.org/problems/171/) gives historical prize context; current eligibility, payment, novelty and sponsor submission are not claimed. SOURCE_QUALIFICATION.md records the read coverage and protected unrelated quota-cover work.

## Exact finite results

The complete Pareto-minimal thresholds are:

| maxX numerator | maxY numerator | Number of matchings at these bounds |
|---:|---:|---:|
| 2 | 33 | 1 |
| 6 | 13 | 2 |
| 10 | 6 | 1 |
| 14 | 4 | 1 |
| 33 | 3 | 1 |

A feasible pair of bounds contains at least one of these five pairs coordinatewise; the saved joint distribution establishes this statement for this input. The reader exports all six matchings belonging to the five minimal thresholds.

Bounds (20,20) admit 2,461 matchings, and (12,12) admit seven. At bounds (10,13), prefix [1] admits 13 completions. Each of the eight other one-column prefixes violates a coordinate bound on its fixed first edge. These counts are for labelled permutations; equal signatures do not identify matchings.

For example, bounds (5,13) give remaining X rows {0,2} only Y neighbor {1}. The two rows cannot both be matched injectively. At bounds (13,4), rows {1,5} have only neighbor {2}; at (32,3), rows {1,8} have only neighbor {4}. The saved reader contains these exact finite obstructions.

## Recurrence and completeness

Let mask encode the used Y columns and let i be its population count. The remaining rows are exactly i through n-1. For each unused column j, append edge (i,j) and recurse to mask with bit j set. Every permutation has a unique first remaining column, so these branches partition the completion family.

Each state's histogram maps the joint pair of suffix coordinate maxima to its exact multiplicity. The terminal full mask has one empty completion with maxima (0,0); all costs and accepted bounds are nonnegative. For edge cost (cx,cy) and a child histogram entry (x,y,count), the parent receives count at
\[
(\max(cx,x),\max(cy,y)).
\]
Aggregating equal pairs preserves multiplicity. Descending numeric mask order visits every child before its parent. Induction proves that every saved histogram contains every suffix completion exactly once. Counts use BigInt during accumulation and decimal strings in the certificate.

The frontier is read from the root histogram sorted by increasing x and then y. A pair is retained exactly when y is smaller than every earlier y. The first pair for a fixed x has its least y, so later pairs with that x are dominated. This yields exactly the undominated attainable signatures.

## Saved-reader contract

CommonJS usage:

~~~js
const { loadSavedIndex } = require("./load_saved_index.cjs");
const index = loadSavedIndex();
const family = index.condition({ maxX: 12, maxY: 12 });
const first = index.select({ maxX: 12, maxY: 12 }, "0");
const inverse = index.rank({ maxX: 12, maxY: 12 }, first.permutation);
const witness = index.obstruction({ maxX: 5, maxY: 13 });
~~~

The example demonstrates the interface; the published reader already contains the actual calls. Loading saved files assembles the certificate and does not call compile.

- summary() returns the saved total, signature count, frontier and construction counters.
- distribution(mask=0) returns the saved joint histogram for a used-column mask. A nonzero mask describes a suffix state, not a complete matching with an unspecified arbitrary row assignment.
- condition({maxX=37,maxY=37,prefix=[]}) validates an injective prefix of initial X rows, then counts compatible suffixes from saved histogram rows. Bounds must be safe integer numerators in [0,37]. Any real bounds induce the same matching family as rounding down their products with 37 and clipping to the finite cost range; the API accepts the integer representatives directly.
- select(condition,rank) returns a complete permutation and branch trace. Rank is zero-based within the conditioned family, in ordinary lexicographic order of the complete Y-label array.
- rank(condition,permutation) returns the inverse rank. The array must be a complete permutation, must extend the fixed prefix and must obey both coordinate bounds.
- obstruction(condition) returns feasible, prefix-violation, or hall-deficiency. The last includes the left subset, its complete neighbor set and positive deficiency in the remaining rectangle-allowed graph.
- caches() and work() expose actual new query work and memoized counts/conditions/obstructions.

Exact nonnegative ranks may be BigInt, decimal strings, or safe integer numbers. Invalid or repeated labels, invalid bounds, prefix mismatch, a permutation outside the family and an out-of-range rank throw. Empty families have no selectable rank. The full permutation prefix is valid and has one completion when all its edges satisfy the bounds.

The constructor accepts equal cloud sizes from 1 through 10, safe integer common denominators up to one million, and coordinate numerators in the corresponding unit square. Duplicate point coordinates still carry distinct labels. Only the declared nine-point instance was executed. The reader checks basic shape and argument contracts but consumes the certificate's mathematical content as a premise; it is not an independent verifier of untrusted saved data. Returned objects are read-only by convention.

### Ranking and prefixes

A compatible prefix fixes both used columns and initial row assignments. Its own maxima must obey the rectangle. Since a full bottleneck is the coordinatewise maximum of prefix and suffix maxima, validating the prefix and filtering suffix entries by the same bounds is sufficient.

At each remaining row, columns are considered in ascending order. The number of admissible completions in a branch is obtained by filtering that child's saved histogram. Selection subtracts the sizes of earlier branches; ranking sums them. The partition argument above makes these operations inverse.

A prefix that already contains an out-of-bounds edge is a different failure from an unmatched remaining graph. It immediately has zero completions, even if all remaining rows could be matched. The API therefore reports that edge and does not manufacture a Hall obstruction for the remaining rows.

For a compatible prefix with zero completions, the obstruction query forms each remaining row's allowed-neighbor bitmask and enumerates nonempty left subsets in increasing bitmask order until |N(U)|<|U|. The returned certificate is sufficient by injectivity: distinct rows of U would require |U| distinct columns inside the smaller set N(U). The classical Hall theorem guarantees such a subset for a finite bipartite graph without a perfect matching. This implementation retains the explicit certificate; it does not count that theorem as a newly proved result. A missing witness after a saved zero count throws an inconsistency error.

The actual consumer exercised empty-prefix Hall deficiencies and incompatible nonempty prefixes. A compatible nonempty prefix with an infeasible suffix is covered by the stated algorithm and reasoning but was not an additional runtime exercise.

## Production and query evidence

The once-only constructor formed 162 coordinate differences, 512 states, 2,304 assignment branches, 64,339 histogram transitions and 21,827 stored histogram cells. It made 403 frontier comparisons. It did not enumerate complete permutations or repeat an accepted matching/quota computation.

The one actual reader has 103 saved responses and 18 selected-rank inverse matches. Its 24 primary conditions include the unrestricted family, all Pareto bounds, two interior rectangles, seven infeasible rectangles, and all nine one-column prefixes at (10,13). Complete first-permutation prefixes bring the retained condition cache to 33. All six Pareto matchings are exported.

The reader retained 192 count-cache entries and 24 obstruction outcomes. Fresh work was 19,055 saved-cell scans, 201 count-cache hits, 66 condition-cache hits, 105 prefix-edge reads, 136 ranking candidate edges, 387 selection candidate edges, 567 Hall edge reads, 325 subset-neighbor unions and 650 cardinality calculations. It built no new coordinate-cost matrix or suffix histogram. There was no reader error, missing response or query rerun.

The rank inverses are meaningful use of the API, not a second independent completeness proof. No separate brute-force permutation comparison or imported benchmark was run. Source, input and plan were publicly checkpointed before construction; the complete certificate was checkpointed before the reader; each reader request and result was retained in sequence and the entire reader output was then publicly checkpointed.

## Files and recovery

certificate_manifest.json contains the fixed input, cost matrix, summary, frontier and construction counters, plus eight contiguous 64-state shard identities. Concatenating their states in declared order reconstructs the full 1,175,435-byte certificate at Git blob 54ec365852ece27b334f4082ad65d509ee019a95, under JSON.stringify(certificate,null,2) plus one LF. The serialization identity was checked without replaying mathematics.

saved_reader.json contains every response, the complete query caches, inverse records and Pareto exports. Its compact JSON plus LF is 55,068 bytes, Git blob f90a33f5839a7efb9866bf2cfa9a6c04d9384025. public_checkpoints.json supplies acknowledged public manifest locators in dependency order. These are provider-acknowledged Git blobs; a local computed identity alone is not represented as an acknowledgement. The checkpoint helper does not promise indefinite retention of unreferenced objects or certify mathematical content.

The source and saved dataset provide an exact finite matching capability. They make no statement about arbitrary random clouds, a worst-case complexity improvement, the Talagrand exponent tradeoff, a new matching theorem or prize progress.
