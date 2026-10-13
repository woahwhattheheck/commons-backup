# Finite three-member sunflower family index

This package classifies every family of three-element subsets of the six labelled vertices \(\{0,1,2,3,4,5\}\) that contains no three-member sunflower. It stores a decision diagram with exact cardinality coefficients, then uses the saved diagram to count, rank and select families under required and excluded edge conditions.

The complete finite family has 33,652 members. Its maximum size is 10 triples, attained by 12 labelled families. All 12 maximum families and all 120 size-nine families are exported in the saved reader evidence. This is a fixed-ground-set result and a reusable navigation API, not an improvement to the sunflower lemma.

## Primary definition and coverage

Alweiss, Lovett, Wu and Zhang, *Improved bounds for the sunflower lemma*, arXiv:1908.08483v3, Definition 1.1, defines a sunflower by the condition
\[
S_i\cap S_j=\bigcap_t S_t\qquad(i\ne j).
\]
The common intersection is its kernel, and removing the kernel from each member gives its petals. The definition permits an empty kernel. Their terminology distinguishes a set system whose members have size at most \(w\) from a \(w\)-uniform family whose members all have size \(w\).

Primary PDF: https://arxiv.org/pdf/1908.08483

The accessed version is stamped 31 August 2021 and has a title page dated 1 September 2021; the original preprint is from 2019. The bounded read covered Definition 1.1 on page 1 and the uniformity convention on page 3. Its introduction credits Erdős and Rado's delta-systems. No bound, proof, example or numerical table from that paper was used.

Here the family is an ordinary set
\[
\mathcal F\subseteq\binom{\{0,1,2,3,4,5\}}3.
\]
A forbidden sunflower chooses three distinct members of \(\mathcal F\). There are no repeated edges and no ordering multiplicity among members. This distinct-member convention is the finite set-family interpretation, not a claimed additional sentence quoted from Definition 1.1.

The intake associates the sunflower problem with Erdős 20 / PPL 038. The exact attempted formal-source URL was

https://api.github.com/repos/google-deepmind/formal-conjectures/contents/FormalConjectures/ErdosProblems/20.lean

That request returned an error classified UNKNOWN: “RemoteProtocolError: Server disconnected without sending a response.” No source text was retrieved. The route is held; it was not retried or recovered through another copy. This publication therefore does not claim to inspect, verify or resolve that unavailable formal statement, and it makes no independent current-status assertion. The self-contained finite definition above comes from the independently named primary paper.

## Identified input premises

The twenty labelled triples were transferred literally from an accepted different family index:

- Commons PR: https://github.com/woahwhattheheck/commons/pull/31607
- Immutable source commit: c705b5b34cfd0f78e6ff1b4a92598c8971fb24c6
- Path: research/ppl074_k4_free_families/six_vertex_family_certificate.json
- Blob: bb3748e67572ff2a2b89b2fe09f3ad015c5d0886
- Consumed field: record.edges.

The complete retained certificate was read as input and its provider/blob identity matched. Only its twenty literal edge labels are used. Its K4 constraints, state graph, family coefficients, queries and mathematical result are not recomputed or consumed as sunflower facts.

Unconstrained tail coefficients use literal binomial rows 0 through 20 from:

- Commons PR: https://github.com/woahwhattheheck/commons/pull/31787
- Merge: 73b115a70008c88293a6a2e0efd3be612e0f4f73
- Path: research/erdos10_selected_prime_binary_minima/bit70_minima_index.json
- Blob: a781a03e3113d1bf6ecfe968178a33248d6dcacf
- Consumed field: pascal[0..20].

No Pascal recurrence is repeated. The resulting input is 6,047 bytes, blob
039ea3c34d7bcc7b028c3633cae7c4b511ff1845, and was banked before the new construction.

## Exact constraint compilation

Each of the twenty supplied triples receives its six-bit vertex mask. The constructor examines all \(\binom{20}3=1,140\) choices of three distinct edge labels. It computes the three pairwise intersections and retains a forbidden pattern exactly when these intersections coincide. Its certificate records the edge labels, edge-selection mask, kernel and three petals.

The resulting list has 60 forbidden patterns, all with two-vertex kernels. This is also consistent with a direct finite observation: a three-member, three-uniform sunflower with kernel size \(c\) has union size \(c+3(3-c)=9-2c\). On six vertices, a distinct-member sunflower can therefore only have \(c=2\). In this instance, sunflower avoidance is equivalent to each vertex pair belonging to at most two chosen triples.

The constructor still checks the complete 1,140-pattern universe; it does not assume this observation in place of enumeration. Empty kernels are permitted in the definition even though none can occur for this input.

## Decision diagram and coefficients

A residual forbidden pattern is a mask of edge labels that may not all be included. Variables are the twenty edge labels in the inherited order.

At the current label:

- Excluding it discards every forbidden pattern containing it.
- Including it removes that label from every pattern containing it.
- An empty residual pattern rejects the branch.
- Duplicate patterns and supersets of an already forbidden smaller pattern may be removed without changing the family.
- With no remaining patterns, the suffix is free and uses the saved binomial coefficient row.

The two branches are disjoint and exhaust the choices at that label. Memoization is keyed by the next variable and the exact normalized residual constraints. Node interning additionally identifies equal variable/child triples. Thus every accepted labelled family has exactly one decision path.

If the two child generating polynomials are \(P_0(z)\) and \(P_1(z)\), the node polynomial is
\[
P(z)=P_0(z)+zP_1(z).
\]
The coefficient of \(z^k\) counts accepted completions selecting \(k\) remaining edges. All counts fit safe integer Numbers under the declared 24-edge cap. Terminal coefficients are 0 and 1.

The actual root coefficients, including every size, are:

| Number of selected triples | Families |
|---:|---:|
| 0 | 1 |
| 1 | 20 |
| 2 | 190 |
| 3 | 1,080 |
| 4 | 3,870 |
| 5 | 8,604 |
| 6 | 11,070 |
| 7 | 7,020 |
| 8 | 1,665 |
| 9 | 120 |
| 10 | 12 |
| 11 through 20 | 0 |

The sum is 33,652. Maximum cardinality and inclusion-maximality are different concepts: this package reports the former and does not claim that every inclusion-maximal family has ten edges.

The upper bound 10 also follows directly here: there are fifteen vertex pairs, each can occur in at most two chosen triples, and each triple uses three pairs. Hence \(3|\mathcal F|\le30\). The twelve retained size-ten witnesses attain it. This is a finite counting argument, not the general sunflower conjecture.

## Actual construction work

| Operation | Count |
|---|---:|
| Supplied edge masks formed | 20 |
| Distinct edge triples examined | 1,140 |
| Pair intersections | 3,420 |
| Forbidden sunflower patterns | 60 |
| Residual normalization calls | 6,061 |
| Dominance checks | 273,519 |
| Memoized constrained states | 3,030 |
| Decision nodes, including terminals | 3,036 |
| Coefficient cells | 28,010 |
| New coefficient additions | 27,994 |
| Saved binomial entries copied | 14 |
| Pascal recurrence operations | 0 |
| Earlier K4 computations | 0 |

The complete construction is 752,777 UTF-8 bytes, blob
f3d84f73cdbee8d2712fcc31e13ac1d87b2eed9a.

Source and input were banked before the single construction call. The two small preconstruction source refinements tightened decimal-mask and option validation; no mathematical construction or reader had run before them. There was no constructor failure, replay or lost output.

## Reader API

The CommonJS module sunflower_family_index.cjs exports compile(input) and openIndex(data, caches?).

The reader exposes:

| Method | Purpose |
|---|---|
| summary() | Full family coefficients and constructor counters |
| family(options={}) | Count and full size coefficients under constraints |
| select(rank, options={}) | Family at zero-based rank |
| rank(mask, options={}) | Exact rank or nonmembership |
| page(offset=0, limit=20, options={}) | Bounded family export |
| membership(mask) | Sunflower-free status or a retained obstruction |
| obstruction(id) | One complete saved sunflower pattern |
| conditions() | Every built conditional coefficient cache |
| work() | Reader counters |

Options are required, excluded, min_size and max_size. Required/excluded values are edge-selection masks; strings must be unsigned decimal integers, and safe integer Numbers are accepted. Contradictory required/excluded masks are rejected. Sizes are safe integer Numbers between zero and twenty, inclusive. Ranks are zero-based safe integers. The page cap is 1,000.

Bit \(i\) indicates the supplied edge at index \(i\). The complete edge list is in the data and input files. The reader returns both selected indices and their vertex triples.

Ranking follows the decision path: at each increasing edge index, exclusion precedes inclusion. This is lexicographic order on the zero/one decision sequence, not ascending numerical-mask order. Size conditions filter that same ordering. Required edges force the inclusion branch, excluded edges force exclusion, and the conditional polynomial retains degree shifts for every selected required edge.

For a new required/excluded pair, the reader computes coefficients only where a remaining condition matters. Below that boundary it reads saved base coefficients. The complete cache is retained. Changing only min_size or max_size reuses the same conditional polynomial. The reader performs no new pairwise set intersections, forbidden-pattern generation or base decision-diagram construction.

Membership obstructions identify three contained edge labels with their saved common kernel and petals. They are direct finite countercertificates for the supplied mask. The first encountered pattern is returned; no extremal or canonical-minimal witness property is asserted.

The saved source/caches are trusted mathematical input artifacts with independent content identities. Loading checks the format, edge binding and basic data shapes. It does not reconstruct the proof or recalculate the certificate. Callers should treat returned data as immutable.

## Actual saved reader

The first reader banked 78 complete responses and 36 rank/select inverse matches. It exported all twelve maximum families and all 120 size-nine families. The twelve maximum masks, in the declared rank order, are:

806108, 800060, 691434, 670266, 628070, 612950,
435625, 420505, 378309, 357141, 248515, 242467.

Additional complete coefficient queries give:

| Required / excluded condition | All sizes | Size ten |
|---|---:|---:|
| No constraint | 33,652 | 12 |
| Require edge 0 | 9,611 | 6 |
| Require edge 0, exclude edge 1 | 7,598 | 4 |
| Require edges 0 and 1 | 2,013 | 2 |
| Require the three edges of obstruction 0 | 0 | 0 |
| Exclude edge 0 | 24,041 | 6 |
| Exclude all ten triples containing vertex 0 | 388 | 0 |

The last condition's maximum is six, with ten maximum families. The inherited edge order puts the ten triples containing vertex zero at indices 0 through 9; their exclusion mask is 1023.

The required sunflower in the empty conditional family is a concrete rejection certificate, not an assertion about unrelated families. The unconstrained full 20-edge mask also returns a saved sunflower obstruction, while a retained size-ten witness passes membership.

The seven complete condition caches include the unconstrained case. Eight requested constraint/size options reuse these seven required/excluded keys; the two size-ten options do not cause duplicate polynomial computation.

Reader counters:

| Operation | Count |
|---|---:|
| Condition caches built | 7 |
| New conditional node visits | 26 |
| Conditional coefficient cells | 460 |
| Conditional additions | 349 |
| Reads of saved base coefficient entries | 34,218 |
| Rank steps | 720 |
| Selection steps | 3,120 |
| Membership pattern scans | 61 |
| Materialized edge records | 1,331 |
| New sunflower intersections | 0 |
| Base decision-diagram reconstructions | 0 |

Counters describe named operations in this implementation, not every primitive JavaScript instruction. Inverse matches check actual saved-query consistency; the finite exhaustion argument comes from the complete constraint list and branch partition described above.

Every reader request and response was banked immediately. No reader failed, and no output was reconstructed from a summary.

## Artifacts and use

Files:

- input6.json: literal input premises and source coverage.
- sunflower_family_index.cjs: compiler and saved reader.
- six_vertex_sunflower_index.json: complete patterns, nodes and coefficients.
- saved_reader_queries.json: exact executed query program, all requests/responses, counters and inverse count.
- saved_condition_caches.json: every conditional coefficient cache.
- This guide and README.md.

A loading example, not an additional executed query:

~~~javascript
const fs = require("node:fs");
const { openIndex } = require("./sunflower_family_index.cjs");
const data = JSON.parse(fs.readFileSync("six_vertex_sunflower_index.json", "utf8"));
const caches = JSON.parse(fs.readFileSync("saved_condition_caches.json", "utf8"));
const api = openIndex(data, caches);
const options = { required: 1, excluded: 2, min_size: 10, max_size: 10 };
const family = api.family(options);
const first = api.select(0, options);
~~~

The catalogue task number is an intake association. The substantive publication is this independently defined finite API. It neither supplies an exponential bound as uniformity grows nor improves a known general theorem, settles a current open-status question, establishes novelty, or demonstrates prize eligibility. No sponsor contact or submission was made.
