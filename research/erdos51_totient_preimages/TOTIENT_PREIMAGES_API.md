# Complete finite inverse-totient fibers

This package exhausts all positive integers n whose Euler totient divides a declared positive integer M. It compiles the complete inverse fibers for every divisor of M, retaining exact counts, least and greatest preimages, and navigation in prime-exponent lexicographic order.

The actual input is **M=20736=2^8·3^4**. Its 45 divisors give **41 nonempty fibers containing 1,314 positive integers in total**. In particular, **φ(n)=20736 has exactly 173 positive solutions; its least solution is 21037 and its greatest is 103740**. These are complete finite-fiber conclusions, not statements restricted to a scanned interval of n.

## Source conventions and the infinite question

[NIST DLMF §27.3, equation 27.3.3](https://dlmf.nist.gov/27.3) supplies the positive-integer formula
`φ(n)=n∏_{p|n}(1-1/p)`, over distinct prime divisors. The section's multiplicative-function convention includes φ(1)=1. The independently retained [Beachy–Blair author excerpt, Proposition 1.4.8](https://faculty.niu.edu/math_beachy/aaol/integers.shtml), supplies the same product. These source passages were already read for earlier work and were transferred as conventions without another source call.

For a positive prime power, the formula gives φ(p^e)=p^(e-1)(p-1). The finite candidate exhaustion and dynamic program below are this package's derivation from that classical formula. Neither source is claimed to supply this implementation, its numerical output, or a newly discovered inverse-totient algorithm.

The complete [FormalConjectures Erdős 51 statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/51.lean) was read for this task. Its decoded content has Git-blob identity `f951c1611ba273f26782b1946a78c26f6dd977f3` (1,436 bytes). It asks whether there is an infinite set A of attained totient values such that the least preimage n_a satisfies n_a/a→∞ as a→∞ through A. The source currently annotates the question research open and retains a local placeholder. This is source-limited status, not an independent literature survey or proof audit.

The implementation uses positive n, including 1, and positive target values. It does not import a natural-number convention at n=0. For positive targets this causes no spurious zero preimage. The exact fiber at target 1 contains 1 and 2. A finite collection of least-preimage ratios does not answer the infinite-set question, even when every selected fiber is exhausted.

No prize, sponsor acceptance, current quantitative frontier, or novelty claim is made.

## Why the finite candidate set is complete

Suppose φ(n) divides M and p is any prime dividing n. The factor p-1 divides φ(n), so p-1 divides M. Every possible prime factor of n therefore appears among d+1 for d ranging over the complete positive divisor set of M. It is unnecessary to guess an upper bound for n or to restrict n to the primes dividing M.

The constructor factors M by exact integer trial division, generates all its divisors, and examines every candidate d+1. A candidate is prime exactly when no integer k with 2≤k and k²≤d+1 divides it. The saved trial list records each tested divisor and remainder, stopping at the least divisor for a composite. Exhausting that range certifies primality by the elementary fact that a composite has a factor at most its square root. Values 2 and 3 have empty trial lists and satisfy this argument. These are fresh checks for this construction, not reuse or replay of a prior prime table.

For each surviving prime p, the options are:
- exponent e=0, contributing n-block 1 and totient-block 1;
- every e≥1 for which p^(e-1)(p-1) divides M, contributing n-block p^e and that totient-block.

The positive blocks increase with e, so this list is finite and exhaustive. The special choices p=2,e=0 and p=2,e=1 both have totient-block 1 but different n-blocks. They are retained separately. Advancing the prime stage, rather than requiring the residual target to decrease, handles this correctly.

Every positive n with φ(n)|M yields exactly one option at each candidate prime, by unique prime factorization. Conversely every option vector whose totient-block product equals a target t|M produces a positive n with φ(n)=t. Distinct vectors produce distinct integers. This establishes a bijection and the completeness of all selected fibers.

## Suffix recurrence and extrema

Order the candidate primes increasingly and their options by increasing exponent. Let C_i(t) count suffix option vectors beginning at prime stage i whose totient product is t. At the terminal stage, C_s(1)=1 and C_s(t)=0 for t≠1.

For an option o with totient-block w and integer block v, the transition is allowed exactly when w divides t. Then
`C_i(t)=Σ_o C_(i+1)(t/w)`.
All residual targets remain divisors of M, so a rectangular stage-by-divisor table suffices.

Alongside each count, the source stores the minimum and maximum integer products among nonempty suffixes:
`min_i(t)=min_o v·min_(i+1)(t/w)`,
with the analogous maximum. Empty suffixes contribute nothing; target 1 at the terminal stage has product 1. The chosen option indices support exact extremal traces. The minimum and maximum here are in ordinary numeric order, independently of the navigation ordering.

Select traverses options in increasing exponent order, subtracting saved child counts. Rank adds the counts of preceding valid options. Both retain their complete stage traces and assemble the resulting n from saved prime-power blocks. The order is lexicographic on the full exponent vector over ascending candidate primes. It is **not increasing numeric n**.

## Actual finite certificate

| Quantity | Value |
| --- | ---: |
| Target M | 20,736 |
| Positive divisors / target fibers | 45 |
| Attained target values | 41 |
| Candidate values d+1 | 45 |
| Certified candidate primes | 22 |
| Options, including exponent zero at every prime | 56 |
| Positive-exponent options | 34 |
| Suffix table cells, including terminal row | 1,035 |
| Represented positive integers across all fibers | 1,314 |
| Trial steps used to factor M | 2 |
| Successful factor divisions of M | 12 |
| Divisor products generated | 44 |
| Candidate primality trial divisions | 626 |
| Dynamic-program option visits | 2,520 |
| Divisible option transitions | 1,617 |

The 22 candidate primes are
`2,3,5,7,13,17,19,37,73,97,109,163,193,257,433,577,769,1153,1297,2593,3457,10369`.
Their presence illustrates why restricting n to the prime factors 2 and 3 of M would miss solutions.

Selected complete fibers:

| Totient target | Count | Least preimage | Greatest preimage |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 1 | 2 |
| 2 | 3 | 3 | 6 |
| 3 | 0 | — | — |
| 8 | 5 | 15 | 30 |
| 128 | 9 | 255 | 510 |
| 2,304 | 66 | 2,509 | 10,920 |
| 10,368 | 124 | 10,369 | 51,870 |
| 20,736 | 173 | 21,037 | 103,740 |

The four empty target fibers are 3, 9, 27, and 81. The complete 45-row target table, including reduced least-preimage ratios, is retained in the snapshot. Totient fibers are disjoint, so their counts sum to the 1,314 represented integers without duplicate counting.

Construction does not enumerate those 1,314 full exponent vectors or integers. It stores their finite candidate, option, and suffix representation. The reader expands only requested vectors and pages.

## API

The CommonJS module exports `buildIndex(input)` and `openIndex(snapshot)`. The constructor accepts `{M:"20736", ...metadata}`; M must be a canonical positive decimal string and at most 1,000,000. The recorded input metadata is preserved but is not used as a factorization premise: the constructor factors the supplied M itself.

The saved consumer opens the existing index:

```javascript
const {openIndex} = require("./totient_preimages.cjs");
const snapshot = require("./divisors20736_preimages.json");
const index = openIndex(snapshot);
const fiber = index.query({op:"fiber", target:"20736"});
const least = index.query({op:"extreme", target:"20736", kind:"minimum"});
const selected = index.query({op:"select", target:"20736", rank:"86"});
const back = index.query({
  op:"rank", target:"20736", exponents:selected.exponents
});
console.log(fiber.count, least.n, selected.n, back.rank);
```

Counts, targets, ranks, integers and block products are decimal strings. Prime indices, exponents and stages are ordinary bounded integers. String integer inputs must be canonical and at most 4,096 characters. Target queries require a positive divisor of saved M: an unsupported target is rejected, not reported as having zero preimages. Only an included target with saved count zero has an empty certified fiber.

| Query | Result |
| --- | --- |
| `summary` | Saved counts of targets, candidates, primes, options and represented integers |
| `targets` | All saved fiber counts, numeric extrema and reduced least ratios |
| `factorization` | M's factorization trace and divisor list |
| `candidates` | Every d+1 candidate with full trial remainders and least-divisor witness |
| `primes` | Candidate-prime records and all exponent options |
| `fiber, target` | One saved complete fiber summary |
| `state, stage, target` | One saved suffix cell |
| `extreme, target, kind` | Numeric minimum or maximum with a saved-choice trace; null n for an empty fiber |
| `select, target, rank` | One preimage in exponent lexicographic order |
| `rank, target, exponents` | Rank and integer for a complete valid exponent vector |
| `page, target, start, limit` | Consecutive selected records, with limit 0–1,000 |
| `classify, n` | Exact membership in the saved union, with a target and rank when admitted |

The classify query divides the supplied positive integer by the saved candidate primes. If a residual factor remains or a listed exponent exceeds its allowed options, the integer is outside this saved family. If all prime factors and exponents fit, it multiplies the saved totient-blocks; their product must still divide M. This last check matters: independently allowed prime powers can consume too much of one target factor when combined. An outside-family answer does not classify any unrelated number-theory property.

The reader performs structural parsing, not a full independent proof check of adversarial snapshots. It trusts the identified source and certificate. It does not repeat primality testing, option construction, or the suffix recurrence. Returned data are copied. Query arithmetic such as exact division and multiplication remains real work and is counted as described below.

## Fresh reader and actual ordering

The fresh session has **37 complete, individually banked responses**, followed by one banked aggregate. There was no failed query or missing response.

For target 20736:
- exponent rank 0 selects 21037;
- rank 86 selects 55420;
- rank 172 selects 62208;
- all three selected exponent vectors return their original ranks and integers;
- the numeric minimum 21037 happens to have exponent rank 0;
- the numeric maximum 103740 has exponent rank 94, demonstrating the ordering distinction.

The page at target 1 returns both 1 and 2. A page of the empty target-3 fiber is empty. The session retains five selected records beginning at target-20736 rank 80. It also returns exact minimum/maximum traces, complete candidate and target records, and terminal/intermediate table cells.

Classification queries recognize 1,2,21037,103740 and 4 in the saved union. The candidate 20737 and the huge integer 10^100 are outside it. The latter query uses exact repeated division of the supplied integer; it is not a replay of candidate primality or table construction.

Fresh scoped work totals:
- 657 saved suffix-cell reads;
- 305 option visits in rank/select traversal;
- 660 integer product multiplications in assembly/classification;
- 212 successful exact factor divisions.

These counters are not an exhaustive arithmetic-operation count: parsing, failed divisibility tests, map access, comparisons, rational reduction, copying and source-independent overhead are not all represented. No timing or complexity improvement is claimed.

## Immutable data and production history

| Artifact | Git-blob identity | UTF-8 bytes |
| --- | --- | ---: |
| Frozen executed source | ff5b9ca06a168a0f805735f89e87a86d79f3af61 | 9,200 |
| Frozen complete input | 42a027210dc32092c129a58d59f53906b8d8f20b | 347 |
| Complete snapshot | 941a179632d7332e3a73a91f575c582ac8d20127 | 219,820 |
| Complete reader output aggregate | 5f2b25546ac3ab099e855039f5f419038ff0f5d8 | 239,931 |

The snapshot includes the input, factorization trace, all divisors, candidate tests, prime-power options, every suffix cell, all 45 target summaries and construction counters. The reader file includes every request, response, cumulative counter and selection/rank comparison.

Source syntax was parsed before freezing. The actual bounded construction ran once; each result and reader response was banked before dependent work continued. The previously accepted E828 finite smooth-host totient computation, E50 density bounds and E936 modular screens were not rerun. This new computation's complete positive inverse fibers differ from those earlier fixed-input families.

The resulting finite least-preimage table does not produce an infinite sequence with diverging least-preimage ratio or establish the Erdős 51 assertion.
