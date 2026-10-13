# Selected-prime binary-summand minimum index

This API gives the exact minimum number of powers of two needed after choosing a prime from one supplied finite palette. Its first consumer covers **every 70-bit integer**, from 590295810358705651712 through 1180591620717411303423, using the palette **2, 3, 5, 7, 11, 13, 17**. It stores 2,080 bit-template blocks and shared binomial tables rather than enumerating the 590295810358705651712 integers.

The selected-prime minimum ranges from **1 to 67**. Exactly seven integers attain 1, and exactly 73 attain 67. The saved reader exports both families completely and retains 47 query responses, including 16 matching rank/select inverses. A representation found with a selected prime is valid for the unrestricted problem. A large selected-prime minimum is **not** a lower bound for the unrestricted minimum: an omitted prime may give fewer powers.

## Source, conventions and exact input lineage

The actually read FormalConjectures source was requested at
[FormalConjectures/ErdosProblems/10.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/10.lean)
without an explicit commit ref. Its complete returned UTF-8 text has Git blob identity
`958f3b843469d868f4be2e702285abfac440e4d5` (4,565 bytes). This is a content identity, not a claimed repository commit pin.

Its `sumPrimeAndTwoPows(k)` uses a prime and a multiset of natural-number exponents with cardinality at most k. Consequently exponent zero, repeated exponents and the empty sum are allowed. The main eventual-coverage question is annotated research open with a local placeholder. The separate density variant and other variants have their own annotations; this package does not execute local examples or inspect linked proofs. In particular, it does not evaluate the supplied published numerical example.

Paul Erdős, [“Problems and results on combinatorial number theory. III”](https://www.renyi.hu/~p_erdos/1977-27.pdf), in *Number Theory Day*, Lecture Notes in Mathematics 626 (1977), pp. 43–72, asks on printed p. 50, §3, about odd integers that are not a prime plus r or fewer powers of two. The passage also separates infinitude, density and arithmetic-progression questions. This source supplies historical attribution through retained extracted text. Its passage does not explicitly fix zero or repeated exponents or the empty sum; those conventions here come from the complete formal source. The prior screenshot response contained only a text marker and no image payload. No visual inspection is claimed, and the separate garbled Granville–Soundararajan PDF route was not retried.

The actual input is `input70.json`. Only its seven-value prime array was transferred from the released [E364 packet, PR #31780](https://github.com/woahwhattheheck/commons/pull/31780), at merge
`7aaf6aa49acc15d91cdd4e9505a5cd28b95ae995`, path
`research/erdos364_prime_square_obstructions/palette7_consecutive_triples.json`,
blob `944c37d1786272166338e2c5dbf64274f29e29ef`, field `primes`.
No prior modular table, prime sieve, CRT calculation, binary representation table or E9 calculation was imported or rerun. These prime values are identified input premises; this module performs no primality tests.

The actual parameters are bit length B = 70, low width L = 5, base 32 and high width K = 65. All inputs in this domain exceed all selected primes, so their remainders are positive. The source's empty-sum convention is therefore not an attained case in this consumer.

## Exact reduction

For a nonnegative integer m, the fewest powers of two whose sum is m equals its binary popcount. To see this even when repetition is permitted, repeatedly replace two equal powers by the next power. Each replacement reduces the number of terms, and the final distinct-power expansion is the unique binary expansion. That expansion itself attains the resulting bound. This elementary argument supports this implementation; it is not presented as a new theorem.

Write n = 32q + r, where 0 ≤ r < 32 and q has exactly 65 bits. For a selected prime p < 32, put b = 1 when r < p and b = 0 otherwise. Then

```text
n - p = 32 (q - b) + (r - p mod 32).
```

The two displayed parts occupy disjoint binary positions. For each residue r, the constructor saves every prime's borrow bit, low remainder and low popcount, along with the minimum low cost and all tied primes separately for the two borrow cases.

Let t = v2(q). Since q > 0,

```text
popcount(q - 1) = popcount(q) - 1 + t.
```

Thus, if C0 and C1 are the best available low costs without and with borrowing, the selected-prime minimum is

```text
popcount(q) + min(C0, C1 + t - 1),
```

with an unavailable borrow class omitted. Equality between the two costs retains both classes' prime masks. This accounts for all seven primes, including ties; a support bit means the prime is optimal, not merely that it produces some representation.

For t < 64 the high part has the template `1 ?...?... 1 0...0`, with 63 - t free bits and t trailing zeroes. For t = 64 it is `1` followed by 64 zeroes. Appending the five-bit encoding of r gives one full block. There are 32 × 65 = 2,080 disjoint blocks, covering the whole domain.

Within a block the cost is the number of free ones plus a saved fixed offset. The row of binomial coefficients for f free bits counts strings by their number of ones. Its saved cumulative row answers any allowed-weight interval by subtraction. Summing these complete block weights yields the global cost histogram and the cost/optimal-prime-mask histogram. The constructor checks that the total block weight equals the domain size; it does not enumerate the represented integers.

## Actual saved result

| Quantity | Exact value |
| --- | ---: |
| 70-bit integers represented | 590295810358705651712 |
| Bit-template blocks | 2,080 |
| Minimum selected cost | 1 |
| Integers attaining minimum | 7 |
| Maximum selected cost | 67 |
| Integers attaining maximum | 73 |
| Integers with selected cost at most 3 | 15,615 |
| Distinct exact optimal-prime masks | 17 |
| Nonzero joint cost/mask buckets | 1,113 |

The seven cost-one integers are exactly 2^69 + p for p in the supplied palette. Each has that one selected prime as its unique optimum and exponent list [69]. Both endpoints of the 70-bit domain have selected cost 67, with tied optimal primes 7, 11 and 13.

The complete cost histogram is in `bit70_minima_index.json`. Complete minimum and maximum family exports are saved as reader queries 9 and 18. Their order is the API order below, so “first maximum” does not mean the numerically smallest integer with cost 67.

Examples of the declared conditional families are:

| Condition | Exact count |
| --- | ---: |
| Cost at most 3 and binary prefix `10` | 15,151 |
| Cost exactly 30 and prime 5 among the optimizers | 5,591,766,152,171,334,128 |
| Low residue 0 and binary prefix `11101` | 1,152,921,504,606,846,976 |
| Binary prefix `0` | 0 |
| All seven primes simultaneously optimal | 0 |

The cost-thirty midpoint query has n = 891377239442469171113 and tied optimal primes 5, 7 and 17. The returned witness and inverse rank are in the saved responses. These examples are query results for this input, not claims about the unrestricted prime universe.

## API and ordering

Load `selected_prime_binary_minima.cjs` as a CommonJS module. It exports `SCHEMA`, `construct(input)` and `open(snapshot)`.

A future caller may construct a genuinely new declared input. To consume this published input, load the already saved JSON and call `open`; do not rerun `construct` merely to reproduce the certificate.

```javascript
const fs = require("node:fs");
const { open } = require("./selected_prime_binary_minima.cjs");
const snapshot = JSON.parse(fs.readFileSync("./bit70_minima_index.json", "utf8"));
const api = open(snapshot);
const options = { min_powers: 30, max_powers: 30, required_prime_mask: 4 };
const family = api.family(options);
const selected = api.select("2795883076085667064", options);
const inverse = api.rank(selected.n, options);
```

This example illustrates the interface and the saved request; it was not executed again while writing the guide.

The total order is increasing low residue r, then increasing t = v2(q), then lexicographic order of the free bitstring within that block. **It is not numerical order of n.** All ranks are zero-based decimal strings. The order remains the same after filtering.

| Method | Meaning |
| --- | --- |
| `summary()` | Saved domain, histogram, prime-mask counts and construction work |
| `family(options)` | Compile or reuse a condition; return its count and nonempty block count |
| `select(rank, options)` | Select one member in the declared block order |
| `rank(n, options)` | Return membership and rank, or a nonmember result |
| `page(start, limit, options)` | Up to 100 consecutive selected members |
| `profile(n)` | Exact saved-block cost and all optimal primes |
| `representation(n, primeIndex?)` | Canonical distinct-power representation using one optimal prime |
| `low(residue)` | One of the 32 saved low-residue records |
| `block(id)` | One of the 2,080 saved blocks |
| `caches()` | Complete conditions compiled in this reader instance |
| `work()` | Cumulative instrumentation counters |

Options are optional integer `min_powers` and `max_powers` in 0..B, integer `required_prime_mask` and `forbidden_prime_mask`, optional integer `low_residue` in 0..31, and an optional binary prefix of length at most B. Mask bit j names `primes[j]`; required bits must all be optimal and forbidden bits must all be absent from the optimal set. Contradictory cost bounds or overlapping required/forbidden masks are rejected. A leading-zero prefix is valid and yields no 70-bit members.

Pass the original options object to later calls. Returned normalized conditions use `low_residue: null` to describe an omitted restriction, whereas the public input contract accepts omission or an integer, not explicit null.

`representation` permits only a prime marked optimal. With no prime index it selects the least palette index among the ties. It subtracts that prime, scans the remainder's binary digits and returns its increasing set-bit exponents. It checks that their count matches the saved minimum. This is fresh query arithmetic, not lookup of an old power-sum table.

`open` performs structural shape checks; it does not independently reprove primality, regenerate low costs or validate every coefficient. Its correctness depends on the identified input premises, the saved data and the stated construction reasoning. No claim of an independent proof checker is made.

## Saved reader and query work

The first reader started only after source, input and complete construction output were banked. Its 47 responses are complete in `saved_reader_queries.json`. They include:

- All seven cost-one and all 73 cost-67 members.
- Seven minimum-family inverse ranks, three maximum-family inverse ranks, three full-family inverse ranks and three conditioned inverse ranks: all 16 match.
- Full-family first, midpoint and last selections in the stated order.
- Three declared conditioned midpoint selections and inverse ranks.
- Lower and upper endpoint profiles, four canonical representations and the first and last saved blocks.
- Two empty conditions and a deliberate nonmember rank query.

Nine condition caches contain 5,264 entries. They are exported in three complete-record shards, with `conditional_cache_manifest.json` recording order and identities. The original full cache serialization has Git blob `c2f95918e0b4998e74249d6aff126fc5a440c3f8` and 1,237,444 bytes. Concatenating the shard cache arrays in order and using the manifest's serialization reconstructs these bytes exactly. This assembly is a byte-identity operation only; no condition, coefficient or mathematical result was rebuilt.

The reader keeps its cache within one `open` instance. The published cache files preserve the actual query evidence; this version does not provide an API to import them into a new instance. A later fresh condition compilation must be reported as new query work.

The reader's instrumented work is:

| Counter | Actual value |
| --- | ---: |
| Conditions compiled / cache hits | 9 / 25 |
| Saved block scans | 18,720 |
| Prefix character checks | 6,559 |
| Conditional entries / prefix additions | 5,264 / 5,264 |
| Saved Pascal-prefix reads / range subtractions | 11,150 / 5,575 |
| Cache binary-search probes | 637 |
| Selection / rank bit decisions | 2,803 / 436 |
| Rank additions / subtractions | 197 / 2,634 |
| Template character reads | 7,140 |
| Input bit scans | 2,285 |
| Profile cost additions | 23 |
| Representation subtractions / bit scans | 4 / 280 |
| Saved low records / block reads | 4 / 25 |

The request preparation additionally records four BigInt midpoint divisions and one BigInt final-rank subtraction. Ordinary loop, array-index and validation operations are not presented as a complete arithmetic-cost census. All 47 responses and their cumulative counters were banked immediately. There was no failed reader request or unavailable reader output in this delivery.

The reader reports zero constructor calls, new low costs, new Pascal cells, new base-histogram cells, primality tests and integer enumeration. Its conditional scans, rank/select arithmetic, bit scans and four remainder calculations are real new work and are not described as zero computation.

## Construction work and limits

The executed source has Git blob `185fe1d56f9a08aaac1a567c36e08acf77bb43ee` (14,635 bytes). Before its first execution, a static instrumentation clarification changed the histogram counter to charge both additions per weight and named the borrow-cost addition/subtraction counter. The earlier 14,615-byte draft was never executed. No construction was rerun.

The actual constructor formed 32 low-popcount cells with 31 additions; 224 low-prime records and subtractions with 58 wrap additions; 2,080 Pascal cells with 1,953 additions; and 2,144 cumulative cells with 2,080 additions. Its 2,080 blocks used 2,210 instrumented borrow-cost addition/subtraction steps, 133,184 histogram additions, 2,080 prime-mask histogram additions and 2,080 total-weight additions. These counters describe the named operations, not elapsed time or a complete machine-instruction count.

Generic bounds are B ≤ 160, low width 2..8, at least two high bits and at most 16 ordered prime premises below the low base. The supplied actual caps are 10,000 blocks, 20,000 combined Pascal/cumulative cells and 1,000,000 histogram additions. Cap failure is an error, not permission to publish a partial result as complete. This actual input completed within every cap.

## Files and scope

`input70.json` records the exact input and premise lineage.
`bit70_minima_index.json` is the full 850,502-byte construction snapshot, Git blob
`a781a03e3113d1bf6ecfe968178a33248d6dcacf`.
`saved_reader_queries.json` is the full 134,237-byte reader packet, Git blob
`97992d98d411aa0b10f7cea539025248b276ecae`.
The three cache shards and their manifest retain all conditional entries. No live source or network call is needed for saved-data navigation.

This package proves exact finite statements for the declared bit-length domain and selected prime palette, conditional on the identified prime premises. It neither proves a uniform bound for every prime, verifies or extends a published counterexample range, settles an infinitude or density assertion, nor claims mathematical novelty or a prize result. Historical source wording and current formal annotations are kept separate from proof verification.
