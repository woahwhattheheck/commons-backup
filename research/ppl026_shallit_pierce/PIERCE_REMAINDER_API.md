# Fixed-modulus Pierce remainder forest

This module compiles every positive starting value below one bounded denominator into a shared remainder forest. Each record gives the first-zero length, the last positive remainder, and an exact integer identity
$$
c\,b+k\,a=d.
$$
The retained interface supports lookup, complete or paged traces, length-based rank/select, and profiles of a supplied finite set of starts. A coefficient is returned as an inverse only when the recorded terminal divisor is one.

The complete consumer fixes $a=2196$. Its 2,195 starts have maximum length 10, attained exactly at 1247 and 1324. A separate retained-data consumer profiles the 720 units already recorded in Commons #31280: 38 chains end at one and 682 end at a larger proper divisor. These are finite results for the stated denominator and accepted source list.

## 1. Exact recurrence and length convention

For integers $a\ge2$ and $1\le b<a$, define
$$
b_0=b,\qquad
q_i=\left\lfloor\frac{a}{b_i}\right\rfloor,\qquad
b_{i+1}=a-q_i b_i
$$
while $b_i>0$. Let $L=P(a,b)$ be the first index with $b_L=0$. The final exact-division transition is counted: a positive divisor $b<a$ has length one. The denominator $a$ stays fixed at every step. Updating both arguments would define a different remainder process.

This is the convention in Jeffrey Shallit's [2014 open-problems slides, slides 46–49](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf). The represented rational number is $b/a$, so the fixed $a$ is its denominator. No assumption that $a$ is prime or that $b$ is coprime to $a$ is made.

Every positive transition strictly decreases the current remainder. Consequently, the directed edges $b\mapsto a\bmod b$ form an acyclic graph on $0,\ldots,a-1$ with all paths ending at zero. The positive vertices adjacent to zero are precisely the proper positive divisors of $a$. Write
$$
d(b)=b_{L-1}
$$
for the last positive remainder. Thus $1\le d(b)<a$ and $d(b)\mid a$.

The quotient sequence also strictly increases before termination. If $q_i=\lfloor a/b_i\rfloor$, then $b_i>a/(q_i+1)$, and therefore $b_{i+1}<a/(q_i+1)$ whenever the next remainder is positive. It follows that $q_{i+1}\ge q_i+1$. The identity
$$
\frac{b_i}{a}=\frac1{q_i}\left(1-\frac{b_{i+1}}a\right)
$$
gives the nested finite Pierce expansion. All its quotients, including the final exact-division quotient, are expansion digits. The cofactor formula below uses a different product which excludes that last quotient.

## 2. Terminal-divisor coefficients

Suppose $r=a-qb>0$. The tail beginning at $r$ is already the tail of the chain beginning at $b$, so
$$
L(b)=1+L(r),\qquad d(b)=d(r).
$$
If $c(r)r\equiv d(r)\pmod a$, substituting $r\equiv-qb\pmod a$ gives
$$
c(b)\equiv-qc(r)\pmod a,\qquad
c(b)b\equiv d(b)\pmod a.
$$
At a terminal positive vertex, choose $c(b)=1$, since $d(b)=b$. Induction down the decreasing forest proves the congruence for every start. Equivalently,
$$
c(b)\equiv(-1)^{L-1}\prod_{i=0}^{L-2}q_i\pmod a,
$$
where an empty product is one. The final quotient $q_{L-1}=a/d(b)$ is deliberately excluded.

The implementation takes the representative $0\le c<a$ and sets
$$
k=\frac{d-cb}{a}.
$$
The congruence ensures that $k$ is an integer, giving the exact saved identity $cb+ka=d$. With this normalization, $-(a-1)\le k\le0$. These are coefficients for the terminal divisor; they are a greatest-common-divisor identity only when that terminal equals the initial gcd.

Since $1\le d<a$, the saved coefficient $c$ is an inverse of $b$ modulo $a$ if and only if $d=1$. Initial coprimality does not by itself force this particular chain to reach one. Therefore an empty `inverse_from_this_chain` field says that this chain's coefficient is not an inverse; it does not declare that the initial $b$ is a nonunit.

For a prime denominator, every proper positive divisor is one. In that special case every admitted start ends at one and its saved coefficient is an inverse. The general API does not assume or test primality.

### How the gcd can change

Let $g=\gcd(a,b)$ and write $a=gA$, $b=gB$ with $\gcd(A,B)=1$. At a positive transition $r=a-qb$,
$$
\gcd(a,r)=g\,\gcd(A,q).
$$
Indeed, after dividing by $g$, the gcd is $\gcd(A,A-qB)=\gcd(A,qB)=\gcd(A,q)$. Along the positive part of a chain, the gcd with the fixed denominator can therefore only grow by divisibility. Its final positive value is $d$. The zero term is excluded from this statement: $\gcd(a,0)=a$.

Scaling both $a$ and $b$ by the same positive integer scales every remainder by that integer and leaves the quotients and length unchanged. Dividing the saved congruence by the initial $g$ gives
$$
c(b)(b/g)\equiv d/g\pmod{a/g}.
$$
Because $b/g$ is invertible modulo $a/g$ and $d/g$ divides $a/g$,
$$
\gcd(c(b),a/g)=d/g.
$$
Thus the coefficient represents the normalized inverse modulo $a/g$ exactly when $d=g$. For an initial unit, this specializes to $\gcd(c(b),a)=d$; that latter equality must not be asserted for arbitrary nonunits. For a unit start, reaching one is equivalent to every nonterminal quotient remaining coprime to $a$, again excluding the final exact-division quotient.

These identities explain the output. The implementation does not run gcd calculations to obtain its forest or profile.

## 3. Compiler and exact arithmetic

The module has no dependencies or I/O and exports:

- `compilePierceRemainderForest({source_id, a})`;
- `openRetainedPierceForest({source_id, snapshot})`;
- `PIERCE_LIMITS`.

The compiler visits $b=1,\ldots,a-1$ once in increasing order. For a nonzero next remainder $r$, row $r-1$ is already available because $r<b$. Length, terminal divisor and cofactor are therefore obtained from the saved child record instead of tracing the whole chain again. The recurrence pass uses a constant number of bounded arithmetic operations per start. Length-group and terminal-histogram keys are sorted for output.

Inputs must be safe JavaScript integers with $2\le a\le65536$. The implementation uses ordinary Number arithmetic within that explicit bound. Relevant products are below $a^2\le2^{32}$; quotient, remainder, coefficient and aggregate values are exactly representable. The length sum is at most $a(a-1)/2$, since each chain is strictly decreasing. The cap is an implementation contract, not a restriction in the mathematical question.

A source label is a nonempty string of at most 512 code units. It identifies the caller's premise but does not authenticate a repository or author. Invalid inputs are refused. An admitted compiler request has a bounded complete traversal and returns `EXACT_FOREST`; there is no partial-forest success status.

The snapshot contains exactly $a-1$ rows. Row $b-1$ has columns:

| Index | Field | Meaning |
|---:|---|---|
| 0 | `next_remainder` | $a\bmod b$ |
| 1 | `quotient` | $\lfloor a/b\rfloor$ |
| 2 | `length_to_zero` | First zero index, including the final division |
| 3 | `terminal_positive` | Last positive remainder $d$ |
| 4 | `cofactor_residue` | The representative $c$ in $[0,a-1]$ |
| 5 | `modulus_coefficient` | The integer $k$ in $cb+ka=d$ |

It also retains increasing start lists grouped by length, the complete length and terminal histograms, all maximizing starts, the sum of lengths, an explicitly unreduced mean fraction, and the terminal roots. The work record distinguishes quotient divisions, remainder products, cofactor modular products and certificate divisions.

## 4. Retained navigation and trust boundary

Opening a snapshot does not repeat the compiler. The loader checks the schema, the denominator cap, all row shapes and numeric ranges, exactly $a-1$ row slots, increasing length-group keys, increasing bounded starts within each group, and a total of $a-1$ group entries.

These are structural checks. They do not recompute the quotient or remainder, establish the recurrence, verify any integer identity, authenticate the source, recompute histograms, or prove that the supplied groups partition the starts according to the saved lengths. In particular, the total group-entry count alone does not establish disjoint membership across different groups. Mathematical row contents, group membership and summary values remain trusted source premises. `describe().boundary` reports these limits explicitly.

| Operation | Input | Result and ordering |
|---|---|---|
| `describe()` | None | Detached summary and loading boundary |
| `lookup(b)` | $1\le b<a$ | Saved row fields, certificate, and conditional inverse field |
| `trace({b,limit})` | Start and at most 256 steps | Saved rows and values, ending at zero or returning `next_b` |
| `selectStart({length,rank})` | Present length and zero-based rank | Start in increasing numerical order within that length |
| `rankStart(b)` | A start | Its saved length and zero-based rank in that group |
| `pageStarts({length,start_index,limit})` | Present length, offset, at most 128 records | A numerical-order page and next offset or null |
| `profileStarts({source_id,starts})` | At most 65,535 supplied entries | Sorted distinct starts, full saved profile rows and summary |
| `snapshot()` | None | Detached JSON snapshot |

An absent requested length is an error rather than an empty synthetic group. `pageStarts` permits the start index equal to the group's size and returns an empty terminal page. Its default page size is 32. Traces default to the maximum 256 steps. A trace follows the saved decreasing edges without performing new remainder operations. If it stops at the step cap, resume from `next_b`; each page includes its initial value, so the boundary value appears in both adjacent pages. Complete traces include the final zero.

A profile treats its input as a set: it deduplicates and sorts the starts. Its rows are `[start,length_to_zero,terminal_positive,cofactor_residue,modulus_coefficient]`. An empty input is allowed and has null maximum length. Profiling does not establish whether a start is a unit or whether the input includes every unit; such interpretations require a separately identified source. It reads the saved rows and performs no remainder or gcd calculations.

### Loading the published consumer

In a connected V8 context, evaluate the public CommonJS source and parse the complete published JSON. File acquisition is separate from this dependency-free module.

```js
const moduleObject = {exports: {}};
new Function("module", "exports", sourceText)(
  moduleObject, moduleObject.exports
);
const {openRetainedPierceForest} = moduleObject.exports;
const saved = JSON.parse(dataText);
const forest = openRetainedPierceForest({
  source_id: "Published a=2196 forest",
  snapshot: saved.compilation.snapshot
});

// Each operation below consumes retained rows; it does not compile the forest.
const certificate = forest.lookup(257);
const maximumPage = forest.pageStarts({
  length: 10, start_index: 0, limit: 128
});
const trace = forest.trace({b: 257, limit: 256});
```

This example documents the interface. The actual saved consumer already exercised it; readers need not repeat that consumer to use its recorded results. To compile a distinct bounded denominator, use `compilePierceRemainderForest` with a new identified source request.

## 5. Complete finite result at denominator 2196

The one compiler call wrote all 2,195 positive-start rows. It recorded 2,195 quotient divisions, 2,195 remainder products, 2,178 cofactor modular products and 2,195 certificate quotient divisions. No gcd or primality tests were used. The observed 2 ms duration is one connected-runtime observation, not a benchmark.

| Length | All starts | Starts in the accepted unit list |
|---:|---:|---:|
| 1 | 17 | 1 |
| 2 | 106 | 13 |
| 3 | 338 | 77 |
| 4 | 552 | 159 |
| 5 | 538 | 183 |
| 6 | 358 | 142 |
| 7 | 184 | 85 |
| 8 | 79 | 45 |
| 9 | 21 | 14 |
| 10 | 2 | 1 |

The sum of lengths over all starts is 10,418, with mean $10418/2195$. Both maximizing starts, 1247 and 1324, are retained. Over the supplied 720 units, the length sum is 3,752 and the unique maximum-length start is 1247.

| Last positive remainder | All starts | Accepted unit starts |
|---:|---:|---:|
| 1 | 38 | 38 |
| 2 | 4 | 2 |
| 3 | 46 | 28 |
| 4 | 276 | 108 |
| 6 | 98 | 50 |
| 9 | 38 | 10 |
| 12 | 718 | 250 |
| 18 | 118 | 54 |
| 36 | 824 | 180 |
| 61 | 6 | 0 |
| 122 | 4 | 0 |
| 183 | 4 | 0 |
| 244 | 8 | 0 |
| 366 | 8 | 0 |
| 549 | 2 | 0 |
| 732 | 2 | 0 |
| 1098 | 1 | 0 |

All 17 positive root values are displayed in this terminal table. In particular, 38 unit starts produce chain inverses and 682 do not. This is a statement about these chains' coefficients; all 720 inputs retain their accepted unit status.

### Source custody of the unit consumer

The list comes from [Commons #31280](https://github.com/woahwhattheheck/commons/pull/31280):

- merge `e4929586e70f694872e0867907dcd42429d35391`;
- path `research/ppl009_erdos241_b3/prime13_affine_orbit_minimum.json`;
- Git blob `0c31cc4c2e3e2639bb204f4b97095132134932e6`;
- unit entries `result.classes[*].unit_members`;
- selected old optimal units `result.optimal_unit_cuts[*].unit`.

That accepted artifact records 120 disjoint six-member classes containing all 720 units modulo 2196. This continuation flattened those retained lists and consumed them as that stated premise. It did not regenerate units, test gcds, recertify their coverage, reconstruct the field, inspect triples, or repeat the affine-gap optimization. The complete input list is included in the new JSON for direct reuse.

The six selected old optimal units have the following new Pierce records. The two all-start maximizers are also shown.

| Start $b$ | Length | Terminal $d$ | Coefficient $c$ | Coefficient $k$ |
|---:|---:|---:|---:|---:|
| 257 | 5 | 12 | 564 | -66 |
| 487 | 8 | 4 | 1948 | -432 |
| 1051 | 6 | 4 | 1168 | -559 |
| 1145 | 7 | 4 | 1028 | -536 |
| 1709 | 9 | 4 | 248 | -193 |
| 1939 | 6 | 12 | 1632 | -1441 |
| 1247 | 10 | 4 | 1916 | -1088 |
| 1324 | 10 | 12 | 1992 | -1201 |

For example, the retained trace of 257 is
$$
257,\ 140,\ 96,\ 84,\ 12,\ 0,
$$
and its saved exact identity is
$$
564\cdot257-66\cdot2196=12.
$$
It provides a concrete unit whose Pierce coefficient is not an inverse. All eight complete traces are retained in the dataset. The same fresh retained-data invocation profiled the complete source list, paged both maximizing starts, ranked 257 as rank 27 among the 538 starts of length five, and selected 1247 as rank zero at length ten. None of these operations repeated the forest traversal.

## 6. Historical bounds and scope

Write
$
M(a)=\max_{1\le b<a}P(a,b)
$
for the maximum first-zero length at a fixed denominator. This is the asymptotic quantity relevant to Shallit's question.

Paul Erdős and Jeffrey O. Shallit's [*New bounds on the Length of Finite Pierce and Engel Series*, 1991, volume 3(1), pages 43–53](https://jtnb.centre-mersenne.org/articles/10.5802/jtnb.41/) uses the denominator as the second argument in its notation. Its original recurrence begins at the numerator and repeatedly reduces that fixed denominator modulo the current positive remainder. The [original paper](https://jtnb.centre-mersenne.org/article/JTNB_1991__3_1_43_0.pdf), DOI 10.5802/jtnb.41, gives
$
M(a)=O_\epsilon\!\left(a^{1/3+\epsilon}\right)
\qquad\text{for every }\epsilon>0.
$
The epsilon in this historical theorem must not be dropped when quoting the rounded exponent on an older slide. Its logarithmic lower bound is an infinitely-often statement, obtained from the source family with numerator $m$ and denominator $\operatorname{lcm}(1,\ldots,m)-1$. It is not a lower bound of order $\log a$ for every sufficiently large denominator. No source example or family was enumerated here.

Zachary Chase and Mayank Pandey's [*On the length of Pierce expansions*](https://www.math.kent.edu/~zchase/pierce.pdf), [arXiv:2211.08374v1](https://arxiv.org/abs/2211.08374), November 15, 2022, gives the stronger bound
$
M(a)\ll_\epsilon a^{1/3-2/177+\epsilon}
\qquad\text{for every }\epsilon>0
$
in Theorem 1.1. Theorem 1.2 gives
$
M(a)\gg\frac{\log a}{\log\log a}
$
for every sufficiently large denominator. This uniform lower bound has different quantifiers from the older infinitely-often logarithmic result.

In Chase and Pandey's notation, their fixed $n$ is the denominator called $a$ here. Their maximum also allows the starting numerator equal to $n$, which has length one. For denominators at least two, excluding that endpoint leaves the maximum unchanged because the admitted start one already has length one. The present API still keeps its strict $b<a$ input contract.

The 2022 source is cited as an author-posted preprint; no journal-publication status is asserted. These are the primary bounds established by the inspected sources, without an exhaustive literature-frontier claim. The finite denominator-2196 forest neither strengthens them nor supplies an effective cutoff for their asymptotic assertions. Original mathematical authorship is preserved.

## Files and limits of the result

- `pierce_remainder_forest.cjs` is the public compiler and retained-data interface.
- `pierce_2196_forest_and_unit_profile.json` contains every forest row, all length groups and histograms, the accepted input list and its exact source identity, all 720 profile rows, all eight traces, and the actual rank/select/page outputs.
- This guide supplies the convention, shared-recursion derivation, terminal-cofactor interpretation, source credit, and loading boundary.
- `README.md` is the short entry point.

The finite computation concerns one denominator. The accepted unit list is a separately identified premise. The compiler's current bound is 65,536, and no larger denominator or second forest was run here. The artifact does not solve the asymptotic length problem, establish a new external maximum or frontier, claim a new inverse algorithm, or review the proofs of the cited papers.
