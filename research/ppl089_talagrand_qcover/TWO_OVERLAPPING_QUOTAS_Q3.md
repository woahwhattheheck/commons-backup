# Three-cover theorem for two overlapping quotas

## Theorem and explicit cover

Let $E$ be a finite set, let $U,V$ be arbitrary subsets of $E$, and let $r,s$ be nonnegative integers. The sets $U$ and $V$ may overlap, coincide, contain one another or be empty. Give each coordinate $i$ an independent inclusion probability $p_i\in[0,1]$, and write

$$
D=\{A\subseteq E:|A\cap U|\le r,\ |A\cap V|\le s\},
\qquad
w(I)=\prod_{i\in I}p_i.
$$

Let $D^{(3)}$ be the sets that cannot be covered by three members of $D$, and let $B(I)=\{A\subseteq E:I\subseteq A\}$. If $\mu(D)\ge2/3$, there is an explicit family $G$ with

$$
D^{(3)}=\bigcup_{I\in G}B(I),
\qquad
\sum_{I\in G}w(I)\le\frac{27}{64}<\frac12.
$$

When $r,s\ge1$, take

$$
G={U\choose3r+1}\ \cup\ {V\choose3s+1},
$$

as a set union, counting duplicate generators once. When a capacity is zero, first remove its forced-zero coordinates from the other quota, as specified below. A requested subset size exceeding the ambient set's size gives an empty generator family.

This extends the retained disjoint-quota result to two possibly crossing quota sets. It includes arbitrary independent biases and gives the required q=3, mass-2/3 statement for this restricted family. It establishes no theorem for general overlapping quota systems, arbitrary matroids or arbitrary downsets.

## Primary convention and retained inputs

Michel Talagrand's [original problem statement](https://michel.talagrand.net/prizes/combinatorics.pdf) defines $D^{(q)}$ through failure of coverage by $q$ members of $D$ and $B(I)$ through containment of $I$. For a common inclusion probability $\delta\le1/2$, its cost is $\sum_I\delta^{|I|}$. The product weights here agree with that cost in the common-probability case and additionally allow unequal independent coordinates. The restricted-family theorem does not resolve the arbitrary-family problem.

For a finite coordinate set $B$, write

$
e_h(p_B)=\sum_{\substack{I\subseteq B\\|I|=h}}\prod_{i\in I}p_i,
$

with $e_0=1$ and $e_h=0$ when $h>|B|$. Thus $e_h$ is exactly the product weight of all $h$-element generators from $B$.

The accepted [q=3 partition note](PARTITION_MATROID_Q3.md), blob **42fc269e1cc57a4e81fd5778ea76d6c6cea5ab3b**, was delivered in [Commons #31037](https://github.com/woahwhattheheck/commons/pull/31037). We consume the following exact statements from that source.

1. **Half-mass coefficient bound.** Section 1, equation (9), gives, for every capacity $k\ge2$ and finite independent probability vector with $\Pr(S\le k)\ge1/2$,

   $$
   e_{3k+1}(p)\le\frac{2187}{5040}. \tag{H1}
   $$

   This includes insufficient coordinate support, where the weight is zero. The bound retains the threshold note's factorial estimate, blob **d555833e2524b7ede05208ff2955d520a6ae1e16**, and Hoeffding's interval comparison through the accepted proof.

2. **Clipped-scaling identities.** Section 2, equations (12)–(14), treats

   $
   q_i(t)=\min\{tp_i,1\},\qquad
   W(t)=e_{3k+1}(q(t)),\qquad
   \delta(t)=\Pr(S_t\ge k+1).
   $

   If $W(1)>0$ and $\delta(1)\le1/2$, the path has positive $W$ and $\delta$ and reaches a first finite $t_*$ with $\delta(t_*)=1/2$. Between saturation times, if $j$ coordinates have saturated, then $j\le k$ and

   $
   tW'(t)\ge(3k+1-j)W(t),\qquad
   t\delta'(t)\le(k-j+1)\delta(t). \tag{H2}
   $

   Both functions are continuous across all clamps, including simultaneous ones.

3. **Disjoint-quota logarithmic theorem.** The source's theorem (1) gives the literal $q=3$ cover for disjoint quota blocks, including capacity zero and coordinate probabilities zero or one. If the family's mass is at least 1/2, its cost is at most −log of that mass.

These are declared dependencies. Their proof bodies, earlier computations and source ownership are retained; the new argument below uses their statements and does not audit them.

## Exact combinatorial decomposition

For any integer $q\ge1$, define

$$
C_q(D)=\{X\subseteq E:X\subseteq A_1\cup\cdots\cup A_q
\text{ for some }A_1,\ldots,A_q\in D\}.
$$

We have the exact identity

$$
C_q(D)=\{X\subseteq E:|X\cap U|\le qr,\ |X\cap V|\le qs\}. \tag{1}
$$

Necessity follows by summing the q individual quota bounds. For sufficiency, partition X into its shared part T=X∩U∩V, its exclusive parts B=X∩(U\V), C=X∩(V\U), and O=X\(U∪V).

Write |T|=qa+b with 0≤b<q. Partition T into q parts T_i, b of size a+1 and the others of size a. The assumed inequalities imply |T|≤q min(r,s), so c_i=|T_i|≤min(r,s) for every color.

The remaining U-capacities r−c_i are nonnegative integers with total qr−|T|≥|B|. Fill them successively with the elements of B, obtaining parts B_i with |B_i|≤r−c_i. Independently fill capacities s−c_i with the elements of C. Those fillings do not compete: B meets only U, and C meets only V. Put O in the first part. The sets A_i=T_i∪B_i∪C_i, with O added to A_1, partition X and each satisfy both quotas. This proves (1).

The construction includes zero capacities. For example, r=0 forces X∩U=∅ in the assumed inequalities, so the shared and U-only parts are empty. Vacuous quotas, empty sets and empty color classes cause no exception.

Since D is a downset, any cover by q members may also be replaced by a partition of X: intersect each covering set with X and assign each coordinate to one containing set. Every resulting part remains in D. Thus covers with overlapping members, unions exactly equal to X, and partitions give the same covered family; empty members are allowed.

Taking the complement in (1) gives

$$
D^{(q)}=
\bigcup_{I\in {U\choose qr+1}\cup {V\choose qs+1}}B(I). \tag{2}
$$

The union of generators is a set union, so duplicates count once. Nonminimal generators may remain; neither minimality nor a disjoint generator family is needed. In particular, two crossing quota sets produce no additional mixed obstruction beyond these two cardinality thresholds. The argument does not extend this assertion to three or more arbitrary quota sets.

## A capacity-one mean bound

We require a uniform estimate for unequal Bernoulli probabilities.

**Lemma.** If $X$ is a sum of finitely many independent Bernoulli variables with probabilities in $[0,1]$, then

$$
\Pr(X\le1)\ge\frac23
\quad\Longrightarrow\quad
\mathbb E X<\frac32.
$$

The fixed-mean extremal form used here is classical: Hoeffding's Corollary 2.1 states that extrema of an arbitrary expectation of a Bernoulli sum can be attained with only one probability value other than zero and one. See Wassily Hoeffding, *On the Distribution of the Number of Successes in Independent Trials*, Annals of Mathematical Statistics 27(3) (1956), 713–721, [DOI 10.1214/aoms/1177728178](https://doi.org/10.1214/aoms/1177728178), and the [readable transcription of the 1955 author report](https://paperzz.com/doc/7419023/hoeffding--wassily;--1955-on-the-distribution-of-the-numb...). We give the short special-case reduction and the required numerical bound in full.

### Reduction at mean 3/2

A vector of mean at least $3/2$ has at least two coordinates. Fix such a finite coordinate count and maximize $F(p)=\Pr(X\le1)$ on the compact slice $\sum_i p_i=3/2$, $0\le p_i\le1$. Among the maximizers choose one with the fewest coordinates strictly between zero and one.

For two selected coordinates with probabilities $a,b$, let $Y$ be the sum of all remaining coordinates. Then

$$
F=\Pr(Y\le1)-(a+b)\Pr(Y=1)
+ab\bigl(\Pr(Y=1)-\Pr(Y=0)\bigr).
$$

Along a mean-preserving change $(a,b)\mapsto(a+t,b-t)$, the sum $a+b$ is fixed. If $a,b$ are unequal and both strictly between zero and one, maximality in both local directions forces the coefficient of $ab$ to vanish. $F$ is then constant along the full feasible segment, and one can move a coordinate to zero or one. This contradicts the minimal number of fractional coordinates. Thus all fractional coordinates at the chosen maximizer are equal.

There can be at most one deterministic success because the mean is $3/2$. Coordinates of probability zero can be omitted.

If there is one deterministic success and $n\ge1$ fractional coordinates, their common probability is $1/(2n)$. Consequently

$$
F=\left(1-\frac1{2n}\right)^n
<e^{-1/2}<\frac23.
$$

The last inequality follows from $e^{1/2}>1+1/2$.

If there is no deterministic success, there are $n\ge2$ equal fractional coordinates with common probability $3/(2n)$. Write $x=3/(2n)$. Then

$$
F=(1-x)^{n-1}\left(\frac52-x\right).
$$

For $n=2$ this is $7/16$. For $n\ge3$, $0<x\le1/2$. The inequality $\log(1-x)\le-x-x^2/2$ gives

$$
\log F\le
g(x):=\log\left(\frac52-x\right)-\frac32+\frac{x}{4}+\frac{x^2}{2}.
$$

Since

$$
g''(x)=1-\left(\frac52-x\right)^{-2}>0
\qquad(0\le x\le1/2),
$$

the maximum of $g$ on this interval is attained at an endpoint. Hence

$$
F\le\max\left\{\frac52e^{-3/2},\,2e^{-5/4}\right\}<\frac23.
$$

The strict comparisons need no decimal approximation: the first four terms of the exponential series give $e^{3/2}>67/16>15/4$ and $e^{5/4}>1289/384>3$.

Every maximizer at mean $3/2$ therefore has probability below $2/3$, and so does every point on that slice.

### Scaling from a larger mean

If the original mean $\lambda$ were at least $3/2$, multiply every inclusion probability by $3/(2\lambda)$. The new sum has mean $3/2$ and is coordinatewise stochastically no larger than $X$. Its probability of being at most one is therefore at least $\Pr(X\le1)$, contradicting the slice bound. This proves the lemma. Empty sums and means below $3/2$ require no reduction.

## Uniform cost for a positive quota

For a quota block $B$ with capacity $k\ge1$, put

$$
X_B=\sum_{i\in B}\mathbf1_{\{i\text{ selected}\}},
\quad
\delta=\Pr(X_B\ge k+1),
\quad
W=e_{3k+1}((p_i)_{i\in B}).
$$

Assume $\Pr(X_B\le k)\ge2/3$, so $\delta\le1/3$.

For $k=1$, the new lemma gives $\lambda=\sum_i p_i<3/2$. Expanding $\lambda^4$ and retaining only products with four distinct indices yields $4!e_4(p)\le\lambda^4$. Therefore

$$
W<\frac{(3/2)^4}{4!}=\frac{27}{128}.
$$

For $k\ge2$, use the retained clipped-scaling identities and half-mass bound stated above. If $W=0$ the claim is immediate, including insufficient positive support. Otherwise the path reaches $\delta(t_*)=1/2$. Between clamping points let $j$ be the number of deterministic successes. Before this boundary $j\le k$, and

$$
t\frac{d}{dt}\log\frac{W(t)}{\delta(t)^2}
\ge
(3k+1-j)-2(k-j+1)
=k-1+j\ge0.
$$

Thus $W/\delta^2$ is nondecreasing along the clipped path. Continuity preserves the comparison across its finitely many simultaneous or separate clamps. The retained boundary estimate gives

$$
W
\le W(t_*)\left(\frac{\delta}{1/2}\right)^2
\le\frac{2187}{5040}\cdot\frac49
=\frac{27}{140}
<\frac{27}{128}.
$$

This step consumes the previously proved scaling and boundary statements; it does not require independence between different quota blocks.

## Completing the cover bound

If $r,s\ge1$, $\mu(D)\ge2/3$ implies that each individual quota event has probability at least $2/3$. The two block estimates give

$$
\sum_{I\in G}w(I)
\le e_{3r+1}(p_U)+e_{3s+1}(p_V)
\le\frac{27}{64}<\frac12.
$$

Taking a set union only lowers the sum when U and V produce a duplicate generator. No independence between the two quota events is assumed. Their dependence can be arbitrary because it arises from the allowed overlap of U and V.

### Zero capacities

If $r=0$, membership in $D$ forces $A\cap U=\varnothing$, so the other quota becomes $|A\cap(V\setminus U)|\le s$. The constrained blocks are now disjoint: U of capacity zero and V\U of capacity s. Coordinates outside U∪V may be added as a vacuous block with capacity equal to its size and no generators. Apply the retained logarithmic disjoint-quota theorem to these blocks. Its literal generator family is

$$
G={U\choose1}\ \cup\ {V\setminus U\choose3s+1},
$$

with total weight at most $-\log\mu(D)\le\log(3/2)$. The case $s=0$ is symmetric. If both capacities are zero, the construction is just the singleton generators of U∪V.

For completeness, the same numerical constant covers these cases. For $t\ge0$,

$$
\frac1{1+t}\le1-t+t^2.
$$

Integrating from zero to $1/2$ gives $\log(3/2)\le5/12<27/64$. The asserted bound therefore holds for every pair of nonnegative capacities.

Zero-probability generators remain in the literal cover. A zero product weight does not remove a set-theoretic obstruction. Probability-one coordinates, empty sets, coinciding quotas and quotas exceeding block size are included in the preceding arguments.

## Attribution and scope

This note consumes the accepted threshold, clipped-scaling and disjoint-quota inputs with their original provenance. Kestrel, the October 3 threshold completion, Osprey, LATTICE-73A and Solstice retain the credits recorded by the predecessor. Hoeffding retains the fixed-mean extremal-reduction attribution.

The added proof steps are the exact two-quota decomposition, the stated capacity-one estimate, the squared-failure scaling consequence and their combination for crossing quotas. They are supplied as a complete analytic continuation within Commons, with no mathematical-priority claim. No accepted proof was audited or replayed, and no parameter census, runtime experiment, formal-kernel check, external review or sponsor submission was performed for this note.

