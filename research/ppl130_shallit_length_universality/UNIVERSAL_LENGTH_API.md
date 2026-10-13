# Exact universal-length index for a finite NFA

This module compiles a supplied epsilon-free finite nondeterministic automaton into a bounded, complete index of the lengths at which **every word** is accepted. A successfully closed finite index describes an infinite ultimately periodic set exactly. If a resource cap prevents closure, the compiler returns an explicit incomplete prefix.

The retained consumer is the published prime-cycle DFA with cycle lengths 2, 3, 5 and 7. Its known least universal length is 210. The new artifact retains all family layers, subset transitions and predecessor choices, then uses those records for large-length count/rank/select and a rejected-word witness. No prior accepted Commons automaton computation was rerun.

## Source and classification

Gawrychowski, Lange, Rampersad, Shallit and Szykuła, [*Existential Length Universality*, STACS 2020, LIPIcs 154, 16:1–16:14](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.STACS.2020.16), prove that existence of an integer $\ell\ge0$ with $\Sigma^\ell\subseteq L(M)$ is NEXPTIME-complete for NFAs and NP-complete for DFAs. Supplying the length in binary gives a different NFA decision problem, which is PSPACE-complete. The old board's open classification must be read in light of this published result. These statements neither prove a strict separation of the named complexity classes nor classify the rank/select operations below.

The paper's [full author version](https://arxiv.org/pdf/1702.03961) supplies the prime-cycle construction used here: a rejecting initial state enters cycle $p_i$ on letter $a_i$; all subsequent letters advance, and only position $p_i-1$ accepts. Its minimum/product property is prior work. The actual runtime input is a DFA subclass of the public NFA interface. No new complexity result, minimum, general bound or external frontier is claimed.

## Input and representation conventions

The input has this shape:

```javascript
{
  source_id: "nonempty provenance label",
  automaton: {
    state_count: 18,
    alphabet: ["a1", "a2", "a3", "a4"],
    initial_states: [0],
    final_states: [2, 5, 10, 17],
    transitions: /* transitions[state][symbolIndex] is an array of destination IDs */
  }
}
```

State IDs are the integers from zero through `state_count - 1`. Initial and final state lists and each destination list denote sets. The compiler sorts and deduplicates them; duplicates do not create additional runs. Empty initial, final or destination lists are permitted. Every raw state list must have at most `state_count` entries, even before deduplication.

The alphabet is a nonempty ordered list of distinct nonempty strings. Strings label single symbols: `"a1"` is one symbol, regardless of its two code units. Returned words are arrays of symbols and also arrays of their alphabet indices. No implicit character splitting or Unicode normalization occurs.

The transition matrix has exactly one row per state and one destination list per alphabet symbol. Epsilon transitions are unsupported. An `epsilon_transitions` field is rejected rather than ignored; callers must eliminate such transitions before using the interface. An empty alphabet is also rejected, so vacuous universality at positive lengths is outside this contract.

Length zero is included. Its only word is the empty word, accepted precisely when the initial state set meets the final state set. Multiple initial states have their ordinary existential-run semantics.

## Why the full family is necessary

Let $I\subseteq Q$ be the initial set and $F\subseteq Q$ the final set. For a subset $S\subseteq Q$ and symbol $a$, write

$$
\delta(S,a)=\bigcup_{s\in S}\delta(s,a).
$$

For each length, define the **family of subsets**

$$
\mathcal R_0=\{I\},\qquad
\mathcal R_{\ell+1}
=\{\delta(S,a):S\in\mathcal R_\ell,\ a\in\Sigma\}.
$$

Induction on $\ell$ shows that $\mathcal R_\ell$ is exactly the set of subsets $\delta^*(I,w)$ obtained from the different words $w\in\Sigma^\ell$. Therefore

$$
\Sigma^\ell\subseteq L(M)
\quad\Longleftrightarrow\quad
\forall S\in\mathcal R_\ell,\quad S\cap F\ne\varnothing.
$$

The existential choice of an accepting NFA run occurs **inside** the universal choice of a word. Replacing the family by the union of its members would discard that distinction. An accepting state reachable on one word does not repair rejection of another word.

The empty reachable subset is retained as an ordinary family member. It records words with no run and is rejecting. Because the alphabet is nonempty, each family has at least one member, even if that member is the empty subset. The code never silently drops it.

State subsets are interned once by exact decimal BigInt masks. Each family is a sorted list of those immutable subset IDs. The family signature is the complete comma-separated ID list; no probabilistic hash or universal/non-universal flag substitutes for the family.

## Exact eventual periodicity

The update $\mathcal R\mapsto\{\delta(S,a):S\in\mathcal R,a\in\Sigma\}$ is a deterministic function on a finite collection of families. In an unrestricted mathematical execution, some complete family must repeat. The number of possible families is at most $2^{2^{|Q|}}$; this fact is not a promise that the executable limits will reach closure.

Suppose the first repeated family is

$$
\mathcal R_\nu=\mathcal R_\mu,\qquad 0\le\mu<\nu,
$$

and put $\lambda=\nu-\mu$. Determinism gives $\mathcal R_{\mu+t}=\mathcal R_{\nu+t}$ for every $t\ge0$. The compiler retains distinct layers $0,\ldots,\nu-1$ and the closing edge from $\nu-1$ to $\mu$. For any requested length,

$$
\operatorname{layer}(\ell)=
\begin{cases}
\ell,&\ell<\mu,\\
\mu+((\ell-\mu)\bmod\lambda),&\ell\ge\mu.
\end{cases}
$$

The universal flag of that layer answers the query exactly. This is a period of the complete family sequence. The API does not separately minimize the period of the Boolean acceptance flags, which may be shorter for other inputs.

Every complete snapshot contains:

- the canonical automaton, its initial subset ID, every interned subset mask, and every subset/symbol transition;
- all distinct family lists, each universal flag and one rejecting subset ID when applicable;
- each next-layer ID, including the closing edge;
- a complete, sorted predecessor list for every outgoing layer edge;
- $\mu,\lambda$, all universal prefix lengths and all universal offsets in the cycle.

A complete snapshot has no omitted family, subset transition or predecessor target within its retained period.

## Count, rank and selection

Let $P$ be the sorted universal lengths below $\mu$, and let $C$ be the sorted offsets $c\in[0,\lambda-1]$ for which layer $\mu+c$ is universal. The exact set of universal lengths is

$$
U=P\ \cup\ \{\mu+c+j\lambda:c\in C,\ j\ge0\}.
$$

The two parts are disjoint. If $C$ is empty, $U$ is finite, possibly empty. If $C$ is nonempty, $U$ is infinite.

For a nonnegative inclusive endpoint $L<\mu$, the count is the number of entries of $P$ at most $L$. For $L\ge\mu$, write $L-\mu=h\lambda+r$, with $0\le r<\lambda$. Then

$$
|U\cap[0,L]|=|P|+h|C|+|\{c\in C:c\le r\}|.
$$

Rank is zero-based in ordinary increasing numerical order. For a universal length $L$, its rank is the inclusive count through $L$ minus one. A non-universal length has no rank.

For selection, ranks below $|P|$ select directly from $P$. Otherwise, when $C$ is nonempty, write the residual rank as $h|C|+j$, with $0\le j<|C|$; the selected length is

$$
\mu+h\lambda+C_j.
$$

These formulas use BigInt for unbounded-by-period query values. They do not expand the automaton at each intervening length. A rank beyond a finite set returns `RANK_OUT_OF_RANGE`. Pagination over a finite exhausted set returns an empty page with `has_more: false`.

## Rejected-word witnesses and the closing edge

When a subset $T$ first appears in a successor family, the compiler records one pair $(S,a)$ with $\delta(S,a)=T$, where $S$ lies in the previous family. Choices are deterministic: increasing subset ID, then input alphabet order. They are not claimed to give a lexicographically least word.

To obtain a rejected word of length $\ell$, choose the retained rejecting subset in $\mathcal R_\ell$ and follow predecessor choices backwards for exactly $\ell$ steps. At step $j$, use the **outgoing predecessor map of layer $\operatorname{layer}(j-1)$**. This is essential at a cycle entry: using only an incoming map attached to the canonical target layer could confuse its first prefix occurrence with a later occurrence reached by the closing edge.

Each selected arc is a subset transition. The reversed path starts at $I$ and ends at a subset disjoint from $F$, so its reversed symbol list is a rejected word. At length zero this produces the empty word when it is rejected. The retained consumer at length 211 crosses the closing edge and contains the whole word and its 212 subset IDs.

Materializing a word is separately capped at 4,096 symbols. A larger rejected length returns `WORD_LENGTH_CAP` together with its exact non-universal lookup, without pretending that a partial word is a witness. A universal length returns `UNIVERSAL` and no rejected word, irrespective of its size.

## Public API

The CommonJS exports are `compileUniversalLengthIndex`, `openRetainedUniversalLengthIndex` and `UNIVERSAL_LENGTH_LIMITS`. The module uses only standard JavaScript and BigInt, with no packages, native process or browser dependency.

### Compiler

`compileUniversalLengthIndex({source_id, automaton})` returns one of:

| Status | Meaning | Retained result |
|---|---|---|
| `COMPLETE` | A full family repeated within all hard limits | `snapshot` plus exact work counters |
| `INCOMPLETE` | A named resource cap stopped expansion | Exact observed length range and flags, complete observed families, partial interned work, and the unfinished layer |

Invalid input throws a type or range error. A resource-limited prefix is not accepted by the loader. If that prefix already contains a universal layer, `existence_status` is `WITNESS_FOUND` and its first such length is retained. If it does not, the status is `UNRESOLVED`, not a negative answer.

On an incomplete return, the final observed layer has no completed outgoing map. Some additional subsets or memoized transitions may have been discovered during its interrupted expansion. They do not create a claimed next family, period or negative decision. Work counters distinguish completed family steps from attempted transition work.

### Retained index

`openRetainedUniversalLengthIndex({source_id, snapshot})` returns an object with these methods:

| Method | Result |
|---|---|
| `summary()` | Source labels, counts, preperiod/period, all universal prefix/cycle positions, first universal length and finite/infinite status |
| `lookupLength(length)` | Exact universal flag, canonical layer, family size and a rejecting subset ID when applicable |
| `countUniversalThrough(length)` | Inclusive count in $[0,\ell]$, as a decimal string |
| `selectUniversal(rank)` | Universal length at the zero-based rank, or finite out-of-range status |
| `rankUniversal(length)` | Rank of a universal length, otherwise `null` |
| `pageUniversal({start_rank, limit})` | Increasing length/rank pairs and the next rank |
| `rejectedWord({length})` | Complete bounded rejection witness, universal status, or explicit word-length cap |
| `snapshot()` | A copied complete record, with no recompilation |
| `work()` | Restoration/query accounting and zero transition-recomputation counters |

Lengths and ranks accept a nonnegative safe Number, nonnegative BigInt or canonical unsigned decimal string. Leading zeroes other than the single string `"0"`, signs, fractions and exponential string notation are rejected. Large values should use strings or BigInt. Returned arbitrary-size integers are decimal strings so the full records are JSON-compatible.

The input cap is 1,024 decimal digits. Selection can return up to 1,028 digits because the selected rank may be multiplied by a period at most 4,096; such an output is exact but may exceed the input cap for a later query. Local counts and IDs remain safe Numbers. A page has at most 128 entries; its default limit is 32, and a zero limit is allowed.

### Structural loading is not certification

The loader checks bounded canonical shapes, unique subset masks and family lists, complete transition-table dimensions, period/next-layer layout, sorted complete predecessor targets and consistency of those arcs with the retained transition table. It also checks that the prefix/cycle index lists agree with the retained flags.

It does **not** recompute NFA subset transitions, derive the families, re-evaluate acceptance against final masks, establish mathematical period closure, or authenticate a source label. Those mathematical claims are premises supplied by the identified compiler output. Both the original source label and the caller's retained-source label are returned, without implying a signature or a verified Git identity.

Use a complete artifact from a trusted identified source. Structural acceptance of modified data does not independently prove that the modified data represents the automaton. No verification-only replay is performed by the saved-data consumer.

### Connected V8 usage

After obtaining the complete source and JSON texts through a connected repository read:

```javascript
const cjs = { exports: {} };
new Function("module", "exports", sourceText)(cjs, cjs.exports);

const data = JSON.parse(dataText);
const index = cjs.exports.openRetainedUniversalLengthIndex({
  source_id: "identified prime_cycles_2_3_5_7.json#/compile/snapshot",
  snapshot: data.compile.snapshot
});

const count = index.countUniversalThrough("1" + "0".repeat(100));
const selected = index.selectUniversal("1" + "0".repeat(90));
const rank = index.rankUniversal(selected.length);
const word = index.rejectedWord({ length: "211" });
```

A CommonJS host may instead import the module normally. Neither usage needs to rerun the compiler to consume the committed index.

## Hard limits and cost

| Resource | Hard cap |
|---|---:|
| States | 64 |
| Alphabet symbols | 8 |
| Code units per symbol | 32 |
| Code units per source label | 512 |
| Interned state subsets | 4,096 |
| Members in one family | 4,096 |
| Distinct retained families | 4,096 |
| Total retained family-member rows | 262,144 |
| Total retained predecessor rows | 262,144 |
| Family subset/symbol transition visits | 1,048,576 |
| Decimal digits in a query length/rank | 1,024 |
| Materialized rejected-word symbols | 4,096 |
| Entries in one output page | 128 |

The compiler builds a subset/symbol transition at most once, then reuses it across family layers. Each new subset transition takes at most one masked union per NFA state. It performs no preallocation of all $2^{|Q|}$ subsets or $2^{2^{|Q|}}$ families. Families are sorted after construction and indexed by their complete ID list.

Membership uses one period reduction and a direct flag lookup. Count uses period arithmetic and a binary search in a finite sorted list. Selection uses arithmetic and a direct indexed offset. Rank combines membership and count. A materialized word uses one binary search in a predecessor list per symbol. These operational descriptions do not replace the cited worst-case decision classifications.

## Complete actual consumer

The source input has a rejecting start state 0. The four cycles are:

| Prime | Entry symbol | Cycle state IDs in order | Final state |
|---:|---|---|---:|
| 2 | `a1` | 1, 2 | 2 |
| 3 | `a2` | 3, 4, 5 | 5 |
| 5 | `a3` | 6, 7, 8, 9, 10 | 10 |
| 7 | `a4` | 11, 12, 13, 14, 15, 16, 17 | 17 |

For positive length $\ell$, a word starting with $a_i$ reaches position $(\ell-1)\bmod p_i$. Its acceptance condition is therefore $p_i\mid\ell$. This gives the source family's known universal-length set $\{210,420,630,\ldots\}$; zero remains rejected.

One compile returned:

| Quantity | Retained value |
|---|---:|
| Distinct state subsets | 18 |
| Distinct family layers | 211 |
| Preperiod $\mu$ | 1 |
| Period $\lambda$ | 210 |
| Universal prefix lengths | none |
| Universal cycle offsets | 209 |
| Family-member rows | 841 |
| Predecessor rows | 844 |
| Completed family steps | 211 |
| Family subset/symbol transition visits | 3,364 |
| New subset/symbol transitions | 72 |
| Memoized transition hits | 3,292 |
| NFA state-transition unions | 72 |
| Acceptance-mask checks | 841 |

The cycle offset 209 is relative to $\mu=1$, so it represents first length 210. The retained closing edge is layer 210 to layer 1.

A fresh connected V8 invocation opened the saved record and performed one membership query, one inclusive count, one selection, one rank, one twelve-row page and one rejected-word query. It reports zero subset-transition unions and zero family transitions recomputed.

The endpoint $10^{100}$ is non-universal and maps to layer 130. Its inclusive universal count is

```text
47619047619047619047619047619047619047619047619047619047619047619047619047619047619047619047619047
```

Zero-based rank $10^{90}$ selects $210(10^{90}+1)$, whose complete decimal representation and recovered rank are in the JSON. The first page contains the twelve lengths 210 through 2,520 in steps of 210. The length-211 query returns the word consisting of 211 copies of symbol `a1`; its final subset mask is 2, representing the non-final cycle entry state 1. All 211 symbols and 212 subset IDs are retained.

The single observed compile took 3 ms and the retained consumer took 4 ms in their connected V8 invocations. These are individual timing observations, not statistical benchmarks or general performance claims.

## Retained artifact and scope

`prime_cycles_2_3_5_7.json` contains the complete source parameters and automaton, all cycle layouts, the complete compiler snapshot and work counters, execution observations, every query request/result, the full twelve-row page and the complete rejected word/path. No output is replaced by a hash, sample or truncated transcript.

The artifact establishes an exact infinite periodic answer for this fixed finite automaton because a complete family cycle was reached. The general API only returns such an answer when its supplied input closes within the stated bounds. Other inputs may be incomplete, and the observed DFA run does not exercise every nondeterministic branch or establish a new complexity theorem. Original construction authorship and submission ownership remain unchanged.
