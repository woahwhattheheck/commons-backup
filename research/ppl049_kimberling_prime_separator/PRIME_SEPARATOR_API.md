# Prime separator continuation and saved-frontier API

The module continues Kimberling's prime separator array from an explicitly identified finite boundary prefix. It saves the product frontier, every new boundary choice, complete old-square absence certificates, and one proper product witness for each newly covered non-boundary value. A saved object supports another append and finite prime/gap navigation.

The actual input is the published 60-pair boundary prefix. One continuation adds indices 61–256; one fresh saved-state append adds 257–320. The final new value interval is 204–1,238, containing 157 primes, 878 composites and all 1,035 classification records. The largest first-row difference among the 260 new steps is 11, uniquely at index 96. This is a finite result; a uniform bound on all first-row gaps remains a separate question.

## 1. Sources and exact conventions

[Kimberling's section 12](https://faculty.evansville.edu/ck6/integer/unsolved.html) asks whether successive first-row differences are bounded. The operative construction is the FORMULA in [OEIS A129258](https://oeis.org/A129258), credited to Clark Kimberling. Write the first row as R and the first column as C, with R_1=C_1=1. The array cell is

\[
T(i,j)=C_iR_j.
\]

For the old square P_n={C_iR_j:1≤i,j≤n}, choose

\[
R_{n+1}=\operatorname{mex}_{>0}(P_n),\qquad
C_{n+1}=\operatorname{mex}_{>0}(P_n\cup\{R_{n+1}\}).
\]

Only afterward insert the new row and column products. The source formula and its listed program use this order.

The [A129259 b-file](https://oeis.org/A129259/b129259.txt) and [A129260 b-file](https://oeis.org/A129260/b129260.txt) each supply indices 1–60, explicitly synthesized from their published entries. They end at R_60=199 and C_60=203. The main entry's row/column designation fixes the orientation used here. Its separate 69-term antidiagonal table is not the square seed.

The recorded source prefix and the complete prime/least-factor basis from Commons PR31426 are mathematical input premises. This continuation does not regenerate the prefix, its product square, the prime sieve, or the earlier interspersion computation. Loading a saved state likewise checks its structure without authenticating those premises.

The primary sources identify the construction and the question. This artifact asserts no exhaustive literature census, new sequence term priority, external computational frontier, sponsor outcome or solution of the infinite gap question.

## 2. Coverage, ordering and finite bounds

For every correctly constructed stage n, P_n contains every positive integer at most C_n. This holds at n=1. At the next stage, R_(n+1) and C_(n+1) are the first two missing positive integers of P_n. Every smaller integer other than those two is already present. Inserting the two new boundaries includes both missing values because the opposite boundary contains 1. Therefore P_(n+1) contains every integer at most C_(n+1).

Since all integers through C_n are present before the next choice,

\[
C_n<R_{n+1}<C_{n+1}.
\]

For n≥2, R_n<C_n as well. Thus each boundary increases, the boundaries intersect only at their initial 1, and no later choice can duplicate a previous boundary value.

The set P_n has at most n² distinct values. Its first missing positive integer is at most n²+1, and its second is at most n²+2:

\[
R_{n+1}\le n^2+1,\qquad C_{n+1}\le n^2+2.
\]

These cardinality bounds justify the executable integer envelope. They do not give a constant bound on R_(n+1)−R_n.

The same coverage argument explains the source's prime separation property. The 2n−1 distinct boundary values imply C_n≥2n−1, so every positive integer eventually lies in a covered initial interval. If a prime is a product C_iR_j, one factor is 1; hence it occurs on one boundary. Boundary disjointness makes that side unique. This explanation follows from the stated construction and preserves the source's attribution. The finite API only indexes primes in its newly covered interval; it does not count or regenerate primes below the accepted seed endpoint.

## 3. Sorted product frontiers

Fix a first-row index j. Its product stream is

\[
R_jC_1<R_jC_2<\cdots<R_jC_n.
\]

This is the array column with fixed j. The implementation's historical field name `exhausted_rows` refers to first-row boundary indices j, not to geometric array row indices i.

At a stable stage, the cursor is v=C_n+1. Each stream has either:

- one heap node for its first product at least v, carrying that product and both boundary indices; or
- an exhausted marker if all currently available products are below v.

The initial seed needs one binary lower-bound search per stream. There is no loop over all n² seed pairs and no regeneration of the first n mex steps. Binary search does inspect the selected seed products needed to locate these new frontiers.

The heap is ordered by product, then first-row index, then first-column index. Its minimum is therefore the least still-relevant product in the entire old square.

### Finding the two missing values

At a candidate cursor v:

1. If the heap is empty or its minimum exceeds v, no old-square product equals v. The value is missing.
2. If its minimum equals v, retain one node as an explicit product witness. Pop every node whose product equals v, advancing each of those streams by one column position or marking it exhausted. Advance the cursor.
3. A heap value below the cursor violates the retained invariant and is rejected.

After finding the first missing value, the cursor advances once and scanning continues in the same old square. This skips exactly the first choice. The second missing value is therefore the mex of the old square together with that first choice. No new boundary enters the maps, streams or product set between these two choices.

Duplicate product representations are drained together. They exclude the integer once, while the work receipt records all encountered product hits. Only one explicit proper-factor witness is needed and retained for each covered integer; the artifact does not claim to retain every representation of that integer.

### Inserting the new boundaries

Once both absence certificates have been formed against the old maps:

- Each old active stream keeps its current node. When it eventually reaches the appended column index, the ordinary stream advance uses the new C value.
- Each old exhausted stream considers its newly available product with C_(n+1); it re-enters the heap only if that value is at least the new cursor.
- The new R_(n+1) stream is positioned by a binary lower-bound search in the now-extended C array.

The new cursor is C_(n+1)+1. These updates preserve exactly one active node or exhausted marker for every first-row index. A saved append reuses this state. It does not initialize the earlier streams again.

The new finite work is proportional to frontier setup, new stream placement, products actually drained, and output certificates. A heap update costs O(log N) at size at most N; binary placement costs O(log N). Across a continuation, each product position that is popped advances once. The method does not promise that all pair work disappears for arbitrary far extensions, nor that finite output remains small independently of the requested range.

## 4. Certificates and complete new-value classification

### Absence of a selected value

For either selected value v, the API factors v, enumerates every positive divisor d, and stores

\[
[d,\ v/d,\ \operatorname{index}_R(d),\ \operatorname{index}_C(v/d)].
\]

An absent membership is encoded by index 0. Both maps are still restricted to the old boundaries.

Every possible positive factorization v=R_jC_i appears in this ordered divisor list: choose d=R_j. Thus v is absent from the old square exactly when no row has both membership indices nonzero. The producer rejects such a simultaneous membership. This supplies a complete finite absence certificate, rather than just the assertion that the heap found no hit.

Prime-power factors determine the full divisor list by independent exponent choices. The certificate retains all factor powers and exact division steps, including repeated prime factors. In the actual continuation, every selected value lies inside the accepted least-factor table, so factorization uses direct recorded least-factor lookups. No trial-prime fallback or new primality sieve ran.

The general API also contains a bounded fallback for values above the table limit. It trial-divides by the supplied complete increasing prime basis. Each tested prime has a retained row containing its index, value, input remainder, removed exponent, resulting remainder and final modulus. A remaining factor is prime once the next basis prime exceeds its square root, or the complete basis already extends beyond that square root. This branch was source-inspected only in this artifact.

The prime status of a selected value follows from its complete factorization: exactly one prime power v^1 means prime. Divisibility checks on new candidates do not authenticate the accepted prime table.

### Proper products for covered values

A value scanned after C_n exceeds every old boundary value. If it is an old product R_jC_i, neither factor can be 1, since that would make the value at most C_n. Its retained witness therefore proves compositeness with two proper factors.

Every integer in the new interval (C_seed,C_final] is recorded once, in increasing order, as one of:

| Kind code | Meaning | Certificate |
|---|---|---|
| 0 | Already covered by the old square at that stage | One proper product with both old indices |
| 1 | Selected as a new first-row boundary | Complete old-square absence and factorization |
| 2 | Selected as a new first-column boundary | Complete old-square absence and factorization |

The raw record layout is

`[value, kind, first_row_index, first_column_index, stage_index]`.

For a product record, the array coordinate is `[first_column_index, first_row_index]`. A first-row choice at stage j has array coordinate `[1,j]`; a first-column choice at stage i has coordinate `[i,1]`. Indices are one-based. Prime navigation ranks and page offsets are zero-based.

This is a complete classification only for the newly covered finite interval. The seed boundary values are preserved, but primes through 203 are outside the new prime index.

## 5. Public API

The CommonJS file has no imports, I/O or provider calls. It exports:

- `continuePrimeSeparator(request)`;
- `openRetainedPrimeSeparator(snapshot)`;
- `PRIME_SEPARATOR_LIMITS`.

### Construct a new continuation

The request supplies:

```javascript
{
  source_id: "identifier-for-the-new-state",
  seed: {
    source_id: "identifier-for-the-accepted-prefix",
    first_row: [/* complete accepted boundary */],
    first_column: [/* matching complete accepted boundary */]
  },
  basis_source_id: "identifier-for-the-accepted-prime-basis",
  basis: {
    limit,
    primes,
    least_factor_by_integer
  },
  target_size,
  size_cap: 1024
}
```

Both boundaries begin with 1, have equal positive length, and satisfy the increasing/interlaced structural contract. The target must add at least one pair. `source_id` must differ from the seed identifier.

The basis contains every prime through `limit` and the complete least-factor table at indices 0 through `limit`, with endpoints 0 and 1. Completeness and primality are accepted mathematical premises; the constructor checks types, bounds, ordering and array sizes.

On success, the function returns `{status:"COMPLETE", index}`. A target exceeding the size cap returns `ABOVE_SIZE_CAP` with a null index. Other malformed inputs raise an error. A failure of a mathematical premise can raise an error while constructing a candidate; that failed candidate is not a certified saved state.

### Restore and append

Each data file includes a complete directly loadable `.snapshot`. A saved append uses:

```javascript
const index = openRetainedPrimeSeparator(saved.snapshot);
const result = index.appendThrough({
  target_size: 320,
  source_id: "identifier-for-the-appended-state"
});
const nextSnapshot = index.snapshot();
```

This is usage syntax. The actual saved append is already retained in `seed60_through320.json`; loading that final snapshot is sufficient for the reader operations below.

Appending changes the in-memory index, preserves the old source identifier as `parent_source_id`, and adds a segment recording exactly the new index/value range and work. It does not modify the caller's saved input object. Snapshot and query results are outward copies.

A target below the current size raises an error. An equal target returns `NO_NEW_INDICES` without mutation. Exceeding the size or segment cap returns `ABOVE_SIZE_CAP` or `SEGMENT_CAP` before mutation. Unexpected arithmetic or invalid-premise failures are errors; no rollback guarantee is made for an index whose append has thrown. Discard that failed in-memory candidate and retain the previously saved snapshot.

### Navigation methods

| Method | Meaning |
|---|---|
| `summary()` | Source lineage, endpoints, new-value counts, gap histogram and frontier sizes |
| `boundary(i)` | The i-th row/column pair, labelled accepted seed or new continuation |
| `eventAt(i)` | One new stage, both absence certificates and all classified records from that stage |
| `classifyNewValue(v)` | Exact new-interval classification and its product or absence/factor certificate |
| `countPrimesThrough(v)` | Count of indexed primes in (C_seed,min(v,C_final)] |
| `selectPrime(rank)` | The zero-based rank-th new prime, its side and boundary index |
| `rankPrime(v)` | Recover a new prime's rank, or report that it is not in this finite prime index |
| `pagePrimes(start,limit)` | Increasing-value page of new prime assignments |
| `pageRowGaps(start,limit)` | Page of new first-row steps, with previous value, new value and difference |
| `snapshot()` | Complete saved state, including frontiers and all prior continuation data |
| `work()` | Counters for the current invocation, separate from saved segment counters |

Prime ranks are local to the new interval. For example, rank 0 here is the first indexed prime above 203; it is not the prime's global index. A count with an upper bound below the seed endpoint is empty. A bound above the final endpoint clamps to the retained interval.

An out-of-range selection reports `OUT_OF_RANGE`. Classification outside the new interval reports `OUTSIDE_NEW_INTERVAL`. `NOT_IN_NEW_PRIME_INDEX` does not itself classify a value outside that interval. Pages permit an empty result past the end and report no continuation cursor.

## 6. Executable bounds and loader scope

The hard size cap is 1,024 boundary pairs; callers may choose a smaller cap. At the largest permitted size,

\[
R_N,C_N\le (1024-1)^2+2=1{,}046{,}531.
\]

Every product is at most the square of that bound, below 2^53. Boundary products, factor quotients, membership values and counts are therefore exact safe integers in the JavaScript Number representation. Integer-square-root results are corrected by exact neighboring-square comparisons.

The basis limit is at most 65,536 and must reach at least the floor square root of the cardinality bound for the chosen size cap. The retained basis has limit 16,384, 1,900 primes, and 16,385 least-factor entries. It is more than sufficient for the selected cap.

Other limits are 128 returned records per page, 32 saved append segments, and 1,024 characters per source identifier. Numeric inputs must be safe integers. No arbitrary-precision or unbounded-size contract is implied.

The loader copies the saved state and checks boundary order/range, source identities, array coverage, heap order, one stream marker per boundary index, contiguous classified values, event/index shape and summary dimensions. It does not recompute saved products, replay mex choices, factor old candidates, authenticate an OEIS prefix, establish prime-basis completeness or independently prove a saved certificate.

The current seed, factor-table route and new consumer are exercised. Other seeds, the trial-prime fallback, alternate cap/empty-page/error paths and future larger extensions have source inspection only. This distinction prevents the finite execution receipt from being mistaken for exhaustive behavioral testing.

## 7. Actual continuation and complete retained results

The source used by construction, append and final reader is the same file:

`f0681a124eacc8575f5a62780d80e3ec581161ca`.

No post-consumer source edit was made.

| Quantity | Initial continuation | Saved append only | Final retained continuation |
|---|---:|---:|---:|
| New boundary indices | 61–256 | 257–320 | 61–320 |
| New stages | 196 | 64 | 260 |
| Classified values | 204–974 | 975–1,238 | 204–1,238 |
| Number of values | 771 | 264 | 1,035 |
| Old-product composites | 379 | 136 | 515 |
| Selected composites | 274 | 89 | 363 |
| Primes | 118 | 39 | 157 |
| Primes assigned to first row | 51 | 21 | 72 |
| Primes assigned to first column | 67 | 18 | 85 |
| Final R value | 973 | 1,237 | 1,237 |
| Final C value | 974 | 1,238 | 1,238 |

The final frontier has cursor 1,239, 319 active streams, one exhausted stream and next heap product 1,240. These are saved frontier facts, not a computation of another boundary stage.

All 520 selected-value absence certificates, 2,975 ordered divisor-membership rows and 1,259 least-factor division steps are retained. There are 515 explicit proper-product witnesses and 1,035 complete classification records. All 260 new boundary pairs and all 260 gap records are present.

The new first-row gap distribution is:

| Gap | Number of new steps |
|---:|---:|
| 2 | 50 |
| 3 | 59 |
| 4 | 65 |
| 5 | 45 |
| 6 | 24 |
| 7 | 10 |
| 8 | 3 |
| 9 | 3 |
| 11 | 1 |

These steps are R_61−R_60 through R_320−R_319. The earlier seed gaps were not recomputed. The unique new maximum is R_96−R_95=343−332=11. The retained stage at index 96 covers 338–344, with old-product witnesses for 338–342 and missing-value certificates for 343=7³ and 344=2³·43. The preceding stage supplies the already covered integers through 337.

### Work and reuse

The initial consumer made one frontier initialization for 60 streams, 1,858 binary-search steps, 2,788 product evaluations and 479 product hits. Of those hits, 100 were additional representations of already-counted covered values. It used 959 least-factor lookups and 2,241 divisor-membership rows.

The append loaded 255 saved heap nodes, one exhausted marker, 196 prior events and 771 prior classified records. It initialized zero prior frontiers. The 64 new streams required 576 binary-search steps; the new work used 874 product evaluations, 170 hits including 34 additional representations, 300 least-factor lookups and 734 divisor-membership rows.

Both stages used zero new prime-sieve calls and zero trial-prime divisions. Loading the basis checked the shape of 16,385 retained entries; it did not prove them again.

Observed times were 6 ms for the initial continuation, 8 ms for the saved open and 2 ms for the append. These are single connected V8 observations, not statistical benchmarks or guaranteed performance.

### Fresh saved reader

A final fresh invocation loaded the index without invoking the constructor or append. Eleven queries produced:

- 122 indexed primes in (203,1,000];
- selected rank 78 at value 691, first-row index 185, and the recovered rank 78;
- a sixteen-prime page beginning 977, 983, 991, 997 and ending 1,069;
- the proper product witness 975=325·3 at array coordinate (2,93), selected as an old-square hit during stage 257;
- the full absence/factor certificate for the new column value 981=3²·109 at stage 257;
- the complete maximum-gap stage 96;
- final boundary pair (1,237,1,238);
- every new gap record through three pages of 128, 128 and 4 rows.

The reader copied/indexed the saved data, made 14 prime-index binary-search steps and decoded 281 records. It performed zero frontier initialization, product evaluation, heap update, factor lookup, trial division or prime-sieve work. Its open took 13 ms; the query batch measured 0 ms at Date.now resolution. The latter is not a claim of zero execution time.

## 8. Files and provenance

| File | Purpose |
|---|---|
| `prime_separator_frontier.cjs` | Constructor, saved append, certificates and finite navigation |
| `PRIME_SEPARATOR_API.md` | Construction, proof, API, bounds and execution scope |
| `seed60_through256.json` | Full first-stage snapshot, exact source seed and execution receipt |
| `seed60_through320.json` | Full final snapshot, parent identity, append receipt and all fresh-reader outputs |
| `README.md` | Entry point and concise result |

The initial data blob is `1b6c9ba449d8caa1e164d0e1b08a774575ccb25b`. The final data blob is `adad63e5be713f9bea301fd8ea6dfc7f587abf95`. Both contain a complete `.snapshot`, including the accepted seed and basis needed by the public loader. The final artifact identifies the initial data blob and its source state as its parent.

The basis is selected from `.snapshot.basis` of PR31426's `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json`, blob `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd` at merge `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8`. The unrelated row-prime sieve, local rules and interval counts from that artifact are not consumed.

The deliverable is a source-attributed finite continuation and reusable exact interface. Its gap histogram, prime-side counts and saved-frontier state do not establish a uniform infinite gap bound or a prime-distribution asymptotic.
