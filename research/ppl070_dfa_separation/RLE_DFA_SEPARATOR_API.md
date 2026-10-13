# Exact DFA separation catalogues for compressed binary words

This module constructs the complete catalogue of labelled complete binary transition tables with one through four states for a supplied pair of distinct run-length encoded words. It resolves unary transition powers once and retains every terminal-state tuple. The saved catalogue then supports exact counts, rank/select over accepting-state choices, and explicit finite witnesses.

The actual new input is

$$
w=0^{212}1^2,\qquad x=0^21^{212},
$$

together with their reversals. The period value 210 from the accepted Commons #31360 artifact supplies the reproducible exponent difference; its automaton computation is not rerun. This finite catalogue is separate from the original reversal-gap theorem.

## Source and solved-problem boundary

Farzam Ebrahimnejad, [*On the gap between separating words and separating their reversals*, Theoretical Computer Science 711 (2018), 79–91](https://arxiv.org/html/1605.04835v3), DOI [10.1016/j.tcs.2017.11.012](https://doi.org/10.1016/j.tcs.2017.11.012), proves that $|\operatorname{sep}(w,x)-\operatorname{sep}(w^R,x^R)|$ is unbounded even for a binary alphabet. [Shallit's current author page](https://cs.uwaterloo.ca/~shallit/talks.html) records Problem 5 as solved. The earlier board framing must be qualified by that published result.

The source defines separation as accepting the first word and rejecting the second. Its Lemma 3 identifies the role of distinct terminal states: an accepting set containing the first terminal and excluding the second suffices. The complete-DFA conventions and this source attribution are preserved.

Shallit's [2014 slides](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf), slides 16–17, give the earlier unary-tail/cycle and least-common-multiple lower-bound framework. The fixed-input argument below uses that elementary method. This package does not audit or re-establish the published unbounded-gap proof, supply a new separation frontier, or assert a new complexity or minimum-state discovery.

## Word, state and counting conventions

The alphabet is exactly the two symbols 0 and 1. A run is `[symbol, exponent]`; for example, the first actual word is `[[0,"212"],[1,"2"]]`. Runs are read from left to right by ordinary concatenation.

A raw exponent may be a nonnegative safe Number, nonnegative BigInt or canonical unsigned decimal string. Leading zeroes other than `"0"`, signs, fractional values and exponential string notation are rejected. Zero-length runs are removed. Adjacent runs of the same symbol are merged, with the digit cap checked again on the merged exponent. An empty run list represents the empty word. The two normalized words must be distinct.

No repeated block is expanded into individual symbols. Reversal reverses the run order, preserving each symbol and exponent. This operation also handles an empty word. Normalized output exponents and complete word lengths are decimal strings.

At state count $q$, the state set is $\{0,\ldots,q-1\}$ and the initial state is 0. Each symbol has a total transition function on all $q$ states. Unreachable states are permitted. Every accepting-state subset is potentially allowed, subject to the requested acceptance/rejection constraints.

Counts are for **labelled** automata with this fixed initial state. No graph-isomorphism quotient, relabelling factor or language-equivalence quotient is silently applied. A generic level may include automata with dispensable states. If the first separating level is $q$, its qualifying machines have the minimum state count for the supplied acceptance requirements.

### Three acceptance requirements

| Orientation | Words required to be accepted | Words required to be rejected |
|---|---|---|
| `forward` | $w$ | $x$ |
| `reverse` | $w^R$ | $x^R$ |
| `joint` | $w$ and $w^R$ | $x$ and $x^R$ |

A transition table can distinguish both pairs separately while admitting **no single accepting set** that meets the joint requirement. The API records both notions. It never substitutes two independent endpoint inequalities for a common accepting set.

Complementing an accepting set exchanges the two roles in one ordered pair, explaining why the numerical minimum $\operatorname{sep}(w,x)$ is symmetric in $w,x$. The catalogue still counts the declared ordered acceptance choices, not both orientations of acceptance at once.

## Complete transition-table coverage

A unary function $f:\{0,\ldots,q-1\}\to\{0,\ldots,q-1\}$ is encoded by

$$
c(f)=\sum_{s=0}^{q-1} f(s)q^s.
$$

The least significant base-$q$ digit is the target of state 0. The codes $0,\ldots,q^q-1$ enumerate all unary functions exactly once. For $q=1$, the only code and target are zero.

Write $f_0,f_1$ for the transition functions on symbols 0 and 1. Their binary transition-table code is

$$
c=c(f_0)+q^q c(f_1).
$$

Thus the codes $0,\ldots,q^{2q}-1$ cover every labelled complete binary transition table exactly once. Fixing the initial state to zero loses no possible minimum: a DFA with a different designated initial state can be relabelled to put that state at zero.

The complete input envelope of one through four states contains

$$
1^{2}+2^4+3^6+4^8=66\,282
$$

transition tables. The compiler visits all of them for the selected maximum state count, without a reachability or isomorphism filter.

## Resolving long runs by finite unary orbits

For every unary function and every starting state, the compiler follows the orbit until its first repeated state. It retains the distinct path, the preperiod $\mu$ and the period $\lambda$. These satisfy

$$
0\le\mu<\mu+\lambda\le q.
$$

If the path is $v_0,\ldots,v_{\mu+\lambda-1}$, then for every nonnegative exponent $e$,

$$
f^e(s)=
\begin{cases}
v_e,&e<\mu+\lambda,\\
v_{\mu+((e-\mu)\bmod\lambda)},&e\ge\mu+\lambda.
\end{cases}
$$

This follows directly from the repeated orbit state and determinism. The exponent is reduced by exact BigInt arithmetic. Its numerical magnitude does not cause a loop of $e$ iterations.

Each distinct positive exponent occurring in either word is resolved on all unary functions and starting states once. The four words $w,x,w^R,x^R$ use those same cached powers. A word is evaluated by one power-table lookup per run, starting at state 0.

The snapshot retains every unary map, every starting-state orbit and every resolved power target. The independent code descriptions, orbit rows and power rows are preserved as complete data, not replaced by a timing claim.

## Complete endpoint encoding

For each transition code, let

$$
(a,b,c,d)=
\bigl(\delta(0,w),\delta(0,x),\delta(0,w^R),\delta(0,x^R)\bigr).
$$

The retained byte is

$$
a+qb+q^2c+q^3d.
$$

Because $q\le4$, it lies between zero and $q^4-1\le255$. Exactly two lowercase hexadecimal characters encode each byte, including leading zeroes. Byte position $j$ belongs to transition code $j$; there are exactly $q^{2q}$ bytes at level $q$.

This is a complete fixed-width representation of all endpoint rows, not a hash, sample or list of only successful cases. The public loader decodes every row and rejects an encoding with missing bytes, extra bytes, noncanonical hex characters or a value outside its base-$q$ range.

For one word pair, the terminal states must differ. For the joint query, put

$$
P=\{a,c\},\qquad N=\{b,d\}.
$$

There is a suitable common accepting set precisely when $P\cap N=\varnothing$. In that case its count is

$$
2^{q-|P\cup N|}.
$$

Every state in $P$ is forced to accept, every state in $N$ is forced to reject, and each remaining state is free. The same formula applies to a single orientation with singleton $P,N$. At a successful ordinary pair there are $2^{q-2}$ choices. A conflict has zero choices. The compiler uses these counts without enumerating all accepting subsets.

## Rank and selection of full DFAs

A full DFA in one orientation consists of a transition code and an accepting-state mask satisfying that orientation. The order is:

1. increasing transition code;
2. within one code, increasing integer accepting-state mask.

Ranks are zero-based. For each code, the saved endpoints determine the forced accepting mask, forced rejecting mask and the free state bits. Let $c_j$ be the number of valid masks for transition code $j$. The loader builds prefix sums

$$
B_0=0,\qquad B_{j+1}=B_j+c_j.
$$

For a requested rank $r<B_T$, where $T=q^{2q}$, binary search finds the unique code $j$ with $B_j\le r<B_{j+1}$. The residual rank $r-B_j$ selects the free bits in increasing state order. Inserting those bits into the accepting mask produces the required increasing-mask order.

Ranking checks the forced accepting and rejecting bits, extracts the chosen free bits, and adds their compressed integer value to $B_j$. An invalid mask returns `NOT_A_SEPARATOR`. A selection outside the finite total returns `RANK_OUT_OF_RANGE`.

The loader constructs these prefix sums by reading the retained endpoints. It does not rebuild unary orbits, resolve powers again or re-evaluate all transition tables on the words.

## Public API

Exports:

- `compileDfaSeparatorIndex`
- `openRetainedDfaSeparatorIndex`
- `DFA_SEPARATOR_LIMITS`

The module is pure CommonJS-compatible JavaScript using standard arrays, typed arrays and BigInt. It has no package, browser or native-process dependency.

### Compiler contract

```javascript
const result = compileDfaSeparatorIndex({
  source_id: "identified source of the two run-length words",
  word_a_runs: [[0, "212"], [1, "2"]],
  word_b_runs: [[0, "2"], [1, "212"]],
  max_states: 4
});
```

Every valid request completes the finite envelope from one through `max_states` and returns `{status: "COMPLETE", snapshot, work}`. Invalid input or a request above a hard cap throws before it can be treated as a separation result. There is no silent truncation of the state range.

The default maximum is four states. The compiler does not keep increasing that bound until a separator appears. A retained minimum reported as `NOT_FOUND_THROUGH_CAP` means only that no requested separator occurs in the complete searched range. It makes no assertion of impossibility above that range; joint constraints may also be globally contradictory for some word pairs.

### Opening saved data

```javascript
const index = openRetainedDfaSeparatorIndex({
  source_id: "identified period210_separator_catalog.json#/compile/snapshot",
  snapshot: data.compile.snapshot
});
```

| Method | Purpose |
|---|---|
| `summary()` | Full per-level profiles, counting conventions and first successful state counts |
| `countDfas({states, orientation})` | Number of labelled DFAs satisfying one orientation |
| `selectDfa({states, orientation, rank})` | Full transition table and accepting set at the rank |
| `rankDfa({states, orientation, transition_code, final_mask})` | Rank of that DFA, or `NOT_A_SEPARATOR` |
| `pageDfas({states, orientation, start_rank, limit})` | Finite page of full DFAs with completion information |
| `lookupTable({states, transition_code})` | Transition table, all four retained endpoints and final-choice counts |
| `pageConflictTables({states, start_rank, limit})` | All tables distinguishing both pairs separately but lacking a common accepting set, paged by increasing code |
| `traceTable({states, transition_code})` | Four complete run-boundary paths using retained power rows |
| `snapshot()` | Copied complete normalized data, without recompilation |
| `work()` | Index construction and query accounting |

The orientation is `"forward"` by default; its other values are `"reverse"` and `"joint"`. Table-only methods use the given state count/code and do not require an orientation argument.

State counts, transition codes, masks and ranks are safe Numbers. Counts and rank totals in this capped catalogue are far below the safe-integer limit. Large run exponents use decimal strings or BigInt, with decimal strings retained in JSON.

Page limits default to 32 and may range from zero through 128. An exhausted page is empty and has `has_more: false`. A conflict-table page has its own zero-based table rank; that rank is distinct from the full-DFA rank, which includes accepting-mask choices.

### Structural restoration boundary

The loader validates the complete shapes and ranges, binary alphabet/start and endpoint order, run normalization, exponent index, orbit path shapes, power-row dimensions, encoding identifiers and full byte counts. It rebuilds final-choice prefix sums from the endpoints and requires the resulting profiles to agree with the stored profiles.

It does not independently prove that each unary-map row equals its declared code, follow the orbit edges, re-resolve the stored powers, recompute word endpoints or authenticate source identities. Those mathematical relationships are premises of the identified compiler output. Structurally acceptable altered data is not thereby certified as a correct catalogue.

`traceTable` performs only the requested run-boundary navigation on saved power rows. It does not expand any word or recompute those powers. The data retain these selected paths explicitly, separately from the catalogue's original complete endpoint computation.

### Connected V8 example

After retrieving the complete module and JSON texts through the connected repository interface:

```javascript
const cjs = { exports: {} };
new Function("module", "exports", sourceText)(cjs, cjs.exports);
const data = JSON.parse(dataText);
const index = cjs.exports.openRetainedDfaSeparatorIndex({
  source_id: "identified period210_separator_catalog.json#/compile/snapshot",
  snapshot: data.compile.snapshot
});

const joint = index.countDfas({ states: 4, orientation: "joint" });
const selected = index.selectDfa({
  states: 4, orientation: "joint", rank: Math.floor(joint.count / 2)
});
const rank = index.rankDfa({
  states: 4, orientation: "joint",
  transition_code: selected.transition_code,
  final_mask: selected.final_mask
});
const conflicts = index.pageConflictTables({ states: 4, start_rank: 0, limit: 128 });
```

A CommonJS host may import the module normally. Neither route needs to rerun the compiler to use the committed catalogue.

## Hard bounds and work

| Resource | Hard limit |
|---|---:|
| States | 4 |
| Raw runs per word | 32 |
| Decimal digits per raw or merged exponent | 256 |
| Source-label code units | 512 |
| Entries in an output page | 128 |

These bounds imply at most 64 distinct retained exponents, 66,282 transition codes, 288 unary maps and 1,114 starting-state orbits across the maximum state range. Each orbit has at most four distinct states. At most 71,296 power targets are needed for 64 exponents.

There are at most 128 run occurrences across the two normalized words and their reversals, giving at most 8,484,096 run-power lookups over the complete four-state envelope. Exponent reductions use bounded-digit BigInt arithmetic; repeated-letter strings are not materialized. Full word lengths are retained exactly and may exceed the per-run exponent digit count because a word can contain many runs.

The retained consumer indexes every saved endpoint row once. Subsequent count queries use the prefix total; rank uses its code prefix and at most four free bits; selection uses binary search plus mask decoding. This cost description is limited to the stated finite interface, not a new general complexity theorem for separation.

## Why the actual pair needs exactly four states

The input scalar is taken from [Commons #31360](https://github.com/woahwhattheheck/commons/pull/31360), file `research/ppl130_shallit_length_universality/prime_cycles_2_3_5_7.json`, Git blob `8eeffcc2ec4fd3f82e82429d16b278bce23f01bf`, JSON pointer `/retained_consumer/summary/first_universal_length`. Its value is 210.

Only that retained integer is consumed. The choice does not assert a mathematical implication from NFA length universality to DFA separation. With a new tail parameter 2, it gives the exponent pair 212 and 2 and words of length 214.

On a set with at most three states, the orbit of any unary function has entered a cycle after two applications. That cycle has length 1, 2 or 3, all divisors of 210. Consequently

$$
f^{212}=f^2
$$

as functions for every such unary map. Applying the identity independently to the 0-transition and 1-transition functions makes the terminal states of $w$ and $x$ equal. It also makes the terminal states of $w^R$ and $x^R$ equal. No automaton with at most three states separates either pair.

For a four-state upper bound, let the 0-transition increment a cycle modulo four, let the 1-transition fix every state, start at zero, and accept state zero. The two words have respectively 212 and 2 zeroes, so their final states are 0 and 2 modulo four. Reversal preserves those zero counts. The same DFA satisfies the joint requirement.

Thus the minimum is four for each orientation and for the joint requirement. This is a direct instance of the standard finite-function tail/cycle framework, not a new external lower-bound result. Its purpose here is to clarify the meaning of the complete minimal-state catalogue.

## Actual complete catalogue

One actual compile retained these profiles:

| States | Transition tables | Forward distinguishing | Reverse distinguishing | Forward full DFAs | Reverse full DFAs | Joint full DFAs |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 2 | 16 | 0 | 0 | 0 | 0 | 0 |
| 3 | 729 | 0 | 0 | 0 | 0 | 0 |
| 4 | 65,536 | 4,656 | 4,656 | 18,624 | 18,624 | 6,840 |

At four states, the transition-table categories are:

| Category | Tables |
|---|---:|
| Both pairs separately distinguishable | 2,496 |
| Forward pair only | 2,160 |
| Reversed pair only | 2,160 |
| Neither pair | 58,720 |
| One common accepting set exists | 2,448 |
| Both separately distinguishable, but no common set | 48 |

The first four categories partition all 65,536 tables. The last two split the first category. Final-set multiplicity accounts for the difference between 2,448 compatible transition tables and 6,840 joint full DFAs.

The compiler retained 288 unary maps, 1,114 orbit records, 2,228 power targets and all 66,282 endpoint bytes. Its exact work counters are 2,438 unary orbit steps, 1,826 power-period reductions, 265,128 compressed-word evaluations and 530,256 run-power lookups. It expanded zero repeated-word symbols and enumerated zero final subsets.

### An explicit common-set obstruction

The first conflict-table code is 5,874. Its transitions are:

| State | On 0 | On 1 |
|---:|---:|---:|
| 0 | 2 | 2 |
| 1 | 0 | 1 |
| 2 | 3 | 1 |
| 3 | 3 | 0 |

Its retained endpoints are

$$
\delta(w)=2,\quad \delta(x)=1,\quad
\delta(w^R)=3,\quad \delta(x^R)=2.
$$

The forward requirement forces state 2 to accept. The reversed requirement forces that same state to reject. Each orientation separately admits four accepting masks, but no mask serves both. The required accepting mask is 12 and the required rejecting mask is 6; their intersection is the bit for state 2.

The saved-data API exported **all 48** conflict tables in one complete page, including their transitions, endpoints, required masks and conflicting states. It also retained the first case's full run-boundary paths, not just this displayed example.

### Saved-data selection and finite pagination

The fresh retained-data consumer:

- selected forward rank 9,312, obtaining transition code 30,228 and final mask 8, then recovered rank 9,312;
- selected joint rank 3,420, obtaining transition code 30,215 and final mask 13, then recovered rank 3,420;
- exported the last eight reversed-orientation DFAs, ending exactly at rank count 18,624 with `has_more: false`;
- exported all 48 conflict tables;
- retained four-word run-boundary paths for the first conflict table and for the selected joint DFA.

It indexed the 66,282 saved endpoint rows and built twelve final-weight prefix arrays. It performed no second full-catalogue word evaluation. The two explicit trace queries nevertheless traversed all four compressed words for two selected tables, using sixteen saved run-power lookups. They rebuilt no unary orbit, recomputed no power target and expanded no repeated symbols. The zero catalogue-evaluation counter concerns bulk catalogue processing; selected trace work is accounted for separately.

The one compile took 202 ms and the saved-data consumer took 95 ms in their observed connected V8 invocations. These individual measurements are not statistical benchmarks.

## Retention and scope

`period210_separator_catalog.json` contains complete input provenance, both compressed words, every unary map/orbit/power row, every endpoint byte, every level profile, all work observations, every consumer request/result, all 48 conflict tables, both selected full DFAs, the complete final reversed page and both full run-boundary trace groups.

The complete labelled catalogue and its minimum-state conclusions apply to this specific pair. The general API covers only its explicit binary/four-state/compressed-input envelope. The data do not establish a maximum over word pairs, a new unbounded reversal-gap theorem, or an external frontier. Source attribution and original submission ownership are preserved.
