# Bounded-quotient automata and saved pair navigation

This package intersects a supplied paired-digit DFA with the relations y=q*x for a finite list of positive integer quotients. It retains complete product graphs, all-length reachability certificates and exact suffix-count tables. A separate reader answers fixed-length count, prefix, rank, select, page and membership queries without reconstructing the graphs, repeating breadth-first search or rebuilding the coefficient recurrence.

The distinction between length and quotient bounds is essential. Reachability decides existence over **all word lengths for the compiled quotients**. Saved counting and ranking cover the stated finite range of lengths. Neither operation decides existence when the quotient is unrestricted.

## Sources and scope

[Jeffrey Shallit's April 22, 2013 Fields presentation, *Open Problem: Decidability of Divisibility in Automata*](https://cs.uwaterloo.ca/~shallit/Fields/shallit.pdf), slides 2–4, uses paired base-k digits read most significant first. The shorter coordinate is left-zero-padded, and a canonical pair has no leading (0,0). Slide 4 asks existential divisibility in the accepted set; slide 5 distinguishes a decidable universal condition. Its open-status statement is dated to that presentation. The bounded source check did not establish a later resolution or certify an exhaustive current frontier.

The same existential question appears as Problem 14 on printed slide 40 of [Shallit's 2014 BCTCS slides](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf). The current author talks page lists updates to several problems, but its solved Problem 14 in the separate 2010 talk concerns star-complement-star and must not be transferred to this question.

[Hamoon Mousavi, *Automatic Theorem Proving in Walnut*, February 29, 2016](https://cs.uwaterloo.ca/~shallit/Papers/aut3.pdf), Definitions 1–2 and Sections 2.4, 3.4 and 4.4, describes padded numeral tracks and automatic arithmetic, including multiplication by a fixed positive constant. This package uses that established fixed-multiplier setting. Its explicit residual recurrence below is derived here for the interface; no priority is claimed for constant-multiplication automata or product constructions.

The source slides do not settle every zero/division convention. This API explicitly requires x>0 and q>=1, hence y>0. It excludes the zero pair, negative integers and quotient zero. These are declared restrictions.

## One actual source-derived consumer

The classical Thue–Morse sequence records the parity of the binary digit sum; Shallit's printed slide 30 gives its recurrence and two-state digit automaton. This consumer forms the declared product of two such parity recognizers. It accepts when both x and y have odd binary digit sums.

State s=2*p_x+p_y records the two prefix parities. A digit pair (a,b) has symbol code 2*a+b, and the next state is s XOR symbol. This is a direct finite product of the classical recognizers, not a recomputation of the earlier two-state-transducer atlas, stream kernel or minimization.

~~~json
{
  "base": 2,
  "transition": [
    [0,1,2,3],
    [1,0,3,2],
    [2,3,0,1],
    [3,2,1,0]
  ],
  "start": 0,
  "accept": [3],
  "quotients": [2,3,4,5,6,7,8,9,10,11,12,13],
  "max_length": 70
}
~~~

Length means the common padded track length. With the canonical convention it equals the longer integer's numeral length. A number may have leading zeroes in its own shorter track; the pair as a whole cannot.

The actual graph has **372 states**, **344 reachable states** and **732 valid labelled arcs** across twelve separate quotient families. Its **26,412 coefficient cells** cover remaining lengths 0 through 70 at every state.

## Residual-state construction

Fix a quotient q and a base k. For the prefixes read so far let

~~~text
r = y_prefix - q*x_prefix.
~~~

Reading the next digit pair (a,b) updates this exactly by

~~~text
r_next = k*r + b - q*a.
~~~

Every valid complete multiplication y=q*x remains in the finite range 0<=r<q at each prefix. To prove necessity, suppose t digits remain, and write the remaining suffix values as u and v. The final equality gives

~~~text
r*k^t = q*u - v,
0 <= u,v <= k^t-1.
~~~

The right side lies strictly above -k^t and strictly below q*k^t. Since r is an integer, 0<=r<=q-1. This also handles t=0, when r=0.

Conversely, begin with residual zero, update by the displayed identity, and end with residual zero. Then the whole represented pair satisfies y-q*x=0. Rejecting a leading zero pair makes the complete pair nonzero. With q>=1 this equality forces x and y both positive. Thus the finite residual restriction loses no valid canonical positive pair for the fixed q.

For each input DFA state p and residual r, make a product state (p,r). Number it p*q+r. A valid symbol transition updates both components; a residual outside the allowed interval is rejected. Add one separate canonical-start state numbered m*q, where m is the input state's count. Its transitions use the original DFA start and residual zero, but omit symbol zero. It is not final and has no incoming edges. All ordinary product states permit zero pairs as internal digits.

Accept precisely ordinary states with residual zero and a final input DFA state. The result has m*q+1 states. Its accepted words are exactly the canonical positive pairs accepted by the input DFA with y=q*x.

## All-length existence and shortest witnesses

The constructor performs complete breadth-first search from each canonical start, retaining every reached state, its exact distance, one parent edge, and queue order. Symbols are considered in increasing code order. A first visit therefore gives a shortest, lexicographically first word for that state. The first reached final state gives a shortest accepted pair, breaking shortest-length ties lexicographically.

If no reached state is final, the complete reachable set is an exclusion certificate for that quotient at every length. This remains an ordinary finite-graph argument; it does not require a bound on the integers.

All twelve actual quotient families are nonempty. Their least witness pairs are:

| Quotient | x | y | Canonical length |
| --- | ---: | ---: | ---: |
| 2 | 1 | 2 | 2 |
| 3 | 7 | 21 | 5 |
| 4 | 1 | 4 | 3 |
| 5 | 7 | 35 | 6 |
| 6 | 7 | 42 | 6 |
| 7 | 1 | 7 | 3 |
| 8 | 1 | 8 | 4 |
| 9 | 13 | 117 | 7 |
| 10 | 7 | 70 | 7 |
| 11 | 1 | 11 | 4 |
| 12 | 7 | 84 | 7 |
| 13 | 1 | 13 | 4 |

The complete graph and reachability certificate are saved even when a witness is found early. A generic empty-family case is supported by the same construction; no separate synthetic empty-language consumer was run.

The reader checks saved parent edges and distances, plus closure and distance inequalities along saved reachable edges. Parent chains show each reached state has a path of the stated length. The inequalities d(v)<=d(u)+1 show no shorter path exists, and closure excludes paths to a marked-unreachable state. These checks operate on the saved graph and do not reconstruct its multiplication transitions or rerun BFS. They do not independently authenticate an arbitrarily edited graph against the original DFA.

## Exact fixed-length counting

Let C_l(v) count accepted suffixes of exactly l digits from a product node v:

~~~text
C_0(v) = 1 if v is final, otherwise 0.
C_l(v) = sum over valid labelled transitions v --symbol--> w of C_(l-1)(w).
~~~

Distinct labels are counted separately even when they have the same target. The induction partitions words by their first symbol, so this counts words, not paths with accidental multiplicity. The product is deterministic for each symbol.

The count for complete canonical length l is C_l(start). The separate start handles the leading-pair restriction exactly once. At l=0 its count is zero under the positive-pair convention.

For x>0 the quotient y/x is unique. Therefore the accepted positive-pair families for distinct q are disjoint, and their counts may be summed without duplication. Aggregate navigation orders quotients increasingly, then words by digit-pair lexicographic order within a quotient. It does not claim global numeric x order across quotients.

### Complete length-70 counts

| Quotient | Count |
| --- | ---: |
| 2 | 147573952589676412928 |
| 3 | 49187148229965787409 |
| 4 | 73786976294838206464 |
| 5 | 29514790675795378082 |
| 6 | 24594268998080446977 |
| 7 | 21081993226678848736 |
| 8 | 36893488147419103232 |
| 9 | 16395716078149051793 |
| 10 | 14757395117059525144 |
| 11 | 13415814751206812050 |
| 12 | 12296439618720120844 |
| 13 | 11352199661713395004 |
| **Total** | **450850183389303088663** |

The aggregate length-35 count is 13,095,541,756. All intermediate length totals and all underlying coefficient cells are retained, not just these two lengths.

## Saved navigation

Prefix counting follows saved transitions and reads the completion count at the ending state. It also sums the completion blocks for smaller possible symbols to obtain the first rank of the prefix family. A structurally impossible prefix returns zero with its rejection position. A valid prefix with no accepted completion has count zero and no first rank.

Selection subtracts saved branch counts in symbol order until it finds the branch containing the requested rank. Ranking adds the blocks preceding the actual symbols. Full traces retain nodes, symbols, skipped counts and residual ranks. Only the chosen output word is decoded into its two BigInt values.

Three actual aggregate length-70 selections are:

| Aggregate rank | Quotient | x | y |
| --- | ---: | ---: | ---: |
| 0 | 2 | 295147905179352825856 | 590295810358705651712 |
| 225425091694651544331 | 4 | 204901934339695100916 | 819607737358780403664 |
| 450850183389303088662 | 13 | 90814740055185484876 | 1180591620717411303388 |

The middle selection has within-quotient rank 28663990875009343994. Its first ten symbols [1,0,3,1,2,2,0,1,1,2] define 144115188075855872 completions beginning at within-quotient rank 28534807239019462656. A separate membership query decodes the selected integers and follows the saved graph; it does not regenerate the fixed-length table.

The twenty retained reader queries include aggregate and per-quotient counts, complete reachability records for q=3 and q=9, state and coefficient pages, first/middle/last selections, a rank and prefix, membership of two selected large pairs, a page crossing the q=2/q=3 boundary, the final page, and the unique shortest q=9 word.

The reader opened 372 nodes and 26,412 coefficients. It checked 332 parent records and 676 reachable-edge closure/distance facts, then used 1,132 saved count lookups, 1,097 query transition visits and 567 selected symbols. It performed zero product-transition rebuilds, BFS replays, coefficient recurrences or old transducer/kernel evaluations. These are zero recomputation counters, not a claim of no query arithmetic.

## Interface and bounds

The dependency-free CommonJS module exports `VERSION`, `compileQuotientIndex` and `openQuotientIndex`.

~~~js
const {openQuotientIndex} = require("./quotient_automata.cjs");
const saved = require("./thue_morse_quotients_2_13.json");
const index = openQuotientIndex(saved.snapshot);

index.count(70);
index.selectAll(70, "225425091694651544331");
index.prefix(4, 70, [1,0,3,1,2,2,0,1,1,2]);
~~~

These are examples of navigation through the existing record; a compiler rerun is unnecessary.

Constructor input requires base 2–10, 1–32 labelled DFA states, a complete transition row for every state and every paired symbol, one start state, sorted distinct accepting states, and a sorted nonempty list of distinct quotients in 1–64. The acceptance list may be empty. The maximum saved length is 1–256. Accepting states and quotient arrays are validated rather than silently deduplicated.

The default coefficient budget is 2,000,000 cells, with an accepted maximum setting of 4,000,000. Before construction it also checks at most 1,000,000 product transition entries and a conservative decimal-storage allowance of 16,000,000 units, using cells*(2*max_length+4). These are public resource caps, not mathematical cutoffs for divisibility.

All counts use BigInt internally and canonical decimal strings in JSON. Ordinal ranks accept decimal strings, BigInts, or safe nonnegative Number integers. Unsafe Numbers are rejected. The reader's JSON cap is 24,000,000 characters. Numeric decimal inputs have a 1,024-digit cap; membership additionally allows at most 4,096 paired numeral digits. It can follow longer words than the saved counting horizon because membership uses the finite saved graph, whereas count/rank/select require a length in the saved range.

| Method | Contract |
| --- | --- |
| `summary()` | Saved quotient summaries and length totals. |
| `quotient(q)` | Saved complete reachability records and all length counts. |
| `count(length,q=null)` | Per-quotient count, or aggregate across the compiled list. |
| `prefix(q,length,symbols)` | Completion count, first within-quotient rank and trace. |
| `select(q,length,rank)` | One word and decoded pair in the fixed quotient family. |
| `rank(q,symbols)` | Acceptance and within-quotient rank of a complete word. |
| `selectAll(length,rank)` | Selection in quotient-then-word order. |
| `pageAll(length,start,limit)` | Up to 32 aggregate selections. |
| `statePage(q,start,limit)` | Up to 64 saved graph/reachability rows. |
| `coefficientPage(q,length,start,limit)` | Up to 64 saved coefficient cells. |
| `membership(x,y)` | Positive integer quotient scope, acceptance and saved transition trace. |
| `statistics()` | Opening, query and zero-recomputation counters. |

A zero or nonintegral quotient, x=0, or a quotient outside the list yields an explicit out-of-scope membership result. It is not an assertion about unrestricted acceptance by the input DFA. Selection outside a family throws; an end page at its total count is valid. Arbitrary selected words and repeated calls do not alter the saved snapshot.

Opening validates graph shape, edge bounds, canonical start, the saved reachability certificate, nonnegative exact coefficient shapes, empty-suffix endpoint counts and binding of each saved length total to its start cell. It does not rebuild arithmetic transitions, recompute the coefficient recurrence, or authenticate arbitrary edited summary/shortest records. The identified source output and derivation supply those claims; structural reopening is not an independent proof of all numerical coefficients.

## Work and durable custody

The constructor considered 1,488 product transition candidates, retained 732 valid arcs, visited 344 BFS nodes and 676 reachable arcs, and made 51,240 coefficient additions. No candidate integer-pair enumeration was used; the twelve shortest decoded witnesses are outputs of graph paths. Its observed 16 ms is a single connected-runtime observation, not a performance comparison or benchmark.

Frozen source was syntax-parsed and inspected before execution. Source and exact input were banked before the one actual calculation. The full initial output was banked immediately, then a fresh reader made the twenty queries. No synthetic suite or accepted earlier computation was rerun.

| Item | Git blob |
| --- | --- |
| Frozen `quotient_automata.cjs` | `89f85109cafd677086a90fd5a2d9b25b2eb205dc` |
| Exact standalone input, 841 bytes | `f70f7c87912827da0396a27dc38c601e0832f4ea` |
| Complete pre-reader output, 354,541 bytes | `ab01fe1f63c7208cdc64e64dc79b7290ac6f1314` |
| Final data including twenty queries, 456,890 bytes | `bdacce050fb19c7b29cc1ffcb14ec1ee87dd5d23` |

The final JSON retains the unchanged input and constructor snapshot, with fresh query outputs appended. The package's source, guide, complete data and README are read back as full files after publication.

This finite quotient union gives an exact useful restriction of the source problem, including all-length existence for the selected quotients. It supplies no general bound on a necessary quotient, no decision procedure for unrestricted existential divisibility, no new automatic-arithmetic theorem, and no sponsor submission or reward claim.
