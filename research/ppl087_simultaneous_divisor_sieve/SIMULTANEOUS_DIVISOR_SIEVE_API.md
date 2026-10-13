# Simultaneous small-divisor index

This package navigates the integers k in the finite interval 0 <= k < n for which neither n+k nor n+k² is divisible by any supplied modulus. It records every local residue test and every retained CRT row, then answers counts, ranks, pages, saved CRT-path queries and exact exclusion witnesses. A surviving k has passed only the declared divisibility tests. It is never labeled a simultaneous-prime witness.

## Source and mathematical scope

Zhi-Wei Sun’s author-written [OEIS A185636](https://oeis.org/A185636), dated December 18, 2012, defines the number of integers 0 <= k < n for which n+k and n+k² are both prime, and conjectures positivity for every n > 1. This is the exact strict-k convention used here. The two primes need not be distinct: k=0 or k=1 makes the expressions equal. The entry’s later inclusive-k formulation agrees for n>1 because k=n makes n+k=2n composite.

The catalogue [PPL087](https://prizeproblems.org/problems/087/) identifies this question. Its linked arXiv abstract, 1211.1588, returned a ServerError in the bounded lookup and remains held; the paper itself was not read through another route. The source entry’s dated conjectural wording is not an independently verified current-status or prize assertion. No listed OEIS example, sequence term or reported computational bound was recomputed.

This index concerns a necessary finite small-divisor condition. If both polynomial values are prime, then they survive these tests under the input contract below. The converse is not claimed. A nonempty survivor family proves neither simultaneous primality nor the general conjecture.

## Accepted input

The CommonJS module exports buildIndex(input), openIndex(snapshot), SCHEMA and LIMITS. An input has:

- n: a canonical unsigned decimal string of at most 2,048 digits.
- moduli: a nonempty array of safe integers, each between 2 and 257.
- Every pair of moduli must be coprime.
- Their sum must be at most 2,000 and their product at most 1,000,000.
- n must be strictly larger than every supplied modulus.
- The total number of generated CRT rows, across all stages, must not exceed 200,000.

Additional input provenance fields are not mathematical parameters. The certificate envelope retains the complete actual input; the snapshot retains n and the moduli. Moduli are not required to be prime, and the API performs no primality test. Input order defines local-choice order and the first reported divisor. It need not be increasing, so that first divisor is not generally the smallest divisor of a polynomial value.

The inequality n>m is essential to the simple exclusion contract. For k>=0, both values are at least n. Therefore a modulus m>=2 dividing either value satisfies 1<m<value and is a proper divisor. No equality-to-modulus exception is silently removed. An input outside a bound is refused; the constructor does not return a truncated family.

An empty survivor family is valid. Counts and pages are empty, select has no valid rank, and saved CRT paths are absent. No division by the number of phases is attempted by a successful selection in that case.

## Local tables and exact CRT construction

For each modulus m and every r in {0,...,m-1}, the constructor records a two-bit flag:

| Flag | Meaning |
| --- | --- |
| 0 | Neither polynomial is divisible by m |
| 1 | m divides n+r only |
| 2 | m divides n+r² only |
| 3 | m divides both |

The coefficients are reduced modulo m. If k is congruent to r modulo m, the flags apply to the actual k because both expressions are integer polynomials. Allowed local residues are precisely the zero-flag positions.

Suppose the previous product is M and a saved residue is b modulo M. For an allowed new residue a modulo m, coprimality supplies v=M^(-1) modulo m. Let

    t = ((a-b) v) mod m, in {0,...,m-1},
    c = b + M t.

Then 0<=c<Mm, c=b modulo M and c=a modulo m. The CRT gives exactly one such c. Conversely, any residue surviving all stages has a unique previous residue and new allowed residue, so these rows are complete and without duplication. Induction proves the final rows are exactly all survivor phases modulo the full product P.

A stage stores its modulus, previous product, product, inverse and rows [c,t]. Rows are in mixed local-choice rank order: if the previous row rank is u and the new local allowed index is j, the new rank is u*A+j, where A is the number of local allowed residues. The final order_by_residue permutation sorts these rows numerically by c. The two rank systems are deliberately distinct.

A saved CRT-path query follows mixed-rank prefixes backward and reads the corresponding saved stage rows. It reports parent rank, local index, allowed residue, inverse, step and resulting residue at each stage. It does not recompute modular inverses or the CRT recurrence.

## Counts and navigation

Let sorted survivor residues be R=(r_0,...,r_(S-1)), with period P. Every survivor in the nonnegative integers has a unique representation qP+r_i. In the requested finite interval, retain precisely those with qP+r_i<n.

For 0<=B<=n, write B=qP+r with 0<=r<P. The exact count in [0,B) is

    C(B) = q*S + number of saved residues strictly less than r.

The strict comparison matches the half-open endpoint. Interval counts are C(hi)-C(lo) for [lo,hi). Candidate ranks are zero-based in increasing k order. For j<C(n),

    select(j) = floor(j/S)*P + R[j mod S].

If k survives and r=k mod P has index i in R, its rank is floor(k/P)*S+i. A rejected k has rank null. These formulas count residue classes without enumerating the potentially enormous k interval.

## Public reader methods

Load a certificate and pass its snapshot to openIndex. The reader copies the supplied JSON before indexing it; returned tables and work counters do not expose internal mutation.

| Method | Result |
| --- | --- |
| summary() | Input, period, phase count, complete decimal total, local and stage counts |
| local() | Complete local flags and allowed residues |
| stagePage(stage,start=0,limit=16) | Saved mixed-choice rows, with row ranks |
| phasePage(start=0,limit=16) | Numerically ordered final residues and choice ranks |
| count(end) | Decimal count for [0,end) |
| interval(lo,hi) | Exact half-open interval count |
| select(rank) | The selected k and its zero-based decimal rank |
| rank(k) | Decimal rank, or null for a rejected k |
| page(start,limit=16) | At most limit successive candidate records |
| crtPath(residue) | Saved stage path, or null if the phase is rejected |
| inspect(k) | All supplied-modulus hits, both exact polynomial values, first-hit quotient witnesses |
| work() | Explicit indexing and query work counters |

Bounds, k values and candidate ranks are canonical decimal strings under the digit cap. Stage, phase, residue and page indices are safe integers. Page limits range from 0 to 128. k must satisfy 0<=k<n; count and interval endpoints may equal n. An empty endpoint page at the total is allowed. Negative, noncanonical or out-of-range arguments are refused.

inspect evaluates the two polynomials once each for its query. For each polynomial with a supplied hit, it returns divisor, full decimal quotient, remainder and proper-divisor flag. All hits remain listed, even if only one quotient witness per polynomial is materialized. It reports prime_status="not tested" in every case, including survivors.

The loader checks schema, input bounds, stage products, row shapes and cardinalities, flags versus allowed lists, and the final permutation and strict residue order. It does not rerun local polynomial tests, inverses, CRT construction or independently prove the mathematical provenance of a supplied snapshot. Its mathematical answers are conditional on that snapshot’s identified construction. The actual snapshot below is bound to its source and input blobs.

## One actual input and complete retained result

The sole production input is

    n = 10^1000 + 477965
    moduli = [2,3,5,7,11,13].

The scalar 477965 was taken from the released [#31607](https://github.com/woahwhattheheck/commons/pull/31607) finite hypergraph count solely to choose a fresh integer input. No property, graph, coefficient, constraint, proof or computation of that earlier index is used. This package does not import or replay an earlier prime basis, sieve or CRT family.

| Modulus | n modulo modulus | Allowed k residues | Stage rows |
| --- | --- | --- | ---: |
| 2 | 1 | 0 | 1 |
| 3 | 0 | 1,2 | 2 |
| 5 | 0 | 1,2,3,4 | 8 |
| 7 | 2 | 0,1,2,3,4,6 | 48 |
| 11 | 5 | 0,1,2,3,4,5,7,8,9,10 | 480 |
| 13 | 10 | 0,1,2,5,6,7,8,10,11,12 | 4,800 |

One construction performed 41 local residue tests, six inverses and created 5,339 CRT rows in total. There are exactly 4,800 final survivor phases modulo 30,030. Its phase proportion is 4,800/30,030; this is a periodic small-divisor proportion, not a prime density. The complete count C(n) is a 1,000-digit integer, stored without truncation in reader output 0 and output 8.

The first surviving k is 2; the last is n-13. Neither is asserted to make both values prime. Saved reader outputs give:

| Interval or query | Exact result |
| --- | ---: |
| [0,1000) | 161 survivors |
| [0,30030) | 4,800 survivors |
| [10^500,10^500+123456) | 19,735 survivors |
| [n-1000000,n) | 159,840 survivors |
| [n,n) | 0 survivors |
| k=0 | Both polynomial values have supplied proper divisor 3 |
| k=1 | Both polynomial values have supplied proper divisor 2 |
| k=n-1 | Quadratic value has supplied proper divisor 13; linear value has no supplied hit |

All 30 reader outputs are retained, including complete local tables, saved paths, first/last/median candidates and inverse ranks, two pages, full large counts and exact quotient witnesses. Outputs 25 and 27 deliberately inspect the same value 2 through explicit and selected inputs; both are preserved and included in the work counters. They do not constitute a second compilation.

The fresh reader indexed 5,339 saved rows and 4,800 final phases. Its work was 224 binary-search steps, 96 saved-row lookups, 39 BigInt divisions, 75 BigInt remainders, 12 polynomial evaluations and five quotient witnesses. CRT rows created, local residue tests and primality tests were all zero. Reading and checking structural table relationships is distinct from reconstructing their mathematical contents.

## Files, immutable provenance and validation

- simultaneous_divisor_sieve.cjs: source blob 483bb14c1cc9c10d9f7826f1c7310ba1b8cc5366; 11,233 UTF-8 bytes.
- Original complete input: blob 60ce4a4f8ee6a4c2d4471449a66f3f9fbf4d5bf0; 1,295 bytes. Its full body is embedded in the certificate.
- huge_integer_crt_certificate.json: blob 55964c45530dbcf06855c08fc6f0c4f2fad369e1; 78,666 bytes.
- saved_reader_queries.json: blob 14dd3477e9ea2ae559e2a3923a730b1c5c6da0d3; 80,469 bytes.
- This guide and README provide the API contract, derivation, source boundaries and artifact entry points.

The source was syntax-parsed, and source and input were durably banked before the single production construction. The complete construction and the 30 fresh reader outputs were each saved before publication. No acceptance calculation or published example was rerun, and no separate verification-only artifact was manufactured. Publication uses serial guarded Contents writes and complete immutable/main text and blob readbacks. It makes no file-mode or whole-tree assertion.

The exact finite scope is all k in this one huge interval passing these six declared divisibility filters. It provides useful necessary-condition navigation and proper-factor exclusions; it supplies no new prime, simultaneous-prime witness, record, asymptotic theorem or resolution of Sun’s conjecture.
