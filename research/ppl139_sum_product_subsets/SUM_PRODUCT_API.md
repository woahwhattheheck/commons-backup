# Finite sum–product subset index

The module compiles all fixed-cardinality subsets of an explicitly supplied finite integer host. It retains every subset's two distinct-value image sizes, their joint distribution, the complete Pareto frontier, and every minimizer of the larger image. A saved reader navigates these records and returns exact pair fibers.

The supplied consumer is all nine-element subsets of H = {1,…,17}. Its unique minimizer is

    {1,2,3,4,6,8,9,12,16},

with |A+A| = |AA| = 25. Therefore

    min_{A subset H, |A|=9} max(|A+A|, |AA|) = 25.

The host restriction is essential. This is not a claim that 25 is the minimum over all nine-element integer sets, or a new sum–product exponent.

## Mathematical conventions and source attribution

For a finite integer set A, use

    A+A = {a+b : a,b in A},     AA = {ab : a,b in A}.

These are sets of distinct values. Repeated values from different pairs count once. All of A×A is allowed: a+a and a² are included. Addition and multiplication are commutative, so the compiler stores each unordered pair with repetition exactly once, indexed i≤j. For ordered representation counts, an off-diagonal pair has multiplicity two and a diagonal pair has multiplicity one.

Mei-Chu Chang, “The Erdős–Szemerédi problem on sum set and product set,” Annals of Mathematics 157 (2003), 939–957, introduction equations (0.1) and (0.3), states these set-image definitions and credits Erdős–Szemerédi (1983). Author manuscript:
https://arxiv.org/pdf/math/0402285

Max Wenqiang Xu and Yunkun Zhou, “On Product Sets of Arithmetic Progressions,” Discrete Analysis 2023:10, DOI 10.19086/da.84267, treats integer sets, arithmetic progressions, and dense subsets of progressions. Its equation (1.3) records the asymptotic sum–product conjecture as open as of that paper. Its theorems are prior asymptotic results, not this finite census. Author manuscript:
https://arxiv.org/pdf/2201.00104

The current retrieved Formal Conjectures statement of Erdős 52 asks whether, for each 0<epsilon<1, there is a positive C_epsilon such that every finite integer set A satisfies

    max(|A+A|, |AA|) >= C_epsilon |A|^(2-epsilon).

It has a research-open annotation and local proof placeholders. The complete decoded source was read on 2026-10-05 from:
https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/52.lean

The connector supplied no immutable repository commit or blob identifier. The independently computed Git-blob identity of the returned 1,262 UTF-8 bytes is 36c5dbda182d8622755f0e34fad3f8218da3f438; this is a content identity, not a claimed provider pin. No linked proof was inspected. The annotation and the 2023 paper are dated source evidence, not an exhaustive current literature survey.

The generic API accepts signed integers and zero. Its actual consumer uses a positive interval only. It does not claim that positive-only enumeration covers the formal statement's whole integer domain. The finite host is selected explicitly for this implementation; it is not attributed as a numerical example from either paper.

## Exhaustive finite result

There are C(17,9) = 24,310 subsets. Every one is retained in zero-based lexicographic order of its increasing host-index tuple.

The complete nondominated image-size frontier has five points, each attained by exactly one subset. “Nondominated” minimizes both coordinates: (s,p) dominates (s',p') when s≤s', p≤p', and at least one inequality is strict.

| Global rank | Subset | Sum count | Product count | Ordered additive energy | Ordered multiplicative energy |
|---:|---|---:|---:|---:|---:|
| 0 | 1,2,3,4,5,6,7,8,9 | 17 | 36 | 489 | 209 |
| 1 | 1,2,3,4,5,6,7,8,10 | 18 | 35 | 461 | 225 |
| 45 | 1,2,3,4,5,6,8,9,10 | 19 | 32 | 429 | 241 |
| 54 | 1,2,3,4,5,6,8,10,12 | 20 | 30 | 385 | 277 |
| 631 | 1,2,3,4,6,8,9,12,16 | 25 | 25 | 301 | 321 |

Energy means sum_v r(v)^2, where r counts ordered pairs giving v. Thus it counts ordered quadruples with equal sums or products. Each fiber collection has total ordered multiplicity 9² = 81. These energies were new saved-ledger query outputs, not constructor objectives.

The final record contains:

- all 153 host pairs, including 17 diagonals;
- sorted tables of all 33 host sum values and 114 host product values;
- all 24,310 subset masks and their image counts;
- all 210 nonempty joint histogram cells;
- all five Pareto signatures and the unique minimizer;
- all 28 saved-reader outputs, three slice snapshots, and ten full Pareto pair-fiber collections;
- the complete 15-member conditional slice with objective at most 30, containing host index 0 (value 1) and excluding host index 16 (value 17).

The last global subset, rank 24,309, is {9,…,17}, with image counts (17,44). Rank 12,155 is {1,5,7,8,11,12,13,16,17}, with (27,45). These are retained navigation results, not additional searches for optimum.

## Why the construction covers the stated family

Let the host be h_0<…<h_(n-1). The pair ledger contains one row for each 0≤i≤j<n. Its mask has bits i and j set, with a single bit on a diagonal. That pair belongs to a subset mask M precisely when all of its bits lie in M. Its exact BigInt sum and product are assigned dense IDs in sorted value tables.

The recursive traversal chooses increasing indices. At a node with t chosen indices, the next index ranges from start through n-(k-t). Every k-subset has one increasing sequence of choices and therefore exactly one leaf. Conversely each leaf has k distinct host indices. Trying next indices in increasing order produces lexicographic leaf order.

When adding index i, the newly available unordered pairs are (i,i) and (j,i) for each previously chosen j. They are exactly the pairs that were absent before and present afterward. Increment the multiplicity of each sum ID and each product ID; increase the respective distinct-value count only when its multiplicity changes from zero to one. On backtracking, decrement those same multiplicities and decrease the distinct count only at one to zero.

Induction on the recursion therefore maintains precisely the pair images of the current partial subset. Each leaf records the correct distinct image counts. No pair sum or product is recalculated during recursion. Multiple pairs mapping to one image ID are handled by the counters, including collisions involving zero or negative values.

A histogram counts each leaf once. The minimum of max(s,p) and all attaining row IDs are updated over every leaf. To find the Pareto frontier, sort histogram signatures first by s, then p. A signature is nondominated exactly when its product coordinate is strictly smaller than all earlier product coordinates. Earlier signatures have smaller sum, or the same sum and smaller product. A later signature cannot dominate an earlier one unless it has the same sum and smaller product, which sorting has already excluded. Counts in frontier rows retain all subsets with that signature.

These arguments establish correctness of the stated algorithm, conditioned on its exact implementation and input. The retained complete census is finite evidence. It is not a formal proof assistant development or an independently authenticated dataset.

## Pair fibers and ordered multiplicity

For a requested saved subset, fibers scans the host pair ledger and selects rows whose pair mask lies inside the subset. It groups the retained pair IDs by saved sum or product ID. It performs no new host addition or multiplication.

Every fiber stores its exact decimal image value, all unordered pair IDs, and the ordered multiplicity. An off-diagonal pair represents (i,j) and (j,i), even when another pair has the same value; a diagonal represents only (i,i). The API computes total ordered pairs and ordered energy from these weights. Pair IDs resolve through the retained ledger or pairPage.

These queries are real work: the ten consumer requests scanned 1,530 saved pair rows and returned 257 fibers. Their grouping, fiber counts and energy arithmetic are new query operations. “No image-count reconstruction” in the telemetry refers to not rebuilding the census rows; it does not imply that a requested fiber collection has no new grouping or counting.

## Public CommonJS API

No filesystem, network, native process or external dependency is used.

    const { compile, open } = require("./sum_product_subsets.cjs");

    // A fresh, deliberately bounded construction:
    const snapshot = compile([1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17], 9);

The example shows the constructor contract. Consumers of the published result should open its saved snapshot instead of recomputing it:

    const packet = JSON.parse(savedText);
    const reader = open(packet.construction.snapshot);
    const bestSlice = reader.openSlice(reader.minimizers());
    const best = bestSlice.select(0);
    // best.values: ["1","2","3","4","6","8","9","12","16"]
    // best.sum_count = best.product_count = 25

Exports are compile(host,k), open(snapshotOrJson), LIMITS and SCHEMA.

### Input contract

- The host is an array of at most 20 strictly increasing integers. Empty host is allowed only with cardinality zero.
- Each integer is a safe integer Number or a signed decimal string with at most 128 magnitude digits. No exponent syntax, leading plus, nonintegral Number or imprecise Number is accepted. Negative zero normalizes to zero.
- Duplicate host values are rejected rather than treated as multiplicity. Input order must already be increasing.
- k is an integer from 0 through host length. The k=0 family has one empty subset with both image counts zero.
- The constructor's subset budget is 250,000 rows. With the current host cap, every fixed-cardinality family fits; the guard remains explicit.
- Arithmetic on pair values uses BigInt. Pair masks and bounded counters use Number safely under the host limit.
- Pages contain at most 64 records. Imported JSON is limited to 12,000,000 characters.
- Product strings can have up to 256 magnitude digits; the loader allows 257 for its common image-table structural bound.
- The constructor has no elapsed-time cap. The hard limits are dimensions, input digits and imported snapshot size.

Only the positive 17-point, k=9 consumer was executed. Empty, signed, zero, maximal-host and malformed-input branches were source-inspected, not exercised by a synthetic suite.

### Reader methods

| Method | Result |
|---|---|
| summary() | Input, dimensions, Pareto signatures, minimax count/value, constructor counters |
| select(rank) | One global lexicographic subset row with values, mask, indices and objective |
| rank(values) | Its global rank; input must be increasing and have exactly k host members |
| page(start=0,limit=64) | Global subset page |
| histogram(start=0,limit=64) | Sorted joint histogram cells [sum_count,product_count,multiplicity] |
| minimizers() | Saved row-ID slice containing every minimax subset |
| filter(criteria) | Saved row-ID slice built by one explicit scan of census rows |
| openSlice(slice) | Navigation over already selected row IDs |
| fibers(rank,"sum" or "product") | Complete pair-ID fibers for one subset |
| pairPage(start=0,limit=64) | Host-pair records with exact saved sum/product values |
| stats() | Copy of reader counters |
| snapshot() | Independent full snapshot copy |

All ranks and host indices are zero-based. Values are decimal strings. A page start may equal its family size, returning an empty terminal page. select on an empty family or outside the rank range throws. Returned records and snapshots do not alias retained internal arrays.

filter accepts only:
sum_min, sum_max, product_min, product_max, objective_max, contains, excludes, pareto.

Numeric thresholds are nonnegative integers at most k(k+1)/2. contains and excludes are arrays of distinct host indices, not integer values. Conflicting inclusion/exclusion conditions yield an empty slice. pareto:true selects signatures already saved in the Pareto table. Unknown keys are rejected. There is no hidden isomorphism, scaling, translation, reflection or sign quotient: differently labelled subsets remain distinct.

A slice exposes summary(), page(), select(), rank(values), snapshot(). Slice select returns both slice_rank and global rank. Slice rank returns null for a valid global subset outside that slice. Opening a slice checks its exact host and k, row-ID bounds and order; it does not re-run its filter. This is why a saved slice can be reused without a new census scan.

## Saved schema and trust boundary

The packet's top-level fields are schema, source, input, provenance, construction and saved_reader.

construction.snapshot has schema commons.sum_product_subsets/v1 and retains:
host, k, ordering, pair_columns, row_columns, sum_values, product_values, pairs, rows, histogram, pareto, minimax and stats.

Pair columns are [i,j,mask,sum_id,product_id].
Subset row columns are [mask,sum_count,product_count].
Histogram and Pareto rows are [sum_count,product_count,count].
minimax stores value and complete row_ids.

The saved reader opens a defensive copy, checks dimensions, canonical ordered value tables, pair index/mask layout, ID bounds, subset mask cardinalities and uniqueness, lexicographic row order, histogram dimensions/order/partition total, and bounded increasing minimizer row IDs. It indexes the saved masks once.

The loader does not recompute pair values, reconstruct image counts, verify histogram membership, rederive Pareto dominance, authenticate the minimum, or replay the exhaustive traversal. Slice criterion metadata is likewise not independently checked against every saved ID. Structural validity is not mathematical provenance. For authentic results, bind the complete file and executed-source identities below.

The generic host input and the ledger tables are not interchangeable: supplying a different host with copied counts would be untrusted even if it passed dimensions. Published data must not be described as recertified merely because open succeeds.

## Actual execution and custody

The implementation was authored and parsed, then frozen and checkpointed before computation:

- sum_product_subsets.cjs: 5a802b17baa7e524b59bf9bad0bc3ebd705bd2bd, 12,098 UTF-8 bytes.
- The one initial complete constructor packet: 853a3aeb2be40c7e122bf2474da6d93ca3708ed5, 1,616,478 characters.
- The final compact packet with all saved-reader outputs: e556575a110b9fff13ac39a2ca824c33fd3de4c0, 391,157 UTF-8 bytes.

Both source and each complete data checkpoint were written as Git blobs before prose. The final file preserves the entire construction snapshot, not just its minimum or summary.

Constructor accounting: 153 BigInt additions, 153 BigInt multiplications, 48,620 recursive nodes, 24,310 completed subsets, 393,822 pair insertions and the same number of removals. Its initial wall observation was 179 ms. A fresh source context opened the retained snapshot in an observed 49 ms. These are single observations, not benchmarks.

The fresh reader made 28 recorded calls. It indexed 24,310 saved rows; its two filters explicitly scanned 48,620 rows. Ten fiber requests scanned 1,530 saved pair rows and returned 257 fibers. It performed no host pair arithmetic, subset enumeration or census count recomputation. Histogram and pair pages export all retained table records without rebuilding them. Three slices are saved for later consumers.

No earlier mathematical construction, accepted enumeration, test suite, native executor, workflow, sponsor contact or submission was used. The file supplies exact finite data and a reusable bounded API; it makes no mathematical priority, global extremal, frontier or prize claim.
