# Rational-grid extensions for Erdős problem 143

## Result and purpose

This package constructs exact periodic indices of **individually admissible larger additions** to a supplied finite rational prefix. It supplies a bounded public BigInt implementation, complete CRT derivations, incremental append, and numeric count/rank/select operations. Appending an element consumes the saved incoming prefix and residue index; it checks only the new pairs and intersects only the new residue band.

The actual denominator-two construction is:

| Prefix numerators (all divided by 2) | Guaranteed numerator period | Admissible residues | Least larger candidate |
| --- | ---: | ---: | ---: |
| 5, 7, 12 | 420 | 72 | 17/2 |
| 5, 7, 12, 17 | 7,140 | 1,008 | 32/2 |
| 5, 7, 12, 17, 32 | 57,120 | 7,392 | 38/2 |

Only the first two displayed candidates were appended. The final five-element set is
$$
A_0=\left\{\frac52,\frac72,6,\frac{17}2,16\right\}.
$$
Its ten pair records certify the required separation for every positive integer multiplier. The final index contains all 7,392 residue classes, and its derivation retains all 8,482 joins across the five CRT steps. The final shared-gcd step also records all 21,840 incompatible input-residue/band pairs through four complete arithmetic descriptions.

The candidate set is not itself a well-separated set. For example, the saved first page contains both $87/2$ and $88/2$. Each can separately be added to $A_0$, but their mutual distance is $1/2$, violating the condition at multiplier one. A positive frequency of individually available candidates therefore does not construct an infinite set satisfying the conjecture's hypothesis.

## Original mathematical question

The [FormalConjectures statement of Erdős problem 143](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/143.lean), observed at Git blob `bcefb3101e1f6fdb87665ecd4dc0a1cfa532d58d`, defines a countably infinite set $A\subset(1,\infty)$ with
$$
|kx-y|\ge1
\qquad(x,y\in A,\ x\ne y,\ k\in\mathbb Z_{\ge1}).
$$
It asks whether
$$
\liminf_{x\to\infty}\frac{|A\cap[1,x]|}{x}=0
$$
and, in a separate stronger summability formulation, whether
$$
\sum_{a\in A}\frac1{a\log a}<\infty.
$$
Those are the recorded formal questions; the file's research-open tags do not capture all established progress. Only its definitions and statements were read, with no formal-proof audit.

### The density alternative is already a prior theorem

Dimitris Koukoulopoulos, Youness Lamzouri and Jared Duker Lichtman's 2025 [*Erdős's integer dilation approximation problem and GCD graphs*](https://arxiv.org/abs/2502.09539) proves
$
\sum_{a\in A\cap[1,x]}\frac1a=o(\log x)
$
under the separation hypothesis. See [Theorem 1 and equation (1.9), printed pages 2–3](https://arxiv.org/pdf/2502.09539). The theorem excludes positive upper logarithmic density by producing a pair at distance strictly below any prescribed positive epsilon. Here $k=1$ makes $A$ discrete, and epsilon one applies directly. This is credited prior mathematics, not an outcome of the finite computation.

The lower-natural-density conclusion follows: if $N_A(t)=|A\cap[1,t]|\ge ct$ eventually, partial summation gives
$
\sum_{a\in A\cap[1,x]}\frac1a
=\frac{N_A(x)}x+\int_1^x\frac{N_A(t)}{t^2}\,dt
\ge c\log x-O(1),
$
contradicting the displayed little-o estimate. This does **not** assert that the full natural density exists or is zero.

The cited paper resolves its condition (1.3), the logarithmic-density alternative. Its stronger reciprocal-log divergence condition (1.2) is separate; the corresponding general convergence question is not proved by that theorem or this package. The inspected arXiv record has version 1 submitted February 13, 2025, with no journal reference shown; this guide calls it a 2025 paper/preprint.

This API addresses finite extension feasibility on one fixed rational grid. It does not re-prove the prior density theorem, settle the stronger general convergence question, or construct an infinite counterexample. Its source-listed PPL014 carrier is [the problem catalogue](https://prizeproblems.org/problems/014/); the mathematical conventions are bound to the actual formal statement, and the status correction to the primary paper, rather than inferred from a short catalogue label.

### What one fixed rational grid already implies

For a primitive set of integers $B\subset\{2,3,\ldots\}$, the sum
$\sum_{b\in B}1/(b\log b)$ converges. Here primitive means no distinct member divides another. [Lichtman and Pomerance, *The Erdős conjecture for primitive sets*, Proceedings of the AMS, Series B 6 (2019), 1–14](https://math.dartmouth.edu/~carlp/bproc40.pdf), page 1, attributes this convergence to Erdős (1935); reference [9] identifies his [original article](https://doi.org/10.1112/jlms/s1-10.1.126). This package consumes that established theorem without re-proving it or claiming to have reread the original 1935 article.

If the *entire* infinite set $A$ lies on one fixed grid $(1/Q)\mathbb Z$, put $B=QA$. Exact divisibility $b'=kb$ would contradict the separation hypothesis, so $B$ is primitive. For $b\ge Q^2$,
$
\frac1{(b/Q)\log(b/Q)}
=\frac{Q}{b\log(b/Q)}
\le\frac{2Q}{b\log b}.
$
The finitely many smaller terms are harmless because every $b/Q>1$; for $Q=1$ the comparison is immediate. Thus the stronger convergence assertion already follows for a single common rational grid from the classical integer theorem. This is an elementary specialization of a credited premise, not a new convergence result.

Every finite rational prefix has a common denominator, but an arbitrary infinite real set need not lie on one fixed rational grid. The implementation makes finite extensions and their accepted records reusable; it does not remove that distinction.

## Fixed-grid input and the exact band reduction

Let $Q\ge1$ be an integer. Supply distinct numerators
$$
Q<a_1<\cdots<a_s,
$$
representing the finite set $\{a_i/Q\}$. The denominator is part of the query domain. The API keeps it unchanged: reducing a common factor in the prefix representation would change which later rational values lie on the permitted grid.

For a larger numerator $b>a_s$ (or $b>Q$ for an empty prefix), the exact extension criterion is
$$
b\bmod a_i\in[Q,a_i-Q]
\quad\text{for every }i.
\tag{1}
$$
The endpoints are **included**. The original condition permits distance exactly one, so only scaled distances strictly smaller than $Q$ are forbidden.

To prove (1), fix $a=a_i<b$ and write $b=qa+r$, where $q\ge1$ and $0\le r<a$. The nearest multiples of $a$ on either side of $b$ are $qa$ and $(q+1)a$, both with positive multipliers. Their scaled distances are $r$ and $a-r$. All positive multiples are at distance at least $Q$ precisely when both these distances are at least $Q$, which is equivalent to (1).

This also handles the reverse ordered orientation. For every $k\ge1$,
$$
kb-a\ge b-a=(q-1)a+r\ge Q.
$$
Thus one larger-versus-smaller check covers the condition in both ordered directions. There is no missing multiplier-zero restriction and no need to enumerate an unbounded list of multipliers.

The same calculation validates a finite prefix one new numerator at a time. Each saved pair witness gives its two indices, both numerators, quotient, remainder, adjacent multiples, and the two scaled distances. An invalid proposed pair records a positive multiplier with distance below $Q$.

Boundary cases follow directly:

- If $a<2Q$, the band is empty. That element can be a one-element prefix, but no larger addition on this grid is possible.
- If $a=2Q$, the band consists of the single residue $Q$.
- Empty prefixes are allowed by the finite API. This is an interface extension, not the infinite-set hypothesis of the original question.
- Duplicate input numerators are removed, and the initial input is sorted. Input records do not contribute multiplicity.
- Append requires a strictly larger numerator. It does not silently reorder an established prefix.

## Generalized CRT with every exclusion accounted for

Suppose the saved current index has a positive period $M$ and sorted canonical residues
$$
R\subset\{0,\ldots,M-1\}.
$$
For the next prefix numerator $a$, its band is $B=[Q,a-Q]\cap\mathbb Z$. Put
$$
g=\gcd(M,a),\qquad h=a/g,\qquad M'=Mh=\operatorname{lcm}(M,a).
$$
A pair of residue requirements
$$
b\equiv r\pmod M,\qquad b\equiv t\pmod a,\qquad r\in R,\ t\in B
$$
is compatible exactly when $t\equiv r\pmod g$. When $h>1$, choose
$$
v(M/g)\equiv1\pmod h,
$$
and set
$$
u=\frac{t-r}{g}v\bmod h,\qquad r'=r+Mu.
\tag{2}
$$
The quotient in (2) is an exact integer. Since $0\le r<M$ and $0\le u<h$, the output is already canonical: $0\le r'<M'$. The stored extended-Euclidean coefficients also give an explicit integer identity
$$
c(M/g)+dh=1.
$$
The residue of $c$ modulo $h$ is the saved inverse.

For $h=1$, the new modulus divides the old period. The inverse field is null and $u=0$: the operation simply filters old residues against the new band. This branch is implemented and source-inspected; the actual consumer does not exercise it.

Every compatible pair produces one residue, and every solution modulo $M'$ determines exactly one pair $(r,t)$. Hence there are no duplicate output residues, and the complete output is obtained by sorting the joined values. This is a finite generalized-CRT evaluation, with the standard CRT reasoning stated here; no priority is claimed for that method.

### Compact complete representation of incompatible pairs

The index does not iterate over every incompatible pair. It groups old residues by their class $\rho$ modulo $g$. A class record lists **every old residue index** in that group, and defines its compatible band values as
$$
t=t_0+jg,\quad 0\le j<c_\rho,
$$
where $t_0$ is the first integer in $B$ congruent to $\rho$ modulo $g$. If none exists, the first-value field is null and $c_\rho=0$.

For each listed old residue, **all remaining integers of $B$** are incompatible. Thus the record is a complete description of the excluded pairs, including their exact count $|B|-c_\rho$ per old residue. It is not a sample or a digest.

The new-residue count is known before join enumeration:
$$
\sum_\rho |R_\rho|c_\rho.
$$
This permits an honest resource stop before allocating an oversized result.

### The actual noncoprime step

Before adjoining $32/2$, the incoming numerator period is $M=7140$ with 1,008 residues. The new modulus is 32, its band is $[2,30]$, and
$$
g=4,\quad M/g=1785,\quad h=8,\quad 1785-223\cdot8=1.
$$
The inverse is therefore one modulo eight, and the outgoing period is $57120$.

| Old residue class modulo 4 | Old residues | First compatible band value | Compatible band values per old residue | Incompatible band values per old residue |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 224 | 4 | 7 | 22 |
| 1 | 224 | 5 | 7 | 22 |
| 2 | 336 | 2 | 8 | 21 |
| 3 | 224 | 3 | 7 | 22 |

The full count is
$$
224\cdot7+224\cdot7+336\cdot8+224\cdot7=7392
$$
compatible pairs, and
$$
1008\cdot29-7392=21840
$$
incompatible pairs. All 7,392 joined residues and all four complete class-index lists are retained.

## Numeric count, rank and select

Periods are in integer **numerator units**. The corresponding real period is $M/Q$. It is a guaranteed period from the construction; no minimal-period claim is made.

Let
$$
B_0=1+\max(Q,a_1,\ldots,a_s)
$$
and let $c=|R|$. For $U\ge0$, define the full-grid cumulative count
$$
F(U)=\left\lfloor\frac UM\right\rfloor c+
\#\{r\in R:r\le U\bmod M\},
$$
with $F(U)=0$ for $U<0$. The inclusive count of larger candidates through numerator $U$ is zero for $U<B_0$, and otherwise
$$
F(U)-F(B_0-1).
$$
For a valid candidate numerator $b$, its zero-based numeric rank is
$$
F(b)-F(B_0-1)-1.
$$
For a requested rank $j$, set $z=F(B_0-1)+j$. If $c>0$, selection returns
$$
b=M\left\lfloor\frac zc\right\rfloor+R[z\bmod c].
$$
This gives ordinary increasing numerical order, not a mixed-radix ordering of CRT choices.

Binary search supplies the short residue-prefix counts. Selection uses direct period arithmetic and array indexing. An empty residue list gives zero counts and an EMPTY selection result; it proves only that the **stated finite prefix has no larger extension on this specified grid**.

If $c>0$, there are infinitely many individually available values for the current finite prefix, so a finite candidate page has more rows after it. This is still not a mutually compatible infinite set.

## Public module and bounded contracts

The dependency-free CommonJS module exports:

| Export | Purpose |
| --- | --- |
| `compileRationalGridExtensionIndex(request)` | Normalize a finite input, add entries in increasing order and retain every completed CRT step |
| `openRetainedRationalGridExtensionIndex(snapshot)` | Load an explicitly supplied complete saved index with bounded structural checks |
| `GRID_EXTENSION_LIMITS` | The implementation limits below |

Exact integer inputs may be canonical unsigned decimal strings, nonnegative BigInts or nonnegative safe JavaScript integers. Floats, unsafe Numbers, signs on unsigned strings, and leading-zero decimal strings are rejected. Returned integers that may be large are decimal strings.

| Limit | Value |
| --- | ---: |
| Raw initial prefix entries / final prefix entries | 16 |
| Denominator digits | 16 |
| Prefix or append numerator digits | 32 |
| Completed period digits | 256 |
| Residues in one completed stage | 32,768 |
| Retained joins across the completed derivation | 65,536 |
| Count/lookup/rank-query numerator digits | 1,024 |
| Select/page start-rank digits | 512 |
| Candidate page size | 128 |
| Source-ID characters | 512 |

The fixed denominator must be positive, and all prefix values must exceed one. BigInt arithmetic avoids machine-integer overflow. These are explicit input/output resource bounds, not performance guarantees for every parameter combination.

A selection can produce a numerator beyond the **append** digit cap. Navigation through a saved period and enlargement of its defining prefix have different resource envelopes. A large count likewise need not fit the smaller permitted select-rank range.

### Compiler result

Call with:
```js
const result = compileRationalGridExtensionIndex({
  source_id: "my-finite-prefix",
  denominator: "2",
  prefix_numerators: ["5", "7", "12"]
});
```

The result contains `status`, the normalized `requested_prefix_numerators`, `consumed_prefix_count`, `stopped` and an `index` object.

- COMPLETE means every normalized requested prefix entry was consumed.
- INADMISSIBLE means the next entry failed the separation condition; `stopped` retains its newly checked pair rows and a concrete violating multiplier.
- CAP_STOP means the next compatible-residue derivation would exceed a period/residue/retained-join cap. It retains the planned step and prospective count without enumerating those joins.

On a stop, the returned index remains complete for **its own already consumed prefix**. It does not describe extensions of the entire unconsumed request. This distinction is visible in both the result count and the index summary. Malformed inputs and ordinary interface-bound violations throw TypeError.

### Index methods

| Method | Result |
| --- | --- |
| `summary()` | Exact stated prefix, source ID, guaranteed period, residue count and interpretation |
| `lookup(b)` / `rank(b)` | NOT_LARGER, EXCLUDED or CANDIDATE with zero-based numeric rank |
| `countThrough(U)` | Inclusive count through integer numerator U |
| `countInRange(L,U)` | Inclusive count in the numerator interval |
| `select(j)` | Candidate numerator/denominator, residue index and period quotient, or EMPTY |
| `page(start,limit)` | Consecutive numeric candidates and next rank |
| `append({numerator,source_id})` | A new complete index or an explicit unchanged-prefix stop |
| `snapshot()` | A complete JSON-compatible saved index |
| `work()` | Work performed by this invocation, distinct from the saved derivation's history |

Append returns an index object in its result. On success it is a new index; the incoming prefix and saved history remain unchanged. On failure it is the unchanged prior index, with the attempted numerator, new witnesses, and obstruction or cap plan attached. Work counters cover the attempted operation even when its mathematical state is unchanged. Returned witness/plan records are copied so caller edits do not mutate the child's retained state; this outward-copy boundary was tightened by source inspection without changing or rerunning the construction core.

The source ID is a caller-provided provenance label, not an authentication token. Every step retains the incoming source ID, prefix count, period and residue count, as well as its operation source ID. The complete old derivation is carried forward.

## Retained format and what loading establishes

A saved index records:

1. Fixed denominator, sorted prefix, final guaranteed period and every final residue.
2. All prefix-pair witnesses, indexed by their distinct ordered-by-size pair.
3. Every CRT stage, including its incoming identity/period, new numerator/band, gcd, reduced moduli, inverse coefficients, class descriptions, compatible joins and every outgoing residue.
4. The schema and caller-provided source IDs.

A join row has the compact exact layout
`[old_residue_index, band_residue, multiplier_u, output_residue]`.
Its input residue is in the previous stage's outgoing list, or the initial list `["0"]` at period one. Every row is retained in output-residue order.

The reader checks bounds, decimal shape, ascending prefix and residue lists, row lengths/references, unique pair references, class coverage of input row indices, the source/period chain, and exact agreement between each stage's outgoing list and the next stored input identity. The final list must match the last stage.

It deliberately does **not** recompute pair distances, gcds, inverse identities, compatible-class arithmetic, CRT joins, output completeness, or the source's mathematical claim. A structurally well-formed forged record is not made true by loading it. The caller must supply a trusted retained derivation; append consumes that prior mathematical premise. This prevents an incremental API from hiding a replay of the accepted old computation.

## Actual consumer and complete evidence

`rational_prefix_extensions.json` contains three complete snapshots:

| JSON location | Exact mathematical content |
| --- | --- |
| `/construction/initial/snapshot` | The three-element prefix, 3 pair witnesses and 82 cumulative joins |
| `/construction/append_17/snapshot` | The four-element prefix, 6 pair witnesses and 1,090 cumulative joins |
| `/construction/append_32/snapshot` | The five-element prefix, 10 pair witnesses and 8,482 cumulative joins |

The smaller snapshots intentionally make each accepted stage directly loadable without reconstructing an earlier index from a later one. Repeated records are storage of the same accepted premise, not repeated computation.

The first compiler returned numerator 17 at rank zero. A fresh reader consumed that saved snapshot and appended 17, performing only three new pair checks and one new CRT step. Its rank-zero candidate was 32. A second fresh reader consumed that snapshot and appended 32, performing only four new pair checks and one new CRT step.

The final fresh reader performed four navigation calls:

- Count candidates through the real bound $10^{100}$, by using numerator upper bound $2\cdot10^{100}$.
- Select rank $10^{90}$.
- Recover that selected candidate's rank.
- Export the first sixteen candidates.

The complete inclusive count was
```text
2588235294117647058823529411764705882352941176470588235294117647058823529411764705882352941176470590
```
and the selected numerator at rank $10^{90}$ was
```text
7727272727272727272727272727272727272727272727272727272727272727272727272727272727272727277
```
with denominator two. The saved rank recovery is exact. Its residue is 16,077, at index 2,082 in the final canonical list.

The first sixteen candidate numerators are
```text
38, 53, 58, 82, 87, 88, 93, 117, 122, 123, 138, 142, 158, 163, 172, 173
```
with denominator two. This page is a finite navigation result, and the remainder of the complete residue index is in the snapshots. No further greedy append was run.

### Execution accounting

| Invocation | New pair checks | New CRT steps | New compatible joins | Old pair/CRT replay |
| --- | ---: | ---: | ---: | ---: |
| Initial compiler | 3 | 3 | 82 | 0 |
| Saved append of 17 | 3 | 1 | 1,008 | 0 |
| Saved append of 32 | 4 | 1 | 7,392 | 0 |
| Final saved navigation | 0 | 0 | 0 | 0 |

The final reader structurally read five stage records, 8,482 join rows, ten pair rows and 15,874 residue entries (including the repeated final-list check), then indexed 7,392 final values. Its four queries used 38 binary-search steps and no gcd, inverse, prefix-pair or CRT construction.

Observed elapsed times were 2 ms, 7 ms, 16 ms and 31 ms for those invocations respectively. These are single connected-V8 observations with the recorded scope, preceding the outward-result copy adjustment described above; they are not statistical benchmarks or general runtime claims.

Only this input and these calls were executed. Other prefixes, empty-input/residue cases, the dividing-modulus branch, invalid/cap-stop branches and `countInRange` have source inspection only. No synthetic suite, accepted-input replay, native runtime or conjecture-proof execution was used.

## Reuse without repeating the construction

```js
// sourceText and data are the already retained module text and JSON,
// supplied by the caller. No filesystem or network operation is required.
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);

const index = loaded.exports.openRetainedRationalGridExtensionIndex(
  data.construction.append_32.snapshot
);

const nextPage = index.page("16", 12);       // New numeric navigation.
const oldState = index.snapshot();           // Complete accepted premise.
// A later deliberate extension may call index.append({...}).
// Check result.status before using its returned prefix.
```

Loading and navigation do not repeat the old constructor. A later append still must satisfy the new pair condition and the declared resource caps. The guarantee remains exact for the fixed finite prefix and grid; it does not become an assertion about the original infinite real-set question.
