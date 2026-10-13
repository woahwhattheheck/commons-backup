# Smooth pair-sum graphs and retained maximum-clique certificates

## Purpose and mathematical scope

This module compiles a finite candidate set of distinct nonnegative integers into an index of its pair sums. It then searches the graph associated with a chosen set of allowed primes. An edge joins two distinct candidates exactly when every prime factor of their sum belongs to that allowed set.

A completed search returns one maximum clique in that particular finite graph. The retained evidence contains the new sum factorizations, all unordered-pair references, all adjacency masks, every processed search node, every coloring bound, both children of every branch, and every incumbent improvement. A saved incomplete search retains the pending stack and can continue from those states.

The application is the prime-support question recorded in [FormalConjectures/ErdosProblems/126.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/126.lean). The exact inspected file has Git blob **b193747601aea2ef1f5f3f04805b4991112b6aff**. Its convention is

$$
f(n)=\min_{\substack{A\subseteq\mathbb N\\ |A|=n}}
\left|\operatorname{PrimeFactors}
\left(\prod_{(a,b)\in A.\mathrm{offDiag}}(a+b)\right)\right|.
$$

The source writes the equivalent greatest universal lower-bound definition using IsGreatest. Its natural-number domain includes zero; the finite-set domain excludes repeated elements; and offDiag contains ordered pairs with unequal endpoints. For distinct nonnegative integers, every such sum is positive. In particular, the only zero sum would come from the excluded diagonal pair (0,0).

The ordered product is the square of the unordered-pair product:

$$
\prod_{(a,b)\in A.\mathrm{offDiag}}(a+b)
=
\left(\prod_{\{a,b\}\subseteq A,\ a\ne b}(a+b)\right)^2.
$$

Both have the same distinct prime support. The module may therefore retain one factorization reference per unordered pair.

For a returned clique A, its complete pair witnesses establish

$$
f(|A|)\le
\left|\bigcup_{\{a,b\}\subseteq A}\operatorname{PrimeFactors}(a+b)\right|.
$$

The right-hand side is the union actually observed in A. It is not automatically the cardinality of the allowed-prime set: an allowed prime may never occur in the selected sums.

This is a finite construction and search capability. Its maximum is conditional on the declared candidate universe and the declared allowed-prime set. It does not establish a matching global lower bound for f, enumerate all prime supports, search every natural-number set, enumerate all maximizing cliques, or settle an asymptotic question.

### Source status is a separate fact

The inspected formal catalogue annotates the main divergence question f(n)/log(n) -> infinity as research solved with answer True, while the local theorem body is still "by sorry". It links an external Lean resolution pinned to [commit 2516785fe6bbc43e979cf6029c976d9f998a7fba](https://github.com/tadamcz/erdos126/blob/2516785fe6bbc43e979cf6029c976d9f998a7fba/Erdos126/Resolutions/Erdos126_132usd_25h.lean#L3053). That external proof was not read, run or independently audited for this contribution. The annotation is source metadata, not an independently verified theorem claim by this module.

The same inspected catalogue marks the separate f(n)=o(n/log(n)) variant research open, with another local sorry. It attributes the historical log(n) << f(n) << n/log(n) bounds to Erdős and Turán, *On a Problem in the Elementary Theory of Numbers*, American Mathematical Monthly (1934), pages 608–611. That historical paper was not acquired here; the attribution is to the inspected catalogue.

One attempted retrieval of the canonical problem page returned HTTP 403 and was left unretried. No content was reconstructed from that unavailable page.

## Accepted factor-source custody

The actual consumer uses the complete accepted least-factor basis at:

- Repository: woahwhattheheck/commons.
- Path: research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json.
- Pinned revision: **8bcf059ef0fda877c0975f7a89a2ae565e71a3b8**.
- Git blob: **7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd**.
- Exact field: **snapshot.basis**.
- Declared limit: **16384**.
- Increasing accepted prime list: **1900 entries**.
- Least-factor table: **16385 entries**, addressing integers 0 through 16384, with entries 0 and 1 at those first addresses.

The [pinned source artifact](https://github.com/woahwhattheheck/commons/blob/8bcf059ef0fda877c0975f7a89a2ae565e71a3b8/research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json) is an established premise. This work neither regenerates its sieve nor repeats the earlier interspersion-row calculations.

The compiler checks source shape, exact bounds, increasing prime membership, and the agreement between a declared prime and its diagonal least-factor entry. It does not prove primality or the leastness of every table entry. For each newly needed sum s, it repeatedly reads p=lpf[s], requires an accepted prime p dividing the current value exactly, and records the exact positive quotient. Every quotient is smaller than its dividend. The chain stops at 1.

If a needed entry is absent, outside the accepted prime list or not an exact divisor, the compiler throws. Missing coverage is never evidence of primality.

A factor chain

$$
s=p_1q_1,\quad q_1=p_2q_2,\quad \ldots,\quad q_{t-1}=p_t\cdot1
$$

telescopes to a factorization of s. The saved row retains all triples (value, prime, quotient), the prime powers, and the bit positions for its distinct prime support. The special sum 1 has an empty chain, empty prime powers and zero support mask; it qualifies for every allowed-prime set, including the empty set.

The saved index preserves the source identity and complete accepted prime list. It does not duplicate the entire source least-factor array: every newly used division is already retained, and the original full table remains identified by its pinned artifact and field.

## API

The module is CommonJS, uses exact safe-integer arithmetic for covered factor divisions and BigInt masks for sets, and has no filesystem, network, clock, random source or external package dependency.

```js
const {
  compileSmoothSumIndex,
  openSmoothSumIndex
} = require("./smooth_sum_clique_index.cjs");
```

### compileSmoothSumIndex(options)

```js
const index = compileSmoothSumIndex({
  source_id: "application-specific-source-id",
  basis_id: "gitblob:7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd:snapshot.basis",
  candidates: Array.from({ length: 128 }, (_, value) => value),
  basis: acceptedArtifact.snapshot.basis
});
```

The caller supplies the original accepted basis object. Its exact fields are limit, primes and least_factor_by_integer. The candidate list must be strictly increasing, contain at least one element, contain at most 128 elements, and contain nonnegative safe integers. Every distinct-endpoint sum must lie within the declared basis limit.

Compilation constructs the complete unordered-pair address table. It factors each distinct pair sum once even when many pairs have that sum. No allowed-prime graph is built until a search requests one.

The actual interval 0 through 127 contains 8128 unordered pairs and needs exactly the 253 sums from 1 through 253. The largest admissible sum is 126+127=253; the self-sum 127+127 is outside the domain.

### searchMaximumClique(options)

```js
const result = index.searchMaximumClique({
  allowed_primes: [2, 3, 5],
  node_budget: 64
});
```

The allowed-prime request is copied and sorted. Duplicates are rejected; every prime must belong to the accepted source; the empty list is supported. A canonical comma-separated key identifies a graph.

The first search for a key builds its adjacency masks from the saved prime-support rows, then starts a depth-first search. A later call for the same incomplete key processes only pending states. A later call for a completed key returns its saved maximum with zero new search nodes.

The result contains:

| Field | Meaning |
|---|---|
| status | complete or incomplete |
| stop_reason | exhausted, node_budget or node_capacity |
| graph_key, allowed_primes | Exact graph identity |
| edge_count | Retained unordered edge count |
| processed_this_call | New states processed in this invocation |
| processed_node_count | Total processed states for this graph |
| pending_count | Saved states not yet processed |
| incumbent | A witnessed clique, even when the search is incomplete |
| maximum | Saved exact finite maximum only after complete exhaustion; otherwise null |
| new_work | The work added by this invocation, excluding inherited work |

An incomplete incumbent is a feasible clique and supplies a construction witness. It is not an optimality certificate.

The default node budget is 256; callers may request 1 through 10000 states in one call. Each graph has a hard capacity of 50000 allocated node addresses. Before touching a pending state the search reserves space for both possible children. At the hard capacity it conservatively leaves that state pending, without partially processing it. A capacity stop therefore remains incomplete even if a more elaborate capacity policy might have allowed a final prune. Repeated calls do not turn such a stop into an optimum.

### snapshot() and openSmoothSumIndex(snapshot, options)

```js
const saved = index.snapshot();

const resumed = openSmoothSumIndex(saved, {
  source_id: "application-specific-saved-reader-id"
});

const next = resumed.searchMaximumClique({
  allowed_primes: [2, 3, 5],
  node_budget: 256
});
```

The snapshot is complete JSON-compatible retained state, including all graph views, all completed and pending search states, incumbent history, cumulative work and session activity. It is a supported restoration format for this API.

Opening copies the supplied state and checks bounded shape and reference integrity. Checks include unique pair addresses, canonical in-universe masks, factor-prime addresses, unique graph/search keys, contiguous allocated node IDs, strictly forward child addresses, matching parent/child branch references, and the requirement that a complete search have an empty pending stack and a retained maximum.

Opening does not repeat factor divisions, construct adjacency, establish that color classes are independent, replay clique checks, recompute branch masks or rerun the search. It is not an independent mathematical verifier for an adversarial snapshot. Correct continuation and result interpretation rely on custody of a snapshot emitted by this compiler/search implementation, its declared accepted factor source, and its mathematical invariants. A forged snapshot can satisfy shape checks while containing false mathematics.

Every open starts a new session whose mathematical work counters are zero. Loading counts are separate from new mathematical work. Runtime address maps and BigInt representations may be reconstructed from retained records; that indexing is not charged as new factorization, graph construction or search.

### getMaximum(options)

```js
const savedMaximum = resumed.getMaximum({
  allowed_primes: [2, 3, 5]
});
```

This is a retained-result query. It does not build a missing graph or start a missing search. Its status is complete, incomplete or not_searched. A complete result includes one canonical increasing list of selected candidates; every selected unordered-pair/factor reference; the actual distinct prime union; the search-node count; and the incumbent-history address. Increasing output order canonicalizes only the chosen witness; no lexicographic extremality is claimed.

### getPair(options)

```js
const pair = resumed.getPair({ left: 0, right: 1 });
```

Both endpoint values must belong to the declared universe and must differ. The request may reverse the endpoints. The result uses canonical increasing endpoint order and returns the retained pair-row address and complete saved factorization of their sum. Diagonal requests throw DIAGONAL_PAIR.

### pageSums(options)

```js
const page = resumed.pageSums({ offset: 0, limit: 256 });
```

Offset addresses the ordered distinct-sum table. Limit is 1 through 256. The returned page includes its total row count and next_offset, which is null at the end. It copies saved rows and performs no new division.

### summary()

The summary reports candidate, sum and pair counts; retained graph/search summaries; cumulative mathematical work; and the active session's loading and new-work counters. Calling summary or snapshot does not create a query event and does not execute mathematical work.

### Ownership of returned data

Options that contain lists or saved state are defensively copied. Public results and snapshots are also copied. Modifying a caller-held result does not mutate the live index. The returned API object and exported constants are frozen.

## Exact search argument

A search state contains a clique R and a candidate set C. The invariant is that R is a clique, C is disjoint from R, and every member of C is adjacent to every member of R. The initial state has empty R and the full candidate universe.

### Greedy colors give an upper bound

At a nonempty candidate state, the implementation builds one independent color class at a time. Within a class it chooses the least remaining vertex, removes it from the uncolored set, and restricts the class's available vertices to nonneighbors of every vertex already chosen for that class.

Consequently each class is independent. Every chosen vertex is removed from the uncolored set exactly once; the process ends only when no uncolored vertex remains. The classes therefore partition C.

If there are k classes, an extension clique can use at most one vertex per class. Thus

$$
|\text{any clique extending }R\text{ through }C|\le |R|+k.
$$

The module retains every class as a complete list of candidate indices and retains the resulting bound. When that bound is no larger than the size of a witnessed incumbent, the state is pruned.

Equality is deliberately sufficient to prune: the API finds one maximum, rather than all cliques tied for maximum size. Every prune identifies the incumbent-history entry used at that point.

### Include/exclude branches cover every extension

If the bound leaves room for improvement, the implementation chooses the last vertex of the last retained color class. For that vertex v, every extension either contains v or excludes v.

The include state is

$$
(R\cup\{v\},\ C\cap N(v)),
$$

and the exclude state is

$$
(R,\ C\setminus\{v\}).
$$

These cases are disjoint and exhaustive. The include branch preserves the clique invariant because v belonged to C. Its new candidates remain common neighbors of R and are neighbors of v. The graph has no self-loops, so v is absent from its own neighborhood. The exclude branch preserves the invariant by taking a subset of C.

Both child addresses and the chosen vertex are retained in their parent record. Child records retain their parent address and include/exclude label. Children receive larger IDs than their parent, preventing a retained branch cycle.

The explicit stack pushes the exclude child before the include child, so the include branch is processed first. The stack order is preserved across saved opens.

### Incumbents and leaves

Before deciding a node, the search compares its current clique to the incumbent. Every strict improvement stores the complete clique witness and node address in a monotone history. An empty candidate set is a leaf; its current clique has already participated in that comparison.

The initial empty clique is retained as the first history entry. Every processed node identifies the incumbent history valid after its own comparison. No incumbent is just an unsupported numerical lower bound.

### Completion

Every allocated state is either a processed leaf/prune, a processed branch with both children accounted for, or a pending state. A budget stop preserves the pending stack and reports incomplete.

When the pending stack is exhausted, the initial full graph has been covered by valid branch partitions and valid terminal bounds. The final witnessed incumbent is therefore maximum in the declared graph. Only then does the implementation construct and save the maximum result and actual prime union. Later readers return that object without regenerating its witness selection.

A consumer wishing to perform an independent proof audit can inspect the full source, accepted factor premise and retained trace. This contribution preserves that evidence; it does not disguise a structural saved-state open as such an audit.


## Recorded consumer: the interval 0 through 127

The first and only compilation for this contribution began at **2026-10-04T19:33:37.617Z** using implementation blob **983a039c73d48035cbaf7bcfe5ef34ea2ebc21ac** (37494 UTF-8 bytes). The implementation was frozen before that execution and remained unchanged through the saved continuation, second graph and fresh reader.

The complete result is in [interval0_127_prime_support_cliques.json](./interval0_127_prime_support_cliques.json). Its final snapshot includes the complete source-prime list, every new factor row, all 8128 pair rows, both complete adjacency views and both complete search traces. It does not depend on ephemeral tool-store references.

### Two exact finite maxima

| Allowed primes | Graph edges | Maximum size | One retained maximum clique | Actual prime union |
|---|---:|---:|---|---|
| 2, 3, 5 | 1278 | 5 | 0, 8, 24, 72, 120 | 2, 3, 5 |
| 2, 3, 5, 7 | 2035 | 7 | 0, 4, 12, 20, 36, 60, 108 | 2, 3, 5, 7 |

The first graph has no clique of size 6 in this universe; the second has no clique of size 8 in this universe. Each statement follows from its own exhausted finite search, not from extrapolation between the graphs.

The selected witnesses also give the valid construction inequalities f(5) <= 3 and f(7) <= 4 under the inspected natural-number convention. These are not claims of new best-known bounds or of the exact global values of f.

### Real saved continuation

The first P={2,3,5} call requested a budget of 64 states. It processed 64 states, retained a size-5 incumbent, and correctly reported incomplete with one pending state.

The pending state had ID 64, parent ID 62, branch exclude, and empty current clique. Its exact candidate mask is preserved in the consumer's pending-handoff record. Reopening that snapshot loaded the 64 processed states and the one pending state. A subsequent budget of 256 processed **13 new states**, including children arising from that pending branch, and exhausted the stack.

The completed P={2,3,5} trace has **77 nodes: 38 branches, 35 prunes and 4 leaves**. The first 64 records were preserved exactly; no prior node was recolored or searched again. That continuation performed zero factor divisions, zero pair-table construction, zero graph construction and zero pair-support checks.

A separate saved open then consumed the same factor index for P={2,3,5,7}. It constructed only the new graph view and ran that graph's own search. The new view required 8128 saved-support membership checks. Its complete search has **157 nodes: 78 branches, 75 prunes and 4 leaves**. It performed zero factor divisions and did not repeat the completed first search.

The construction of the second graph naturally shares edges with the first graph, but its adjacency masks are independently built for its own allowed-prime predicate. Reusing the factor index does not substitute the first graph's optimality proof for the second one's proof.

### Complete mathematical work accounting

| Work item | Compilation and first P3 batch | Saved P3 continuation | Saved P4 consumer | Fresh reader | Cumulative |
|---|---:|---:|---:|---:|---:|
| Distinct sums factored | 253 | 0 | 0 | 0 | 253 |
| Accepted least-factor reads | 660 | 0 | 0 | 0 | 660 |
| Exact factor divisions | 660 | 0 | 0 | 0 | 660 |
| Unordered pair rows built | 8128 | 0 | 0 | 0 | 8128 |
| New graph views | 1 | 0 | 1 | 0 | 2 |
| Pair-support checks | 8128 | 0 | 8128 | 0 | 16256 |
| Adjacency edges added | 1278 | 0 | 2035 | 0 | 3313 |
| New searches | 1 | 0 | 1 | 0 | 2 |
| Search nodes processed | 64 | 13 | 157 | 0 | 234 |
| Color classes built | 274 | 63 | 925 | 0 | 1262 |
| Vertices assigned to color classes | 3048 | 831 | 6440 | 0 | 10319 |
| Branch decisions | 32 | 6 | 78 | 0 | 116 |
| Prune decisions | 28 | 7 | 75 | 0 | 110 |
| Leaf decisions | 4 | 0 | 4 | 0 | 8 |
| Incumbent improvements | 5 | 0 | 7 | 0 | 12 |
| Maximum result objects built | 0 | 1 | 1 | 0 | 2 |
| Maximum pair witnesses selected | 0 | 10 | 21 | 0 | 31 |
| Distinct factor rows selected for those maxima | 0 | 10 | 21 | 0 | 31 |

A color-assignment count is work at a newly processed search state. A vertex may appear in the candidate sets of several different states; this is ordinary search work, not a repeated accepted-source calculation.

Likewise, cumulative edge additions count edges once per graph view. The value 3313 is the sum of the two graph edge counts, not the cardinality of a union of their edge sets.

### Fresh saved-result reader

After both searches completed, a fresh open loaded 253 factor rows, 8128 pair rows, two graph views and 234 processed search nodes. It made nine API queries: two maximum lookups, six pair lookups and one complete sum page.

| Pair query | Canonical pair | Sum | Retained factorization |
|---|---|---:|---|
| 0, 1 | 0, 1 | 1 | Empty prime support |
| 8, 24 | 8, 24 | 32 | 2^5 |
| 72, 120 | 72, 120 | 192 | 2^6 * 3 |
| 4, 108 | 4, 108 | 112 | 2^4 * 7 |
| 60, 108 | 60, 108 | 168 | 2^3 * 3 * 7 |
| 127, 126 | 126, 127 | 253 | 11 * 23 |

Each returned factorization includes the full retained division chain, not just the displayed powers. The last request shows endpoint-order normalization and a pair whose support lies outside both declared prime palettes.

The page request offset=0, limit=256 returned all 253 ordered sum rows, reported total=253, and ended with next_offset=null. All nine requests added zero to every mathematical work counter, including factor divisions, adjacency construction, coloring, search, maximum construction and witness selection.

Retained-data identity comparisons confirmed that the source factor rows and pair rows were unchanged across all opens; the first 64 node records formed an unchanged prefix of the completed first trace; the carried pending state kept its exact address and candidate set; and the completed graphs/searches were unchanged by the final reader. These comparisons concern custody of saved bytes and records. They do not independently re-prove the retained mathematics.

### Timing observations

| Observed operation | Milliseconds |
|---|---:|
| First compilation | 14 |
| First 64-state P3 batch | 8 |
| First call total including source evaluation and retention | 53 |
| Saved open before P3 continuation | 29 |
| Thirteen new continuation states | 1 |
| Saved open before P4 | 26 |
| New P4 graph and complete search | 11 |
| Final saved-reader open | 35 |
| Nine retained-result queries | 3 |

These are individual observations from the actual consumer, not benchmarks, speedup ratios or runtime guarantees. The implementation contains no timing instrumentation; the surrounding consumer recorded the durations.

## Bounded implementation limits and failure behavior

| Limit | Value |
|---|---:|
| Candidate vertices | 128 |
| Accepted basis limit | 65536 |
| Allowed primes per graph | 32 |
| Retained graph views/searches | 8 |
| States requested in one search call | 10000 |
| Allocated node capacity per graph | 50000 |
| Sessions retained in one snapshot | 64 |
| Query events per session | 256 |
| Source identity string length | 512 characters |
| Sum rows returned per page | 256 |
| Recursive copied items | 6000000 |
| Copied string characters | 64000000 |
| Copy nesting depth | 32 |

The declared basis must cover every distinct-endpoint sum. A single-candidate universe is supported and has an empty pair table. Empty and singleton maximum witnesses have empty pairwise prime support. No self-sum is introduced to make their support nonempty.

These limits bound copying and retained state; they are not mathematical completeness guarantees. Very large retained objects can hit copy limits, and search capacity can be reached before optimality is known. A capacity stop is explicitly incomplete; malformed inputs or copies beyond their structural limits throw a named error.

The object-copy format supports JSON-style null, booleans, strings, safe integer numbers, arrays and plain objects. It rejects unsafe numbers, unsupported object types, excessive depth/items/text and reserved prototype-related field names. No BigInt value appears in exported JSON; set masks use canonical lowercase hexadecimal strings, with zero encoded as "0".

The actual published consumer completed far below its node capacity. No interrupted state, unresolved provider error or partial search is presented as a finished result.

## Evidence and publication boundary

The implementation and full consumer evidence were prepared as four owned files in research/ppl017_erdos126_smooth_sums. Existing accepted factor-source files, other problem modules and other owners' work were not edited.

The mathematical work was the single new compilation, the new finite searches, the saved continuation and the new retained-result reader described above. No earlier sieve, accepted row consumer or accepted proof calculation was replayed. No test suite, fixture family, workflow or native runtime probe was added.

The source identities, input declarations, actual phase results, full saved state and reader outputs make the capability reviewable outside the execution session. The API can be used directly from the published CommonJS source; the consumer JSON is a portable artifact with a supported saved-index snapshot.

The contribution establishes a reusable finite-search capability and its explicit results. The global Erdős126 research status remains the separately attributed source metadata described at the beginning of this guide.
