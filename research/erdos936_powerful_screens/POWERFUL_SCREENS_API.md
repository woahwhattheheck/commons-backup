# Periodic local screens for powerful numbers

This module gives exact selected-prime obstructions to powerfulness of a^n+1 and a^n−1, for positive exponents n. It compiles small modular-power cycles, then combines their flags in independent CRT coordinates. The saved counts support classification, modular witnesses and rank/select over positive period blocks without expanding the powers or enumerating all global exponent phases.

The actual input is base a=2 and the identified odd primes 3,5,7,11,13,17. One valid exponent period is P=4,084,080. Its four exact local-screen classes are:

| Mask | Meaning | Phases per period |
|---:|---|---:|
| 0 | Neither sign excluded by a selected prime | 79,632 |
| 1 | Plus sign excluded, minus sign not excluded | 1,418,784 |
| 2 | Minus sign excluded, plus sign not excluded | 1,159,200 |
| 3 | Both signs excluded | 1,426,464 |

Thus 2,845,248 phases exclude powerfulness of 2^n+1, and 2,585,664 exclude powerfulness of 2^n−1. Passing a local screen means only that this finite prime list supplies no valuation-one witness. It is not a proof that the value is powerful.

## Definitions, sources and scope

A powerful number is a positive integer N such that every prime divisor p also satisfies p²|N. This convention is stated in Edward Beckon, *On Consecutive Triples Of Powerful Numbers*, Rose-Hulman Undergraduate Mathematics Journal 20(2) (2019), Article 3, primary abstract:
https://scholar.rose-hulman.edu/rhumj/vol20/iss2/3/

Accordingly, one prime p for which p|N but p² does not divide N certifies that N is not powerful. The absence of a witness among selected primes does not decide the predicate. The definition permits 1 vacuously; the API uses n≥1, so both a^n±1 are positive for a≥2. It does not apply the positive powerful-number predicate to the n=0 minus value zero.

Beachy and Blair's author-hosted *Abstract Algebra*, second-edition excerpt, Theorem 1.4.11 gives Euler's theorem for a base coprime to the modulus, and Proposition 1.4.8 gives the totient product:
https://faculty.niu.edu/math_beachy/aaol/integers.shtml

For an identified odd prime p not dividing a, Euler's theorem gives a^(p(p−1))≡1 modulo p². The integer p(p−1) is a valid period of the power residues; it is not asserted to be their least order. The modular cycles in this artifact are a new finite construction for this input. Source statements were inspected, not their proofs or numerical examples.

The complete FormalConjectures source read for the problem is:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/936.lean
blob 44466434df56d3a2b1cbebd79de42757a2b0b5f6.

It records four separate eventual-nonpowerful questions, for 2^n+1, 2^n−1, n!+1 and n!−1, all with research-open annotations and local placeholders. These are retained source annotations, not an independently verified current frontier. This module concerns the exponential pair only; it does not compute a factorial variant, establish finiteness, claim a new mathematical record, contact a sponsor or submit for a prize.

## Identified input and execution lineage

Only the prime values were reused from accepted #31649:

- Merge 0e4428eaef33d6c06bace7c5b1dc0d96f15f6496.
- research/erdos828_totient_shifts/primes17_cap3_index.json.
- Blob 06d71f61df8e7913a2131bcad12a9b229c452a35.
- Exact field input.primes, omitting 2.
- Earlier provenance is #31519's input.moduli list.

The supplied primes are an explicit premise. No primality test or old CRT, sieve, gap, product, factorization or totient calculation was replayed. The new CRT coordinate coefficients belong to this new exponent period; they are not borrowed from the earlier covering index.

The exact input fixes base=2, base_period=240 and primes=[3,5,7,11,13,17]. Source and input were banked before one compiler execution. A separate fresh module instance then opened the saved construction JSON and produced 43 individually banked responses. No compiler or reader replay occurred, and no output was lost.

## Modular certificate

For a cycle entry R=a^n mod p², store
u_plus=(R+1) mod p² and u_minus=(R−1) mod p².
A sign is excluded precisely when its u is nonzero and divisible by p. Then the underlying positive integer has residue divisible by p but nonzero modulo p², proving v_p=1. The reader supplies p, p², the exponent's phase in the saved cycle, R and u. It does not materialize a^n±1.

The compiler starts at R=1, records every phase 0..p(p−1)−1, and advances by R←aR mod p². It requires the final residue to be 1. This checks the stated finite cycle closure during its one construction. That closure does not establish primality of an arbitrary supplied p; the mathematical prime premise remains explicit.

The complete actual cycles have lengths 6,20,42,110,156,272, totalling 606 entries. Each entry is [power residue, plus shifted residue, minus shifted residue, two-bit exclusion mask]. The final power residue is saved separately for all six cycles.

## Independent coordinates and exact suffix counts

Write an exponent phase as n=b+240t, with 0≤b<240. For p=3 and p=5, the valid cycle periods 6 and 20 divide 240, so their flags depend only on b.

For p in {7,11,13,17}, p−1 divides 240 while p does not. Therefore 240(t−t') is divisible by p(p−1) if and only if t−t' is divisible by p. The local flag for this prime depends exactly on b and the single coordinate t mod p. The four coordinates are independent by the Chinese remainder theorem.

Let T=7·11·13·17=17,017. Every coordinate tuple selects one t modulo T and, for each b, one exponent phase modulo P=240T. These B times T choices exhaust the 4,084,080 phases exactly once. P is a valid combined period; least-period optimality is not claimed.

The saved CRT coefficients are:

| Coordinate prime | T/p | Inverse of T/p modulo p | Coefficient |
|---:|---:|---:|---:|
| 7 | 2,431 | 4 | 9,724 |
| 11 | 1,547 | 8 | 12,376 |
| 13 | 1,309 | 3 | 3,927 |
| 17 | 1,001 | 8 | 8,008 |

For coordinates r_i, t is the least nonnegative residue of the sum r_i·coefficient_i modulo T. These coefficients are new finite arithmetic for this index.

A base row records the OR of the fixed-prime flags and every flag for each possible outer-prime coordinate. Let S(j,m,c) count completions from coordinate j onward, with accumulated mask m and final target c. At the terminal coordinate, S(d,m,c)=1 if m=c and zero otherwise. The recurrence is
S(j,m,c)=sum_r S(j+1, m OR flag(j,r), c).
Each coordinate value is a disjoint choice, so the sum counts exactly. The base-row count for c is S(0,base_mask,c). Summing over b gives the four full-period totals.

The compiler retains all flags and all suffix coefficients. It does not enumerate all CRT tuples or all global exponent phases. The last total-count comparison checks that the four classes sum to P; this is part of the once-only construction, not a later validation rerun.

Actual work:
606 modular multiplications and cycle entries; six cycle closures; 480 fixed-prime phase lookups; 11,520 coordinate-flag cells; 19,200 suffix cells; 184,320 suffix additions; four CRT inverses. New primality tests and globally enumerated exponent phases are zero.

## Rank order and positive exponent convention

Rank is not increasing numeric exponent order. The order is:

1. Positive period block (kP,(k+1)P], for k≥0.
2. Base phase b=0,...,239.
3. Lexicographic residues (t mod 7,t mod 11,t mod 13,t mod 17).

Within one class, the suffix counts skip coordinate branches. Cumulative base-row counts select b. A global rank divides into period-block number and rank within that block, since every positive block has the same class count.

The zero exponent phase represents the right endpoint (k+1)P of its positive block. Every other phase represents kP+phase. Conversely, for a positive exponent n, its block is floor((n−1)/P), its phase is n mod P, b is phase mod 240, and t=(phase−b)/240. This is a bijection between positive exponents and the declared ordered coordinates.

In particular, class 0 rank 0 is exponent P=4,084,080, not the least numeric exponent passing both local screens. The phase-zero tuple comes first in coordinate order. Numeric predecessor/successor, numeric interval counts, and numeric-order ranks are not provided by this API.

For any positive integer j, exponent n=jP has a^n≡1 modulo every selected p². Then a^n−1 is zero modulo those squares, and a^n+1≡2, so no selected odd prime gives valuation one. Thus infinitely many exponents pass both finite screens. This is a limitation of finite selected-prime exclusion, not evidence that the associated values are powerful.

## Saved consumer

The 43-response reader opens the complete production JSON without calling buildIndex. It exercises full-cycle and base-row views, direct exponent witnesses, all four class rank spaces, pages crossing a positive-period boundary and huge positive exponents.

For n=14 it returns class 3. The minus witness is p=3 with 2^14≡4 modulo 9 and shifted residue 3. The plus witness is p=5 with power residue 9 modulo 25 and shifted residue 10. Both shifted residues have exactly the required local divisibility. This example was selected as a finite query, not taken from a primary-source numerical table.

For every class, first/middle/last selections and their inverse ranks are retained. Representative middle selections are:
class 0, rank 39816 → exponent 2042040;
class 1, rank 709392 → exponent 121;
class 2, rank 579600 → exponent 120;
class 3, rank 713232 → exponent 122.
Their nonmonotone exponent values illustrate the coordinate order.

Thirteen stored selection/inverse-rank pairs match. A four-element class-0 page starts two ranks before the end of its first period block and crosses into the next block. The saved response names every selected exponent and coordinate tuple.

For n=10^1000+2197, the reader returns phase 3375557 and class 1. The retained plus witness is p=3, cycle phase 5, power residue 5 modulo 9 and shifted residue 6. The minus sign is not excluded by this finite list; it is not certified powerful. Adding P·10^200 preserves the class and all modular witnesses. The saved rank changes by 1418784·10^200, as required by the period-block order. A separate class-1 selection at rank 10^1000+14 has its inverse rank and modular witness response retained.

The huge exponents are decimal inputs, not lengths of expanded powers. No 2^n value is constructed. Query work is explicit: 30 saved-cycle lookups, 838 coordinate-flag lookups, 682 suffix-count lookups, 158 base-prefix binary steps and 80 CRT arithmetic terms. New modular-power steps, suffix cells and globally enumerated exponents are zero. CRT reconstruction and BigInt division remain fresh query arithmetic.

## API and limits

The dependency-free CommonJS module exports SCHEMA, LIMITS, buildIndex(input), openIndex(index).

Input:
base is an integer in [2,10^6];
base_period is an integer in [1,4096];
primes is an increasing list of 1..8 identified odd primes at most 97, each coprime to base;
provenance is required metadata.

For each supplied p, either p(p−1) must divide base_period (a fixed prime), or p−1 must divide base_period and p must be coprime to base_period (an independent outer coordinate). Other configurations are rejected. The outer coordinate moduli must be pairwise coprime. Counts and CRT arithmetic use BigInt.

Resource limits are two million coordinate-flag cells and one million suffix cells. A failed resource guard stops construction. The actual six-prime base-two consumer is the only compiler execution here. Other allowed parameter combinations were source-inspected, not run as extra examples.

The saved file wraps the index. Open it as:

const reader = openIndex(JSON.parse(dataText).index);

Opening copies the data and checks schema, basic period relationships, cycle dimensions/residue ranges, coordinate dimensions and suffix array shape. It does not recompute power cycles, verify primality, rerun suffix recurrences, audit the CRT inverse equations, or authenticate provenance. It performs no file-hash check internally. A structurally loadable arbitrary file is not thereby a mathematical certificate.

Methods:

- summary(): full class counts, marginal exclusion totals, ordering and build counters.
- cycle(prime): the complete retained cycle for one supplied prime.
- phase(b): the complete fixed-base row, flags and suffix counts.
- point(n): class and all selected-prime modular witnesses for one positive exponent.
- select(mask,rank): global coordinate-order selection within exactly one of masks 0,1,2,3.
- rank(n): class and global coordinate-order rank of one positive exponent.
- page(mask,start,count): at most 64 consecutive ranks, possibly crossing period blocks.
- work(): current query counters without incrementing query count.

Inputs n and rank are canonical decimal strings with at most 2,048 digits. Exponents must be strictly positive; zero, negative strings, leading zeros and signs are rejected. Ranks are nonnegative. A selected exponent exceeding the same decimal budget is rejected rather than returning an output that cannot be fed back into rank. The BigInt coordinate arithmetic itself remains exact.

Class 0 means neither sign has a selected-prime witness; masks 1 and 2 are the exact one-sign-only classes; mask 3 means both excluded. Selecting an empty class throws. Marginal “plus excluded” is the disjoint union of classes 1 and 3, and marginal “minus excluded” is classes 2 and 3. The API ranks exact classes and does not conflate these unions with single classes.

No natural numeric interval-navigation method is promised. The finite period counts may be written as exact fractions count/P for their local-screen densities, but they are not densities of powerful values.

## Source and data identities

- Executed module: 8ac72d0c76aedc1e728a954fb7a78e67136ce1c0, 10,187 bytes.
- Exact input: d54fbea3e80e0d1a84fda83f3e8d570cfa096ef9, 896 bytes.
- Complete production JSON: 1c8e063e1463934d262e29071abd1028391d1b68, 171,331 bytes.
- Complete saved reader: 0cd36c44a2a26669fd66d7be5e84bb18d284194f, 50,660 bytes.

The production file includes the full input, all six cycles, every base row and suffix coefficient, all CRT coefficients and cumulative class counts. The reader file includes every response and each separately banked response identity. No partial excerpt is described as a full dataset.

The general eventual-nonpowerful questions, local mathematical definition, accepted prime premise, new finite construction and saved query behavior remain distinct. No sponsor contact or submission occurred.
