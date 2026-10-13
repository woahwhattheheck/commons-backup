# Single-edge C4 repair index

The API adds one missing point–line edge to an identified cyclic projective-plane incidence graph and keeps that edge. It records the newly created four-cycles and represents every smallest set of original edges whose deletion restores C4-freeness. This package contains the one order-13 consumer, its complete cycle and coefficient records, and all 25 saved-reader results.

## Actual result

The accepted plane has 183 points, 183 lines, 14 incidences at each vertex and 2,562 original edges. Point 0 and line 0 are distinct vertices in the two parts and were nonincident. Adding their edge creates 14 four-cycles. Their original length-three paths use 42 distinct edges.

Exactly 14 original edges must be deleted while retaining the inserted edge. There are 3^14 = 4,782,969 minimum repairs. Each repaired graph has 2,549 edges. There are 120 profiles recording the numbers deleted from the point star, middle path positions and line star.

The actual constructor retained 14 cycle records and 680 suffix coefficients using 1,680 coefficient additions. It did not enumerate individual repairs, point pairs, the whole graph or the earlier field and difference calculations. Its observed 1 ms is a single environment observation, not a benchmark.

The fresh reader's 25 queries include:

| Query | Saved result |
| --- | --- |
| Profile (5,4,5) | 252,252 repairs |
| Median zero-based rank 126126 in that profile | Choice word 11112000002222 |
| Two permitted choices per cycle, with profile (5,4,5) | 1,126 repairs |
| Costs 1 + (edge ID mod 5), among minimum repairs | Minimum cost 23, attained twice |
| Inserted point-0–line-0 edge | Present |
| Selected deleted point-4–line-60 edge | Absent |
| Unselected point-4–line-0 edge | Present |
| Other nonincident point-0–line-1 edge | Absent |

The reader built 431 conditional coefficient cells with 675 additions for its requested masks. That is new query work, explicitly retained in the output. It used 321 coefficient lookups, 112 selection steps, 14 rank steps, 42 cost comparisons and four incidence queries. It constructed no new cycle rows or base coefficients and replayed no field or old difference equations.

## Files and use

- `single_edge_c4_repair.cjs`: dependency-free CommonJS constructor and saved reader.
- `point0_line0_repairs.json`: input premises, full constructor result, every reader request/result, complete conditional tables and work counters.
- This guide and `README.md`.

The snapshot is at `package.construction.snapshot`; all queries are at `package.retained_reader.queries`. Coefficient tables and cycle rows are complete, not samples.

```js
const fs = require("node:fs");
const { openC4Repairs } = require("./single_edge_c4_repair.cjs");
const record = JSON.parse(fs.readFileSync("./point0_line0_repairs.json", "utf8"));
const index = openC4Repairs(record.construction.snapshot);

const count = index.count({ profile: [5, 4, 5] });
const repair = index.select("126126", { profile: [5, 4, 5] });
const rank = index.rank(repair.deleted_edges.map(e => e.id), { profile: [5, 4, 5] });
```

This example illustrates the public interface. It is not an additional computation claimed by the package. Opening a snapshot copies and structurally checks the supplied records; it does not recalculate the construction.

## Input contract and inherited premise

`compileCyclicPlaneRepair(input)` accepts:

- `modulus`: integer N from 3 through 4,096.
- `difference_set`: 3 through 64 strictly increasing residues in [0,N). With q = length − 1, N must equal q²+q+1.
- `point`, `line`: labels in [0,N) for a missing incidence.
- `selected_difference_rows`: exactly one accepted difference witness for each required nonzero difference.
- `premise`: source identity and the mathematical property being consumed.

The intended premise is a planar difference set: every nonzero residue has a unique ordered expression `to − from` using its members. The parameter shape, distinct residues and supplied row layout do not by themselves prove that premise. The constructor does not test prime powers, build a field, audit all differences or certify arbitrary user-supplied claims.

Here the exact accepted source is:

- Commons #31474, `research/ppl088_erdos30_singer_plane/prime13_singer_plane.json`.
- Pinned commit `8a113ba792d9a9d674a5d8b0af7f78c079f846c7`.
- Source data blob `5561a91eddf8cfd7911641702b60cd51e308078d`, 181,456 bytes.
- Difference set [4,7,32,50,52,61,85,91,101,108,122,123,127,135].

That full source was read once and matched by provider and independent Git blob identity. This operation copied its literal difference set and only the 14 required existing witness rows. It checked the row locators, not their old arithmetic equations, and did not invoke the old compiler or reader.

Line v contains points v+d modulo N for d in D. For inserted (u,v), each x=v+d on line v has x≠u. Its accepted difference row satisfies x−u=to−from, so the joining line through u and x is u−from modulo N. The new constructor forms this joining-line offset and the three original edge records. For point0/line0, the first selected difference is 4 with from123/to127, giving joining line60.

An edge ID is point*N+line. Points and lines have separate types; their equal integer labels do not merge vertices. All edges are unordered graph edges encoded once by their point and line endpoints.

## Why the repair family is exact

Let H be any simple bipartite C4-free graph and add a missing edge uv across its two parts. Any four-cycle in the enlarged graph must use uv: a cycle avoiding it would already be in H. Removing uv from such a cycle leaves an old length-three path u–b–x–v.

Two different such paths cannot share b, since their two distinct internal points together with b and v would form an old four-cycle. They cannot share x, since their two distinct internal lines together with u and x would form an old four-cycle. The paths therefore have distinct internal vertices and pairwise disjoint old edges.

A repair retaining uv must delete at least one edge from each path. Choosing one of its three old edges for every path destroys every new four-cycle. Deleting edges creates no cycles, so this is sufficient. With t paths, minimum size is t and there are exactly 3^t minimum repairs. An inclusion-minimal repair also selects exactly one from each path: an extra selection or an edge outside these paths could be restored without leaving a cycle. This statement concerns deletion of original edges while keeping uv.

For the accepted plane there are 14 points on line0 and one joining line through point0 and each. These give all the possible new cycles. The constructor records them rather than searching all vertex quadruples.

The generic graph reasoning explains the capability. The implemented constructor specializes it to the identified cyclic-plane input contract; it does not accept an arbitrary graph adjacency list.

## Order, profiles and saved coefficients

Cycles follow the supplied increasing D order. In each cycle, type 0 is the edge at the inserted point's star, type 1 is the middle old edge, and type 2 is the edge at the inserted line's star. Choices are ternary words in lexicographic order 0 < 1 < 2; ranks start at zero.

A profile (a,b,c) counts the chosen types and sums to t. For suffix i, each coefficient row `[a,b,count]` represents that suffix's choices with a type-0 and b type-1 deletions; type2 has count t−i−a−b. Tables are sorted by a then b. The empty suffix has one empty choice.

For permitted type masks m_i, the suffix generating polynomial is the product of (z0 when bit0 is set) + (z1 when bit1 is set) + (z2 when bit2 is set). Coefficients are built backwards by adding permitted terms. Unrestricted masks are all7 and use the saved constructor tables. Other masks form fresh conditional tables once per reader context; `conditioningData` returns them completely.

Masks 0 through7 are accepted. A zero mask gives an empty family, so counts are zero and selection has no valid rank. The actual reader uses three contexts: unrestricted, the supplied two-choice masks and the cost-minimizing masks. Full tables for both nontrivial contexts are retained. They are not claimed to have been precomputed in the constructor.

## Public methods

| Method | Meaning |
| --- | --- |
| `summary()` | Copy of the finite summary |
| `cyclesPage(start=0,limit=32)` | Complete cycle rows in pages |
| `profilesPage(start=0,limit=32)` | Unrestricted full-length profile counts |
| `count({allowed,profile}={})` | Count permitted repairs, optionally with a profile |
| `countPrefix(prefix,options={})` | Count extensions of a ternary choice prefix |
| `select(rank,options={})` | Repair at zero-based rank, edges and full branch trace |
| `rank(edgeIDs,options={})` | Rank an unordered collection containing one edge per cycle |
| `witness(choices)` | Selected edges and the cycle blocked by each |
| `edgeStatus(point,line,choices)` | Incidence status after the selected repair |
| `minimumCost(costs,allowed=null)` | Independent minimum per-cycle costs and all tie masks |
| `conditioningData(allowed=null)` | Complete coefficient tables for the mask context |
| `statistics()` | Structural-opening and query counters |

Options `allowed` contain t bit masks; omitted or null means all7. Options `profile` are omitted/null for all profiles or a triple of nonnegative integers summing to t. Selection ranks and returned counts are decimal strings. Safe nonnegative integer ranks are accepted, but decimal strings avoid rounding. Rank input is an array of t distinct original edge IDs selecting exactly one per cycle. A disallowed choice or profile mismatch returns `valid:false`; malformed or unknown edges throw.

Pages have a start in [0,total] and limit in [0,64]. A zero-length page is allowed and may leave the same next offset. A full choice string has t characters from 0,1,2; prefixes may have any length from zero through t. No graph-isomorphism quotient or color-label quotient is applied.

Costs are nonnegative integers, with a triple for each cycle. `minimumCost` minimizes weight within cardinality-minimum repairs, optionally under masks. It does not optimize arbitrary superfluous deletions, or couple costs to a requested global profile. Infeasible masks return a zero count and null minimum. Tied minimum choices give a product of independent masks, which can be navigated using the usual count/select API.

The API permits decimal inputs up to 100 digits and snapshot strings up to 12,000,000 characters. Each reader admits at most 64 mask contexts and a cumulative 1,000,000 conditional coefficient-cell budget. These are implementation limits, not mathematical bounds on arbitrary repair problems. Source inspection covered the larger admitted branches; the actual consumer is only the order-13 instance.

## Validation and durable records

The source was inspected, syntax-parsed, frozen and banked before the constructor was called once. The exact input was also banked first. The complete resulting snapshot was banked in its producing call. A fresh connected V8 context then opened its saved snapshot and performed the 25 stated queries once, banking the whole output in that call.

| Item | Git blob identity |
| --- | --- |
| Executed source, 13,268 bytes | ba5810b735ddc0e2b868ee04735763ff165e295c |
| Exact input, 1,703 bytes | f936595b3f047286fa6aa3fa8695c8b8aac3e301 |
| Initial complete construction, 63,387 bytes | 2d1f7f8420f9168cf7dde0904025e42e270fb9a7 |
| Complete fresh reader record, 159,276 bytes | c6845892c08797b85d623e464f9d96b3a091adfa |

The published package nests both complete records, so reopening does not depend on an ephemeral runtime store. Structural checks cover schema, cycle layout, edge identities, coefficient ranges/order and the terminal coefficient. They are not an independent proof checker for forged source premises or arbitrary coefficient contents. The exact argument above and the identified inherited source remain part of the certificate's mathematical contract. No accepted computation, proof, larger consumer or new test suite was rerun.

## Sources and finite scope

Füredi and Simonovits, *The history of degenerate (bipartite) extremal graph problems*, arXiv:1306.5167v2 (June 29, 2013), use ordinary subgraphs, not necessarily induced, and simple graphs without loops or multiple edges. Their rectangular adjacency-matrix account identifies C4-freeness with absence of an all-one 2-by-2 submatrix. Thus a four-cycle remains forbidden if its vertices have other incident edges. Primary: https://arxiv.org/abs/1306.5167 and https://arxiv.org/pdf/1306.5167, printed pp.4,8,24–26 and p.28.

The input construction retains the classical Singer attribution: J. Singer, *A theorem in finite projective geometry and some applications to number theory*, Trans. AMS 43(3) (1938), 377–385, DOI 10.1090/S0002-9947-1938-1501951-4. The modern trace-zero quotient description is supplied by Mészáros, Rónyai and Szabó, *Singer difference sets and the projective norm graph*, https://arxiv.org/pdf/1908.05591, §1.2. This continuation consumes the accepted plane and does not claim its construction or field proof anew.

The completely read FormalConjectures statement at https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/713.lean has decoded-content Git identity b262b327e134e3344cd1c5b85dbb6c8413a81409. For a bipartite forbidden graph with at least two edges, it asks whether ex(n,G) is asymptotic to c*n^alpha with c>0 and alpha in [1,2), and separately whether such an exponent must be rational. Both are annotated research open with local placeholders. That source annotation is not a proof or an exhaustive present-status assessment.

This finite repair classification settles neither asymptotic question. It is not an unrestricted graph-edit optimum, an extremal edge count over all graphs, a new Singer construction or a mathematical priority claim. The inserted edge is required to remain; allowing its deletion would be a different problem.
