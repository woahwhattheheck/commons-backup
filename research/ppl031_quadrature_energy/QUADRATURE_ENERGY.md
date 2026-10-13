# A quadrature-energy bound for Hager's nodal derivative hypothesis

For every positive integer n, let p be a real polynomial of degree at most n with p(-1)=0. Suppose that |p'(tau_i)| <= 1 at either the n Gauss–Legendre nodes or the n right-Radau nodes specified below. Then
\[
 |p(t)|\le \sqrt{2(t+1)}\le 2\qquad(-1\le t\le1).
\]
In particular the common constant-2 conclusion in Hager's displayed statement follows. The right-Radau nodal constant is exactly 2 because its last node is 1.

This note is a direct consequence of classical positive quadrature and Cauchy–Schwarz. It does not assert novelty or independently verified current literature status. It does not establish Hager's sharper Gauss nodal bound 1+tau_n. No numerical quadrature rule, matrix, example, parameter sweep or previously accepted proof was evaluated or replayed.

## Nodes and the precise remaining distinction

The [official Hager statement](https://people.clas.ufl.edu/hager/files/prize.pdf), dated September 2, 2015, takes the following two choices:

- Gauss: the n zeros of the Legendre polynomial P_n, all in (-1,1).
- Right-Radau: the n-1 zeros of the Jacobi polynomial P_(n-1)^(1,0), augmented by tau_n=1.

The PDF's opening blanket strict inequality for all nodes is inconsistent with the subsequently explicit Radau endpoint. Here the endpoint is stated explicitly. For n=1 the right-Radau rule has just the node 1.

Hager's document gives a common target 2 and a more precise Gauss target 1+tau_n. These are separate conclusions. The argument below proves the common target and the exact right-Radau nodal constant. It supplies only an interval for the sharp Gauss nodal constant.

Let
\[
 C_{\rm rule}(n)=
 \sup\{\max_i|p(\tau_i)|:\deg p\le n,\ p(-1)=0,\
                      \max_j|p'(\tau_j)|\le1\}.
\]
Then this note proves:

| Rule | Conclusion |
|---|---|
| Right-Radau | C_R(n)=2 for every n>=1 |
| Gauss | 1+tau_n <= C_G(n) <= sqrt(2(1+tau_n)) < 2 |

For -1<tau_n<1, the upper endpoint sqrt(2(1+tau_n)) is strictly greater than 1+tau_n. Therefore that Gauss interval leaves a real gap; it is not the sharper conjectured equality in disguise. The full-interval norm sup_{-1<=t<=1}|p(t)| has sharp bound 2 for either node choice, but that is different from the maximum restricted to Gauss nodes.

## Positive quadrature lemma

Let distinct nodes tau_1,...,tau_n in [-1,1] have weights w_i>0 such that
\[
 \int_{-1}^{1} f(x)\,dx=\sum_{i=1}^n w_i f(\tau_i)
 \quad\text{for every real polynomial } f,\ \deg f\le2n-2.
\]
Exactness on constants gives sum_i w_i=2. If p has degree at most n, then q=p' has degree at most n-1, so q^2 has degree at most 2n-2. Consequently
\[
 \int_{-1}^{1}q(x)^2\,dx
 =\sum_i w_iq(\tau_i)^2
 \le \sum_i w_i=2.
\]
For any t in [-1,1], the fundamental theorem of calculus and p(-1)=0 give
\[
 p(t)=\int_{-1}^{t}q(x)\,dx.
\]
Cauchy–Schwarz on [-1,t] now yields
\[
 |p(t)|^2
 \le (t+1)\int_{-1}^{t}q(x)^2\,dx
 \le (t+1)\int_{-1}^{1}q(x)^2\,dx
 \le 2(t+1).
\]
The endpoint t=-1 gives zero directly; no division by t+1 is used. Taking square roots proves the claimed bound. No property of the sign of p' between quadrature nodes is needed.

More generally, without normalizing the derivative data, the same reasoning proves
\[
 |p(t)|\le \sqrt{t+1}\,
       \left(\sum_i w_i\,p'(\tau_i)^2\right)^{1/2}.
\]
This is an exact functional inequality, not an estimate obtained from floating-point samples.

## Why both rules satisfy the lemma

Classical Gauss quadrature has positive weights and is exact through degree 2n-1; see [NIST DLMF §3.5(v)](https://dlmf.nist.gov/3.5#v), especially Eq. 3.5.20_1. Classical n-node right-Radau quadrature is positive and exact through degree 2n-2. Joulak and Beckermann's [generalized Gauss–Radau formulation](https://arxiv.org/pdf/0803.2281), Eqs. (1)–(2), uses m interior nodes and endpoint multiplicities r,s. Taking m=n-1, r=0, s=1, a=-1, b=1 and d lambda=dx gives precisely the right endpoint rule. Their degree formula becomes 2n-2, and the interior orthogonality weight becomes 1-x. The [Jacobi weight convention](https://dlmf.nist.gov/3.5.E26) identifies these interior zeros with P_(n-1)^(1,0).

For completeness, exactness and positivity also follow directly from those orthogonality conventions. Let ell_i be the cardinal Lagrange polynomial at the n nodes, and define
\[
 w_i=\int_{-1}^{1}\ell_i(x)\,dx.
\]
Interpolation makes the formula exact on all polynomials of degree at most n-1.

For Gauss, let g=P_n. Divide any f of degree at most 2n-1 as f=g h+r, with deg h<=n-1 and deg r<=n-1. Legendre orthogonality gives integral(g h)=0. The factor g vanishes at every quadrature node, so f and r have identical nodal values. Exactness for r proves exactness for f.

For right-Radau, let Q=P_(n-1)^(1,0) and g=(x-1)Q. Divide f of degree at most 2n-2 as f=g h+r, with deg h<=n-2 and deg r<=n-1. Jacobi orthogonality with weight 1-x gives
\[
 \int_{-1}^{1}g(x)h(x)\,dx
 =-\int_{-1}^{1}(1-x)Q(x)h(x)\,dx=0.
\]
Again g vanishes at all nodes, so interpolation of r proves exactness for f. When n=1, f is constant and the division step has zero quotient; the formula reduces to evaluation at 1 with weight 2.

For either rule, ell_i^2 has degree 2n-2 and nodal values delta_ij. The established exactness therefore implies
\[
 w_i=\sum_jw_j\ell_i(\tau_j)^2
     =\int_{-1}^{1}\ell_i(x)^2\,dx>0.
\]
Strict positivity follows because ell_i is a nonzero real polynomial on a nondegenerate interval. Thus the weights used in the energy argument are positive; positivity is not inferred from a numerical approximation.

## Sharpness and the Gauss gap

The polynomial p(x)=1+x has p(-1)=0 and derivative identically 1, so it is admissible for both rules. At the right-Radau node 1 its value is 2. Together with the upper bound, this proves C_R(n)=2.

For Gauss, the same polynomial gives C_G(n)>=1+tau_n. Every Gauss node satisfies tau_i<=tau_n, so the energy lemma gives C_G(n)<=sqrt(2(1+tau_n)). Because 0<1+tau_n<2, squaring shows that sqrt(2(1+tau_n))>1+tau_n. The argument leaves the sharper Gauss claim open within this note; it makes no statement about whether other literature has established it.

## Operator interpretation, without a matrix computation

For arbitrary derivative samples y_j, interpolation gives the unique q of degree at most n-1 with q(tau_j)=y_j. Integrating from -1 gives the unique admissible-degree p with p(-1)=0 and those derivative samples. Its nodal values are A y, where
\[
 A_{ij}=\int_{-1}^{\tau_i}\ell_j(x)\,dx.
\]
For each fixed row, the exact maximum over |y_j|<=1 is sum_j|A_ij|, attained by choosing the signs of that row's entries (zero entries allow either sign). The energy argument proves
\[
 \sum_j|A_{ij}|\le\sqrt{2(1+\tau_i)}.
\]
Hence \|A\|_{\infty\to\infty}\le2, with equality for right-Radau. This is an algebraic interpretation of the proved inequality. No A entries, cardinal coefficients, quadrature weights or sample signs were computed here, and the earlier thirteen-node Lebesgue/Bernstein package was not consumed or reconstructed.

## Evidence and scope

The author prize PDF and the PPL card were read directly. The independent Gauss/Radau/Jacobi source passages were qualified by the existing source scout; only their definitions, positivity and exactness statements were used. The complete argument above is elementary reasoning in this collaboration, not a report of reading or checking Hager's cited proof papers. In particular, the PDF's mention of numerical checks through n=300 is historical source text, not a computation reproduced here.

The dated source's award and open-problem wording do not establish current prize eligibility or research status. There was no sponsor contact, submission, award claim, numerical validation, formal-kernel check, benchmark or independent proof audit. This note should be cited as a classical-quadrature consequence with the stated sharper-Gauss limitation.
