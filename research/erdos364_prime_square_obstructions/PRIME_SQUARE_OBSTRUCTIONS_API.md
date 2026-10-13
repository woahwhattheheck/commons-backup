# Prime-square obstruction navigation for consecutive powerful numbers

This finite index represents all starting residues modulo **260,620,460,100** for the three offsets 0, 1 and 2 and the supplied prime palette **{2,3,5,7,11,13,17}**. It records exactly which shifted integers have an exponent-one prime witness from that palette. Its **666 local rows** and **64 suffix coefficients** represent the complete phase family without enumerating its 260 billion residues.

A set bit is a certificate that the corresponding positive integer is **not powerful**. An unset bit means that the selected primes did not exclude it. In particular, the **3,526,439,007 mask-zero phases are unresolved survivors**, not a collection of powerful triples or a counterexample family.

The package offers exact conditioned phase counts, coordinate ranks, selections, positive representatives, periodic translates and explicit divisibility witnesses. It is not a search for actual powerful triples, a verification or extension of an existing existence-search range, or a solution of the general conjecture.

## Definition and actual sources

A positive integer N is powerful when every prime p dividing N also satisfies p²|N. Thus one prime with p|N and p²∤N excludes powerfulness. The predicate includes 1 vacuously. No conclusion follows from a failure to find such a prime in a finite list.

The retained primary convention was supplied by the successfully read journal abstract of Edward Beckon, [“On Consecutive Triples Of Powerful Numbers”](https://scholar.rose-hulman.edu/rhumj/vol20/iss2/3/), Rose-Hulman Undergraduate Mathematics Journal 20(2) (2019), Article 3. That previously qualified abstract supplies the definition; this package did not reread a numerical example, proof, table or status discussion from the paper. No result here is attributed to that author beyond the retained definition.

The exact problem statement was separately and completely read from [FormalConjectures/ErdosProblems/364.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/364.lean). Its observed UTF-8 blob is **f1d6e09dc6a147f10d1e213addf0f845afa44c4d**, 2,186 bytes. The request used the contents endpoint without an explicit ref; the blob identifies the actual returned text, while the branch URL can move.

The formal main statement quantifies a natural n and asserts that n,n+1,n+2 cannot all be powerful. The API's restriction **n≥1** is explicit and is not presented as the literal quantifier of that theorem. The observed main and stronger gap variants are tagged research open with local placeholders. The file also contains a separate textbook quadruple theorem; it is not the target of this computation and was not executed or reproduced. No Lean proof verification or exhaustive current literature assessment is claimed.

## Exact input lineage

Only the seven prime values were transferred from the already retained prime prefix in Commons [#31726](https://github.com/woahwhattheheck/commons/pull/31726):

- Repository: woahwhattheheck/commons.
- Merge input ref: e04374c3650c68ff5ed22c8997f6805eb5b31c85.
- Path: research/erdos238_consecutive_prime_blocks/prime_prefix1900_blocks.json.
- Git blob: 0224dfb74525d7d18b6e5aba20f01e1784a0c8f2.
- Zero-based positions: 0 through 6.
- Literal values: [2,3,5,7,11,13,17].

This transfer used the saved prime array. It did not consume an old least-factor table or replay a sieve, primality test, prime-gap calculation or earlier CRT family. The prime status of the supplied values is an inherited input premise.

The generic constructor requires one through twelve increasing distinct prime premises, each at most 97. It checks the integer/order bounds and coprimality needed by its CRT inverses, but does not perform primality testing. Supplying composite values would violate its mathematical input contract, even if an unrelated coprimality check happened to pass.

The constructor source and complete input were banked before the single actual calculation. Input blob **e397981ffbdbfdb2dd71952b5809b0d4626ae9f1** has 1,259 bytes. The complete output was banked before the fresh saved reader.

## Local masks and the CRT family

For a prime p and r in {0,…,p²−1}, local bit i is set exactly when p divides r+i and p² does not divide r+i, for i=0,1,2. This is a predicate on the residue r modulo p². For every positive n with n≡r mod p², it has the same truth value for n+i.

The bit assignments are:

| Bit value | Certified excluded number |
|---:|---|
| 1 | n |
| 2 | n+1 |
| 4 | n+2 |

The aggregate mask is the bitwise OR of the seven local masks. Its exact meaning is “the offsets excluded by at least one selected prime,” not “all nonpowerful offsets.” Additional primes may exclude offsets whose bits are unset.

The moduli are 4,9,25,49,121,169,289. They are pairwise coprime. The Chinese remainder correspondence identifies each residue-coordinate tuple with exactly one phase modulo their product M=260620460100. Saved cofactors, inverses and CRT weights reconstruct that phase.

The constructor stores a local mask for every residue, a local eight-bin histogram, and suffix mask coefficients. For a coordinate i and suffix aggregate mask m, the coefficient counts tuples of all remaining residues whose OR is m. The terminal empty tuple has mask zero and count one. Prepending a local residue with mask a sends a tail mask b to a OR b; multiplying by the local histogram and summing gives the recurrence.

The recurrence classifies every coordinate tuple exactly once. CRT then proves that its root counts classify every phase exactly once. No phase enumeration or actual integer factorization is needed.

M is used as a valid period. No claim that it is the smallest period is required. The modular predicate applies to every positive translate in the class; it remains a necessary-condition screen rather than a complete powerful-number test.

## Complete counts

| Exact aggregate mask | Offsets excluded by the palette | Phase count |
|---:|---|---:|
| 0 | none; all three unresolved | 3,526,439,007 |
| 1 | n | 20,147,642,843 |
| 2 | n+1 | 20,147,642,843 |
| 3 | n, n+1 | 46,396,094,180 |
| 4 | n+2 | 20,147,642,843 |
| 5 | n, n+2 | 46,396,094,180 |
| 6 | n+1, n+2 | 46,396,094,180 |
| 7 | n, n+1, n+2 | 57,462,810,024 |

Mask zero has 3,526,439,007 phases. Every other mask certifies that the triple cannot consist entirely of powerful numbers. A mask-seven phase certifies that all three numbers are nonpowerful. These are exact statements about the selected-prime predicate, not a classification of all actual triples.

Some saved all-three-survivor prefix conditions are:

| Residue-coordinate prefix | Remaining phase count |
|---|---:|
| empty | 3,526,439,007 |
| [0] | 0 |
| [3] | 3,526,439,007 |
| [3,0] | 1,175,479,669 |
| [3,8,24] | 90,421,513 |

Coordinates in that table use the successive moduli 4,9,25,… . They are not digits in an ordinary positional number system.

## Ordering and positive representatives

The index orders residue tuples lexicographically, using increasing residues at the modulus-4 coordinate first, then modulus 9, and so forth. It does **not** order starting integers numerically.

For example, the first five mask-zero tuples yield positive representatives:

1. 195465345075.
2. 91758241575.
3. 248671598175.
4. 144964494675.
5. 41257391175.

Their lack of numerical ordering is intentional. The first tuple is [3,0,0,0,0,0,0]; subsequent tuples in this page increment the final coordinate.

The CRT phase lies in [0,M−1]. The API maps phase zero to the positive representative M and leaves all other phases unchanged, producing one representative in [1,M]. A nonnegative decimal cycles argument q selects n=representative+Mq. This keeps n positive and gives one complete period per fixed q.

Rank depends on the residue tuple and the requested condition. The same residue tuple in different positive periods has the same rank. There is no numeric-window counting, increasing-integer rank or claim to enumerate all positive integers through a finite count.

## Saved API

The dependency-free CommonJS module exports construct(input), open(snapshot) and SCHEMA. Importing it does not calculate anything.

~~~javascript
const api = require("./prime_square_obstructions.cjs");
const reader = api.open(snapshot);
reader.family({must_survive:7});
reader.select("0", {must_survive:7});
reader.rank("195465345075", {must_survive:7});
reader.family({prefix_residues:[3,0], must_survive:7});
reader.witness("100000000000000000000000000000000000000000000000000000000000000000000000000000019");
~~~

Methods:

| Method | Result |
|---|---|
| summary() | Saved palette, period, exact mask counts and construction work |
| family(options) | Number of phases satisfying the condition |
| select(rank,options,cycles="0") | Conditioned coordinate rank, tuple, phase and positive translated integer |
| rank(n,options) | Conditioned rank or a nonmember result for the positive integer |
| page(start,limit,options,cycles="0") | Up to 100 selected rows; ranks remain coordinate-lexicographic |
| local(index) | The complete retained local mask row and histogram |
| witness(n) | All selected-prime exponent-one witnesses for the three shifted integers |
| work() | Fresh saved-reader work counters |

Options have optional must_fail and must_survive masks in [0,7], and a prefix_residues array. These two masks must be disjoint. must_survive means that no selected-prime obstruction is allowed at the corresponding offset; it does not demand or certify actual powerfulness.

An exact mask m is requested by must_fail=m and must_survive=7 XOR m. Leaving both zero includes every mask. A residue prefix fixes the first coordinate values exactly. Every count concerns phase tuples in one period, not distinct integers across an unbounded set of translates.

Integers, ranks and cycles are nonnegative decimal strings, with n required positive. Malformed conditions and out-of-range selections throw. Empty prefixes are permitted. The reader performs structural checks of the saved arrays, not a new local predicate or coefficient verification.

Condition counts sum selected saved suffix coefficients. Selection subtracts preceding residue-branch counts; ranking adds them. A selected tuple is reconstructed with saved CRT weights. These operations are fresh query arithmetic and are explicitly counted, while local mask and suffix-table construction remain zero.

## Explicit large witness

One actual reader request uses n=10^80+19. Its saved lookup returns mask 7 and four obstruction records:

| Shift | Prime | Nonzero remainder modulo p² |
|---:|---:|---:|
| n+1 | 3 | 3 |
| n+1 | 5 | 20 |
| n | 7 | 7 |
| n+2 | 11 | 110 |

The full output retains each positive shifted value, its exact quotient by p, its quotient by p² and its nonzero remainder modulo p². Thus it supplies witnesses for all three offsets. These quotient operations are query work on this requested integer, not a factorization or a rebuild of local tables.

Other actual selections use q=10^50 periods. The saved rank responses recover the same coordinate ranks after those translations. A survivor selected at such a large translate remains unresolved, just as its representative does.

## Actual construction and limits

The constructor's engineering limit is at most 10,000 local rows, checked before enumerating the residue rows. The prime-count and prime-size bounds are also checked before the substantive calculation. The actual run uses seven primes and 666 rows.

| Construction operation | Count |
|---|---:|
| Modulus products p² | 7 |
| Period products | 7 |
| Local residue rows | 666 |
| Divisibility remainders modulo p | 1,998 |
| Remainders modulo p² after p divides | 174 |
| Histogram increments | 666 |
| CRT cofactor divisions | 7 |
| Euclidean divisions for inverses | 32 |
| CRT weight products | 7 |
| Retained suffix coefficient cells | 64 |
| Weighted suffix products | 176 |
| Suffix additions | 176 |

Primality tests, full-phase enumerations and integer factorizations were zero. No cap was reached and no failed construction was repeated.

## First fresh reader and custody

The banked fresh reader contains **52 complete responses**:

- the summary and all seven local tables;
- all eight exact-mask family counts;
- first, middle and last selections for masks 0,1,3,7, with twelve matching inverse rank responses;
- four translated witness requests and one independent huge-integer witness;
- five survivor prefix conditions;
- the first five survivor phases;
- an unrestricted rank request for the independent huge integer.

Every response was saved immediately before the next query. The twelve inverse pairs were compared from their retained strings; no query was rerun for that comparison. No reader response was lost.

| Fresh reader operation | Count |
|---|---:|
| Queries | 52 |
| Saved local-row reads | 8,623 |
| Saved coefficient reads | 68,272 |
| Coefficient sums | 20,579 |
| Selection branches | 4,127 |
| Rank branches and additions | 4,363 each |
| Rank subtractions | 4,008 |
| CRT products and additions | 119 each |
| CRT reductions | 17 |
| Translation products and additions | 17 each |
| Input residue reductions | 126 |
| Witness value additions | 10 |
| Witness prime quotients | 10 |
| Witness square quotients and remainders | 10 each |

Reader construction calls, new local predicates, new suffix coefficients, primality tests and factorizations were all zero. Request preparation separately used four midpoint divisions, four last-rank subtractions, one 10^80 power evaluation and one addition. Parsing, array access and metadata serialization are not presented as zero-cost operations.

The complete 13,289-byte snapshot has Git blob **944c37d1786272166338e2c5dbf64274f29e29ef**. It includes all local rows, histograms, CRT constants, suffix cells, counts, provenance and work counters. The saved reader file contains full requested tuples, integers and quotient witnesses. Nothing is represented by a digest in place of its underlying data.

The bounded qualification recorded an unavailable all-state PR search after a secondary rate limit. That exact query remains held; the completed source reading, current Slack observations and separate code-carrier check are not relabelled as exhaustive repository absence. This limitation creates no mathematical evidence for the conjecture.

The publication supplies this particular finite modular index and its exact positive translations. It does not prove the no-triple conjecture, its stronger gap variant, actual powerfulness of any survivor, a new search frontier, an asymptotic density statement about powerful triples, or any record, priority, sponsor or prize claim.
