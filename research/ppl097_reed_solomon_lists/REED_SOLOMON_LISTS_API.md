# Exact finite Reed–Solomon lists

This package indexes every codeword of one bounded Reed–Solomon code against one fixed received word. It retains complete agreement fibers and every codeword in an exact packed representation. Saved readers provide Hamming-radius lists, punctured-coordinate and prescribed-agreement filters, count/rank/select, and selected codeword decoding without repeating polynomial evaluation.

The actual center has seven nearest codewords at distance seven. This is a fixed-center finite result. It is not a worst-case list-size bound, a new decoding threshold, or progress on an unread prize parameter.

## Primary sources and boundaries

Robert J. McEliece, [The Guruswami–Sudan Decoding Algorithm for Reed–Solomon Codes](https://tmo.jpl.nasa.gov/progress_report/42-153/153F.pdf), IPN Progress Report 42-153, May 15, 2003, Section II, defines an evaluation code over GF(q) at a fixed list of distinct points, using polynomials of degree less than k. Its fixed-received-word distance inequality counts coordinates where polynomial values differ from the received symbols. We use that ordinary Hamming-ball convention. The tutorial also distinguishes its algorithm’s unfiltered candidate output from the exact in-radius list; this index retains the exact radius-filtered family.

The [PPL097 catalogue](https://prizeproblems.org/problems/097/) links Arnon, Boneh and Fenzi’s [Open Problems in List Decoding and Correlated Agreement](https://eprint.iacr.org/2026/680). The directly read abstract and metadata identify it as a July 2026 revised preprint concerning the Proximity Prize. Its linked PDF returned 403 and remains held; no alternate copy was fetched. The formal grand-challenge parameters, bounds, proofs and award rules were not read from that PDF. They are not inferred from this small-field consumer.

The present work neither implements nor claims an improvement to the Guruswami–Sudan algorithm. It performs a deliberately bounded complete enumeration once, then navigates its saved records. No current literature frontier, prize eligibility, sponsor contact or submission is asserted.

## Exact code and input contract

For a supported prime q, distinct points alpha_0,...,alpha_(n-1), and 1<=k<=n, the code is

    C = { (f(alpha_0),...,f(alpha_(n-1))) : f in F_q[x], degree(f)<k }.

The zero polynomial and polynomials of lower degree are included. There are exactly q^k coefficient vectors. Distinct vectors give distinct full codewords: their difference is a nonzero polynomial of degree below k and has at most k−1 roots, whereas n>=k distinct evaluation points are available.

Input fields are:

- prime: one of the fixed supported primes 2,3,5,7,11,13,17,19,23,29,31.
- dimension: the integer k, with 1<=k<=n.
- points: a nonempty array of distinct residues from 0 through q−1, in evaluation order.
- received: exactly n residues from 0 through q−1.

The API uses prime fields with ordinary integer arithmetic modulo q. It does not support arbitrary extension-field encodings or infer primality for user-supplied integers. Membership in the displayed finite prime list is checked; no primality algorithm or earlier field cycle is run.

A construction is refused if q^k exceeds 100,000 or n*q^k exceeds 1,000,000. These are finite resource limits. All coefficient ranks and family counts fit safe integers. Arithmetic inside Horner evaluation is small; packed words use BigInt. Length n is at most 31, so coordinate masks use bits 0 through n−1 within the nonnegative signed 32-bit range.

The module exports buildIndex, openIndex, SCHEMA, PRIMES and LIMITS. Provenance fields in the actual input envelope are not code parameters.

## Coefficient and codeword order

Write f(x)=a_0+a_1*x+...+a_(k-1)*x^(k-1), with each a_i in {0,...,q−1}. Its coefficient rank is

    rank(f) = sum_i a_i*q^i.

This rank orders all candidate identities. Coefficients are displayed in increasing degree order. The ordering is numerical coefficient rank, not lexicographic comparison of the displayed coefficient array.

For a codeword (w_0,...,w_(n-1)), the exact packed representation is

    packed = sum_j w_j*q^j.

Every digit lies between zero and q−1, so base-q expansion uniquely recovers the complete word. It is serialized as a canonical decimal string. The reader decodes this stored value by division and remainder; it does not substitute the coefficient vector into the evaluation points again.

## Complete agreement fibers

For each coefficient vector, the one construction evaluates all n coordinates using Horner’s rule and stores the agreement mask A, where bit j is one exactly when f(alpha_j)=received_j. Its full Hamming distance is n−popcount(A).

All coefficient ranks having the same agreement mask form one fiber. Fibers are sorted by mask, and each fiber’s ranks are increasing. They partition every integer rank from zero through q^k−1 exactly once. The full distance histogram is obtained by adding the size of each agreement class at its distance. The snapshot also keeps every packed codeword, indexed directly by coefficient rank.

This constructor really enumerates all q^k polynomials. Its finite exhaustive work is disclosed rather than described as an asymptotically efficient list decoder. The saved reader never repeats that enumeration or any construction Horner step.

## Conditions, puncturing and prescribed matches

A query object accepts only:

- keep_mask: coordinates used for distance, defaulting to all n coordinates.
- require_mask: coordinates required to agree exactly, defaulting to zero.
- radius: a nonnegative integer no larger than popcount(keep_mask), defaulting to that length.

A saved fiber with agreement mask A is accepted precisely when

    (A AND require_mask) = require_mask
    and popcount(keep_mask AND NOT A) <= radius.

The radius is closed and integer-valued. For retained length m>0, it corresponds to normalized radius radius/m. No floating threshold rounding is performed. Required matches may also include coordinates outside keep_mask; they remain additional exact constraints on the full word.

Candidate identities remain distinct full codewords. Puncturing can make two full codewords have the same shortened evaluation vector, but this API does not identify those candidates. In particular, with no coordinates retained and no required matches, all q^k full codewords remain candidates at radius zero. This is not a count of distinct empty shortened words.

Each new condition scans the saved agreement fibers once and retains its complete accepted fiber-ID list, candidate count and filtered distance histogram. Repeated conditions reuse that record. The reader allows at most 128 distinct conditions; additional requests are refused. Condition creation uses the saved masks, not polynomial evaluation.

## Count, rank and select

For a fixed condition, let its accepted fibers be F. The number of candidate coefficient ranks below B is

    sum_(f in F) lower_bound(f.coefficient_ranks, B).

Each rank occurs in exactly one fiber, so this sum is exact without deduplication or codeword reconstruction. It is monotone in B. Binary search over the coefficient-rank interval finds the candidate with any requested list rank. A direct rank query first checks the saved fiber identity, then sums the counts below its coefficient rank. Rejected coefficient ranks receive null.

The method enumerates neither all candidates nor all coefficient vectors during count/rank/select. It does scan accepted fibers and binary-search their saved rank arrays; those operations are counted. Requested pages explicitly materialize only their selected records.

## Public reader interface

Open a certificate by passing its snapshot to openIndex.

| Method | Meaning |
| --- | --- |
| summary() | Code dimensions, histogram, nearest distance and construction work |
| input() | Complete code parameters and received word |
| fiberPage(start=0,limit=16) | Complete saved fiber records, including their coefficient-rank lists |
| count(query={}) | Complete condition record and candidate count |
| prefix(query,bound) | Candidate count below a coefficient-rank bound |
| select(query,rank) | Selected coefficient vector and its saved agreement/distance record |
| rank(query,coefficientRank) | Candidate list rank or null |
| page(query,start="0",limit=16) | Up to limit selected records |
| inspect(coefficientRank) | Saved agreement mask, full distance and decoded coefficients |
| word(coefficientRank) | Complete codeword decoded from its saved packed value |
| conditions() | Every created condition record |
| work() | Indexing and query work counters |

Candidate ranks, page starts and prefix bounds are canonical nonnegative decimal strings of at most six digits. Values cannot exceed q^k; selection additionally requires a rank below its candidate count. Coefficient ranks, coordinate masks, radii and page indices are safe integers in their respective ranges. Pages contain at most 128 records. An endpoint page at the candidate count is allowed and empty.

A fiberPage row may contain a large rank list; the page bound limits the number of fibers, not the length of each complete fiber. Returned full_distance always refers to all n original coordinates, including when the selection condition measures distance on a smaller keep_mask.

The loader checks schema, input bounds, sorted fibers, the complete disjoint partition of coefficient ranks, packed-word ranges and histogram shape/total. It copies the supplied JSON, builds rank-to-fiber lookup data and does not recompute agreements, codewords or the histogram from polynomial evaluations. Consequently structural loading alone does not certify the mathematical provenance of arbitrary data. The actual snapshot below is bound to its source and input.

## One actual received word

The actual field is F_13, dimension k=4 and evaluation points 0 through 12. The received word is

    [5,8,8,12,7,4,12,9,2,1,6,1,7].

Its symbols were selected by reducing the thirteen saved sequential input masks from [#31617](https://github.com/woahwhattheheck/commons/pull/31617) modulo 13, in chronological order. Those source masks and the exact source reader blob are retained in the input envelope. This is an input-selection convention only; no Boolean product, matrix layer, conditional coefficient or old field computation was repeated.

The sole construction enumerated 28,561 polynomials and produced 791 agreement fibers. It performed 371,293 coordinate evaluations, 1,485,172 Horner steps, packed 371,293 digits and decoded 114,244 coefficient digits. All 28,561 packed codewords are saved.

The complete full-distance histogram is:

| Distance | Number of codewords |
| ---: | ---: |
| 0 through 6 | 0 |
| 7 | 7 |
| 8 | 51 |
| 9 | 355 |
| 10 | 1,648 |
| 11 | 5,493 |
| 12 | 10,914 |
| 13 | 10,093 |

Thus the closed radius-seven list has seven codewords, radius eight has 58 and radius nine has 413. The seven nearest coefficient vectors, all decoded as full codewords by the saved reader, are:

| Coefficient rank | [a_0,a_1,a_2,a_3] | Agreement mask |
| ---: | --- | ---: |
| 512 | [5,0,3,0] | 1923 |
| 3789 | [6,5,9,1] | 1582 |
| 10171 | [5,2,8,4] | 6229 |
| 10377 | [3,5,9,4] | 858 |
| 13434 | [5,6,1,6] | 6313 |
| 20085 | [0,11,1,9] | 7434 |
| 27478 | [9,7,6,12] | 2530 |

List rank 29 at radius eight selects coefficient rank 15225, vector [2,1,12,6]. The last radius-eight list rank, 57, selects coefficient rank 28511, vector [2,9,12,12]. Their full distances are eight.

Two additional finite conditions illustrate puncturing and prescribed matches:

- keep_mask=3822 drops coordinates 0,4,8,12 and retains nine positions. Requiring agreement at positions 1 and 2 (require_mask=6) and permitting at most five retained-coordinate errors gives 14 full-codeword candidates.
- keep_mask=127 retains the first seven positions. Radius three, with no additional required matches, gives 35 full-codeword candidates.

Retaining no coordinates with radius zero gives all 28,561 full candidates. Requiring agreement at every coordinate gives none, even if the distance radius is thirteen.

## Saved reader work and delivery evidence

All 38 reader-query responses are retained, together with all nine complete condition records. They include the complete seven-word nearest list and its full decoded codewords, larger-radius selections and inverse ranks, exact prefix counts, the two punctured cases and empty-list cases.

The fresh reader indexed 791 saved fibers, 28,561 coefficient ranks and 28,561 packed words. It scanned 7,119 fibers to create nine conditions, with 14 condition-cache hits. Rank and select used 9,278 prefix-fiber scans and 9,278 binary-search steps. Selected records decoded 152 coefficient digits; eleven selected complete codewords decoded 143 packed digits. Polynomials enumerated, coordinate evaluations and Horner steps were all zero in the reader.

Retaining every packed codeword uses storage to avoid repeating polynomial evaluation during selected-word queries. All reported query responses are complete saved records.

## Files and immutable provenance

- reed_solomon_lists.cjs: source blob 320cd97dc350ec26e48438dfa3c739c144cf36ab, 9,420 UTF-8 bytes.
- Complete original input: blob dd620475b1fe4faeae4fba344b79097695aec128, 741 bytes; embedded in the certificate.
- prime13_received_word_certificate.json: blob ba2432a78228e84f31e72fe9e0a9248844ff78cd, 701,248 bytes.
- saved_reader_queries.json: blob a02f4413b414c6248231fd8cdca28e59e52c23f3, 100,946 bytes.
- This guide and README provide the contract and source qualifications.

The source was syntax-parsed and banked with the input before the one production construction. Complete construction and saved-reader outputs were banked before guarded publication. No accepted calculation, known source example or earlier proof was replayed. Publication uses serial Contents operations and full immutable/main text and blob readbacks without a file-mode or whole-tree assertion.

The delivered result is exact navigation around this one received word and its declared finite coordinate restrictions. It does not maximize over received words, determine a universal list size or normalized threshold, implement the unread grand-challenge parameters, or establish a new decoding theorem.
