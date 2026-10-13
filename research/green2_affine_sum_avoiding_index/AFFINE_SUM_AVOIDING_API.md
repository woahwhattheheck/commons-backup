# Restricted sum avoidance over an integer affine family

This package classifies every set A = λ{1,...,19} + τ with nonzero signed integer λ and integer τ. It indexes all subsets S of A whose sums of distinct selected elements avoid the entire ambient A. Its finite critical-parameter index supports exact counts, ranks, selections, pages and rejection witnesses, including huge integer scales and shifts.

The result concerns this one affine host family. It is not a bound for arbitrary n-element integer sets, a new worst-case construction, a resolution of the Erdős–Moser asymptotic question, or a prize claim.

## Exact source convention

Ben Green, *100 Open Problems*, Problem 2, printed p. 3, takes A⊂Z and explicitly defines the restricted sumset using s1≠s2. It asks for S⊂A with that restricted sumset disjoint from A. The comment attributes the problem to discussions of Erdős and Moser.

Primary source: https://people.maths.ox.ac.uk/greenbj/papers/open-problems.pdf#problem.2 . The exact passage was transferred from previously retained primary text; no new source call, bound, proof or numerical example was needed.

FormalConjectures defines M(A) as the largest cardinality of such an S:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/GreensOpenProblems/2.lean .
The fully read source is 3,746 UTF-8 bytes, blob e59708c8692a1141e993ce34dda249f26da22628. The request used its default repository ref; no immutable source commit was independently observed. Its eventual all-n/all-A statement and research annotations remain separate from this finite computation. No Lean proof was executed.

Two distinctions are essential:

- Sums must avoid the whole A, including its unselected elements. For A={1,...,19}, S={1,2} fails because 1+2=3∈A, although 3∉S.
- Diagonal sums are omitted. A singleton is always admissible, even {0} when 0∈A. There is no positivity or nonzero restriction on members of the ambient integer set.

## Literal input lineage

The base host H={1,...,19} is identified by the earlier accepted finite B2-family input. Its complete pair-sum fibers are consumed as arithmetic premises; their old sum computation and B2 constraints are not replayed.

| Input | Exact immutable source |
|---|---|
| All 190 unordered pair records, including diagonals | Commons #31744, merge 9112c0a9d8fd664a61791c750d5992912f4a4b4b; research/erdos158_b2_two_families/snapshot_manifest.json, blob d35a641c600104ad6b73cfc955eaca8ff72c6ead; field snapshot.fibers |
| Binomial and cumulative rows 0..19 | Commons #31787, merge 73b115a70008c88293a6a2e0efd3be612e0f4f73; research/erdos10_selected_prime_binary_minima/bit70_minima_index.json, blob a781a03e3113d1bf6ecfe968178a33248d6dcacf; fields pascal[0..19], cumulative[0..19] |

The new input is 10,382 bytes, blob e84a704410acfea6209d6b09a4afe271a0e00a4f. It copies these exact records and provenance. The compiler checks host ordering, pair membership/masks, dimensions and numeric syntax. Completeness and correctness of the saved sum/binomial premises are inherited, not independently re-proved.

The new interpretation discards the 19 diagonal pairs and retains 171 distinct pairs. It does not calculate a+b again. This is a new graph construction from accepted pair sums, not a replay of the earlier B2-family enumeration.

## Why finitely many parameter cases suffice

Write selected values as λa+τ and λb+τ with a≠b in H. Their sum is in A exactly when

    (λa+τ) + (λb+τ) = λc+τ

for some c∈H. Since λ≠0, this is equivalent to

    τ/λ = c - a - b.

For each saved distinct pair and each target c the compiler forms this new difference c−saved_sum. These are the only critical ratios. At a fixed ratio, an edge joins a,b when their affine sum belongs to the ambient set; its stored witness gives c. Then admissible selected subsets are precisely independent sets of that labelled graph.

For the actual host there are exactly 53 critical ratios: every integer from −36 through 16. All nonintegral ratios, and every integral ratio outside that set, use the edgeless graph. This generic case permits all 2^19 subsets. It is one parameter class representing infinitely many (λ,τ), not a count of those parameter pairs.

The affine map is injective because λ≠0. Thus base-index subsets correspond bijectively to numerical subsets of A, even for negative λ. A negative scale reverses numerical value order but does not alter the selected base labels or the graph criterion. Zero may occur when τ/λ is the negative of a host value; it is handled by ordinary edges, with no diagonal loop added.

Different parameter pairs can describe the same or related numerical sets. The API resolves the supplied pair and retains its explicit base-index labeling. It does not claim a quotient or count of distinct ambient sets across all scales and shifts.

## Shared independent-set certificate

For an available vertex mask U, choose its smallest indexed vertex v. Every independent set either excludes v or includes it and excludes all its neighbors. Its cardinality polynomial therefore satisfies

    P_U(z) = P_(U minus {v})(z)
             + z P_(U minus ({v} union neighbors(v)))(z).

The empty state contributes 1. States are shared across all parameter graphs only when their labelled remaining vertex mask and induced adjacency are identical. Sharing on those complete keys preserves both the family and its ordering.

When an induced state has no edges, the compiler copies the inherited binomial row for |U| and its cumulative row. It keeps a free child for rank navigation but performs no Pascal recurrence. Other states evaluate the displayed new independent-set recurrence and save every coefficient and cumulative value.

There are 1,039 shared nodes, 6,964 coefficient cells and 6,964 cumulative cells. The 53 critical graphs retain all 3,249 edge witnesses. The 54 graph classes, including the generic one, form 28 distinct (maximum size, maximum count, total count) profiles.

The state recurrence partitions the independent sets into disjoint exclude/include branches. Saved cumulative coefficients count any requested size interval. Rank and select use the eligible exclude count before the include branch, giving exact inverse navigation without enumerating the represented family.

## Actual finite result

Across the entire declared affine family, the smallest value of M(A) is 5. It occurs precisely when τ/λ=−10, equivalently τ=−10λ. The ambient set is then a nonzero integer scaling of {-9,...,9}. There are 124 admissible subsets, including the empty subset, and exactly four with maximum size five.

At λ=1, τ=−10, those four subsets, in the reader's base-index order, are:

    {5,6,7,8,9}
    {4,6,7,8,9}
    {-9,-8,-7,-6,-4}
    {-9,-8,-7,-6,-5}

This is an exact minimum within this affine family of nineteen-element sets. It is not the minimum over every nineteen-element integer set.

Selected graph results are:

| Ratio τ/λ | Edges | Total admissible subsets | Maximum size | Number of maximum subsets |
|---:|---:|---:|---:|---:|
| −36 | 1 | 393,216 | 18 | 2 |
| −20 | 81 | 2,046 | 10 | 2 |
| −19 | 90 | 1,535 | 10 | 1 |
| −11 | 130 | 140 | 6 | 1 |
| −10 | 131 | 124 | 5 | 4 |
| −9 | 130 | 140 | 6 | 1 |
| −1 | 90 | 1,535 | 10 | 1 |
| 0 | 81 | 2,046 | 10 | 2 |
| 16 | 1 | 393,216 | 18 | 2 |
| Generic | 0 | 524,288 | 19 | 1 |

Every remaining critical ratio and its complete cardinality polynomial is retained in affine19_sum_avoiding_index.json. The graph summaries are exhaustive for the parameter classes, without extending the base host or treating other integer sets as covered.

## Saved API and ordering

The CommonJS module exports compile(input) and openIndex(snapshot). A fresh consumer opens the saved index without compiling:

    const fs = require("node:fs");
    const {openIndex} = require("./affine_sum_avoiding_index.cjs");
    const saved = JSON.parse(
      fs.readFileSync("affine19_sum_avoiding_index.json", "utf8"));
    const api = openIndex(saved);
    const parameters = {scale:"1", shift:"-10"};

The example describes independent consumption; this delivery did not rerun the accepted construction.

| Method | Output |
|---|---|
| summary() | Complete parameter-class summaries and minimum-of-maxima result |
| profiles() | All 28 saved cardinality profiles and their graph IDs |
| graph(parameters) | Resolved parameter class, complete edges/witnesses and coefficients |
| family(parameters,options) | Exact size-interval count and saved maximum/count |
| select(parameters,rank,options) | Base mask, selected base/affine values and full decision trace |
| rank(parameters,mask,options) | Inverse rank or explicit rejection witness/reason |
| page(parameters,start,limit,options) | Bounded rank page with next rank and family total |
| membership(parameters,mask) | Membership plus first saved conflict witness when invalid |
| work() | Fresh arithmetic/lookup counters |

Parameters use signed decimal strings or BigInt. Defaults are scale="1", shift="0". A zero scale is rejected. Resolution computes exact quotient and remainder of shift by scale; only a zero remainder and an exact stored ratio key select a critical graph. A huge integral quotient outside the finite map remains generic without conversion to an unsafe Number.

Size options are min_size and max_size, defaulting to [0,19]. Masks are Number bitmasks from 0 through 524287; bit i chooses base value i+1. Counts/ranks fit the finite at-most-24-vertex compiler bound. Invalid masks, size bounds, ranks or parameter syntax throw. Page start may equal the total, yielding an empty page; an individual selected rank must be smaller than total. Page limits are at most 10,000.

Ordering is exclude-first in increasing base-index decisions, restricted to the requested size interval. Forced omissions of neighbors do not create additional choices. This is not numerical-mask order. The returned affine_values follow increasing base indices, so negative scales produce decreasing numerical values. Neither rank convention changes with the magnitude or sign of the scale.

For nonmembership, the reader scans saved graph edges until both endpoints are selected, then materializes the two affine summands and the ambient target from the saved witness. It performs fresh BigInt multiplication/addition. It does not regenerate sums, critical ratios, graphs or coefficient states.

The snapshot is treated as immutable by the reader. Exposed records should not be modified by a caller.

## Actual reader evidence

saved_reader_queries.json contains all 43 requests and full responses, including all 124 admissible subsets at ratio −10. Four of those are the complete maximum family above. Their size-five ranks were checked, together with three generic size-nine selections and five parameterized maximum selections: twelve inverse matches in total.

For scale 2 and shift 1, the ambient values are the odd integers 3 through 39, so the generic graph applies. The recorded size-nine family has 92,378 members; ranks 0, 46,189 and 92,377 were selected and ranked back. The complete nineteen-element set is itself admissible.

The retained huge-scale inputs include scale=10^100+7 and shift=−10 times that scale, and their simultaneous sign reversal. Both resolve to the saved ratio −10 graph and materialize actual large selected values without reconstruction. Another huge input with nonzero remainder resolves to the generic graph.

The saved witnesses make the source distinction concrete:

- In the original host, mask 3 selects {1,2}; the retained ambient witness is 3, so it is rejected even though 3 is unselected.
- Mask 1 selects singleton {1} and is accepted; the diagonal 1+1 is not tested.
- At ratio −10, mask 512 selects {0} and is accepted.
- Mask 768 then selects {-1,0}; it is rejected because their sum −1 belongs to A, even though the target coincides with a selected summand.

The reader performed 165 exact parameter divisions and 165 remainders, 1,863 coefficient lookups, 1,849 DAG steps, 1,063 saved-edge scans, 2,803 mask-bit checks, 445 affine multiplications and 445 affine additions. A page resolves parameters for its individual selections as well as the page header; these are included in the counts. Critical subtractions, pair-sum additions, graph reconstruction and coefficient recurrence were all zero in the reader.

## Work, caps and artifact identities

The constructor examined 190 inherited pairs, omitted 19 diagonals and consumed 171 distinct pairs. It performed 3,249 new critical subtractions and retained 3,249 witnesses with 6,498 adjacency insertions. State-key formation used 16,500 vertex probes. It copied 244 binomial coefficient cells and 244 cumulative cells, performed 10,947 new independent-set coefficient additions and 6,720 cumulative additions. It performed zero pair-sum additions and zero Pascal recurrence operations.

Caps were 24 host values, 256 graph classes, 20,000 witnesses, 100,000 nodes and 2,000,000 coefficient cells. The actual construction completed within each bound. There was no failed production or reader call, no missing response, and no host expansion.

Source/input were banked before the one production; the complete result before the fresh reader; each request and response immediately. The publisher and full-content identity checks establish byte custody, not a mathematical replay.

| Artifact | UTF-8 bytes | Git blob |
|---|---:|---|
| affine_sum_avoiding_index.cjs | 10,632 | bfb13720367ab32c900b304015e4e179f7e1bba5 |
| input_affine19.json | 10,382 | e84a704410acfea6209d6b09a4afe271a0e00a4f |
| affine19_sum_avoiding_index.json | 438,171 | 2463ff390c46b78241e6c547a6d937eeae642715 |
| saved_reader_queries.json | 258,588 | 660ff4c4de410fa47427b88775147ed03045dab0 |

The original question quantifies over arbitrary large finite integer sets. Reusing one finite base host through unbounded affine parameters does not satisfy that quantifier. The exact finite parameter classification and its saved queries are the delivered capability.
