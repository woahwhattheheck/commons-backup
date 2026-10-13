# Dimension-six mutually unbiased bases: exact cyclotomic evidence

Status: **CLASSICAL THREE-PRODUCT-BASE CONSTRUCTION / COMPLETE EXACT CERTIFICATE / SAVED-RESULT API**.

The public module constructs the columns of
$I_6$, $H_2\otimes F_3$ and $Y_2\otimes(DF_3)$, with
$H_2=\bigl(\begin{smallmatrix}1&1\\1&-1\end{smallmatrix}\bigr)$,
$Y_2=\bigl(\begin{smallmatrix}1&1\\i&-i\end{smallmatrix}\bigr)$,
$F_3[y,j]=\omega^{yj}$ and $D[y,y]=\omega^{y^2}$.
Here $\omega=e^{2\pi i/3}$ and rows/columns use the explicit tensor order in
the guide.

These are the established three product bases in dimension six. The new
contribution is a bounded exact compiler and reusable saved-certificate
reader with complete arithmetic evidence.

| File | Purpose |
|---|---|
| [cyclotomic_mub_certificates.cjs](cyclotomic_mub_certificates.cjs) | Public constructor, generic finite cyclotomic compiler and saved-result reader |
| [EXACT_MUB_CERTIFICATE_API.md](EXACT_MUB_CERTIFICATE_API.md) | Ring proof, matrix conventions, API, bounds, complete counters and primary sources |
| [dimension6_product_triple.json](dimension6_product_triple.json) | All input columns, conjugates, 171 records, 1,026 component terms and seven reader responses |

## Exact result

Coordinates are integer polynomials in
$\zeta=e^{2\pi i/12}=(\sqrt3+i)/2$, reduced by
$\zeta^4=\zeta^2-1$. The compiler uses BigInt coefficients throughout.
It retains unnormalized columns and positive integer **squared norms**.
No square-root approximation or floating-point tolerance is used.

The complete certificate has:

- 18 positive squared norms: six ones and twelve sixes;
- 45 zero upper off-diagonal inner products within the three bases;
- 108 exact cross-basis identities
  $6|\langle v,w\rangle|^2=\|v\|^2\|w\|^2$.

After normalization, every cross-basis squared overlap is exactly $1/6$.
Every six-coordinate inner product retains its factors, reduced component
products and running partial sums.

One actual build and compilation used 1,197 ring products, 279 ring
conjugations and 171 rational reductions. A fresh reader then returned a
complete basis, five overlaps and the last twelve cross-basis records. It
made zero new inner-product, ring-product or rational-reduction calls.

For example, the reader returned $i$ and $-i$ for opposite directions of the
same saved overlap, both with normalized squared magnitude $1/6$. Between the
first Fourier and first quadratic columns it returned
$-\sqrt3+i\sqrt3$, whose squared magnitude six becomes $1/6$ after division by
the squared-norm product 36.

## API and scope

The exports are `buildDimensionSixProductTriple`,
`certifyCyclotomicMubFamily` and `openCyclotomicMubCertificate`.
The generic compiler supports dimensions two through six, twelfth-cyclotomic
integer coordinates and positive integer squared column norms. It records
finite failures for supplied families and reports unsupported norms separately.
The saved reader validates structure and selected references; it does not
authenticate or recompute the source mathematics.

The original problem asks for at least four MUBs in dimension six, or a proof
that seven cannot exist. This classical three-basis certificate resolves
neither target. The guide credits the prime-field/tensor construction and the
published theorem that a product triple cannot be extended by another MU
vector; the latter is cited source context, not a consequence independently
proved by this certificate.

Complete source identities, exact usage, orientation rules, resource limits
and the primary references are in the [API guide](EXACT_MUB_CERTIFICATE_API.md).
