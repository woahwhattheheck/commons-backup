# Exact finite families avoiding {n,2n,3n}

This package compiles all subsets of [1,96] that never contain n, 2n and 3n simultaneously. Its saved decision diagram represents **1,877,043,752,444,810,703,667,200,000** subsets. Their maximum cardinality is **77**, attained by **37,908** subsets. The exact cardinality coefficients support selection, ranking, pages and required/forbidden-element conditions without enumerating the represented family.

Only these dilated triples are forbidden. This is not the family avoiding every three-term arithmetic progression.

## Source and mathematical boundary

The full [FormalConjectures Erdős 168 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/168.lean) was read as 3,795 bytes, identified by Git blob `6b08aee5f3ee7342717f6a0230be36ac26db5d9d`. It defines a non-ternary finite set by excluding simultaneous membership of n, 2n and 3n, and defines F(N) as the maximum cardinality among such subsets of {1,…,N}. Its two main declarations ask for the limiting value of F(N)/N and whether that limit is irrational. They are annotated research open with local placeholders. A separate limit-existence declaration is annotated research solved, attributed to Graham, Spencer and Witsenhausen, again with a local placeholder. The file's elementary API lemmas were not executed or used as numerical verification targets.

The historical reference was identified as R. L. Graham, H. S. Witsenhausen and J. H. Spencer, *On extremal density theorems for linear forms*, Number Theory and Algebra (1977), pages 103–109. The exact author archive route `https://mathweb.ucsd.edu/~ronspubs/77_05_extremal_density.pdf` returned a seven-page PDF with zero extracted text lines. A first-page screenshot response contained only a text marker and no image payload. No visual inspection, original-definition confirmation, proof, table or limiting-value calculation is claimed. The unusable source route was held without retry, alternate copy or OCR. The actually read formal definition is this package's statement authority.

The input is the declared finite interval [1,96], chosen for this consumer. No published finite example or prior AP dataset was imported. Zero and negative integers are outside the host. For positive n, the three forbidden values are distinct. The empty subset is valid, and every element is selected at most once.

The exact result F(96)=77 is a finite classification under that definition. It neither establishes the limiting value nor decides its irrationality. The general existence of a limit is credited to the source rather than presented as a consequence of this computation. There is no current-status survey, historical-record comparison, novelty or prize claim.

## Component factorization

Every positive integer has a unique expression

```text
n = c · 2^a · 3^b, with gcd(c,6)=1 and a,b≥0.
```

Multiplication by 2 or 3 preserves c. Therefore every forbidden triple lies wholly in one component determined by c; no triple joins two different components. A subset of the full interval is admissible exactly when its intersection with every component is admissible. This is the elementary decomposition used by this implementation, not a quoted algorithm from the unread historical scan.

The constructor groups the host by removing factors of 2 and 3, then creates exactly the triples with 1≤n≤floor(N/3). For N=96 this gives 32 components and 32 constraints. The computation's 140 factor divisions are new production work on this input. They do not use or replay an accepted prime, factorial, totient, AP or other factorization artifact.

Variables are ordered first by increasing component core c, then by increasing integer value within that component. The final selected values are displayed in increasing numerical order, but rank order is the **component-ordered binary decision vector**, with exclusion before inclusion. It is not lexicographic order of the displayed integer list and not an ordering modulo any symmetry.

## Decision diagram and exact coefficients

Within a component, each residual forbidden mask records values that would still need to be selected to complete a forbidden triple. Excluding a variable discards every residual constraint containing it, because that triple can no longer be completed. Including the variable removes its bit from every residual constraint. An empty residual constraint rejects the inclusion branch.

The component recursion memoizes the next local variable and sorted distinct residual masks. Components are assembled in reverse variable order. Completing one component points to the already compiled tail for later components. A saved component's `root` therefore represents that component **together with its tail**, rather than a stand-alone local family. Its `tail_root` identifies that distinction explicitly.

Each decision node stores a variable position and exclusion/inclusion children. Identical triples (variable, low child, high child) share a node. When the inclusion child is rejecting, the variable is omitted from the diagram and is forced absent on that edge. Equal low and high children are not collapsed: they correspond to two different subsets.

Terminal 0 rejects; terminal 1 accepts the empty remaining selection. For each node v, the exact cardinality polynomial is

```text
P_v(z) = P_low(z) + z P_high(z),   P_0(z)=0, P_1(z)=1.
```

Its coefficient of z^k counts k-element selections. The recurrence and the residual-constraint branch rules partition the complete finite family. They provide the exhaustion argument for the maximum cardinality and its count. All coefficients are computed with BigInt and serialized as decimal strings.

The actual diagram has 268 nodes including its two terminals. The constructor retained 15,350 coefficient cells across nonterminal nodes. The root polynomial has degree 77 and leading coefficient 37,908. Summing its coefficients gives the total family count stated above. The full root coefficients, not only these summary numbers, are retained.

Constructor limits were fixed before the actual run: N from 3 through 128, each component at most 24 vertices, at most 200,000 new recursive states and at most 2,000,000 nonterminal coefficient cells. The actual run used 405 states and 286 memo hits, created 266 nonterminal nodes, reused 20 existing node triples and made 87 zero-inclusion reductions. No limit was reached and no expanded or repeated run occurred.

## Saved conditional navigation

```javascript
const {openIndex} = require("./dilated_triple_families.cjs");
const saved = require("./interval96_family_index.json");
const api = openIndex(saved);

api.query({op:"family", size:77});
api.query({op:"select", size:77, rank:"18954"});
api.query({
  op:"family",
  condition:{required:[1,2], forbidden:[3]}
});
```

The constructor is `compile(input)`; saved consumers use `openIndex(snapshot)`. Reopening checks saved dimensions, the variable permutation, coefficient string format and child/variable ordering. It converts saved coefficients to BigInt but does not recompute the constructor's coefficient recurrence, factor components or regenerate constraints. These are structural consistency checks on trusted saved output, not a hostile-input verification of every coefficient.

A condition has arrays `required` and `forbidden` of distinct host labels. The arrays are sorted for caching; duplicates, out-of-host labels and overlap between the two arrays are invalid. Up to 16 distinct conditions can be cached in one reader. Empty arrays mean the unrestricted family.

Conditioning uses the saved diagram. A required variable prohibits exclusion, and a forbidden variable prohibits inclusion. Because diagram edges can skip forced-absent variables, each traversal checks whether a skipped interval contains a required variable; if so, that branch contributes zero. This check also applies before an accepting terminal. Unconstrained suffixes reuse saved coefficient vectors immediately.

Other suffixes get newly computed conditional polynomials, memoized separately for each condition. Their cumulative reader budget is 500,000 coefficient cells. This fresh query arithmetic is reported explicitly and is distinct from rebuilding the original family or base coefficients.

An optional `size` restricts navigation to one cardinality from 0 through N. Omitting it counts all cardinalities. Ranks and offsets are nonnegative decimal **strings**, since the represented family greatly exceeds safe integer counts. Selection follows the exclusion-before-inclusion order, comparing a rank with the relevant low-child count. Ranking adds that count when an included variable is taken. Skipped selected variables, impossible branches and unsatisfied conditions produce nonmembership.

| Operation | Result |
| --- | --- |
| `summary` | Host, component, constraint and node counts; total and maximum-cardinality count; variable order; constructor work |
| `family` | Condition, selected-size count, full conditioned coefficient vector and maximum conditioned cardinality |
| `select` | Subset at a decimal rank, optionally at a fixed size |
| `rank` | Membership and decimal rank of a supplied subset |
| `page` | Up to 256 ranked subsets from a decimal offset |
| `classify` | Admissibility and the first fully selected saved forbidden triple, if any |
| `component` | One component's labels, residual starting masks and root/tail references |
| `node` | One saved decision node and its complete coefficient vector |
| `conditions` | Every cached condition's full coefficient summary |

The `classify` query directly checks saved constraint triples and counts those checks as new reader work. It does not refactor labels or regenerate triples. It concerns the unconditioned non-ternary property; use `rank` for membership in a filtered family.

The `family` response's full coefficients and maximum fields concern the condition across all cardinalities even when `size` selects a single count. A contradictory positive condition returns a zero count, empty coefficient vector and null maximum size. Selection from it is invalid. The empty subset has one representation in the unrestricted size-zero family.

All saved input and returned query objects are copied. Decimal counts and ranks must remain strings in transport.

## Actual reader results

The new reader produced 36 complete outputs, each individually banked before the next query. There were no exceptions or lost responses. Nine select/rank pairs matched exactly, including the first, middle and last maximum-size subsets and the first, middle and last members of the full family.

| Condition | Total admissible subsets | Maximum size | Maximizers |
| --- | ---: | ---: | ---: |
| None | 1,877,043,752,444,810,703,667,200,000 | 77 | 37,908 |
| Require 1 and 2; forbid 3 | 254,260,700,962,573,254,656,000,000 | 77 | 28,431 |
| Require 32, 48 and 96 | 70,416,898,032,431,792,128,000,000 | 76 | 47,385 |
| Forbid 1 through 6 | 54,360,024,184,856,248,320,000,000 | 74 | 13,122 |
| Require 1, 2 and 3 | 0 | None | 0 |

“Maximizers” means maximum cardinality within the given condition. It does not mean every inclusion-maximal subset.

The packet includes the first and last twenty unrestricted size-77 subsets, full coefficients for all five conditions, component 0 and component 31, the root node, unrestricted size-zero and size-96 counts, and both valid and invalid subset classifications. The first maximum subset's saved-constraint classification is valid. The set {1,2,3} is rejected with that same triple as its witness.

The nine exact inverse-rank matches are:

| Family | Rank |
| --- | ---: |
| Unrestricted size 77 | 0 |
| Unrestricted size 77 | 18,954 |
| Unrestricted size 77 | 37,907 |
| All unrestricted sizes | 0 |
| All unrestricted sizes | 938,521,876,222,405,351,833,600,000 |
| All unrestricted sizes | 1,877,043,752,444,810,703,667,199,999 |
| Require 1,2 and forbid 3; size 77 | 28,430 |
| Require 32,48,96; size 76 | 0 |
| Forbid 1 through 6; size 74 | 0 |

The reader created five conditions and had 24 cache hits. Its actual new work comprised 259 conditional-node calculations, 15,660 conditional coefficient cells, 4,706 saved-polynomial shortcut accesses, 16 skipped-required rejections, 4,275 selection steps, 796 rank steps and 33 saved-constraint checks. These counters describe the named operations rather than every interpreter action. Constructor-state creation, factor division, constraint generation and base-coefficient reconstruction counters were all zero.

## Custody and files

| Artifact | Git blob |
| --- | --- |
| Frozen declared input | `458b1dc01f29c3ce470d5f7845a88a4f71526d21` |
| Executed constructor/reader source | `8854665a14bf7bf33943b4c124d14b9f73ebcbff` |
| Complete family index | `96adc069d6af628c0eb8c24c1815cf3a1ca08a6f` |
| Complete reader packet | `11ca9baeef34434c76790c77e06f8011ff87dd75` |

The package publishes `dilated_triple_families.cjs`, `interval96_family_index.json`, `saved_reader_queries.json`, this guide and `README.md`. The full index retains every component, variable, constraint, node and coefficient used by the actual consumer. The represented subsets themselves are generated only when requested.

The results apply to this one finite interval and its declared conditions. No limiting density, irrationality decision, global optimization algorithm bound or mathematical priority claim follows from the finite numbers.
