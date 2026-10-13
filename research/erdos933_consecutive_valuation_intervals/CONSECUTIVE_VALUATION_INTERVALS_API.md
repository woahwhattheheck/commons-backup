# Consecutive valuation interval API

This index partitions the positive integers by capped 2-adic and 3-adic valuations of n(n+1). It retains exact v2 categories 1 through 12, an explicit v2 >= 13 overflow category, exact v3 categories 0 through 8, and an explicit v3 >= 9 overflow category. Its **130 cells** are represented by **910 arithmetic progressions**, with common period **161,243,136**. The separate saved reader counts and ranks integers in requested finite numerical intervals without enumerating or factoring those integers.

Exactly 108 cells have both valuations known; 22 involve at least one overflow category. An overflow label is a lower bound, never an asserted exact exponent. The API does not evaluate logarithms or decide the asymptotic source problem.

## Actual source and access boundary

The fully read [FormalConjectures 933](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/933.lean) defines

    k(n) = v2(n(n+1)),   l(n) = v3(n(n+1)),

and asks whether the limsup of 2^k(n) 3^l(n) / (n log n) is infinite. The 3,770-byte source text has Git blob identity bca2eeaf04405fb67be4a50b3bc5a60aff131d05. Its native contents request used the default repository ref and supplied no immutable commit, so the identity binds the actual returned text rather than every future main version.

The main theorem is annotated research open and retains a local placeholder. A separate Mahler variant is annotated solved with a placeholder. A further known lower-bound variant includes a proof script and an explicit example family. That example and proof were not evaluated, reverified, expanded, or used as the input to this consumer. The present work is not a formal-kernel audit or a claim about the global question's current frontier.

The cited bibliography is P. Erdős, “Problems and results on number theoretic properties of consecutive integers and related questions,” Proceedings of the Fifth Manitoba Conference on Numerical Mathematics (Winnipeg, 1975), Congressus Numerantium XVI, Utilitas Mathematica, 1976, pp. 25–44. The exact author archive https://combinatorica.hu/~p_erdos/1976-39.pdf returned a 400 timeout. No original convention passage was retrieved; the failed route remains held, with no retry, alternate copy, proof or example review. The actually read formal text supplies the valuation definition.

The API's positive-n restriction is explicit. It does not assign an exact finite valuation to n(n+1)=0 or inherit a library's convention for v_p(0). The caps 12 and 8 are this new finite input. No old prime search, sieve, least-factor table, accepted factorization or earlier valuation computation was repeated.

## Exact category construction

Consecutive positive integers are coprime, so for each prime all of the valuation of their product belongs to the factor divisible by that prime.

For a >= 1, exact v2(n(n+1)) = a is equivalent to

    n = 2^a or 2^a-1 modulo 2^(a+1).

Indeed, the divisible factor must be an odd multiple of 2^a modulo 2^(a+1). Every positive consecutive product is even, so an exact dyadic category zero is unnecessary. The overflow event v2 >= A+1 has residues 0 and -1 modulo 2^(A+1).

For v3 = 0, n has residue 1 modulo 3. For b >= 1, exact v3(n(n+1)) = b has four residues

    d*3^b or d*3^b-1 modulo 3^(b+1), for d in {1,2}.

The coefficient d records the two possible nonzero residues after dividing the divisible factor by 3^b. The overflow event v3 >= B+1 has residues 0 and -1 modulo 3^(B+1). Thus the zero ternary category and both overflow categories are essential parts of the partition.

For each pair of categories, the compiler combines every dyadic and ternary residue by the Chinese remainder theorem. Their moduli are coprime. If x is the dyadic residue, y is the ternary residue, and M2,M3 their moduli, it retains

    r = x + M2 * ((y-x) * inverse(M2 modulo M3) modulo M3),
    normalized modulo M2*M3.

The actual class modulus is retained for every cell. Different cells may contain equal-looking residue integers with different moduli; disjointness concerns their integer solution sets, not uniqueness of the literal residue number.

The axis categories exhaust and partition all positive integers. Their Cartesian CRT cells therefore also exhaust and partition the positive integers. Every class modulus divides the common period P=2^13*3^9. Summing each cell's residue count times P divided by its modulus gives P; that equality is retained as new construction accounting, not a replayed finite-integer census.

| New construction work | Value |
|---|---:|
| Power products | 22 |
| Euclidean steps | 465 |
| Distinct CRT inverses / inverse-cache hits | 108 / 22 |
| CRT residue pairs | 910 |
| Cell accounting terms | 130 |
| Individual integer enumeration / factorization / logarithms | 0 / 0 / 0 |

Each cell contains its axis indices, exact/overflow labels, lower exponent bounds, modulus, inverse, all residues, number of classes per common period, and smooth-factor information. The complete 39,909-byte snapshot has blob 0c600ddc9698f5e135417def13f4df87a7c67670.

## Exact finite-interval navigation

For a saved progression n = r modulo m, the number of integers in the closed positive interval [L,R] is

    floor((R-r)/m) - floor((L-1-r)/m).

The implementation uses mathematical floor, including negative numerators. JavaScript BigInt division truncates toward zero, so the helper explicitly subtracts one for a negative nonintegral quotient. This matters near the lower endpoint, even though L itself is positive.

A selected family is a union of disjoint cells. Its count is the sum of their progression counts. Numerical rank counts selected integers in [L,n-1]; select uses binary search for the smallest x with more than rank selected integers in [L,x]. The ordering is increasing integer n, with zero-based ranks and inclusive interval endpoints. It is not coordinate-lexicographic order, cell order, or class-residue order. All binary-search decision records are retained in actual select responses.

Condition arrays a and b choose categories on the respective axes. Exact categories are integer labels; the literal string "overflow" selects the corresponding unresolved category. Omitting an axis permits every category. An empty selected axis produces an empty family. Selecting overflow does not impose an upper bound on the actual valuation.

## Reader API

~~~javascript
const fs = require('fs');
const {openIndex} = require('./consecutive_valuation_intervals.cjs');
const data = JSON.parse(fs.readFileSync('capped_valuation_cells.json', 'utf8'));
const reader = openIndex(data);
const condition = {a:[7], b:[4]};
const lo = '100000000000000000000000000000000000123456789';
const hi = '100000000000000000001000000000000000123456789';
const count = reader.count(lo, hi, condition);
const selected = reader.select(lo, hi, '0', condition);
const inverse = reader.rank(lo, hi, selected.record.n, condition);
~~~

This is a CommonJS usage example. The actual source was loaded unchanged in V8, with no native executor, Node CLI or filesystem process.

| Method | Contract |
|---|---|
| compile(input) | Build the new power, category and CRT records once. |
| openIndex(saved, caches?) | Open trusted saved cells and optional complete range caches. |
| summary(), axes(), cells() | Return complete saved definitions and cells. |
| count(L,R,condition) | Exact family size in the positive closed interval. |
| counts(L,R,condition) | Complete per-cell count table and total. |
| classify(n) | Find the saved axis categories, return congruence quotient certificates and preserve overflow. |
| select(L,R,rank,condition) | Select an increasing-n rank and retain the binary decision trace. |
| rank(L,R,n,condition) | Return its rank, or null when n does not meet the condition. |
| page(L,R,start,limit,condition) | At most 50 consecutive selections and an explicit next rank. |
| caches(), work() | Complete new interval-mass caches and work counters. |

Endpoints, n and ranks accept BigInt, exact decimal strings and safe integer Numbers. Invalid or nonpositive endpoints, reversed intervals, duplicate/unknown category labels, negative ranks and out-of-family selections are rejected. Conditions retain numeric category types: the string "7" is not the exact category number 7. An endpoint page beginning at the family count is empty.

classify(n) tests n against saved axis residue classes. It does not repeatedly divide n(n+1) to recover valuations. Each axis returns n=q*m+r with saved modulus m and an allowed residue r; that is the retained congruence certificate.

For a cell with both valuations exact, the reader returns the exact smooth part 2^a3^b and computes the requested quotient n(n+1)/(2^a3^b). The category derivation establishes that this quotient is coprime to six, but it is not otherwise factored. If either axis overflows, smooth_part and remaining_coprime_to_6 are null. Only the smooth-factor lower bound is returned. No lower-bound exponent is relabelled as exact.

Saved snapshots and cache entries are trusted constructor output, not a hostile-input proof certificate. Fresh range counts, floor divisions, modulus tests and requested product arithmetic are query work. There is no new power table, CRT inverse or factorization in the reader.

## Actual first consumer

The main finite interval is

    L = 10^80 + 123456789,
    R = L + 10^25 + 987654321 - 1.

The complete 130-cell distribution over that interval is retained. Selected conditions give:

| Condition | Count |
|---|---:|
| Both valuations in their exact categories | 9,996,542,736,554,070,488,913,229 |
| Dyadic overflow, any ternary category | 2,441,406,250,000,000,241,126 |
| Ternary overflow, any dyadic category | 1,016,105,268,505,817,303,018 |
| Both overflow | 248,072,575,318,803,052 |
| Exact a in {8,9,10,11,12}, exact b in {5,6,7,8} | 615,219,986,790,631,570,187 |
| Exact a=7, b=4 | 1,286,008,230,452,675,024,134 |
| Exact b=0, any dyadic category | 3,333,333,333,333,333,662,551,441 |
| Empty dyadic selection | 0 |

The separate reader retained **58 complete responses**, **21 inverse rank matches**, and **1,775 complete interval-mass cache entries**. First, middle and last ranks of seven nonempty conditions were selected and ranked back. Five additional members of the exact a=7,b=4 cell were paged with their complete decision traces.

A separate large query n=P*(10^90+37)-1 is deliberately left in the two overflow categories. It has certified v2 >= 13 and v3 >= 9, and a smooth-factor lower bound P=161,243,136. Its exact smooth part and residual factor remain null. The reader also retains classification of L and all selected-cell counts on the short positive interval [5,75]; no exact valuation of zero is introduced.

| Fresh reader work | Value |
|---|---:|
| Condition normalizations / cell-filter reads | 58 / 7,540 |
| Range-cache hits / misses | 441 / 1,775 |
| Progression counts / mathematical floor divisions | 277,726 / 555,452 |
| Binary-search steps | 2,162 |
| Axis modulus tests / saved-residue reads | 603 / 1,480 |
| Congruence quotient certificates | 98 |
| Requested product evaluations for exact smooth cells | 30 |
| New powers / CRT constructions / factorizations | 0 / 0 / 0 |

These are named-operation counters, not elapsed-time benchmarks or complete instruction counts. Both construction and reader completed once without an error, and every actual query response was banked immediately.

## Complete serialization

The full reader packet is 1,068,749 bytes, blob 121cd398835dc13c42caf2130d4567cbf856925d. Four complete query shards and a manifest preserve all 58 responses. The manifest retains the original queries property as null; replacing it with the concatenated shard arrays and serializing with two-space indentation plus a final newline exactly reproduced the original bytes. That is a byte-custody check, not a rerun of the queries.

The complete cache is stored separately and may be supplied to openIndex for later reuse. No counts or decision traces are sampled.

| Artifact | Bytes | Blob |
|---|---:|---|
| consecutive_valuation_intervals.cjs | 8429 | a21aa75c59981b51078c9c79d31b866c1d3aae08 |
| input_caps.json | 1035 | 68ac99a0311d798bfedffcd72ba87b53d9edc7d4 |
| capped_valuation_cells.json | 39909 | 0c600ddc9698f5e135417def13f4df87a7c67670 |
| reader_manifest.json | 5525 | 2e9be4b71e6403ef16ce176be2094986330f188d |
| reader_queries_0.json | 272236 | bcb8d676ac97f4178916657b3c03017f43863bfd |
| reader_queries_1.json | 214203 | f4e86d955c81844ba3807692cff215791689ce31 |
| reader_queries_2.json | 248168 | ce35282c1fca1f8b6bca1711615eb6dadd49de90 |
| reader_queries_3.json | 287771 | ad48b54dd384025051df8095a4adc18ad003acc5 |
| saved_range_caches.json | 530398 | 4a37a7d4f3949dd39be83e17a18e9acb557246a3 |

The guide and README preserve the exact definition, original-source access gap, positive domain, finite caps, overflow semantics and actual consumer. This is an interval-navigation capability for declared valuation categories. It does not settle the logarithmic limsup, reproduce the known lower-bound construction, establish a new smooth-number theorem, certify a linked proof, or claim mathematical priority or prize progress.
