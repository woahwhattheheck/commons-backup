# Finite dictionary factor index

This package constructs a bounded exact index for contiguous factors of the Kleene star of a finite dictionary. When the search finishes with a missing word, it retains the entire shortest-word family as a finite directed acyclic graph, with exact counts and zero-based lexicographic rank/select. When it closes the reachable graph without reaching the empty subset, it establishes factor universality for that input.

The actual consumer is the published binary dictionary $S_6$. Its index contains 1,383 subset states, establishes shortest missing length 91, and accounts for **all 128 shortest missing words**. Every one of those words and its state path is saved in `gusev_pribavkina_s6_factor_index.json`.

## 1. Sources and scope

The historical intake card points to [Jeffrey Shallit's problem slides, slide 45](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf). Problem 17 asks for the complexity of deciding $\operatorname{Fact}(L^*)=\Sigma^*$ from a finite list; Problem 18 concerns the shortest missing length.

The decision complexity is settled. **Maksymilian Mika and Marek Szykuła**, [*The Frobenius and factor universality problems of the Kleene star of a finite set of words*](https://arxiv.org/pdf/1902.06702), *Journal of the ACM* 68(3), article 18 (2021), [DOI 10.1145/3456663](https://doi.org/10.1145/3456663), prove PSPACE-completeness even for binary alphabets in Theorem 5.12. Their exponential lower-bound examples also supersede a universal quadratic Restivo bound. This decision theorem does not separately classify counting or selecting shortest words. The old open-complexity framing is not used here.

The finite dictionary comes from **Vladimir V. Gusev and Elena V. Pribavkina**, [*On Non-Complete Sets and Restivo's Conjecture*](https://arxiv.org/pdf/1104.0388), DLT 2011, LNCS 6795, pp. 239–250, [DOI 10.1007/978-3-642-22321-1_21](https://doi.org/10.1007/978-3-642-22321-1_21). Section 2 defines, for $\Sigma=\{a,b\}$ and $k\ge4$,

$$
S_k=(\Sigma^k\setminus\{ba^{k-1},b^{k-1}a\})
\;\cup\;
(\Sigma^{k-1}\setminus\{a^{k-1},b^{k-1}\}).
$$

Their matching bounds in Sections 3–4 give shortest length $5k^2-17k+13$. Thus length 91 for $k=6$ is a credited published result. This historical family is not presented as the strongest general lower-bound family.

This package supplies finite computational data and a reusable interface. It claims no new general length bound, complexity classification, priority, or exhaustive literature frontier. The source papers' proofs were not audited or rerun.

## 2. Mathematical and string conventions

The caller supplies a finite ordered alphabet and a finite list of dictionary words. Dictionary multiplicity is discarded: repeated equal entries have no effect. Empty dictionary entries are also removed because they do not change $L^*$. Arbitrary finite concatenation allows dictionary entries to be used repeatedly, and the concatenation of zero entries is the empty word $\varepsilon$.

A factor is a contiguous substring. A word may start or end inside a dictionary entry and may cross any number of concatenation boundaries. In particular, a factor need not itself belong to $L^*$. The empty word is always a factor.

Alphabet entries are distinct Unicode scalar values, each supplied as a one-symbol string. Surrogate code points are rejected. There is no Unicode normalization: distinct scalar sequences remain distinct words. Word lengths count scalar values, not UTF-16 code units. Lexicographic order uses the caller's alphabet order, not an implicit locale or JavaScript string order.

The source problem uses a nonempty alphabet. The API additionally handles an empty alphabet: its only word is $\varepsilon$, so factor universality is immediate. For a nonempty alphabet with no nonempty dictionary entries, the shortest missing words are exactly the one-symbol words. These endpoint conventions are part of the interface; the recorded binary consumer does not exercise every endpoint.

## 3. Trie automaton for factors

Build a prefix trie of the distinct nonempty dictionary words, including the root $\varepsilon$. Mark the nodes that end dictionary entries. Add an epsilon transition from each marked node to the root, allowing another entry to begin. Before taking factors, the root is the initial and accepting state: closed walks from root to root spell precisely concatenations of dictionary words.

Every trie node is reachable from the root by its prefix. Every node can also reach the root: finish a dictionary word extending that prefix, then take the restart transition. Consequently, making **every trie node initial and accepting** recognizes exactly $\operatorname{Fact}(L^*)$:

- A path from any node to any node can be prefixed by a root-to-start path and followed by an end-to-root path. Its label is therefore a contiguous factor of a dictionary concatenation.
- Conversely, a factor of a root-to-root walk is the label of the corresponding subpath, whose endpoints are among those initial and accepting nodes.

This reasoning also covers the trie containing only the root. It uses the ordinary trie and subset constructions from automata theory, not a new decision-complexity argument.

The implementation folds each restart into the labeled transition entering a terminal node. If a trie edge leads to node $j$, its destination mask contains $j$ and also the root when $j$ is terminal. An absent edge has mask zero. Starting from all nodes and applying these rows keeps the active subsets epsilon-closed.

For an active subset $Q$ and symbol $c$, its next subset is the union of the stored destinations from all $q\in Q$. Since every node is accepting, a word is missing exactly when its resulting subset is empty.

## 4. Exact shortest-word certificate

The compiler performs breadth-first search from the subset of all trie nodes. Each distinct subset is assigned its first-discovery distance and parent. Outgoing symbols are processed in the explicit alphabet order.

If the empty subset first appears at distance $g$, the compiler finishes every transition row whose source distance is less than $g$. It retains the discovered frontier at distance $g$ but does not expand that frontier. Thus every possible path of length below $g$ has been accounted for, and none reaches the empty subset. The saved parent path supplies a missing word of length $g$.

If no empty subset is reached and every reachable row is processed, the finite subset graph is closed under every alphabet symbol. Induction on word length then establishes $\operatorname{Fact}(L^*)=\Sigma^*$.

A stopped search is different from either completion. It retains its partial graph and the explicit exhausted budget. Finding an empty subset before a later resource stop still supplies an exact non-universality witness and shortest length, but an unfinished predecessor layer does not yield a completed all-shortest-word count. The summary distinguishes the decision from completion of that count.

### Counting all shortest words

A prefix of a shortest missing word must reach its subset along a shortest path. Otherwise, replacing that prefix by a shorter path to the same subset and keeping the remaining suffix would produce a shorter missing word.

Therefore all shortest missing words lie in the distance-increasing subgraph: each used edge goes from distance $d$ to distance $d+1$. This is a DAG even though the full subset graph can have cycles.

Give the empty subset at distance $g$ suffix count 1 and every other distance-$g$ state count 0. In decreasing distance order, sum the counts on distance-increasing outgoing edges. The count at the initial subset is the exact number of shortest missing words. Multiple symbols reaching the same destination contribute separately because they form different words.

For selection, compare a zero-based rank against these outgoing counts in alphabet order, subtracting earlier blocks until the rank enters one block. Repeat at its destination. For ranking, add the counts of earlier symbol blocks along the supplied word. Every step shortens the remaining length, and the same partition of the word family defines both operations. Counts use BigInt and are serialized as canonical decimal strings.

## 5. Public interface

The dependency-free CommonJS module exports:

| Export | Purpose |
|---|---|
| `createFiniteFactorIndex(request)` | Build the trie, run one bounded subset search, and compute shortest-word counts if its predecessor layers finish. |
| `openRetainedFiniteFactorIndex({source_id, snapshot})` | Open a complete retained index as an explicitly identified premise, without rerunning the automaton search or count recurrence. |
| `FACTOR_INDEX_LIMITS` | Fixed maximum input, search, and paging bounds. |

An index provides:

| Method | Result |
|---|---|
| `describe()` | Status, source identifier, provenance, sizes, shortest length/count, decision state, and any resource stop. |
| `snapshot()` | A detached JSON-compatible copy of the complete or partial retained data. |
| `selectShortest(rank)` | The selected shortest word, its zero-based rank, length, and full subset path. |
| `rankShortest(word)` | The rank and path of a shortest missing word; rejects other words. |
| `pageShortest({start_rank, limit})` | Up to 128 ranked words, with a continuation rank or `null`. |

Ranks accept nonnegative BigInts, nonnegative safe integer Numbers, or canonical decimal strings. A page may start exactly at the family size and return no records. A zero-sized page is allowed; callers requesting further progress must use a positive limit.

Statuses are:

| Status | Meaning |
|---|---|
| `SHORTEST_MISSING_WORDS` | Shortest length and the complete shortest-word DAG/count are established for this finite input. |
| `FACTOR_UNIVERSAL` | All reachable subset rows are closed, with no empty subset. |
| `RESOURCE_LIMIT` | A stated budget stopped the search; inspect whether a missing witness was already found. No all-shortest count is supplied. |

The navigation methods require `SHORTEST_MISSING_WORDS`. They raise `NoMissingWordError` for a universal index and `IncompleteFactorSearchError` for an unfinished index. Invalid input shapes raise TypeError; out-of-range inputs, symbols, ranks, and words raise RangeError.

### Retained-index premise

The loader requires a complete snapshot. Its structural checks cover bounded array sizes, the ordered alphabet, subset-mask syntax/range/uniqueness, the initial subset, distances, parent indices, required transition entries, and the shortest endpoint/count fields. It does **not** authenticate the source identifier, rebuild the dictionary trie, recalculate transition images, replay BFS, or recompute the suffix-count recurrence. The dictionary and NFA record arrays remain retained premises; this is not an independent certificate validator.

Use data from an appropriate trusted, pinned source. The returned provenance makes those omissions explicit. A label passed as `source_id` is not a cryptographic or repository identity check.

### Example: use the saved family without recompiling

```js
const {
  openRetainedFiniteFactorIndex
} = require("./finite_factor_index.cjs");

const saved = require("./gusev_pribavkina_s6_factor_index.json");

const index = openRetainedFiniteFactorIndex({
  source_id: "the pinned Commons S_6 dataset supplied by the caller",
  snapshot: saved.index
});

const summary = index.describe();          // length 91; count "128"
const middle = index.selectShortest("64"); // word and full state path
const page = index.pageShortest({start_rank: "96", limit: 32});
```

In a connected V8 context, a previously retrieved source string can be loaded without Node dependencies:

```js
const moduleObject = {exports: {}};
new Function("module", "exports", retrievedModuleText)(
  moduleObject, moduleObject.exports
);
const index = moduleObject.exports.openRetainedFiniteFactorIndex({
  source_id: "the retained dataset identity",
  snapshot: retrievedDataset.index
});
```

Content retrieval and source pinning happen outside the module. The module performs no network, filesystem, process, or provider operations.

## 6. Bounds and partial results

| Resource | Hard maximum |
|---|---:|
| Alphabet symbols | 8 |
| Raw dictionary entries | 1,024 |
| Symbols in one dictionary word | 128 |
| Total raw dictionary symbols | 32,768 |
| Trie nodes | 512 |
| Discovered subsets | 16,384 |
| Computed subset transitions | 131,072 |
| NFA membership visits across transitions | 8,388,608 |
| Search distance | 1,024 |
| Words in one page | 128 |

The optional `budget` can reduce the subset, transition, NFA-membership, or depth limits; it cannot increase them. Dictionary/trie limits are input refusals. Search limits return `RESOURCE_LIMIT` with the partial snapshot and next source state/symbol. If a subset limit is reached after calculating a previously unseen destination, that unrecorded mask is retained in the stop record.

Mask unions use BigInt. Trie indices, counters, lengths, and bounded loop products remain safe integer Numbers. The empty subset has hexadecimal mask `"0"`. A `null` transition entry means an unprocessed row entry; it does not mean the empty subset. The corresponding processed transition uses the empty subset's numeric state ID.

These bounds make runtime and output finite; they do not change the mathematical problem or promise that every admissible dictionary will finish. No partial result is promoted to factor universality.

## 7. Actual $S_6$ consumer

The source definition yields 30 words of length 5 and 62 words of length 6, for 92 distinct entries and 522 input symbols. Exactly 96 binary candidates were generated to instantiate the dictionary, with its four specified exclusions. Search did not enumerate the binary words of lengths through 91.

| Quantity | Retained value |
|---|---:|
| Prefix-trie states | 125 |
| Discovered subset states | 1,383 |
| Fully processed transition rows | 1,354 |
| Recorded binary transitions | 2,708 |
| Unexpanded distance-91 frontier states | 29 |
| Shortest missing length | 91 |
| Shortest missing word count | 128 |
| Nonzero-count states in the shortest-word DAG | 117 |
| Edges in that shortest-word DAG | 123 |
| NFA membership visits | 13,738 |
| New-subset mask bit probes | 172,750 |
| Suffix-count additions | 1,568 |

The complete predecessor layers establish that every word of length at most 90 is a factor. The search does not claim to have expanded the entire reachable DFA: the distance-91 frontier is intentionally retained without outgoing rows.

One compiler call produced the index. In a fresh connected V8 invocation, the retained loader opened it and one page exported all 128 words and their 92-state paths. No search or count recurrence was repeated. The compilation took 19 ms in that observation; this is not a statistical benchmark.

The actual consumer exercised compilation, structural loading, selection, and complete paging. The rank method and the universal/resource-limit endpoints were not exercised by a separate synthetic suite.

### Exact finite form of all 128 words

The complete exported family has variable positions

$$
6,\ 18,\ 32,\ 45,\ 58,\ 72,\ 84
$$

in zero-based indexing; the other 84 positions are fixed. Every possible binary assignment to those seven positions occurs exactly once. The dataset retains all 128 projected assignments, so the finite family is completely explicit.

Equivalently, put $u=ba^5$, $v=b^5a$, and $r=b^5a^5$. All shortest words in this particular dictionary are

$$
u\,c_0\,
(r\,a\,c_1\,b^3\,r\,c_2)\,
(r\,a^2\,c_3\,b^2\,r\,c_4)\,
(r\,a^3\,c_5\,b\,r\,c_6)\,v,
\qquad c_0,\ldots,c_6\in\{a,b\}.
$$

This is the $k=6$ specialization of the witness shape already given in Gusev–Pribavkina's Theorem 1. Here the complete finite index establishes that its 128 assignments exhaust the shortest-word family for $S_6$. It does not assert such an exhaustiveness classification for every $k$.

The finite exhaustion follows directly from the retained output: all words agree on fixed positions; their variable-position projections are distinct; and there are $128=2^7$ possible assignments and 128 records. This additional output analysis uses the exported words, not a second automaton or word search.

## 8. Retained data layout

The dataset includes the exact source family and references, complete input dictionary, trie nodes and folded transition masks, all subset masks and first parents, every processed transition, BFS distances, suffix counts, complete layer sizes, all 128 ranked shortest words with paths, the seven-position family description and every projected assignment, runtime accounting, loader provenance, and the finite scope boundary.

The shortest-word data remain directly usable through the public retained-index loader. The source identifiers document provenance rather than certify it, and the complete repository version binds the module and dataset together. Original authorship and submission ownership are preserved.
