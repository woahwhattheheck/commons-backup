# Totient divisibility over a finite smooth family

This module indexes positive integers n from a fixed finite prime-exponent box and answers exact queries about phi(n) dividing n+a, where a may be any signed integer within the declared digit cap. Its parameter windows count pairs (n,a), keeping different n distinct even when they share the same a.

The actual family has 16,384 members: n=product p^e for p in {2,3,5,7,11,13,17} and every exponent e in {0,1,2,3}. The maximum is 133049351085651000. This is a finite set of n. Allowing arbitrarily large query shifts does not make it a proof of infinitely many n for any fixed shift.

## Source conventions and boundaries

NIST's Digital Library of Mathematical Functions, Section 27.3, treats Euler's totient as multiplicative on positive integers with phi(1)=1. Equation 27.3.3 gives
phi(n)=n product_(p|n) (1-1/p),
with the product over distinct prime divisors. The empty product at n=1 agrees with phi(1)=1.

Actually read primary locators:
- https://dlmf.nist.gov/27.3
- https://dlmf.nist.gov/27.3.E3

The exact current FormalConjectures source is FormalConjectures/ErdosProblems/828.lean, blob **67ad26faef60756f7a81b51a2608426e016fb138**. It asks whether every integer a has infinitely many natural numbers n with phi(n) dividing n+a. Its main assertion and the separate Lehmer variant are annotated research open; its phi(n)|n characterization is separately tagged textbook. The local theorem bodies are placeholders and the linked proof was not opened or reviewed. An independent historical primary account of the n+a question was not retrieved in the bounded lookup; the general-question statement here is bound to the actually read formal source.

The present API uses positive n only. It includes n=1 and excludes any formal-source n=0 convention. The formal Lehmer variant starts at n>1 and concerns phi(n)|n-1; none of this package's finite observations resolve it. Divisibility is over integers, so negative n+a is allowed and the quotient witness may be negative.

The unbounded direction is explicit: the API varies a over signed parameters while n remains in a fixed finite box. The conjecture instead fixes each a and asks for infinitely many n. A window count below is a count of incidence pairs, not a deduplicated count of shift values and not a global solution-count asymptotic.

## Accepted prime input, new work and execution custody

Only seven identified input values are consumed from accepted Commons PR #31519:
research/ppl137_residue_coverings/primes_through17.json,
blob **18c48c14b2da0777caed5c8ff7df0d68024867e9**,
field input.moduli = [2,3,5,7,11,13,17].

That input explicitly identifies the first seven primes. Its old residue sieve, CRT phases, Jacobsthal gaps, coverage computation and queries were not replayed. This implementation performs no primality tests. All totient interpretations remain conditional on that identified prime premise. For generic inputs the caller must supply known distinct primes and an explicit provenance string; structural range checks are not a primality certificate.

The new exponent caps are all three. The source blob **1b9e99bb1e9b4da0b300e6a219492fb63ac52536** and exact input blob **c0c1c0c1397183aaf8ccaf4072b483f1b2b28062** were banked before the one production build. It forms new prime-power/totient tables, finite products and shift classes. It does not repeat the accepted calculation.

The initial full construction checkpoint is blob **6bdfa8fdaa3b7bc435272a42abb02e845dfbcdf5** (1,572,906 UTF-8 bytes). For publication, its complete class array was split into eight kernel files; its rows already occupy eight row files. This was a serialization of retained values, not a mathematical recomputation. The published manifest is **06d71f61df8e7913a2131bcad12a9b229c452a35** and retains the original checkpoint identity.

The fresh reader assembled the index from that exact manifest and all sixteen complete saved files. Every output was retained before the next query. The published query file embeds the whole final cache response, rather than requiring ten tiny response-member files. Its initial reader checkpoint is recorded for lineage; embedding retained responses did not run any query again. There are no missing ephemeral responses in this consumer and no post-build implementation change.

## Exact construction and finite proof

For each identified prime p and exponent e, save
p^e and phi(p^e) = 1 if e=0, otherwise p^(e-1)(p-1).
Unique prime factorization makes distinct exponent tuples distinct positive n. The totient product formula then gives
n=product p_i^e_i and phi(n)=product phi(p_i^e_i).

The recursive construction independently chooses each exponent in its declared range and visits every tuple once. It sorts resulting rows by increasing n. In the actual seven-factor box, there are 4^7=16,384 rows.

For each row set m=phi(n)>0 and r=(-n) mod m, with 0<=r<m. Then
phi(n) | n+a if and only if a is congruent to r modulo m.
Rows with the same (m,r) share a class. They are still different n and each contributes separately to incidence counts. The actual data have 16,375 classes. For example n=1 and n=2 both have phi(n)=1, so both satisfy the divisibility relation for every shift; neither is silently discarded.

Let N_max=product p_i^cap_i and P=phi(N_max). For any allowed e_i, phi(p_i^e_i) divides phi(p_i^cap_i): it is 1 at exponent zero, and otherwise the only varying factor is a nondecreasing power of p_i. Taking products proves phi(n)|P for every row. Thus P is a common period in a for the entire finite family. This proof does not claim that P is the least period.

In the actual data:
- N_max = 133049351085651000.
- P = 24018781602816000.
- Across a=0,...,P-1, the number of incidence pairs (n,a) is 229579205656252023.
- The mean number of matching n over this parameter period is exactly 105991218763/11088896000.

Indeed each row contributes P/phi(n) shifts in a complete period. The saved class multiplicities account for every n, and summing their contributions gives the numerator above. The reduced mean is this finite periodic average. It is not a density over an unbounded family of n.

The actual build counters are 28 prime-power table rows, 21,845 recursive search nodes, 43,688 product multiplications, 16,384 new product rows and residue reductions, and 16,375 class records and period quotients. The prime-test counter is zero. Recursive-node and operation counters do not claim separate storage of every transient event; all terminal products, tables and classes are retained.

## Storage and assembly

Each row is:
[n_decimal, phi_decimal, least_nonnegative_residue_decimal, exponent_code, class_id].

The exponent code is mixed-radix with prime 0 least significant and radix cap_i+1. Rows themselves are ordered numerically by n, not by this code. All integer magnitudes that may exceed safe JavaScript precision are stored as canonical decimal strings and computed with BigInt.

Each kernel class retains its positive modulus, least residue, every associated row identifier, and occurrences_per_period=P/modulus. Class order is the order in which classes are first encountered while scanning increasing n.

The small manifest contains input/source identities, prime-power tables, exact period and aggregate counts, complete file identities and the index fields other than its split classes array. Before openIndex, concatenate the classes arrays from kernel_files in listed order into index.classes. Pass the parsed row_files in listed order as the second argument. This assembly copies stored arrays only; it does not reconstruct products, totients or congruence classes.

| Complete data file | Blob | UTF-8 bytes |
| --- | --- | ---: |
| totient_rows_00000_02047.json | 6d1e511909e5965f3eff04ba6dbb90967ca104dc | 68210 |
| totient_rows_02048_04095.json | 5075fafac149ad18ce3168559b2bcf399d958cb2 | 81235 |
| totient_rows_04096_06143.json | 1ace59d1582d47551fdfd669696c6ac458cab04a | 88046 |
| totient_rows_06144_08191.json | a95fac7b72dcd6d9c1c8e6205454491948edeca5 | 93850 |
| totient_rows_08192_10239.json | 1495dd25106eb6ac266ab8658ad51b5cc928405c | 99499 |
| totient_rows_10240_12287.json | f4d1b8b29a152c1e9b090ef6c6751c80f57d47de | 106875 |
| totient_rows_12288_14335.json | ce19947b4ffe92e7a62432a234ebe1e99c7532f9 | 113519 |
| totient_rows_14336_16383.json | a3d87d3e7b9fd9f3d8f6aa3780212f21cc0b1743 | 125183 |
| kernel_classes_00000_02047.json | e31efaaf0815508a29680ed7e19d456c1ba8745d | 186058 |
| kernel_classes_02048_04095.json | d8cd12cdb0adb7a9ecf1d1ea2b9a6b87b02cb07e | 190989 |
| kernel_classes_04096_06143.json | 1e71b596ccf1b22e85b4519fc4a91b57c67b1d54 | 193025 |
| kernel_classes_06144_08191.json | 7298a3deb3c194f51fd8363c7d955d7a312333ee | 194893 |
| kernel_classes_08192_10239.json | 3fa5a3d208cafca2468e727fd569505c70a9579b | 196964 |
| kernel_classes_10240_12287.json | d84f345b88a19f3893ce3dd2ffaa6e58f2b2f780 | 200489 |
| kernel_classes_12288_14335.json | 5d206d9e3881ce18147cc8ff3fa0cb5164d75813 | 202491 |
| kernel_classes_14336_16374.json | 24a4bbd51b7da8acaa9d31b06a9b914402eb3ec5 | 205362 |

The row files cover 0 through 16,383; kernel files cover class identifiers 0 through 16,374. No publication file needs the original monolithic class array. Every value from that array is present in the complete kernel shards, with its order preserved.

## Exact point and parameter-window navigation

A point query first reduces a modulo P, then scans saved classes. Class (m,r) matches exactly when the reduced parameter is congruent to r modulo m. Its saved row identifiers are filtered by the optional n range and sorted. Equal phases with equal n ranges reuse this cached family, even when their unreduced parameters have thousands of digits.

Point ranks are zero-based in increasing n. Selection returns n, phi(n), the requested parameter and the exact signed quotient (n+a)/phi(n). Rank reverses the selected n's position in the cached list. A congruent parameter has the same admissible n but a different quotient witness; the latter arithmetic is performed for the actual requested parameter.

For an inclusive window [L,H], L<=H, a class (m,r) has first permitted parameter
first = r + m*ceil((L-r)/m).
If first>H its count is zero; otherwise it has
count = floor((H-first)/m)+1.
Floor and ceiling are mathematical signed operations. The code corrects BigInt truncation toward zero when needed, so negative window endpoints are handled exactly.

For each eligible n with positive class count, the window index stores a cumulative pair count. Window ordering is increasing n first, then increasing a within that n's residue class. Different n that share one a remain different pairs. Binary search of cumulative counts selects an n block; division-free offset arithmetic a=first+j*m selects its parameter. Ranking checks the chosen parameter's residue and window position and adds the preceding block count.

Counts over an astronomically long parameter window therefore use one exact class formula and one finite prefix sum per relevant record. The API never enumerates all shifts in that window.

## Public contract

Exports are SCHEMA, SHARD, LIMITS, buildIndex(input), openIndex(index, shards).

The constructor accepts 1 through 10 strictly increasing identified prime bases, each at most 1,000,000; exponent caps are integers from 0 through 8. The box has at most 100,000 rows. A nonempty prime_premise string records the caller's mathematical premise. The constructor checks structural bounds and ordering; it deliberately does not establish primality. Composite bases are outside the totient API contract even if they pass those structural checks.

The maximum generic product has at most 480 decimal digits, within the 2,048-digit input cap. Row shards have at most 2,048 rows. Generic kernel serialization may be split externally, as it is in this actual artifact.

The reader copies inputs and checks schema, shard spans, strictly increasing positive n, positive saved totients, residue ranges, identifier bounds, final row coverage and each listed class-to-row binding. These checks are structural consistency, not an independent proof of prime provenance, tuple exhaustiveness, totient values, period validity or completeness of every class list. Callers must bind the full file identities to the manifest; openIndex does not hash files, run primality tests or invoke the constructor.

| Method | Result |
| --- | --- |
| summary() | Finite family size, class count, maximum n, period and period pair statistics |
| row(i) | One saved product, totient, residue and identifiers |
| factorization(i) | Decoded prime-power factors and their saved totient factors |
| kernel(i) | One complete saved class |
| point(a, range) | Exact finite matching count and cache identity |
| pointSelect(a, rank, range) | One n with quotient witness |
| pointRank(a, n, range) | Rank of an admitted n |
| pointPage(a, start, count, range) | Up to 32 point-family members |
| window(L,H,range) | Pair count, admitted n count and tested class count |
| windowSelect(L,H,rank,range) | One pair and quotient witness |
| windowRank(L,H,n,a,range) | Inverse pair rank |
| windowPage(L,H,start,count,range) | Up to 32 pairs |
| caches() | Complete cached point and window records |
| work() | Named work counters |

factorization returns the prime-power factors of n and local phi(p^e) factors. A local p-1 may itself be composite; this method does not claim a fully prime-factored representation of phi(n).

range may contain only min_n and max_n, canonical decimal strings with 1<=min_n<=max_n<=N_max. Omitted endpoints mean 1 and N_max. The default family therefore includes n=1 and n=2. Required positivity and the maximum range are enforced.

Signed parameters/window endpoints are canonical decimal strings with at most 2,048 magnitude digits. "-0", leading zeros and malformed strings are rejected. Counts, totals and ranks are decimal strings. Negative ranks and ranks at or beyond the total are rejected; page start equal to the total returns an empty page. Pages are capped at 32 records. Row, class and exponent-code identifiers are bounded safe integers.

The reader caches at most 32 distinct point phases/ranges and eight exact windows/ranges. Its caches() result is complete evidence from the session. The present openIndex interface does not preload those cached results on a later opening: new queries scan the saved mathematical index and build their own reported finite cache. No query-cost-free restoration claim is made.

Example usage, shown without re-executing the actual consumer:

~~~javascript
const {openIndex} = require('./totient_shifts.cjs');
const manifest = /* parsed primes17_cap3_index.json */;
const kernelShards = /* parsed manifest.kernel_files */;
const rowShards = /* parsed manifest.row_files */;
const index = {...manifest.index,
  classes: kernelShards.flatMap(s => s.classes)};
const reader = openIndex(index, rowShards);
reader.point("1"); // five finite matches, including n=1
const range = {min_n:"2",max_n:"10000"};
const family = reader.window("-20","20",range); // total "340"
const pair = reader.windowSelect("-20","20","339",range);
reader.windowRank("-20","20",pair.n,pair.parameter,range);
~~~

## Actual retained reader results

The published saved_reader_queries.json is blob **67a02f786d1371fc85a4506bdf66abc6ba0c889e**. It contains 34 complete ordinary outputs and the full value of one caches() response, for 35 logical queries. That cache response has seven point entries and three complete windows, including every retained class count and cumulative block. Its original pre-bundling reader checkpoint is **0fedc354d41e8f90c261b22349f69c2c419ef5f0**. Bundling these existing records changed only storage format.

The complete point pages show:
- a=0: n in {1,2,4,6,8,12,18,24,36,54,72,108,216}, count 13.
- a=-1: n in {1,2,3,5,7,11,13,17}, count 8.
- a=1: n in {1,2,3,15,255}, count 5.
- At a=1 with min_n=2, the count is 4.

Those are exhaustive only in the specified exponent box. In particular the a=-1 list is not a proof of Lehmer's conjecture outside this finite family, and the a=0 list is not a new proof of the separately cited global characterization.

The reader also counts eight matches at a=2 and six each at a=5 and a=17. For a=1+P*10^1000 it reuses the phase-1 cache. All five quotient witnesses are retained; the last has n=255, phi(n)=128, a 1,017-digit parameter and a 1,015-digit quotient. This is fresh arithmetic on a selected huge parameter, not a totient or class recomputation.

For the restriction 2<=n<=10000:
- The inclusive window [-20,20] contains exactly 340 pairs, with 118 admitted n.
- The first is n=2,a=-20, quotient -18.
- The last is n=5100,a=20, phi(n)=1280, quotient 4.
- The inclusive window [10^40,10^40+10^25] contains exactly 84554615105186672910327581 pairs, using 635 admitted n.

The latter window's middle rank is 42277307552593336455163790. Its saved pair has n=15, phi(n)=8, and
a=10000000000000003551793754080024974643617.
The retained inverse rank agrees. The last pair has n=9996, phi(n)=2688, and
a=10000000000000009999999999999999999999860.
Its last rank is 84554615105186672910327580. The reader also returns a three-pair page starting at rank 10^25.

A third window restricts n to N_max alone and a to [0,100]; it has zero pairs. Empty windows over the finite family are supported without a fabricated selected witness.

The actual counters distinguish new query work:
- 16,384 saved rows indexed.
- 114,625 point-class scans across seven distinct cache keys.
- 51 point-row range checks.
- 49,152 row scans for three windows; 1,271 rows pass their n-range filters.
- 1,255 class counts, 1,996 signed window divisions and 753 cumulative additions.
- 135 selection/rank binary-search steps, 45 quotient witnesses and two exponent decodes.

The reader's counters for new primality tests, product rows, totients and kernel classes are all zero. These named counters do not claim to count every comparison, serialization operation or BigInt addition. Cache hits and the complete stored responses remain visible in the query file.

## Evidence ceiling

The prime values are an identified accepted input premise, not a new primality result. The constructor applies the classical product formula only within its declared finite box. The saved reader's structural checks are not a second proof audit.

The finite parameter period and exact pair counts concern the entire stated box, but say nothing about infinitely many additional n outside it. Repeated admissible shifts for a fixed n do not answer the question of infinitely many n for a fixed shift. All source status, historical attribution and finite arithmetic results are kept distinct; no current-frontier, novelty, prize or sponsor-submission claim is made.
