# Rectangular-grid distance multiplicity and pair navigation

This API compiles the positive Euclidean-distance classes of an explicitly supplied integer rectangle. It counts unordered pairs of distinct points and retains a disjoint displacement-block representation of every pair. It provides saved multiplicity filters, pair rank/select and exact integer translations/scalings, without enumerating all point pairs.

For the new 53 by 89 rectangle, there are 4,717 points and 11,122,686 unordered pairs. The complete index has 4,716 absolute-displacement blocks and 2,397 realized positive distance classes. Exactly 1,590 classes have multiplicity at most 4,717; 1,589 of them are not the diameter. These are properties of this particular finite rectangle, not a theorem for arbitrary planar point sets.

## Source question, conventions and qualification

Clemen, Dumitrescu and Liu, “On multiplicities of interpoint distances,” Acta Mathematica Hungarica 177 (2025), 231–245, DOI 10.1007/s10474-025-01562-y, defines

    mu(X,d) = #{(i,j) : 1 <= i < j <= n, distance(x_i,x_j)=d}.

Its Conjecture 1.1 assumes n>=5 and asks for a non-diameter distance of multiplicity at most n. The diameter multiplicity bound supplies the second low-multiplicity distance. Its four-point exception explains why the small-n hypothesis cannot simply be omitted. The source discusses the general question as open at its publication date and includes square-grid examples; none of those examples or proofs is recalculated here. Author/institutional full text:
https://publikationen.bibliothek.kit.edu/1000188330/170672891

Paul Erdős, “Some old and new problems in combinatorial geometry,” Annals of Discrete Mathematics 20 (1984), 129–136, printed pages 134–135, discusses distinct planar points, distance occurrence counts summing to n choose 2, and credits Pannwitz for the diameter bound:
https://www.renyi.hu/~p_erdos/1984-22.pdf

The PPL149 catalogue card also asks whether the number of distances occurring at most n times must tend to infinity. The bounded primary passages inspected here did not establish that stronger formulation; it remains explicitly catalogue-qualified in this guide:
https://prizeproblems.org/problems/149/

The direct Formal Conjectures ErdősProblems/132.lean contents request returned 404 once. That route remains held, with no retry or substituted status inference. No linked proof, current comprehensive frontier, external submission or prize entitlement is asserted.

The finite contract counts positive distances only, excludes self-pairs, and counts an unordered pair once. It differs from a pinned-distance convention that includes the pin itself and zero. Squaring positive Euclidean distances preserves equality and order, so the API uses exact squared-distance keys q, representing distance sqrt(q).

The input is the specifically declared point set

    G = {(x,y) in Z² : 0<=x<53, 0<=y<89}.

It is a new selected consumer, not a numerical example attributed to the cited papers. The earlier 17 by 29 pinned-profile and line-navigation artifacts were neither loaded nor recomputed.

## Exact finite results

| Quantity | Value |
|---|---:|
| Width, height | 53, 89 |
| Points n | 4717 |
| Unordered distinct pairs | 11122686 |
| Absolute-displacement blocks | 4716 |
| Distinct positive distances | 2397 |
| Distinct multiplicities in histogram | 1627 |
| Classes with mu<=n | 1590 |
| Such classes excluding diameter | 1589 |
| Pairs in low-multiplicity non-diameter classes | 2377044 |
| Diameter squared | 10448 |
| Diameter multiplicity | 2 |
| Greatest multiplicity | 38656 |
| Squared distance attaining that greatest multiplicity | 325 |

The smallest squared-distance key in the low-multiplicity family is 882, with 4,352 pairs. Unit distance has 9,292 pairs and does not belong to that family. The q=325 class has six absolute-displacement blocks, illustrating why counts must merge different sum-of-two-squares representations.

There are exactly seven non-diameter classes occurring at most eight times:

| Squared distance | Pair multiplicity |
|---:|---:|
| 9929 | 8 |
| 10100 | 6 |
| 10145 | 8 |
| 10170 | 8 |
| 10244 | 6 |
| 10273 | 4 |
| 10345 | 4 |

Together these seven classes contain 44 pairs. Their complete IDs and cumulative pair weights are retained, not just this displayed table.

The full data file contains every block, every distance class, both levels of pair-prefix counts, the complete multiplicity histogram, both low-multiplicity lists, two saved slices and all 26 fresh-reader outputs. No class or represented pair is omitted by a sampling rule.

## Disjoint displacement blocks

For a general width w and height h, each unordered distinct pair is given its canonical orientation: compare x first, then y, and place the smaller point first. Its absolute coordinate displacement is (a,b), where

    0<=a<w, 0<=b<h, (a,b)!=(0,0).

There are exactly wh-1 such displacement types. Each has squared distance q=a²+b² and translation count

    B(a,b) = (w-a)(h-b).

If a and b are both positive, there are two orientations:

    plus:  (x,y) -- (x+a,y+b),
    minus: (x,y+b) -- (x+a,y),

with 0<=x<w-a and 0<=y<h-b. These two cases are disjoint and exhaust positive and negative signed vertical differences when the first x is smaller. If a=0 or b=0, only the plus orientation is retained; a duplicated sign would describe the same unordered pairs.

Therefore the block's pair count is

    B(a,b)                    if a=0 or b=0,
    2 B(a,b)                  otherwise.

Every unordered distinct pair has a unique absolute displacement, orientation and translation. Conversely every permitted block/orientation/translation produces one such pair. This proves that the blocks partition all n(n-1)/2 pairs, where n=wh.

Different blocks can have the same q. The compiler groups them by their exact squared-distance key and sums their disjoint weights. Distinct q values are distinct positive distances because the square-root function is injective there.

The largest q is (w-1)²+(h-1)². It is the diameter key when n>=2. For w,h both greater than one, its one block has two orientations and one translation each: the two diagonals of the bounding rectangle. Degenerate one-row or one-column grids are handled by the same block formulas. A single-point grid has no positive distance, no pair and no diameter ID.

This is a self-contained rectangular counting derivation. It does not claim a new lattice-distance theorem or an extension of a cited general planar bound.

## Rank and selection

Distance classes are ordered by increasing q. Within a class, blocks are ordered by their compiler IDs, which follow increasing a then increasing b. Within a block, the plus orientation precedes minus; translations are ordered by increasing x then increasing y.

For block-local rank u, divide by B to obtain the orientation, then divide the remainder by h-b to obtain x and y. Substituting these values into the formulas above selects a pair directly.

Distance-class prefixes add the weights of earlier blocks. Global prefixes add the weights of earlier distance classes. Selection uses binary searches in those two retained prefix tables. Rank reverses the process:

1. Normalize the two grid points into canonical order.
2. Compute a, absolute b and the sign orientation.
3. Find the saved block by (a,b).
4. Recover x and the smaller y.
5. Add the saved block and class prefixes.

No pair enumeration or squared-distance calculation is needed for this reverse lookup. It uses the saved block's q and class ID.

A saved distance slice contains increasing distance IDs and their cumulative pair weights. It supports selection by distance rank or by pair rank in the selected union. A pair outside the slice has slice rank null. Its global rank remains defined.

## Exact translated and scaled witnesses

A transform has integer x0, y0 and positive integer scale c. It maps a grid point to

    (x0 + c*x, y0 + c*y).

Translation preserves distances and scaling multiplies squared distance by c². Multiplicities and pair ranks are unchanged. The API returns both grid coordinates and exact decimal transformed coordinates; it does not approximate square roots.

The actual saved reader used

    x0 = 10^100 + 31,
    y0 = -10^110 - 27,
    c  = 10^20 + 3.

Low-multiplicity non-diameter slice pair rank 1,188,522 gives grid points (23,5) and (31,68). Their base squared distance is 4,033; their global pair rank is 9,860,936. The transformed squared distance is

    40330000000000000002419800000000000000036297.

All four transformed coordinates are retained in the data packet. A global rank query on those coordinates returns 9,860,936; the slice query returns 1,188,522. This is actual saved navigation and fresh BigInt transform arithmetic, not a new geometry compilation.

The inverse requires each translated coordinate difference to be divisible by c and the resulting grid coordinates to be in range. The two points must be distinct. Input point order may be reversed because pairs are unordered.

## Public CommonJS API

    const { open } = require("./rectangle_distance_index.cjs");
    const packet = JSON.parse(savedText);
    const reader = open(packet.construction.snapshot);
    const rare = reader.openSlice(reader.lowMultiplicity(true));
    const pair = rare.selectPair(1188522);
    const fiber = reader.fiber(4033);

Consumers should open the saved snapshot rather than rerun this constructor. compile(width,height) is for a new bounded rectangle. Exports also include SCHEMA and LIMITS. The module has no I/O or external dependencies.

### Bounds and data types

- width and height are positive safe integers, individually at most 1,000,000.
- Their product is at most 100,000. This also bounds each side effectively and keeps all base squared distances and pair counts exact as Number integers.
- There are at most 99,999 blocks, at most that many distance classes, and at most 4,999,950,000 represented unordered pairs. Ranks are Number integers, not bitwise pair masks.
- Pages contain at most 64 records. Imported JSON is capped at 16,000,000 characters.
- Transform inputs are safe integer Numbers or signed decimal strings of at most 128 magnitude digits, with no exponent syntax. scale must be positive.
- Transformed coordinates supplied to rankPair may have up to 135 magnitude digits, allowing the output growth from a bounded grid and a 128-digit scale. The source enforces divisibility and grid bounds after exact BigInt subtraction/division.
- Base q keys are nonnegative safe integer Numbers. Zero or an unrealized q returns null from distance and fiber; distancePair requires a realized positive q.
- The cap controls dimensions, not elapsed runtime.
- Only the stated 53 by 89 input and recorded query paths were executed. Single-point, one-dimensional, maximum-dimension and malformed-input branches were source-inspected, not exercised by a synthetic suite.

### Reader methods

| Method | Meaning |
|---|---|
| summary() | Dimensions, total pairs, distance count, diameter, low-multiplicity counts |
| distance(q) | One class record, or null |
| distancePage(start=0,limit=64) | Increasing-q class page |
| fiber(q) | Complete displacement blocks and local prefixes for q |
| selectPair(globalRank,transform={}) | One pair from the complete pair family |
| distancePair(q,rank,transform={}) | One pair at distance-local rank |
| rankPair(points,transform={}) | Global and local rank fields |
| lowMultiplicity(excludeDiameter=false) | Saved slice at threshold n |
| filter(criteria) | One explicit scan over saved distance classes |
| openSlice(slice) | Navigation over saved class IDs and pair prefixes |
| histogram(start=0,limit=64) | Multiplicity-to-distance-ID records |
| blockPage(start=0,limit=64) | Raw displacement records |
| stats() | Copy of reader counters |
| snapshot() | Independent complete snapshot copy |

A class record includes distance_id, squared_distance, pair_count, block_count, is_diameter and low_multiplicity. Point IDs use x-major order: id=x*h+y. The generic low_multiplicity flag means pair_count<=wh, regardless of whether a global conjecture's small-n hypotheses apply.

filter accepts only min_multiplicity, max_multiplicity, min_squared, max_squared and exclude_diameter. Thresholds are inclusive. Multiplicity thresholds are integers from zero through the total pair count; q thresholds are nonnegative safe integers. Contradictory bounds produce an empty slice.

A slice exposes summary(), page(), selectDistance(), selectPair(), rankPair(), snapshot(). Its rankPair returns a Number or null; the whole reader's rankPair returns the richer global/local rank record. All ranks are zero-based. Empty-family selection throws. Page start may equal family size; zero-size pages are permitted and do not advance.

Transforms use only keys x0, y0 and scale, defaulting to 0, 0 and 1. Reflection, rotation, anisotropic scaling and rational scaling are not part of this transform contract.

Returned objects and snapshots do not alias the retained internal arrays.

## Saved schema and provenance boundary

construction.snapshot has schema commons.rectangle_distance_fibers/v1. Its blocks have columns

    [dx,dy,squared_distance,translation_count,orientations,pair_count,distance_id].

A group contains squared_distance, pair_count, block_ids and block_prefix. pair_prefix supplies the global class prefixes. multiplicity_histogram stores each multiplicity with the complete sorted class IDs. low_multiplicity saves both including-diameter and excluding-diameter families.

The loader makes a defensive copy and checks dimensions, the canonical displacement-index layout, value ranges, increasing q keys, prefix dimensions/order/endpoints, group-block links, block coverage, low-list ordering, histogram dimensions/partition size and diameter-ID placement. A reader indexes blocks and classes once.

It does not recompute q=a²+b² or the translation/orientation formulas, regroup geometry, recalculate the histogram or verify every prefix increment against its claimed weight. It does not independently authenticate low-multiplicity membership or prove a loaded slice complete. These mathematical relationships remain part of the constructor provenance.

The loader's checks are structural and arithmetic dimensions, not an independent geometry proof. Bind the complete data and executed source identities before using these results as authentic. Merely passing open does not certify a supplied foreign snapshot.

## Actual work and durable identities

The source was parsed, inspected, frozen and checkpointed before construction. A pre-freeze input-contract edit allowed transformed rank coordinates enough digits to accept the module's own bounded transform outputs; it changed no executed result.

- rectangle_distance_index.cjs: a2cf82b2a337c4d717313d74341ea61e8c4c11ef, 13,992 UTF-8 bytes.
- Initial complete constructor packet: 7d6141fc69eb598e2513e403186eda413182a1b3, 471,747 characters.
- Final data with all 26 reader outputs: bd42105427490aacc0d50f04fd40871ad6418c15, 524,266 UTF-8 bytes.

The sole constructor computed 4,716 displacement squares and zero point pairs. Its single wall observation was 5 ms. A fresh module context opened the snapshot in an observed 16 ms. These are observations, not performance benchmarks.

The reader made 26 queries, indexed 2,397 groups and 4,716 blocks, scanned 2,397 groups for one filter, and took 76 binary-search steps. It selected five pairs and ranked five pairs. It compiled zero displacements, recomputed zero base squared distances and enumerated zero point pairs. Exact transformed-coordinate and scaled-distance arithmetic is fresh query work and is not hidden by those counters.

An initial orchestration cell failed JavaScript parsing because unary minus directly preceded exponentiation. No module loading, reader opening or query executed in that cell. Parentheses were corrected in the orchestration only; the frozen implementation and sole construction were not rerun. The data records this disposition.

All source and complete data checkpoints were written as Git blobs before this guide. No accepted grid, pinned-distance, line or square-example computation was replayed; no native process, test suite or workflow was used.

The result gives reusable finite geometry navigation and exact multiplicities for one rectangle. It establishes neither of the general planar questions, a global extremal optimum, mathematical novelty nor a current external frontier.
