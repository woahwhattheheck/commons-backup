# First-block-bounded grammar and exact word navigation

This package gives an exact finite automaton and an equivalent terminal-first right-linear grammar for a regular restriction of Okhotin's published block-comparison language. Only the first block length is bounded. Later block lengths, the number of blocks and the total word length remain unbounded.

The retained instance has first-block bound B=7. Its 53 reachable states are pairwise inequivalent, with all 1,378 shortest distinguishing-suffix records saved. The grammar contains 150 rules. Saved coefficients count and navigate words through length 128; that coefficient horizon does not truncate the automaton or grammar language.

## Primary source and qualification

Alexander Okhotin, *Describing the syntax of programming languages using conjunctive and Boolean grammars*, arXiv:2012.03538v1, title page dated December 8, 2020, printed page 11, Example 4, supplies the source grammar:

```text
S -> SA & not Cb | A
A -> aA | b
C -> aCa | B
B -> BA | b
```

Its language consists of words

```text
a^n1 b a^n2 b ... a^nk b
```

with one or more blocks, nonnegative block lengths, and n_i different from n_1 for every i>=2. Later block lengths need not differ from one another. A lone block is allowed, and an a-run may be empty. The literal alternative S->A and A->b support these boundary conventions. The empty word itself is excluded. In the retrieved PDF's text extraction some greater-than-or-equal glyphs flatten to strict signs; no claim of visual verification is made. The screenshot response contained a text marker and no actual image payload.

Primary source: https://arxiv.org/pdf/2012.03538

The general PPL105 question asks for an equivalent Greibach normal form for every Boolean grammar. The separate author-slide locator https://www.mathnet.ru/PresentFiles/36541/Okhotin_Slides.pdf supplied only an indexed primary excerpt identifying the terminal-first shape A->a alpha; its direct fetch timed out and remains held. This guide does not claim to have read the complete slides, their epsilon conventions, or a current solution-status theorem. The catalogue is not treated as a current sponsor or prize verification.

Here the emitted rules are explicitly of the ordinary context-free shapes Q->x or Q->x R, where x is one terminal from {a,b} and Q,R are nonterminals. These are the strict terminal-first right-linear case of Greibach form. No epsilon rule, conjunction or negative conjunct is required for this regular restriction. The start state rejects the empty word, so no epsilon exception is needed. Producing these rules for a restricted regular language does not convert every Boolean grammar, nor does it convert the full unrestricted Example 4 language.

## Declared restricted language

For a nonnegative integer B, define L_B to contain exactly the above words satisfying 0<=n_1<=B. There is no bound on n_i for i>=2, except n_i!=n_1. The literal input uses B=7 and a separate coefficient horizon H=128. Those two scalars were taken from the intermediate dimension and profile count of released Commons #31627. No matrix, product, deletion family, codeword, or earlier Boolean chart is consumed or recomputed.

Input blob: `639e6fb825955868f53cc6c843063f4edfb898d8` (640 UTF-8 bytes).
Its complete text is embedded in the construction envelope.

The restriction itself is declared here, rather than attributed as a bound imposed by Okhotin. The classical facts that regular languages have finite automata and right-linear grammars are not claimed as new. The contribution is the explicit reusable construction and complete finite certificate/navigation record for this input.

## State invariant and exact all-length behavior

Before the first b, a state F_r remembers the number r of initial a symbols, for 0<=r<=B. Its a transition advances to F_(r+1), or to the dead state if r=B; its b transition enters T_(r,0).

After the first b, state T_(r,c) remembers the first length r and the current later-block counter capped at r+1:

```text
c = min(actual current a-run length, r+1).
```

There are states c=0,...,r+1. Reading a increments the capped counter. Reading b goes to the dead state exactly when c=r, and otherwise resets to T_(r,0). Since c=r occurs exactly at actual length r, capping all larger lengths loses no information relevant to the exclusion. Every T_(r,0) is accepting, marking a completed block; all other states reject. The dead state loops on both letters and rejects.

This invariant proves correctness by induction on every finite input prefix. The initial phase enforces the first-length bound, and each subsequent b checks precisely the required comparison with the first block. Ending before a b leaves an incomplete block and rejects. No word-length bound is used in this argument.

Every raw state has a saved access word:

- F_r: a^r.
- T_(r,c): a^r b a^c.
- Dead state: a^(B+1).

These words follow the stated transition rules and establish reachability. The construction has (B+1)(B+6)/2+1 raw states. At B=7 this is 53 states and 106 transitions.

## Distinguishing suffixes and quotient

The compiler works on unordered pairs of distinct raw states. Pairs with different acceptance bits receive distance zero and the empty distinguishing suffix. It then performs a reverse breadth-first traversal of the pair transition graph. If a letter sends a pair to a pair with distance d, that predecessor pair can be distinguished in d+1 symbols. The first discovered distance is the shortest such distance because the traversal starts simultaneously from every distance-zero pair.

After all distances are known, each positive-distance pair selects the first letter in a<b order that decreases distance by one, followed by the saved suffix of that successor pair. Induction on distance gives a distinguishing suffix, and the first-letter choice gives the lexicographically first suffix among shortest ones. Its saved proof edge records the chosen symbol and unordered successor pair. A distance-null pair has no path to an acceptance difference; the unmarked relation preserves acceptance and successor equivalence, so it identifies precisely states agreeing on every finite suffix. These are standard finite-automaton equivalence principles, not a new minimization result.

The actual 53-state input has 360 initial acceptance-different pairs. The reverse traversal visits 2,591 predecessor-pair combinations and marks every one of its 1,378 pairs. Thus no two raw states merge: the reachable DFA is minimal, and its quotient has the same 53 states. The longest shortest suffix has length nine. For example, raw states 41 and 50 have saved shortest suffix `abaaaaaab`, with first proof edge to the unordered pair [42,51].

All pairs, including their suffixes and proof edges, are retained. The reader returns those records; it does not recompute pair distinguishability. A query using identical state labels returns equivalent immediately. “Minimal” refers to the DFA state count for L_7; no minimal grammar-size assertion is made.

## Terminal-first grammar and derivations

There is one nonterminal Q_q per quotient state q. For every transition q --x--> r, emit Q_q->x Q_r. When r is accepting, also emit Q_q->x. The start nonterminal corresponds to the DFA start state. No epsilon production is emitted.

For a nonempty word, use the continuation rule for each symbol except the last, then use the terminal-only rule for the last symbol. Such a complete derivation exists exactly when the deterministic run ends in an accepting state. Conversely, every terminal derivation follows those transitions and must finish using a transition into an accepting state. This proves exact equivalence for nonempty words. Both the start DFA and the grammar reject the empty word.

The reader retains rule identifiers in every accepted membership, rank or selected-word trace. An accepted word has one such terminating derivation: its run is deterministic and only the final step may use a terminal-only rule. Nonterminating rule cycles, including dead-state cycles, do not derive finite words. The grammar does not need to discard those rules for language correctness.

There are 150 actual rules: 106 continuation rules and 44 terminal-only rules. Every rule has one leading terminal and at most one following nonterminal. The complete rule array and transition-to-rule index are saved.

## Exact coefficient table

For each quotient state q and remaining length l, let C(l,q) count accepted suffixes of exactly l symbols:

```text
C(0,q) = 1 if q is accepting, otherwise 0
C(l,q) = C(l-1, delta(q,a)) + C(l-1, delta(q,b)).
```

The two leading symbols define disjoint word families, proving the recurrence. Arbitrary-precision integers are serialized as canonical decimal strings. The compiler forms 6,837 cells through horizon 128, using 6,784 additions. It does not enumerate the represented words.

| Word length | Accepted word count |
|---:|---:|
| 0 | 0 |
| 1 | 1 |
| 2 | 1 |
| 7 | 26 |
| 8 | 46 |
| 13 | 964 |
| 64 | 390736134555862151 |
| 128 | 3261580183297445286869369238003347558 |

At a fixed length, words are ordered lexicographically with a<b. Prefix counts follow the saved transition path and read the remaining-length coefficient. Ranking adds the size of the a-branch whenever the actual next symbol is b. Selection compares the residual rank with that branch size and chooses one branch. Each method therefore uses the same exact partition of completions.

## Reusable API and limits

The dependency-free CommonJS module exports `SCHEMA`, `LIMITS`, `buildIndex`, and `openIndex`.

`buildIndex(firstBound, horizon)` requires safe integers 0<=firstBound<=12 and 0<=horizon<=512. It constructs the semantic DFA, the full pair-separation certificate, quotient, grammar and coefficient table. Only B=7, H=128 was executed here; other supported parameter branches were source-inspected. The bounds are engineering limits and do not narrow the definition of the source language.

`openIndex(snapshot)` clones and structurally checks the saved record, indexes pair rows, and parses coefficient strings to BigInt. It checks dimensions, transition ranges, acceptance types, pair order and lengths, coefficient syntax, and rule identifiers/shapes. It does not independently re-prove the state semantics, verify each separator by running it, recompute quotient equivalence, cross-check every grammar edge, or rebuild coefficients. Its mathematical provenance is conditional on the saved construction.

| Reader method | Result |
|:---|:---|
| `summary()` | Dimensions, grammar size, horizon count and construction work |
| `rawState(id)` | Semantic state record, transitions and quotient label |
| `quotient()` | Complete saved quotient and class map |
| `grammar()` | Complete rules and transition-to-rule index |
| `distinguish(left,right)` | Saved shortest suffix/proof edge, or equivalence |
| `pairPage(start=0,limit=16)` | Rows in increasing raw-state pair order |
| `counts()` | Start-state counts at every saved length |
| `count(length,prefix='')` | Exact number of completions and prefix state trace |
| `membership(word)` | Accepted/rejected, complete run, and rule IDs if accepted |
| `rank(word)` | Zero-based rank for a member; lower insertion rank for any word |
| `select(length,rank)` | Word, full count decisions, run and derivation |
| `page(length,start=0,limit=8)` | Selected records in lexicographic order |
| `work()` | Saved-index and new-query work counters |

Words contain only a and b. Membership accepts inputs up to 4,096 symbols, independent of the saved coefficient horizon. Count, rank and select require the requested total length to be within the horizon. A prefix longer than the requested length has zero completions. Ranks are nonnegative BigInts, safe integers, or canonical decimal strings; string rank inputs are capped at 300 digits. Page starts may equal the family size for an empty page; selection ranks must be strictly smaller. Pair pages allow at most 128 rows, word pages at most 32. Invalid dimensions, symbols, state labels, ranks and ranges are rejected.

The construction uses a finite state-pair computation and O(H*K) coefficient cells for K quotient states; large integer arithmetic has its ordinary bit cost. No new general counting or grammar-conversion complexity bound is asserted.

## Saved construction and fresh reader

Executed source: `a86e1ee6db1b816a70fd0b4a40a1eebb0fb568bf` (12,084 bytes).
Complete construction envelope: `470fc77f99f8d12e0ed22631afb70ac9d5849bf9` (507,992 bytes).
Saved reader: `1a2eb0c938ca5c177fa90a088bc0906b4610c5b2` (269,190 bytes).

The source was syntax-parsed, inspected and banked with the declared input before the one production construction. A fresh reader then opened that saved envelope and retained all 38 responses. Its queries include the complete quotient, grammar and length totals, selected state and pair records, membership/derivation traces, prefix counts, ranks and pages.

Membership results include:

| Word | Accepted | Reason |
|:---|:---:|:---|
| empty word | No | No completed first block |
| b | Yes | One zero-length block |
| bb | No | Later length zero repeats the first |
| abb | Yes | First length one, later length zero |
| aaabaaab | No | Later length three repeats the first |
| aaabaabaab | Yes | Later lengths two and two are permitted |
| aaaaaaab | Yes | First length seven |
| aaaaaaaab | No | First length eight exceeds B |
| b followed by 500 a symbols, then b | Yes | Later length 500 differs from first length zero |

The last query has length 502, demonstrating that membership and the grammar are not truncated at the coefficient horizon. This is one retained query, not an enumeration of long words.

At total length 128:

- Prefix b has 96151855463018422468774568 completions.
- Prefix aaaaaaab has 529409360875746391620417085680307588 completions.
- Prefix aaaaaaaa has none.
- Prefix aaabaab has 22528515451855502178764364254368012 completions.
- Median rank 1630790091648722643434684619001673779 was selected and ranked from the saved coefficients; its complete word, decisions and derivation are retained in the reader file.
- The first and last length-128 words, three initial length-13 words, and an empty page at the end are also retained.

Opening indexed 53 raw states, 53 quotient states, 1,378 pair rows and 6,837 coefficient cells. The 38 queries made 1,470 transition lookups, 512 coefficient lookups, five separator lookups, 1,075 rule lookups, 75 rank additions and 423 selection steps. Counters for transition construction, pair construction and coefficient construction are all zero. Following a saved automaton and doing rank arithmetic is explicitly new query work, not a replay of the compiler.

## Opening the package

This is a usage example, not an additional execution:

```javascript
const fs = require('node:fs');
const { openIndex } = require('./first_block_grammar.cjs');
const envelope = JSON.parse(fs.readFileSync(
  './bound7_language_certificate.json', 'utf8'
));
const index = openIndex(envelope.snapshot);

index.membership('aaabaabaab'); // accepted; includes its rule IDs
index.membership('aaabaaab');   // rejected
index.distinguish(41, 50);      // saved suffix abaaaaaab
index.count(128, 'aaaaaaab');
index.select(128, '1630790091648722643434684619001673779');
```

## Files and boundary

| File | Content |
|:---|:---|
| `first_block_grammar.cjs` | Reusable constructor and saved reader |
| `FIRST_BLOCK_GRAMMAR_API.md` | Semantics, proof, contract, source coverage and results |
| `bound7_language_certificate.json` | Complete input, DFA, pairs, quotient, rules and coefficients |
| `saved_reader_queries.json` | All 38 responses and work counters |
| `README.md` | Entry point |

The DFA and grammar describe every finite word of L_7, while the saved coefficient table has its explicit length horizon. Neither result establishes a Greibach transformation for arbitrary Boolean grammars, the full unrestricted Example 4 language, the status of the general conjecture, or eligibility for an award. There was no sponsor contact or submission and no claim of mathematical priority.
