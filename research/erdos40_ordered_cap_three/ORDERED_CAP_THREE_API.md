# Ordered representation cap three and finite prefix-density navigation

This package describes every subset A of [1,19] whose ordered representation function r_A(n) = #{(a,b) in A x A : a+b=n} is at most three for every integer n. It builds a new family from the authenticated B2[2] diagram in Commons #31744 and existing two-pair supports in #31750. It does not rerun either older constructor or reader.

The new family has **12,670 sets**, with cardinality coefficients [1,19,171,969,3432,5922,2152,4]. Its maximum size is seven, attained four times. A separate fixed-window objective is
D(A) = min over 4 <= N <= 19 of |A intersect [1,N]|^2/N.
Its maximum is **25/13**, attained uniquely by {1,2,3,5,9,14,19}; its minimizing prefix is N=13.

Both statements concern this fixed finite host. A finite set has zero density eventually, so neither the finite score nor its optimizer establishes the global Erdős40 implication about infinite sets or any admissible function g(N).

## Statement and counting conventions

The [PPL163 card](https://prizeproblems.org/problems/163/) identifies Erdős40. The complete observed [Formal40 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/40.lean), blob 2b1a28e117d90af2ddf5affc5e298a4b2d719e0b, quantifies over subsets of the naturals and asks for functions g tending to infinity such that a lower bound of square-root scale divided by g forces unbounded limsup of sumRep. Its counting interval is [1,N]. The current source has open annotations and local placeholders; its included implication proof toward Erdős28 was not executed or independently audited.

The imported definition was resolved through actual import paths to [Convolution.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjecturesForMathlib/Combinatorics/Additive/Convolution.lean), observed blob cb534ea66bd32dca892aa972e72b1bea83e58554. sumConv sums over ordered antidiagonal pairs, and sumRep is indicator self-convolution. These are observations at an explicit main read, not an immutable repository-commit claim.

An independent author definition appears in Charles Helou, *Characterization of Representation Functions*, INTEGERS 17 (2017), A44, [author paper](https://math.colgate.edu/~integers/r44/r44.pdf). Retrieved first-page indexed text defines the ordered pair count for A in the nonnegative integers. Only that definition text was used, not a full-paper proof or example review. Gang Yu's previously qualified B2[g] definition counts unordered pairs a<=b, including a=b; it is the convention of the saved inputs.

The direct canonical erdosproblems.com/40 route returned 403 Forbidden and remains held without retry or alternate recovery. Secondary card status/reward labels do not establish current award eligibility, sponsor acceptance or a solved result.

## Why these copied constraints are exact

Write U_A(n) for the number of unordered pairs a<=b and delta_A(n) for the indicator that n is even and n/2 belongs to A. Then
r_A(n) = 2 U_A(n) - delta_A(n).
This is elementary bookkeeping: each off-diagonal pair supplies two ordered pairs, while a diagonal supplies one.

There can be at most one diagonal pair in a sum fiber. Therefore r_A(n) >= 4 if and only if that fiber contains at least two distinct off-diagonal unordered pairs. A diagonal together with one off-diagonal pair contributes exactly three and is allowed.

Every cap-three set is B2[2]. The saved #31750 Sidon delta already contains every two-pair witness, with both endpoint pairs and its complete union support. Selecting only witnesses with both pairs off-diagonal and intersecting their avoidance conditions with the complete saved B2[2] family gives exactly the new family. No support union or pair sum needs to be recalculated. Completeness of the saved witnesses and base family is an inherited premise.

The actual selection retained **444 of 525** saved witnesses. Each selected support has four distinct elements: two off-diagonal pairs with the same sum cannot share exactly one endpoint without being the same unordered pair. The implementation uses the existing support masks; this observation is explanatory, not a repeated support construction.

The positive host excludes zero explicitly. Sums outside [2,38] have no representations. The empty set is included. Sets are labelled subsets of [1,19], with no translation/reflection/isomorphism quotient.

## Immutable input lineage

Base: [Commons #31744](https://github.com/woahwhattheheck/commons/pull/31744), merge 9112c0a9d8fd664a61791c750d5992912f4a4b4b, directory research/erdos158_b2_two_families/.

| File | Blob | Bytes |
|---|---|---:|
| snapshot_manifest.json | d35a641c600104ad6b73cfc955eaca8ff72c6ead | 400759 |
| nodes_00.json | a4978bf920b089eb5ada24245d97d97034da1bb4 | 346428 |
| nodes_01.json | 598733b6d72cce46ce3df9c583e454406a196f8d | 349288 |
| nodes_02.json | cd782fee0722ac9b446b515ed4fc58e0b4eb1ab3 | 351317 |
| nodes_03.json | e8066688a31519ebf4f45fbf76689c92b903c2f0 | 47175 |

All complete bodies were acquired and independently matched. Replacing the manifest's null nodes slot with the concatenated node arrays reproduces f9b551bf2f8d67f29fc5e764866b1e6797cbf3e1, 1,437,975 bytes. That is a serialization/identity check, not a family or coefficient recomputation.

Constraint source: [Commons #31750](https://github.com/woahwhattheheck/commons/pull/31750), merge 07662575018ecd10f1fbb14a99a593e20567171c, research/erdos44_sidon_extension_refinement/host19_sidon_delta.json, blob 04c37939e513719e2e8863fc1624847887e9780a, 217,574 bytes. Its complete 525 witnesses were acquired without executing its source. The old Sidon result, seed extensions, optima and saved queries remain separate.

Both guides were read as input contracts: a96f5ef75fae5c6ec25036edc10f022d7e8bbb3d and 15b99317b22dd9dc7a18c4edde22a4bca136bd63. input.json binds these sources and the finite score window.

## Refinement and complete new profiles

The old diagram is zero-suppressed, ordered by variables 1 through 19. Node 0 rejects and node 1 accepts. A skipped variable is absent. At a node:
- Excluding its variable discards residual supports that require it.
- Including the variable removes its bit from each residual support; completing a support rejects the high branch.
- Supports requiring skipped variables are impossible and are discarded.
- With no residual supports left, the old subgraph and coefficients are returned unchanged.

Memoization uses the inherited node ID and normalized residual supports. Unique nodes use (variable,low,high). The unique table starts with every old node. A genuinely new node computes P_low + z P_high; an existing node reuses its coefficient vector literally. High-reject nodes reduce to their low child; equal low/high children are not collapsed as if this were an ordinary BDD.

Actual work retained:
| Item | Count |
|---|---:|
| Saved nodes | 6423 |
| Saved witness filters | 525 |
| Selected copied witnesses | 444 |
| New refinement states | 5753 |
| Memo hits | 2558 |
| Skipped-support drops | 6488 |
| Unchanged subgraph returns | 43 |
| Old-node reuses | 1169 |
| New unique-node hits | 281 |
| Zero-high reductions | 3126 |
| Appended nodes | 1177 |
| New coefficient cells | 4713 |
| New family traversal visits | 25339 |
| Saved family rows | 12670 |
| New prefix-count cells | 240730 |
| Finite score comparisons | 202720 |

New pair sums, new support unions, old constraint constructions and old coefficient recomputations are all zero.

Only the new family is then traversed once, low before high, preserving the 19-bit membership-vector order. Each accepted path saves [mask,size,prefixCounts,scoreNumerator,scoreDenominator,minimizerMask]. prefixCounts is a 19-character base-36 encoding of counts at N=1 through 19. The score is reduced by integer gcd, and its minimizer mask has bit N-4 for every tied minimizing N. The empty-set score is 0/1 and all sixteen N values tie.

The row count is checked against the new root's already stored coefficient sum. No old base coefficient is reevaluated. Global row IDs are permanent array positions. This order differs from increasing numeric mask, increasing cardinality, and lexicographic order of the displayed element lists.

The constructor enforces this fixed N=19 and score window [4,19], at most 200,000 refinement states, 1,000,000 new coefficient cells and 100,000 rows. No cap was reached. Structural checks do not authenticate hostile input or independently prove the inherited base.

## Finite objectives and actual results

The score compares squared prefix counts divided by N using exact integer cross-products. It optimizes a fixed finite lower envelope. Cardinality is a different objective.

All four maximum-cardinality sets were exported:
| Set | Finite score | Minimizing N |
|---|---|---|
| {1,6,11,15,17,18,19} | 1/5 | 5 |
| {1,5,9,12,17,18,19} | 1/4 | 4 |
| {1,2,3,8,11,15,19} | 9/7 | 7 |
| {1,2,3,5,9,14,19} | 25/13 | 13 |

The last set uniquely maximizes the finite score over the entire family, not merely over the size-seven slice. Its prefix counts are [1,2,3,3,4,4,4,4,5,5,5,5,5,6,6,6,6,6,7].

Selected conditional results:
| Condition | Sets | Best finite score | Ties |
|---|---:|---|---:|
| Entire family | 12670 | 25/13 | 1 |
| Size six | 2152 | 36/19 | 4 |
| Contains 1 and 19 | 1024 | 25/13 | 1 |
| Omits 1 | 8974 | 9/5 | 1 |
| Omits 1,2,3,4 | 3016 | 0 | 3016 |
| Prefix counts at 4,8,12,16 at least 2,3,4,5 | 1137 | 25/13 | 1 |
| Score at least 1 | 666 | 25/13 | 1 |
| Score at least 3/2 | 50 | 25/13 | 1 |
| Score at least 2 | 0 | undefined | 0 |

The 3,016 score-zero ties are retained through full row IDs in the condition cache; they were not all exported again as repeated verbose rows.

## Reader API

Require ordered_cap_three.cjs and call open(certificate). The saved certificate alone supplies reader rows, copied witnesses and metadata. Opening does not run construct, load the old modules or reconstruct any prefix count/score. Bind file identities before opening; shape checks are not mathematical validation.

- summary(): family count, cardinality optimum, finite-score optimum and inherited base count.
- scoreGroups(): every distinct reduced finite score and its multiplicity.
- row(id): one complete saved set/profile.
- condition(raw): full matching row IDs, size counts, maximum score and all optimal row IDs.
- select(raw,rank) and rank(raw,values): zero-based conditional order and inverse.
- page(raw,start,limit): up to 256 matching rows; default 64.
- optimumSelect, optimumRank, optimumPage: the same navigation restricted to the highest finite score within the condition.
- explain(values): cap-three membership and saved profile, or one copied four-element collision witness implying at least four ordered representations.
- snapshot() and work(): full cached conditions and counters.

A raw condition allows:
- required and forbidden arrays of distinct labels in 1..19;
- inclusive integer min_size and max_size bounds;
- prefix_min entries {N,count} with N in 1..19 and count in 0..19;
- inclusive score_min and score_max rationals {num,den}, supplied as nonnegative decimal integers with positive denominator.

Restrictions intersect. Duplicate quotas at the same N use their maximum. A quota greater than N, overlapping required/forbidden labels, reversed size bounds, or incompatible rational bounds yields an empty family. Rationals are compared by BigInt cross-products. Use decimal strings for large integers to avoid caller-side numeric rounding. Negative scores are not accepted because this score is nonnegative.

Ranks are bounded ordinary integers because the complete family has 12,670 members. A nonmember rank returns null. Empty families have null maximum score and no optimal IDs; selecting rank zero from one throws. Pages allow start equal to count and limit zero. Duplicate set labels, invalid labels/quotas/rationals/ranks, and invalid page bounds throw. At most 64 distinct normalized conditions are cached. Feed queries the raw condition object; normalized cache objects use a different representation.

An explain call tests family membership independently of a condition. A set can be a cap-three member yet have null rank under a restrictive condition. The witness is a saved off-diagonal pair collision, not a recomputed sum.

Every fresh condition scans the saved rows and applies membership, size, prefix and rational filters. Rank uses the sorted global row IDs, and select addresses them directly. All optimal ties remain in fixed global order.

## First actual reader and retention

The frozen reader ran once after its native plan checkpoint. It retained **137 responses** and **53 matching inverse checks**, including both ordinary-family and finite-score-optimum ranks. All four maximum-cardinality sets and the unique global finite-score maximizer were exported. The first/last 32 rows, empty end/zero-limit pages, invalid-family witness, empty set and allowed diagonal-collision case are retained.

The 18 complete conditions include rational endpoint equality, score-zero ties, required/forbidden overlap, impossible prefix quota, and reversed/impossible size ranges. Actual reader work: 228,060 row checks, 45,354 quota checks, 63,351 rational comparisons, 53 selects, 54 rank calls (one nonmember), one witness inspection, and 113 cache hits. New refinement, pair sums, prefix cells and score calculations are zero.

The complete catalogue is 1,444,334 bytes with computed identity c1f94524ac74d1609a82a17e3cc984cf1b88d6bd; its four parts and manifest are natively acknowledged, not the whole assembled blob. The complete first reader is 1,680,166 bytes with computed identity 4c34697ca5ffe09cf880da9531f7ffb747cd5706; its five parts and manifest are acknowledged. For either, concatenate exactly in descriptor order before JSON.parse. Identity reconstruction is not computation replay.

public_checkpoints.json lists the native source/input/plan, constructor, reader-plan and complete-reader checkpoints. The full publication spec is checkpointed separately before its guarded writer. Native acknowledgement does not by itself establish indefinite blob retention, mathematical correctness, sponsor acceptance or deployment.

## Limits of interpretation

This delivers an exact finite ordered-cap-three family and finite prefix-score navigator. It does not identify any g in Erdős40, give an infinite dense set, settle Erdős28, rerun the old B2/Sidon results, claim a new extremal record, inspect a held source by another route, or submit for an award. It preserves the actual source and computation boundaries.
