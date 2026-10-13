# Exact subsets in a finite five-cycle graph product

This package counts and navigates every independent subset and every clique in one explicitly defined graph on **390,625 labelled vertices**. Vertices are length-eight words over five symbols. Distinct words are adjacent precisely when their first differing coordinates are adjacent on the cycle 0–1–2–3–4–0.

Both the maximum independent-set size and the maximum clique size are **256**. There are 5^255 maximum members in each mode. The complete cardinality profile, including the empty subset, is retained exactly. Counts are BigInts; the total number of subsets in either mode has 220 decimal digits.

The new construction composes eight polynomial levels from the identified saved five-cycle family. It does not enumerate the product graph's vertices, edges or subsets. The fresh reader retained **79 complete responses**, **30 select/rank inverse matches**, 35 selected subsets containing 3,308 returned vertex entries, and eight exact vertex-marginal queries. Reader coefficient products used for allocation decisions are reported separately from the saved polynomial construction.

## Source and scope

The fully read [FormalConjectures Erdős 77 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/77.lean) defines R(k) as the least n for which every two-coloring of the edges of K_n has a monochromatic K_k. It asks for the limit of R(k)^(1/k), with its formal statement requiring convergence to the requested value. The observed source annotation is research open and the local proof is a placeholder.

The actual request used the Contents endpoint for FormalConjectures/ErdosProblems/77.lean at the repository default ref. Its full returned text has 2,098 bytes and local Git blob ad95571444c307e01b1bad4b146ec6f296b79dee. No immutable source commit was supplied for that response. Source annotations are not a Lean run, proof audit or independently established frontier.

The product used here is the ordinary lexicographic five-cycle power, defined explicitly below. A bounded independent source lookup identified Bao-Xuan Zhu and Qinglin Lu, *Unimodality of the independence polynomials of some composite graphs*, arXiv:1507.05754 (2015). Its indexed author abstract names the lexicographic product and independence-polynomial notation. The exact PDF https://arxiv.org/pdf/1507.05754 returned DisabledError and remains held; no HTML version, alternate copy or retry was used. No adjacency definition or polynomial-composition theorem was independently read in that paper. The present guide derives the recurrence directly from its explicit finite graph definition and does not attribute that derivation to an unread passage.

This construction supplies no new Ramsey record, asymptotic improvement or value of the root limit. Its large graph is represented through classical recursive structure; large vertex count alone is not evidence of progress on the asymptotic problem. No sponsor contact or submission occurred.

## Exact inherited base input

The base independent subsets come from the accepted six-vertex atlas in [Commons #31710](https://github.com/woahwhattheheck/commons/pull/31710), retained as input by [#31834](https://github.com/woahwhattheheck/commons/pull/31834). The relevant six-vertex graph is C₅ on vertices 0,...,4 together with isolated vertex 5. Only subset masks below 32 are selected, so vertex 5 is excluded.

| Input identity | Value |
|---|---|
| Original merge | b31ce2319839cfcebae956e9e63757b355ee9fb1 |
| Original row shard | research/erdos82_regular_induced_universe/six_vertex_rows_0.json |
| Row-shard blob | 118c6759ce0c5e3ab16fca22578263999f310a26 |
| Graph mask | 4649 |
| Saved degree-zero subset bitfield | 15073700150737 (hexadecimal) |
| Retained via merge | 48d400e8ddad6995d7ae9fd01fd2564e88ab10b4 |
| New explicit input | input_depth8.json |
| Input bytes / blob | 2,495 / f76dd1cccb112ed10d013e3229c16014fdd37367 |

In the old fifteen-edge ordering, the five cycle edges have indices 0,5,9,12,3. The extraction uses saved subset descriptors and the identified bitfield; it does not evaluate adjacency, induced degrees or independent-set predicates.

The eleven retained base masks, in order, are

    0, 1, 2, 4, 5, 8, 9, 10, 16, 18, 20.

They describe the empty set, five singletons and five nonadjacent pairs. The input's vertices arrays preserve the exact members of each record. This accepted base family is a premise of the new compiler, not a newly certified output of the old graph atlas. Source identity and structural consistency do not themselves reprove its semantics.

No old graph enumeration, degree computation, regularity census, independent-family search, cut computation, tournament construction or prior Ramsey calculation is replayed.

## Graph definition and labels

For depth d≥0, vertices are words of length d over {0,1,2,3,4}. The depth-zero graph has one vertex, the empty word. A word (a₀,...,a_{d−1}) has integer label

    a₀5^(d−1) + a₁5^(d−2) + ... + a_{d−1}.

For two different words, locate their first differing position. They are adjacent exactly when the two symbols there differ by 1 or 4 modulo 5. Equal words have no loop.

Equivalently, the graph at depth d consists of five labelled copies of the depth-(d−1) graph. Consecutive outer copies are joined completely, while nonconsecutive outer copies have no cross edges. This explicitly fixes the convention; it is not a Cartesian, tensor or strong graph product.

The actual depth is eight. Every vertex label is an integer from 0 through 390,624. Vertex labels are distinguished; no isomorphism or automorphism quotient is taken.

## Direct counting derivation

Let P_d(z) count independent subsets by cardinality, including the empty subset. At depth zero,

    P_0(z) = 1 + z.

For d≥1, consider the outer copies met by an independent subset. Those occupied digits must form one of the eleven retained independent patterns of C₅. For each occupied digit, the subset inside that copy is a nonempty independent subset of depth d−1. Unoccupied digits contribute no vertices.

The decomposition into an outer pattern and its child subsets is unique. Put Q=P_{d−1}−1. The empty outer pattern contributes one, the five singleton patterns contribute 5Q, and the five two-digit patterns contribute 5Q². Hence

    P_d(z) = 1 + 5(P_{d−1}(z)−1) + 5(P_{d−1}(z)−1)².

The square counts ordered child choices in the increasing order of the two occupied outer digits. It does not divide by two: the child copies are different labelled vertex blocks. Each unordered vertex subset still occurs exactly once because its outer pattern and its two labelled child subsets are fixed.

The compiler retains every coefficient of every P_d, together with the nonempty powers Q⁰,Q¹,Q² used by navigation. No floating-point approximation, sample or truncated coefficient range is used.

Maximum size doubles at every level, so it is 2^d. Let M_d count maximum independent subsets. Then M_0=1 and M_d=5M_{d−1}², giving

    M_d = 5^(2^d−1).

At d=8 this yields size 256 and count 5^255, agreeing with the retained highest coefficient. This formula explains the compilation; no independent numerical power was recomputed as a test.

## Clique mode

The digit permutation

    0→0, 1→2, 2→4, 3→1, 4→3

is multiplication by two modulo five. On distinct digits it exchanges adjacency and nonadjacency of C₅. Applied in every coordinate, it leaves the position of the first difference unchanged and exchanges adjacency and nonadjacency of the full graph.

Consequently it bijects independent subsets with cliques, preserving cardinality. The compiler stores one coefficient table shared by both modes. Clique selection applies this digit permutation to an independent subset; clique ranking applies the inverse permutation first. A clique is counted as its vertex set, not as an ordering of its vertices.

This is a same-two-color graph construction across every level. It is distinct from multicolor constructions that allocate separate palettes to the first differing coordinate.

## Actual construction

The source and input were banked before the compiler ran once. Its complete result was banked before opening the saved reader. There were no construction errors or reconstruction runs.

| Depth | Vertices | Maximum subset size | Decimal digits in total |
|---:|---:|---:|---:|
| 0 | 1 | 1 | 1 |
| 1 | 5 | 2 | 2 |
| 2 | 25 | 4 | 3 |
| 3 | 125 | 8 | 7 |
| 4 | 625 | 16 | 14 |
| 5 | 3,125 | 32 | 27 |
| 6 | 15,625 | 64 | 55 |
| 7 | 78,125 | 128 | 110 |
| 8 | 390,625 | 256 | 220 |

The full exact integers appear in the saved data. The maximum-family count at depth eight has 179 decimal digits.

| Compiler work | Actual count |
|---|---:|
| Saved base records read | 11 |
| Polynomial levels composed | 8 |
| Convolution products | 21,845 |
| Convolution additions | 21,845 |
| Weighted coefficient additions | 510 |
| Cardinality coefficient cells | 520 |
| Nonempty-power coefficient cells | 795 |
| Old graph enumeration | 0 |
| Old independent-set tests | 0 |
| Old induced-degree computation | 0 |
| Product vertices enumerated | 0 |
| Product edges enumerated | 0 |

The compiler forms the new polynomial coefficients, including the base-pattern cardinality polynomial. It does not re-evaluate the saved base subsets' graph properties.

## API and canonical ordering

Load depth8_certificate.json, then call openIndex from lexicographic_subsets.cjs. The source exports compile(input) for a genuinely new input and openIndex(saved) for saved navigation. Do not invoke compile to answer a query against this published certificate.

| Method | Result |
|---|---|
| summary() | Saved input size, maximum sizes, exact totals and compiler work |
| profile(depth=8) | Complete saved polynomial and nonempty-power rows at that depth |
| select(options, rankText) | A complete vertex subset and recursive decision trace |
| rank(options, vertices) | Inverse rank, or null for a well-formed nonmember |
| page(options, offsetText, limit) | Up to 32 selected records |
| marginal(options, vertex) | Exact counts containing and avoiding one vertex |
| adjacency(x,y,depth=8) | First differing coordinate and its declared adjacency |
| exportAllocationCache() | Complete fresh-query coefficient-product cache |
| work() | Actual saved-reader work |

options contains depth, mode and size. Defaults are the full depth, mode="independent", and size=null. mode may be "independent" or "clique". A non-null size restricts to that exact cardinality. Ranks are canonical nonnegative decimal strings; vertex labels and depth/cardinality parameters are bounded safe integers.

For a fixed cardinality, recursive order is:

1. The outer independent pattern, by increasing saved mask.
2. For a two-child pattern, the positive cardinality of its first child, in increasing order; the second child has the remaining size.
3. Child ranks in mixed-radix order, first child before second.

For all cardinalities, size is the first ordering key. Clique mode inherits this order through the digit permutation; it is not separately sorted by its resulting vertex labels. Returned vertex lists are numerically sorted for convenient use, but ranks do not mean lexicographic order of those lists.

Each two-child allocation has weight c_{d−1}(a)c_{d−1}(k−a). The reader computes only products actually needed by its queries and caches them by depth, total size and first-child size. This is explicitly new query arithmetic. It does not rebuild Q² or any complete level polynomial.

Selection subtracts pattern and allocation blocks, then divides a selected block rank into child ranks. Ranking groups supplied vertices by their first digit, identifies the saved outer pattern, recursively ranks children, and adds preceding blocks. The two procedures use the same unique decomposition. Traces retain depth, block offset, outer pattern, child sizes and child or local ranks.

An absent well-formed subset yields null. Duplicate vertex labels, malformed decimal ranks, unsupported modes and out-of-range parameters are rejected. Generic malformed-input and resource-limit branches were source-inspected but are not presented as executed tests.

## Exact single-vertex marginals

Coordinatewise rotations of C₅ act transitively on the vertices of every depth. They preserve adjacency and therefore independent subsets and cliques. For a fixed size k, every vertex belongs to the same number of qualifying subsets.

If c_d(k) is the saved count and N=5^d, double-counting vertex/subset incidences gives

    containing(v,k) = k c_d(k) / N.

For all sizes, the numerator is Σ_k k c_d(k). Avoiding is the total minus containing. The implementation performs exact BigInt division and rejects a nonintegral result. This transitivity derivation justifies the quotient; the division check alone would not prove it.

The actual reader queried vertex zero in independent mode and vertex 390,624 in clique mode, for all sizes and for sizes 17,128,256. These eight responses retain their complete decimal counts and their declared interpretation. They do not provide multi-vertex conditioning or a general graph marginal oracle.

## Actual saved-reader use

All 79 requests and complete responses were banked individually immediately after execution. All 30 select/rank inverse checks matched. No reader response was lost and no corrected query path was needed.

The consumer used first, middle and last ranks in both modes for the full family and exact sizes 2,17,128,256. It also retained the two empty selections, eight marginals, three complete depth-two maximum independent subsets, and direct adjacency/closed-absence queries.

The first pair from a selected maximum independent subset differs at coordinate seven with digits 2 and 4 and is nonadjacent. The first pair from a selected maximum clique differs there with digits 3 and 4 and is adjacent. An equal-vertex query reports no loop. The invalid independent pair [0,1] and invalid clique pair [0,2] both return null. These are concrete first-use outputs of the declared API, not exhaustive pairwise verification of every selected set.

| Reader work | Actual count |
|---|---:|
| Saved levels indexed | 9 |
| Saved coefficient cells indexed | 520 |
| Coefficient reads | 68,855 |
| Pattern visits | 61,960 |
| Fresh allocation products | 514 |
| Allocation-cache hits | 5,843 |
| Rank additions | 32,764 |
| Recursive tree nodes visited | 14,383 |
| Vertex-digit operations | 26,416 |
| Selected subsets | 35 |
| Returned vertex entries | 3,308 |
| Marginal products | 518 |
| Marginal divisions | 8 |
| New complete convolutions | 0 |
| New level polynomials | 0 |
| Graph-edge enumeration | 0 |

The final 514-entry allocation cache is retained with all original responses. Saved opening checks shapes and parses counts; it does not rederive the polynomials or reauthenticate the accepted base-family theorem.

## Files and custody

| Artifact | Bytes | Git blob |
|---|---:|---|
| Frozen source | 10,178 | eaa133819321c8b9a4e2ced9e3c761d34e7c013f |
| Exact input | 2,495 | f76dd1cccb112ed10d013e3229c16014fdd37367 |
| Complete construction | 140,013 | 2d30785b6e4d7686c4e8393f706e635835e2b1fc |
| Full assembled reader | 834,010 | 7661dfea518729254da56afb6b882cc40ce2fae1 |
| Reader manifest | 67,500 | 4c31fa6f3a3acd94bf2ed17c47fcec9634260b41 |
| Reader outputs 00 | 408,688 | aa265f40fea22d309b8a69124bc748b6315d137c |
| Reader outputs 01 | 358,257 | abdb8523cdad0299c1dc0b42868f3166b1413b29 |
| Reader loader | 444 | 927e6a5fe22db7ff42f5800883e1fab8fd04e08d |

reader_manifest.json preserves all packet fields except outputs, which are carried in two ordered complete shards. The first contains responses 1–32 and the second 33–79. load_reader.cjs checks their start/count fields and assembles the packet. Reassembly matched the original JSON plus its trailing newline byte-for-byte, without invoking either compiler or reader.

The exact constructor data is a single complete file, depth8_certificate.json. The complete input, lineage and resource contract are also published separately as input_depth8.json. The manifests' hashes are custody metadata, not a substitute for obtaining the complete content.

## Cost and limitations

At level d, the largest size is 2^d. The direct convolution uses O(4^d) coefficient products, while the graph has 5^d vertices. These bounds describe this explicit recursive family. BigInt arithmetic costs grow with coefficient size and are not assumed constant in a general complexity claim.

Outputting a selected k-vertex subset necessarily costs at least k entries. The reader traverses only the recursive decomposition required by the selected or supplied subset, scans finite allocation choices, and reuses saved coefficients. It is not claimed to give constant-time rank/select.

The implementation permits depth at most ten and polynomial degree at most 1,024, caps retained coefficient/power cells at 100,000, and bounds supplied vertex lists by 1,024. The actual construction and reader concern depth eight, with a small depth-two page and depth-four profile also queried. Unexercised depths and failure branches are not promoted to tested coverage.

This graph has neither a clique nor an independent set of size 257, but that finite fact is not presented as a competitive Ramsey bound. The package does not establish existence or the value of the general root limit, compare best-known bounds, prove a new product theorem, or claim priority. It supplies complete exact navigation and actual saved evidence for the declared classical family.
