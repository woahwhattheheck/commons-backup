# Cubic power traces in Beatty sequences

For each integer $m\ge 6$, let $\alpha$ be the largest root of

$$
f_m(x)=x^3-mx^2+(m-1)x-1.
$$

This directory gives an explicit infinite recurrent subsequence of
$\lfloor n\alpha\rfloor$, a bounded exact-integer navigation API, and the
complete result of one $m=7$ navigation request. The proof applies to every
integer $m\ge6$; the executable API has the finite limits stated below.

[Kimberling's problem 23, “Special Numbers”](https://faculty.evansville.edu/ck6/integer/unsolved.html)
asks for a characterization of the slopes whose Beatty sequences contain a
homogeneous linearly recurrent subsequence. The result here supplies a sufficient
cubic family. It does not give that full characterization or assert priority.

## The family theorem

Define integer traces by

$$
S_0=3,\qquad S_1=m,\qquad S_2=m^2-2m+2,
$$
$$
S_{k+3}=mS_{k+2}-(m-1)S_{k+1}+S_k.
$$

Let $L=\lfloor\log_2(2m)\rfloor+1$, the binary digit length of $2m$, and set

$$
K=(m-2)L.
$$

Then, for every integer $k\ge K$,

$$
\boxed{\lfloor\alpha S_k\rfloor=S_{k+1}.}
$$

Both $S_k$ and $S_{k+1}$ are positive and strictly increasing. Thus the
Beatty indices $n_j=S_{K+j}$ and values $a_j=S_{K+j+1}$, $j\ge0$, give an
infinite subsequence. Both satisfy the same homogeneous recurrence with integer
coefficients $m,-(m-1),1$. They also satisfy
$n_{j+1}=\lfloor\alpha n_j\rfloor$.

The API reports the absolute trace index $k$. The zero-based position in the
constructed subsequence is $j=k-K$.

### 1. Three rational intervals isolate the roots

Put $M=m-1$ and $t=(M-1)/M$. Since $M\ge5$,

$$
0<\tfrac12<t<1<M<m.
$$

The following signs are exact:

| Argument $x$ | $f_m(x)$ | Sign |
|---|---:|---|
| $0$ | $-1$ | Negative |
| $1/2$ | $(2m-11)/8$ | Positive |
| $t=(M-1)/M$ | $-(2M^2-2M+1)/M^3$ | Negative |
| $M$ | $-1$ | Negative |
| $m$ | $m(m-1)-1$ | Positive |

The intermediate value theorem therefore supplies roots in the three disjoint
intervals

$$
\beta\in(0,\tfrac12),\qquad
\gamma\in(\tfrac12,t),\qquad
\alpha\in(M,m).
$$

A cubic has only three roots, so these are all its roots and they are distinct.
In particular, the two smaller conjugates lie strictly between zero and one.

The polynomial is monic with constant term $-1$. Its only possible rational
roots are $1$ and $-1$, whereas
$f_m(1)=-1$ and $f_m(-1)=-(2m+1)$. It is consequently irreducible over the
rationals. The slope $\alpha$ has degree three. In the usual terminology, it is
a totally positive Pisot unit: its other conjugates are positive and smaller
than one in absolute value.

### 2. The recurrence is a power-trace identity

For $k\ge0$, define

$$
T_k=\alpha^k+\beta^k+\gamma^k.
$$

Viète's identities give $T_0=3$, $T_1=m$, and
$T_2=m^2-2(m-1)$. Multiplying each root's polynomial equation by its $k$-th
power and adding gives

$$
T_{k+3}=mT_{k+2}-(m-1)T_{k+1}+T_k.
$$

The initial conditions agree, so $T_k=S_k$. The integral recurrence and seeds
prove integrality without evaluating the roots.

All three roots are positive. Moreover,

$$
S_{k+1}-S_k
=(\alpha-1)\alpha^k-(1-\beta)\beta^k-(1-\gamma)\gamma^k
>(m-2)(m-1)^k-2>0.
$$

This proves the positive, strictly increasing index and value sequences needed
for a subsequence.

### 3. An explicit one-sided error bound proves the floor

The dominant-root terms cancel in

$$
E_k=\alpha S_k-S_{k+1}
=(\alpha-\beta)\beta^k+(\alpha-\gamma)\gamma^k.
$$

Both summands are positive. Since $\alpha<m$ and
$0<\beta,\gamma<t<1$,

$$
0<E_k<2m\,t^k.
$$

Write $d=m-2$, so $t=d/(d+1)$. The binomial expansion gives

$$
(1+1/d)^d>1+d(1/d)=2,
\qquad t^d<\tfrac12.
$$

The inequality is strict because $d\ge4$ leaves positive higher terms.
By the definition of binary digit length, $2m<2^L$. Hence for all $k\ge K=dL$,

$$
0<E_k<2m\,t^k\le2m\,t^{dL}
<\frac{2m}{2^L}<1.
$$

Thus $S_{k+1}<\alpha S_k<S_{k+1}+1$, proving the displayed floor identity.
No decimal root estimate enters this argument.

### The general trace principle behind the construction

More generally, suppose a real algebraic integer $\alpha>1$ of degree
$d\ge2$ has all its other conjugates $\alpha_2,\ldots,\alpha_d$ in $(0,1)$. The power sums of its
conjugates are integers satisfying the homogeneous recurrence of its monic
minimal polynomial. For their trace sequence,

$$
\alpha S_k-S_{k+1}
=\sum_{i=2}^d(\alpha-\alpha_i)\alpha_i^k
$$

is positive and tends to zero. Therefore the same floor relation holds for a
sufficiently late tail. The displayed cubic family makes the root intervals and
the starting index completely explicit.

The positive-conjugate hypothesis supplies the sign as well as convergence.
This argument does not classify slopes with negative or nonreal conjugates,
all Pisot numbers, arbitrary cubic irrationals, or all real slopes.

## Exact floor certificates returned by the API

A reported pair $(n,a)$ carries integer signs of

$$
P_m(a,n)
=a^3-ma^2n+(m-1)an^2-n^3
=n^3 f_m(a/n).
$$

The API checks

$$
(m-1)n\le a,\qquad a+1\le mn,\qquad
P_m(a,n)<0<P_m(a+1,n).
$$

These checks locate $\alpha$ strictly between $a/n$ and $(a+1)/n$.
Indeed, $f'_m(m-1)=(m-1)(m-2)>0$ and
$f''_m(x)>0$ on $[m-1,m]$, so $f_m$ is strictly increasing on that interval,
where its unique largest root lies. Consequently
$a<\alpha n<a+1$ and $a=\lfloor\alpha n\rfloor$.

Each certificate includes $n,a$, both complete scaled polynomial values, the
rational endpoints and the increasing-polynomial interval. The scale is
`denominator^3`; denominators are positive. The all-index proof establishes the
family, while these finite certificates make each requested output directly
checkable by integer arithmetic.

## Navigation without generating the whole prefix

The module works in $\mathbb Z[x]/(f_m)$, where

$$
x^3=mx^2-(m-1)x+1.
$$

It caches the degree-at-most-two remainders of
$x,x^2,x^4,x^8,\ldots$. Multiplication first forms a polynomial of degree at
most four and reduces its highest terms in descending order.

If

$$
x^k\equiv c_0+c_1x+c_2x^2\pmod{f_m(x)},
$$

then

$$
S_k=3c_0+mc_1+(m^2-2m+2)c_2.
$$

Binary exponentiation supplies this remainder directly. A trace request uses
$O(\log k)$ polynomial products, and power rows and complete traces are cached
within the index. These are arithmetic-operation bounds, not constant-cost
bounds for integers of arbitrary size.

The threshold query first brackets the answer by exponentially increasing its
offset from $K$, then uses binary search. Strict monotonicity proves
minimality within the constructed subsequence. It retains every observed value
and comparison. A query does not enumerate all Beatty indices or walk all
preceding trace terms.

## Public API

The module uses CommonJS and built-in BigInt only.

```javascript
const {createCubicTraceIndex} = require('./trace_beatty_index.cjs');

const index = createCubicTraceIndex({m: 7});
const hit = index.firstValueAtLeast('1' + '0'.repeat(1000));
if (hit.status === 'found') {
  const rows = index.window(hit.k, 4);
  const complete = index.snapshot();
}
```

The delivered `m7_navigation.json` already contains this completed request.
Read that file when reusing its result.

| Operation | Result and scope |
|---|---|
| `createCubicTraceIndex({m})` | Creates one index for the fixed polynomial family; returns `m`, `first_k` and `last_k` as well as the methods below. |
| `proof()` | Returns a JSON-safe copy of the exact root intervals, signs, seeds, recurrence and explicit $K$ bound. |
| `at(k)` | Returns a copied exact Beatty pair and floor certificate at an absolute trace index. Previously built certificates are reused. |
| `firstValueAtLeast(T)` | Returns `found` with the least allowed $k$, value, predecessor and all comparisons, or `outside_index_limit` if the entire supported domain is below $T$. |
| `window(start, count)` | Returns copied certificates at consecutive absolute trace indices and records which certificates were used. |
| `snapshot()` | Returns every retained power row, trace row, finite floor certificate, query record, limit and operation count as a JSON-safe copied record. |

Thresholds must be positive canonical decimal strings or BigInt values. JavaScript
Number thresholds are deliberately not accepted, avoiding silent loss of
integer precision. Parameter $m$, indices and counts must be safe integer
Numbers within their declared bounds.

### Fixed implementation limits

| Limit | Value |
|---|---:|
| Parameter $m$ | $6$ through $128$ |
| Largest internal trace index | $8192$ |
| Constructed pair indices | $K\le k\le8191$ |
| Threshold digits | $4096$ |
| One window | $1$ through $64$ pairs |
| Retained trace records, including three seeds | $128$ |
| Retained floor certificates | $64$ |
| Threshold/window query records | $32$ |

The parameter and storage limits are API resource bounds. They do not limit
the mathematical theorem. `outside_index_limit` means that no qualifying value
was found within this API's declared index domain; it does not say that the
infinite sequence fails to reach the threshold.

A storage cap can interrupt a query after earlier values have been retained.
The query then has `status: "incomplete"` and its error in `snapshot()`. Export
that state instead of treating it as a completed answer. Invalid inputs and
unsupported indices are rejected. No provider action or external write occurs
inside this arithmetic module.

Snapshots are result records. Version 1 does not expose a restore function or
authenticate arbitrary supplied JSON as a valid mathematical result.

## Completed $m=7$ consumer

One constructor, one threshold query and one four-value window were performed.
For $m=7$,

$$
f_7(x)=x^3-7x^2+6x-1,\quad
(S_0,S_1,S_2)=(3,7,37),\quad
L=4,\quad K=20.
$$

The first constructed value at least $10^{1000}$ occurs at absolute trace
index **$k=1281$**, equivalently constructed position **$j=1261$**.
The previous value has 1000 decimal digits; the found value has 1001.
Their exact inequality is

$$
S_{1281}<10^{1000}\le S_{1282}.
$$

The four returned pairs use $k=1281,1282,1283,1284$.
Every pair passed the two exact polynomial-sign bounds.

The following prefixes and suffixes are abbreviated display aids. The JSON file
contains the complete integers.

| Integer | First 24 decimal digits | Last 24 decimal digits | Digits |
|---|---|---|---:|
| Previous value / first Beatty index $S_{1281}$ | 719685876667436502629383 | 096703991795815672143503 | 1000 |
| Found value $S_{1282}$ | 434181770256993456741567 | 916812335896936347679457 | 1001 |

The complete retained record has:

- 12 power rows, with exponents $1,2,\ldots,2048$ through powers of two;
- 27 trace rows, comprising three Newton seeds and 24 direct power-basis evaluations;
- 23 threshold probes and both complete query records;
- four full floor certificates and the four requested pairs;
- 112 polynomial products: 11 cached power squares and 101 term products;
- eight trace-cache hits and one reused floor certificate;
- zero root approximations and zero steps through a linear prefix.

All comparisons, coefficient vectors, applied power bits and full witness
integers are retained in `m7_navigation.json`. The source blob used was
`5cfb07f2a0cc2adad4085b9e83a3d6032fe0fa02`. The consumer ran once in the
connected JavaScript environment; it used no native process or provider call
for the arithmetic. It did not regenerate the published $m=6$ example or
replay the separate quadratic construction.

The actual execution covers the $m=7$ constructor, threshold navigation,
cache reuse, a four-pair window and its exact integer certificates. Other
parameters, invalid-input paths and domain/cap exhaustion have source inspection
only in this delivery. No separate test, fixture, benchmark or workflow is
included.

## Prior work and scope

Kai Wang's [“Integer Sequences for the Sum of Powers of Trigonometric Values”
(2019)](https://www.scirp.org/journal/paperinformation?paperid=92818),
DOI [10.4236/oalib.1105417](https://doi.org/10.4236/oalib.1105417), section 4,
entry $EQ(2,0)$, explicitly lists
$x^3-6x^2+5x-1$ and the trace
$3,6,26,129,650,3281,16565,\ldots$.
That sequence and the classical use of polynomial power sums are prior work.
The note supplies its own derivation of the displayed sufficient family and
its implementation; focused source searches do not establish novelty or a
complete literature survey.

The separate [quadratic construction](../ppl034_kimberling_beatty/QUADRATIC_BEATTY_API.md)
uses positive Pell units and has its own source and completed consumer.
Neither directory claims the full characterization in Kimberling's problem.
Original problem authorship and submission ownership remain with their
respective sources; this delivery makes no sponsor submission or award claim.
