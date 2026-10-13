# Finite integer-alphabet Hankel prefix index

This package classifies every word of length at most eleven over the fixed integer alphabet **{5,7,11}** whose in-range shifted Hankel determinants are all nonzero. The complete family contains **54,331 words of length eleven**, with every valid shorter prefix and every first-zero branch rejection retained.

This is a finite integer-alphabet consumer. It does not construct an infinite sequence or settle Shallit's integer variant. It also does not repeat the accepted four-symbol morphic calculation: every new matrix entry belongs to {5,7,11}, whereas that earlier calculation used only entries in {1,2,3,4}.

## Source convention and current distinction

Shallit's official [BCTCS 2014 slides](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf), printed slides 32–33, define a sequence indexed from zero and the matrix

    H_n(k)[i,j] = a_(k+i+j),   0 <= i,j < n.

Problem 8 asks for a sequence on **three real numbers** with nonzero determinants for every n >= 1 and k >= 0. It does not fix the alphabet {1,2,3}, require integer symbols, or restrict to unshifted leading determinants.

The actually read [current author updates](https://cs.uwaterloo.ca/~shallit/talks.html), under the 2014 and 2010 talks, report that Claudemir de Souza Cavalcante solved the three-real-number question on July 31, 2026, using an LLM. The author separately describes the variant on three or four integers as unresolved. This package records that attributed statement, not a proof verification. The linked certificate was not opened or reviewed. The old slide's open label is therefore not promoted to current status.

The finite alphabet here is a declared restriction of the integer variant. Its scalars 5,7,11 are copied from the input of [#31845](https://github.com/woahwhattheheck/commons/pull/31845), merge 316030d85af9fa132a15acf88daf570292cccb7d, path research/erdos890_consecutive_prime_incidence/input4.json, blob e00a3c161c7dd808d86de01aebe29d36e1e7bc9d. Their primality is irrelevant; no prior CRT, sieve or factor computation is used.

The completed PPL036 work, #31364, #31371 and #31401, remains an independent accepted result for the morphic alphabet {1,2,3,4}, through order 64. No old factor language, determinant, minor, closure proof or reader query is recomputed here. No matrix input in the two computations is equal.

## Finite definition and exhaustive prefix construction

For a finite word w of length L, admissibility means

    det(H_n(k)) != 0
    for every n>=1, k>=0 with k+2n-2 < L.

Order one therefore checks every individual symbol. The empty word is admissible because it has no positive-order Hankel window. A positive-order n matrix uses exactly 2n-1 consecutive symbols.

Every prefix of an admissible word is admissible. Conversely, after appending one symbol to an admissible prefix, the only new windows are those ending at that new symbol. The compiler checks these in increasing order n. When it finds a zero, the whole branch is rejected: any extension would retain that same zero window. Otherwise the new prefix is retained and extended by each alphabet symbol, in increasing numerical order.

This argument makes the bounded search complete. It uses neither a heuristic candidate list nor an assertion that surviving finite prefixes extend indefinitely. A valid short prefix may have no completion at a later length; saved completion counts answer only through length eleven.

The prefix tree records all three branch outcomes at each nonterminal node. A successful branch retains its child and every new-window determinant reference checked during that append. A rejected branch retains the first zero, including its order, shift and determinant-record ID. Terminal nodes retain one completion. Nonterminal completion counts sum the child counts; rejected branches contribute zero.

| Length | Admissible prefixes |
|---:|---:|
| 0 | 1 |
| 1 | 3 |
| 2 | 9 |
| 3 | 24 |
| 4 | 66 |
| 5 | 174 |
| 6 | 462 |
| 7 | 1,194 |
| 8 | 3,114 |
| 9 | 8,080 |
| 10 | 20,994 |
| 11 | 54,331 |

There are 88,452 retained nodes in total. These are labelled words, not equivalence classes under reversal, symbol permutation, rescaling or any other symmetry.

## Exact determinant records

The implementation memoizes a determinant by the entire odd-length symbol word defining it. The code digits 0,1,2 encode the alphabet positions 5,7,11; they are not the matrix entries.

The classical Desnanot–Jacobi determinant identity specializes for Hankel matrices to

    D_n(k) D_(n-2)(k+2)
      = D_(n-1)(k) D_(n-1)(k+2) - D_(n-1)(k+1)^2.

The leading and trailing principal minors give the two outer terms, and the two off-diagonal minors agree because the matrix is Hankel. The compiler uses D_0=1 as its empty-minor convention and computes D_1 directly from the symbol.

Every division has a nonzero denominator in this prefix procedure. All smaller windows ending at the current position have already passed, and every smaller window ending earlier belongs to the accepted prefix. If a lower order fails, the branch stops before any higher-order division is requested. The source checks the nonzero-minor precondition and exact divisibility before recording the quotient.

This is an application of a classical identity, not a new determinant theorem. The retained records include every computed value and its four parent references; the zero-order and one-symbol cases have empty parent lists. Zero values are retained. No zero-denominator fallback or floating-point determinant is used.

| Once-only construction work | Value |
|---|---:|
| New determinant evaluations | 64,080 |
| Total records including D_0 | 64,081 |
| Distinct zero records | 274 |
| Condensation numerators / exact divisions | 64,077 / 64,077 |
| Determinant cache hits | 718,282 |
| Prefix nodes | 88,452 |
| Append attempts / window checks | 102,363 / 526,081 |
| Completion additions | 88,451 |
| Accepted old determinant evaluations | 0 |

The all-ternary-tree and determinant budgets are explicit in input11.json. The actual run stayed within them. A source-only return-shape correction for rejected-prefix marginals occurred before the first construction; no executed calculation was changed or repeated.

At the final append depth, 8,651 extensions are rejected. Their first-zero orders are 2: 5,710; 3: 1,464; 4: 1,103; 5: 183; and 6: 191. These are branch-rejection counts at length eleven, not counts of distinct zero matrices or all invalid words.

## Complete saved reader

~~~javascript
const fs = require('fs');
const {unpack} = require('./unpack_prefix_index.cjs');
const {openIndex} = require('./integer_hankel_prefix_index.cjs');
const manifest = JSON.parse(fs.readFileSync('prefix_manifest.json','utf8'));
const data = unpack(manifest, name =>
  JSON.parse(fs.readFileSync(name,'utf8')));
const reader = openIndex(data);
const selected = reader.select('1000', [5,7]);
const inverse = reader.rank(selected.word, [5,7]);
const positionCounts = reader.marginals([5,7]);
~~~

The example documents CommonJS reuse. The actual compiler and reader loaded unchanged source in V8; no native executor, Node CLI or filesystem process was used.

| Method | Contract |
|---|---|
| compile(input) | Construct the finite prefix family and exact determinant records once. |
| openIndex(saved) | Open the trusted retained tree and records. |
| summary() | Complete saved counts, rejection profile and work summary. |
| prefix(word), check(word) | Admissibility and completion count; rejected input gets the first-zero certificate. |
| count(prefix) | Number of full length-eleven completions of that prefix. |
| select(rank,prefix) | Zero-based lexicographic completion and full saved-branch trace. |
| rank(fullWord,prefix) | Exact inverse, or null on a rejected branch. |
| page(start,limit,prefix) | Up to 100 consecutive selections and a next rank. |
| marginals(prefix) | Complete positional counts of the three symbols among its full completions. |
| determinantPage(start,limit) | Up to 1,000 complete saved determinant records. |
| work() | New reader operation counters. |

Words are arrays containing only the three exact integer symbols. Prefixes may be empty but cannot exceed length eleven. Rank and page-start values accept nonnegative BigInt, exact decimal strings or safe integer Numbers. A ranked word must be full length and extend the requested prefix. Invalid symbols, dimensions, negative ranks and out-of-range selections are rejected.

Lexicographic order uses 5 < 7 < 11. It is not the stored depth-first node-ID order. Select subtracts saved child completion counts; rank adds counts of earlier siblings. A zero-completion branch is skipped. An endpoint page beginning at the family count is empty.

A rejection certificate materializes the saved zero matrix from its word and order. It does not evaluate its determinant again. Positional marginals scan saved nodes under the requested prefix and add child completion counts at each position; this is new query work, not determinant or family reconstruction.

The reader trusts the retained constructor output. Structural loading does not authenticate a hostile replacement table or re-prove the mathematics.

## Actual first consumer

The separate reader retains **65 complete responses** and **21 inverse rank matches**. First, middle and last completions were selected for each of seven prefix families and ranked back.

| Prefix | Length-eleven completions |
|---|---:|
| Empty | 54,331 |
| [5] | 18,106 |
| [7] | 18,115 |
| [11] | 18,110 |
| [5,7] | 6,591 |
| [5,7,11] | 2,492 |
| [5,5,7] | 2,460 |

All 33 global positional counts are retained, as are complete tables for prefixes [5], [5,7] and [5,7,11]. Global counts for positions 0 through 10, with columns ordered 5,7,11, are:

| Position | 5 | 7 | 11 |
|---:|---:|---:|---:|
| 0 | 18,106 | 18,115 | 18,110 |
| 1 | 18,105 | 18,117 | 18,109 |
| 2 | 18,110 | 18,100 | 18,121 |
| 3 | 18,108 | 18,102 | 18,121 |
| 4 | 18,116 | 18,096 | 18,119 |
| 5 | 18,112 | 18,107 | 18,112 |
| 6 | 18,116 | 18,096 | 18,119 |
| 7 | 18,108 | 18,102 | 18,121 |
| 8 | 18,110 | 18,100 | 18,121 |
| 9 | 18,105 | 18,117 | 18,109 |
| 10 | 18,106 | 18,115 | 18,110 |

The reader also retains pages, three determinant-record pages, and actual first-zero certificates at each order 2 through 6. These query words were taken from the new saved rejection branches; no published example was reconstructed. The complete saved matrices and parent references are included in the output.

| Fresh reader work | Value |
|---|---:|
| Branch reads / completion reads | 1,145 / 133,432 |
| Rank additions / selected words | 155 / 34 |
| Determinant-record reads / materialized matrix entries | 42 / 94 |
| Marginal node scans / additions | 353,808 / 132,711 |
| New determinant evaluations / divisions | 0 / 0 |

All query responses were banked immediately. No response or partial result was lost, and both construction and reader completed without an exception. The counters are not timing benchmarks.

## Lossless structural storage

The original complete snapshot has **17,811,720 bytes**, blob **0ed40650811407c536a24b4c31255b98cb7cc859**. It is retained through a lossless array encoding, reducing repetitive property names while preserving every record:

- Node: [code, completions, branches].
- Branch: [target, checkedRecordIDs, zeroOrNull]; the branch's array index is its symbol ID.
- Zero: [recordID, order, shift].
- Determinant: [code, order, value, parentIDs].

Ten node shards and six determinant shards contain every encoded row, in order. The manifest retains the original nodes and determinants properties as null. unpack_prefix_index.cjs reconstructs their original object shapes and property order. Compact JSON serialization plus a final newline exactly matched the original snapshot bytes. This was a structural byte comparison only; no determinant, division, prefix search or reader query was rerun.

The combined encoded shard content is 8,729,096 bytes. This reduction changes representation only, not the mathematical family or evidence. The actual reader operated on the original banked snapshot; the reconstructed version is byte-identical.

| Shard | Start | Count | Bytes | Blob |
|---|---:|---:|---:|---|
| prefix_nodes_00.json | 0 | 9641 | 599889 | 0ab8c07e4cbcc490ce0db14038b08ed751e040b4 |
| prefix_nodes_01.json | 9641 | 9419 | 599938 | 9daab52e80c444cd2029452df24e49fd9f4e1150 |
| prefix_nodes_02.json | 19060 | 9401 | 599971 | 78e4530e57cb9acee43952494ef90b317080096a |
| prefix_nodes_03.json | 28461 | 9421 | 599934 | e4f7f7cb1fec90ed633a3584529dce6c63b4b9eb |
| prefix_nodes_04.json | 37882 | 9388 | 599992 | 44f82bfa08b2dc72b389de8394ce8c9a5463615c |
| prefix_nodes_05.json | 47270 | 9413 | 599931 | 41289e9cfc9f633c36c7f2f269a94394832d4457 |
| prefix_nodes_06.json | 56683 | 9415 | 599938 | 23ef41ce6cb09c5e8808f71588fc70e6149ba61b |
| prefix_nodes_07.json | 66098 | 9397 | 599982 | 493f7bead972d845180b3568ac25eaa1b30d4578 |
| prefix_nodes_08.json | 75495 | 9404 | 599873 | c8e22ff1c5deee578809f327130e90af2c6083f4 |
| prefix_nodes_09.json | 84899 | 3553 | 226793 | 3b80be8b16591b5d9ac4b6eb25f9b670e71ba2ee |
| determinants_00.json | 0 | 13349 | 599955 | 8f2d6e57aff513c6b8eb77873e87d41d165f8d0b |
| determinants_01.json | 13349 | 12279 | 600000 | 62f7357f65210b69ccacf3a1f35c59757a91ce53 |
| determinants_02.json | 25628 | 12157 | 599975 | a590ec3c8bfad9c20ae89e272899101aa7f9b715 |
| determinants_03.json | 37785 | 12197 | 599979 | fba8c26b72f15cde528d6af438aaff799a7554e1 |
| determinants_04.json | 49982 | 12070 | 599997 | c6e820ac199bad9d14de37296091445c74f6e972 |
| determinants_05.json | 62052 | 2029 | 102949 | b6d90a3ae28619948e74b3f77de614e4a582a088 |

The 133,702-byte saved_reader_queries.json has blob 310c24b5350384acc7b64735f985c46e9a3bbc8c. The constructor/reader source has blob 904fbd5f75dc9f69c26a492d37c6093e8254cf7e; the structural decoder has blob bf064d33f7979019ec11a250dd1c7f0f26bcf0c8. Input and manifest identify every remaining source and data boundary.

This exhaustive fixed-alphabet, fixed-length result neither provides an infinite integer sequence nor reopens the author-reported solved real problem. It makes no asymptotic theorem, novelty, external acceptance or prize claim.
