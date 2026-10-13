# Tournament inverse fibers and saved partial-coloring queries

This module compiles the complete space of small **labeled tournaments** into a forward cyclic-triple map and an inverse index. It then answers realizability, orientation count/rank/select, partial triple-coloring, and transitive-subset queries from the saved records.

The delivered six-vertex constructor ran once. Its 32,768 orientations produce **8,563 distinct cyclic-triple signatures**. All forward words, inverse codes, signatures, offsets, and topology descriptors are retained. A separate saved reader made 15 queries with zero orientation enumeration, cyclic-triple reclassification, or inverse-index reconstruction.

The partial pattern making triples `012` and `123` cyclic and triples `013` and `023` transitive has 2,048 matching labeled orientations in 623 complete-signature fibers. The saved reader selected rank 777 in the specified grouped order and retained its exact inverse rank. The records are complete finite data for this construction family; they do not improve the asymptotic Ramsey bound.

## Primary source, target, and scope

[Conlon, Fox and Sudakov, *Hypergraph Ramsey numbers*, arXiv:0808.3760v1](https://arxiv.org/pdf/0808.3760), printed page 3, describes the construction credited there to Erdős and Hajnal: orient every unordered pair; color an unordered triple red precisely when it is a directed cycle, and blue otherwise. It notes that a four-vertex tournament has at most two cyclic triples and relates blue homogeneous sets to transitive subtournaments. The implementation and the proofs below use these conventions.

The same paper's introductory discussion distinguishes the two-color three-uniform Ramsey target from higher-color results. PPL039 / Erdős564 asks for a double-exponential lower bound for the diagonal two-color three-uniform Ramsey number. A separate observed default-branch formal source states the eventual inequality `2^(2^(c*n)) <= hypergraphRamsey 3 n` for some real `c>0`. Its local annotation is open and its theorem contains placeholders.

That formal read returned complete decoded text without a blob SHA or commit identity. No immutable formal-source pin, Lean execution, linked proof verification, or independent current-status survey is claimed. The accessible paper supplies the construction provenance independently.

The new contribution is a bounded forward/inverse data structure and its finite consumer. It does not assert that every red-`K4^(3)`-free hypergraph is representable, identify orientations modulo isomorphism, quotient reversal, or infer an asymptotic result from six vertices. No sponsor contact, submission, prize application, or payment claim accompanies it.

## Delivered files and fixed source

| File | Role |
|---|---|
| `tournament_fibers.cjs` | Dependency-free CommonJS compiler and saved reader. |
| `six_vertex_fibers.json` | Complete finite index, every saved-reader event, source/operation metadata, work counters, timings, and literal custody checks. |
| `TOURNAMENT_FIBERS_API.md` | This encoding, derivation, API, evidence, and resource contract. |
| `README.md` | Entry point and result summary. |

The source used by both the constructor and reader is Git blob `0a07891cdc03dc0dbce7058658385b2cad446c42`, **38,780 UTF-8 bytes**. It was frozen before the first constructor and was not changed during execution.

All computational quantities fit bounded exact integer ranges. For at most six vertices there are at most 15 edge bits and 20 triple bits. Integer bit masks therefore stay below `2^20`, safely inside JavaScript's signed 32-bit bitwise range. Counts and indices are safe integer Numbers. No floating transcendental operations, BigInt approximation, package dependency, random generator, filesystem, network, clock, or native process is needed by the module.

The compiler explicitly enumerates every orientation for a new bounded input. There is no resumable partial-construction state, and the reader does not invoke the compiler. A future new vertex count requires its own deliberate compiler input; inspecting the delivered data uses its saved record.

## Encodings

### Labels, edges, and orientation codes

Vertex labels are `0,...,n-1`. Unordered pairs `(i,j)` with `i<j` are listed lexicographically, first by `i` and then by `j`.

An orientation is an integer code in `[0,2^E)`, where `E=n(n-1)/2`. Edge bit `e` equal to one means its lower label points to its upper label. Zero means the upper label points to the lower label. Leading zero bits are significant positions in this fixed-width encoding.

For six labels:

| Edge ID | Pair | Meaning of bit 1 |
|---:|---|---|
| 0 | `0,1` | `0→1` |
| 1 | `0,2` | `0→2` |
| 2 | `0,3` | `0→3` |
| 3 | `0,4` | `0→4` |
| 4 | `0,5` | `0→5` |
| 5 | `1,2` | `1→2` |
| 6 | `1,3` | `1→3` |
| 7 | `1,4` | `1→4` |
| 8 | `1,5` | `1→5` |
| 9 | `2,3` | `2→3` |
| 10 | `2,4` | `2→4` |
| 11 | `2,5` | `2→5` |
| 12 | `3,4` | `3→4` |
| 13 | `3,5` | `3→5` |
| 14 | `4,5` | `4→5` |

Thus one integer represents every directed edge of its labeled tournament. Label permutations are not identified; different codes are different orientations.

### Triples and cyclic signatures

Unordered triples `i<j<k` are listed lexicographically. For the stored edge bits

$$
a=b_{ij},\qquad b=b_{ik},\qquad c=b_{jk},
$$

the triple is cyclic exactly when

$$
a=c\quad\hbox{and}\quad b\ne a.
$$

These are the two directed-cycle patterns. The middle stored bit refers to `i→k`, so its direction must not be silently reversed.

A cyclic signature has one bit for each triple. Bit one means cyclic/red; bit zero means transitive/blue. The six-label triple table is:

| Triple ID | Vertices | Triple ID | Vertices |
|---:|---|---:|---|
| 0 | `0,1,2` | 10 | `1,2,3` |
| 1 | `0,1,3` | 11 | `1,2,4` |
| 2 | `0,1,4` | 12 | `1,2,5` |
| 3 | `0,1,5` | 13 | `1,3,4` |
| 4 | `0,2,3` | 14 | `1,3,5` |
| 5 | `0,2,4` | 15 | `1,4,5` |
| 6 | `0,2,5` | 16 | `2,3,4` |
| 7 | `0,3,4` | 17 | `2,3,5` |
| 8 | `0,3,5` | 18 | `2,4,5` |
| 9 | `0,4,5` | 19 | `3,4,5` |

The authoritative IDs and vertices are the complete `saved.topology.triples` array. Every signature uses the compiler's actual lexicographic ordering; consumers should use that array when creating constraints.

### Vertex subset masks

A vertex subset is an integer mask in `[0,2^n)`. Vertex `v` belongs when bit `v` is one. The constructor retains all `2^n` subset descriptors, including the empty set. Each descriptor stores its vertices, size, and the mask of triples wholly contained in it.

The empty subset, singleton subsets, and pairs are vacuously transitive because they contain no triples. Their unique total orders are determined by their orientation, with the empty order permitted.

## Complete forward map and inverse fibers

The forward array `forward.cyclic_words` is indexed directly by orientation code. It has one word for every code from zero through `2^E-1`. Each word retains all triple outcomes, including its zero bits; compact bit packing omits no classification.

The inverse index has three arrays:

| Array | Meaning |
|---|---|
| `inverse.signatures` | Every observed signature, strictly increasing. |
| `inverse.offsets` | Cumulative fiber boundaries, starting at zero and ending at the full orientation count. |
| `inverse.orientation_codes` | Every orientation code exactly once, grouped by signature and increasing within each group. |

For fiber index `f`, the corresponding orientation codes occupy the half-open array slice

$$
[\text{offsets}[f],\text{offsets}[f+1]).
$$

Its size is the difference of those offsets. This representation retains all inverse witnesses and supports direct within-fiber selection without reconstructing any tournament.

Construction visits codes in increasing order, computes their cyclic words once, and appends each code to its signature bucket. It then sorts the distinct signatures and concatenates their already ordered buckets. The resulting inverse order is **increasing signature, then increasing orientation code within that signature**. It is not the global numeric order of all orientation codes.

Because the entire finite orientation space was enumerated, an absent signature has zero representing labeled tournaments for that vertex count. No partial-prefix absence is reported as global impossibility.

## Mathematical relationships used by the reader

### Global reversal

Global reversal complements every one of the `E` edge bits:

$$
\operatorname{rev}(x)=(2^E-1)-x.
$$

It reverses every directed cycle and every transitive triple while preserving which type each triple has. Consequently, it maps each inverse fiber to itself.

Within one fiber of size `f` sorted by increasing code, complementation reverses the order, so rank `r` maps to rank `f-1-r`. It has no fixed orientation: `2^E-1` is odd and cannot equal twice an integer code. Every nonempty fiber therefore has even cardinality.

This order reversal applies within a single fiber. It does not reverse a view's ordering across several different signatures.

### Transitive subsets and their orders

A tournament is transitive if and only if it contains no directed triangle. One proof is to take a shortest directed cycle: if its length exceeds three, a chord either gives a directed triangle or a shorter directed cycle. Thus the absence of triangles forces acyclicity. A topological order then orients every pair consistently and is unique.

Let `w` be a realizable cyclic signature and `M(S)` the saved mask of triples inside a vertex subset `S`. Then

$$
S\text{ is transitive}\quad\Longleftrightarrow\quad w\,\&\,M(S)=0.
$$

This property depends only on the cyclic signature, so the same transitive subset catalog applies to every orientation in its fiber. The reader evaluates these new mask intersections from saved words; it does not recompute individual triple orientations.

To obtain the actual order, `transitiveOrder` decodes only the selected orientation's edges inside the subset. For a transitive subset of size `s`, its within-subset outdegrees are exactly `s-1,s-2,...,0`. Sorting by decreasing within-subset outdegree gives the unique order, and the method retains the scores and checks that shape.

Whole-tournament outdegrees are not used in place of within-subset outdegrees. A nontransitive subset returns its nonzero cyclic subword and no order.

### Four-vertex obstruction and a proper construction family

Every transitive triple has a unique vertex pointing to its other two vertices. For a tournament on four vertices with outdegrees `d_v`, this gives

$$
\#\{\text{cyclic triples}\}=4-\sum_v\binom{d_v}{2}.
$$

For each nonnegative integer `d`,

$$
\binom d2\ge d-1.
$$

The four outdegrees sum to six, so the sum of binomial coefficients is at least two. Hence there are at most two cyclic triples. In particular, a red `K4^(3)` cannot occur in this construction.

The converse fails. On four vertices, a three-uniform hypergraph with exactly three red triples is red-`K4^(3)`-free but cannot be a tournament cyclic-triple image. The delivered query uses signature `19`: bits `0,1,4` are one, giving triples `012,013,023`, while `123` is blue. Every other triple on the six labels is blue. There are only three red triples, so no red four-vertex complete hypergraph exists; nevertheless its first four labels already violate the two-cycle bound. The complete inverse index returns no orientation.

This is a finite structural restriction of the credited construction family, not a statement about all two-color hypergraphs.

### Maximum cyclic-triple count on six vertices

For six vertices the same source-vertex count gives

$$
\#\{\text{cyclic triples}\}=20-\sum_v\binom{d_v}{2},\qquad
\sum_v d_v=15.
$$

For every integer `d>=0`,

$$
\binom d2-(2d-3)=\frac{(d-2)(d-3)}2\ge0.
$$

Thus the sum is at least `2*15-3*6=12`, and at most eight triples can be cyclic. The recorded constructor attains eight, with first code 280. This elementary finite bound explains the observed maximum; it makes no asymptotic Ramsey assertion.

### Partial signatures

A partial coloring specifies two disjoint sets of triple IDs: required cyclic and required transitive. A complete signature `w` matches when

$$
(w\,\&\,C)=C,\qquad (w\,\&\,B)=0,
$$

where `C` and `B` are the respective masks.

Every orientation lies in exactly one full-signature fiber. Summing the sizes of the compatible fibers therefore counts matching orientations without duplicates. The reader saves the selected fiber indices and their cumulative orientation counts as a pattern view.

A pattern view uses the same grouped order: increasing complete signature, then increasing code within that signature. Binary search in its cumulative counts selects the containing fiber; the remainder is the within-fiber rank. Ranking performs the inverse lookup.

If the requirements prescribe both colors for a triple, the method returns an explicit contradictory mask and an empty view without scanning the fibers. Repeated IDs within one requirement array are invalid input. Both requirements are explicit arrays, which may be empty.

## Actual six-label results

The source was first constructed at **2026-10-04T22:02:06.388Z**. It retained 15 edge descriptors, 20 triple descriptors, 15 quadruple descriptors, and all 64 vertex-subset descriptors.

The complete orientation space has 32,768 elements. Its 8,563 signatures lie inside a full space of `2^20` possible red/blue triple words. This ratio describes the labeled tournament image, not the fraction of red-`K4^(3)`-free hypergraphs that are representable.

### Orientation counts by cyclic triples

| Number of cyclic triples | Labeled orientations |
|---:|---:|
| 0 | 720 |
| 1 | 960 |
| 2 | 2,240 |
| 3 | 2,880 |
| 4 | 6,240 |
| 5 | 3,648 |
| 6 | 8,640 |
| 7 | 4,800 |
| 8 | 2,640 |
| 9 through 20 | 0 |

### Fiber-size distribution

| Orientations in a fiber | Number of signatures |
|---:|---:|
| 2 | 5,160 |
| 4 | 2,772 |
| 8 | 280 |
| 16 | 105 |
| 24 | 210 |
| 48 | 35 |
| 720 | 1 |

The unique size-720 fiber is signature zero: every triple is transitive, and the labeled total orders give its `6!` orientations. These are distinct labeled orders, not one quotient class.

The first maximum-cyclic orientation is code 280, signature 53,732. That signature's fiber is index 2,307 and contains four orientations, from code 280 through code 32,487. Its complete inverse slice is retained.

The transitive-subset counts for that signature, from subset size zero through six, are

~~~text
[1, 6, 15, 12, 3, 0, 0]
~~~

Its maximum transitive size is four. The three maximum vertex masks are `15,30,60`. For the first of these, the selected orientation's order is `[3,2,1,0]`.

### Selected saved-consumer results

The all-transitive fiber's rank 359 is orientation code 16,383, with full vertex order `[0,1,2,3,5,4]`. Its global reversal is code 16,384 at rank 360 in the same 720-element fiber.

For the partial pattern with cyclic IDs `[0,10]` and transitive IDs `[1,4]`, the required masks are 1,025 and 18. It has 623 matching full signatures and 2,048 orientations. The view is retained at session zero, query ten.

Grouped rank 777 selects orientation code 31,521 with signature 66,569. It belongs to global fiber index 2,420, at within-fiber rank one and view-fiber position 187. The separate rank query returns 777 using the saved view's prefix counts. The last eight entries of that view are also retained in the reader history.

## Public API

The frozen CommonJS export contains `SCHEMA`, `LIMITS`, `compileTournamentFibers`, and `openTournamentFibers`. The compiler returns a copied plain JSON record. The reader returns a frozen method object; method results and exported snapshots are copies, so changing them does not modify the internal index.

### Compile a genuinely new bounded input

~~~js
const { compileTournamentFibers } = require("./tournament_fibers.cjs");

const index = compileTournamentFibers({
  source_id: "my-new-tournament-space",
  vertices: 6
});
~~~

`vertices` must be an integer from three through six. `source_id` must be a nonempty string of at most 512 characters. Labels are fixed integers zero through one less than the vertex count. The compiler visits the complete orientation space in one bounded call and returns no unfinished frontier.

The delivered six-label index has already been computed. A consumer can inspect it directly through the saved-reader route instead of invoking this constructor again.

### Open the delivered index

~~~js
const { openTournamentFibers } = require("./tournament_fibers.cjs");
const evidence = require("./six_vertex_fibers.json");

const reader = openTournamentFibers(evidence.saved, {
  source_id: "my-distinct-index-consumer"
});

const fiber = reader.findFiber({ signature: 0 });
const chosen = reader.selectFiber({ signature: 0, rank: 359 });
const order = reader.transitiveOrder({
  orientation_code: chosen.orientation_code,
  vertex_mask: 63
});
~~~

A new opening preserves the original source/request and adds a session under a distinct session source ID. Reusing an existing session source ID is rejected. The original vertex count and encoding cannot be replaced through a saved opening.

The examples are caller instructions. They were not additional invocations used to produce the shipped receipt. The module itself performs no filesystem access.

### Method reference

| Method | Arguments | Result |
|---|---|---|
| `findFiber` | `{signature}` | Exact existence/count and first/last orientation codes, or zero witnesses in the complete finite space. |
| `pageSignatures` | `{offset,limit}` | Ordered fiber descriptors. |
| `getOrientation` | `{orientation_code}` | Saved cyclic word and a newly decoded list of all directed edges. |
| `pageFiber` | `{signature,offset,limit}` | Ordered orientation codes and ranks in one fiber. |
| `selectFiber` | `{signature,rank}` | Orientation code at a zero-based within-fiber rank, or an explicit out-of-range/absent result. |
| `rankFiber` | `{signature,orientation_code}` | Membership and within-fiber rank, or the observed different signature. |
| `reverseOrientation` | `{orientation_code}` | Complemented code, retained matching signature, original rank, and reversed within-fiber rank. |
| `transitiveSubsets` | `{signature}` | All vertex-subset classification rows for a realizable signature, counts by size, maximum size, and all maximizing masks. |
| `transitiveOrder` | `{orientation_code,vertex_mask}` | Unique order and within-subset scores, or a nonzero cyclic-subword obstruction. |
| `createPatternView` | `{required_cyclic,required_transitive}` | Saved compatible-fiber list, cumulative orientation counts, total count, and a stable history reference. |
| `selectPatternOrientation` | `{view,rank}` | Orientation at a zero-based rank in a saved pattern view's grouped order. |
| `rankPatternOrientation` | `{view,orientation_code}` | Pattern membership and grouped rank. |
| `pagePatternOrientations` | `{view,offset,limit}` | A bounded page in the pattern's grouped order. |
| `summary` | None | Copies counts, observed maxima/histograms, work, opening checks, and export-budget totals; adds no event. |
| `snapshot` | None | Copies the full index and all sessions/events; adds no event. |

Codes, signatures, vertex masks, indices, offsets, limits, and ranks are Numbers and must be safe integers. Signatures may be any integer in the full `2^T` triple-word space, including unrealizable words. Orientation codes must lie in the complete `2^E` orientation space. A rank may be any nonnegative safe integer; a rank beyond a finite count returns a normal negative result.

Pages require an offset from zero through the total and a limit from one through 64. Offset equal to the total gives an empty final page. Results contain `offset`, `total`, `records`, and `next_offset`. A null next offset means that particular ordered collection is exhausted. It is not a global search-completeness signal; the index's separate complete-space flag supplies that scope.

A missing signature's fiber can be paged at offset zero, returning an empty collection. `transitiveSubsets` requires a realizable signature before interpreting its subsets as tournament subsets; an unrealizable word receives an explicit negative result. `transitiveOrder` always starts from an actual indexed orientation code.

### Pattern-view references

A pattern view is stored as the result of its `createPatternView` event. Its reference is

~~~js
{ session_id: 0, query_id: 10 }
~~~

for the view created in the delivered reader. A later opening preserves those existing session and query IDs. It may add new views under its new session ID.

For example, the delivered view can be consumed with:

~~~js
const picked = reader.selectPatternOrientation({
  view: { session_id: 0, query_id: 10 },
  rank: 777
});
const page = reader.pagePatternOrientations({
  view: { session_id: 0, query_id: 10 },
  offset: 2040,
  limit: 8
});
~~~

The reference must point to a successful retained `createPatternView` result bound to the same original source. It is not an arbitrary caller-supplied list of fibers. A view's order remains increasing signature followed by increasing orientation code within each signature.

Creating a view scans each saved distinct signature at most once and stores its exact matching fiber indices and prefix counts. Subsequent rank/select/page operations reuse those saved lists and prefixes. They do not rescan all signatures or regenerate orientations.

## Reader isolation and exact export-budget accounting

Saved opening makes one full bounded copy of the supplied record and validates its structures. The reader then keeps the fixed index internal. Query handlers read that index and construct new results; they do not mutate it.

For each query, the implementation copies the arguments, prepares a complete result/event record, and prepares the separate caller result before committing. It checks that adding the event preserves the full snapshot's copy limits and that accumulated work counters remain safe integers. Only then does it append the event and update the fixed-shape scalar counters.

The occupancy ledger counts the same JSON-value visits and string/key characters as the full-copy routine. Appending an event contributes exactly that event's counts. Replacing existing Number counter values changes neither the number of visited values nor string/key character totals. New-session and event nesting depths are included explicitly. Sparse arrays are rejected, so unvisited holes cannot evade this accounting.

This arrangement gives ordinary queries isolation and complete receipt retention without copying all forward words or inverse codes on every call. Result-size and algorithm costs still apply. The full `snapshot` operation intentionally copies the whole retained record.

If a query operation throws, it tries to retain an error event and the work attempted so far. If the failure event would itself exceed the budget, the prior committed state remains intact and the thrown error records the retention failure. Checks made before operation entry, such as an exhausted session or malformed argument object, may fail without adding an event.

Normal negative consumer outcomes—an unrealizable signature, a code in another fiber, an out-of-range rank, a nontransitive subset, or contradictory partial requirements—are represented in result records. Invalid IDs, repeated constraint IDs, malformed objects, exhausted limits, and invariant failures throw errors with a `code`.

The exact budget refers to visited JSON values and literal string/key characters, **not serialized byte size**. Rendered digits of Number values are not counted as string characters. The separate file byte identity describes the actual JSON text.

After the actual 15 queries, the reader's complete snapshot occupied 86,202 counted values, 17,544 literal string/key characters, and maximum depth eight. All query receipts fit before their commits, and the full final snapshot was exported successfully.

## Saved-opening assurance

The loader checks structural identity and references, including:

- Schema, original source/request binding, bounded vertex count, and expected finite universe sizes.
- Complete edge/triple/quadruple/subset array lengths and bounded IDs, masks, vertices, and descriptors.
- Lexicographic edge and triple order and each triple's references to its three edge descriptors.
- Exactly one bounded cyclic word for every orientation code.
- Strictly increasing signatures, cumulative endpoints, nonempty fibers, increasing codes within each fiber, and a global permutation of all orientation codes.
- Every inverse code's equality with its saved forward word.
- Complete-space summary bindings, nonnegative safe integer work fields, distinct session sources, and bounded query histories.
- Saved pattern-view source/reference bindings, ordered fiber indices, prefix endpoints, and each retained fiber weight.

These checks establish an internally linked record. They do not recompute the cyclic predicate, enumerate orientations, rebuild the inverse buckets, rederive subset triple-membership masks, authenticate every historical result, or re-establish the claimed construction histograms and extrema.

The loader's explicit output includes zero replay/rebuild counters and `mathematical_proof_authenticated:false`. Numerical semantics remain the retained-constructor premise. Externally edited snapshots need separate source authentication before their mathematical claims are trusted.

The actual saved opening inspected:

| Check | Actual count |
|---|---:|
| Edge descriptors | 15 |
| Triple descriptors | 20 |
| Quadruple descriptors | 15 |
| Vertex subsets | 64 |
| Forward words | 32,768 |
| Fibers | 8,563 |
| Inverse-code / forward-word bindings | 32,768 |
| Other counted reference checks | 8,995 |
| Earlier pattern-view bindings | 0 |
| Orientations re-enumerated | 0 |
| Cyclic triples reclassified | 0 |
| Inverse index rebuilt | 0 |
| Independent proof authentication | No |

There were no earlier sessions at this opening. The pattern view was created afterward by the reader. A further opening of a history-containing snapshot, including the pattern-view validation branch, was not executed as an additional verification run.

## Bounds and complexity

| Resource | Limit |
|---|---:|
| Vertex count | 3 through 6 |
| Page limit | 64 |
| Sessions in one snapshot | 24 |
| Events per session | 128 |
| Source ID length | 512 characters |
| Copied JSON-value visits | 4,000,000 |
| Copied string/key characters | 32,000,000 |
| Copy nesting depth | 48 |

These limits work together. A large history or deep argument/result record can hit a copy bound before a session or event count is exhausted. An empty result does not exempt a call's arguments and receipt from the budget.

Write `E=binom(n,2)`, `T=binom(n,3)`, `N=2^E`, and `F` for the number of distinct signatures. The constructor performs `N*T` cyclic-triple classifications and builds `N` inverse code entries. It also builds all `2^n` subset descriptors and their triple masks. Signature sorting contributes its actual comparison count; sorting costs are separate from the complete orientation loop.

The fixed representation uses `N` forward words, `N` inverse codes, `F` signatures, `F+1` offsets, and the bounded topology descriptors. No list of every directed edge or triple bit is expanded for every orientation.

Fiber lookup takes a binary search over signatures. A selected orientation code is then a direct offset lookup. Ranking uses an additional within-fiber binary search. Pattern creation scans `F` signatures once; later selections use the stored prefix list, and ranking uses the saved fiber membership and code order.

A transitive-subset query performs `2^n` mask intersections. Extracting one subset's order decodes only its contained edges and sorts at most `n` scores. These are new consumer operations on saved data, explicitly counted below.

Public-query costs include cloning arguments, results, and the new event. They do not include a full fixed-index clone per query. Saved opening and explicit snapshot export do copy and scan the complete record. No timing below is a distribution, throughput guarantee, or native-runtime measurement.

## Actual computation and reader work

### Complete constructor work

| Declared operation | Actual count |
|---|---:|
| Edge descriptors | 15 |
| Triple descriptors | 20 |
| Quadruple descriptors | 15 |
| Quadruple-face references | 60 |
| Vertex-subset descriptors | 64 |
| Subset vertex-bit reads | 384 |
| Subset/triple containment checks | 1,280 |
| Orientations enumerated | 32,768 |
| Edge-bit extractions for cyclic classification | 1,966,080 |
| Cyclic-triple classifications | 655,360 |
| Predicate comparison tests | 983,040 |
| Cyclic signature-bit updates | 163,840 |
| Cyclic-count histogram updates | 32,768 |
| Inverse bucket insertions | 32,768 |
| Signature-sort comparisons | 55,950 |
| Inverse codes appended | 32,768 |
| Final inverse fibers | 8,563 |
| Inverse prefix-count additions | 8,563 |

The comparison count records the predicate's actual short-circuit path: equality of the two consecutive-edge bits is checked first, then the third-bit inequality only when needed. Every triple's final Boolean value is preserved in its orientation's cyclic word.

The sort comparison count is an observed implementation count in the connected V8 runtime. It is not a mathematical constant for all JavaScript engines or a bound on every low-level operation.

### The fifteen saved-reader events

The fresh reader opened at **2026-10-04T22:03:23.893Z**.

| Query ID | Method | Actual consumer |
|---:|---|---|
| 0 | `getOrientation` | Decodes all 15 edges of first maximum-cyclic code 280; retrieves signature 53,732. |
| 1 | `findFiber` | Finds signature 53,732, fiber 2,307, count four. |
| 2 | `pageFiber` | Returns the first 12 orientation codes of signature zero. |
| 3 | `selectFiber` | Selects rank 359 in signature zero: code 16,383. |
| 4 | `rankFiber` | Ranks code 16,383 in that fiber: 359. |
| 5 | `reverseOrientation` | Complements it to code 16,384 at rank 360. |
| 6 | `transitiveOrder` | Extracts full order `[0,1,2,3,5,4]` for code 16,383. |
| 7 | `transitiveSubsets` | Returns all 64 subset rows for signature 53,732 and its three maximum masks. |
| 8 | `transitiveOrder` | Extracts order `[3,2,1,0]` on mask 15 for code 280. |
| 9 | `findFiber` | Finds no representing orientation for signature 19. |
| 10 | `createPatternView` | Saves 623 compatible fibers and 624 prefix endpoints, totaling 2,048 orientations. |
| 11 | `selectPatternOrientation` | Selects grouped rank 777: code 31,521, signature 66,569. |
| 12 | `rankPatternOrientation` | Returns grouped rank 777 for that code in the saved view. |
| 13 | `pagePatternOrientations` | Returns the final eight orientations of the saved view. |
| 14 | `pageSignatures` | Returns the final 12 inverse fiber descriptors. |

Each event retains its exact arguments, complete result, and declared work. Selecting an orientation and subsequently ranking it are separate consumer operations; the second operation is counted and is not presented as a free verification of the first.

The 44 returned-record count is at method/page-row level. It does not count every nested directed edge, scalar, or row inside an individual composite result.

### Reader work totals

| Declared operation | Actual count |
|---|---:|
| Queries | 15 |
| Binary-search steps | 233 |
| Saved orientation-word reads | 7 |
| Newly decoded orientation edge bits | 36 |
| Fiber descriptors/weights read | 636 |
| Signature-mask checks | 9,186 |
| Subset-mask checks | 66 |
| Saved fibers scanned for pattern creation | 8,563 |
| Pattern prefix-count additions | 623 |
| Within-subset outdegree increments | 21 |
| Order-sort comparisons | 14 |
| Order-score shape checks | 10 |
| Reversal complements | 1 |
| Required constraint bits set | 4 |
| Constraint-overlap checks | 1 |
| Method-level returned records | 44 |
| Orientations enumerated | 0 |
| Cyclic triples reclassified | 0 |
| Inverse index rebuilt | 0 |

The reader performs real new mask, count, search, reversal, and orientation-order work. Zero replay counters refer specifically to regenerating the original orientation/triple map or inverse buckets. They do not imply that the saved reader performs no computation.

Counters record the named operations in the implementation. Ordinary Number index arithmetic, JSON copying, allocation, loop mechanics, module evaluation, and other engine instructions are not exhaustively counted.

### Single timing observations

| Operation | Observed wall-clock duration |
|---|---:|
| Complete six-vertex constructor | 150 ms |
| Fresh saved opening | 31 ms |
| Fifteen-query loop, including local receipt retention | 7 ms |

Individual public calls recorded zero or one millisecond at the available wall-clock resolution. Zero means below that resolution during the observation, not zero runtime. The query-loop number includes local call-receipt retention but not the final full snapshot export. These are single observations, with no benchmark distribution or native-runtime claim.

## Data layout and complete custody

The 676,846-byte JSON file contains one complete fixed index, plus all 15 reader events. Long primitive arrays are line-wrapped while preserving every entry and its original order. Their positional meanings are defined by the encoding and offset arrays.

| JSON location | Contents |
|---|---|
| `implementation` | Executed source path, byte count, Git blob identity, and source-freeze statement. |
| `execution` | Original constructor/reader requests, actual start timestamps, and execution scope. |
| `construction_receipt` | Actual constructor result, complete declared work, topology counts, and timing. |
| `saved.topology` | Every edge, triple, quadruple, and vertex-subset descriptor. |
| `saved.forward.cyclic_words` | All 32,768 orientation-indexed cyclic words. |
| `saved.inverse.signatures` | All 8,563 observed signatures in order. |
| `saved.inverse.offsets` | All 8,564 inverse boundaries. |
| `saved.inverse.orientation_codes` | All 32,768 inverse witnesses in grouped order. |
| `saved.result` | Complete count histograms and the retained observed maximum/largest-fiber metadata. |
| `saved.construction_work` | Full original construction counters. |
| `saved.sessions[0].queries` | All 15 exact arguments, results, and per-query work records. |
| `saved.sessions[0].queries[10].result` | Complete partial-pattern view, all compatible fiber IDs, and all prefix counts. |
| `reader_receipt` | Opening and final summaries, timing observations, and per-call timing rows. |
| `custody` | Literal identity comparisons of every fixed-index field across the saved reader. |

All nine fixed-index fields—schema, original source, request, conventions, topology, forward map, inverse arrays, result metadata, and construction work—were compared literally before and after the reader. Every comparison matched. The constructor had zero sessions; the final record has the one new reader session.

Those comparisons are serialization and source-custody checks. They do not re-enumerate orientations, recalculate cyclic triples, or independently authenticate the mathematical construction. JSON formatting was separately checked for exact parsed-value identity; formatting changed no result.

## Static review, actual execution, and unexercised branches

Before the first computation, the source was parsed and statically inspected, including the fixed bit widths, source/index bindings, fiber/view ordering, and event commit boundaries. Concrete pre-execution adjustments added explicit constraint-mask counters, rejected sparse arrays, checked accumulated work-counter bounds before commit, and guarded saved pattern-reference objects.

The six-vertex constructor and the fresh 15-query reader then ran once using the same frozen source. There was no constructor retry, query error, alternate implementation, cyclic-classification replay, or inverse-index rebuild. All actual outputs and work records are retained.

The public three-, four-, and five-vertex constructor branches were not separately executed. Nor were invalid-input failures, duplicate/contradictory constraint handling, nontransitive-order rejection, event/session exhaustion, copy-budget failures, or history-containing saved reopening added as extra fixture runs. The actual negative realizability query for signature 19 is a retained consumer result, not a substitute for exercising those other branches.

The guide's triple-ID table is formatted from the retained topology descriptors. No classification was repeated to produce that table.

Publication verification concerns the complete delivered texts, their Git blob identities, changed paths, requested-revision readbacks, and PR metadata. It does not expand the executed mathematical scope or turn a structural saved opening into an independent proof verifier.

The contribution supplies an exact finite inverse image of a credited construction, explicit witnesses, reusable saved views, and new finite consumer arithmetic. It makes no claim that six-vertex statistics extrapolate to the double-exponential target, that its label classes are isomorphism classes, or that its finite results establish prize eligibility.
