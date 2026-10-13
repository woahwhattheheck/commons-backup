# Single-cube divergence image and kernel

Original work: [Commons #14999](https://github.com/woahwhattheheck/commons/issues/14999).  
Preceding dimension result: [#30995](https://github.com/woahwhattheheck/commons/pull/30995).

The one-cube case has the following exact dimensions. Here \(k\) is the
velocity degree, so the pressure degree is \(k-1\).

| \(k\) | Continuous Dirichlet velocity dimension | Discontinuous pressure ambient dimension | Actual divergence-image dimension | Divergence-kernel dimension |
| --- | ---: | ---: | ---: | ---: |
| 4 | 81 | 120 | **76** | **5** |
| 5 | 192 | 210 | **155** | **37** |

The quartic result is exceptional: substituting \(n=1\) into the
[formulas proved for \(n\ge2\)](DIVERGENCE_DIMENSION.md) would give 77 and
4, which are incorrect for a single cube. The degree-five counts happen
to agree with that substitution; their justification here is the complete
single-cube operator, not an extension of the previous proof.

[The calculator](single_cube_dimension.cjs) constructs that operator with
integer coefficients, computes a nonzero minor, and returns independent
integral kernel vectors. It checks every kernel vector against the
original matrix. Its exact arithmetic is JavaScript `BigInt`; there is
no numerical rank tolerance.

## 1. Spaces and coefficient identification

Let \(\Omega=(0,1)^3\), with the six positively oriented Freudenthal/Kuhn
tetrahedra from [kuhn.py](kuhn.py). Set

\[
V_{1,k}=\{v\in C^0(\overline\Omega)^3:
v|_T\in\mathcal P_k(T)^3,\quad v|_{\partial\Omega}=0\},
\qquad
Q_{1,k}=\operatorname{div}V_{1,k},\qquad
Z_{1,k}=\ker(\operatorname{div}|_{V_{1,k}}).
\]

The matrix has coefficients in \(\mathbb Z\). Its rank over
\(\mathbb Q\) equals its rank over \(\mathbb R\), since nonzero minors
characterize both ranks. All stated space dimensions therefore hold over
the reals, as in the preceding dimension note.

For a cell with ordered vertices \(t_0,\ldots,t_3\), write the velocity
in the normalized Bernstein basis

\[
B_\alpha^k=\frac{k!}{\alpha_0!\cdots\alpha_3!}
\lambda_0^{\alpha_0}\cdots\lambda_3^{\alpha_3},
\qquad |\alpha|=k.
\]

Associate its coefficient with the integer numerator

\[
p(T,\alpha)=\sum_{i=0}^3\alpha_i t_i,\qquad
x(T,\alpha)=p(T,\alpha)/k.
\]

These are coefficient labels, not sampled values of the polynomial.
The Bernstein trace basis on a shared face agrees up to its vertex
permutation. Thus identifying coefficients with the same physical label
is exactly the \(C^0\) condition. A label belonging to two cells lies
on their common face, edge or vertex; there is no identification of
distinct cell-interior coefficients.

Zero Dirichlet trace prescribes zero for precisely those coefficient
labels with at least one coordinate of \(p\) equal to 0 or \(k\).
The remaining labels are all of

\[
\{1,\ldots,k-1\}^3.
\]

To see coverage, order the three coordinates of a grid point. It lies in
a monotone-chain tetrahedron, whose barycentric numerators are the
successive coordinate differences and the two endpoint differences.
Those are nonnegative integers summing to \(k\). Conversely, every
Bernstein label has integer coordinates between 0 and \(k\). Therefore
there are \((k-1)^3\) free scalar coefficients and

\[
\dim V_{1,k}=3(k-1)^3.
\]

Columns list these integer triples in lexicographic order, then their
\(x,y,z\) components. Rows list the six cells, then all degree-\((k-1)\)
multi-indices \((a,b,c,k-1-a-b-c)\), with ascending nested loops over
\(a,b,c\). The full ambient pressure space has dimension
\(6\binom{k+2}{3}\). No pressure row is discarded before computing rank.

## 2. The complete integer divergence matrix

The construction reuses the geometry, coefficient labels and derivative
formula of [p4_mean_repair.py](p4_mean_repair.py), specialized to one
cube and retaining **all** pressure coefficients. The earlier two-cube
edge/mean constructor is neither invoked nor changed.

For each pressure multi-index \(|\beta|=k-1\),

\[
(\operatorname{div}v)_{T,\beta}
=k\sum_{i=0}^3\nabla\lambda_i\cdot v_{T,\beta+e_i}.
\tag{1}
\]

Every positive unit Kuhn cell has determinant 1. With
\(u=t_1-t_0,\ v=t_2-t_0,\ w=t_3-t_0\), its gradients are

\[
g_1=v\times w,\qquad g_2=w\times u,\qquad
g_3=u\times v,\qquad g_0=-g_1-g_2-g_3.
\]

Consequently \(A_k=(1/k)\operatorname{div}\), in these coefficient
bases, is an integer matrix. Boundary coefficients contribute zero;
shared coefficients contribute to their single global column.

| \(k\) | Shape of \(A_k\) | Nonzero entries | Certified rank | Certified nullity |
| --- | --- | ---: | ---: | ---: |
| 4 | \(120\times81\) | 216 | 76 | 5 |
| 5 | \(210\times192\) | 480 | 155 | 37 |

Multiplication by nonzero \(k\) does not change image dimension or
kernel. All six cells have equal volume and every normalized Bernstein
basis function of the same degree has the same integral on a cell.
The calculated column sums are exactly zero, expressing the global
zero-integral condition for a Dirichlet velocity. This condition alone
does not characterize the image: \(Q_{1,k}\) is the actual column space
of (1), not the entire ambient zero-mean pressure space.

## 3. Exact lower and upper rank witnesses

The calculator uses fraction-free elimination, scanning columns in order
and selecting the first nonzero remaining row. If \(d\) is the previous
nonzero pivot and \(p\) is the current pivot, the trailing update is

\[
R_{ij}\ \longleftarrow\
\frac{pR_{ij}-R_{ic}R_{rj}}{d}.
\tag{2}
\]

The initial \(d\) is 1. Every division in (2) is checked for zero
remainder. Row exchanges retain the original row indices. The pivot
minor identity for fraction-free elimination says that the last nonzero
pivot is the determinant of the original matrix restricted to those
selected rows and columns **in their recorded order**. In each degree,
that determinant is \(-3\), so the reported \(r\) columns are independent.

The upper rank witness is separate and explicit. For every free column
\(f\), back-substitution starts with \(v_f=1\) and all other free
coordinates zero. At an equation \(d v_p+s=0\), put
\(g=\gcd(|d|,|s|)\). Multiply the current vector by the positive integer
\(|d|/g\), then set

\[
v_p=-(s/g)\operatorname{sgn}(d).
\]

This solves the current equation exactly and preserves the already
solved homogeneous equations. Divide the completed vector by the gcd
of its coordinates to make it primitive. The code then directly
multiplies the **original** \(A_k\) by the vector and refuses any nonzero
component.

Let \(K\) contain the resulting vectors as columns and let \(F\) be the
ordered free-column list. The constructed matrices satisfy

\[
A_kK=0,\qquad K[F,:]=\operatorname{diag}(\delta_1,\ldots,\delta_{N-r}),
\qquad \delta_j>0.
\tag{3}
\]

Thus the \(N-r\) kernel vectors are independent. They prove
\(\operatorname{rank}A_k\le r\); the nonzero minor proves the reverse
inequality. This gives both dimensions without assuming row reduction
has found every kernel vector.

For degree four, \(K\) has 5 columns and 72 nonzero entries, and all
\(\delta_j=1\). For degree five, it has 37 columns and 674 nonzero
entries, and the \(\delta_j\) are 1 or 3. These integral vectors form a
basis over \(\mathbb Q\) and \(\mathbb R\); no saturated
\(\mathbb Z\)-module basis is asserted.

The following witness indices and diagonal values are the direct
calculator output. The complete sparse vectors are returned in
`kernelBasis`; each vector is a list of `[velocityColumn, integerString]`.

### Degree 4

The selected minor has order 76 and determinant `-3`.
Indices are zero-based and retain the listed order.

```json
{"pivotRows":[16,39,19,96,98,93,111,95,87,56,51,57,76,71,77,112,113,105,73,42,52,74,65,75,72,62,107,31,36,37,33,38,18,91,94,85,11,53,58,10,50,78,90,110,84,79,45,54,70,64,114,61,104,22,13,32,25,34,15,27,35,82,5,14,21,30,24,81,2,47,55,1,44,20,60,80],"pivotColumns":[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,52,53,54,55,56,57,58,59,60,61,62,63,65,66,67,69,71,72,73,74,75,76,78,79,80],"freeColumns":[51,64,68,70,77],"freeDiagonal":["1","1","1","1","1"]}
```

### Degree 5

The selected minor has order 155 and determinant `-3`.
Indices are zero-based and retain the listed order.

```json
{"pivotRows":[31,69,34,171,173,168,201,170,162,192,164,152,101,96,102,136,131,137,202,203,195,193,196,182,133,87,97,134,125,135,132,122,197,198,204,185,127,73,88,128,115,129,126,112,123,108,187,61,66,67,63,68,166,33,169,160,163,150,26,98,103,25,95,138,165,200,159,191,149,139,90,99,130,86,206,121,194,181,77,91,124,114,111,107,184,52,62,28,55,30,64,57,167,157,161,147,20,29,51,60,54,156,146,17,92,27,16,89,15,120,155,190,145,80,93,76,85,71,106,180,12,22,24,42,56,53,45,58,47,59,143,10,23,37,19,41,44,142,7,21,6,36,50,40,141,3,82,94,2,79,1,75,0,70,175],"pivotColumns":[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,45,46,47,48,49,50,51,52,53,54,55,56,58,59,60,61,62,63,64,65,66,67,68,69,71,72,73,74,75,76,77,79,80,83,85,86,87,88,91,94,95,96,97,98,99,100,101,102,103,104,106,107,108,110,111,112,114,116,119,120,121,122,123,124,126,127,128,129,131,133,134,136,138,139,142,143,144,145,146,147,148,149,150,151,153,154,155,156,158,159,160,162,165,167,168,170,171,174,175,177,179,180,181,182,183,184,186,187,189,190,191],"freeColumns":[44,57,70,78,81,82,84,89,90,92,93,105,109,113,115,117,118,125,130,132,135,137,140,141,152,157,161,163,164,166,169,172,173,176,178,185,188],"freeDiagonal":["1","1","1","1","3","3","1","1","3","3","1","1","1","1","1","3","3","1","1","1","3","3","1","1","1","1","1","3","3","1","1","3","3","1","1","1","1"]}
```

## 4. Reuse

The file has no imports or package dependencies. From the repository root:

```sh
node research/ridgway_freudenthal/single_cube_dimension.cjs
node research/ridgway_freudenthal/single_cube_dimension.cjs 4
node research/ridgway_freudenthal/single_cube_dimension.cjs 5
```

The default prints a JSON array containing both degree certificates.
The optional argument selects one degree. Degrees other than 4 or 5
are outside this calculator's scope.

The CommonJS API exports `assembleSingleCube(degree)` and
`singleCubeDimension(degree)`. The former returns the complete `BigInt`
matrix \(A_k\), ordered cells, integer node numerators and pressure
multi-indices. The latter returns JSON-compatible dimensions, pivot
indices, minor determinant, free coordinates and the complete sparse
kernel basis. Large integers are decimal strings in that certificate;
the assembler's raw matrix remains `BigInt`.

The actual image has a basis given by the columns of \(kA_k\) indexed by
`pivotColumns`. To recover any kernel vector as a continuous velocity,
decode column \(j\) as node `nodeNumerators[Math.floor(j/3)]` and component
`j % 3`, assign the listed Bernstein coefficient to every incident cell,
and assign zero to the boundary coefficients.

The recorded calculation on 4 October 2026 loaded this complete source
as a CommonJS module in native V8 and called `singleCubeDimension(4)` and
`singleCubeDimension(5)`. Both exact constructions completed, including
(2), the original-matrix products in (3), and the column-sum identity.
The Node command-line entry is provided for ordinary reuse; no operating
system or Node CLI execution is claimed for that recorded calculation.

## 5. Scope and source continuity

Translation and positive isotropic scaling preserve these dimensions:
the affine identification preserves coefficient continuity and boundary
trace, while divergence is multiplied by the reciprocal cube scale.

[The uniform-bound guide](GLOBAL_DIVERGENCE_BOUND.md#9-the-single-cube-case-and-physical-scaling)
already treated \(n=1\) by finite-dimensional existence on the actual
image. This note supplies the previously missing exact image/kernel
dimensions and a complete coefficient matrix. It does not estimate the
minimum singular value, compute a sharp inf-sup constant, or replace the
accepted \(n\ge2\) protected-map construction. The prior analytic
dimension derivation and all original local-operator attribution remain
in place.

The reused source pins were read before this continuation:

| Source | Git blob |
| --- | --- |
| `kuhn.py` | `d977af1865b03f9af0ff0262d19fc6deadcc09e6` |
| `p4_mean_repair.py` | `fe820f9ea94915df61fac3f3db85c5be1e02bf9c` |
| `DIVERGENCE_DIMENSION.md` before its finite-case link | `b6aef634cab88619e3202e9f0a2288248dd4d47c` |
| `GLOBAL_DIVERGENCE_BOUND.md` | `6ad5daadbf6d0ea36cda2990c3a09c5d2b6d6aeb` |

This is a finite-case continuation of the existing research carrier.
Scientific priority and any foundation or prize disposition remain
separate from the calculation.
