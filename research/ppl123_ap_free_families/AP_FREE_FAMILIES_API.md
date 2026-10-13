# Complete finite families without arithmetic progressions

This contribution represents every subset of an integer interval that avoids a fixed-length arithmetic progression. It preserves the complete family, its counts by cardinality, all earlier interval roots, and the actual construction and query receipts. A saved reader can locate a member by rank, rank a supplied member, page sets of a chosen size, inspect a progression obstruction, or map a member by reflection or an injective affine transformation.

The recorded case has `k = 3`. Its final complete interval is `[1,25]`, containing **140,840 admissible subsets**. Their maximum size is **10**, and there are **33 sets of that size**. All 33 appear in the saved reader's event 3. The source first completed `N=18`, then opened that record and extended it through `N=25`. An attempt at point 26 exceeded the coefficient-storage limit and was rolled back. No complete `N=26` family, or result for 27 or 28, is reported.

The result is a finite census with a reusable API. It is not an asymptotic formula, a new extremal-record claim, or a prize submission.

## Files and identities

| File | Purpose | Git blob / bytes |
|---|---|---|
| `ap_free_families.cjs` | Dependency-free CommonJS implementation | `653954fa143241bfc9d90568fdeb828f77264bc0` / 40,316 |
| `three_term_families.json` | Complete final record, execution context and literal-custody results | `727f1781f4912f36430c82350b5b4acb83ef78bc` / 657,608 |
| `AP_FREE_FAMILIES_API.md` | Mathematical argument, interface, evidence and limits | This guide |
| `README.md` | Entry point and compact result summary | Companion file |

The operation identity is `ERDOS142-AP-FREE-FAMILY-ZDD-20261004-7CA6`. It remains unchanged across the UTC date boundary during documentation and delivery.

## Mathematical contract

For fixed integers `k >= 3` and `N >= 0`, define the forbidden subsets

$$
\mathcal H_{k,N}
=
\{\{a,a+d,\ldots,a+(k-1)d\}:a\ge1,\ d\ge1,\ a+(k-1)d\le N\}.
$$

The represented family is

$$
\mathcal F_{k,N}
=
\{A\subseteq[1,N]: P\nsubseteq A\text{ for every }P\in\mathcal H_{k,N}\}.
$$

Progressions are in the integers. Positive difference removes reverse duplicates; there is no modular wraparound. The empty set is a member. Every admissible subset is retained separately, including smaller sets. There is no quotient by reflection, translation, dilation, or graph isomorphism.

The extremal size `r_k(N)` is the maximum cardinality in this family. The definition agrees with Leng, Sah and Sawhney's primary paper [1]. The July 2026 preprint of Morris, Ortega and Rué [2] studies the number of all such sets, distinguishes that count from `r_k(N)`, and states that precise extremal asymptotics remain unresolved. It gives asymptotic family-count bounds; this implementation does not reproduce those theorems. The separate canonical Erdős 142 page returned HTTP 403 during qualification. No current award eligibility is inferred from that inaccessible page or from the older intake card.

### Persistent family representation

The implementation uses a zero-suppressed decision diagram (ZDD). Node 0 denotes the empty family; node 1 denotes the family containing only the empty set. A nonterminal row is

```text
[element, lo_child, hi_child, polynomial_id]
```

Its family consists of the LO child's sets and the HI child's sets with `element` added. A node with HI child 0 is suppressed. Equal LO and HI children are retained: they express optional inclusion. These are standard ZDD semantics [3]. This implementation orders elements **decreasingly**, reversing the presentation order in the referenced notes. Every child has a smaller element and an earlier node ID. Equal triples `(element, LO, HI)` share a node.

The complete pool also retains nodes needed by earlier intervals and intermediate filters. Its 10,630 rows are the size of the retained pool, not a claim about the number of nodes reachable from the final root alone.

### Why extension preserves every admissible set

Let `m=N+1` and write `F = F_{k,N}`. A new progression must have largest element `m`. Its other elements are

$$
R_{m,d}=\{m-d,m-2d,\ldots,m-(k-1)d\},
\quad
1\le d\le\left\lfloor\frac{m-1}{k-1}\right\rfloor.
$$

Filter `F` to obtain the family `G` of sets containing none of those required subsets. Then exactly

$$
\mathcal F_{k,m}
=
\mathcal F_{k,N}\ \cup\
\{A\cup\{m\}:A\in G\}.
$$

The two parts are disjoint according to whether `m` is present. A set in the first part needs no new constraint. In the second part, its old elements already avoid every earlier progression, and the filters exclude precisely the progressions ending at `m`. Conversely, every admissible set belongs to one of these two parts. Starting with $\mathcal F_{k,0}=\{\varnothing\}$ proves the complete-family invariant by induction.

A new root at element `m` therefore uses the **unchanged previous root as LO** and the filtered family as HI. The source does not rebuild the old family. It saves every new-maximum filter's input and output root, in increasing difference order.

The internal `avoidContaining` operation applies the same argument recursively. Its required elements are in decreasing order. If the current diagram has already skipped a required element, all remaining sets are safe. At a required element, the entire LO branch is safe, while HI must avoid the remaining required elements. At an unrelated larger element, both branches retain the same requirement. Exhausting the requirement rejects the family. These cases partition the represented sets, so the operation removes exactly the sets containing the required subset.

### Counting and addressing

For every node the constructor computes and interns its cardinality polynomial:

$$
P(z)=P_{\mathrm{LO}}(z)+zP_{\mathrm{HI}}(z),
\qquad P_0(z)=0,\quad P_1(z)=1.
$$

Coefficient `j` counts represented sets of size `j`. The cached sum of coefficients counts the whole family. The largest nonzero degree gives its maximum size, and that coefficient gives the number of maximum sets. Skipped elements are absent and contribute no extra factor.

Together with the complete-family invariant, this makes the final degree 10 a finite exact `r_3(25)` result for this construction. A single size-10 witness alone would only give a lower bound. The minimum unrestricted size is always zero; “maximum size” here does not mean inclusion-maximal.

Rank order compares membership bits from `N` down to 1, with LO before HI. Ranks start at zero. This differs from lexicographic order on increasing lists of elements. A rank can refer to all represented sets or only sets of one stated cardinality. Branch decisions use cached totals or one saved polynomial coefficient; a set address follows at most `N` nonterminal nodes.

When a new point is added, every old set lies in the new root's LO branch. Thus every old whole-family rank, and every old rank within a fixed cardinality, is preserved. This is a consequence of the representation and ordering, not an empirical extrapolation from the two recorded examples.


## Using the saved record

```javascript
const { openAPFamily } = require('./ap_free_families.cjs');
const evidence = require('./three_term_families.json');
const family = openAPFamily(evidence.record);

const counts = family.histogram({ n: 25 });
const maxima = family.pageSets({ n: 25, size: 10, offset: 0, limit: 64 });
```

These are usage examples. The delivered record already includes the actual 20-query reader session. That final three-session export was not opened again merely to repeat the recorded queries.

The module exports `SCHEMA`, `LIMITS`, `createAPFamily` and `openAPFamily`. The record schema is `commons.ap_free_family/v1`. The evidence wrapper has its own schema, `commons.ap_free_family_evidence/v1`; pass its `record` member to the opener.

`createAPFamily({source_id, k})` creates only the unit family on the empty domain. It does not construct an interval implicitly. `openAPFamily(record)` copies and checks the supplied record, restores node/polynomial identity maps, and appends a new session. Both return a frozen facade over private state. Inputs, snapshots and returned answers are copied; modifying a returned object does not modify the retained record.

### Construction and observation

| Method | Arguments and behavior |
|---|---|
| `advance` | Required `points`; optional `max_new_nodes` and `max_new_polynomial_coefficients`. Extend one point at a time with the same `k`. Defaults use the remaining global capacities. |
| `summary` | No arguments. Return the completed frontier, pool sizes, current session and work totals. No event is appended. |
| `openingWork` | No arguments. Return the current session's opening receipt. No event is appended. |
| `snapshot` | No arguments. Copy the complete record. No event is appended. |

`advance` returns the effective request, completed range, new pool sizes, status, stopped-point details where applicable, and work split into committed construction, discarded-point work, and preparation. A zero-point request is valid. It still creates an event.

Every advance or query result has `reference: {session_id, event_id}` and its work receipt. References are zero-based positions in the saved session history. The stored event also retains the method, actual arguments and result. Invalid arguments and exceptions do not append an event.

### Saved queries

For family queries, `n` defaults to the completed frontier and can name any earlier retained interval. `pageConstraints` has the separate scope rule described below. Omitted or null `size` means the full family. A specified size must be an integer from zero through `n`.

| Method | Required arguments | Optional arguments | Returned information |
|---|---|---|---|
| `histogram` | None | `n` | Full size-count vector, total, maximum size and number of maxima |
| `pageIntervals` | None | `offset, limit` | Complete interval rows, roots, filter spans and completion frontiers |
| `pageNodes` | None | `offset, limit` | Node IDs, elements, children, polynomial IDs and cached totals |
| `pagePolynomials` | None | `offset, limit` | Polynomial IDs, complete coefficient vectors and totals |
| `pageConstraints` | None | `n, offset, limit` | Saved filter transitions and their arithmetic progressions |
| `selectSet` | `rank` | `n, size` | A member and its branch trace |
| `selectMaximum` | `rank` | `n` | A maximum-size member and its branch trace |
| `pageSets` | None | `n, size, offset, limit` | Ranked members, without individual branch traces |
| `rankSet` | `values` | `n, size` | Membership, rank if present, and the traversed path |
| `reflectSet` | `rank` | `n, size` | Source member, reflected member and its rank |
| `affineImage` | `rank, scale, offset` | `n, size` | Source member, element/image pairs and sorted image |
| `findProgression` | `values` | `n` | First contained progression in the saved constraint order, or null |


Paging offsets start at zero, can equal the reported total, and default to zero. Limits default to 64 and can be zero through 64. `next_offset` is null at the end. A zero-length request before the end returns the unchanged next offset; consumers that advance through pages need a positive limit. A requested size with no members produces an empty `pageSets` result. Selecting a rank from that empty size class raises `E_EMPTY_SIZE`.

For `pageConstraints`, omitted `n` means the full retained constraint list. A specified `n` selects only constraints introduced when that point was added. The returned progression is increasing; its saved required subset omits its maximum. This reconstructs the small arithmetic descriptor from its recorded maximum and difference, without running the family filter.

Supplied `values` must be strictly increasing, distinct integers in `[1,n]`. A cardinality-filtered `rankSet` requires their length to equal `size`. An ordinary nonmember returns `member:false` and `rank:null`. This is a query result, not an exception. Its diagram path does not automatically name a progression; `findProgression` scans the saved constraints for an explicit witness.

Reflection uses `v -> n+1-v`. Affine images use `v -> offset+scale*v`, with nonzero scale. Their parameters are canonical signed decimal strings, with at most 128 digits excluding the sign; neither a leading plus nor negative zero is accepted. Arithmetic uses BigInt internally and returns decimal strings. A negative scale reverses order, so the API returns both source/image pairs and an increasing image list. These maps preserve nontrivial integer arithmetic progressions in both directions. The image domain need not itself be `[1,n]`; the operation does not construct a new interval family.

### Complete record layout

The outer record stores `schema`, `source_id`, fixed `k`, `core` and `sessions`.

| Core field | Stored meaning |
|---|---|
| `n` | Largest completed interval endpoint |
| `nodes` | All terminal and nonterminal rows retained by construction |
| `polynomials` | Interned, constant-term-first coefficient arrays |
| `polynomial_totals` | Cached sums aligned with the polynomial rows |
| `polynomial_coefficients` | Total number of stored coefficient entries |
| `constraints` | Rows `[maximum, difference, input_root, output_root]` |
| `intervals` | Root and count summaries for every endpoint from zero to `n`, with complete filter spans and pool frontiers |
| `work` | Committed construction counters; discarded work remains in its advance receipt |

Each session records its ordinal, opening endpoint, opening work, events and query-work totals. Each event retains its position reference, method, arguments, result and work. The evidence file contains **one final complete record**, rather than separate copies of the full core for each phase.

The opener checks dense JSON structures, exact schema fields, integer bounds, terminal rows, node uniqueness, earlier child IDs, decreasing element order, polynomial uniqueness, coefficient sums, interval frontiers, the unchanged-LO spine, complete ordered constraint descriptors and historical event identities. It also checks accumulated historical query-work receipts.

It does **not** rerun the constraint filters or recompute a node's polynomial from its children's polynomials. It therefore checks structural and accounting consistency without authenticating an imported family's mathematical completeness. A claimed source ID or blob identity is not such authentication. The recorded construction's completeness argument is the invariant above, together with the published implementation and its retained execution.


## Actual complete census

One constructor created the unit family. Its first advance completed 18 points. A fresh opener then extended the same record by seven complete points before the resource stop. Every interval row below is retained in the record; the reader retrieved the complete table in session 2, event 2.

| N | All admissible sets | Maximum size | Number of maxima |
|---:|---:|---:|---:|
| 0 | 1 | 0 | 1 |
| 1 | 2 | 1 | 1 |
| 2 | 4 | 2 | 1 |
| 3 | 7 | 2 | 3 |
| 4 | 13 | 3 | 2 |
| 5 | 23 | 4 | 1 |
| 6 | 40 | 4 | 4 |
| 7 | 65 | 4 | 10 |
| 8 | 106 | 4 | 25 |
| 9 | 169 | 5 | 4 |
| 10 | 278 | 5 | 24 |
| 11 | 443 | 6 | 7 |
| 12 | 705 | 6 | 25 |
| 13 | 1117 | 7 | 6 |
| 14 | 1760 | 8 | 1 |
| 15 | 2692 | 8 | 4 |
| 16 | 4151 | 8 | 14 |
| 17 | 6314 | 8 | 43 |
| 18 | 9526 | 8 | 97 |
| 19 | 14127 | 8 | 220 |
| 20 | 20944 | 9 | 2 |
| 21 | 30848 | 9 | 18 |
| 22 | 45589 | 9 | 62 |
| 23 | 66495 | 9 | 232 |
| 24 | 96847 | 10 | 2 |
| 25 | 140840 | 10 | 33 |

The final size-count vector, with coefficient index equal to set size, is

```text
[1,25,300,2156,9706,26996,44290,39332,16061,1940,33]
```

Thus a request for size 11 returns an empty family. The saved maximum-family page contains all 33 members and has no next page. Its first member is

```text
[1,2,5,7,11,16,18,19,23,24]
```

The evidence file carries all remaining maxima, not only this representative.

### Actual saved-data addresses

| Reader events | Request and result |
|---|---|
| 4–5 | Whole-family rank 4,763 at `N=18` selects `[2,4,7,8,11,13,17]`. Its rank at `N=25` is still 4,763. |
| 6–7 | Whole-family rank 70,420 at `N=25` selects `[4,6,7,18,24]`. Its rank among size-5 members is 17,209. |
| 8 | Reflection maps maximum-family rank 16 to rank 14, both at `N=25` and size 10. |
| 9 | The last maximum member, rank 32, is mapped by a large negative integer scale and positive offset. All ten exact decimal pairs and the ordered image are retained. |
| 10–11 | `[1,13,25]` is rejected. Its progression witness is saved constraint 143, with maximum 25 and difference 12. |
| 12 | The size-11 page has total zero. |
| 13–14 | Maximum-family rank 96 at `N=18` selects `[5,6,8,9,14,15,17,18]`. Its rank among size-8 members at `N=25` remains 96. |
| 15–16 | All new-maximum constraints for points 25 and 19 are read from their saved spans. |
| 17–19 | Tail nodes, tail polynomials and the initial six nodes are paged from the record. |

These are addresses into the represented families. They do not recompile an interval or a constraint filter. No second constructor, enlarged-input experiment, independent exhaustive subset loop, or repeated point-26 attempt was performed.

### Resource stop at point 26

The coefficient limit measures stored coefficient **entries**. The complete `N=25` record uses 38,469 entries, 5,618 polynomial rows and 10,630 node rows. During the point-26 attempt, 11 filters completed. The next needed new polynomial had seven entries, while the attempted pool had reached 49,996 entries and had only four slots left.

The source rolled back that entire point: 3,131 tentative nodes, 1,595 tentative polynomial rows, 11,527 tentative coefficient entries, and the 11 completed tentative filter records were removed from the committed core. Their work counts and stop reason remain in session 1, event 0. The last complete interval is still 25, with its previous history unchanged.

The available space after rollback does not establish that the same next point can be completed under the unchanged limit. The delivery does not retry it or increase the limit.

### Work and literal custody

| Construction counter | First 18 points | Committed extension to 25 | Discarded point-26 attempt |
|---|---:|---:|---:|
| Completed points | 18 | 7 | 0 |
| Completed new-maximum filters | 72 | 72 | 11 |
| Filter calls | 3644 | 29205 | 10421 |
| New nodes | 1304 | 9324 | 3131 |
| New polynomial rows | 765 | 4851 | 1595 |
| New coefficient entries | 4686 | 33781 | 11527 |
| Coefficient additions | 6919 | 54432 | 19002 |

The constructor's subset-enumeration counter remains zero. The complete committed core contains 144 constraints and preserves all earlier interval roots.

Literal comparisons established that all 1,306 old node rows, all 767 old polynomial rows and their totals, all 72 old constraints, all 19 old interval rows, and the original session remained unchanged as prefixes after extension. The point-19 root's LO child is exactly the saved point-18 root. The fresh reader then left the entire extended core and both previous sessions unchanged. These are custody comparisons of retained values, not a second mathematical construction.


The fresh reader opened a two-session record containing 10,630 node rows, 5,618 polynomial rows, 38,469 coefficients, 144 constraints and 26 interval rows. It copied 104,166 JSON values while restoring 10,628 node identities and 5,618 polynomial identities. That linear import work is distinct from the subsequent queries.

Across the 20 actual queries, the recorded counters are: 648 node steps, 662 coefficient reads, 69 cached-total reads, 73 saved-row reads, 38 selected-set outputs, 104 returned rows, 515 integer mappings, and 144 saved-constraint scans. Family construction, constraint-filter replay and polynomial recurrence replay are all zero during those queries. The selected-set counter includes the 33 maxima returned by the single maximum-family page.

The observed constructor time was 1 ms and its first advance 10 ms. The saved extension opened in 16 ms and advanced in 59 ms. The reader opened in 99 ms and its query loop took 14 ms. These are **single observations in the connected JavaScript environment**, not benchmarks. Module loading and explicit snapshot/summary retention are outside the construction timings. The reader loop includes retaining its returned results and excludes the final full snapshot. No native Node process, shell execution or workflow was used.

## Bounds and failure semantics

| Bound | Value |
|---|---:|
| Domain endpoint | 48 |
| Fixed progression length | 3 through 8 |
| Retained node rows, including terminals | 16,000 |
| Retained polynomial coefficient entries, including terminals | 50,000 |
| Requested points in one advance | 48 |
| Filter calls in one attempted point | 1,000,000 |
| Page size | 64 |
| Sessions per record | 16 |
| Events per session | 32 |
| Source-ID length | 512 characters |
| Affine parameter digits | 128, excluding a sign |
| JSON-copy value count | 4,000,000 |
| JSON string and key units | 20,000,000 UTF-16 code units |
| JSON-copy nesting depth | 48 |

Family counts, ranks and coefficients use exact safe integer Numbers. Their mathematical maximum under the domain cap is `2^48`. Affine parameters and image values use the separate decimal-string interface described above.

The JSON limits count visited values and string/key units; they are not a serialized UTF-8 byte limit, and the textual digits of JSON Numbers are not included in the string-unit count. The file byte sizes in this guide are separately computed UTF-8 Git-blob identities.

A normal advance can stop because of a global domain, node, coefficient, per-call node/coefficient, or per-point filter-call limit. A completed point is never silently truncated. The implementation prepares private arrays and maps for the advance; a resource stop rolls back only the unfinished point, preserves any earlier points completed in that call, and records the discarded work separately. An unexpected exception commits neither that candidate core nor an event.

The node and coefficient pools have no general small-size guarantee. A larger interval can require substantially more storage. The reported complete endpoint is determined by the actual result, not by the requested endpoint.

Unknown fields, malformed or sparse JSON arrays, unsupported values, accessors, cycles, unsafe integer Numbers, invalid set/rank/size arguments, and exhausted session/event budgets raise `APFamilyError` with a code. They do not create success or error receipts. The delivered execution did not exercise those error paths. The observed coefficient-limit stop is a normal recorded outcome.

The generic `k=4..8` construction branches, other resource-stop paths, session/event exhaustion and invalid-import branches were not executed. The final three-session export, which includes all 20 reader receipts, was not reopened again. Historical query-receipt validation on that final export is therefore a source-inspected path, not an additional claimed runtime observation.

## Research scope and sources

The reusable result is the finite family, its exact cardinality distribution, persistent extension rule, saved construction history and navigation API. It preserves admissible members of every size, because smaller sets can remain important after extension. There is no heuristic restriction to previous maxima.

A larger-interval count, an asymptotic estimate, or a new best-known construction requires additional evidence. This delivery makes no such claim and contacted no author, sponsor or prize administrator.

1. James Leng, Ashwin Sah and Mehtaab Sawhney, *Improved Bounds for Szemerédi's Theorem*, version dated 2024-02-28. [Author-hosted primary PDF](https://www.mit.edu/~asah/papers/2402.17995.pdf). Used for the extremal definition and dated context; its bounds are not presented as a complete survey of later work.
2. Patrick Morris, Miquel Ortega and Juanjo Rué, *Counting subsets of integers free of arithmetic configurations*, arXiv:2607.17746v1, 2026-07-20. [Primary preprint](https://arxiv.org/pdf/2607.17746). Used for the distinction between extremal size and complete-family counting.
3. Ben Lynn, [ZDDs defined](https://crypto.stanford.edu/pbc/notes/zdd/zdd.html) and [Constructing ZDDs](https://crypto.stanford.edu/pbc/notes/zdd/construction.html). Author-hosted notes on the standard representation. The decreasing-order extension and AP-specific filter argument in this guide are derived explicitly above.

All three source groups were inspected on 2026-10-04. The source-status limitation for the canonical Erdős 142 page remains recorded; no alternate retrieval of that failed page or award claim was made.
