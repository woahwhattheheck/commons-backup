# Contiguous least-common-multiple windows

This module represents every nonempty contiguous window of an identified finite increasing sequence, then answers exact LCM, strict-threshold, length-profile and count/rank/select queries from saved endpoint runs. The actual 16,384 values are the positive products of the accepted primes through 17, with each exponent between zero and three. Their 134,225,920 contiguous windows are represented by 100,848 complete run records.

At threshold 10^9, exactly 15,614 windows have LCM strictly below the threshold. There are 818 length-three windows and 67 length-fourteen windows. The complete saved profile contains every length from 1 through 16,384. Its last nonzero entry is length 68 with count one. These are finite-prefix results for this supplied sequence, not a bound for arbitrary infinite increasing sequences.

## Primary conventions and the separate question

Beachy and Blair's author-hosted *Abstract Algebra*, second-edition excerpt, Definition 1.2.8, defines the positive least common multiple as a common multiple dividing every common multiple. Proposition 1.2.9 describes two positive integers on a common prime list and gives the LCM exponent as the maximum of the two exponents. Missing prime factors have exponent zero; the positive integer one is permitted. Iterating this binary rule gives the maximum exponent over any nonempty finite family.

Primary locator:
https://faculty.niu.edu/math_beachy/aaol/integers.shtml

The exact consecutive-window formulation here is bound to the separately read FormalConjectures/ErdosProblems/873.lean, blob 377a2d01de3e10c275b085adbd6d80e46fb64b80:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/873.lean

For a strictly increasing positive infinite sequence, its F(a,X,k) counts starts i for which lcm(a_i,...,a_(i+k−1))<X. Its main research-open statement quantifies over every such sequence and every positive epsilon, then asks for a k controlling every positive X. The source separately marks triple upper and infinitely-often lower bounds solved, and marks an all-scale lower-bound supplement false/solved. Local proofs remain placeholders and the external proof link was not opened or reviewed. No independent original-paper passage for the consecutive-window question was retrieved. The formal file is the explicit statement/status custody; the algebra source supports the finite LCM convention only.

This API uses positive finite values, zero-based starts, strictly positive window lengths and only windows fully contained in the finite input. It excludes empty windows. Queries accept exact rational thresholds, a subclass of the real thresholds in the infinite problem. Finite exhaustion cannot establish the original quantifiers or an asymptotic theorem, and an eventually empty finite length profile is not evidence for the required infinite-sequence statement. No new record, prize result or sponsor submission is claimed.

## Exact inherited input

The input uses only sorted n values and exponent codes from accepted #31649:

- Merge: 0e4428eaef33d6c06bace7c5b1dc0d96f15f6496.
- Original manifest: research/erdos828_totient_shifts/primes17_cap3_index.json.
- Manifest blob: 06d71f61df8e7913a2131bcad12a9b229c452a35.
- Eight source row-file identities are copied into the present provenance.
- The consumed row fields are n and exponent_code. Totients, residue classes, periods and query results are not inputs to this calculation.
- Prime list: [2,3,5,7,11,13,17], caps [3,3,3,3,3,3,3].
- Codes use radices cap+1, with the first prime as the least significant coordinate.

The input contains one occurrence of every exponent code 0..16383, sorted by its already-saved positive n value. The first is (1,0), the last is (133049351085651000,16383). The code/product relationship and primality are accepted premises. Structural uniqueness and increasing-value checks do not reprove them. The new constructor does not multiply prime powers, factor n, compute phi, test primes, or repeat the earlier CRT/totient/kernel work.

For generic use the constructor requires a complete identified exponent box, not an arbitrary sparse subsequence: every exponent code must occur once. This makes the family closed under coordinatewise maximum and allows every LCM value to be looked up among accepted products. It is an input contract, not a claim that all increasing integer sequences have this form.

## Complete endpoint-run construction

For a fixed start i, as the inclusive end j advances, every prime exponent of the window LCM can only increase. A run [lo,hi,code] records that every end j in that interval has the same maximum exponent vector.

Process starts from right to left. For the final start, the only run is its singleton. If the complete runs for i+1 are known, prepend the singleton ending at i. For every old run, join its exponent code with that of the value at i, using coordinatewise maximum. The old end interval stays unchanged. Consecutive intervals with equal resulting codes are coalesced.

Inductively, the old runs partition every end from i+1 through N−1, and joining adds exactly the missing first value to every window. The singleton supplies end i. Thus the new runs cover every permitted end exactly once, with the correct LCM code. Coalescing equal adjacent codes changes no window or value. This proves complete coverage for every start.

Each change raises at least one integer coordinate. There are at most 1+sum(caps) runs per start, and often fewer because a start already carries positive exponents. For this seven-coordinate cap-three box the bound is 22; the actual maximum is 22. The general total-run cap remains a separate resource guard.

Joining exponents produces a code already present in the complete input box. The module reads its saved n value. It performs no new multiplication to reconstruct that product. Its code decoding and maximum operations are new construction work, not factorization.

Actual once-only work:

| Quantity | Value |
|---|---:|
| Input values / decoded exponent codes | 16,384 |
| Exponent digits decoded | 114,688 |
| Coordinatewise join calls | 100,826 |
| Coordinate maxima | 705,782 |
| Coalesced adjacent runs | 16,362 |
| Emitted complete run records | 100,848 |
| Nonempty represented windows | 134,225,920 |
| Maximum runs at any start | 22 |
| New products, factorizations, totients or prime tests | 0 |

The source and exact input were banked before that build. All run records are saved. Counters describe executed operations; transient join events are not claimed as individually retained records.

## Exact threshold and navigation formulas

A threshold is a pair (p,q), where p is a signed integer and q a positive integer. The test is q*LCM<p. This preserves the strict inequality with integer arithmetic, including equality, negative p and very large decimal numerators or denominators. Threshold fractions need not be reduced.

For a run with start i, end interval [lo,hi] and saved LCM value v, intersect the interval with [i+length_min−1, i+length_max−1]. If the interval is nonempty and q*v<p, it contributes its number of integer endpoints. Start restrictions simply select which starts' runs are scanned. A retained condition member therefore represents a consecutive set of admitted endpoints for one start and one LCM.

Members are ordered by increasing start, then increasing end. Their cumulative endpoint counts give a finite exact rank space. Selection binary-searches the cumulative total and offsets the chosen member's first end; ranking locates the containing member and adds the endpoint offset. Different starts or ends are different windows even if their entries have the same LCM.

For a length profile, each condition member contributes one window at every length from lo−i+1 through hi−i+1. Two difference-array updates and a prefix sum produce the count for every length. This is new query arithmetic using saved runs, not a repeat of exponent joins. For the unconstrained-start, unconstrained-length condition, the result is the exact finite-prefix counterpart of F(a,X,k).

All counts and ranks use BigInt and decimal strings. Source positions and bounded run IDs use safe integers. No floating point approximation is used for thresholds or LCM values.

## Complete fresh-reader evidence

A fresh module instance opened the serialized manifest and all twenty-five complete run files. It did not call buildIndex. Thirty-four responses, including the complete ten-condition cache response, were individually banked. No response was lost. The complete reader checkpoint was subsequently split by serialization only into a compact manifest and four member files.

The strict threshold X=10^9 gives 15,614 windows, represented by 13,354 admitted run slices. The full saved length profile starts:

| Length | Count |
|---:|---:|
| 1 | 9,253 |
| 2 | 2,347 |
| 3 | 818 |
| 4 | 435 |
| 7 | 151 |
| 14 | 67 |
| 20 | 49 |
| 68 | 1 |
| 69 through 16,384 | 0 |

The sum of all saved profile counts is 15,614. The separate fixed-length condition results agree with the corresponding saved profile entries. These are comparisons of retained outputs, not rerun queries.

The last length-three selection has rank 817, start 2484 and end 2486, with LCM 300179880. The middle length-fourteen selection has rank 33, start 33 and end 46, with LCM 643242600. Their inverse ranks are retained. The start-limited query 100≤start≤999, lengths 2..13 and X=10^9 has 2,299 windows; its middle rank 1149 is [369,370], with LCM 346500. All three selection/inverse-rank pairs match.

The first triple [1,2,3] has LCM 6. With length fixed at three, threshold 6 admits no window; thresholds 7 and 13/2 each admit exactly that first window. This preserves strictness instead of silently treating < as ≤.

Direct saved lookups include the full length-16384 window and its last singleton; both have LCM 133049351085651000. At start 8192 and length 14, the LCM is also that maximum. The first fourteen values have LCM 360360. A fixed full-length query at threshold 10^1000 has exactly one result and selects the entire input; the threshold arithmetic is new query work, not generation of a longer sequence.

Fixed length 1024 at threshold 10^9 and length 16385 (larger than the input) each return zero. A repeated identical length-three condition reuses its reader cache.

Actual reader work:
917,846 run scans; 204,155 exact threshold comparisons; 16,235 conditional cumulative additions; 124 selection steps; 19 direct-window binary-search steps; 1,759 inverse-rank member checks; 26,708 length-profile difference updates and 16,384 prefix additions. One condition cache hit is recorded. New exponent joins, new LCM run records and new product values are zero. “No construction replay” does not mean no fresh arithmetic.

All ten caches and their 16,235 member records are retained. Profile output includes all 16,384 length rows, not an excerpt. Pages and individual selections are exactly the outputs named in the reader manifest; no full list of all 15,614 admitted windows was separately exported.

## Module contract

The dependency-free CommonJS source exports:
SCHEMA, SHARD, LIMITS, buildIndex(input), openIndex(index,shards).

Input fields:

- primes: 1..8 increasing supplied prime bases, structurally bounded between 2 and 1,000,000. Primality is a premise, not tested.
- caps: matching integer exponent caps between 0 and 12.
- values: complete [positive decimal n, exponent_code] rows in strictly increasing n order.
- provenance: identified source metadata. The code does not authenticate that metadata.

The product of radices must be at most 50,000 and equal the number of value rows. The full run cap is 1,000,000; a budget exception stops that build. The actual cap-three/seven-prime input fits the stronger mathematical bound of 22 runs per start. Other admitted inputs were source-inspected only and were not executed as extra examples.

buildIndex returns {index,shards}. Shards have at most 4,096 rows. The index includes the complete values, per-start row pointers, source ordering, construction counters and row-shard ranges. A row is [start,minimum_end,maximum_end,exponent_code]. All starts and ends are zero-based and inclusive.

To open the published index:

const reader = openIndex(
  manifest.index,
  manifest.row_files.map(ref => parsedFiles[ref.file])
);

The caller supplies full parsed files. Opening checks the schema, strictly increasing values, unique complete code positions, contiguous shard ranges, and exact endpoint coverage for every start. These are structural checks. It does not repeat exponent joins, verify supplied products, prove maximal coalescing, or audit completeness/provenance of a claimed mathematical input. It does not hash files internally; manifest blob pins are for independent transport verification.

Reader methods:

- summary(): dimensions, complete construction counters and ordering.
- sourceValue(position): the retained [n,code] input row.
- run(row): a complete stored endpoint-run record with its LCM value.
- window(start,length): exact LCM for one fully contained nonempty window, using a binary search among that start's runs.
- condition(spec): create/reuse a strict-threshold condition and return its ID, count and number of retained member slices.
- select(conditionID,rank): zero-based selection in increasing-start/increasing-end order.
- rank(conditionID,start,end): inverse rank, or null for a valid but nonmember window.
- page(conditionID,startRank,count): at most 64 consecutive selections.
- lengthProfile(conditionID): full [length,count] rows for 1..N, respecting all restrictions in that condition.
- caches(): complete current condition metadata and member arrays.
- work(): counters without incrementing the query count.

A condition has threshold:{numerator,denominator}. Optional start_min/start_max default to the complete input. Optional length_min/length_max default to 1..N. Length bounds may be as high as 1,000,000; a range beyond the finite input yields an empty family. Bounds must be ordered. Direct window() instead requires containment and rejects an overlong length.

Numerators are canonical signed decimal strings, denominator canonical positive decimal strings, each with at most 2,048 magnitude digits. Negative zero and leading zeros are rejected. Equivalent unreduced fractions are mathematically equal but do not share a cache unless their input strings match. Rank strings are canonical nonnegative decimal, at most 100 digits. A page may start at exactly the count and return empty. Out-of-range selection throws.

A reader holds at most twelve conditions and 1,500,000 condition-member records. A new condition scans the selected starts' saved runs; exact repeated conditions reuse their cache. Saved cache files document this actual session. openIndex begins an empty runtime cache and does not silently preload those saved conditions, so new calls may legitimately perform fresh scans.

Condition members are [start,minimum_end,maximum_end,code,cumulative_count]. Published member shards prepend the condition ID. Concatenating those shards in start order and distributing by condition ID reconstructs the full saved cache without executing any query.

## Source identities and complete files

Executed source: c89e716c7babe33dcb0ee5532bae2a0975ecb0e4 (9,901 bytes).
Exact input: 0d54c826a0fe68b56ab143802c8080ed173c99f5 (319,087 bytes).
Complete once-only production checkpoint: 6378a8352b96b02e88ecf72a4eea218aa194bcf9.
Construction manifest: 6420791a9d516d57771efa180b355cbc15879542.
Initial complete reader checkpoint: 8bf6eea53923269b7b8ad14165d50269c5d5cd18.
Published compact reader: a9ab13a66a2ddf9dde5f49b6b86ea57b502602ed.

All source, input, construction and response bytes were banked before publication. Splitting the unchanged saved arrays into files was serialization, not a second calculation. There was one build and one fresh reader session.

| Complete file | Git blob |
|---|---|
| `lcm_runs_000000_004095.json` | `9730295945183bbb37154e041f7dd51efd65e48f` |
| `lcm_runs_004096_008191.json` | `29b65924019e79e82dd5f1064b0f93fae748d614` |
| `lcm_runs_008192_012287.json` | `7ba0093f5875e39f72d5ffe687e4805a8d62c768` |
| `lcm_runs_012288_016383.json` | `e788a658eb397edc6384b2198b7307b92745b9cb` |
| `lcm_runs_016384_020479.json` | `e893916aafd1cca041967062a480277728f4d643` |
| `lcm_runs_020480_024575.json` | `692f2618deec0938b5f8d3ec3eb35db5a18ccfc5` |
| `lcm_runs_024576_028671.json` | `20266280dad7f93c63c61f4576a84629f0fa5799` |
| `lcm_runs_028672_032767.json` | `12f52ff64bf414e876cc11d3beaccc4f4bc9710d` |
| `lcm_runs_032768_036863.json` | `ef74c80ea5d17d7c7b429e61d010ed12b4083607` |
| `lcm_runs_036864_040959.json` | `6ccd15d76fcc308b0325d0fde6489d689c8953fa` |
| `lcm_runs_040960_045055.json` | `a33cfc632fd8785a0577833f3fb3e9dc2a545fd8` |
| `lcm_runs_045056_049151.json` | `e9d8a534555e24f5675ddd3f748222d2fb21d01e` |
| `lcm_runs_049152_053247.json` | `9c0c251ff57e5300c842e7293c022f749d3456cc` |
| `lcm_runs_053248_057343.json` | `4844169ad678f16cd0bd6b3316f39a062420515e` |
| `lcm_runs_057344_061439.json` | `6e7e6c61f392b219407fec3186e9100e3da1c46b` |
| `lcm_runs_061440_065535.json` | `c051f6548dbf5f7d41580492576d8ef0983c9ae8` |
| `lcm_runs_065536_069631.json` | `bad4616d663634ca3990aa2a876a6be7f73dd4d0` |
| `lcm_runs_069632_073727.json` | `3ded38301cf99b52588816312e20d1dd4f2cb7bc` |
| `lcm_runs_073728_077823.json` | `a29dd1e0917edcadc0d2bbd9e5a966cb11742d36` |
| `lcm_runs_077824_081919.json` | `5e426e52d88dd00a8cefc9727f77634a0fdf5750` |
| `lcm_runs_081920_086015.json` | `aa9355e47200b88eec40e9aecd6ce008b88245fe` |
| `lcm_runs_086016_090111.json` | `bc8c64b63dbcdf8d8644bc3be933b13405fcf776` |
| `lcm_runs_090112_094207.json` | `2ba28e4983cecbf66f5eb23f67a5ca8b02429aaf` |
| `lcm_runs_094208_098303.json` | `b3629b372f43c6188736a6d4ff64be0ac799a58b` |
| `lcm_runs_098304_100847.json` | `998daabc86025d741a39e9d89050fe7934e432ff` |
| `smooth_lcm_windows.json` | `6420791a9d516d57771efa180b355cbc15879542` |
| `condition_members_00000_04095.json` | `6c0d19041fd9cd2515c99104e47131e6a287984d` |
| `condition_members_04096_08191.json` | `cdaeca51e69530968d55d354e5d19d07470554f7` |
| `condition_members_08192_12287.json` | `fbfc9bc690113c53f6ce0181efebbe0d172956ec` |
| `condition_members_12288_16234.json` | `929001de11c4f162756963058e7709c6bcd1ee57` |
| `saved_reader_queries.json` | `a9ab13a66a2ddf9dde5f49b6b86ea57b502602ed` |

These exact finite artifacts, imported source premises and status annotations have separate roles. No accepted calculation, external proof or sponsor process was replayed.
