# Selected-prime sums with two powers of two

This package counts odd integers represented by `n = p + 2^k + 2^l` within a declared finite interval, using an explicitly supplied finite set of identified primes. Both exponents are nonnegative, and equal exponents are allowed. The saved family counts an integer once even when several selected primes represent it. Its representation fibers retain the prime and an unordered exponent pair `k <= l`; ordered exponent pairs have multiplicity one on the diagonal and two otherwise.

## Mathematical scope and input lineage

The complete read of `FormalConjectures/ErdosProblems/9.lean` has content blob `5d86baf5c54f7cb54a45f93a315d0633927322d7`. It defines the unrestricted set using every prime, including 2, and natural-number exponents. It records infinitude as research solved, crediting Schinzel through Erdős's 1977 account, while the positive-upper-density assertion remains research open in that source. Both research theorems retain local placeholders; no proof was reviewed. The finite index below addresses neither assertion.

The actual primes are `[2,3,5,7,11,13,17]`, copied from `input.primes` in Commons #31649, merge `0e4428eaef33d6c06bace7c5b1dc0d96f15f6496`, file `research/erdos828_totient_shifts/primes17_cap3_index.json`, blob `06d71f61df8e7913a2131bcad12a9b229c452a35`. That source identifies them from #31519 `input.moduli`. The new operation consumes only those seven values; no earlier prime, sieve, CRT, product, totient, recurrence, or classification computation is repeated.

The actual domain is every odd positive integer below `2^70`. Absence from this family means only absence over these seven primes. A missing representation may use a larger prime. The source conventions and the elementary finite decomposition are not claims of mathematical novelty or prize progress.

The independently read author-primary source is Paul Erdős, “Problems and results on combinatorial number theory III,” in *Number Theory Day*, Lecture Notes in Mathematics 626, Springer (1977), pp. 43–72, [author archive PDF](https://www.renyi.hu/~p_erdos/1977-27.pdf). Printed page 50, section 3, discusses odd integers failing to be a prime plus a prescribed number or fewer powers of two, and explicitly attributes infinitude for the two-power form to Schinzel. The paragraph separately raises density and arithmetic-progression questions. It does not explicitly fix the exponents' lower bounds or distinctness; the explicit zero/equality conventions here come from the fully read Formal9. No visual-inspection claim, original proof audit, or current literature-frontier claim is made.

## Complete finite decomposition

For a positive integer `d`, a representation `d = 2^k + 2^l` exists precisely when either:

- `d` has two set binary bits, which give the two distinct exponents; or
- `d >= 2` has one set bit in position `j`, which gives the equal pair `(j-1,j-1)`.

These two cases give a unique unordered exponent pair. The value 1 fails, and a nonpositive difference fails. Hence the small odd values `n < B` can be retained directly with all selected-prime fibers.

Choose `B=2^b` strictly larger than every supplied prime. For `n >= B`, write uniquely `n=B h+r`, with odd `1 <= r < B` and `h>=1`. Write the positive high part uniquely as

```text
h = u * 2^(z+1) + 2^z,
```

where `z` is its number of trailing zero bits. If the domain has `L` bits, put `H=L-b` and `m=H-z-1`; then `u` is an arbitrary `m`-bit integer.

For one selected prime `p<B`, set `borrow=1` if `p>r`, and zero otherwise, and set `low=r-p+borrow*B`. Binary subtraction gives

```text
popcount(n-p) = popcount(low) + popcount(u) + (borrow ? z : 1).
```

The formula includes the case `h=1`: then `h-1=0`. Because `n>=B>p` and `n` is odd, the relevant positive difference is at least two whenever it has one bit. Thus total popcount one or two is exactly the representation predicate here.

For fixed `(r,z,w)`, where `w=popcount(u)`, every integer in the stratum has the same selected-prime support mask and the same diagonal mask. Its size is the binomial coefficient `C(m,w)`. When `w>=3`, no prime can represent the integer: without borrowing there is the additional high one bit, and with borrowing the nonzero low part contributes at least one bit. The index retains weights 0, 1, and 2 separately, and groups the remaining weights into an exact zero-support stratum of size `2^m - 1 - m - C(m,2)`. These rows, together with the small values, partition the entire odd domain. They do not enumerate its integers.

## Numerical queries

A bound `x` gives, for each retained row, a bound on its upper part:

```text
h_max = floor((x-r)/B)
u_max = floor((h_max - 2^z)/2^(z+1)).
```

Negative upper bounds contribute zero, and the remaining bounds are clipped to `[0,2^m-1]`. Standard binary prefix counting uses the saved binomial coefficients to count upper parts of weight 0, 1, or 2. The grouped tail is its full prefix length minus those three counts. Summing matching rows yields an exact numerical count. Rank counts integers below the queried value; select uses monotone binary search over the saved finite interval. This is increasing numerical order, with support overlaps counted once.

These query operations perform new comparisons, prefix arithmetic, and point-fiber subtraction. Their counters are retained explicitly. Opening the saved index checks shapes and domains only; it does not rebuild strata or binomial coefficients, rerun primality, or re-prove the source premise.

## API and bounds

`buildIndex(input)` accepts `{bits, primes, ...provenance}`. The identified prime list must be strictly increasing, contain 1–16 entries from 2 through 127, and is a mathematical premise rather than primality-checked input. The module chooses the least power of two `B` strictly greater than the largest entry. Bits must be an integer from `log2(B)+1` through 256; the conservative stratum allocation bound `(B/2)*(bits-log2(B))*4 <= 65536` must hold. Provenance is copied into the saved result. Larger unexercised parameter branches were inspected in source only.

`openIndex(saved)` accepts either the complete parsed object or its JSON string, and returns:

| Method | Meaning |
| --- | --- |
| `summary()` | Domain size, represented and absent counts, ordered/unordered representation counts, prime marginals, full support/diagonal spectrum, construction work |
| `point(n)` | Exact selected-prime fiber of one odd positive integer in the saved domain |
| `count(bound, filter?)` | Number of matching odd integers at most the bound; clips above the saved maximum |
| `interval(lo, hi, filter?)` | Inclusive numerical interval count; reversed bounds fail |
| `select(rank, filter?)` | Zero-based increasing numerical selection |
| `rank(n, filter?)` | Numerical inverse, or a null rank when that odd value does not meet the filter |
| `page(start, limit, filter?)` | Up to 32 consecutive selected values; start may equal the family size |
| `stratum(i)` | One complete saved stratum row by its zero-based index |
| `work()` | Cumulative reader arithmetic/caching counters; does not increment the query count |

An omitted filter selects nonempty support. `{exact: mask}` selects that exact support, including `{exact:0}` for absence over the selected primes. Optional `required` and `forbidden` bit masks further require or exclude prime supports. Bits follow the saved prime-list order, least significant first. With `exact` omitted, an otherwise empty filter still selects represented values. Contradictory masks produce an empty family; selecting from it fails by rank range. The diagonal mask is descriptive, not a separate filter input.

Integer arguments accept nonnegative safe integer numbers, BigInts, or canonical decimal strings of at most 2,000 digits. Point/rank require an odd positive integer inside the saved domain. Count and interval allow even endpoints; values beyond the saved maximum do not expand it. Selection is zero-based and throws on an out-of-range rank. Returned large integers and counts are decimal strings. Prefix-count memoization stores at most 4,096 entries; overflow only forgoes further caching, without changing counts.

A typical saved-data consumer is:

```javascript
const fs = require('node:fs');
const {openIndex} = require('./selected_prime_powers.cjs');
const saved = fs.readFileSync('./primes17_bits70_index.json', 'utf8');
const api = openIndex(saved);
const one = api.point('5');
const total = api.count('1180591620717411303423');
const selected = api.select('6735');
const inverse = api.rank(selected.n);
const selectedPrimeAbsences = api.count('1000', {exact: 0});
```

There is no call to `buildIndex` in this consumer. The example API names and saved-file contract are the implemented interface; the actual retained execution is the separate reader below.

## Actual once-only construction

The source was frozen and banked at `7377c5a69eddf203af6a834e8014c766ea234619` before its only production run. Input blob `c9602c8cc720ab2c1401ad64efa4fcc4c1f73370` contains the complete prime lineage and bound. The resulting complete index is blob `70761d12b44a2590fab8ca47cb2aef021666ed9f` (348,653 UTF-8 bytes).

| Quantity | Exact result |
| --- | ---: |
| Bit bound | 70 |
| Maximum integer | 1,180,591,620,717,411,303,423 |
| Odd integers in the declared domain | 590,295,810,358,705,651,712 |
| Represented by the selected primes | 13,470 |
| Absent over the selected primes | 590,295,810,358,705,638,242 |
| Unordered representations, retaining prime roles | 14,559 |
| Ordered representations, retaining prime roles | 28,704 |
| Small odd values retained individually | 16 |
| Complete strata | 4,064 |
| Support/diagonal buckets | 32 |
| Binomial cells | 198 |

The prime marginals are 69 for prime 2 and 2,415 for each of 3, 5, 7, 11, 13 and 17. They count support incidences and therefore must not be summed as a distinct-integer count. The complete spectrum retains those overlaps. Integer 23, for example, has a representation with each of the six selected odd primes but none with 2. No integer in this finite domain has all seven support bits.

Production work contains 112 small-value differences and 21,504 local residual calculations. It enumerates neither the large integers in the domain nor power-pair families, and performs no primality tests. The 16 small values are explicitly enumerated and classified; “no enumeration” does not erase that boundary.

## Fresh saved-reader execution

The frozen module was loaded separately, and `openIndex` consumed the complete saved JSON. All 42 responses were retained individually before continuing, then collected in `saved_reader_queries.json`, blob `3c1040bf38bed6d3854af2604c87831367faedc7` (37,834 bytes). No construction was repeated.

Eight adjacent select/rank pairs match in the already-retained response records. Representative results are:

| Query | Exact saved result |
| --- | --- |
| Represented values at most 31 | 14 |
| Represented values below 2^35 | 3,075 |
| Represented values from 2^69 through the maximum | 399 |
| First represented integer, rank 0 | 5 |
| Represented integer at rank 6,735 | 1,125,899,907,891,203 = 3 + 2^20 + 2^50 |
| Last represented integer, rank 13,469 | 885,443,715,538,058,477,585 = 17 + 2^68 + 2^69 |
| Absent-over-selected-primes rank 10^20 | 200,000,000,000,000,025,345 |
| Values supported by both 2 and 3 | 69 |
| Exact support mask 126 | One value, 23 |
| Exact support mask 127 | Zero values |
| Absent-over-selected-primes values from 1 through 1,000 | 350 |

The first integer, 5, has `(p,k,l)=(2,0,1)` and `(3,0,0)`. Their ordered multiplicities are two and one. The final three-value page and a five-value page requiring both 2 and 3 are retained completely; they are requested pages, not new enumerations of the complete family.

Reader work is explicitly new arithmetic: 2,353,056 saved-row scans, 9,264 small-row scans, 1,230,016 saved-binomial lookups, 7,831,221 prefix-bit steps, 1,120 binary selection steps and 217 point-fiber subtractions. There are 579 retained count-cache entries and 581 cache hits. The reader creates zero new strata, binomial cells or primality results. Structural reopening and inverse comparisons do not constitute an independent revalidation of the construction mathematics.

## File contract and limits

The five files are the reusable source, this guide, the complete index, all saved reader responses, and a short README. The index declares the row schemas, includes every row and coefficient, and carries its original input. It has no truncated shard or missing response. The reader's request/response records include the individual banked blob identities.

This finite chosen-prime language is useful for exact support and order-statistic queries. It does not determine the unrestricted Erdős set, its density or infinitude, or primality outside the inherited premise. No sponsor contact, proof submission, award eligibility or payment is asserted.
