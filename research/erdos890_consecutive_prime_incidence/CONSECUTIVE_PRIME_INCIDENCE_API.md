# Consecutive-window prime-incidence API

This package indexes a declared finite-prime screen for four consecutive positive integers. Its twelve primes are 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41 and 43. One compilation represents every residue class modulo their product through complete multivariate suffix coefficients. A separate reader provides exact counts, per-offset conditions, coordinate-order rank/select, pages and divisibility witnesses for requested positive integers.

The complete period is **2,180,460,221,945,005**. Of its residue classes, **369,766,473,834,496** have more than four palette incidences and therefore certify that the unrestricted sum in the source question exceeds four. The other **1,810,693,748,110,509** classes are palette survivors only. Their missing prime factors are not classified.

## Source statement and coverage

The fully read [FormalConjectures 890](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/890.lean) defines omegaGt(k,n) by counting the distinct prime divisors of n strictly greater than k. Part a asks whether, for every k at least one,

    liminf as n tends to infinity of sum_{i=0}^{k-1} omegaGt(k,n+i) <= k.

The actual 2,909-byte text has Git blob identity 9a0cc315538facca7a33b696d5556ad0a9f59931. The native contents request used the repository's default ref; it did not return an immutable source commit. This identifies the text actually consumed, not a future main version. Its main part-a and part-b annotations are research open, and their local proofs are placeholders. The separately annotated solved unrestricted-omega variants are not checked or reproved here. Part b is a different limsup statement and does not define this finite screen.

The source cites P. Erdős and J. L. Selfridge, “Some problems on the prime factors of consecutive integers,” Illinois Journal of Mathematics 11(3) (1967), 428–430, DOI 10.1215/IJM/1256054564. That bibliography was independently located, but the exact author archive https://combinatorica.hu/~p_erdos/1967-21.pdf returned a 400 timeout. No original-paper convention passage was obtained, and that route remains held without retry or alternate copy. The actually read formal text supplies the mathematical contract; no original proof, examples, current frontier or prize terms were reviewed.

The API restricts n to positive integers. It does not assign a factorization to zero or transfer a formal natural-number zero convention into a divisibility witness. Repeated prime powers count once. Primes at most four are outside this screen, and primes above 43 are unclassified.

## Exact inherited input

The twelve primes are copied from zero-based indices 2 through 13 of the retained prime list in [#31789](https://github.com/woahwhattheheck/commons/pull/31789), at merge 8f7f9ec9393a19d18789d72b23882f7f4657c5b7:

    research/erdos1094_binomial_valuation_index/input256.json
    1,973 bytes, blob 522485b25d27bf7c37b0042dea6339fd4dea15d8

The retained full input bytes were compared with this identity before copying the literal values. Distinct primality is an explicit accepted premise. No prime search, sieve, old least-factor data, factorial valuation, binomial factorization or earlier numerical calculation was used or repeated. The new input file records both this lineage and the exact formal-text identity.

## Finite screen and why it is exact

For fixed k and a supplied prime p greater than k, at most one of n, n+1, ..., n+k-1 is divisible by p: if p divided two, it would divide a nonzero difference smaller than p. The residue n modulo p therefore contributes either one hit to a unique offset or no hit.

For offset i, the unique hit residue is -i modulo p. The k residues are distinct. The other p-k residues contribute no hit. In increasing residue order, the saved groups are:

| Residues | Contribution |
|---|---|
| 0 | Offset 0 |
| 1 through p-k | No hit |
| p-k+1 through p-1 | Offsets k-1 down through 1 |

Each coordinate thus has k+1 groups but p actual choices. A no-hit group is an interval of p-k distinct residues, not a single residue. The counts retain that multiplicity.

Because the supplied primes are distinct, the Chinese remainder theorem gives a bijection from residue-coordinate tuples to classes modulo P, their product. The compiler computes each cofactor P/p and its inverse modulo p by the extended Euclidean algorithm, retaining the resulting CRT weight. For tuple r, sum(r_p * weight_p) modulo P reconstructs its class.

The canonical positive representative is in [1,P]: class zero is represented by P. A nonnegative cycle q denotes n = representative + qP. In particular, cycle zero does not produce n=0. Every positive integer belongs to exactly one such representative/cycle pair.

Let c_i count palette primes dividing n+i. Then sum_i c_i is exactly the number of palette incidences, with no multiplicity from powers and no duplicate prime at different offsets. The full source sum is at least this value. Therefore sum_i c_i > k is a valid exclusion of the full inequality at that n. Conversely sum_i c_i <= k does not imply the full inequality: additional primes greater than k may divide those integers.

Every excluded residue class recurs, but recurring failures do not decide a liminf assertion that seeks sufficiently small values infinitely often. No infinitude of source witnesses, global lower bound on the liminf, or resolution is claimed.

## Suffix coefficient construction

For coordinates i through m-1 define the multivariate polynomial

    F_i(z_0,...,z_{k-1}) =
        product over j>=i of (p_j-k + z_0 + ... + z_{k-1}).

The coefficient of z_0^c_0 ... z_{k-1}^c_{k-1} counts the suffix residue tuples with exactly that vector of hits. The terminal polynomial is one. The compiler forms each preceding table by adding one coordinate's groups, with the no-hit interval weighted by its size.

Every coefficient is a nonnegative exact BigInt, serialized as a decimal string. Every reachable vector and every suffix position is retained. Vectors are sorted lexicographically for storage; this profile order is separate from the coordinate-tuple rank order. The sum of the root coefficients is checked against P as construction accounting.

| New construction work | Value |
|---|---:|
| Coordinates / offset groups | 12 / 60 |
| Period multiplications / CRT weights | 12 / 12 |
| Euclidean steps | 38 |
| Coefficient updates | 21,840 |
| Complete suffix coefficient cells | 6,188 |
| Root offset profiles | 1,820 |
| Primality tests / old sieve / old factorization | 0 / 0 / 0 |

The represented 2,180,460,221,945,005 residue classes are not individually enumerated. The complete output is 237,588 bytes, blob 6e490c7b6bd6c3e25db693c49336f2fcf4fee675.

## Complete total-incidence distribution

| Palette incidences | Residue classes per period |
|---:|---:|
| 0 | 22,507,852,492,125 |
| 1 | 174,978,838,934,640 |
| 2 | 470,871,167,864,544 |
| 3 | 636,072,168,676,608 |
| 4 | 506,263,720,142,592 |
| 5 | 257,847,066,648,576 |
| 6 | 87,848,147,304,448 |
| 7 | 20,441,795,788,800 |
| 8 | 3,255,767,334,912 |
| 9 | 348,734,357,504 |
| 10 | 23,989,321,728 |
| 11 | 956,301,312 |
| 12 | 16,777,216 |

These count n residue classes, not assignments with multiple labels for the same prime, and not distinct factorization multisets. Counts over a fixed number of complete periods scale by that number. Arbitrary numerical interval counting is not an API operation.

## Saved reader

~~~javascript
const fs = require('fs');
const {openIndex} = require('./consecutive_prime_incidence.cjs');
const data = JSON.parse(fs.readFileSync('four_term_prime_incidence.json', 'utf8'));
const reader = openIndex(data);
const condition = {min_total: 5};
const count = reader.count(condition);
const selected = reader.select('123456789', condition, '100000000000000000000');
const inverse = reader.rank(selected.record.residues, condition);
const witness = reader.window(selected.record.n);
~~~

This is a CommonJS usage example. Actual work loaded the unchanged source in V8; no native executor, Node CLI or filesystem process was used.

| Method | Contract |
|---|---|
| compile(input) | Construct the new CRT weights and complete coefficient tables once. |
| openIndex(saved, caches?) | Open trusted saved constructor output and optional complete mass caches. |
| summary(), coordinates() | Return the complete saved summary and coordinate groups. |
| profiles(condition) | Return every saved root profile satisfying the condition. |
| count(condition) | Count all residue tuples satisfying the condition. |
| select(rank, condition, cycle) | Select a tuple and produce a positive representative, translated n, support and exact divisibility witnesses. |
| rank(residues, condition) | Return the exact rank or null if the tuple is outside the family. |
| page(start, limit, condition, cycle) | Return up to 100 consecutive coordinate-order selections and a next rank. |
| window(n) | Classify the twelve palette incidences of one requested positive n and retain their quotient witnesses. |
| caches(), work() | Return all newly populated mass-cache entries and work counters. |

Conditions have optional inclusive per-offset arrays min and max, each of length four, and inclusive min_total and max_total. Defaults are zero minima and twelve maxima. Incompatible bounds produce an empty family. Integer ranks, cycles and n accept BigInt, exact decimal strings or safe integer Numbers. Coordinates and count bounds use safe nonnegative integer Numbers. Invalid dimensions, negative ranks/cycles, nonpositive n and out-of-family ranks are rejected. The reader trusts saved tables and caches; this is not a hostile-input proof format.

Ordering is **lexicographic on the twelve residue coordinates**, with primes in increasing order and each residue increasing from zero. It is neither increasing positive n, numerical CRT residue order, profile order, nor a quotient by window reversal. Different cycles are specified explicitly; rank does not rank all positive integers across cycles.

For a prefix, the reader scans the retained suffix table and sums exactly those coefficients whose final hit vector meets the condition. It caches this mass. Selection traverses coordinate groups in residue order. Every residue in a no-hit interval has the same suffix mass, so a single quotient/remainder division selects its position inside the interval. Ranking sums earlier group masses and the earlier residues inside the chosen group. No coefficient recurrence, CRT inverse, primality or factorization is reconstructed.

Materialization performs new CRT multiply/add operations and exact quotient arithmetic for requested outputs. The division witnesses certify the displayed palette divisors only. The field full_factor_count is explicitly “not established.”

## Actual first consumer

The separate reader retained **67 complete responses**, **24 inverse rank matches**, every one of the 1,820 root profiles, all coordinate groups and **727 complete mass-cache entries**. No response was lost and no constructor or reader error occurred.

| Condition | Residue classes |
|---|---:|
| No restriction | 2,180,460,221,945,005 |
| At most four total incidences | 1,810,693,748,110,509 |
| At least five total incidences | 369,766,473,834,496 |
| Every offset has at least one | 154,129,047,245,880 |
| Every offset has at least two | 170,927,801,520 |
| Exactly three at each offset | 369,600 |
| No palette hit anywhere | 22,507,852,492,125 |
| Offset zero has no palette hit | 927,040,536,576,000 |
| Every offset has at least four | 0 |

First, middle and last ranks of each nonempty condition were selected and ranked back. The exact-three-at-each-offset family also has a five-record page. A selected excluded-class query used rank 123456789 and cycle 10^80, producing residue 1169950412170540 and hit vector [6,0,0,0]. Its first integer has the six displayed palette divisors 5,7,11,13,17,19. A fresh window query on that large n retained the same support via saved groups and new residue arithmetic. These are actual queries, not asserted consequences of unexecuted examples.

The endpoint queries n=1 and n=P preserve positivity and the class-zero convention. Another separately supplied large n is classified only against the palette.

| Fresh reader work | Actual value |
|---|---:|
| Condition normalization calls | 66 |
| Saved profile scans / coefficient additions | 254,876 / 92,151 |
| Mass-cache hits / misses | 1,140 / 727 |
| Coordinate-group reads | 1,093 |
| Rank blocks / selection blocks | 816 / 1,011 |
| CRT multiply/adds / reductions | 408 / 34 |
| Input residue reductions | 48 |
| Quotient witnesses / selected records | 261 / 34 |
| New coefficients / inverses / primality tests | 0 / 0 / 0 |

These counters describe the named operations, not a benchmark or complete machine-instruction count. Query scans and arithmetic are new work and are reported separately from construction.

## Complete retained files

No snapshot or coefficient data is sampled. The core files have these byte identities:

- consecutive_prime_incidence.cjs: 9700 bytes, blob 99242939ec606e224d40efddbfe15e614fb70931.
- input4.json: 1178 bytes, blob e00a3c161c7dd808d86de01aebe29d36e1e7bc9d.
- four_term_prime_incidence.json: 237588 bytes, blob 6e490c7b6bd6c3e25db693c49336f2fcf4fee675.
- saved_reader_queries.json: 560547 bytes, blob 1b0015fe8d49183b845c3a42e369efa0cabc72a3.
- saved_condition_caches.json: 91370 bytes, blob 4ffd18931d7ae19f7565d447df8c030c0ea3128f.

The guide and README identify the finite scope, source-access gap, accepted input premises, ordering, and actual work. This reusable finite screen does not settle either part of Erdős 890, certify survivor factorizations, verify a linked formal proof, or assert mathematical priority, an extremal record or prize progress.
