# Complementary hypergraph colorings from a saved decision diagram

This package counts and navigates the labelled two-colorings of the twenty triples on six vertices for which neither color contains all four triples of a four-vertex set. It consumes the complete K₄³-free family already published in Commons #31607 as a saved zero-suppressed decision diagram (ZDD). The new work intersects that family with its edge-complement image. It does not regenerate the old forbidden-clique constraints, recompile the old family, enumerate tournaments, or scan all complete color assignments.

The new family has **118,784** colorings. Red cardinalities range from six to fourteen. All thirty minimum-red colorings and all thirty maximum-red colorings are exported in the saved reader evidence. The fresh reader retained **85 complete responses**, **31 inverse matches**, and seven complete conditional tables. This is a finite labelled-family and navigation result, not an asymptotic Ramsey improvement or a new exact Ramsey number.

## Statement, attribution and input custody

The fully read [FormalConjectures Erdős 564 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/564.lean) defines R₃(n) as the least number of vertices forcing a monochromatic complete n-vertex 3-uniform hypergraph in every two-coloring of the triples. It asks whether there is an absolute c>0 such that R₃(n)≥2^(2^(cn)) for all sufficiently large n. Its observed annotation is research open and its local proof is a placeholder. No Lean execution or proof audit is claimed.

The actual source request was the repository Contents endpoint for FormalConjectures/ErdosProblems/564.lean with its default ref. The complete returned text is 1,294 bytes, local Git blob 1e980718b6a9eb7ea8f66ffd1a50865b9d263946. The provider did not bind that response to an immutable source commit. The statement supplies the asymptotic problem and the ordinary monochromatic-clique convention; this package addresses one declared six-vertex family.

The earlier [tournament inverse index #31447](https://github.com/woahwhattheheck/commons/pull/31447) is a separate completed contribution. It credits the classical Erdős–Hajnal cyclic-triple construction through Conlon–Fox–Sudakov, *Hypergraph Ramsey numbers*, arXiv:0808.3760. That tournament image, its inverse fibers and its 15 saved queries are not inputs to the current product, and no tournament computation or construction proof is replayed here.

The actual source family comes from [#31607](https://github.com/woahwhattheheck/commons/pull/31607):

| Item | Exact identity |
|---|---|
| Immutable merge | aaa9ac48515a2c4b944954a1cf25ec6579574130 |
| Source module | research/ppl074_k4_free_families/k4_free_families.cjs |
| Module blob | a52f65c8b6e5223a1b6a7af9fac895b8c5526966 |
| Complete saved certificate | research/ppl074_k4_free_families/six_vertex_family_certificate.json |
| Certificate bytes / blob | 570,644 / bb3748e67572ff2a2b89b2fe09f3ad015c5d0886 |
| Source guide blob | e46f0eb331dd1f4ee68e6623df0cdc36fa7869a6 |

All three immutable texts were acquired completely and their provider and independent Git blob identities matched. Reading the old module established the saved representation's semantics; its constructor and reader were not invoked. The current input extracts only the twenty triple labels, the source root, and the variable/low/high transitions of its 1,065 nodes. Old residual constraints, family coefficients, maximum examples and reader results are not compiled again.

The inherited premise is that this source ZDD accepts exactly the K₄³-free subsets of the twenty triples. Authenticating the bytes does not independently reprove that premise. The old Formal500 404 and linked OEIS source failure remain held; neither route was retried or used to qualify the present statement.

Current ownership qualification found the completed #31447 lane and no conflicting active coloring consumer in the bounded results. An initial Slack request was rejected before provider access because keywords was a string; the corrected array request was made once. Both envelopes are retained. This argument correction is not a source-access retry. No other source acquisition failure occurred for this package.

## Exact finite objects

Vertices are labelled 0 through 5. Every edge is an unordered triple of distinct vertices. The twenty variables, in order, are:

| Index | Triple | Index | Triple |
|---:|---|---:|---|
| 0 | 012 | 10 | 123 |
| 1 | 013 | 11 | 124 |
| 2 | 014 | 12 | 125 |
| 3 | 015 | 13 | 134 |
| 4 | 023 | 14 | 135 |
| 5 | 024 | 15 | 145 |
| 6 | 025 | 16 | 234 |
| 7 | 034 | 17 | 235 |
| 8 | 035 | 18 | 245 |
| 9 | 045 | 19 | 345 |

A mask's set bits are red edges; the other twenty-bit positions are blue edges. Each edge has exactly one color. Colors and vertex labels are retained. There is no quotient by vertex permutation, isomorphism or color exchange in the base total.

For every four vertices, at least one of their four triples must be red and at least one blue. Thus each color's edge set must belong to the supplied K₄³-free family. This is ordinary hypergraph Ramsey coloring: it is not a proper edge-coloring condition, and intersecting triples may have the same color.

Let F be the inherited family and U the twenty-edge universe. The new family is

    C = {R ⊆ U : R ∈ F and U\R ∈ F}.

The API uses all six host vertices even when one color has isolated vertices. An induced-hypergraph or unlabeled-copy interpretation is not substituted.

## Complementary product construction

The old ZDD has terminal 0 for the empty family and terminal 1 for the family containing only the empty remaining set. Its variable numbers increase down every branch. A variable skipped by a ZDD path is forced absent, rather than free.

For source node a, current position k and desired membership bit b, define the transition:

- From terminal 0, return 0.
- If a's variable is k, take its low child for b=0 or high child for b=1.
- If a's variable is greater than k, keep a for b=0 and return 0 for b=1.

The terminal-one variable is the end position, so this rule also handles its remaining forced-zero variables. A source variable below k violates the representation invariant.

A new state (k,a,b) records the current position and the residual red and blue source nodes. A red bit of zero advances red with zero and blue with one; a red bit of one advances red with one and blue with zero. Any zero source node rejects the branch. At the end, both source nodes must be terminal one.

This is exact by induction on the remaining variable positions. The two source paths enforce red and blue membership separately, and the complementary choices assign every edge once. Every accepted coloring determines one product path and every accepting product path determines one coloring. No additional consistency condition is needed.

The compiler memoizes each reachable product state and merges decision nodes having the same position and two children. It retains every position on a nonzero path. In particular, it does not silently interpret a skipped product variable as a free color choice.

For a product node v with low child L and high child H, its red-cardinality polynomial is

    P_v(z) = P_L(z) + z P_H(z).

The terminals have polynomials zero and one. Coefficient k counts colorings with exactly k red edges; evaluation at one gives the total. Each new coefficient is derived only from new product children. Old source-family coefficients are not read or recomputed.

The complete reachable state table includes states that reduce to rejection and states sharing a decision node. It records position, both source IDs, both new child IDs and the resulting node ID. The decision table retains variable, children, every polynomial coefficient and total.

## Actual construction

The source and exact input were banked before the compiler's one invocation. The full result was banked before the saved reader was opened. No constructor error or reconstruction run occurred.

| Red edges | Accepted colorings |
|---:|---:|
| 0–5 | 0 |
| 6 | 30 |
| 7 | 1,620 |
| 8 | 10,500 |
| 9 | 28,080 |
| 10 | 38,324 |
| 11 | 28,080 |
| 12 | 10,500 |
| 13 | 1,620 |
| 14 | 30 |
| 15–20 | 0 |
| Total | 118,784 |

The saved coefficient array trims trailing zeros. Queries at cardinalities beyond its last entry return zero.

| Construction work | Actual count |
|---|---:|
| Copied source nodes, including terminals | 1,065 |
| Distinct product states | 5,681 |
| Product memo hits | 3,686 |
| Source transition operations | 22,724 |
| Dead branch hits | 1,992 |
| Nonterminal product decision nodes | 4,242 |
| Saved decision nodes including terminals | 4,244 |
| Coefficient cells including terminals | 28,059 |
| Coefficient additions | 44,143 |
| Old constraint generation | 0 |
| Old family compilation | 0 |
| Tournament computation | 0 |
| Complete colorings enumerated by compiler | 0 |

The finite bounds are not asserted as new literature values or records. In particular, this six-vertex example does not establish an exact threshold or the double-exponential asymptotic assertion.

## Saved reader and ordering

Load the complete product from its manifest and shards, then open it:

~~~javascript
const {loadIndex} = require('./load_saved_index.cjs');
const {openIndex} = require('./complementary_zdd_colorings.cjs');
const saved = loadIndex(manifest, readText);
const index = openIndex(saved);
~~~

The caller supplies readText(path), returning the exact shard text. Loader checks cover shard positions and lengths. Opening validates bounded node shapes, references and full-level ordering. These are structural checks on trusted input, not a fresh semantic verification or adversarial certificate audit.

| Method | Meaning |
|---|---|
| summary() | Saved total, red-cardinality profile and construction work |
| labels() | The retained variable-to-triple map |
| decode(mask) | Red and blue edge indices, complement mask and red count |
| select(k, rankText) | Select in the full family or exact-red-size fiber; k=null means all |
| rank(mask, k=null) | Return the inverse rank, or null for a semantic nonmember |
| page(k, offsetText, limit) | At most 256 complete selected records and traces |
| condition({red,blue}) | Fix edge indices to the indicated colors |
| complement(mask,k=null) | Return original and color-reversed rank records |
| exportConditions() | Every retained conditional table, including the base view |
| work() | Explicit saved-reader work counters |

Masks are safe integers within the declared universe. Ranks are canonical nonnegative decimal strings. Edge-index lists may not contain duplicates or contradictory assignments. Malformed inputs throw; a well-formed nonmember passed to rank returns null.

Order is lexicographic in the color word at increasing edge index, with blue/zero before red/one. Since the first variable is the least significant mask bit, this is **not increasing integer-mask order**. A cardinality fiber inherits the same order. Traces retain node, variable, branch, low-branch count and residual or accumulated rank.

Rank and select read the saved coefficients and traverse one product path. They perform no source ZDD transitions and do not rebuild the product. Decoding lists edge indices; it does not recompute a geometric or clique predicate.

## Conditional completion

A condition fixes disjoint sets of red and blue edge indices. The reader disables the corresponding forbidden branches and applies the same low-plus-shifted-high recurrence on the saved product DAG. New conditional cells and additions are counted as query work. No source constraints or new base product nodes are generated.

Each condition is memoized by its two masks, and its complete table is retained. Empty conditions reuse the base coefficients and create no conditional cells. A full valid assignment yields one completion; a monochromatic tetrahedron condition yields zero.

| Actual condition | Completions | New conditional cells |
|---|---:|---:|
| Edge 0 blue | 59,392 | 3,020 |
| Red 0,1; blue 2,3 | 10,100 | 858 |
| Red 0,1,4; blue 10 | 8,731 | 835 |
| Red 0,5,9; blue 2,11,16 | 1,941 | 626 |
| Red 0,1,4,10 | 0 | 158 |
| Blue 0,1,4,10 | 0 | 158 |
| Complete balanced mask 520961 | 1 | 20 |

Indices 0,1,4,10 are the four triples on vertices 0,1,2,3. This interpretation comes from the declared labels; it is not a re-execution of the old constraint compiler.

Color reversal is a fixed-point-free involution on this nonempty edge universe. Exactly one coloring in each reversal pair has edge zero blue, so that condition gives 59,392 representatives. It identifies color exchange only; vertex permutations are not quotiented. The base count of 118,784 retains both colors.

Bitwise complement reverses the declared lexicographic order. Therefore, within complementary cardinality fibers, rank r maps to C−1−r. The actual reader records, among other pairs:

| Original mask / fiber / rank | Reversed mask / fiber / rank |
|---|---|
| 171904 / all / 0 | 876671 / all / 118783 |
| 143906 / red size 6 / 15 | 904669 / red size 14 / 14 |
| 520961 / red size 10 / 19162 | 527614 / red size 10 / 19161 |

The complement method obtains the saved ranks directly; the displayed relation is an elementary explanation, not an extra replayed test.

## Actual reader evidence

All 85 requests and complete responses were banked individually at first execution. There were no failed queries, lost responses or corrected execution paths.

The consumer includes:

- First, middle and last selection and inverse ranking in the full family and red-cardinality fibers 6, 7, 10, 13 and 14.
- All thirty minimum-red and thirty maximum-red colorings, each with its full decision trace.
- Closed absence for the all-blue and all-red assignments.
- Three complete color-reversal rank pairs.
- Seven conditional profiles and complete tables.
- First, middle and last conditional selections where they exist, deduplicating the single-member case.

All 31 select/rank pairs returned the requested rank. These are actual API use records. They do not independently reprove the imported source family.

| Saved-reader work | Actual count |
|---|---:|
| Saved nodes indexed | 4,244 |
| Saved coefficient cells indexed | 28,059 |
| Node visits | 2,576 |
| Coefficient reads | 2,706 |
| Rank additions | 377 |
| Selected colorings | 91 |
| Edge decodes | 1,820 |
| New conditional cells | 5,675 |
| New conditional coefficient cells | 32,310 |
| New conditional additions | 49,928 |
| Conditional memo hits | 4,390 |
| Old source transitions | 0 |
| New product states | 0 |
| New base coefficients | 0 |

The 91 selected colorings include the sixty records exported by the two complete pages. Condition-table snapshots are also retained inside their original responses and in the final reusable condition cache; this intentional duplication preserves the actual responses.

## Complete files and byte custody

The compiler result and reader packet are split without dropping rows or fields. The product manifest contains the exact input and replaces only nodes and states with ordered shard descriptors. The reader manifest replaces only outputs and conditions. Reassembly reproduced each original JSON serialization plus its trailing newline byte-for-byte. This was a structural comparison, not a constructor or reader replay.

| Artifact | Bytes | Git blob |
|---|---:|---|
| Frozen compiler/reader module | 9,606 | 02a4540a5ecaf496dc9997aa791ad3445c7a44f6 |
| Exact new input | 73,553 | 757074345d97912fd223987f279199bdf91bd5db |
| Full assembled product | 884,560 | 015477b0c31d0c088bba88d6e271267cd798301e |
| Product manifest | 37,763 | d3947d9e2c587ffbcc94531dcd60c59103d57bf8 |
| Full assembled reader packet | 1,171,545 | d08ff8bc8980dec06be1712a2a59038be2ad99fd |
| Reader manifest | 4,999 | 562a770bb72dd04c1af293a696ba52ac41c2d0a9 |
| Loader | 791 | 95574962695714628419e6e5eb13e39f0265e982 |

The manifest lists every shard with path, start, count, bytes and blob. product_nodes_00.json contains all 4,244 nodes. product_states_00.json and product_states_01.json contain all 5,681 states. Three reader_outputs files contain all 85 responses; two reader_conditions files contain all eight views including the unconditioned base.

The source input is also published separately as input_source_zdd.json. The repeated input inside the product manifest is retained deliberately to reconstruct the original result exactly.

## Cost, validation and limits

For E variables and S source nodes, the product has at most (E+1)S² possible state keys, although this bounded traversal visits only reachable ones. A state uses four constant-time source transitions and two recursive child lookups. Polynomial work is linear in the retained coefficient lengths. The API does not claim polynomial complexity in vertex count for an arbitrary Ramsey problem; its supplied family may itself be exponentially large.

Conditional work is bounded by the reachable saved product nodes for each fixed assignment. Rank/select traverses at most E positions, apart from input decoding and table access. BigInt arithmetic cost is not treated as constant in a general complexity claim.

The implementation caps variables at 24, source nodes at 100,000, product states and decision nodes at 250,000, and compiled coefficient cells at 4,000,000. A conditional table is capped at 1,000,000 cells. These are resource contracts, not tested coverage claims. The actual consumer uses exactly twenty variables and the identified six-vertex source.

Generic malformed-input, resource-cap and other unexecuted branches are not represented as exercised tests. No native executor, synthetic fixture suite, accepted calculation replay, sponsor contact or submission was used. The publication supplies a reusable finite complementary-family operation and complete evidence for this declared input.
