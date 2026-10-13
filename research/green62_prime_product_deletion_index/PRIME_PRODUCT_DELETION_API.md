# Prime products modulo 257 and target-specific prime deletions

This index records all products of exactly two primes below 257 and the complete deletion family that destroys each nonzero target residue. It is a finite navigation API: its counts concern a specified target and a subset of the 54 available primes. It does not settle the eventual-prime statement in Green's Problem 62, establish a threshold, certify an award claim, or assert mathematical novelty.

## Source and inherited inputs

Ben Green, *100 Open Problems*, Problem 62, printed p. 30, asks whether, for every sufficiently large prime p, every nonzero residue is a product of two primes strictly below p. The primary passage credits Erdős, Odlyzko and Sárközy (1987), reference 113. Repeated prime factors are not excluded. One is not a prime padding factor, and zero is not a target.

Primary source: https://people.maths.ox.ac.uk/greenbj/papers/open-problems.pdf#problem.62 . The exact statement was read; no source proof, numerical example, threshold or broader status survey was used.

The separately fully read FormalConjectures source is
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/GreensOpenProblems/62.lean .
Its observed full content has Git blob 65732969b4fef45cc0c9f9f38d95ba4235aa5bb0, 1,577 UTF-8 bytes. The request used the repository's default ref, rather than an independently pinned commit. Its research-open annotation and local placeholder are recorded as source metadata, not a proof review.

The new input is supplied in input257.json (61,235 bytes, blob c21b7c29112e926a838ecf136a054b2c054dc097). Its provenance binds two accepted premises:

| Premise | Immutable source | Exact retained data |
|---|---|---|
| Prime list and modulus | Commons #31789, merge 8f7f9ec9393a19d18789d72b23882f7f4657c5b7; research/erdos1094_binomial_valuation_index/input256.json, blob 522485b25d27bf7c37b0042dea6339fd4dea15d8 | All 54 primes from 2 through 251; next_prime=257 |
| Binomial rows and cumulative rows | Commons #31787, merge 73b115a70008c88293a6a2e0efd3be612e0f4f73; research/erdos10_selected_prime_binary_minima/bit70_minima_index.json, blob a781a03e3113d1bf6ecfe968178a33248d6dcacf | Literal pascal[0..54] and cumulative[0..54] |

No primality test, sieve, prior binomial valuation, binary-minimum computation, or Pascal recurrence was rerun. Prime completeness, primality of 257, and the supplied binomial identities are explicit inherited premises. The generic compiler checks ordering, dimensions and decimal syntax, not these mathematical premises.

## The finite certificate

The one production enumeration retains 1,485 unordered pairs i<=j, including all 54 diagonal pairs. Each row stores its prime indices, ordinary product, residue, quotient and ordered weight. An off-diagonal row represents two ordered pairs; a diagonal represents one. All 256 nonzero targets are covered, with 2,916 ordered representations in total.

Fix a nonzero target x. For a selected prime a, the congruence ab=x modulo the prime modulus has at most one partner b. Its unordered product fiber is consequently a matching, with possible loops. The constructor also checks that no prime index occurs in two different rows of a target's fiber. This is not a claim that fibers for different targets are disjoint.

Suppose a fiber has e ordinary edges, l loops and f unused prime vertices, so 2e+l+f=54. A deletion set destroys x exactly when it contains at least one endpoint of every edge and every loop vertex. Each unused vertex is optional. Its cardinality generating polynomial is

    z^l (2z + z^2)^e (1 + z)^f.

This formula counts subsets of prime vertices, not pair records or labelled endpoint choices. The two size-one choices on an ordinary edge delete its two different endpoints. The size-two choice deletes both. A loop has only one forced vertex.

The least deletion size is e+l, with 2^e minimum deletion sets. The saved coefficient at that degree provides the actual minimum count. Full deletion always destroys every target. If a generic input had an uncovered target, e=l=0 would give minimum zero and every deletion set would destroy that already absent target. The actual input has no uncovered target.

There are 20 different (e,l,f) profiles. Shared suffix states retain 176 nodes, 7,372 coefficient cells and 7,372 cumulative cells. A state with e>0 applies the factor 2z+z^2 to its child. A state with e=0 directly copies a saved binomial row, shifted by l zero cells; its cumulative row is copied with the same shift. The inherited cumulative rows include an initial zero, which the adapter removes to obtain the local inclusive convention. No free-bit/Pascal recurrence is evaluated.

| Selected target | Edges | Loops | Free vertices | Minimum deletions | Minimum deletion sets |
|---:|---:|---:|---:|---:|---:|
| 1 | 8 | 0 | 38 | 8 | 256 |
| 8 | 10 | 1 | 33 | 11 | 1,024 |
| 69 | 11 | 0 | 32 | 11 | 2,048 |
| 163 | 1 | 0 | 52 | 1 | 2 |
| 168 | 1 | 0 | 52 | 1 | 2 |
| 169 | 1 | 1 | 51 | 2 | 2 |
| 239 | 10 | 1 | 33 | 11 | 1,024 |

Minimum deletion sizes across the entire target family range from 1 to 11. Exactly targets 163 and 168 attain 1; exactly 8, 69 and 239 attain 11.

The only pair for 163 is 17*191=3247=12*257+163. The only pair for 168 is 229*251=57479=223*257+168. Target 169 has the loop 13*13 and the ordinary pair 29*59=1711=6*257+169. Ignoring diagonal representations would therefore change its deletion family.

The summary's target_deletion_incidences_by_size sums coefficients over all 256 targets. It counts (target, deletion-set) incidences. A deletion set that destroys several targets occurs several times in that array. It is not a count of distinct globally damaging palettes, and different target families are not treated as independent.

## Ordering and representation

Prime indices are zero-based in the supplied increasing list. Deleted masks and all potentially large counts/ranks are decimal strings. A mask is in [0,2^54); bit i records deletion of prime i. The remaining prime set is the complement inside this fixed host.

For each target the groups are:

1. Nonloop pairs, ordered by their first prime index.
2. Loop vertices in index order.
3. Unused vertices in index order.

At an ordinary pair the choices are first endpoint only, second endpoint only, both. At a loop the only choice is deletion. At an unused vertex the choices are keep, delete. Family ranks are zero-based in this lexicographic group-choice order, restricted to the requested deletion-cardinality interval. They are not numerical-mask order, prime-set lexicographic order, or increasing target order.

Every group covers disjoint prime indices within a target. Thus each path corresponds to exactly one deletion subset and vice versa. A range query uses saved cumulative coefficient differences. Rank and select sum the eligible suffix counts of preceding choices; their branch intervals partition the requested family. This gives the inverse relationship without generating the represented subsets.

## API

The CommonJS module exports compile(input) and openIndex(snapshot). Compilation is an explicit new production operation. Reading the shipped snapshot uses openIndex and does not invoke compile. The reader treats the supplied object as immutable; callers should not mutate its exposed records.

    const fs = require("node:fs");
    const {openIndex} = require("./prime_product_deletion_index.cjs");
    const saved = JSON.parse(fs.readFileSync("prime257_deletion_index.json", "utf8"));
    const api = openIndex(saved);

The example is for an independent consumer. It was not used to replay the accepted construction in this delivery.

| Method | Result |
|---|---|
| summary() | Saved full coverage, profile/state sizes and target-deletion incidence coefficients |
| profiles() | Saved (e,l,f) rows and their target lists |
| fiber(target) | Complete pair witnesses, ordered count, groups, state path and coefficients |
| family(target, options) | Exact count with min_deletions <= size <= max_deletions |
| select(target, rank, options) | Selected deleted mask, indices/primes and full decision trace |
| rank(target, mask, options) | Inverse rank or explicit nonmembership with surviving pair/count reason |
| page(target, start, limit, options) | At most 10,000 selected records, total and next rank |
| coverage(mask) | Every target's surviving unordered/ordered counts and first surviving pair |
| work() | Fresh reader operation counters |

Targets are integer residues 1..256; zero and out-of-range values are rejected. Omitted cardinality bounds mean [0,54]; inverted or out-of-range bounds are rejected. rank/select arguments that may be large use decimal strings or BigInt. A page start may equal the family size, yielding an empty page. Individual select ranks must be strictly smaller than that size. Rank/select/filtering does not silently convert large values to Number.

coverage scans saved product-pair records and checks deleted bits. It performs no product or modular arithmetic. A first surviving pair is a saved witness; its null value means this target is destroyed by the given deletion. An invalid target, mask, rank or malformed required input throws rather than being silently normalized.

The compiler caps the supplied instance at the declared limits: 128 primes, modulus 100,000, 20,000 pair products, 200,000 coefficient cells, 10,000 suffix states. Arithmetic products are safe integers within this modulus cap; counts use BigInt internally and decimal strings in the snapshot. The actual inherited rows use a much smaller host.

## Actual fresh reader

saved_reader_queries.json contains all 47 requests and full responses, including decision traces and complete coverage rows. Twelve selected masks were ranked back successfully: three size-27 selections, three minimum selections for strong targets, and all six exported minimum deletions for targets 163, 168 and 169.

For target 69 there are exactly 50,020,977,505,120 blocking deletion subsets of size 27. The actual reader selected ranks 0, 25,010,488,752,560 and 50,020,977,505,119. It did not enumerate this family.

A selected minimum blocking set for 69 is

    {2,3,11,19,37,43,59,79,83,127,227}.

Its mask is 281476056819859. The saved coverage query finds 255 surviving targets and exactly the target 69 absent. It leaves 946 unordered pairs and 1,849 ordered pairs.

Other coverage queries record:

| Deleted set | Surviving targets | Surviving unordered pairs | Surviving ordered pairs |
|---|---:|---:|---:|
| Empty | 256 | 1,485 | 2,916 |
| All 54 primes | 0 | 0 | 0 |
| First ten primes, mask 1023 | 253 | 990 | 1,936 |
| Target-69 size-27 rank zero, mask 17336890241919123 | 200 | 378 | 729 |
| Target-69 minimum rank zero, mask 281476056819859 | 255 | 946 | 1,849 |

The first-ten-primes deletion loses exactly 20, 163 and 169. All complete rows, including the 56 targets lost by the chosen size-27 deletion, are in the query file. The query plan also records an explicit nonmember: the empty deletion does not destroy 69.

The fresh reader performed 1,203 coefficient lookups, 1,341 group steps, 7,425 saved-pair scans, 13,607 bit checks and 21 mask decodes. It performed zero modular products and zero coefficient-recurrence operations. These are operation counts, not wall-clock timings or a claim that query arithmetic is absent.

## Construction work and chronology

The successful production retained 1,485 products, remainders and quotients; 2,916 matching-incidence checks; 10,628 weighted coefficient additions; 5,542 new cumulative additions; and 14,080 target-incidence coefficient additions. It copied 1,821 binomial coefficient entries and 1,821 cumulative entries, with 18 shifted zero cells. It performed zero primality tests, sieve operations or Pascal recurrence operations.

The first invocation failed at the binomial input-shape guard, before product arrays or polynomial states were constructed. Its source blob was 48e67e3516700425ee562a36b6089c697d4af214. It had incorrectly expected cumulative rows of length f+1. The inherited rows have length f+2 and a leading zero. The corrected source (1902fd61f38ca35bebf8a24d93b31fd1f0eb9c61) validates that shape and copies slice(1). The successful invocation was the first actual pair/polynomial construction; no failed or successful arithmetic output was replayed.

Input and source were banked before that production. The complete snapshot was banked before a fresh reader was opened. Each query request and returned response was banked immediately. All reader outputs survived; there is no missing-query disclosure for this packet. No post-construction check regenerated products, matching fibers, binomial coefficients or suffix recurrences.

## Files and identity boundary

| File | Purpose | Git blob |
|---|---|---|
| prime_product_deletion_index.cjs | Compiler and saved-data reader, 10,820 bytes | 1902fd61f38ca35bebf8a24d93b31fd1f0eb9c61 |
| input257.json | Literal source input and premise provenance, 61,235 bytes | c21b7c29112e926a838ecf136a054b2c054dc097 |
| prime257_deletion_index.json | Entire finite snapshot, 885,568 bytes | 49d5aa89b1d7c909d3dc0316d4daf58b69b486f7 |
| saved_reader_queries.json | Complete 47-query record, 231,153 bytes | ec8b16e8bb58dc3a0523742776fc0943287a50f4 |
| PRIME_PRODUCT_DELETION_API.md | Sources, derivation, interface and actual limitations | This guide |
| README.md | Entry point | Companion |

Git blob identity and complete content readbacks establish byte custody. They do not reprove a prime premise, replay a calculation, or establish the global conjecture. The finite count concerns this labelled prime universe and these target-specific deletion families only.
