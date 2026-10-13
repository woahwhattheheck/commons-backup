# XOR Ramsey product API and data-custody boundary

**The implementation is recovered in full; the original saved dataset is unavailable.** The connected work store disappeared after one construction and an 18-query saved-reader session had completed, before publication began. The complete module was recovered from the literal tool transcript and independently hashed: **25,505 UTF-8 bytes, Git blob `62aae4f304edd0440c61e1e2a09dfa57ae4a1b2c`**, exactly matching the source frozen before execution. Recovery did not execute the module, reconstruct its snapshot or repeat any mathematics.

This publication banks that real implementation, its derivation and a candid [custody record](product14_run_custody.json). It does **not** deliver the originally planned complete dimension-14 snapshot or all 18 query outputs. The custody record is deliberately a different schema and cannot be passed to the saved-index loader. Its surviving counts and input list are execution observations, not substitutes for the absent certificate rows.

The lost wrapper had been assembled as 133,904 UTF-8 bytes with Git blob `307b3fc55a2c46b3b282e3deb8f4aa326567ce3d`. Its compact snapshot had 25,909 characters. That pre-loss content identity has no durable locator and is not evidence that GitHub holds the blob. No replacement bytes are assigned that identity. The originally planned `greenwood_gleason_product14.json` is not included.

## Sources and current problem status

Erdős 183 asks whether the multicolor triangle Ramsey numbers satisfy
\[
R(3;k)^{1/k}\longrightarrow\infty.
\]
Here \(R(3;k)\) is the least \(n\) such that every assignment of \(k\) available colors to the unordered edges between distinct vertices of \(K_n\) has a monochromatic triangle.

The [official August 1, 2026 report, item 9](https://openai.com/index/ten-advances-in-mathematics/), reports a superexponential lower bound resolving the problem. The complete [Formal Conjectures statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/183.lean), observed at blob `024e2abb14fbd8b48ca575f80bd98320827d53a7`, likewise labels the result solved and links an external proof. These are attributed source reports. This operation did not inspect or execute that proof. A direct report-PDF request timed out once and remained held. The earlier prize catalogue's open label is superseded by this source evidence; this package does not claim a new resolution or independently certify the reported one.

R. E. Greenwood and A. M. Gleason, [“Combinatorial Relations and Chromatic Graphs,” Canadian Journal of Mathematics 7 (1955), 1–7](https://doi.org/10.4153/CJM-1955-001-4), §4, Theorem 4, supply the source-authored three-color \(K_{16}\) construction and establish \(R(3;3)=17\). Their [original publisher scan](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/BF0DEBC881488344266BCD77CBBCD86B/S0008414X00030091a.pdf/div-class-title-combinatorial-relations-and-chromatic-graphs-div.pdf), printed pages 4–5, uses \(x^4-x-1=0\) over \(\mathbb F_2\), the subgroup
\[
H=\{1,x^3,x^3+x^2,x^3+x,x^3+x^2+x+1\},
\]
and its two nontrivial multiplicative cosets to color differences. The integer encoding and palette order below are interface choices.

The first-differing-coordinate product is a standard construction. Its complete elementary argument is given here to specify the API; no priority claim is made. The bounded source lookup did not establish an exact original product bibliography, so a speculative author attribution is not supplied.

## Base contract and triangle certificate

Put \(B=2^b\), with \(1\le b\le6\). Base vertices are coefficient-bit labels \(0,\ldots,B-1\) in \(\mathbb F_2^b\), with addition given by XOR. The caller supplies ordered nonempty classes \(D_0,\ldots,D_{C-1}\) partitioning exactly the nonzero labels. Class order determines local color names; entries inside each class are sorted.

For every class, the compiler requires
\[
u,v\in D_c,\quad u\ne v
\quad\Longrightarrow\quad u\mathbin{\mathrm{xor}}v\notin D_c.
\]
It records every unordered within-class pair, its XOR and the XOR's class. Equal inputs give zero and cannot be a third nonzero edge difference.

Color an unordered edge \(\{a,a'\}\) by the class of \(a\mathbin{\mathrm{xor}}a'\). In any triangle, if two differences are \(u,v\), the third is \(u\mathbin{\mathrm{xor}}v\). A monochromatic triangle would contradict the displayed condition. The generic compiler therefore needs only the finite additive certificate, not field multiplication or a field theorem.

Every base vertex has \(|D_c|\) neighbors of color \(c\), and the number of unordered base edges in that color is \(E_c=B|D_c|/2\). The compiler stores all canonical base edges \(a<a'\), grouped by color in lexicographic order, plus sorted neighborhoods.

### Greenwood–Gleason normalization

The coefficient encoding is
\[
a_0+a_1x+a_2x^2+a_3x^3
\longleftrightarrow a_0+2a_1+4a_2+8a_3.
\]
The displayed subgroup becomes `[1,8,12,10,15]` in its source order. Multiplication by \(x\) shifts left one bit and, if the \(x^4\) bit is set, XORs with polynomial mask `19`, implementing \(x^4=x+1\). Two five-element stages give the remaining cosets.

| Local color | Sorted differences |
| --- | --- |
| 0 | 1, 8, 10, 12, 15 |
| 1 | 2, 3, 7, 11, 13 |
| 2 | 4, 5, 6, 9, 14 |

All ten normalization steps survived in a complete pre-loss transcript output and are transcribed in the custody record. They include six conditional reductions. The original run observed 30 within-class witnesses, 40 edges per color, 120 base edges and 240 neighborhood entries. Those complete witness/edge arrays did not survive the storage loss and are not reconstructed here.

The normalizer performs no full field-table construction, irreducibility/primitivity test or generator search. The finite XOR condition is what the compiler uses to establish the required base property.

## Product theorem

For \(d\ge1\), use all length-\(d\) base-\(B\) words, most significant digit first, as the \(N=B^d\) labelled vertices. Leading zero digits are included conceptually. For two distinct vertices, let \(j\) be their first differing coordinate. If the two digits there form a base edge of local color \(c\), assign global color \(g=jC+c\). Each coordinate has a separate palette, giving \(dC\) colors.

For three distinct vertices, let \(j\) be the first coordinate where their symbols are not all equal.

- If exactly two symbols occur, the two crossing edges first differ at \(j\). The edge inside the equal-symbol pair first differs later, because that pair consists of distinct full words. Its coordinate palette differs from the other two.
- If three distinct symbols occur, all three edge colors at \(j\) are those of a base triangle, which is not monochromatic.

This proves that every product triangle is nonmonochromatic, without enumeration. At \(d=1\), only the three-symbol case is possible for three distinct vertices. Labels are not quotiented by graph isomorphism.

For color \(g=jC+c\), put \(T=B^{d-j-1}\) and \(P=B^j\). A common prefix, base edge and two arbitrary tails give
\[
\#E_g=P E_c T^2.
\]
For any fixed vertex, the colored neighbors are obtained by choosing one of \(|D_c|\) permitted digits and an arbitrary tail, hence
\[
\deg_g=|D_c|T.
\]
Summing gives \(\sum_g\#E_g=\binom N2\) and \(\sum_g\deg_g=N-1\).

For the source palette, \(B=16,C=3,E_c=40,|D_c|=5\). The familiar construction consequence is \(R(3;3d)\ge16^d+1\), not a new record and not the superexponential theorem reported for Erdős 183.

## Exact rank and selection contracts

Ranks are zero-based. Large labels, ranks and counts are decimal strings on output.

For a canonical product edge \(x<y\) of color \(g=jC+c\), let \(p\) be its common-prefix integer, \(r\) the saved local-color base-edge rank, and \(u,v<T\) its tails. Its rank is
\[
((pE_c+r)T+u)T+v.
\]
The ordering is **prefix, base-edge rank, first tail, second tail**. It is not global lexicographic order on integer vertex pairs. Selection reverses this expression by successive quotient/remainder operations with \(T,T,E_c\). A decoded base pair \(a<a'\) gives
\[
x=(pB+a)T+u,\qquad y=(pB+a')T+v.
\]
The differing digits ensure \(x<y\). Reversed caller inputs to `rankEdge` are canonicalized and flagged.

For a fixed vertex, let its digit at \(j\) be \(a\), and let \(b_i\) be the \(i\)-th numerically sorted base neighbor of color \(c\). Neighbor rank \(iT+v\) selects
\[
y=(pB+b_i)T+v.
\]
This is increasing numerical order in that colored neighborhood.

The highest set bit of BigInt \(x\mathbin{\mathrm{xor}}y\) locates the first differing base-\(B\) digit. Saved powers then give the symbols and tail space. No preceding vertices or edges are expanded.

The triangle reader returns all three edge records and either `two_symbols_at_first_split`, `saved_sum_free_witness` or `three_distinct_base_colors`. The first two cases were observed in the pre-loss reader session; the third was source-inspected. The general proof does not depend on the finite query sample.

## Public API and resource limits

The plain CJS module has no imports, network, filesystem or native-process dependency. It exports:

- `XOR_RAMSEY_LIMITS`;
- `makeGreenwoodGleasonPalette()`;
- `compileXorRamseyProduct(input)`;
- `openRetainedXorRamseyProduct(snapshotOrJSONString)`.

The normalizer returns the source subgroup, ordered cosets, sorted classes, ten reduction records, counters and bibliography.

The compiler input has required `bits_per_symbol`, `difference_classes`, `dimension` and `provenance`. Provenance is a JSON object or text encoding an object, copied under a 65,536-character cap; supplying it is not source authentication. Optional `max_palette_witnesses`, `max_base_edges` and `max_product_colors` may lower the corresponding hard budgets, including to zero.

| Limit | Value |
| --- | ---: |
| Bits per base symbol | 1–6 |
| Dimension | 1–128 |
| Product vertex bits | At most 512 |
| Within-class pair witnesses | 1,953 |
| Base edges | 2,016 |
| Product color rows | 4,096 |
| Compact snapshot characters | 4,000,000 |
| Provenance characters | 65,536 |
| Decimal-string digits | 350 |
| Page rows | 1–128 |

The dimension, bit and color bounds apply together. They are implementation limits, not restrictions on the mathematical product.

A successful compiler result has status `EXACT_TRIANGLE_FREE_PRODUCT` and `summary`, `snapshot`, `work` and `snapshot_chars`. A failing XOR palette returns `NOT_TRIANGLE_FREE_PALETTE` with evaluated witnesses and violations but no snapshot. Insufficient preflight budgets return `INCOMPLETE_BUDGET` before the witness loops, base-edge enumeration or product-power construction. The final snapshot-character cap can also refuse a result. Incomplete results are not loadable; no resumable partial compiler is promised. Structural/range violations throw, and malformed JSON can produce standard JavaScript errors.

A complete snapshot has schema `commons.xor_ramsey_product/v1`. It contains the partition/class map, all XOR witnesses, base edge families, neighborhoods, provenance, powers, per-color counts and summary. The saved reader deep-copies its input, freezes the API and returns detached results.

| Reader method | Result |
| --- | --- |
| `summary()`, `source()` | Product summary or source metadata |
| `basePalette()` | Difference classes, map and base summary |
| `baseWitnessPage(options)` | Within-class XOR witness page |
| `baseEdgePage(localColor,options)` | Canonical base-edge page |
| `baseNeighbors(localColor,baseVertex)` | Sorted base neighbors |
| `colorSummary(color)`, `colorPage(options)` | Product count rows |
| `edgeColor(x,y)` | Coordinate, local/global color, symbols |
| `rankEdge(x,y)`, `selectEdge(color,rank)` | Inverse edge navigation |
| `edgePage(color,options)` | Consecutive mixed-radix edge ranks |
| `rankNeighbor(vertex,neighbor)` | Color and neighbor rank |
| `selectNeighbor(vertex,color,rank)` | Neighbor and decomposition |
| `neighborPage(vertex,color,options)` | Consecutive numeric neighbors |
| `encodeVertex(digits)`, `decodeVertex(value)` | Exactly \(d\) base-\(B\) digits and integer labels |
| `triangleCertificate([x,y,z])` | Three edge rows and local evidence |
| `snapshot()`, `statistics()` | Detached saved state or counters |

Vertex and rank inputs accept safe integer Numbers, nonnegative BigInts or canonical nonnegative decimal strings. Strings have at most 350 digits and no leading zeros except `"0"`. Vertices and selection ranks must be strictly below their family bounds; there is no modular wrapping. Colors, base labels and digit entries are Numbers. Loop edges and repeated triangle vertices are rejected.

Pages accept `{start,limit}`, defaulting to zero and 128. Start equal to family size gives an empty final page; larger starts are rejected. Pages return decimal `start` and `total`, numeric `count`, records and decimal `next_start` or final `null`.

The loader checks the saved partition, every XOR witness, complete ordered base-edge coverage, neighborhoods, powers, per-color formulas and global edge/degree identities. These are real arithmetic checks. Zero reconstruction counters do not mean zero arithmetic. The reader does not call the compiler/normalizer or re-enumerate all base pairs or product objects. Bibliographic and Git-source claims remain external custody metadata.

Compilation stores \(O(B^2+dC)\) bounded records and \(d+1\) powers, with exact integer costs depending on bit length. Pages scale with returned records plus bounded BigInt arithmetic; no bit-length-independent constant-time claim is made.

## Surviving execution observations

The one actual input used the source palette and dimension 14. The dimension came from `snapshot.summary.difference_set_size` in the accepted Singer artifact:

- repository `woahwhattheheck/commons`;
- path `research/ppl088_erdos30_singer_plane/prime13_singer_plane.json`;
- commit `8a113ba792d9a9d674a5d8b0af7f78c079f846c7`;
- blob `5561a91eddf8cfd7911641702b60cd51e308078d`.

This was a parameter choice only, not a mathematical link between the Singer plane and Ramsey coloring. Earlier field, trace, difference-set and B3 computations were not repeated.

| Pre-loss observed summary | Value |
| --- | ---: |
| Vertices | 72,057,594,037,927,936 |
| Colors | 42 |
| Unordered edges | 2,596,148,429,267,413,778,236,451,145,646,080 |
| Neighbors per vertex | 72,057,594,037,927,935 |
| Classical construction lower bound for \(R(3;42)\) | 72,057,594,037,927,937 |

The transcript printed the successful compiler status and all counters: 15 palette entries, 30 witnesses, 120 base edges, 240 neighborhood entries, 14 power steps and 42 color rows. Product vertex/edge/triangle enumerations, base-triangle enumeration, full field tables, irreducibility/primitivity tests and generator searches were zero.

A fresh reader was opened once and completed 18 queries. Its complete statistics survived in the transcript: 30 saved XOR checks, 120 saved edge checks, 240 neighborhood checks, 14 power checks, 42 color-row checks and 198 returned page rows. Compiler and normalizer reinvocations were zero. All 18 operation names and exact inputs survived and are copied to the custody record; their complete output packet did not.

Individual runtime observations were 4 ms for normalization plus compilation, 3 ms to open the reader and 9 ms for the queries. They are not benchmarks. The executed source was frozen beforehand; other dimensions, input branches and refusals were source-inspected only. No synthetic suite or post-loss mathematical execution was performed.

A consumer with a separately available complete snapshot can load it directly in connected V8:

```js
const module = {exports: {}};
new Function("module", "exports", completeModuleText)(module, module.exports);
const reader = module.exports.openRetainedXorRamseyProduct(completeSnapshot);
const row = reader.colorSummary(0);
```

This is interface documentation, not a claim that this publication supplies `completeSnapshot` or that the example was executed during recovery. The supplied custody JSON must not be used in its place.

## Publication boundary

The recovered API and the self-contained product/count/rank arguments are usable source work. The original full finite artifact remains unavailable. No release statement should call that dataset complete, describe its 18 outputs as durably retained, or imply a later rerun recovered the original bytes.

The classical construction's attribution, the source-reported solution of Erdős 183, the one observed execution and the missing run data have separate evidence. This publication makes no new Ramsey-number, asymptotic, novelty, sponsor or prize claim.
