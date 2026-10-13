# Complete clique families from retained smooth-sum graphs

This package adds complete family counts and conditional navigation to the two finite graphs already saved in [Commons #31433](https://github.com/woahwhattheheck/commons/pull/31433). Its input is the exact saved adjacency, not the old factorization program or maximum-search trace.

The vertices are the labelled integers 0 through 127. In each inherited graph, distinct vertices are adjacent when their positive sum has no prime factor outside the declared palette. A clique is a vertex set whose every distinct pair is adjacent. Empty and singleton sets are included. Labels are retained; no scaling, graph automorphism or isomorphism quotient is applied.

The earlier work already established maximum sizes 5 and 7 and retained one witness for each. The new capability counts every clique by size, exports every clique at those inherited maximum sizes, and supports required/forbidden vertices, inclusive cardinality bounds, pages, exact rank/select and vertex marginals. It does not resubmit the maximum values as new results.

## Complete finite results

| Allowed primes | Saved edges | DAG nodes including terminal | Counts for sizes 0 upward | All cliques | Cliques at inherited maximum |
|---|---:|---:|---|---:|---:|
| 2,3,5 | 1,278 | 2,505 | 1, 128, 1278, 1743, 635, 37 | 3,822 | 37 of size 5 |
| 2,3,5,7 | 2,035 | 8,753 | 1, 128, 2035, 6395, 6349, 2372, 320, 6 | 17,606 | 6 of size 7 |

The certificate contains every DAG state, candidate mask, branch address and coefficient vector. The saved reader contains all 43 maximizing sets with their exact ranks. All six size-7 sets contain zero, as the full maximum-family vertex marginal records. These statements concern only the declared finite graphs, not global values or asymptotics of the Erdős126 function.

## Input and attribution

The immutable source premise is:
- Repository: woahwhattheheck/commons.
- PR: 31433.
- Merge: d7c882fab3d7ee2581b7735bb19805bd2dcbf5ca.
- Data path: research/ppl017_erdos126_smooth_sums/interval0_127_prime_support_cliques.json.
- Data blob: e92c77a8e5095ae58e30c340f75305f060075f12, 869,513 UTF-8 bytes.
- Guide blob: 4c8ce0b1a513cad90bc3ab92531ff78626bb9e43, 26,173 UTF-8 bytes.
- Copied fields: snapshot.candidates, each snapshot.graph_views adjacency_masks_hex and graph labels, and the already published maximum sizes.

Both complete input bodies independently matched their Git blob identities. The source and graph contracts are trusted inherited premises. No least-factor table, factor divisions, pair support, adjacency, greedy coloring, old search node or prior maximum proof was reconstructed.

The prior guide attributes the natural-number/off-diagonal convention to FormalConjectures/ErdosProblems/126.lean blob b193747601aea2ef1f5f3f04805b4991112b6aff. Zero is allowed, repeated elements are excluded, and ordered unequal-pair products have the same distinct prime support as unordered-pair products. This package uses that attribution; it did not newly acquire or audit the formal file or linked external Lean proof. The guide reports a research-solved annotation for the main question with a local sorry, and an open annotation for a separate little-o variant. Those are dated inherited catalogue facts. The current PPL017 card's open/reward label is not adopted as a current-status determination.

The prior canonical-page HTTP 403 remains held and unretried. Its exact URL spelling was not recovered from the guide. No sponsor contact, eligibility assessment, award or submission is claimed. See SOURCE_QUALIFICATION.md.

## Family recurrence and completeness

For a candidate mask C, let F(C) be all cliques contained in C, including the empty clique. For nonempty C choose its least vertex v and write R=C minus {v}. The disjoint partition is

```
F(C) = F(R)  disjoint-union  { {v} union S : S in F(R intersect N(v)) }.
```

Every clique excludes v or includes v. In the latter case its remaining vertices are a clique in the saved neighbors of v. Conversely each such remaining clique extends by v. This proves the recurrence directly for the declared graph premise.

At C=empty the family contains exactly the empty set, with polynomial 1. If P_C(z) counts cliques by cardinality, then P_C=P_R+z P_(R intersect N(v)). Each child has fewer candidates. Memoization by exact candidate mask computes each new state once per graph. Child IDs are less than parent IDs; terminal ID is zero. The two graphs use separate state maps.

The constructor retains all states, not just states that can improve an incumbent. There is no coloring bound, maximum-based prune or numerical optimum search. The original maximum sizes are metadata used to select the complete maximizing families for export.

## Order

Ranks are zero based in lexicographic order of the 128-bit membership vector, read at vertices 0,1,...,127, with absent (0) before present (1). This is not numeric-mask order and is not the usual lexicographic order of increasing vertex lists.

At a decision node, every exclude-branch set precedes every include-branch set. A vertex omitted from a candidate mask is forced absent for that continuation. Output vertex arrays are increasing labels; their display order does not redefine ranking.

Masks are canonical lowercase hexadecimal with no leading zeros except "0". Counts and ranks are exact decimal strings.

## Loading the public evidence

The complete constructor JSON is split into four literal UTF-8 text parts. Read certificate_manifest.json, concatenate the listed parts in order without separators, and parse the resulting JSON. The complete assembly is 1,255,152 bytes with computed Git blob 31dd2c971c654d52d5463344e8a8e7b94524845d.

The reader JSON is split into five text parts and has its own saved_reader_manifest.json. Its complete assembly is 1,953,488 bytes with computed Git blob 69a57f0c34883b4736c86a75f13d2db85276b235.

The native checkpoints acknowledged the individual parts and assembly descriptors, not either whole assembled blob. The assembly identities are exact comparisons, not independently observed whole-blob provider locators. Concatenation checks verified byte identity only; they did not replay a mathematical recurrence.

```js
const { createReader } = require("./clique_families.cjs");
const reader = createReader(certificate);
const condition = { graph: "2,3,5,7", require: [0], min_size: 6 };
reader.condition(condition);
reader.select(condition, "0");
reader.rank(condition, [0, 1, 3, 5, 9, 15, 27]);
reader.page(condition, "0", 256);
reader.marginals(condition);
```

These calls illustrate the interface; the published actual queries are the saved reader responses, not a claim that this example was separately executed.

The exported compile(input) is the once-used constructor. Loading and navigating an existing certificate requires only createReader; it must not invoke compile again.

## Conditional reader

Every condition supplies an exact saved graph key, optional require and forbid arrays of distinct vertex labels, and optional inclusive min_size/max_size integers. Defaults are 0 and 128. Bounds are clipped against the host in the direction relevant to each endpoint. Reversed, entirely out-of-range or incompatible conditions have count zero. Unknown graphs, repeated/out-of-range vertices, and noninteger bounds throw.

Required and forbidden masks determine a reusable conditional polynomial pool. Cardinality intervals share that pool. With neither mask present, the reader references the saved base polynomials instead of recomputing them. The coefficient vector returned by condition counts every cardinality after vertex constraints and before cardinality-range filtering; count applies the requested range.

At node v:
- The exclude branch is forbidden when v is required.
- The include branch is forbidden when v is forbidden.
- The include branch is also forbidden if restricting to N(v) drops any other still-required vertex.
- An overlap between required and forbidden masks makes every branch infeasible.

These checks preserve exactly the constrained family. In particular, merely intersecting a required mask with a child candidate set would be incorrect: a dropped required vertex must reject that branch.

Selection uses saved conditional suffix coefficients, adjusted by the number of already selected vertices, to skip whole branches. Ranking follows a supplied set through the same decisions and adds the counts of earlier exclude branches. A non-clique set is NOT_IN_FAMILY; a violation of the condition is NOT_IN_CONDITION. Select at rank greater than or equal to count is OUT_OF_RANGE. Decimal ranks are nonnegative canonical strings of at most 64 characters.

Pages accept a decimal offset and a limit from 1 through 256. Offset=count yields an empty successful page; offset>count is OUT_OF_RANGE. next_offset is null at the end.

Marginals return, for each vertex, the number of admitted labelled cliques containing it. A forward polynomial records how many prefixes of each cardinality reach a DAG state. Combining those prefix multiplicities with the included child's saved conditional suffix polynomial counts sets passing through that include decision. Shared DAG nodes need those prefix multiplicities; one visit is not one full clique. The empty condition has zero marginals.

snapshot retains the conditions, every nontrivial filtered pool with its branch flags, and work counters. Base pools are recorded as references to certificate polynomials rather than duplicated. Treat the certificate, reader results and snapshots as immutable. This is a trusted saved-data API, not an adversarial certificate validator or an independent mathematical proof audit. It has no filesystem, network, clock or external package dependency.

## Actual first reader use

The reader driver and plan were independently checkpointed before execution. The one actual run returned 149 responses, including:
- all 43 maximizing cliques through two complete pages;
- 42 selections with inverse ranks, all matched;
- 38 unique conditions, with 14 nontrivial filtered polynomial pools;
- six complete vertex-marginal vectors;
- every fixed cardinality through the inherited maximum plus one;
- empty, incompatible, end-page and invalid-pair outcomes.

Every request was retained before invocation, every returned response was retained, and the latest complete caches and counters were saved after every response. No reader call failed or was rerun.

| Graph | Declared condition | Count |
|---|---|---:|
| 2,3,5 | full | 3822 |
| 2,3,5 | maximum | 37 |
| 2,3,5 | require-zero | 420 |
| 2,3,5 | forbid-zero | 3402 |
| 2,3,5 | require-zero-and-one | 25 |
| 2,3,5 | require-one-and-last | 9 |
| 2,3,5 | incompatible-pair | 0 |
| 2,3,5 | odd-only | 1341 |
| 2,3,5 | required-and-forbidden | 0 |
| 2,3,5 | reversed-cardinality | 0 |
| 2,3,5 | negative-maximum-size | 0 |
| 2,3,5 | above-host-minimum | 0 |
| 2,3,5,7 | full | 17606 |
| 2,3,5,7 | maximum | 6 |
| 2,3,5,7 | require-zero | 2725 |
| 2,3,5,7 | forbid-zero | 14881 |
| 2,3,5,7 | require-zero-and-one | 178 |
| 2,3,5,7 | require-one-and-last | 44 |
| 2,3,5,7 | incompatible-pair | 0 |
| 2,3,5,7 | odd-only | 5261 |
| 2,3,5,7 | required-and-forbidden | 0 |
| 2,3,5,7 | reversed-cardinality | 0 |
| 2,3,5,7 | negative-maximum-size | 0 |
| 2,3,5,7 | above-host-minimum | 0 |

The fixed-size responses reproduce the table's entire new family polynomial and return zero at sizes 6 and 8 respectively. They are reads of the new saved family, not a rerun of the original maximum-search proof.

## Work accounting

Constructor:
```json
{
  "adjacencyCopies": 256,
  "statesBuilt": 11256,
  "memoHits": 11258,
  "candidateIntersections": 11256,
  "coefficientAdds": 54420,
  "newFactorDivisions": 0,
  "newPairRows": 0,
  "newGraphViews": 0,
  "oldSearchNodes": 0,
  "oldColorBounds": 0
}
```

Reader:
```json
{
  "conditionsBuilt": 38,
  "conditionHits": 153,
  "filteredPoolsBuilt": 14,
  "basePolynomialReferences": 11258,
  "filteredNodeVisits": 78792,
  "coefficientAdds": 330513,
  "countCoefficientReads": 6536,
  "selectionSteps": 1885,
  "rankSteps": 1632,
  "materializedSets": 85,
  "marginalNodeVisits": 24046,
  "marginalProducts": 26622,
  "newFamilyStates": 0,
  "newFactorDivisions": 0,
  "newAdjacency": 0,
  "oldSearchNodes": 0
}
```

The 11,256 constructed nonterminal states plus two terminals are the 11,258 saved DAG nodes. The 85 materialized sets are 42 direct selections and 43 page entries; the 42 inverse queries do not rematerialize them. Counts may be large in other supplied graphs; memory/time can be exponential in the number of vertices. The implementation restricts the declared vertex list to 0 through n-1 with n<=128, but does not promise a resource bound for every such graph.

The actual input is source-defined, fully retained, and completed. No tests, fixture family, old mathematical computation, old proof or benchmark replay was added.

## Checkpoint and publication boundary

public_checkpoints.json retains the public native-blob checkpoint chain for source/input/plan, complete result parts, reader driver/plan, and complete reader parts. The full frozen publication spec is additionally banked before publication, with its recovery locator supplied in the completion receipt; it is not recursively included in itself.

Checkpoint acknowledgement establishes the returned content identity, not branch inclusion, mathematical correctness or indefinite retention. The later guarded Commons publication separately checks paths, pins, commits, PR head, expected-head merge and complete immutable file contents. Current-main observation is stated in the release receipt with its exact scope.
