# Exact prefix navigation for interlacing triangles

The module counts and navigates triangular arrangements of the labels $1,\ldots,N$, where $N=h(h+1)/2$ and every entry is strictly between its two adjacent entries below it. Rows may change direction.

The actual height-6 index contains all **16,814 admissible value-prefix states**, their exact counts, and all 441 cell-label marginal counts. Its total is **42,263,042,752 arrays**, the existing height-6 value of OEIS A347608. The saved index makes this finite family directly usable for selection, ranking, prefix completion counts, and cell distributions.

## 1. Coordinates, labels, and source convention

The input height is positive. Rows are displayed from the one-cell top row to the $h$-cell bottom row. Row and column coordinates are zero-based:

$$
0\le r<h,\qquad 0\le c\le r.
$$

The row-major cell index is

$$
\operatorname{cell}(r,c)=r(r+1)/2+c.
$$

A valid array uses every integer $1,\ldots,N$ exactly once. For an upper cell $u$ with lower neighbors $v,w$, it requires

$$
a_v<a_u<a_w
\quad\text{or}\quad
a_w<a_u<a_v.
$$

Thus neither increasing rows nor a single common orientation is assumed. Horizontal reflections are distinct arrays. No quotient by reflection or by value complement is taken. Height zero is outside the accepted input; height one is a valid endpoint.

This follows [Clark Kimberling's problem 18](https://faculty.evansville.edu/ck6/integer/unsolved.html). Sidoli's note and OEIS display their row indices starting with the long row; reversing that display order gives the coordinates used here without changing the betweenness condition.

## 2. The exact value-prefix representation

For a completed array and $0\le k\le N$, let

$$
S_k=\{c:a_c\le k\}.
$$

It records the cells occupied by the smallest $k$ labels, without recording their internal order. Write its membership bits as $b_c=1_{c\in S_k}$.

For every upper/lower triple $(u;v,w)$, admissibility means

$$
\min(b_v,b_w)\le b_u\le\max(b_v,b_w).
$$

Exactly two local patterns are forbidden: the top alone is present, or both lower cells are present while the top is absent.

### Bijection with complete chains

Every valid array yields a chain

$$
\varnothing=S_0\subset S_1\subset\cdots\subset S_N=E,
\qquad |S_k|=k,
$$

of admissible subsets. Strict betweenness implies the binary condition at every threshold.

Conversely, assign label $k$ to the unique cell added in $S_k\setminus S_{k-1}$. If an upper label were smaller than both lower labels, its own threshold would exhibit the forbidden top-only pattern. If it were larger than both, the threshold at the larger lower label would exhibit the other forbidden pattern. Therefore every triple satisfies strict betweenness.

These two operations are inverse. Counting the full arrays is exactly counting the maximal one-cell chains through admissible prefix subsets. Different internal orders reaching the same subset are kept by a forward count, rather than collapsed into one array.

### Every admissible subset can occur

The local condition also suffices for a subset to be an actual value cut of some valid array. Assign distinct real values in $(0,1)$ to its bottom-row cells and in $(2,3)$ to the other bottom-row cells. Work upward, always choosing a previously unused value strictly between the two lower values and inside the required interval.

If both lower bits agree, admissibility forces the upper bit to agree, and their open interval lies in that same band. If the bits differ, the interval between their values meets both bands in a nonempty open interval. Each choice can avoid the finitely many values already used.

Finally replace all distinct real values by their ranks. Strict comparisons remain unchanged, and every selected cell precedes every unselected cell. The subset is therefore a prefix of that valid integer array. This argument supplies both a path into the subset and a path out to the full set; no separate enumeration of binary patterns is needed.

The same two forbidden binary patterns already appear in Sidoli's orientation construction. Here the bits encode membership at a value threshold, with one bit for every cell. The orientation interpretation and its prior attribution are kept separate.

## 3. Transitions and exact counts

A transition adds one unused cell $c$ to an admissible set $S$. Only the local triples containing $c$ can change.

When $c$ is the top of a lower triple, exactly one of its children must already be present. When $c$ is a lower member of an upper triple, it may be added unless the top is absent and the other lower member is already present. There is at most one lower triple and two upper triples to inspect for any cell.

The compiler starts with the empty set and explores every admitted transition, recording each state once. Every edge raises the number of assigned labels by one, so the graph is acyclic.

Let $F(S)$ count paths from the empty prefix to $S$, and let $C(S)$ count paths from $S$ to the full set. The exact recurrences are

$$
F(\varnothing)=1,\qquad
F(S\cup\{c\})\mathrel{+}=F(S),
$$

and

$$
C(E)=1,\qquad
C(S)=\sum_{S\to S\cup\{c\}}C(S\cup\{c\}).
$$

Forward and reverse graph passes evaluate these integers using BigInt. The total is $C(\varnothing)=F(E)$.

For a **specified valid order** of the smallest labels ending at $S$, the number of completions is $C(S)$. The number of all arrays whose smallest labels occupy the same *set* $S$, allowing every valid internal prefix order, is $F(S)C(S)$. The API returns both constituent counts and explicitly distinguishes their meanings.

### Cell-label marginals

For cell $c$ and label $k$, the number of complete arrays having $a_c=k$ is

$$
M(c,k)=
\sum_{\substack{|S|=k-1\\S\to S\cup\{c\}}}
F(S)\,C(S\cup\{c\}).
$$

A full path with that cell-label pair splits uniquely at its transition adding $c$. Its prefix and suffix can be chosen independently, which gives the product in the summand. Each complete array contributes once to the relevant cell-label entry.

The compiler retains this entire $N$ by $N$ table. The marginal interface retrieves saved counts; it does not run a second enumeration.

### Ordering for rank and selection

An array is encoded by the row-major cell occupied by label 1, then by label 2, through label $N$. The interface uses zero-based lexicographic order on this sequence of cell indices. This is an explicit API choice; it is not lexicographic order on the displayed rows of values.

At a prefix, outgoing cells are considered in increasing index order. An outgoing branch has exactly $C(S\cup\{c\})$ completions. Selection subtracts the sizes of preceding branches; ranking adds those sizes before following the supplied array. The branch trace records each skipped weight and the residual rank.

## 4. Public interface

The dependency-free CommonJS module exports:

| Export | Purpose |
|---|---|
| `compileInterlacingPrefixIndex({source_id,height,budget})` | Compile a bounded complete prefix graph, both count directions, and all cell-label marginals. |
| `openRetainedInterlacingPrefixIndex({source_id,snapshot})` | Open saved complete counts as an explicit source premise. |
| `INTERLACING_LIMITS` | Height, state, transition, work, count-input, and page bounds. |

The optional budget may lower the state, transition, and candidate-check limits. It may not enlarge them.

An opened index exposes:

| Method | Meaning |
|---|---|
| `describe()` | Saved count, finite dimensions, ordering and validation boundary. |
| `select({rank})` | A complete array, its label-position sequence, and the exact branch trace. |
| `rank(rows)` | The index of a supplied complete array, or an explicit invalid-array result. |
| `countCompletions({label_positions})` | Completion count for one supplied prefix order, and all prefix orders reaching its occupied-cell set. |
| `cellValueCounts({row,column})` | The retained distribution of labels at one zero-based cell. |
| `page({start_rank,limit})` | Consecutive ranked arrays, with an explicit next rank or null. |
| `snapshot()` | A detached JSON-compatible copy of the saved index. |

Ranks accept nonnegative BigInt values, safe integer Numbers, or canonical decimal strings. Unsafe Numbers and noncanonical strings are refused. Selection requires rank below the saved count. A page may start exactly at the count and return an empty terminal page.

Array rows must have lengths $1,2,\ldots,h$ and contain each label once. A structurally valid permutation that fails the interlacing path returns `INVALID_ARRAY`. Repeated cells or a forbidden local step in a proposed prefix return `INVALID_PREFIX`, with the first invalid label. Malformed types, dimensions, or labels throw an input error.

### Retained use

```js
const api = require("./interlacing_prefix_index.cjs");
const saved = require("./height6_prefix_index.json");

const index = api.openRetainedInterlacingPrefixIndex({
  source_id: "the pinned Commons height-6 dataset",
  snapshot: saved.compilation.snapshot
});

const midpoint = index.select({rank: "21131521376"});
const extensions = index.countCompletions({
  label_positions: midpoint.label_positions.slice(0, 7)
});
// completion_count: "4084080"
// all_prefix_orders_to_this_mask: "4"

const top = index.cellValueCounts({row: 0, column: 0});
const last = index.page({start_rank: "42263042748", limit: 4});
// four complete arrays, next_rank: null
```

In connected V8, evaluate a retrieved module string with `new Function("module","exports",sourceText)` and supply the previously retrieved snapshot object. Retrieval and pinning are outside this module. It performs no network, process, or filesystem operation.

## 5. Saved records and validation boundary

Each saved record is

```text
[prefix_mask_hex, ways_to_reach_prefix, ways_to_complete_prefix]
```

Bit $c$ refers to row-major cell $c$. Hexadecimal masks have no prefix or leading zero, except the empty mask `"0"`. Records are sorted by their numeric mask. Counts are canonical decimal strings. Every record occupies one explicit JSON line.

The full graph is represented by these states together with the module's local transition rule. Its 70,488 edge pairs are not separately duplicated in the snapshot. A query generates only the local options it needs and reads their saved suffix counts.

The loader checks bounded dimensions, strictly ordered mask encodings, decimal count encodings, the required empty/full records, the marginal-table shape, and the stated interface ordering. It does **not** authenticate the source, prove admissibility of every saved mask, establish complete state coverage, recompute the count recurrences, or recalculate marginals. The stored mathematics remains a trusted premise from the pinned compilation.

A rank, select, or prefix query does apply the local transition rule to its visited path. If a required successor is absent from the saved premise, it throws. This bounded query work is distinct from validating the entire graph or rerunning its counts.

## 6. Complete height-6 consumer

The original computation processed one requested height:

| Item | Recorded value |
|---|---:|
| Cells | 21 |
| Complete arrays | 42,263,042,752 |
| Prefix states | 16,814 |
| Transitions | 70,488 |
| Candidate cell checks | 176,547 |
| Local clause checks | 301,735 |
| Forward count additions | 70,488 |
| Suffix count additions | 70,488 |
| Marginal weight products | 70,488 |

The observed 211 ms is one runtime observation, not a benchmark or a comparison with prior implementations. The complete snapshot retains both counts at every state and all 441 marginals.

A fresh connected V8 call opened that snapshot. It selected ranks 0, 10,000,000,000 and 21,131,521,376; exported the last four arrays; ranked the horizontal reflection of the midpoint array; queried two prefixes; and retrieved two cell distributions. The graph traversal and count passes were not repeated.

For example, rank 10,000,000,000 has these rows:

| Row | Labels from left to right |
|---:|---|
| 0 | 14 |
| 1 | 13, 16 |
| 2 | 10, 17, 12 |
| 3 | 6, 18, 15, 4 |
| 4 | 5, 9, 20, 3, 8 |
| 5 | 7, 1, 21, 11, 2, 19 |

This visibly retains changing row directions. The complete selected arrays and all branch traces are in the dataset.

For the midpoint array, its first seven assigned positions reach mask `4109b`, with 4,084,080 completions of that specified prefix order and four prefix orders reaching the same set. Its first fourteen positions reach `4b7bf`, with 280 completions and 134,680 prefix orders. The reflected midpoint's rank is 16,320,132,291.

### Top-label distribution and elementary symmetries

Following a strictly smaller child at each row below the top gives $h-1$ distinct labels smaller than the top. Following larger children gives $h-1$ larger labels. Therefore every valid top label lies in

$$
h\le a_{\mathrm{top}}\le N+1-h.
$$

For height 6, the recorded distribution is:

| Top label | Complete arrays |
|---:|---:|
| 6 or 16, each | 568,169,616 |
| 7 or 15, each | 1,901,411,104 |
| 8 or 14, each | 3,650,985,072 |
| 9 or 13, each | 5,271,321,280 |
| 10 or 12, each | 6,365,767,008 |
| 11 | 6,747,734,592 |

All other top labels have zero count. The finite output attains every value in the permitted interval.

Horizontal reflection preserves the condition, as does replacing every value $a$ by $N+1-a$. Consequently the corresponding cell marginals are equal at mirror cells and symmetric in the label $k$ versus $N+1-k$. In the uniform finite family, every fixed cell has exact mean label $(N+1)/2$. These are elementary bijection consequences, not additional computation claims.

## 7. Bounds and unfinished results

| Resource | Hard limit |
|---|---:|
| Height | 7 |
| Cells at the height cap | 28 |
| Discovered prefix states | 65,536 |
| Admitted transitions | 1,048,576 |
| Candidate cell checks | 2,097,152 |
| Digits in accepted rank/count strings | 64 |
| Arrays per page | 128 |

The height cap keeps every mask below $2^{28}$, within positive safe Number bit operations. Counts and ranks use BigInt. State indices, cells and work counters use bounded safe Numbers.

If there are $R$ discovered states and $E$ admitted transitions, the traversal makes at most $NR$ candidate tests, each using at most three local clauses. The count passes perform $O(E)$ exact arithmetic operations. The live compiler stores the graph in $O(R+E+N^2)$ space; the retained index omits duplicated edge pairs and stores $O(R+N^2)$ records and marginal entries. Integer bit costs are separate from these operation counts.

A state, transition, or candidate limit returns `RESOURCE_LIMIT` with the discovered graph, the last fully processed node, the current partial node/cell and work accounting. Its exact total is null. The current outgoing row can be unfinished; such data are not accepted by the complete-index loader. The implementation does not describe an unfinished graph as a finite exact count.

Only height 6 was executed for this delivery. Height 7 remains an accepted input subject to the caps; it was not run, and completion at that height is not promised. The resource-stop and invalid-input branches were inspected in source without a synthetic execution suite. No higher-height search was added for a larger headline.

## 8. Attribution and remaining scope

The family is Kimberling's strict interlacing problem. [OEIS A347608](https://oeis.org/A347608), credited to **James B. Sidoli** (2021), already records 42,263,042,752 triangles at height 6. Its higher terms for heights 7–9 are explicitly credited to **Dylan Nelson** (2022). The height-6 total here is prior enumeration, not a new term or a claim about the largest existing computation.

Sidoli's posted note, [*On the Number of Interlacing Triangles of Size n*](https://oeis.org/A347608/a347608_2.pdf) (October 29, 2021), supplies the orientation-poset decomposition, its two forbidden binary patterns, and the sum of linear-extension counts in Theorem 3.1. These retain their original attribution. The note is a publicly posted author paper; no journal-publication or independent proof-review status is asserted here.

The prefix bits in this API record membership among the smallest labels already assigned. They do not encode local comparison orientations. The retained height-6 artifact records 16,814 states and the rule defining their 70,488 transitions, supports exact prefix navigation, and includes every cell-label marginal. These are this implementation's finite artifact results. Generic hardness of counting linear extensions does not, on its own, classify this restricted family.

This finite package supplies explicit source-bound data and navigation. The saved records support exact finite questions for height 6; they do not imply a product formula, asymptotic enumeration, a complexity classification of Kimberling's restricted family, or an external numerical frontier. Original authorship and submission ownership remain with their sources.

