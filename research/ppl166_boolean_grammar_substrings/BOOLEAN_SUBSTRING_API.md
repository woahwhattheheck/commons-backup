# Retained substring certificates for binary Boolean grammars

This API builds a complete chart for the nonempty substring occurrences of one bounded word. It retains every binary-concatenation split, including those used in negative conjuncts and rejected rules, together with positive-parse counts and valid-rule records. A saved reader supports membership, occurrence count/rank/select/pages, split and rule evidence, ranked positive parse certificates, and two finite ambiguity diagnostics.

The actual consumer uses a normalized presentation of **Okhotin's Example 4** on a **231-symbol word**. One construction covers **26,796 substring occurrences** and **12,326,160 candidate split checks**. It records **3,663 accepted S-occurrences**. Both finite ambiguity diagnostic lists are empty for this word's substrings. This does not establish Boolean unambiguity on every word, and it does not answer the inherent-ambiguity question.

## 1. Source and the four separate notions

Alexander Okhotin's [*Describing the syntax of programming languages using conjunctive and Boolean grammars*](https://arxiv.org/pdf/2012.03538), dated December 8, 2020, supplies the source grammar in Example 4, printed page 11. It checks that later a-block lengths differ from the first. The grammar and language are prior material; the binary presentation below is an explicit derived normalization.

Definition 4 uses **strongly unique language-equation solutions**, requiring uniqueness at each finite length cutoff. Negation does not justify a general monotone least-fixed-point interpretation. Definition 5 requires both disjoint complete alternatives for each nonterminal and unique partitions for every concatenation appearing in a positive or negative conjunct. The latter also concerns strings rejected by the enclosing rule. Positive parse trees omit negative components, so uniqueness of an accepting tree alone is insufficient.

The [PPL166 intake card](https://prizeproblems.org/problems/166/) asks whether some language is inherently ambiguous for Boolean grammars. This artifact does not claim a current literature census or a resolution.

Keep these statements distinct:

| Notion | Meaning here |
| --- | --- |
| Unique language-equation solution | Each nonterminal's membership language is well-defined. The restricted grammar contract below has a direct proof of this property. |
| Unique positive parse certificate | A particular accepted substring has one positive parse. Negative conditions are guards, not additional subtrees. |
| Finite Definition-5 diagnostics | Neither alternative overlap nor multiple concatenation partitions occurs among this supplied word's substrings. |
| Boolean or inherent unambiguity | The former quantifies over every word for a grammar; the latter concerns all equivalent Boolean grammars for a language. The finite chart establishes neither. |

In particular, a well-defined membership language can have ambiguous rules. Language-equation uniqueness and grammatical unambiguity are different properties.

## 2. Source grammar and explicit normalization

The source example is

```text
S -> S A & not(C b) | A
A -> a A | b
C -> a C a | B
B -> B A | b
```

It describes the nonempty words

\[
a^{n_1}b\,a^{n_2}b\cdots a^{n_k}b,
\qquad k\ge1,\quad n_i\ge0,\quad n_i\ne n_1\ (i\ge2).
\]

The later exponents need not be pairwise distinct. A single block is accepted, including b when its exponent is zero.

The implementation does not apply a general grammar-normalization algorithm. It performs the following explicit substitutions for this named grammar:

1. Introduce terminal aliases `Ta -> a` and `Tb -> b`.
2. Introduce `D -> C Ta`, so `Ta D` represents `a C a`.
3. Inline the unit alternative `S -> A` as `S -> Ta A | b`.
4. Inline `C -> B` as `C -> B A | b`.
5. Add an explicit `not(epsilon)` guard to every binary rule.

These are substitutions in the grammar's language equations. The source grammar is nonnullable: A cannot contain epsilon because each alternative contains a terminal; then B cannot contain it because its recursive alternative includes A; C cannot contain it because its recursive alternative includes terminal a and its unit alternative is B; finally S cannot contain it because its alternatives include A. The new aliases and D are likewise nonnullable. Adding the empty-word guards therefore preserves this source language.

The nonterminal order is `[S,A,B,C,D,Ta,Tb]`. The rule IDs are:

| ID | Production |
| ---: | --- |
| 0 | S -> S A & not(C Tb) & not(epsilon) |
| 1 | S -> Ta A & not(epsilon) |
| 2 | S -> b |
| 3 | A -> Ta A & not(epsilon) |
| 4 | A -> b |
| 5 | B -> B A & not(epsilon) |
| 6 | B -> b |
| 7 | C -> Ta D & not(epsilon) |
| 8 | C -> B A & not(epsilon) |
| 9 | C -> b |
| 10 | D -> C Ta & not(epsilon) |
| 11 | Ta -> a |
| 12 | Tb -> b |

The six shared ordered pairs are:

| Pair ID | Concatenation | Rule uses |
| ---: | --- | --- |
| 0 | S A | Positive in rule 0 |
| 1 | C Tb | Negative in rule 0 |
| 2 | Ta A | Positive in rules 1 and 3 |
| 3 | B A | Positive in rules 5 and 8 |
| 4 | Ta D | Positive in rule 7 |
| 5 | C Ta | Positive in rule 10 |

Shared pairs are evaluated once per substring. Their support remains available even when no enclosing rule accepts that substring.

## 3. Restricted grammar contract and exact semantics

A grammar declares a nonempty finite alphabet, an ordered set of nonterminals, a start symbol and a set of productions. A terminal production has one terminal symbol on the right. Every other production has one or more positive binary conjuncts and zero or more negative binary conjuncts, plus the explicit exclusion of epsilon.

For example,

\[
A\to B_1C_1\ \&\cdots\&\ B_uC_u\
\&\neg D_1E_1\ \&\cdots\&\neg D_vE_v\
\&\neg\epsilon,\qquad u\ge1.
\]

The Boolean conditions require every positive concatenation to contain the whole word and every negative concatenation to exclude it. Each concatenation may use its own split; conjunction does not require all conjuncts to split at the same position.

The JSON field `nonempty_binary_guard:true` explicitly declares the epsilon exclusion on **every** binary production. The `negative` list contains the binary negative pairs; it does not need to repeat the separately declared epsilon guard.

The guard is essential to the general contract. Merely omitting an epsilon production does not force the empty word out of every solution of arbitrary language equations: the equation \(X=XX\) has both the empty-language and the singleton-epsilon solutions. Here, terminal rules reject epsilon and every binary rule explicitly rejects it, so the empty-word membership of every nonterminal is forced to be false.

Now proceed by word length. On a nonempty word of length l, any admitted concatenation split has two positive component lengths, both smaller than l. Assuming shorter-word membership is fixed, all binary conjuncts and every rule truth value are fixed. Terminal membership is fixed directly. This defines the membership value at length l uniquely. The construction supplies existence as well as uniqueness, and it is consistent across finite cutoffs. Thus this restricted contract has a strongly unique language-equation solution.

This argument allows recursive nonterminal references because they always shorten the evaluated substring. It does not accept nullable grammars, unit productions, arbitrary conjunct strings or general cyclic negation. The explicit normalization above is separate from the public input validator.

Epsilon concatenations have at most one partition trivially. The chart therefore stores only nonempty substrings and nonempty binary splits. Terminal rules also have no variable split. Empty-span queries return nonmembership and positive-parse count zero.

## 4. Complete chart and positive-parse counts

Let the supplied word have n symbols, with zero-based half-open spans [i,j). The chart covers every \(0\le i<j\le n\), ordered by increasing length and then increasing start. Its cell address is

\[
\operatorname{cell}(i,j)=
\frac{(l-1)(2n-l+2)}2+i,\qquad l=j-i.
\]

For a shared ordered pair (B,C), retain the exact split set

\[
K_{B,C}(i,j)=
\{t: i<t<j,\ w[i:t]\in L(B),\ w[t:j]\in L(C)\}.
\]

The bit at offset \(t-i\) is set in the saved hexadecimal mask. Offset zero and the endpoint offset l are never valid splits.

The constructor visits all candidate splits for **every shared pair** before evaluating enclosing rules. It does not short-circuit away a negative pair after a positive rule condition fails. With P shared pairs, its candidate-check count is exactly

\[
P\sum_{l=2}^n(n-l+1)(l-1)
=P\binom{n+1}{3}.
\]

This is the complete finite split domain for this word, not all words of length at most n.

### Positive parse recurrence

Write \(T_A(i,j)\) for the number of positive parse trees rooted at A on the span. For an ordered pair, its positive-parse count is

\[
Q_{B,C}(i,j)=
\sum_{t\in K_{B,C}(i,j)}
T_B(i,t)T_C(t,j).
\]

A binary rule is valid when every positive split set is nonempty and every negative split set is empty. Its positive-parse count is the product of the Q-values for its positive conjuncts. An invalid rule contributes zero. A matching terminal rule contributes one. Finally, \(T_A\) is the sum of the counts of its valid alternatives.

All arithmetic uses bounded BigInt values. The product across positive conjuncts counts separate choices of their parse trees; it does not add trees for negative conjuncts. A successful negative condition is recorded as an empty split set.

A partition count \(|K_{B,C}|\) and the weighted count \(Q_{B,C}\) are different quantities. One partition can have several child parse trees. Conversely, multiple partitions in a rejected negative context matter to Definition 5 even if there is no accepting root tree.

### Finite ambiguity diagnostics

The saved index records both complete finite violation families:

- For each substring and nonterminal, more than one valid complete production is a rule-overlap record.
- For every shared pair on every substring, more than one split is a multiple-partition record. Pair-use metadata identifies all positive and negative contexts using that pair.

The second check covers pairs on rejected substrings and in rules that fail for another reason. The Boolean summary field `finite_boolean_unambiguity_on_substrings` means exactly that both finite record lists are empty. It is not a theorem about all words.

### Sparse storage with a complete zero convention

Every substring has a membership-mask entry. Pair, rule and nonterminal count records are sparse:

| Record | Shape |
| --- | --- |
| Nonzero pair | `[cell_id, pair_id, split_mask_hex, positive_parse_count, partition_count]` |
| Valid rule | `[cell_id, rule_id, positive_parse_count]` |
| Positive nonterminal count | `[cell_id, nonterminal_id, positive_parse_count]` |

Rows are in strict cell/ID order. An absent row means **exact zero**, not missing or unfinished work. The full cell and pair domains are declared. This stores all positive and negative pair results, including zero results, without writing an explicit tuple for every zero.

The snapshot also retains occurrence-cell lists, both complete diagnostic lists, grammar/pair metadata and summary counts.

## 5. Saved navigation and certificates

### Occurrences

An occurrence is an accepted **position span**. Equal substring texts at different positions remain different occurrences. The index does not count distinct strings or enumerate a language.

For a chosen nonterminal, occurrence lists use the chart's length-then-start order. Rank is zero-based. Selection reads the corresponding retained cell; rank uses a binary search of the occurrence list. Pages return consecutive ranks and a continuation rank, or null at the end.

### Rule and split evidence

`ruleEvidence` returns its positive and negative pair masks and both kinds of count, even for a rejected rule. It also lists all valid alternatives for the same head on that span.

`splitPage` returns actual partitions in increasing offset order, with the two child spans and nonterminals. It reads saved support and child counts, then computes the returned partition's product weight. It does not search all candidate splits again.

### Ranked positive parse certificates

`selectParse` chooses a positive parse by rank:

1. Select a valid rule in input rule order using its saved count.
2. Distribute the within-rule rank across positive conjuncts in their declared order by mixed-radix division.
3. For each conjunct, visit supported splits in increasing offset order, weighted by the product of its two child counts.
4. Divide the selected split's rank into left and right child ranks and recurse on shorter spans.
5. Attach the selected rule's negative guards, each with its empty saved split mask.

The output is a DAG of nodes identified by nonterminal, span and parse rank. Repeated identical subtrees can share a node; unfolding the references gives the positive tree. All references and negative guards are retained. An explicit node cap bounds output expansion.

The certificate exposes a positive parse under the retained chart's premises. Its uniqueness does not replace the separate negative-context and alternative-overlap diagnostics.

## 6. Public API and limits

The module is dependency-free CommonJS with no I/O. It exports:

| Export | Purpose |
| --- | --- |
| `compileBooleanSubstringIndex(options)` | Build the complete bounded chart once. |
| `openRetainedBooleanSubstringIndex(snapshot)` | Restore the saved chart with explicit checks and premises. |
| `BOOLEAN_SUBSTRING_LIMITS` | Fixed resource bounds. |

Constructor options have `source_id`, `word` and `grammar`. A grammar contains `source_id`, `alphabet`, `nonterminals`, `start`, `nonempty_binary_guard:true` and `rules`. A rule is either `{head,terminal}` or `{head,positive,negative}`, with every binary conjunct an ordered two-nonterminal array. An omitted negative list means no binary negative conjuncts.

Productions are a set. Duplicate productions, even with reordered equivalent conjunct lists, are rejected. Repeated conjuncts within the same sign are rejected rather than counted as independent parse choices. A pair appearing in both signs makes that rule unsatisfiable, but the pair remains part of the diagnostic domain.

Nonterminal and rule orders are preserved and determine IDs. Shared-pair IDs follow first appearance while visiting rules, positive conjuncts and then negative conjuncts.

### Open the retained consumer in connected JavaScript

Provide the fetched complete module text as `sourceText` and JSON as `dataText`:

```javascript
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);

const saved = JSON.parse(dataText);
const index = loaded.exports.openRetainedBooleanSubstringIndex(saved.snapshot);

const rejected = index.ruleEvidence(0, 191, 199);
const negativeWitness = index.splitPage(1, 191, 199, { offset: 0, limit: 8 });
const acceptedCount = index.countOccurrences("S");
```

This usage illustrates retained queries; it is not another execution in the recorded experiment. Opening the snapshot does not call the constructor.

| Method | Contract |
| --- | --- |
| `summary()` | Copy of the finite chart totals, full-word result, ordering and scope. |
| `cell(start,end)` | Span text, cell ID and all member nonterminals with positive-parse counts. |
| `parseCount(nonterminal,start,end)` | Positive-parse count, including zero for rejection or an empty span. |
| `countOccurrences(nonterminal)` | Number of accepted positions; defaults to the grammar's start symbol. |
| `rankOccurrence(nonterminal,start,end)` | `found` with rank, or `not_member`. |
| `selectOccurrence(nonterminal,rank)` | One accepted span in length/start order. |
| `pageOccurrences(nonterminal,startRank,{limit})` | Consecutive accepted spans and `next_rank`. |
| `ruleEvidence(ruleId,start,end)` | Truth, positive count, all conjunct evidence and valid head alternatives. |
| `splitPage(pairId,start,end,{offset,limit})` | Supported partitions, their child spans and newly computed product weights. |
| `selectParse(nonterminal,start,end,rank)` | One ranked positive parse DAG; rank defaults to zero. |
| `diagnostics({kind,offset,limit})` | Pages of `"rule"` or `"split"` violations; kind defaults to rule. |
| `snapshot()` | Complete JSON-safe mathematical state. |
| `work()` | Current construction, saved-check and query counters. |

Start and end are Number safe integers with \(0\le start\le end\le n\). The end is exclusive. Symbol positions count Unicode scalar values, not UTF-16 code units or grapheme clusters; this consumer uses ASCII a and b.

Ranks accept safe integer Numbers, BigInts or canonical unsigned decimal strings. Mathematical parse counts and occurrence counts/ranks are returned as decimal strings. IDs, span positions, page offsets, finite partition counts and diagnostic counters use Numbers. Split masks are canonical lowercase hexadecimal with no `0x` prefix.

Pages default to 128 records. Start equal to the family size returns an empty terminal page; a larger start fails. A parse or occurrence selection at the count fails. Empty-span membership is false by the grammar contract.

| Bound | Value |
| --- | ---: |
| Alphabet symbols | 16 |
| Nonterminals | 24 |
| Rules | 96 |
| Total binary conjuncts per rule | 8 |
| Shared ordered pairs | 64 |
| Word symbols | 256 |
| Complete candidate split checks | 20,000,000 |
| Parse-count decimal digits | 512 |
| Page records | 128 |
| Nodes in one positive parse certificate | 4,096 |
| Source-ID characters | 2,048 |

All applicable caps must hold. A grammar and word can each satisfy their individual size limits while their combined split domain exceeds the budget; this is refused before chart construction. Large ambiguous parse counts or expanded certificates may reach their own caps. The implementation throws a synchronous `RangeError` instead of truncating mathematical counts or returning an incomplete certificate.

The chart is fixed after construction/opening. Queries change work counters only. Outward results are copies. A failed query may have advanced counters before throwing; it does not alter the chart.

## 7. Saved-loader checks and retained premises

Restoration reads all retained cells and sparse records. It checks:

- Schema, source-ID shape, bounded grammar/word contract, pair catalog and pair-use metadata.
- Complete membership-array length and valid mask bits.
- Strict sparse-record order, unique cell/ID addresses, canonical masks and positive decimal counts.
- Every split bit lies strictly inside its span, and each recorded partition count equals the mask's popcount.
- Rule truth against the **saved** positive and negative masks, including terminal matching and the nonempty guard.
- Each nonterminal count is the sum of its retained valid-rule counts, and membership agrees with positive count.
- Summary totals, every occurrence-index entry, and both complete finite diagnostic lists.

These checks do not recompute the child-membership convolution that produced a split mask. They also do not recompute pair counts as sums of child products or binary-rule counts as products of positive-conjunct counts. Those multiplicative records and their completeness remain identified construction premises. A source ID is not an external authentication mechanism.

The actual opening checked 348,348 rule guards against saved masks. It performed 5,863 rule-to-nonterminal additions and 5,863 summary additions, checked 5,402 set bits and 5,863 occurrence entries, and loaded all 26,796 membership cells. It was not a zero-work restoration.

It performed **zero new chart evaluations, zero candidate split checks and zero parse-count construction products**. Later selected certificates and split pages do perform the specific query products reported below. Successful loading is not an independent proof of every saved recurrence or of source provenance.

## 8. Actual input and complete results

### Identified scalar composition

The 24 block lengths are copied from the accepted #31434 artifact:

| Field | Identity |
| --- | --- |
| Repository | `woahwhattheheck/commons` |
| Path | `research/ppl133_erdos1052_unitary_divisors/factorial89_unitary_divisor_index.json` |
| Merge | `acff365f95e3c91a3c1b5660eef926c215e9a807` |
| Git blob | `3cad8b2aaa202bf868dc490692410092989871ec` |
| Field | `.snapshot.factors[*].exponent` |

The exponents are

```text
85, 42, 20, 13, 8, 6, 5, 4, 3, 3, 2, 2,
2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1
```

Each supplies an a-block followed by b. The composition contains 207 a symbols and 24 b symbols, for a total of 231. All 24 source indices and block boundaries are retained. These are scalar inputs to a formal-language example; no property of factorial factorization is asserted to imply a grammar theorem. No valuation, unitary-divisor, prime or earlier grammar computation was repeated.

### Complete chart

| Quantity | Result |
| --- | ---: |
| Nonempty substring occurrences | 26,796 |
| Declared cell/pair entries | 160,776 |
| Candidate split checks | 12,326,160 |
| Nonzero pair split/count rows | 5,402 |
| Valid-rule count rows | 5,863 |
| Positive nonterminal count rows | 5,863 |
| Full word accepted by S | true |
| Full-word positive-parse count | 1 |
| Rule-overlap occurrences | 0 |
| Multiple-partition occurrences | 0 |

The nonterminal occurrence counts are:

| Nonterminal | Accepted occurrences | Sum of positive-parse counts |
| --- | ---: | ---: |
| S | 3,663 | 3,663 |
| A | 231 | 231 |
| B | 300 | 300 |
| C | 869 | 869 |
| D | 569 | 569 |
| Ta | 207 | 207 |
| Tb | 24 | 24 |

Every positive nonterminal entry in this chart has count one. That observation alone would not imply the negative-context condition; the independent complete split diagnostics also matter.

### Actual rejected and accepted substrings

| Span | Text / blocks | Result |
| --- | --- | --- |
| [0,231) | The complete 24-block word | S accepts; one positive parse. |
| [191,199) | `aaabaaab`, lengths 3,3 | S rejects because the later block matches the first. |
| [195,205) | `aaabaabaab`, lengths 3,2,2 | S accepts; the later equal lengths are allowed. |
| [191,202) | `aaabaaabaab`, lengths 3,3,2 | S rejects because its earlier prefix has already failed. |

For [191,199), rule 0 has a positive S·A split at offset 4, mask `10`, and a negative C·Tb split at offset 7, mask `80`. Its negative condition therefore fails. The negative split's absolute position is 198; its children are C on `aaabaaa` and Tb on `b`. The selected C certificate has 13 nodes.

For [191,202), both the S·A and C·Tb masks are zero. The negative condition succeeds, but the positive condition fails. Thus checking only the final block inequality would give the wrong membership answer.

For the full word, rule 0 has its positive split at offset 229, separating the accepted prefix [0,229) from the final A-block `ab`. Its negative mask is zero. The selected full-word positive certificate contains 461 nodes, all retained with its negative guards.

### Occurrence navigation

The accepted [195,205) occurrence has S-rank **186**. The selection at rank **1,831** returns [105,219), length 114.

Two saved pages contain 24 occurrences:

- Ranks 0–11 are the first twelve accepted one-symbol b occurrences, beginning at [85,86) and ending at [204,205).
- Ranks 3,651–3,662 form the final page, from [1,227), length 226, through the full word [0,231), length 231.

The second page is terminal. All 24 records, not only their endpoints, are in the dataset.

### Actual execution accounting

One constructor ran in a connected V8 context. Its principal work was:

| Work | Count |
| --- | ---: |
| Chart cells evaluated | 26,796 |
| Candidate split checks | 12,326,160 |
| Successful pair splits | 5,402 |
| Pair positive-count products | 5,402 |
| Pair positive-count additions | 5,402 |
| Rule evaluations | 348,348 |
| Binary-rule positive-count products | 5,536 |
| Nonterminal count additions | 5,863 |

A fresh saved reader then made exactly **20 public calls**: four cell queries, one parse count, two occurrence counts, one occurrence rank, one occurrence selection, two occurrence pages, three rule-evidence calls, two split pages, two positive-parse selections and two diagnostic pages.

Query work included 11 occurrence binary-search steps, 238 product weights, 501 parse-rule rows visited and 236 supported parse-split rows visited. It returned 25 selected occurrence records, consisting of one direct selection and 24 page records; the separate rank receipt is not included in that counter. It returned two split records and 474 parse nodes across the two certificates. Both diagnostic pages were empty because their complete retained families are empty.

The constructor's observed elapsed time was 1,082 ms. Saved opening took 178 ms, and the 20 calls took 21 ms in that observation. These are single elapsed measurements, not statistical benchmarks or a claim of improved general parsing complexity.

## 9. Files, identities and execution boundary

| File | Role |
| --- | --- |
| `boolean_substring_index.cjs` | Public constructor and saved query API. |
| `BOOLEAN_SUBSTRING_API.md` | This derivation, scope, API contract and actual results. |
| `factorial89_exponent_word_chart.json` | Complete source composition, grammar, chart, occurrence indices, diagnostics and all query certificates. |
| `README.md` | Entry point and saved-reader usage. |

Executed source: Git blob **77bea4f678a0134f9714fc18ee2309f05bfa07ad**, **28,957 UTF-8 bytes**.

Complete JSON: Git blob **df544623b2a0835b341b8390e8f7f1e67b678b72**, **932,834 UTF-8 bytes**.

The directly loadable field is `snapshot`. The top-level artifact also retains `primary_source`, `input_composition`, `normalization`, `preflight`, `constructor_request`, `constructor_execution`, `retained_consumer` and `execution_boundary`. The sparse zero convention is explicit; no positive or negative split domain was silently dropped.

There was one input composition, one constructor and one fresh saved open, with unchanged executed source. Empty input, other grammars, maximum limits, ambiguous grammar inputs and the remaining rejection paths were source-inspected only. No synthetic suite, accepted computation replay or native process was used.

This is a reusable finite parsing and evidence interface. Its semantic uniqueness proof applies to the stated guarded binary contract; its numerical results and ambiguity diagnostics apply to the single retained word. It makes no global Boolean-unambiguity, inherent-ambiguity, novelty, external-frontier or general complexity claim.
