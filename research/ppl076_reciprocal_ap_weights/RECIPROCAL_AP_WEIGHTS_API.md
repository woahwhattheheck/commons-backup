# Reciprocal-weight navigation on saved AP-free families

This package maximizes an exact rational objective over an identified, already compiled finite family. Its actual input is the complete family of subsets of {1,...,n} with no nontrivial three-term arithmetic progression, for every n from 0 through 25. The family is inherited from Commons #31465. This package adds weighted scores, optimal-family counts and navigation; it does not generate that family again.

For n=25 the unique reciprocal-weight maximizer is
\[
A=\{1,2,4,5,10,11,14,22,25\},\qquad \sum_{a\in A}1/a=17693/7700.
\]
Every one of the 26 retained interval roots has a unique maximizer. Complete selected sets and branch traces are in the reader outputs. This is a finite extremum, not an assertion about every interval or an infinite set.

## Sources and scope

Bloom and Sisask, *Breaking the logarithmic barrier in Roth's theorem on arithmetic progressions*, arXiv:2007.03528v2 (1 September 2021), define a nontrivial three-term progression by x+y=2z with x distinct from y. For increasing integer triples this is (a,a+d,a+2d) with positive integer d. Their Corollary 1.2 proves that a set of positive integers with divergent reciprocal sum contains infinitely many nontrivial three-term progressions. This three-term implication is established prior mathematics. Their introduction distinguishes the conjecture requiring arbitrarily long progressions.

Primary statement read: https://arxiv.org/pdf/2007.03528 (Theorem 1.1 and Corollary 1.2).
Metadata: https://arxiv.org/abs/2007.03528 .

The separately read FormalConjectures/ErdosProblems/3.lean content has Git content identity b84747c2c08d9c571f3e27a90d59da75701d8345 (3,804 bytes). Its main arbitrary-length assertion is annotated research open; its three-term special case is annotated research solved. The native response provided decoded content, not an immutable repository commit. Local theorem placeholders and external references were not proof-checked. These are source annotations, not an independent current-frontier census.

The finite input uses only positive elements 1,...,25, so reciprocal weights never involve division by zero. A set chooses each element at most once. The empty set is allowed and has weight zero. The exact finite result implies that every subset of [1,25] with reciprocal sum exceeding 17693/7700 contains a nontrivial three-term progression, conditional on the identified complete-family premise. It does not settle Erdős 3, improve the cited asymptotic theorem, or claim mathematical novelty.

## Input custody and the new objective

Accepted carrier: https://github.com/woahwhattheheck/commons/pull/31465 .
Merge: 4378925477b4bafe23e1563fa5ffc775c9d89109.

| Accepted input | Path | Git blob |
|---|---|---|
| Complete AP-free record | research/ppl123_ap_free_families/three_term_families.json | 727f1781f4912f36430c82350b5b4acb83ef78bc |
| Source defining the saved graph interface | research/ppl123_ap_free_families/ap_free_families.cjs | 653954fa143241bfc9d90568fdeb828f77264bc0 |

The full accepted data was retrieved at that merge and its 657,608-byte content identity matched. The old source was inspected to bind the node format and determine that it did not expose a weighted objective. It was not executed. Only the literal node triples [element,lo,hi] and interval roots were copied from the saved record. Old polynomial IDs, coefficients, AP constraints, work sessions and old reader outputs are not construction inputs here. No old family count or maximum-cardinality result was revalidated.

The new input has 10,630 nodes and 26 roots. Its normalized reciprocal weights are supplied explicitly. The selected-input content blob is 3d647b19bd76f710d9753063661d6b1a3d976076 (152,093 bytes). The complete resulting certificate retains the same node triples, roots, weights and exact premise locator, so the production dependency remains inspectable without invoking the earlier module. The old N=26 resource stop is outside this work and was not retried.

## Saved ZDD convention and recurrence

Node 0 is the empty family. Node 1 is the family containing only the empty set. A nonterminal node [v,l,h] denotes the disjoint union
\[
\mathcal F_l\ \cup\ \{S\cup\{v\}:S\in\mathcal F_h\}.
\]
Children have smaller IDs and smaller element labels. A skipped element is absent. The include child is nonzero under the zero-suppressed convention. These structural conditions are checked; correctness and completeness of the represented AP-free family remain the identified premise.

All rational weights are scaled to a positive common denominator D. For the actual weights, D=lcm(1,...,25)=26,771,144,400. Integer weight w_v=D/v makes every comparison exact. More generally the API accepts signed rational weights with positive denominators. No floating point score comparison occurs.

Let M_j be the maximum scaled score at node j, C_j its multiplicity, and B_j a two-bit optimal-branch mask. The empty family has M_0=null, C_0=0; terminal 1 has M_1=0, C_1=1. At [v,l,h], compare M_l against w_v+M_h, ignoring unreachable branches. Select the larger score, or both branches on equality. Add child counts only for selected branches. Bit 1 means exclude; bit 2 means include. Because the two branches represent disjoint sets, ties add counts without duplicate sets.

Induction in node-ID order proves that each saved cell contains the exact maximum and number of maximizers. This induction evaluates a new objective on an existing diagram. It does not establish the diagram's underlying arithmetic-progression theorem or replay its old cardinality-polynomial recurrence.

For rank/select, the exclude branch precedes the include branch at each descending variable. The skip count for an include branch is the saved optimal count of its exclude sibling, when that sibling is optimal. Returned sets are increasing lists. This is diagram order, not increasing-list lexicographic order. No set is emitted unless requested.

## Conditional queries

A query specifies increasing, disjoint required and forbidden element lists. Required values must all appear; forbidden values must be absent. A state carries a saved node ID and the remaining required-element bit mask. An outstanding required value above the current node label is impossible, because skipped variables cannot reappear. Terminal 1 succeeds only when no required value remains. At other nodes, a required current value disables exclusion and a forbidden current value disables inclusion. The same exact maximum/count recurrence then applies.

This is new query computation, not a claim that conditions were answered for free. A condition record retains every visited state, remaining mask, cell and child key. Reopening that record navigates its saved optimal branches without recomputing its dynamic program.

The three actual conditions at n=25 are:

| Condition | Maximum reciprocal weight | Count | New retained cells |
|---|---:|---:|---:|
| Forbid 1 | 403523/265200 | 1 | 5,970 |
| Require 1,2,3 | Infeasible | 0 | 5,974 |
| Require 25 and forbid 1 | 403523/265200 | 1 | 2,523 |

The two feasible conditions share the selected optimum {2,3,5,6,12,13,16,17,25}. This equality is a result of those queries, not an identification of their full feasible families. An infeasible query returns count zero and null score. Selecting or ranking an optimum in an infeasible family is rejected.

## Public API

The module is CommonJS with no dependencies or I/O:

~~~javascript
const { compileWeights, openWeights } = require('./reciprocal_ap_weights.cjs');
const certificate = require('./weighted_ap_certificate.json');
const reader = openWeights(certificate.record);
reader.at(25).summary();
reader.at(25).select('0');
reader.at(25).rank([1,2,4,5,10,11,14,22,25]);
~~~

| Method | Meaning |
|---|---|
| compileWeights(input) | Construct new weighted cells on supplied identified node triples and roots. |
| openWeights(record) | Structurally load saved cells; no base objective recurrence. |
| reader.summary() | All retained root scores/counts, common denominator and node count. |
| reader.at(n).summary() | Exact unrestricted optimum at one saved root. |
| reader.at(n).select(decimalRank) | Select an optimal set and full branch trace. |
| reader.at(n).rank(increasingSet) | Rank a member of the optimum family; reject other sets. |
| reader.at(n).page(decimalStart,limit) | Page at most 256 selected optimal sets. |
| reader.pageNodes(start,limit) | Return at most 256 saved nodes and cells. |
| reader.condition(n,required,forbidden) | Perform a new conditional DP and return its record and navigation handle. |
| reader.openCondition(record) | Navigate a previously saved condition record for the same graph and weights. |
| reader.work() | Return a copy of current reader counters. |
| reader.snapshot() | Return a copy of the loaded base record. |

The constructor input contains n, premise, nodes, roots and weights. Each weight is {element,numerator,denominator}; numerators are signed canonical decimal strings and denominators positive canonical decimal strings. Ranks/counts are decimal strings; node IDs and elements are safe integers. Input nodes are capped at 50,000, n at 64, input rational numerator/denominator lengths near 100 digits and the common scale at 2,048 digits. A conditional record is capped at 200,000 rows. The actual input lies well below these bounds. Larger branches and alternate weight systems were source-inspected, not exercised.

Structural reopening checks shape, decimal encoding and child availability. It does not authenticate an untrusted record, recompute its optimality proof, verify its AP-free provenance, or establish that a foreign condition record belongs to these weights. Use condition records with the same identified graph, units and scale from which they were produced. Returned arrays/records are copied so ordinary callers cannot mutate internal retained data.

## Complete output and shard loading

weighted_ap_certificate.json contains the complete once-only construction outcome, including all 10,630 node triples and score/count/mask cells. The 36 complete reader responses are in saved_reader_queries.json. Its condition manifests contain metadata and exact ordered shard ranges. All five condition shards are published; none is a preview.

To reconstruct a saved condition record without running its DP:

~~~javascript
const fs = require('node:fs');
const path = require('node:path');
const queries = require('./saved_reader_queries.json');
const entry = queries.conditions.find(x => x.request.label === 'exclude_one');
const rows = entry.shards.flatMap(s =>
  JSON.parse(fs.readFileSync(path.join(__dirname, s.file), 'utf8')).rows);
const condition = { ...entry.record, rows };
const navigation = reader.openCondition(condition);
navigation.select('0');
~~~

The example uses ordinary filesystem access by a downstream consumer; the module itself has no I/O. Manifest start/end ranges are half-open and preserve the original retained row order. It is the caller's responsibility to load every listed shard for a complete record. No query output has been omitted or reconstructed after loss.

## Actual work and validation boundary

Source was syntax-parsed and inspected before freezing. Frozen source blob: 5409c64831a1cca6db109b06cf0c55568ff5c490 (9,542 bytes). The sole construction completed 10,630 weighted cells and 10,628 comparisons. The complete outcome was banked as 12b7bcb28ae328f2f4fadd0913f51ef15b3f2f0e (386,482 bytes) in the same operation that produced it. The observed 19 ms execution duration is one environment observation, not a benchmark.

A fresh module instance opened the saved construction and produced 36 query responses: one summary, all 26 root selections, an inverse rank at n=25, a saved-node page and the stated conditional summaries/pages/ranks. It retained 14,467 new conditional cells and 14,458 comparisons, plus 500 saved-node visits. Base weighted cells recomputed: zero. AP construction and old polynomial cells computed: zero. The full reader outcome, including all condition records before sharding, was banked as 3bcdcf15d31630b644cd08f8aee5b05045c34dec (1,438,721 bytes).

The actual finite construction and these saved queries are the validation evidence. No native runtime, synthetic test suite, old AP enumeration, source-paper proof audit or sponsor submission occurred. Publication uses the guarded serial Contents method with full text and expected-head checks; it does not independently verify file modes or the whole repository tree.
