# All binary linear covering codes in dimension six

This package indexes every labelled linear subspace of F2^6, its complete cosets, covering radius and nearest-codeword data. It gives exact finite optima and saved navigation under explicit membership and distance conditions. No infinite-dimension assertion, nonlinear optimum, new code record, or award claim follows from this one ambient space.

## Source and scope

Ben Green's *100 Open Problems*, Problem 40, printed pp. 20–21, fixes a positive radius r and considers subspaces V_n with V_n+H(r)=F2^n along an infinite sequence of dimensions. The normalized density is |V_n||H(r)|/2^n. Its question concerns the resulting f(r) as r tends to infinity. The following page separately considers arbitrary subsets and the requirement of every dimension.

Primary source: https://people.maths.ox.ac.uk/greenbj/papers/open-problems.pdf#problem.40 . Only the defining passage and distinction between variants were used. Hamming-code sanity constructions, source upper-bound proofs, numerical examples and code tables were not imported or replayed.

The fully read FormalConjectures source is
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/GreensOpenProblems/40.lean .
Its observed complete content is 6,736 bytes, Git blob 99d4b7bb10358b91183ff9d7ebb61b5fbaea0db5. The request used the repository default ref rather than an independently observed immutable source commit. Its explicit ball is weight at most r, centered at zero; f is the liminf over dimensions of the minimum linear covering density for that fixed radius. Research-open tags and local placeholders are source metadata. A returned Lean comparison proof was not executed or independently audited.

The finite input deliberately fixes n=6. It includes the literal pascal[6] and cumulative[6] from Commons #31787:
merge 73b115a70008c88293a6a2e0efd3be612e0f4f73,
research/erdos10_selected_prime_binary_minima/bit70_minima_index.json,
blob a781a03e3113d1bf6ecfe968178a33248d6dcacf.
The input blob is 8959a9eeb335a3fb89a602f4731b2b9476eaac27, 1,355 bytes. These rows supply ball volumes 1,7,22,42,57,63,64. No binomial recurrence or earlier binary-minimum computation was repeated.

For this API, radius zero is included as an explicit finite convention. Green's source fixes positive radii for its asymptotic question. The ambient dimension is positive. The zero-dimensional subspace {0} is included; it is not an empty center set. Translated balls need not be disjoint.

## Complete construction

Coordinates are labelled bits 0 through 5; the integer from 0 to 63 represents its binary vector. Addition is XOR. Code labels are subspaces, not arbitrary generating matrices and not classes under coordinate permutations.

Each subspace has one reduced-row-echelon basis with pivot columns ordered from the lowest bit upward. The compiler enumerates every pivot mask. For each pivot set, a row has its own pivot equal to one, every other pivot column zero, every column before its pivot zero, and arbitrary entries in nonpivot columns to the right. It enumerates those free entries exactly once.

Every enumerated basis is reduced and independent. Conversely, ordinary elimination over F2 gives this unique basis for every subspace. Thus the enumeration is exhaustive without counting several bases of the same subspace. This finite completeness argument uses standard row reduction, not a claimed new code-construction theorem.

For each basis the compiler reduces all 64 ambient error vectors. The remainder has zero pivot coordinates and identifies its coset modulo the code. Free-coordinate patterns index the cosets, with index zero the code itself. The saved syndrome_map maps every ambient vector directly to that coset index.

Each coset retains:

- Its free-coordinate representative.
- All its error vectors, ordered by (Hamming weight, integer value).
- Its entire weight histogram and cumulative histogram.
- Its minimum error weight and the number of errors at that minimum.

The global 64-vector weight table is constructed once. The code's covering radius is the largest coset minimum weight. Its minimum nonzero distance is the smallest positive weight in the zero coset. For the code {0}, that latter minimum does not exist and is stored as null.

For a received vector x, every codeword c corresponds uniquely to e=x XOR c in x's coset. Therefore the saved list of errors with weight at most r is exactly the list of codewords at Hamming distance at most r from x, after applying x XOR e. Its shortest errors give all nearest codewords, including ties. This reader transformation is new query arithmetic; it does not require basis reduction or a distance computation.

## Actual finite result

There are 2,825 labelled subspaces, 26,387 cosets and 28 dimension/radius/minimum-distance profiles.

| Dimension | Number of subspaces |
|---:|---:|
| 0 | 1 |
| 1 | 63 |
| 2 | 651 |
| 3 | 1,395 |
| 4 | 651 |
| 5 | 63 |
| 6 | 1 |

Counts by covering radius 0 through 6 are respectively 1, 413, 1,437, 777, 175, 21 and 1. These are counts of labelled subspaces of this entire fixed ambient space; coordinate-equivalent subspaces remain separate members.

At a fixed finite n and r, the ball volume is constant, so minimizing density among covering subspaces is equivalent to minimizing their dimension. The complete index gives:

| Radius | Minimum dimension | Minimum code size | Ball volume | Minimum finite density | Number attaining it |
|---:|---:|---:|---:|---:|---:|
| 0 | 6 | 64 | 1 | 1 | 1 |
| 1 | 4 | 16 | 7 | 7/4 | 350 |
| 2 | 2 | 4 | 22 | 11/8 | 91 |
| 3 | 1 | 2 | 42 | 21/16 | 7 |
| 4 | 1 | 2 | 57 | 57/32 | 42 |
| 5 | 1 | 2 | 63 | 63/32 | 63 |
| 6 | 0 | 1 | 64 | 1 | 1 |

A covering code of radius at most r can have actual covering radius smaller than r; the table minimizes over all eligible codes. A density returned for an ineligible code is only its normalized ball-volume product and has covers:false. It is not a covering-density candidate.

These are exact n=6 statements. In particular, 11/8 is this finite minimum at radius two. It is not the limit f(2), a bound claimed to be best in the literature, or an identification of linear and nonlinear optima.

## Saved API

The CommonJS module exports compile(input) and openIndex(snapshot). compile is the explicit construction path; the shipped index is read using openIndex. The reader treats the input object as immutable. Exposed code/coset arrays must not be mutated by callers.

The snapshot is split into twelve complete code shards. Load the manifest and concatenate the declared shards in order:

    const fs = require("node:fs");
    const {openIndex} = require("./binary_linear_cover_index.cjs");
    const manifest = JSON.parse(fs.readFileSync("dimension6_manifest.json", "utf8"));
    const saved = {
      ...manifest.snapshot,
      codes: manifest.shards.flatMap(s =>
        JSON.parse(fs.readFileSync(s.file, "utf8")).codes)
    };
    const api = openIndex(saved);

The complete joined JSON string, in this retained property order, has 4,974,728 UTF-8 bytes and blob b02175aa336d299c1c147dd50633a6238aa08fb6. Actual assembly from the twelve published shard strings matched the original string byte for byte. This was serialization identity, not a second code construction or proof check. The example is for an independent consumer, not an instruction that this delivery rerun the accepted production.

| Method | Behavior |
|---|---|
| summary() | Saved complete counts and finite optimum summaries |
| profiles() | All 28 profile rows with complete code-ID lists |
| optima() | All radius optima, including every attaining code ID |
| code(id) | Full saved basis, syndrome map and cosets |
| family(condition) | Exact count and ID of a cached conditional code family |
| familyPage(condition,start,limit) | Brief code records for a bounded rank interval |
| selectFamily(condition,rank) | One code in the cached family |
| rankFamily(condition,id) | Exact inverse rank or nonmembership |
| coset(id,x) | Complete saved coset and its histogram for received x |
| neighbors(id,x,r,start,limit) | Codewords within radius r, with error and distance records |
| nearest(id,x) | Every nearest codeword |
| rankNeighbor(id,x,r,c) | Rank of c in the within-radius list, or nonmembership |
| density(id,r) | Exact numerator/denominator and covers flag |
| caches() | All complete conditional code-ID arrays generated by this reader |
| work() | Measured fresh reader operations |

A condition accepts min_dimension, max_dimension, max_radius, min_distance, allow_zero_dimension, contains and excludes. Defaults are dimensions 0..6, radius at most 6, distance at least zero, zero-dimensional code allowed, and no vector restrictions. Membership conditions refer to the actual labelled ambient vectors; containing a basis vector and excluding the same vector correctly gives an empty family.

The null minimum distance of {0} is treated as an infinite minimum in the filter: it passes every finite min_distance unless allow_zero_dimension:false excludes it. This explicit API convention is illustrated by the saved distance-seven queries; it is not a claim that {0} contains a nonzero vector of that weight.

Conditions are normalized by sorting/deduplicating vector lists. Each previously unseen condition scans the stored code fields and syndrome maps once and retains its complete ID array. Later count/rank/page operations reuse that array. This query filtering is new work and is counted separately from construction.

Code IDs are ordered by increasing numeric pivot mask, then increasing numeric free-entry assignment, with free entries listed row-by-row and increasing nonpivot column. A family is ordered by these IDs. This is not an isomorphism ordering.

Within one code/received-vector list, ranks are ordered by (error weight, error integer), not by codeword integer; XOR can change that numerical order. The nearest list is the initial minimum-weight portion of the same order. Ranks and masks fit the explicitly bounded finite Number domain. Invalid IDs/vectors/radii/ranks, inverted dimension ranges, and malformed conditions throw. Page start may equal count, giving an empty page. Individual selections require a rank below count. The maximum page limit is 10,000.

## Actual reader queries

saved_reader_queries.json retains all 62 actual requests and complete responses. saved_condition_caches.json retains all nine complete cache arrays. There were twelve actual inverse matches: three code-family selections and nine nearest-codeword selections. No output is missing.

The reader exported all 91 smallest radius-two codes and all 350 smallest radius-one codes. Additional saved conditions give:

| Condition | Count |
|---|---:|
| Dimension at most 2, radius at most 2, contains vector 3 | 1 |
| Dimension at most 2, radius at most 2, excludes vector 1 | 90 |
| Dimension at most 2, radius at most 2, contains vector 63, minimum nonzero distance at least 2 | 10 |
| Dimension at most 4, radius at most 1, minimum distance at least 3, dimension positive | 0 |
| Contains and excludes vector 3 | 0 |
| Minimum nonzero distance at least 7, zero-dimensional code allowed | 1 |
| Same distance condition with zero-dimensional code excluded | 0 |

The family reader selected the first, middle and last radius-two optimum code, IDs 64, 289 and 2467. Each complete code record is in the query output. Their nearest codeword to received vector 13 is respectively 61, 1 and 31, in each case at distance two. For the zero subspace the nearest codeword to 63 is zero at distance six; for the full space it is 63 at distance zero. These are finite labelled examples from this new construction.

Reader work was 25,425 code scans, 3,503 syndrome lookups, 595 code lookups, 23 cumulative-coefficient lookups, 20 returned error entries, 29 codeword XORs, 9 neighbor-rank probes and 19 family-rank probes. There were zero RREF enumerations, basis reductions, weight computations or histogram rebuilds in the reader.

## Construction work and custody

The one successful production used 63 weight-recurrence steps, 64 pivot masks, 19,458 free-entry bit probes and 9,729 set free entries. It classified 180,800 ambient vectors, performing 542,400 reduction-bit probes and 271,200 row XORs. It retained 180,800 histogram increments, 184,709 cumulative additions, and 369,418 histogram/cumulative cells. There were 2,825 profile insertions and 19,775 scans for finite radius optima. The inherited binomial row was copied without a recurrence.

Caps were dimension at most eight, 10,000 subspaces, 1,000,000 ambient assignments and 2,000,000 coset cells. This input completed within every cap. The generic cap can stop a larger input without claiming a complete classification; no such partial output occurred here.

Source and input were banked before the first construction; the full output before the reader; every query before the next. No failed production or reader invocation occurred for this packet. The complete coefficient/coset data and all query records are retained.

The full source is binary_linear_cover_index.cjs, 10,457 bytes, blob e036f4c2d178ac9fc7b2aa30f03e607ddfe3d73a. The reader packet is 116,948 bytes, blob 738d856bde55d0199207f756ac7ff00acba99177. The complete cache packet is 4,082 bytes, blob 8a55bf573ac77e681b04a015aed5b45b5c5cfdf7. The manifest records every shard's start, count, byte length and Git blob identity.

Full byte and provider identity checks establish the published artifact's custody. They do not replay row reduction, independently verify the inherited binomial theorem, or turn the finite n=6 table into an asymptotic or nonlinear result.
