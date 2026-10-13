# Exact navigation in the cyclic Turán construction

The public module `cyclic_turan_index.cjs` describes the classical cyclic three-part, three-uniform hypergraph without listing its triples. It supplies exact counts, classification, rank/select, bounded pages, vertex degrees, and a missing-edge witness in any four-vertex set. A saved descriptor can be opened directly in a fresh runtime.

The retained instance has **2,197 labelled vertices, 981,093,378 edges, and 783,910,512 nonedges**. All ten composition blocks, their arithmetic, and all fourteen actual public-query receipts are in `n2197_cyclic_turan_index.json`. This is a complete implicit index, not an explicit list of its 1,765,003,890 triples.

The construction is classical. Its existence gives the finite inequalities
\[
\operatorname{ex}(2197,K_4^{(3)})\ge981093378,
\qquad
T(2197,4,3)\le783910512,
\]
where \(T\) is the minimum number of triples covering every four-set. Neither inequality is asserted to be equality.

## 1. Source and scope

This index implements the classical cyclic three-part construction attributed to Turán. [Andrew Frohmader’s published account](https://www.combinatorics.org/ojs/index.php/eljc/article/download/v15i1r137/pdf/), *More Constructions for Turán’s (3,4)-Conjecture*, Electronic Journal of Combinatorics **15** (2008), R137, pages 1–2, partitions vertices as evenly as possible and uses triples meeting all three parts or two vertices from one part and one from a cyclic neighbor. With our direction \(A\to B\to C\to A\), these are \(ABC,AAB,BBC,CCA\). Edges are unordered sets of three distinct vertices. Frohmader’s predecessor wording becomes this convention by reversing the cyclic labelling.

The broader Erdős712 question concerns a limiting extremal density for complete forbidden uniform hypergraphs. Here the selected case is \(K_4^{(3)}\). The balanced construction supplies the classical edge-density lower bound \(5/9\). [Oleg Pikhurko](https://pikhurko.github.io/E/Pikhurko25am.pdf), *Constructions of Turán systems that are tight up to a multiplicative constant*, Advances in Mathematics **464** (2025), 110148, uses the complementary covering function and states
\[
\operatorname{ex}(n,K_4^{(3)})=\binom n3-T(n,4,3).
\]
The construction therefore gives covering-density upper bound \(4/9\). That 2025 introduction describes this as the first open case; this is a dated source statement, not an exhaustive later-status survey.

The new artifact counts the particular balanced finite construction and supplies navigation and queried nonedge certificates. It neither establishes global extremality nor determines the limiting extremal density.

## 2. Vertex and edge conventions

The vertex set is \([n]=\{1,\ldots,n\}\). The three parts are contiguous labelled intervals \(A,B,C\), of sizes \(a,b,c\), in that order. A triple is an unordered set of **three distinct** vertices. Public triple and four-set inputs may arrive in any order; the module sorts them and rejects repetitions. It does not identify different labels or quotient hypergraphs by isomorphism.

The permitted repeated-part orientation is
\[
A\longrightarrow B\longrightarrow C\longrightarrow A:
\]
two vertices in a part may be joined to one vertex in its indicated successor. Thus the edge classes are \(ABC,AAB,BBC,CCA\). In the class name \(CCA\), the two \(C\)-vertices form the pair; the actual output triple is still sorted numerically. Reversing the cyclic naming gives an isomorphic description when the parts are correspondingly relabelled; it is not a change in the mathematical attribution.

For a balanced request `{n,...}`, the allocation is
\[
(a,b,c)=\left(\left\lfloor\frac{n+2}{3}\right\rfloor,
              \left\lfloor\frac{n+1}{3}\right\rfloor,
              \left\lfloor\frac n3\right\rfloor\right).
\]
Alternatively, `part_sizes` accepts an explicitly ordered triple of nonnegative sizes. The construction and all formulas remain valid for unbalanced and empty parts. The \(5/9\) limiting statement below concerns the balanced family.

If \(n<3\), both triple families are empty and density fractions are `null`. If \(n<4\), no valid four-set query exists; the clique exclusion and covering properties are vacuous. An empty part has `null` endpoints and degrees, because it has no vertex at which to evaluate a degree. These endpoint branches are part of the public contract and were inspected in source, not separately run as a synthetic suite.

## 3. Why every four-set has a nonedge

This is the elementary argument for the credited construction. Take four distinct vertices and record their counts in the three parts.

If a part contains at least three of them, any three from that part form a same-part nonedge. This covers compositions \(4+0+0\) and \(3+1+0\).

Otherwise, the composition is either \(2+2+0\) or \(2+1+1\).

- In the \(2+2+0\) case, the two occupied parts cannot both be the permitted successor of the other in a directed three-cycle. Choose a pair in the part for which the other occupied part is the forbidden successor, and one vertex in that other part.
- In the \(2+1+1\) case, the repeated part permits a singleton in exactly one of the two other parts. Choose its pair and the singleton in the other part.

In both cases this gives a reverse-oriented mixed nonedge: \(AAC\), \(ABB\), or \(BCC\). Consequently the edge hypergraph contains no complete four-vertex three-graph, and its complement meets every four-set.

The executable witness follows this argument directly. It first scans parts \(A,B,C\) for three available vertices, choosing the first three in the first qualifying part. Otherwise it scans potential pair parts in that same order and looks for a vertex in the forbidden successor. It then ranks the selected missing triple. It does not generate the four candidate triples or enumerate other four-sets.

The returned certificate distinguishes `same_part_triple` from `reverse_cyclic_pair` and, in the latter case, records both the chosen and permitted singleton parts. Correctness is the argument above, not an exhaustive runtime check over \(\binom n4\) inputs.

## 4. Counts, degrees, and the limiting convention

Every triple has one of ten part compositions. The four edge classes have total
\[
E=abc+\binom a2 b+\binom b2 c+\binom c2 a.
\]
The six nonedge classes have total
\[
C=\binom a3+\binom b3+\binom c3+
  \binom a2c+\binom b2a+\binom c2b.
\]
Here a binomial coefficient is zero if its nonnegative upper argument is below its lower argument. Partitioning triples by composition proves
\[
E+C=\binom{a+b+c}{3}.
\]

For a vertex in a nonempty part \(A\), its edge degree is
\[
d_A=bc+(a-1)b+\binom c2.
\]
The three terms correspond to \(ABC\), a pair containing that vertex in \(AAB\), and the vertex acting as singleton in \(CCA\). Cyclically,
\[
d_B=ca+(b-1)c+\binom a2,\qquad
d_C=ab+(c-1)a+\binom b2.
\]
Its nonedge degree is \(\binom{n-1}{2}-d_A\), or the corresponding cyclic expression. Summing incidences gives
\[
a d_A+b d_B+c d_C=3E.
\]
Terms for empty parts contribute zero without assigning a fictitious vertex degree. The complementary degree sum is \(3C\).

The constructor evaluates the three pair counts, three same-part triple counts, total triple count, and one per-vertex pair count: eight fixed-order binomial evaluations. It constructs ten block rows. It checks both the triple partition identity and the two incidence identities on the actual input. No vertices, triples, or four-sets are enumerated to obtain these counts.

For balanced parts, \(a,b,c=n/3+O(1)\). Thus
\[
E=\frac{5}{54}n^3+O(n^2),\qquad
\binom n3=\frac16n^3+O(n^2),
\]
so this classical family has limiting edge density \(5/9\) and complementary density \(4/9\). The finite quotient \(E/\binom n3\) is not the limiting extremal density. In particular, a finite construction's edge count is a lower bound on the maximum, not a proof of that maximum or an upper bound on its limit.

## 5. Exact ordering and inverse navigation

Ranks are zero-based within one chosen family. The order is explicit:

- Edges: `ABC, AAB, BBC, CCA`.
- Nonedges: `AAA, BBB, CCC, AAC, ABB, BCC`.

A block's start is the sum of preceding block counts in that family. Blocks with count zero retain their rows and may share a start; selection skips them. This is a block order with colexicographic combination order inside repeated-part blocks. It is **not** global lexicographic order on all sorted triples.

Within each part, the smallest vertex has local index zero.

For \(ABC\), local indices \((i,j,k)\) have block rank
\[
((i b)+j)c+k.
\]
The \(C\)-index varies fastest, then \(B\), then \(A\). Ordinary exact quotient and remainder invert this mixed-radix formula.

For a pair with local indices \(i<j\), its colex rank is
\[
\binom j2+i.
\]
There are \(\binom j2\) pairs whose larger entry is smaller than \(j\), followed by the \(j\) pairs having larger entry \(j\), in increasing smaller entry. For a pair block whose singleton part has size \(s\), the block rank is
\[
\left(\binom j2+i\right)s+k,
\]
where \(k\) is the singleton's local index. The singleton varies fastest.

For a same-part triple \(i<j<k\), the colex rank is
\[
\binom k3+\binom j2+i.
\]
The leading term counts all triples with smaller largest entry. The remaining term orders the lower pair. This provides each rank from zero through \(\binom{s}{3}-1\) exactly once.

Selection inverts the colex rank by binary search for the largest admissible upper index whose binomial contribution does not exceed the remaining rank. The identity
\[
\binom{v+1}{r}-\binom vr=\binom v{r-1}
\]
places the residual in the next smaller combination's valid range. After choosing the largest and, if needed, middle entries, the final residual is the smallest local index. These are bounded searches on integers, not combination generation.

Classification identifies the composition, computes that block rank, and adds the saved start. Selection locates the containing nonempty block, performs mixed-radix or colex inversion, and returns sorted vertex labels. For a valid generated descriptor, the formulas prove the two operations are inverse. The implementation also refuses selected or ranked values that contradict the supplied block size.

Construction uses a fixed number of arithmetic operations for three parts and ten blocks. Ranking and four-set classification use a fixed number of part operations; colex selection uses \(O(\log n)\) binary-search comparisons at binomial orders at most three. A page has at most 128 selections. These statements count arithmetic operations, not unit-cost operations on arbitrarily long integers; bit lengths still affect BigInt cost.

## 6. Public API and limits

Exports:

```js
module.exports = {
  createCyclicTuranIndex,
  openRetainedCyclicTuranIndex,
  CYCLIC_TURAN_LIMITS
};
```

Create an index with exactly one size specification:

```js
createCyclicTuranIndex({
  n: "2197",
  source_id: "identified caller input"
});

// General contract; this alternative was source-inspected, not separately run.
createCyclicTuranIndex({
  part_sizes: ["733", "732", "732"],
  source_id: "identified ordered partition"
});
```

`source_id` is a required nonempty label of at most 2,048 characters. It is retained provenance metadata, not an authenticated identity. Inputs accept nonnegative BigInt values, safe integer Numbers, or canonical decimal strings. A canonical nonnegative decimal is `"0"` or a nonzero leading digit followed by digits; signs, leading zeroes, exponent notation and fractional forms are rejected. Vertex queries additionally require positivity. Unsafe numeric inputs are rejected rather than rounded.

| Limit | Value |
|---|---:|
| Decimal digits in each part size and total vertex count | 256 |
| Decimal digits in an input rank or saved count | 768 |
| Returned triples in one page | 128 |
| Source label length | 2,048 characters |

The total size must satisfy the vertex cap even if each individual part satisfies it. All mathematical counts, labels, local indices, offsets and ranks are computed with BigInt and returned as decimal strings. Small control values such as page length, multiplicities and diagnostic counters are Numbers. There is no conversion of a potentially large rank or label to Number.

The returned object has these methods:

| Method | Result and contract |
|---|---|
| `count("edge"|"nonedge")` | Exact family size as a decimal string. |
| `summary()` | Part intervals, degrees, ten blocks, totals and unreduced exact density fractions; fractions are null when \(n<3\). |
| `classifyTriple(vertices)` | Family, rank, composition class, block rank and sorted labels; this is the same implementation as `rankTriple`. |
| `rankTriple(vertices)` | Classifies and ranks exactly three distinct valid labels. |
| `select(family, rank)` | Triple at a rank satisfying \(0\le r<\text{count}\). |
| `page(family, {start, limit})` | Consecutive ranks; defaults are start zero and limit 128. Start equal to count returns an empty terminal page. |
| `degree(vertex)` | Part name, local index, edge degree and complement degree for the given label. |
| `nonedgeInFour(vertices)` | Exactly four distinct labels, their part counts, a direct composition certificate, and a ranked missing triple. |
| `snapshot()` | Complete JSON-safe implicit descriptor, including the retained arithmetic. |
| `work()` | Counters for the current constructed or opened object. |

A page limit must be an integer from one through 128. A page start beyond the family size is rejected. `next_rank:null` means the page reaches the end of that family; it does not say that other query types or mathematical problems are exhausted. Errors are synchronous `RangeError` exceptions. Query errors may leave diagnostic counters incremented, but they do not alter mathematical state.

The index's mathematical state is immutable after construction or opening. Inputs are not sorted in place. Summary, snapshot and query results are outward copies; modifying a returned object does not change the index. Only diagnostic work counters change during normal queries. The module performs no I/O and has no package dependencies.

## 7. Saved descriptors and their trust boundary

`openRetainedCyclicTuranIndex(snapshot)` opens the descriptor without calling the constructor. It normalizes the fixed metadata, three part rows and ten block rows; checks canonical bounded numbers, contiguous part intervals, the declared balanced allocation, composition labels, contiguous family block starts, family totals, degree-complement totals and the supplied incidence equalities.

Those checks establish a structurally usable saved representation with the stated additive consistency. They do **not** independently recompute binomial counts or the degree formulas, prove a supplied descriptor's mathematical provenance, authenticate `source_id`, or compare a Git blob. Unknown extra fields are not copied into the normalized state. A fabricated descriptor can therefore carry false numerical premises despite passing these checks; query-time range guards are not a general certification of it.

For the checked-in consumer, the descriptor comes from the one recorded constructor execution and is bound to the exact source identity below. A caller loading another descriptor must establish its provenance separately. Opening an index does not recertify the source calculation.

A normal CommonJS consumer can use the saved artifact directly:

```js
const { openRetainedCyclicTuranIndex } = require("./cyclic_turan_index.cjs");
const receipt = require("./n2197_cyclic_turan_index.json");
const index = openRetainedCyclicTuranIndex(receipt.snapshot);

index.count("edge"); // "981093378"
index.nonedgeInFour(["651", "986", "1532", "2197"]);
index.select("nonedge", "2197"); // vertices ["3", "20", "25"]
```

In a connected V8 context, obtain the two complete texts through the authorized repository API, evaluate the CommonJS source with a module object, parse the JSON text, and call the same exported loader. No filesystem or subprocess is required:

```js
const moduleBox = { exports: {} };
new Function("module", "exports", sourceText)(moduleBox, moduleBox.exports);
const index = moduleBox.exports.openRetainedCyclicTuranIndex(
  JSON.parse(datasetText).snapshot
);
const page = index.page("edge", { start: "392758988", limit: 8 });
```

These examples describe how to consume the retained result. They are not additional executions claimed by this artifact.

## 8. The actual 2,197-vertex consumer

The input integers are taken from the already-retained Commons #31431 file:

`research/ppl066_kimberling_greedy_differences/published1000_through1384.json`

Git blob: `261dfae6d26afdd491aba3daf5875cb00fb2d795`  
Pinned merge: `d7e40695887c85ccc8f28d7b3cee8a4fa4a7c6cf`

| Existing position index | Stored value | New use |
|---|---:|---|
| 1,001 | 651 | Four-set vertex |
| 1,257 | 986 | Four-set vertex |
| 1,379 | 2,197 | Vertex count and four-set vertex |
| 1,384 | 1,532 | Four-set vertex |

Their sequence meaning is only a reproducible source of finite input integers. No earlier greedy transition, maximum search, sign window, or published sequence prefix was reconstructed.

### Part degrees

| Part | Labels | Size | Edge degree per vertex | Nonedge degree per vertex |
|---|---|---:|---:|---:|
| A | 1–733 | 733 | 1,339,194 | 1,070,916 |
| B | 734–1465 | 732 | 1,339,926 | 1,070,184 |
| C | 1466–2197 | 732 | 1,339,925 | 1,070,185 |

For every vertex the two degrees sum to 2,410,110. The weighted edge degree sum is 2,943,280,134, exactly three times the edge count. The complementary sum is 2,351,731,536.

### All ten retained blocks

`C(x,j)` in the formula column denotes \(\binom{x}{j}\). Start ranks belong to the indicated family.

| Class | Family | Formula | Start rank | Count |
|---|---|---|---:|---:|
| ABC | edge | abc | 0 | 392,758,992 |
| AAB | edge | C(a,2)b | 392,758,992 | 196,379,496 |
| BBC | edge | C(b,2)c | 589,138,488 | 195,843,672 |
| CCA | edge | C(c,2)a | 784,982,160 | 196,111,218 |
| AAA | nonedge | C(a,3) | 0 | 65,370,406 |
| BBB | nonedge | C(b,3) | 65,370,406 | 65,102,860 |
| CCC | nonedge | C(c,3) | 130,473,266 | 65,102,860 |
| AAC | nonedge | C(a,2)c | 195,576,126 | 196,379,496 |
| ABB | nonedge | C(b,2)a | 391,955,622 | 196,111,218 |
| BCC | nonedge | C(c,2)b | 588,066,840 | 195,843,672 |

The totals are 981,093,378 edges and 783,910,512 nonedges, summing to 1,765,003,890. The saved density fractions retain these exact numerators and the common denominator without decimal rounding.

### Four-set and navigation outputs

The source quartet is \(\{651,986,1532,2197\}\). Its part counts are \((1,1,2)\). A pair in \(C\) permits a singleton in \(A\), so the pair \(\{1532,2197\}\) together with \(986\in B\) is missing. The returned triple is
\[
\{986,1532,2197\},
\]
class \(BCC\), nonedge rank **783,423,984**, block rank **195,357,144**.

Other actual outputs include:

| Operation | Exact result |
|---|---|
| Rank source triple \(\{651,986,1532\}\) | Edge \(ABC\), rank 348,470,130 |
| Select that edge rank | \(\{651,986,1532\}\) |
| Select nonedge rank 2,197 | \(AAA\), \(\{3,20,25\}\) |
| Rank \(\{3,20,25\}\) | Nonedge rank 2,197 |
| Select final edge rank 981,093,377 | \(CCA\), \(\{733,2196,2197\}\) |
| Page eight edge ranks from 392,758,988 | Last four \(ABC\) triples followed by first four \(AAB\) triples |
| Page final eight nonedge ranks | \(BCC\) triples with pair \(\{2196,2197\}\) and singleton 1458 through 1465 |

The two pages retain all sixteen returned triples. The receipt also contains both family-count calls and all four queried vertex-degree records.

### Execution accounting

One constructor call at **2026-10-04 19:32:34.603 UTC** used eight construction binomial evaluations and ten block rows. It enumerated zero vertices and zero full triple or four-set families. Its observed elapsed time was one millisecond.

A separate connected V8 context opened the saved JSON descriptor at **19:33:09.844 UTC** and made fourteen public calls. Opening inspected three part rows and ten block rows. The calls produced nineteen selected triples, including the sixteen page records, and one missing-edge witness. They used 140 colex binary-search steps and 143 query binomial evaluations, with **zero construction binomial evaluations or block reconstruction**. Opening and queries each took one millisecond in this observation. These are single elapsed observations, not statistical benchmarks or a claim about maximum-sized inputs.

The source was unchanged across constructor and reader. Its Git blob is
`fe690ba3cde091aef98b39e22264e2fe1dfdb628`, containing 20,147 UTF-8 bytes. The complete receipt is Git blob
`3de78527af2bac56cdf75ed8805a5e86f8f97607`, containing 16,372 UTF-8 bytes.

The actual consumer exercises the described balanced input and queries. Other sizes, general unbalanced partitions, empty parts, maximum-digit inputs, and error paths received source inspection only. No second constructor, exhaustive family scan, source-data replay, or separate synthetic verification suite was run.

## 9. Delivery boundary

This package supplies a reusable finite construction and exact navigation with a direct all-four-set mathematical argument. Its implicit representation is small even when its number of triples is large. It does not determine \(\operatorname{ex}(n,K_4^{(3)})\), prove the conjectured limiting extremal density, classify all extremal examples, or supply a new external record.

Original mathematical attribution, the accepted scalar source and existing submission ownership remain intact. The scope is this separately claimed implementation and its complete new finite receipts.

