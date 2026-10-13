# Exact certificates for a fixed left support of the two-copy Werner form

The supplied two-dimensional left support has a **positive definite 32-by-32 rationally certified form**. Consequently every nonzero complex right factor in this support has strictly positive expectation against the two-copy partial transpose of the specified Werner state. The complete integer matrix, partial-trace maps, rational factorization and three evaluated directions are retained in `diagonal_shift_support_certificate.json`.

The public module constructs this type of exact certificate for one or two independent real integer left columns. A separate reader opens an identified saved result, exposes the complete form and factor rows, and evaluates new complex right factors without repeating the construction or elimination. This is a restricted continuous-family computation. It does not claim a new universal Werner-state result.

## 1. Sources and dated status

The original target is Problem 5 in Paweł Horodecki, Łukasz Rudnicki and Karol Życzkowski's [author manuscript, *Five open problems in theory of quantum information*](https://kcik.ug.edu.pl/wp-content/uploads/2021/12/2002.03233.pdf), dated December 21, 2020. It specifies the two-ququart state \(\rho(4,-1/2)\). The manuscript's historical status and award wording are not assertions about current eligibility or submission rights.

Pablo Costa Rico's [*New Partial Trace Inequalities and Distillability of Werner States*](https://arxiv.org/abs/2310.05726), *Letters in Mathematical Physics* 115, 47 (2025), [DOI 10.1007/s11005-025-01935-y](https://doi.org/10.1007/s11005-025-01935-y), gives the partial-trace criterion. The definitions and Theorem 1 were read in the [author's v3 text](https://arxiv.org/html/2310.05726v3); the journal citation is established by the current bibliographic record. The coefficient matrix is complex, has rank at most two, and need not be Hermitian or positive.

Thomas C. Fraser, Felix Huber, Balázs Pozsgay and István Vona's [July 27, 2026 preprint](https://arxiv.org/abs/2607.24309) explicitly claims the full two-copy result, including this exact state. Its [Sections 5.5–5.7](https://arxiv.org/html/2607.24309v1) also spell out the tensor and partial-trace coordinates. This package records the posted claim without certifying its proof or a peer-review status. The work below neither relies on that claimed global theorem nor treats the original target as unqualifiedly open. No exhaustive literature frontier, mathematical priority or global distillability conclusion is asserted.

## 2. State, tensor ordering and normalization

Let \(F(x\otimes y)=y\otimes x\) exchange the two four-dimensional factors. Write

\[
 \rho=\rho(4,-1/2)=\frac{I-F/2}{14},\qquad
 |\Phi_4\rangle=\frac12\sum_{a=0}^3|a,a\rangle,\qquad
 P=|\Phi_4\rangle\langle\Phi_4|.
\]

The swap's partial transpose is \(F^{T_B}=4P\), hence

\[
 \rho^{T_B}=\frac{W}{14},\qquad W=I-2P,\qquad W^2=I.
\]

The two copies originally have factors \(A_1B_1A_2B_2\). For the Schmidt-rank condition, group them as **\(A_1A_2:B_1B_2\)**. A coefficient matrix \(C\in\mathbb C^{16\times16}\) then represents

\[
 |\psi_C\rangle
 =\sum_{a,b,c,d=0}^3 C_{(a,b),(c,d)}
       |a,b\rangle_A|c,d\rangle_B,
 \qquad \|\psi_C\|^2=\|C\|_F^2.
\]

Both pair indices are row-major: \((a,b)\mapsto4a+b\). Define

\[
 (\operatorname{tr}_1 C)_{b,d}
   =\sum_{a=0}^3 C_{(a,b),(a,d)},\qquad
 (\operatorname{tr}_2 C)_{a,c}
   =\sum_{b=0}^3 C_{(a,b),(c,b)}.
\]

Tracing the first pair against \(P\) contributes
\(\|\operatorname{tr}_1 C\|_F^2/4\); the second contributes
\(\|\operatorname{tr}_2 C\|_F^2/4\); projecting both contributes
\(|\operatorname{tr}C|^2/16\). Expanding \(W\otimes W\) therefore gives

\[
 q(C)=\|C\|_F^2
      -\frac12\left(\|\operatorname{tr}_1 C\|_F^2
                        +\|\operatorname{tr}_2 C\|_F^2\right)
      +\frac14|\operatorname{tr}C|^2.
\]

The expectation against the **normalized state's** two-copy partial transpose is \(q(C)/196\). The module stores the form \(4q\), so its unnormalized-vector expectation is `form_value / 784`. For nonzero \(C\), the unit-vector expectation is

\[
 \frac{4q(C)}{784\,\|C\|_F^2}.
\]

These factors are not interchangeable. No normalization of the caller's coefficient matrix is assumed. For \(C=0\), the unnormalized expression is zero and the normalized value is undefined; the reader represents the latter by `null`.

## 3. The fixed-support reduction

Supply \(r\in\{1,2\}\) real integer columns \(U_j\in\mathbb R^{16}\), linearly independent, and let \(U\) be the resulting \(16\times r\) matrix. For arbitrary **complex** columns \(V_j\in\mathbb C^{16}\), define

\[
 C=UV^T,\qquad
 C_{(a,b),(c,d)}=\sum_{j=0}^{r-1}U_j[a,b]V_j[c,d].
\]

This formula uses the ordinary transpose: it does not conjugate \(V\). Conjugating a caller's parametrization would describe the same full family, but the numerical API convention is fixed.

Every such \(C\) has rank at most \(r\). Conversely, every matrix whose column space is contained in \(\operatorname{span}_{\mathbb C}(U_0,\ldots,U_{r-1})\) has this representation. Thus fixing \(U\) defines a complex linear family of dimension \(16r\), with the rank bound built into the parametrization. The zero matrix and lower-rank members remain allowed.

Flatten \(V\) into \(v\in\mathbb C^{16r}\) in column-block order: first \(V_0\) row-major, then \(V_1\) when present. Put

\[
 G_{ij}=\sum_{a,b}U_i[a,b]U_j[a,b],
 \qquad H_{(i,y),(j,z)}=G_{ij}\delta_{y,z}.
\]

The norm is \(v^*Hv\). The following real integer maps produce the two partial traces and the full trace:

\[
 \begin{aligned}
 (T_1v)_{b,d}&=\sum_{j,a}U_j[a,b]\,v_{j,(a,d)},\\
 (T_2v)_{a,c}&=\sum_{j,b}U_j[a,b]\,v_{j,(c,b)},\\
 tv&=\sum_{j,a,b}U_j[a,b]\,v_{j,(a,b)}.
 \end{aligned}
\]

Their respective dimensions are \(16\times16r\), \(16\times16r\), and \(1\times16r\). The exact symmetric integer matrix is

\[
 \boxed{K_U=4H-2T_1^T T_1-2T_2^T T_2+t^Tt},
 \qquad v^*K_Uv=4q(UV^T).
\]

The compiler retains \(G,T_1,T_2,t,K_U\) in full. It computes no eigenvalue approximation and samples no right-factor family. A certificate that \(K_U\succeq0\) concerns **all** complex right factors in the fixed support, including those with irrational coordinates. The rational-coordinate cap of the query API restricts executable requests, not that algebraic implication.

For a real symmetric \(K\), write \(v=x+iy\). Then \(v^*Kv=x^TKx+y^TKy\). Consequently a real rational positive-semidefinite certificate suffices for all complex \(v\). No Hermitian or positivity assumption on \(C\) is introduced.

## 4. Exact factorization and negative-direction contract

The compiler uses Schur-complement elimination in the original coordinate order. All entries are reduced BigInt rationals with positive denominators. No row permutation is needed for a positive-semidefinite matrix.

At a current pivot \(p=S_{kk}>0\), set
\(L_{ik}=S_{ik}/p\) for \(i>k\), retain \(D_k=p\), and update the remaining symmetric block by

\[
 S_{ij}\leftarrow S_{ij}-\frac{S_{ik}S_{jk}}p.
\]

This is a congruence step: it isolates the term \(p|y_k|^2\). If \(p=0\) and every remaining entry in that pivot row is zero, retain a zero diagonal term and continue. At completion,

\[
 K=L\,\operatorname{diag}(D)\,L^T,
\]

where \(L\) is unit lower triangular. Nonnegative \(D\) gives the explicit sum of squares

\[
 v^*Kv=\sum_jD_j\,|(L^Tv)_j|^2.
\]

The rank is the number of positive \(D_j\); the determinant is their full product, including any zero pivots. If every pivot is positive, \(K\) is positive definite. Since \(U\) has independent columns, \(v\ne0\) then also implies \(C\ne0\).

The implementation does not assume a global theorem to suppress an unexpected indefinite form. A negative current diagonal gives a negative coordinate direction in the remaining Schur block. If the diagonal is zero but \(a=S_{ik}\ne0\), take remaining coordinates

\[
 z_i=1,\qquad z_k=-\frac{S_{ii}+1}{2a},
\]

and all other remaining coordinates zero. Their quadratic value is exactly \(-1\). Applying the inverse transpose of the already retained unit lower triangular transformation gives a direction in the original coordinates. The negative branch records the partial factors, remaining block, direction and value, and checks that direction against the original integer form.

This is a complete failure certificate, not an assumed outcome of the present support. The actual run used the positive-definite branch only. The semidefinite and negative branches were source-inspected and remain unexercised by this consumer.

A factor direction is similarly \(x=L^{-T}e_j\). It has form value \(D_j\) and can be recovered by a triangular solve without elimination. Directions for zero \(D_j\) form a basis of the kernel over either the real or complex field.

## 5. Actual diagonal/shift support

The one new input has

\[
 U_0=\operatorname{vec}\begin{pmatrix}
 1&0&0&0\\0&2&0&0\\0&0&3&0\\0&0&0&5
 \end{pmatrix},
 \quad
 U_1=\operatorname{vec}\begin{pmatrix}
 0&1&0&0\\0&0&1&0\\0&0&0&1\\1&0&0&0
 \end{pmatrix}.
\]

The second column has its ones at \((a,a+1\bmod4)\). These are explicitly selected Commons input vectors, not an example attributed to the source papers. No earlier source dataset or accepted construction was regenerated.

The retained support Gram matrix is \(\operatorname{diag}(39,4)\), with determinant \(156\). The resulting \(K_U\) has rank \(32\), nullity \(0\), and determinant

\[
 111619095298594930035071103900982976640371707084800.
\]

All 32 pivots are positive. For completeness, their exact values in coordinate order are:

| Index | Pivot | Index | Pivot |
|---:|---:|---:|---:|
| 0 | 153 | 16 | 20743/1898 |
| 1 | 146 | 17 | 21601/1715 |
| 2 | 136 | 18 | 55836/4745 |
| 3 | 104 | 19 | 19279/1666 |
| 4 | 146 | 20 | 7014021/655486 |
| 5 | 22028/153 | 21 | 15768856/1348295 |
| 6 | 130 | 22 | 1078425/86404 |
| 7 | 98 | 23 | 35087/3102 |
| 8 | 136 | 24 | 7611843/771914 |
| 9 | 130 | 25 | 179199276/16366049 |
| 10 | 708720/5507 | 26 | 465631049/43364354 |
| 11 | 88 | 27 | 13288844/1078425 |
| 12 | 104 | 28 | 40588224/3322211 |
| 13 | 98 | 29 | 90810304/7611843 |
| 14 | 88 | 30 | 3697778200/313598733 |
| 15 | 231868/2953 | 31 | 412110972/35817773 |

Together with the saved full \(L\), these pivots certify strict positivity for every nonzero member of this 32-complex-dimensional family. They do not quantify over other left supports.

### A complex rank-two query

The fresh reader evaluates the following right factors, using \(j=1,2\) and \(a,b=1,\ldots,4\):

\[
 V_{j-1}[a-1,b-1]=(ja-b)+i(jb-a).
\]

The complete coefficient matrix and partial traces are retained. Its first two rows and columns contain the minor

\[
 \begin{pmatrix}0&-1+i\\1+i&3i\end{pmatrix},
 \qquad \det=2.
\]

Thus \(C\) has rank at least two, and the fixed-support construction gives rank at most two: its rank is exactly two. Also \(C_{0,1}\ne\overline{C_{1,0}}\), so this particular query is not Hermitian.

The exact output is:

| Quantity | Value |
|---|---:|
| \(\|C\|_F^2\) | 4720 |
| \(\|\operatorname{tr}_1C\|_F^2\) | 1668 |
| \(\|\operatorname{tr}_2C\|_F^2\) | 1404 |
| \(\operatorname{tr}C\) | \(10+10i\) |
| \(|\operatorname{tr}C|^2\) | 200 |
| \(q(C)\) | 3234 |
| \(4q(C)\) | 12936 |
| Unnormalized-vector state expectation | \(33/2\) |
| Unit-vector state expectation | \(33/9440\) |

The reader also returns every transformed coordinate and all 32 nonnegative sum-of-squares contributions. Their sum agrees exactly with \(4q(C)\).

Two other new queries recover factor directions \(L^{-T}e_{16}\) and \(L^{-T}e_{31}\):

| Direction | \(4q\) | Norm squared | Unit-vector expectation |
|---|---:|---:|---:|
| 16 | \(20743/1898\) | \(4865851/1108432\) | \(1514239/476853398\) |
| 31 | \(412110972/35817773\) | \(5460487469562294/1282912862679529\) | \(643681198583/186683332292728\) |

Their complete rational right factors, partial traces and individual factor terms are saved. These queries use the already retained factorization; no new support is compiled.

## 6. Public API

`werner_fixed_support.cjs` is dependency-free CommonJS with no I/O. Its exports are:

| Export | Purpose |
|---|---|
| `compileWernerFixedSupport(input)` | Construct the integer form and exact certificate; return a JSON-compatible snapshot. |
| `openRetainedWernerFixedSupport(snapshotOrText)` | Restore the saved mathematical records and expose queries. |
| `WERNER_FIXED_SUPPORT_LIMITS` | Read the fixed executable bounds. |

The compiler accepts:

```js
{
  left_columns: [ /* one or two arrays, each of length 16 */ ],
  provenance: "optional caller-supplied label"
}
```

Columns are real integers, each of absolute value at most 1,000,000. Entries may be safe integer Numbers, BigInts or canonical decimal strings. The columns must be independent: the compiler calculates the one- or two-column Gram determinant and refuses nonpositive results. The provenance string has a 2,048-character cap and is an annotation, not an authenticated source identity.

The fixed local dimension is four. The API does not silently generalize the normalization to another local dimension, another state parameter, another number of copies, or more than two support columns.

### Reader methods

| Method | Result |
|---|---|
| `summary()` | Dimensions, support determinant, certificate kind, rank/nullity, determinant and assurance statement. |
| `support()` | Complete left columns, retained Gram matrix and provenance label. |
| `formEntry(row,column)` | One exact integer matrix entry. |
| `formPage(start=0,count=32)` | Full rows of the retained integer form, with a continuation index. |
| `factorPage(start=0,count=32)` | PSD diagonal entries and the corresponding complete lower-triangular row prefixes. |
| `evaluate(right_columns, options)` | Exact traces, norm, form, normalization and factor contributions for a rational complex query. |
| `factorDirection(column)` | Recover \(L^{-T}e_j\) and evaluate it, without elimination. Requires a PSD certificate. |
| `kernelColumns()` | Indices of zero diagonal terms; call `factorDirection` on these for kernel basis directions. |
| `negativeDirection()` | Evaluate a saved negative witness; return `null` for a PSD certificate. |
| `snapshot()` | A detached JSON-compatible copy of the complete retained snapshot. |
| `work()` | Reader-local operation counts; construction counters stay zero. |

Every matrix or factor index is zero-based. Page starts range from zero through the total row count; counts range from zero through 32. A positive count advances a page. A start equal to the total gives an empty terminal page.

`right_columns` has the same outer shape as `left_columns`, but entries may be complex. A scalar Number, BigInt or rational string is real. A pair `[real, imaginary]` represents a complex scalar. Fractions use `"numerator/denominator"` with a positive denominator; query fractions are reduced on parsing. Decimal numerators and denominators have at most 80 digits. Decimal integer strings use canonical spelling, without a leading plus or leading zeroes.

For example, one entry may be `["2/3", "-5/7"]`. This is an exact Gaussian rational, not a floating-point approximation. Nonintegral JavaScript Numbers are refused; use a rational string.

`evaluate(..., {include_coefficients:true})` additionally returns all 256 coefficient entries of \(C\). The default avoids this expansion and evaluates the norm from the retained support Gram matrix. Complex output scalars are pairs of reduced rational strings, including `["0","0"]` for zero.

Each evaluation returns the full two 4-by-4 partial traces, full trace, their squared norms, \(4q\), \(q\), both expectation conventions and the sum-of-squares terms when present. For a PSD certificate it checks the selected partial-trace expression against the selected factor expression. A disagreement raises an error.

### Connected V8 use on the saved dataset

The following describes loading the identified source text and the complete published JSON. It is not a second execution receipt:

```js
const cellModule = { exports: {} };
new Function("module", "exports", sourceText)(
  cellModule, cellModule.exports
);

const packet = JSON.parse(dataText);
const index = cellModule.exports.openRetainedWernerFixedSupport(
  packet.snapshot
);

const status = index.summary();
const direction = index.factorDirection(31);
const firstRows = index.formPage(0, 16);
const work = index.work(); // form_constructions=0, eliminations=0
```

The source is executable text and must be identified through the repository custody appropriate to the caller. The reader itself does not fetch files or authenticate Git blobs.

## 7. Snapshot and assurance boundary

The snapshot schema is `commons.werner_fixed_support/v1`. It includes:

- The fixed tensor and normalization convention, input columns and provenance.
- The full support Gram matrix and determinant.
- Both complete partial-trace matrices and the complete full-trace row.
- Every entry of the symmetric integer form.
- Every entry of \(L\), every diagonal pivot and rank/nullity/determinant for a PSD certificate.
- A partial factorization, remaining block and explicit negative direction if that branch occurs.
- The constructor's logical operation counts.

The reader enforces matrix shapes, input bounds, exact rational formats, the retained Gram determinant's consistency and positivity, symmetry of the saved Gram and form, unit lower-triangular structure, nonnegative PSD pivots, and the saved rank/nullity summary. It reads all relevant arithmetic entries. It does not recalculate the Gram matrix from the left columns, recalculate the trace maps, reconstruct \(K_U\), or multiply the entire factorization to authenticate \(K_U=LDL^T\).

Accordingly, loading an arbitrary caller-authored packet is **not** a proof that its source, maps or factorization are genuine. The saved result's provenance is an explicit premise. The checks for selected queries compare the expression obtained from retained Gram/trace maps with the retained factor sum, and do not replace full source authentication. The completed dataset is bound to the executed source identity below.

The mathematical certificate is complete enough for an independent consumer to examine its identities. This operation preserves it rather than running a second full construction. The one actual calculation and its fresh reader are distinct from a general verifier or a proof audit of an external paper.

## 8. Bounds and work performed

The implementation accepts at most 32 complex right-factor coordinates. Internal exact integers are capped at 4,096 decimal digits. The snapshot parser accepts at most 4,000,000 characters for either serialized text or the serialization of an object input. Resource refusals are explicit; they do not become approximate answers.

The construction uses \(O(n^3)\) rational Schur work for \(n=16r\le32\), with \(O(n^2)\) factor storage. Trace-map and form assembly are bounded by these fixed dimensions. Arithmetic cost also depends on integer sizes; the logical counts below do not treat a long BigInt operation as constant physical time.

The one actual constructor performed:

| Operation | Count |
|---|---:|
| Support dot products / scalar terms | 3 / 48 |
| Trace-map assignments | 288 |
| Symmetric form entries computed | 528 |
| Partial-trace Gram products | 16,896 |
| Full-trace products | 528 |
| Exact pivot examinations | 32 |
| Factor quotients | 496 |
| Schur updates | 5,456 |
| Form constructions / eliminations | 1 / 1 |

A fresh module context opened the saved packet once and made ten public API requests: summary, support, two complete form pages, two complete factor pages, two factor directions, the complex matrix query, and the kernel-index query. The kernel list was empty.

The reader parsed 2,117 integer entries and 1,057 rational entries. Its three evaluated vectors used 192 Gram terms, 3,168 trace-map terms, 1,584 factor-transform terms and 96 sum-of-squares terms. The two triangular solves used 992 terms. It returned all 32 matrix and factor rows and performed 512 coefficient terms for the explicitly requested complex coefficient matrix. It performed **zero** support dot products, trace-map assignments, form constructions, pivot examinations, factor quotients or Schur updates.

Observed times were 10 ms for the constructor, 5 ms for opening the saved record, and 16 ms for the ten requests. These are single connected-V8 observations, not statistical benchmarks or guarantees for other inputs.

The source was syntax-parsed and its mathematical indexing, zero-pivot handling, normalization, one-column shapes, rational arithmetic and bounds were inspected before the actual run. Only the specified two-column positive-definite construction and the retained queries were executed. Other supports, single-column consumers, zero-vector queries, semidefinite/negative branches and rejection paths were not exercised. No synthetic suite or earlier accepted mathematics was replayed.

## 9. Complete artifact custody

| File | Content |
|---|---|
| `werner_fixed_support.cjs` | Exact constructor and saved-reader API. |
| `WERNER_FIXED_SUPPORT_API.md` | Conventions, reduction, certificate argument, API contract, actual output and limitations. |
| `diagonal_shift_support_certificate.json` | Complete input, snapshot, source/status provenance and all ten request/response records. |
| `README.md` | Entry point and finite-family result. |

Executed source Git blob: **7b12525be10d3532e5dfec80bd36d1caa7c91d48**, 19,732 bytes. The source remained unchanged after its execution. Complete data Git blob: **4271b18c70007c485c641112747b23c47a8bd1cf**, 147,936 bytes.

The exact conclusion is strict positivity throughout the specified left-support family. It supplies no universal left-support classification, claim about more than two copies, resolution of the general NPT bound-entanglement question, or new claim of mathematical priority.
