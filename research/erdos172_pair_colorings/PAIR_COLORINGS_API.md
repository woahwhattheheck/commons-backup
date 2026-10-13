# Finite sums-and-products pair-coloring index

This index represents all labelled binary colorings of the interval [1,22] avoiding every monochromatic set
`{x,y,x+y,xy}`
with 1≤x<y, x+y≤22 and xy≤22. Both variables must share the pattern's color. Equal numerical outputs are one vertex of the pattern.

The complete finite input has **34 distinct patterns and 1,744 avoiding colorings**. A saved residual-clause DAG has **1,002 nodes**, including false and true terminals, and **10,312 nonterminal coefficient cells**. It counts by the number of ones and supports exact conditional counts, lexicographic ranks, selected colorings and explicit rejection witnesses.

This is an interval-restricted pair-pattern classification. It does not establish a threshold, a statement about colorings of all natural numbers, or the existence of arbitrarily large finite sets with all subset sums and products monochromatic.

## Exact problem and source boundaries

The fully read [FormalConjectures Erdős 172 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/172.lean) has decoded-content Git-blob identity `52f5b490089dda2d68504616f8237018b15380a3` (1,303 bytes). It asks whether every finite coloring of the natural numbers admits arbitrarily large finite A for which the sums and products over every nonempty subset of A have one common color. Since A is a set, the selected elements are distinct. Singleton subsets include the elements of A themselves. The local theorem is a placeholder with a research-open annotation; no external proof or independent current-status survey was reviewed.

For a positive pair A={x,y}, the full set of required numerical values is exactly {x,y,x+y,xy}. The current API imposes three additional finite restrictions: positive variables, x<y, and every required value inside [1,N]. It makes no assertion about zero or patterns leaving this interval. For x=1, xy=y; deduplicating that repeated numerical value retains the correct set condition.

Joel Moreira, [Monochromatic sums and products in N](https://annals.math.princeton.edu/wp-content/uploads/annals-v185-n3-p10-p.pdf), Annals of Mathematics 185 (2017), 1069–1090, DOI 10.4007/annals.2017.185.3.10, takes N={1,2,...}. Corollary 1.5 gives infinitely many x,y with **{x,xy,x+y}** monochromatic. It does not require y to have that same color. Question 1.3 distinguishes the full four-value pattern. The 2017 question's status wording is dated source context, not a claim that no later result exists.

Ryan Alweiss, [Monochromatic Sums and Products over Q](https://arxiv.org/abs/2307.08901), explicitly describes the full nonempty-subset sums/products pattern and credits Hindman's conjecture. The inspected abstract's theorem concerns rational numbers. It is not transferred here to the natural-number problem, and its abstract is not used to supply the distinctness convention. That convention comes from the complete formal finite-set statement.

These primary passages establish the scope distinction. The finite counts and implementation here are not attributed to those papers, and no new Ramsey threshold, general theorem, or mathematical priority is claimed.

## Input and pattern completeness

The constructor accepts an integer N from 2 through 24 and generates every positive pair x<y in [1,N]. A pair contributes a pattern exactly when both x+y and xy are at most N. Each pattern is represented by its sorted distinct values and a bit mask whose bit v-1 represents vertex v. Pairs yielding the same set are grouped into the same pattern and retained in its `pairs` list.

For N=22, 231 candidate pairs were considered and 34 satisfy the range conditions. They yield 34 distinct patterns. No pair is omitted by a heuristic. The saved pattern records contain every contributing pair.

A binary coloring avoids one pattern precisely when that pattern contains at least one 0 and at least one 1. Thus every pattern supplies two clauses:
- a positive clause requiring at least one 1;
- a negative clause requiring at least one 0.

Both color labels and all vertex labels remain distinguished. Complementary colorings are two different members of the family. There is no quotient by color swap, arithmetic symmetry, or isomorphism.

## Residual-clause construction

The variable order is vertex 1, then 2, through N. At each stage the residual positive and negative clauses describe exactly the restrictions still unsatisfied by the assigned prefix.

Assigning bit 0 removes that vertex from positive clauses and satisfies every negative clause containing it. Assigning bit 1 does the reverse. An empty residual clause is false. When all N positions have been assigned, empty clause lists are true.

Each clause list is normalized by removing duplicates and clauses containing a smaller clause of the same polarity. The smaller clause implies the larger one, so this subsumption preserves exactly the satisfying colorings. Numeric mask sorting places a proper subset before its superset, since adding a bit increases a nonnegative mask. Positive and negative lists are normalized separately; no cross-polarity implication is assumed.

States with the same level and normalized residual lists share a DAG node. Every nonterminal stores its level, both clause lists and the 0/1 child IDs. A fixed 250,000-state cap throws if exceeded. It does not return a partial accepted family. The actual run used 1,000 nonterminal nodes, well within the cap.

No variable level is skipped, including after all clauses have been satisfied. This makes the weight recurrence direct. If P_v(z) counts valid suffixes by their number of ones at node v, then
`P_v(z)=P_zero(z)+z·P_one(z)`.
The false terminal has polynomial 0; the true terminal has polynomial 1. The saved coefficient arrays include zero coefficients. The complete root polynomial counts the family, and summing its coefficients gives 1,744.

This argument proves coverage of all 2^22 labelled colorings through the symbolic recurrence. The actual constructor does not enumerate the individual 2^22 colorings or the individual 1,744 accepted strings.

## Actual result

| Number of ones | Avoiding colorings |
| ---: | ---: |
| 0–4 | 0 |
| 5 | 3 |
| 6 | 43 |
| 7 | 186 |
| 8 | 328 |
| 9 | 240 |
| 10 | 66 |
| 11 | 12 |
| 12 | 66 |
| 13 | 240 |
| 14 | 328 |
| 15 | 186 |
| 16 | 43 |
| 17 | 3 |
| 18–22 | 0 |

Color complementation preserves all avoidance conditions and exchanges weight k with weight 22-k, explaining the symmetry of this retained table. It does not identify those two colorings as one counted object.

Construction counters:
- 231 candidate-pair visits and 34 in-range pairs;
- 4,001 clause normalizations and 60,377 subset checks;
- 2,001 state calls, including terminal and memoized calls;
- 297 memo hits;
- 10,312 generated coefficient cells.

These are scoped source counters, not a total CPU or arithmetic-operation count.

## Reader ordering and conditional coefficients

A coloring is a length-N string, with its first character assigned to vertex 1. Lexicographic order uses 0 before 1. This reader ordering should not be confused with treating the constructor's vertex mask as a binary integer, where vertex 1 is the low bit.

Select compares the requested rank with the saved 0-child count, then takes the appropriate branch. Rank adds counts of earlier 0 branches when the queried coloring chooses 1. Optional weight restrictions use the corresponding suffix coefficient and subtract one from the remaining weight after a 1 branch. Complete traces retain each decision and count.

A condition is a list of [position,bit] pairs. Duplicate consistent assignments are coalesced; contradictory assignments are rejected. For an unfixed position, the conditional recurrence adds both branches. A fixed 0 keeps only the 0 branch, and a fixed 1 keeps z times the 1 branch. Beyond the last fixed position, the existing base coefficients suffice. The reader memoizes the remaining new conditional rows by DAG node.

Condition IDs are local to the current reader session. `caches` exports all complete conditional rows for inspection and retention; `openIndex` does not import those exported caches into a new session. Reopening only the base snapshot and requesting a condition computes that condition anew. The actual retained session created each condition once and then reused it for its subsequent queries.

## CommonJS API

```javascript
const {openIndex} = require("./pair_colorings.cjs");
const snapshot = require("./interval22_colorings.json");
const index = openIndex(snapshot);
const condition = index.query({
  op:"condition", fixed:[[1,0],[2,1],[22,0]]
});
const count = index.query({op:"count", condition:condition.id});
const first = index.query({op:"select", condition:condition.id, rank:"0"});
const rank = index.query({
  op:"rank", condition:condition.id, coloring:first.coloring
});
console.log(count.count, first.coloring, rank.rank);
```

Exports are `buildIndex(input)` and `openIndex(snapshot)`. Opening performs structural checks and trusts the identified certificate; it is not an independent checker of adversarial node or coefficient data.

Ranks and counts are canonical nonnegative decimal strings. Rank strings are capped at 4,096 characters. Positions are one-based; node IDs, condition IDs and ranks are zero-based. Weight, when supplied, must be an integer from 0 through N. The initial condition ID 0 imposes no fixed bits.

| Query | Result |
| --- | --- |
| `summary` | Complete saved family size and weight histogram |
| `patterns` | Every pattern with mask, values and contributing pairs |
| `node, id` | One saved clause/DAG/coefficient record |
| `condition, fixed` | A normalized condition and its complete newly needed coefficient rows |
| `conditionSummary, condition` | Saved fixed bits, count and weight histogram |
| `count, condition?, weight?` | Exact matching count |
| `select, rank, condition?, weight?` | One matching coloring and decision trace |
| `rank, coloring, condition?, weight?` | Exact rank of a valid matching coloring |
| `page, start, limit, condition?, weight?` | Consecutive selected records, limit 0–1,000 |
| `classify, coloring` | First monochromatic pattern witness, or acceptance and unrestricted rank |
| `caches` | Complete session-local condition records and coefficient rows |

An invalid coloring's `classify` response retains the original arithmetic pair witness and its monochromatic numerical values. A rank query requires membership and the requested weight/fixed bits; it throws otherwise. Empty families are valid count/page results but have no select rank.

## Fresh saved-reader evidence

All **37** responses were banked individually before the next query. The aggregate also retains six exact select/rank comparisons and all five newly compiled conditions.

Selected results:
- Unrestricted rank 0 is `0010101101010101010101`.
- Rank 871 is `0111101010101011101010`.
- Rank 1743 is `1101010010101010101010`.
- Fixing position 1 to 0 leaves **872** colorings.
- Fixing positions 1,2,22 to 0,1,0 leaves **45**.
- The complementary fixed bits 1,0,1 also leave **45**.
- Fixing positions 1,2,3 all to 0 leaves **0**, since the pair (1,2) produces the monochromatic set {1,2,3}.
- Fixing the full first selected coloring leaves exactly **1**.
- The reader returns all three weight-5 colorings and all three weight-17 colorings.
- The all-zero and all-one strings are rejected with {1,2,3}; the alternating string `0101010101010101010101` is rejected with {2,4,6,8}.
- All six selected strings return the exact supplied ranks in their stated unrestricted, fixed-bit or weight family.

Fresh reader work totals **298 conditional nodes and 3,436 conditional coefficient cells**, alongside **587 base-cell reads, 44 conditional-cell reads, 418 traversal steps and 58 pattern scans**. These are explicitly new query computations. The reader did not regenerate arithmetic patterns, rebuild the base DAG, or recompute base coefficients. Scoped counters do not count every BigInt addition, map operation, string operation or copy.

There was no reader failure, missing response or post-run source correction.

## Artifact identity and reproducibility

| Artifact | Git-blob identity | UTF-8 bytes |
| --- | --- | ---: |
| Frozen source | aa50e2c7eb8e035b05da6ced3cd1521622d47a37 | 8,400 |
| Frozen input | 7e72bff22d2f38af19430ea1aa3c8cfba8cf36ee | 388 |
| Complete DAG snapshot | 5d189d9288fded07cfbaac8fc5ea4968b639c321 | 506,588 |
| Complete reader output aggregate | dafaeb40815082aa828c07096f14f9cf23247839 | 258,004 |

`interval22_colorings.json` contains all patterns, every node and coefficient, root ID, input declaration and work counters. `saved_reader_queries.json` contains every query, full response, cumulative counter, condition row and rank comparison. The source was syntax parsed and banked with the input before the single actual construction.

No earlier van der Waerden, Paley, sum-product-cardinality or other accepted coloring calculation was replayed. The result is a complete finite pair-pattern family and its navigation, with the broader source question left separate.
