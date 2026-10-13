# Exact horizontal sections of a polynomial lemniscate

This package constructs and navigates an exact real section of a polynomial lemniscate. It considers
`p(z) = ∏(z-r)` for supplied distinct integer roots and the horizontal line `z=x+i/q`, with a positive integer q. Its boundary equation is `|p(x+i/q)|=1`; its filled section is `|p(x+i/q)|≤1`.

The actual input is the six literal roots **4, 7, 32, 50, 52, 61**, q = **1,000,000,000,000**, and isolation precision **64 bits**. The once-only construction found **12 distinct real boundary intersections and six closed filled components**. Every retained boundary root is enclosed by an open rational interval of width at most 2^-64. No root in this run was encountered as an exact rational midpoint.

These are line-section results. They do not give the total planar curve length, a length maximizer, or an extremal theorem.

## Source and scope

Alexandre Eremenko and Walter Hayman, [On the length of lemniscates](https://www.math.purdue.edu/~eremenko/dvi/erdos23.pdf), define E(p)={z:|p(z)|=1} for monic p and describe the historical Erdős–Herzog–Piranian length conjecture with the literal normalization p(z)=z^d+1. Their first-page definition concerns the full planar level set. The rational horizontal specialization, arithmetic implementation, and saved navigation here are this package's finite construction.

The intake associated this topic with Erdős 114, but the exact number binding was not independently established. The attempted FormalConjectures/ErdosProblems/114.lean contents route returned 404 and remains held. No canonical page, linked proof, current extremal bound, or general resolution is asserted. The neutral directory name reflects this scope.

Anthony J. Narkawicz and César A. Muñoz, [A Formally-Verified Decision Procedure for Univariate Polynomial Computation Based on Sturm's Theorem](https://shemesh.larc.nasa.gov/fm/papers/NASA-TM-2014-218548.pdf), NASA/TM–2014-218548 (November 2014), §2, supplies the classical signed-remainder chain and Sturm variation theorem. Their chain permits positive scaling and identifies the standard scale 1. Their stated endpoint theorem counts roots in (a,b] when neither endpoint is a multiple root; the nonroot-endpoint specialization supplies the usual distinct-root count. Their formal development and proof were not reviewed here. The one-sided Taylor endpoint treatment below is an explicit derivation used by this implementation, not an attributed NASA API or verification of this code.

A separate Texas A&M sturm.pdf route returned text 404 and remains held. The NASA source was independently surfaced. No screenshot or visual-inspection claim is made.

## Exact input lineage

The six root parameters are the first six literal entries of the already accepted Singer difference-set array:
- Original accepted input: Commons #31474, `research/ppl088_erdos30_singer_plane/prime13_singer_plane.json`, blob `5561a91eddf8cfd7911641702b60cd51e308078d`.
- The literal array was already retained through #31568.
- This construction uses only six integers. It needs no finite-field, Singer, difference-set, incidence, or affine-group property and repeats none of those calculations.

The complete current input, including lineage and finite-scope declaration, was banked before computation as blob `4f90a537b28b69e018d534bc728e5ba41992e2d1` (545 UTF-8 bytes). It is also included verbatim as the snapshot's `input` object. The frozen executed source is blob `d4b1c86a23908a4b949810f886167434e09ee6b1` (8,309 bytes).

## Algebra and certificate

Write
`Q(x)=q^d p(x+i/q)=∏(q(x-r)+i)=R(x)+i I(x)`.
R and I have integer coefficients. Hence the integer polynomial
`F(x)=R(x)^2+I(x)^2-q^(2d)`
has exactly the section boundary as its real zero set, and F≤0 is exactly the filled section. Coefficient arrays use ascending powers.

The source removes only a positive integer content from F. It starts the chain with that primitive polynomial and a positive-content normalization of its derivative. Each subsequent member is the negative rational Euclidean remainder, with denominators cleared by a positive least common multiple and then a positive content removed. It never flips a remainder merely to make its leading coefficient positive. Positive scaling preserves the signs needed by Sturm's theorem.

This implementation accepts only squarefree section polynomials: a zero remainder before the chain reaches a nonzero constant throws. The actual degree-12 polynomial produced a 13-member chain ending at a constant. The saved chain omits the conventional final zero polynomial, which contributes no variation.

For rational c, the sign immediately to the right of any nonzero chain polynomial is the sign of its first nonzero Taylor coefficient at c. The left sign is that sign multiplied by (-1)^j, where j is its vanishing order. Successive derivatives find this coefficient sign because j! is positive. Thus an endpoint certificate retains both sign arrays and both variation limits:
- V(c+) is `Vright`;
- V(c-) is `Vleft`;
- the number of roots in the open interval (a,b) is V(a+)-V(b-).

The source uses this open-interval rule even when an endpoint is a root. A midpoint root is retained as a singleton and excluded from both adjacent open intervals. In the squarefree contract its jump must be one. This avoids assigning the same root to two children. The actual run needed no Taylor derivative fallback and found no exact midpoint root; those generic branches are supported by the stated algebra, not by a claimed executed example.

All real roots lie between min(r)-1 and max(r)+1. Outside that range every factor has modulus greater than one, since |x-r|≥1 and 1/q>0, so F is positive. The actual bounds are [3,62]. The complete interval's variation difference is 12. Each retained split records its midpoint endpoint, parent, depth, and open-root count. Empty leaves are retained too. Count-one leaves are accepted only once their rational width is at most 2^-64. This covers every root without a floating-point approximation or a numerical sign heuristic.

Because F is positive outside the bounding interval and all real roots are simple, its sign alternates across the sorted roots. The filled section is therefore the union of the closed components pairing root ranks (0,1), (2,3), ..., (10,11). Component endpoints are these algebraic roots, not the rational isolating endpoints. A rational root, if present in another accepted input, would be represented by its exact singleton.

## Actual construction

| Retained quantity | Value |
| --- | ---: |
| Polynomial degree d | 6 |
| Section degree | 12 |
| Nonzero Sturm members | 13 |
| Distinct real boundary roots | 12 |
| Filled components | 6 |
| Unique endpoint certificates | 671 |
| Isolation-tree nodes, including empty leaves | 1,339 |
| Exact rational midpoint roots | 0 |
| Isolation width bound | 2^-64 |
| Gaussian factor products | 6 |
| Rational polynomial division steps | 22 |
| Polynomial sign evaluations | 8,723 |
| Horner steps | 52,338 |
| Taylor derivative fallbacks | 0 |

The complete snapshot is `six_root_section.json`, blob `feccc25e1feff09cecda320989802a1910053410`, **697,838 UTF-8 bytes**. These counters describe the explicitly named operations in the source; they are not a total BigInt operation count or a complexity theorem.

The first root is in
`(4722366371197086256867/1180591620717411303424, 2361183185598543128463/590295810358705651712)`.
The last root is in
`(9002011124669931145797/147573952589676412928, 72016088997359449166435/1180591620717411303424)`.
All twelve intervals are stored in increasing root order. These rational bounds are exact.

## API

The CommonJS module exports `buildIndex(input)` and `openIndex(snapshot)`. The retained consumer should open the supplied snapshot. Calling the constructor creates a new certificate and is unnecessary for saved queries.

```javascript
const {openIndex} = require("./polynomial_lemniscate_sections.cjs");
const snapshot = require("./six_root_section.json");
const index = openIndex(snapshot);
const first = index.query({op:"root", rank:0});
const count = index.query({op:"count", left:"4", right:"7"});
const atFour = index.query({op:"point", x:"4"});
console.log(first, count.open_root_count, atFour.in_filled_section);
```

Rational query values are exact strings such as `"4"`, `"-3/7"`, or a decimal integer string. Denominators must be positive. Strings longer than 2,048 characters are rejected. Ratios are reduced on parsing. Ranks and IDs are zero-based; integer roots in the constructor are JavaScript safe integers. The constructor requires 2–8 strictly increasing distinct roots with absolute value at most 1,000,000, a positive decimal q of at most 50 digits, and precision between 8 and 128. Isolation is capped at 10,000 nodes and depth 256; exceeding a cap throws rather than returning a partial certificate.

| Query | Result |
| --- | --- |
| `summary` | Saved finite counts and precision |
| `polynomial` | Scaled real/imaginary arrays, full and primitive section polynomials |
| `chain` | Complete saved nonzero signed Sturm chain |
| `root, rank` | One stored isolating interval or exact singleton |
| `rootsPage, start, limit` | Consecutive root records; limit 0–1,000 |
| `component, id` | One pair of algebraic root ranks, with closed endpoints |
| `savedEndpoint, id` | A saved sign/Taylor/variation certificate |
| `treeNode, id` | One saved isolation record |
| `point, x` | Fresh exact sign and one-sided variation at x, number of roots strictly below x, boundary flag, and filled-section membership |
| `count, left, right` | Fresh endpoint certificates and distinct root count in the open interval; left must be smaller |

`point` and `count` accept rational values outside [3,62] as well. The saved left-bound variation equals the variation at negative infinity, since no roots lie below that bound. This justifies `roots_strictly_less = V(savedLeft+) - V(x-)`.

The reader parses and structurally checks the identified snapshot. It does not independently verify every chain remainder, isolation-tree split, or source premise. It is a trusted-certificate reader, not a proof checker for adversarial input. Returned records are JSON copies, and no mutation of the caller's returned value changes saved records.

## Fresh reader evidence

All **31** successful reader responses were individually banked before the next query; their complete aggregate is `saved_reader_queries.json`, blob `db1d160c1ba0d2aa11bbe119c1364aaf8fa50635`, **63,233 bytes**. There was no failed query, missing response, or source correction in this run.

The reader opened the saved index once and performed **247 fresh polynomial sign evaluations and 1,482 Horner steps**, with zero Taylor derivative fallbacks. It did not reconstruct the Gaussian product, Sturm chain, or isolation tree. Stored-record access, rational reduction, copies, and integer arithmetic are not claimed to be zero-cost or included in the scoped Horner counter.

Selected exact results:
- The point x=4 lies inside the filled section with one boundary root strictly below it; x=7,32,50,52,61 similarly lie inside, with 3,5,7,9,11 roots below them.
- x=0 and x=5 are outside, with zero and two roots below them.
- x=10^200 is outside and has all twelve roots below it.
- The open interval (3,62) contains all twelve roots; (4,7) contains two.
- The open interval (-10^100,4) contains one root.
- Fresh counts of the saved first and last isolating intervals are one each.
- The reader returned all twelve root records, all six components, selected endpoint/tree records, and an empty page starting at rank 12.

These outputs exercise exact finite navigation. They do not measure the planar level-set length, establish extremality of this polynomial, or resolve the historically attributed conjecture.

## Files and reproducibility boundary

- `polynomial_lemniscate_sections.cjs`: complete constructor and saved reader.
- `six_root_section.json`: full polynomial, Sturm, endpoint, tree, root, and component certificate.
- `saved_reader_queries.json`: all 31 requests, responses, cumulative scoped counters, and source/snapshot identities.
- This guide and `README.md`: conventions, lineage, proof argument, usage, and limits.

The actual construction ran once from the frozen input. The fresh reader consumed its saved result. No accepted Singer construction, earlier geometric classification, external proof, or unavailable response was replayed.
