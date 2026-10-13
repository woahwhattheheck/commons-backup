# Quadratic Beatty subsequences from a Pell unit

This package gives an explicit homogeneous linearly recurrent subsequence of a Beatty sequence for every quadratic irrational slope greater than one. The mathematical construction applies at every nonnegative subsequence index. The public implementation accepts bounded integer parameters and indexes terms 0 through 256 using a retained table of nine Pell-unit powers.

The actual new consumer has
$$
r=\frac{7-\sqrt{15}}2.
$$
Its increasing Beatty indices begin $2,16,126,992,\ldots$, and the corresponding values begin $3,25,197,1551,\ldots$. Both sequences satisfy
$$
T_{k+2}=8T_{k+1}-T_k.
$$
A retained-data query locates the first constructed value at least $10^{200}$ at zero-based index 223. The complete data includes every power row and all 22 terms touched by the actual navigation operations.

## 1. Problem and source boundary

Section 23, “Special Numbers,” on [Clark Kimberling's primary problem page](https://faculty.evansville.edu/ck6/integer/unsolved.html) asks which numbers $r$ have a homogeneous linearly recurrent subsequence within $\lfloor nr\rfloor$. The page does not impose the present quadratic or $r>1$ hypotheses. Those are explicit sufficient conditions for this construction. A subsequence here has strictly increasing positive integer indices and strictly increasing values; its recurrence coefficients are integers and there is no inhomogeneous term.

The Pell-unit mechanism uses classical quadratic arithmetic. [Brian Conrad's Math 154 handout, *Generalized Pell equation*](https://math.stanford.edu/~conrad/154Page/handouts/genpell.pdf), treats every positive nonsquare integer $D$, including values with square factors. It records the existence of a nontrivial norm-one unit and explains that sign or inversion can make the real unit greater than one. A fundamental norm-one unit is not required. Example 3.1 explicitly lists $4+\sqrt{15}$, the unit used here. The generalized-Pell search in that example was not repeated.

Recurrent structure in Beatty sequences has established prior literature. [Robert Silber, *A Fibonacci Property of Wythoff Pairs*, Fibonacci Quarterly 14(4) (1976), 380–384](https://www.fq.math.ca/Scanned/14-4/silber2.pdf), relates Fibonacci recurrences to successive Wythoff pairs associated with the golden-ratio Beatty sequences. That special-case construction retains its original credit. The bounded source lookup did not establish an exact published match for the whole parameterized family below. This is not a novelty finding, and no priority or exhaustive literature-frontier claim is made.

## 2. Construction theorem

Let $D$ be a positive nonsquare integer, let $u$ be an integer, let $v$ be a positive integer, and let $\varepsilon\in\{1,-1\}$. Assume
$$
r=\frac{u+\varepsilon\sqrt D}{v}>1.
$$
Choose positive integers $p,q$ with
$$
p^2-Dq^2=1.
$$
No minimality or fundamental-unit assumption is required. Put
$$
\alpha=p+q\sqrt D,\qquad
\beta=p-q\sqrt D=\alpha^{-1}.
$$
Then $\alpha>1$ and $0<\beta<1$.

Let $s=\lfloor\sqrt D\rfloor$, and choose
$$
z_0=1,\qquad
x_0=
\begin{cases}
s,&\varepsilon=1,\\
s+1,&\varepsilon=-1.
\end{cases}
$$
For $k\ge0$, define
$$
\begin{pmatrix}x_{k+1}\\z_{k+1}\end{pmatrix}
=
\begin{pmatrix}p&Dq\\q&p\end{pmatrix}
\begin{pmatrix}x_k\\z_k\end{pmatrix},
\qquad
n_k=vz_k,\qquad
a_k=uz_k+\varepsilon x_k.
$$

**Theorem.** The sequences $(n_k)$ and $(a_k)$ consist of strictly increasing positive integers, and
$$
a_k=\lfloor n_k r\rfloor
\qquad(k\ge0).
$$
Each of $x_k,z_k,n_k,a_k$ satisfies the homogeneous integer recurrence
$$
T_{k+2}=2p\,T_{k+1}-T_k.
$$

### Exact error and floor equality

Define the signed error
$$
e_k=\varepsilon(z_k\sqrt D-x_k).
$$
The floor seed for the plus branch and ceiling seed for the minus branch both give $0<e_0<1$. Nonsquareness makes both inequalities strict. The update has
$$
z_{k+1}\sqrt D-x_{k+1}
=(p-q\sqrt D)(z_k\sqrt D-x_k),
$$
so
$$
e_k=\beta^k e_0\in(0,1).
$$
On the other hand,
$$
n_kr-a_k
=\varepsilon(z_k\sqrt D-x_k)=e_k.
$$
Thus $a_k<n_kr<a_k+1$, which proves the claimed floor equality at every index. No approximate square root is involved.

### Positivity and subsequence order

The seed has $x_0,z_0>0$. The update has positive integer coefficients and $p\ge2$, so $x_k,z_k$ remain positive and $z_{k+1}>z_k$. Hence the positive integer indices $n_k=vz_k$ strictly increase. Since $r>1$, flooring $r$ times strictly increasing integer indices gives strictly increasing values. The first value is positive because $n_0=v\ge1$ and $vr>v$.

This increasing-index condition is part of the subsequence assertion. It does not say that the construction visits every term of the Beatty sequence.

### Homogeneous recurrence

The update matrix has trace $2p$ and determinant $p^2-Dq^2=1$. Direct matrix multiplication gives
$$
M^2-2pM+I=0.
$$
Consequently each coordinate of $M^k(x_0,z_0)^\mathsf T$ satisfies the stated recurrence. The integer linear combinations $n_k=vz_k$ and $a_k=uz_k+\varepsilon x_k$ satisfy it as well.

The recurrence has order at most two. The package does not claim that two is the minimal order for every allowed parameter choice.

### Why the family contains every real quadratic irrational above one

A real quadratic irrational is a root of an integer polynomial $Ar^2+Br+C$ with $A>0$ and nonsquare positive discriminant $\Delta=B^2-4AC$. The quadratic formula writes it as
$$
r=\frac{-B\pm\sqrt\Delta}{2A}.
$$
This has precisely the required parameter form, and classical Pell-unit existence supplies a positive norm-one unit for $\Delta$. Thus the construction gives a sufficient family containing every real quadratic irrational $r>1$.

This existence statement is mathematical. The public compiler requires the caller to supply an explicit Pell unit and admits only parameters within its numerical input cap. It does not find a unit for an arbitrary discriminant or furnish a general characterization for nonquadratic slopes.

## 3. Exact integer certificates for generated terms

The norm
$$
N=x_k^2-Dz_k^2=x_0^2-D
$$
is invariant, since multiplying by the Pell unit multiplies the norm by one. The compiler retains $N$, and the index uses it to produce strict integer square-gap witnesses.

For the plus branch, $x_k<z_k\sqrt D<x_k+1$. The two gaps are
$$
Dz_k^2-x_k^2=-N,\qquad
(x_k+1)^2-Dz_k^2=2x_k+1+N.
$$
For the minus branch, $x_k-1<z_k\sqrt D<x_k$, with gaps
$$
Dz_k^2-(x_k-1)^2=2x_k-1-N,\qquad
x_k^2-Dz_k^2=N.
$$
The construction theorem proves positivity of both gaps in the applicable branch. All endpoints and gaps are retained as decimal integers. Together with the full $x_k,z_k,D$ values, they give explicit finite witnesses for the square-root interval and therefore the Beatty floor equality.

Navigation derives these witnesses from the retained norm and power premises. It does not square every large coordinate or compute another integer square root. A loader that trusts an altered source table has not independently established those identities; the source boundary below is explicit.

## 4. Public module and limits

The dependency-free CommonJS module exports:

- `compileQuadraticBeattyIndex(request)`;
- `openRetainedQuadraticBeattyIndex(request)`;
- `QUADRATIC_BEATTY_LIMITS`.

There is no I/O or external arithmetic dependency. Large integers are represented internally by BigInt and externally by canonical decimal strings.

### Compiler request

```js
{
  source_id: "Caller-specified source identity",
  D: "15",
  u: "7",
  v: "2",
  sign: -1,
  p: "4",
  q: "1"
}
```

The five arithmetic parameters $D,u,v,p,q$ accept canonical decimal strings, BigInt values, or safe integer Numbers. The sign is the Number $1$ or $-1$. Leading zeros, a leading plus, negative zero strings, nonintegral Numbers, and oversized integer inputs are refused. Only $u$ may be negative; $D,v,p,q$ must be positive. Source labels are nonempty strings of at most 512 code units.

The compiler computes the integer square root, refuses a square $D$, checks the supplied Pell identity exactly, and verifies $r>1$ by integer comparisons. Writing $t=u-v$, the exact inequality is:

- for the plus branch, $t\ge0$ or $D>t^2$;
- for the minus branch, $t>0$ and $t^2>D$.

It then records the floor/ceiling seed, its norm, the first two full integer states and the recurrence coefficient $2p$. A valid result has status `CERTIFIED_QUADRATIC_BEATTY_INPUT`. The result does not certify that the supplied Pell solution is fundamental.

| Limit | Public value |
|---|---:|
| Decimal digits per integer parameter | 32 |
| Decimal digits per retained or computed output integer | 16,384 |
| Largest executable subsequence index | 256 |
| Required retained power rows | 9 |
| Largest page | 32 records |
| Source-label size | 512 code units |

Indices and page sizes use safe integer Numbers. The compiler does not accept a request to expand these caps.

The 16,384-digit arithmetic guard exceeds the needs of valid compiled parameters under the fixed index cap. In fact $\alpha<2p<2\cdot10^{32}$, while $x_0+\sqrt D<3\cdot10^{16}$. At $k\le256$, the coordinates are bounded by $3\cdot10^{16}(2\cdot10^{32})^{256}$; multiplication by $u$ or $v$ adds at most 32 decimal digits. Products and sums are also checked during execution. Loading malformed retained values cannot authorize unbounded arithmetic.

### Retained powers and random access

For each $j=0,\ldots,8$, the snapshot stores the components of
$$
\alpha^{2^j}=P_j+Q_j\sqrt D
$$
as
`[2**j, P_j, Q_j, D*Q_j]`.
The $D Q_j$ component avoids multiplying by $D$ again during every state update.

From one row to the next, the compiler uses
$$
P_{j+1}=P_j^2+Q_j(DQ_j),\quad
Q_{j+1}=2P_jQ_j,\quad
DQ_{j+1}=2P_j(DQ_j).
$$
These are eight squarings, not a traversal of all 257 admitted term indices. For a requested index $k$, the index starts from $(x_0,z_0)$ and applies exactly the saved powers selected by the binary digits of $k$. Each application uses four integer multiplications and two additions. The first two states are already retained, and a memo table prevents repeating a state calculation within one opened index.

The power rows cover the complete executable range. They are finite arithmetic data; the all-index construction theorem does not depend on the runtime cap.

## 5. Loading, navigation and trust

Opening requires a complete snapshot with the stated schema, parameters, nine consecutively indexed power rows and two consecutively indexed seed rows. The loader checks bounded canonical integer encodings, positive ranges, row shapes and complete index coverage. It rebuilds a bounded snapshot from those recognized fields rather than carrying arbitrary caller fields forward.

The loader does **not** recheck nonsquareness, the slope inequality, the Pell norm, the seed floor, the relation $D Q_j$, the power-squaring identities, the initial-state formulas or the recurrence coefficient. Source authentication and mathematical provenance remain outside loading. The recurrence, norm and monotonicity identities are trusted premises from the identified snapshot. `describe().boundary` reports those limits.

Generated term records require positive index/value coordinates and positive reported square gaps, but those consistency checks are not a fresh proof of all retained source identities.

| Method | Contract |
|---|---|
| `describe()` | Parameters, coefficient, bounded index size and source boundary |
| `term(k)` | One exact constructed term for integer $0\le k\le256$ |
| `pageTerms({start_index,limit})` | Consecutive terms, with default start 0 and default size 8 |
| `lowerBoundValue({value})` | First constructed value at least the nonnegative integer target, if found by index 256 |
| `rankValue({value})` | Membership and zero-based rank in this constructed subsequence |
| `queriedTerms()` | Every cached full term record, in increasing index order |
| `work()` | This opened index's query, cache, matrix-application and search counters |
| `snapshot()` | Detached bounded snapshot suitable for persistence |

A page may start at 257 and return an empty terminal page. Page size is at most 32; the result reports the next index or null. The two seed states are in the memo table immediately after loading.

Value targets admit at most 16,384 decimal digits. Lower-bound navigation first compares the greatest executable term to the target, then uses binary search on the proved increasing subsequence. It returns the found term, its predecessor where present and every comparison in the search trace.

If the target exceeds the term at index 256, the status is `ABOVE_INDEX_CAP`. That status leaves later indices unsearched. It is not an assertion that the infinite construction never reaches the target. Rank queries preserve that boundary; within the bracketed range they return either `MEMBER_OF_CONSTRUCTED_SUBSEQUENCE` or `NOT_IN_CONSTRUCTED_SUBSEQUENCE`. None of these operations tests membership or rank in the entire Beatty sequence.

### Connected V8 use

Acquire the public source and the complete JSON through the connected source interface, then evaluate the module:

```js
const moduleObject = {exports: {}};
new Function("module", "exports", sourceText)(
  moduleObject, moduleObject.exports
);
const {openRetainedQuadraticBeattyIndex} = moduleObject.exports;
const saved = JSON.parse(dataText);
const index = openRetainedQuadraticBeattyIndex({
  source_id: "Published minus15 power basis",
  snapshot: saved.compilation.snapshot
});
const result = index.lowerBoundValue({value: "1" + "0".repeat(200)});
const page = index.pageTerms({start_index: result.index, limit: 4});
```

These calls illustrate the public interface; their actual outputs are already saved in this delivery. A different admitted parameter set can be compiled through the public constructor using an explicit identified Pell unit.

## 6. Actual consumer: $(7-\sqrt{15})/2$

The one constructor used $D=15,u=7,v=2,\varepsilon=-1,p=4,q=1$. It checked $4^2-15=1$, computed $\lfloor\sqrt{15}\rfloor=3$ and chose the ceiling seed $(x_0,z_0)=(4,1)$. Its preserved norm is one. All nine power rows and both initial states are retained.

Here the seed itself equals the selected unit:
$$
x_k+z_k\sqrt{15}=(4+\sqrt{15})^{k+1}.
$$
The exact floor error is therefore
$$
n_kr-a_k=(4-\sqrt{15})^{k+1}\in(0,1).
$$
The interval witnesses specialize to
$$
15z_k^2-(x_k-1)^2=2x_k-2>0,\qquad
x_k^2-15z_k^2=1.
$$

| Zero-based $k$ | Beatty index $n_k$ | Value $a_k$ |
|---:|---:|---:|
| 0 | 2 | 3 |
| 1 | 16 | 25 |
| 2 | 126 | 197 |
| 3 | 992 | 1551 |
| 4 | 7810 | 12211 |
| 5 | 61488 | 96137 |
| 6 | 484094 | 756885 |
| 7 | 3811264 | 5958943 |

The actual fresh retained-data consumer returned that prefix, found the first value at least $10^{200}$, exported terms 223 through 226 and ranked the third exported value at 225. The exact threshold bracket is:

```text
a[222] = 27869281870439753174233778803151014630968239892184877110792980288896565317836908397456616492843513029308924465810290080778727455556102963036357514250239067529101156266625123036208011162858541197810037
a[223] = 219414392036732466074842761967576947121609498234669304828852006249708345189018463957937310371983016017274163900087233022066080408302200359827326793471080509701878060466438059620033498764245508206909311
n[223] = 140334648854918669038178623696482082570984484746422204470975240497523248927139187949403164564645274303570992849126427833055773943280476529121425718466567443481856324050834913693185910308461297004599552
```

It follows that $a_{222}<10^{200}\le a_{223}$. Monotonicity makes 223 the first index in this constructed subsequence meeting the threshold. This statement does not locate the first term of the full Beatty sequence above that value.

The consumer retained full records at the 22 touched indices:
$$
0,1,2,3,4,5,6,7,128,192,208,216,220,222,223,224,225,226,228,232,240,256.
$$
All comparison records, queried coordinates, exact floor endpoints/gaps, and selected power exponents are in the complete JSON.

The constructor performed one Pell norm check, two integer-square-root bisection iterations, eight power squarings and one initial-state matrix application. Its observed duration was 1 ms. The retained consumer recorded 34 term requests, 14 cache hits, 20 newly calculated states, 63 matrix applications and 18 binary-search comparisons. Its observed duration was 7 ms. Neither duration is a benchmark. The retained consumer performed zero Pell norm rechecks, zero power-table rebuilds and zero irrational square-root or floor evaluations.

No source-paper example, earlier accepted computation or alternative discriminant was run. The plus branch, signed $u$ handling and other admitted parameters are covered by the stated construction and source-level implementation; no additional consumer is claimed for them.

## Files

- `quadratic_beatty_index.cjs`: public constructor and retained navigation interface.
- `quadratic_minus15_index.json`: full construction certificate, nine power rows, source identities, all 22 touched terms and all actual query outputs.
- `QUADRATIC_BEATTY_API.md`: mathematical construction, exact API conventions, source credit and finite-runtime boundary.
- `README.md`: entry point.

The sufficient quadratic family is an all-index mathematical statement. The published run and executable caps are finite. No full real-slope characterization, minimal recurrence order, new external frontier, priority, sponsor or native-execution claim is made.
