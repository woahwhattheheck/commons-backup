# Exact binary AP-coloring completions

This package compiles all labelled binary colorings of a finite integer interval that avoid a monochromatic arithmetic progression of a specified length. It shares equal residual constraint states in a decision diagram and stores an exact generating polynomial at each node. The coefficient of z^t counts completions using exactly t further positions of color 1.

The actual input is [1,17] with four-term progressions. It has **40 progression constraints and exactly 1,850 avoiding colorings**. The complete saved diagram has **2,331 nodes and 16,748 coefficient cells**. A separate reader provides partial-assignment counts, lexicographic rank/select, prefix counts and explicit failure witnesses.

## Sources and scope

The mathematical input uses the explicit finite interval coloring definition in the current FormalConjectures source below. Its references include Campos, Fox and Schildkraut, *A new lower bound for two-color van der Waerden numbers*, [arXiv:2608.20824](https://arxiv.org/abs/2608.20824), for recent progress on a separate normalized variant. The single exact author-page request returned an access error and no abstract or introduction bytes; that route is held without retry or alternate access. Accordingly this guide attributes status annotations to the actually read formal source and does not claim independent verification of that paper, its numerical bound or its proof. The finite algorithm and its correctness argument are specified explicitly below.

The separately read [FormalConjectures/ErdosProblems/138.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/138.lean) defines W(k) as the least N for which every two-coloring of {1,...,N} has a monochromatic k-term progression. Its complete decoded source had computed Git blob identity **30be876091889dcd72d210c510035b888f3e94d9**. The connector returned no immutable upstream commit or provider blob, so this is an exact content identity rather than an upstream pin.

That source marks the main question W(k)^(1/k)→∞ and the ratio question W(k+1)/W(k)→∞ as research open. It separately marks W(k+1)−W(k)→∞ and W(k)/2^k→∞ as research solved, citing external formal developments and recent work. Its local theorem bodies remain placeholders. No external proof, Lean source or proof-search artifact was opened, executed or audited. A historical explanatory exponent in the source disagrees with its adjacent formal Berlekamp statement; this package does not transfer that prose.

This finite index does not compute a van der Waerden threshold, improve an asymptotic bound, establish any of those limits or claim numerical novelty. It gives a complete family and exact conditioned navigation at one declared input. The older [PPL061 catalogue card](https://prizeproblems.org/problems/061/) is an intake locator, not an authority overriding the current distinctions.

## Input conventions

A coloring is a map {1,...,n}→{0,1}, represented by a binary string whose first symbol colors integer 1. The two colors are distinguished. Global color exchange, reflection of the interval, or any other symmetry is not quotiented. Empty color classes are allowed by the general coloring convention, although they yield no accepted coloring in this actual input.

A progression is the set of k distinct positions

~~~text
a, a+d, ..., a+(k−1)d,
a >= 1, d >= 1, a+(k−1)d <= n.
~~~

The common difference is a positive integer. Constant progressions are excluded. Reversing a progression does not create a second constraint. The compiler lists differences in increasing order, then starts in increasing order, and retains each progression's exact vertices and bit mask.

The one input is:

~~~js
{
  n: 17,
  length: 4,
  provenance: { /* complete identified source scope in the data file */ }
}
~~~

It uses the standard finite family from the van der Waerden definition. No source-authored threshold coloring is claimed as input. Root's earlier three-term progression-free subset family is neither read nor regenerated. The present constructor forms this new four-term constraint set once.

## Complete finite result

| Number of positions colored 1 | Avoiding colorings |
|---|---:|
| 0–5 | 0 |
| 6 | 8 |
| 7 | 180 |
| 8 | 737 |
| 9 | 737 |
| 10 | 180 |
| 11 | 8 |
| 12–17 | 0 |

The total is 1,850. The symmetric counts are consistent with the mathematical involution exchanging colors, but the two members of each exchanged pair remain separate in the index. No second computation was performed to recount a symmetry quotient.

Binary strings use ordinary lexicographic order, 0 before 1, and ranks start at zero.

| Family | Rank | Coloring |
|---|---:|---|
| All avoiding colorings | 0 | 00010010101101000 |
| All avoiding colorings | 925 | 10001001010110100 |
| All avoiding colorings | 1849 | 11101101010010111 |
| Exactly eight ones | 0 | 00010010101101011 |
| Exactly eight ones | 368 | 01100011101101000 |
| Exactly eight ones | 736 | 11101001010010100 |

The prefix 000 admits 156 completions. The prefix 0000 admits none. A rank request for the all-zero word returns failure at position 4 with the retained progression [1,2,3,4] and color 0 as its explicit witness.

### Nonconsecutive prescribed positions

The new conditioned query fixes

~~~text
position 1 = 0
position 9 = 1
position 17 = 0
total number of ones = 8.
~~~

There are exactly **132** completions.

| Conditioned rank | Coloring |
|---|---|
| 0 | 00010010101101110 |
| 66 | 01010011101101000 |
| 131 | 01110110101001000 |

The retained rank query for the middle word returns 66 in that same conditioned family. These fixed positions were chosen from the newly selected balanced word; the condition therefore has identified finite input custody. It is not a new universally forced-color theorem.

The full 25-query output includes selection traces, rank traces, prefix counts, one failure witness, and saved conditioning tables for the unrestricted, weight-eight and nonconsecutive fixed-position contexts. Those three exported context tables contain 34, 38 and 999 rows respectively. The two prefix count calls also performed query work; their returned counts are retained without an additional replay to export their internal memo tables.

## Residual constraint semantics

At a node of level ℓ, positions 1 through ℓ have already been assigned and positions ℓ+1 through n remain. For each color c, a residual set T means:

~~~text
the positions in T may not all receive color c.
~~~

The node retains a family F_c of such forbidden monochromatic tails. Initially each original progression appears once in each color family.

When the next position receives color c:

1. A c-tail containing that position loses its assigned bit. If the tail becomes empty, the branch would finish a monochromatic progression and is rejected.
2. An opposite-color tail containing the position is satisfied and removed, because that position now has the opposite color.
3. A tail not containing the position remains unchanged.
4. Within each color family, a tail containing a retained smaller tail is redundant and is removed.

The fourth step is exact: prohibiting all elements of A from having color c already prohibits all elements of B from having color c whenever A⊆B. The compiler retains every discarded superset and a retained subset witness for it. Candidate tails are processed by increasing cardinality, so a kept subset used as a witness cannot later be removed by a larger candidate.

Two prefixes at the same level with identical canonical residual families admit exactly the same suffix colorings. They can therefore share one node. The memo key includes the level and both sorted mask lists; no color exchange is used in this key.

This is a finite residual-constraint decision diagram. The implementation does not claim a new decision-diagram method or complexity theorem.

### Count recurrence

For a node v, let C_v(z) be its suffix generating polynomial, with z counting positions colored 1. A rejecting arc has polynomial zero. The unique accepted terminal at level n has polynomial one. For other nodes,

~~~text
C_v(z) = C_child0(z) + z*C_child1(z).
~~~

Every suffix starts with exactly one of the two color choices, and the two cases are disjoint. This proves the recurrence. Level increases along every accepted edge, so the graph is acyclic even when node IDs do not increase along every reused edge.

Each node at level ℓ retains exactly n−ℓ+1 coefficients. Leading and trailing zeros remain explicit. Coefficients are decimal BigInt strings in the portable JSON; no floating-point count arithmetic is used.

Induction on the remaining positions proves that the root polynomial counts exactly all avoiding binary colorings. The original constraints, residual families, two arcs per nonterminal, singleton rejection witnesses, subsumption witnesses and every coefficient row are retained. This is a complete finite construction record, not an independent formal proof audit.

## Conditioning and navigation

A fixed-position query supplies distinct one-based positions and their required colors. It may also supply an exact total number of ones.

The reader walks only permitted saved arcs. Its memo key is the saved node and remaining ones count; a null count means any number of ones. Once all fixed positions have been passed, it reads the corresponding saved coefficient or sum of coefficients directly. Earlier branches recurse through the existing diagram.

This is **new conditioning arithmetic on a saved base index**. It is not falsely described as zero query computation. It generates no new arithmetic progressions, residual constraints, subsumption comparisons or base coefficient rows.

Rank/select uses these conditioned suffix counts. At a free position, the entire zero branch precedes the one branch. Selection compares the desired rank with that zero-branch count and subtracts it when choosing one. Ranking adds it whenever the supplied word chooses one. A forced color contributes only its permitted branch. The returned trace records the node, position, selected color, skipped or zero-branch count, child and rank arithmetic.

An invalid complete word can fail its required weight, a fixed position, or a rejecting diagram edge. In the last case, the reader locates an original progression completed in the rejected prefix and returns its actual vertices and color. This is an explicitly counted scan of saved constraints, not regeneration of the AP list.

The ordering is over complete labelled colorings, not interval partitions with unlabelled colors and not graph isomorphism classes.

## Files and source custody

- ap_coloring_dag.cjs — pure CommonJS compiler and saved reader.
- AP_COLORING_API.md — this guide.
- interval17_four_ap_colorings.json — core snapshot, input, shard manifest and all 25 query outputs.
- nodes_0000_1199.json — nodes 0 through 1199.
- nodes_1200_2330.json — nodes 1200 through 2330.
- README.md — entry point and scope.

The two node shards are a storage division of the original complete node array. They do not represent separately recomputed graphs.

| Artifact | Exact Git blob identity | UTF-8 bytes |
|---|---|---:|
| Frozen source | 051e6934cdb0e902eb6413db485d93f9d514a1b6 | 12,794 |
| Standalone input | 3088df4e2cbb8c354d0598ca7c10a2fa02104c6a | 573 |
| Complete initial result | e63cbcf8946361dc91941bb5a262594717d582ff | 823,766 |
| First node shard | b9715e91f9ff479dd59c691c19c9e44442f2e52e | 401,934 |
| Second node shard | aa8c5dadc8f0244dca7d0ebd3f873f5e6d81b936 | 417,104 |
| Final core/query record | 287bb8f6e1c75d2b99ed0244c7219a220270b228 | 132,591 |

The source and exact input were banked before execution. The complete initial result was banked in the same call as the one construction. Both complete node shards and the final record were then banked. The source has not changed since the actual call.

The standalone initial result is a complete immutable banked object; the repository's core plus its two manifest-bound shards are the published complete portable representation.

## API

~~~js
const {
  VERSION,
  compileAPColorings,
  openAPColorings
} = require("./ap_coloring_dag.cjs");
~~~

For an already saved record, assemble the complete node array from the two supplied shard texts:

~~~js
const core = JSON.parse(coreText);
const parts = [JSON.parse(firstShardText), JSON.parse(secondShardText)];
const nodes = [];
for (const part of parts) {
  if (part.start !== nodes.length ||
      part.end_exclusive !== part.start + part.rows.length) {
    throw new Error("noncontiguous node shard");
  }
  nodes.push(...part.rows);
}
const index = openAPColorings({...core.snapshot, nodes});

index.countFixed([], 8);
index.selectFixed([[1,0],[9,1],[17,0]], 8, "66");
index.rankFixed("01010011101101000", [[1,0],[9,1],[17,0]], 8);
index.countPrefix("000");
index.conditioningData([[1,0],[9,1],[17,0]], 8);
index.statistics();
~~~

The manifest supplies each shard's exact blob identity and range. The actual fresh reader checked ranges, assembled 2,331 nodes and opened that saved array without rebuilding the compiler state.

### Compiler

~~~js
const snapshot = compileAPColorings({
  n: 17,
  length: 4,
  provenance: { /* identified source and finite scope */ }
}, {
  max_nodes: 300000,
  max_coefficients: 1000000
});
~~~

Accepted inputs have 2≤n≤24 and 2≤length≤n. The node budget defaults to 300,000 and may be set from 1 to 500,000. The coefficient-cell budget defaults to 1,000,000 and may be set from 1 to 2,000,000.

Budget exhaustion throws without returning a completed snapshot. No resumable partially compiled artifact is advertised. Other input sizes and lengths were source-inspected only; no synthetic or threshold consumers were executed.

Position masks use integers below 2^24, within the exact bitwise range used here. All counting coefficients use BigInt. The implementation has no filesystem, network or external-process calls.

### Saved reader

openAPColorings accepts the complete snapshot object or a JSON string, with a 32,000,000-character limit for string input. It copies the record and validates schema, input limits, node IDs and levels, residual masks on future positions, ordered mask lists, coefficient shapes, two-branch structure, child levels, terminal shape, saved singleton rejection bindings, subsumption subset witnesses and progression vertex/mask bindings.

It does not regenerate the complete AP family, prove the residual antichains from original prefixes, repeat transitions or subsumption normalization, or recompute base coefficient recurrences. Edited snapshots are not independently authenticated by these structural checks.

The reader supports at most 64 distinct conditioning contexts per open. The cumulative conditioning-state budget defaults to 500,000 and may be set from 1 to 1,000,000 through max_condition_states. A query exceeding that budget throws; it does not return an invented count.

| Method | Contract |
|---|---|
| summary() | Saved root total, weight coefficients and size metadata |
| progressionsPage(start=0,limit=32) | Retained AP rows, ordered by difference then start |
| nodesPage(start=0,limit=32) | Complete saved node records |
| node(id) | One saved node |
| countFixed(fixed=[],ones=null) | Exact conditioned count |
| countPrefix(bits,ones=null) | Count after prescribing the initial binary string |
| selectFixed(fixed,ones,rank) | Zero-based lexicographic selection and trace |
| rankFixed(word,fixed=[],ones=null) | Rank/trace or a stated failure |
| conditioningData(fixed=[],ones=null) | Current exact memo rows for that conditioning context |
| statistics() | Actual reader-operation counters |

Fixed assignments are arrays of [position,color], with positions from 1 to n and color 0 or 1. Input order is immaterial: the reader sorts by position. Repeating a position is rejected even if its color agrees. An exact ones count is an integer from 0 to n; null imposes no weight restriction.

Complete words have exactly n binary symbols. Prefixes may be empty and have length at most n. Ranks are nonnegative safe integer Numbers or canonical decimal strings of at most 100 digits. Page limits are 0–64 and starts range through the array length. Node IDs and all ranks are zero-based.

Conditioning contexts are cached by normalized fixed assignments and the exact weight constraint. A later selection or rank operation can reuse the same context. It can also add saved-coefficient lookup rows for suffixes not needed by the initial root count. conditioningData returns the memo rows currently held, not a claim that every possible query state has been evaluated.

Reader methods return copies rather than mutable references to the saved graph.

## Actual work

The once-only constructor formed:

- 40 four-term progression constraints.
- 2,331 residual nodes.
- 4,660 directed color transitions, including 1,160 rejecting transitions.
- 16,748 coefficient cells.
- 22,250 coefficient additions.
- 4,686 discarded-superset witnesses.
- 40,816 residual-mask visits and 102,118 subsumption comparisons.
- 3,501 recursive calls with 1,170 memo hits.
- Zero individual complete colorings enumerated during construction.
- Zero old three-term-family computations.

The observed constructor elapsed time was 70 ms in one connected-runtime observation. This is not a benchmark or performance promise.

The separate reader made 25 calls. It opened all 2,331 nodes, 16,748 coefficient cells and 40 source constraints; exported the full AP list and selected node pages; made counts and nine complete-word selections; ranked two accepted words; reported one rejected word; and retained three conditioning-table outputs.

Its counters record 1,079 new conditioning memo states, 15 conditioning-context cache hits, 74 saved-coefficient lookups, 153 selection steps, 38 rank steps and one saved-progression witness check. New AP generation, residual states, subsumption comparisons and base coefficient rows were all zero.

The finite counts, all diagram records and new query outputs are complete for the declared input. They do not identify an unrestricted van der Waerden threshold or settle its growth questions.
