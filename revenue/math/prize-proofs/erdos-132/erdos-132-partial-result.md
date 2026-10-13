# A new confirmed case of Erdős Problem #132 (Erdős–Pach, $100)

**Author:** Claude Opus 5 (Anthropic), working as an autonomous agent for Bryce Muhlnickel.
**Date:** 2026-09-06.
**Status:** *Partial result.* Erdős Problem #132 is **not** solved here. What is proved below is a
new confirmed case of the conjecture plus a general structural lemma. No prize is claimed.

---

## 0. The problem, as currently stated

From <https://www.erdosproblems.com/132> (retrieved 2026-09-06):

> Let $A\subset\mathbb R^2$ be a set of $n$ points. Must there be two distances which occur at
> least once but between at most $n$ pairs of points? Must the number of such distances
> $\to\infty$ as $n\to\infty$?
>
> Asked by Erdős and Pach. Hopf and Pannwitz proved that the largest distance between points of
> $A$ can occur at most $n$ times, but it is unknown whether a second such distance must occur.
> … In [Er97e] Erdős offers **\$100 for 'any nontrivial result'**.
> Erdős believed that for $n\ge5$ there must always exist at least two such distances. This is
> false for $n=4$ … Erdős and Fishburn proved this is true for $n=5$ and $n=6$.
> Clemen, Dumitrescu, and Liu [CDL25] have proved that there are always at least two such
> distances if $A$ is in convex position … They also prove it is true if the set $A$ is
> 'not too convex', in a specific technical sense.

Notation follows Clemen–Dumitrescu–Liu, *On the multiplicities of interpoint distances*,
arXiv:2505.04283v1 (7 May 2025) (= **[CDL]**).

* $X\subseteq\mathbb R^2$, $|X|=n$.
* $\mu(X,d)$ = number of unordered pairs of $X$ at distance $d$ (the *multiplicity* of $d$).
* $\Delta_1>\Delta_2>\dots>\Delta_m$ = the distinct distances of $X$ in decreasing order.
  $\Delta:=\Delta_1$ is the diameter; $m=m(X)$ is the number of distinct distances.
* $L_1,L_2,\dots$ = the convex layers: $L_1$ is the vertex set of $\operatorname{conv}(X)$,
  and $L_{i+1}$ is the vertex set of $\operatorname{conv}\bigl(X\setminus(L_1\cup\dots\cup L_i)\bigr)$.
  Every point of $X$ lies in exactly one layer; write $\lambda(x)=i$ when $x\in L_i$.
* $\ell_i:=|L_i|$.

**Conjecture 1.1 ([CDL], after Erdős).** *For $n\ge5$ and $X\subseteq\mathbb R^2$ with $|X|=n$, it
is not possible that every distance except the diameter occurs more than $n$ times.*

Call $X$ a **counterexample set** if $|X|=n\ge5$ and $\mu(X,d)>n$ for every distance $d\ne\Delta$.

**Known.**

* (Hopf–Pannwitz) $\mu(X,\Delta)\le n$.
* (Erdős–Fishburn) Conjecture 1.1 holds for $n=5,6$; open for $n\ge7$.
* ([CDL], Thm 1.2) Conjecture 1.1 holds when $X$ is in convex position ($\ell_1=n$).
* ([CDL], Thm 1.3) $\mu(X,\Delta_2)\le\min\{\tfrac32(\ell_1+\ell_2),\ \tfrac43\ell_1+2\ell_2,\ 2\ell_1+\ell_2\}$;
  hence Conjecture 1.1 holds whenever that minimum is $\le n$.
* ([CDL], Constr. 1) $\mu(X,\Delta_2)$ can exceed $n$, so $\Delta_2$ alone cannot settle the conjecture.
* (Altman) $N$ points in convex position determine $\ge\lfloor N/2\rfloor$ distinct distances;
  if $N$ is odd and exactly $\lfloor N/2\rfloor$ are determined, the set is a regular $N$-gon $R_N$.
* (Fishburn) If $N\ge8$ is even and $N$ points in convex position determine exactly $N/2$ distances,
  the set is $R_N$ or $R_{N+1}^-$ (a regular $(N+1)$-gon minus one vertex).

**The gap this note attacks.** With $\ell_1=n-1,\ \ell_2=1$ (exactly one point of $X$ is not a hull
vertex) the [CDL] bound reads

$$\min\Bigl\{\tfrac32 n,\ \tfrac43(n-1)+2,\ 2(n-1)+1\Bigr\}=\tfrac{4n+2}{3},$$

and $\tfrac{4n+2}{3}\le n$ never holds. So **[CDL] Theorem 1.3 covers no set with $\ell_1=n-1$**,
and Theorem 1.2 covers only $\ell_1=n$. This case is settled below for odd $n$.

---

## 1. A structural lemma: the $k$-th largest distance lives in the first $k$ convex layers

**Theorem A.** *Let $X\subseteq\mathbb R^2$ be finite with $|X|\ge2$, let $\Delta_1>\dots>\Delta_m$
be its distinct distances and $\lambda(\cdot)$ its convex-layer index. If $p,q\in X$ satisfy
$\operatorname{dist}(p,q)=\Delta_k$, then*

$$\lambda(p)+\lambda(q)\ \le\ k+1 .$$

*Proof.* Strong induction on $k$.

**Claim (\*).** *Let $\operatorname{dist}(p,q)=\Delta_k$, $i=\lambda(p)$, and suppose the theorem
holds for every $k'<k$. Then $\lambda(q)\le\max\{1,\,k+1-i\}$.*

Put $r:=\max\{0,\,k-i\}$.

First, *every $y\in X$ with $\operatorname{dist}(p,y)>\Delta_k$ satisfies $\lambda(y)\le r$.*
Indeed such a $y$ has $\operatorname{dist}(p,y)=\Delta_s$ with $s<k$, so the inductive hypothesis
gives $\lambda(p)+\lambda(y)\le s+1\le k$, whence $\lambda(y)\le k-i\le r$. (If $k-i\le0$ this
would force $\lambda(y)\le0$, which is impossible, so no such $y$ exists and the statement is
vacuously true.)

Consequently, with $X_{r+1}:=X\setminus(L_1\cup\dots\cup L_r)$,

$$X_{r+1}\subseteq \overline B(p,\Delta_k),$$

the closed disc of radius $\Delta_k$ about $p$.

If $\lambda(q)\le r$ we are done, since $r\le\max\{1,k+1-i\}$. Otherwise $q\in X_{r+1}$. Because
$\operatorname{dist}(p,q)=\Delta_k$, the point $q$ lies on the boundary circle
$\partial B(p,\Delta_k)$. The tangent line to that circle at $q$ is a supporting line of
$\overline B(p,\Delta_k)$ meeting the closed disc **only** at $q$; hence it meets $X_{r+1}$ only at
$q$, so $q$ is a vertex of $\operatorname{conv}(X_{r+1})$. By definition of the convex layers,
$\lambda(q)=r+1=\max\{1,\,k+1-i\}$. This proves (\*).

Now fix $k\ge1$ and assume the theorem for all $k'<k$ (vacuous when $k=1$). Let
$\operatorname{dist}(p,q)=\Delta_k$, $i=\lambda(p)$, $j=\lambda(q)$. Applying (\*) in both
directions,

$$j\le\max\{1,\,k+1-i\},\qquad i\le\max\{1,\,k+1-j\}.$$

Suppose $i+j>k+1$. Then $k+1-i<j$, so the first inequality forces $j\le1$, i.e. $j=1$; symmetrically
$i=1$. Then $i+j=2>k+1$ gives $k<1$, contradicting $k\ge1$. Hence $i+j\le k+1$. $\blacksquare$

**Remarks.**

* $k=1$ gives $\lambda(p)=\lambda(q)=1$: diameter pairs lie in $L_1$.
* $k=2$ gives $\lambda(p)+\lambda(q)\le3$: a $\Delta_2$-pair meets $L_1$, and its other endpoint is in
  $L_1\cup L_2$. These two cases are exactly [Ve, Prop. 1] and [CDL, Obs. (2)]; Theorem A is the
  common generalisation to all $k$.
* $k=3$ gives: a $\Delta_3$-pair is of type $L_1L_1$, $L_1L_2$, $L_1L_3$ or $L_2L_2$ — in particular a
  $\Delta_3$-edge touching $L_3$ has its other endpoint in $L_1$.
* **Scope note.** Vesztergombi's papers [22–24] of [CDL] were not accessible to me; the $k$-general
  statement may already be known to her. The proof above is self-contained either way.

**Corollary B.** *For every $k\le m$, put $Y_k:=L_1\cup\dots\cup L_k$. Then
$\mu(X,\Delta_s)=\mu(Y_k,\Delta_s)$ for all $s\le k$, and $\Delta_1,\dots,\Delta_k$ are exactly the
$k$ largest distances of $Y_k$.*

*Proof.* For $s\le k$ a $\Delta_s$-pair has $\lambda(p)+\lambda(q)\le s+1\le k+1$ with both terms
$\ge1$, so $\lambda(p),\lambda(q)\le k$ and the pair lies inside $Y_k$; conversely $Y_k\subseteq X$.
Every distance of $Y_k$ is a distance of $X$, hence $\le\Delta_1$, and $\Delta_1,\dots,\Delta_k$ all
occur in $Y_k$, so they are its $k$ largest distances. $\blacksquare$

---

## 2. Three elementary lemmas

**Lemma C (counting).** *If $X$ is a counterexample set with $|X|=n$, then*

$$m(X)\ \le\ \lfloor n/2\rfloor .$$

*Proof.* $\binom n2=\sum_d\mu(X,d)\ \ge\ \mu(X,\Delta)+(m-1)(n+1)\ \ge\ 1+(m-1)(n+1)$, so
$(m-1)(n+1)\le\frac{n(n-1)}2-1=\frac{(n-2)(n+1)}2$, i.e. $m-1\le\frac{n-2}2$, i.e. $m\le n/2$.
As $m$ is an integer, $m\le\lfloor n/2\rfloor$. $\blacksquare$

(This is the engine behind [CDL]'s convex case: Altman's lower bound $\lfloor n/2\rfloor$ meets
Lemma C exactly, which is why convex counterexamples would have to be Altman-extremal.)

**Lemma D (diameter endpoints are hull vertices).** *If $\operatorname{dist}(p,q)=\Delta(X)$ then
$p,q\in L_1$.*

*Proof.* This is Theorem A with $k=1$; directly: if $p\notin L_1$ then $p=\sum_i\lambda_ix_i$ is a
convex combination of points $x_i\in X\setminus\{p\}$ with $\lambda_i>0$, and
$\Delta=|q-p|\le\sum_i\lambda_i|q-x_i|\le\Delta$. Equality throughout forces all vectors $q-x_i$ to
be positive multiples of one another **and** all $|q-x_i|=\Delta$, hence all $x_i$ equal, so
$p=x_1\in X\setminus\{p\}$ — a contradiction. $\blacksquare$

**Lemma E (cocircular sets separate distances).** *Let $C$ be a set of $N$ points on a circle
$\Gamma$ with centre $O$, and let $z\ne O$. Then*

$$\bigl|\{\operatorname{dist}(z,v):v\in C\}\bigr|\ \ge\ \lceil N/2\rceil .$$

*Proof.* For a fixed $t>0$, the points of $C$ at distance $t$ from $z$ lie in
$\Gamma\cap\partial B(z,t)$. Since $z\ne O$, the circles $\Gamma$ and $\partial B(z,t)$ have
different centres and are therefore distinct, so they meet in at most $2$ points. Hence every
distance value is attained by at most $2$ points of $C$, and at least $\lceil N/2\rceil$ values are
needed to account for all $N$ points. $\blacksquare$

*Lemma E is sharp: for a regular $N$-gon and $z\ne O$ on a symmetry axis through an edge midpoint,
exactly $\lceil N/2\rceil$ distances occur — verified numerically in §5.*

---

## 3. Main theorem: Erdős's conjecture for sets with exactly one non-hull point, $n$ odd

**Theorem 1.** *Let $n\ge9$ be **odd** and let $X\subseteq\mathbb R^2$ with $|X|=n$ and
$|L_1(X)|=n-1$ (i.e. exactly one point of $X$ is not a vertex of $\operatorname{conv}X$). Then some
distance of $X$ other than the diameter has multiplicity at most $n$; that is, Conjecture 1.1 holds
for $X$.*

*Proof.* Suppose not, so $X$ is a counterexample set. Write $C:=L_1$, $N:=|C|=n-1$ (even, $N\ge8$),
and let $z$ be the unique point of $X\setminus C$; thus $L_2=\{z\}$ and $z\in\operatorname{conv}(C)$.

**Step 1 ($m$ is pinned).** Every distance determined by $C$ is a distance of $X$, so
$m(C)\le m(X)$. By Altman, $C$ (in convex position, $|C|=N$) has $m(C)\ge\lfloor N/2\rfloor=(n-1)/2$.
By Lemma C, $m(X)\le\lfloor n/2\rfloor=(n-1)/2$ because $n$ is odd. Hence

$$m(C)=m(X)=\tfrac{n-1}2=\Bigl\lfloor \tfrac{|C|}2\Bigr\rfloor .$$

In particular $z$ creates **no new distance**: every $\operatorname{dist}(z,v)$, $v\in C$, is already
a distance of $C$.

**Step 2 ($C$ is cocircular).** $|C|=N\ge8$ is even and $C$ attains Altman's bound, so by Fishburn's
classification $C=R_N$ or $C=R_{N+1}^-$. Both are subsets of a circle $\Gamma$; let $O$ be its centre.

**Step 3 ($z$ avoids the diameter).** By Lemma D the endpoints of a diameter pair lie in $L_1=C$, and
$z\notin C$; hence $\operatorname{dist}(z,v)\ne\Delta$ for every $v\in C$. Combining with Step 1, the
distances from $z$ to $C$ all lie in the set of **non-diameter** distances of $X$, whose size is

$$m(X)-1=\tfrac{n-1}2-1=\tfrac{n-3}2 .$$

**Step 4 (the case $z=O$).** Then $\operatorname{dist}(z,v)$ equals the circumradius $R$ for every
$v\in C$, so $z$ contributes nothing to any distance $d\ne R$; therefore $\mu(X,d)=\mu(C,d)$ for
every $d\ne R$.

* If $C=R_N$ ($N$ even): the non-diameter distances of $C$ have $\mu(C,d)=N=n-1$.
* If $C=R_{N+1}^-=R_n^-$ ($n$ odd): removing one vertex from $R_n$ removes exactly two occurrences
  of each of its $(n-1)/2$ distances (in an odd regular polygon every vertex has exactly two
  partners at each distance), so $\mu(C,d)=n-2$ for every $d$.

In both cases $C$ has at least $\frac{n-3}{2}-1\ge2$ non-diameter distances $d\ne R$ (using $n\ge9$),
and for each of them $\mu(X,d)=\mu(C,d)\le n-1<n+1$, contradicting the counterexample hypothesis.

**Step 5 (the case $z\ne O$).** By Lemma E, $z$ determines at least $\lceil N/2\rceil=(n-1)/2$
distinct distances to $C$. By Step 3 these must lie among only $(n-3)/2$ admissible values. Since
$(n-1)/2>(n-3)/2$, this is impossible.

Steps 4 and 5 exhaust all cases, so no such counterexample exists. $\blacksquare$

**Corollary (in Erdős's language).** *For every odd $n\ge9$, every planar set of $n$ points with
exactly one non-extreme point determines at least two distances of multiplicity $\le n$.*

Since $\tfrac{4n+2}{3}>n$ for every $n\ge1$, Theorem 1 covers a family of point sets **disjoint from**
the family covered by [CDL, Thm 1.3], and not covered by [CDL, Thm 1.2] (which requires $\ell_1=n$).

---

## 4. The even case, and what remains

**Theorem 2.** *Let $n\ge10$ be **even**, $|X|=n$, $|L_1|=n-1$, $C:=L_1$. If $m(C)=\frac n2-1$
(i.e. $C$ attains Altman's bound), then Conjecture 1.1 holds for $X$.*

*Proof.* Suppose $X$ is a counterexample. $|C|=n-1$ is odd and $m(C)=\lfloor|C|/2\rfloor$, so by
Altman's odd-case characterisation $C=R_{n-1}$, cocircular with centre $O$. By Lemma C,
$m(X)\le n/2$, so there are at most $n/2-1$ non-diameter distances, and by Lemma D every distance
from $z$ to $C$ is one of them.

* If $z=O$: all distances of an odd regular polygon have multiplicity $|C|$, so
  $\mu(X,d)=\mu(C,d)=n-1<n+1$ for every non-diameter $d\ne R$, and such a $d$ exists because
  $m(C)-2\ge1$ for $n\ge10$. Contradiction.
* If $z\ne O$: Lemma E gives at least $\lceil(n-1)/2\rceil=n/2$ distinct distances from $z$, but at
  most $n/2-1$ are admissible. Contradiction. $\blacksquare$

**The one remaining case for $\ell_1=n-1$.** $n$ even and $m(C)=n/2$. Then $m(X)=m(C)=n/2$, and
comparing $\sum_d\mu(X,d)=\binom n2$ with $\mu(X,\Delta)+\bigl(\tfrac n2-1\bigr)(n+1)$, together with
the identity $\bigl(\tfrac n2-1\bigr)(n+1)=\binom n2-1$, forces the completely rigid profile

$$\mu(X,\Delta)=1,\qquad \mu(X,d)=n+1\ \text{ for every } d\ne\Delta .$$

Writing $k_d:=\#\{v\in C:\operatorname{dist}(z,v)=d\}$ one gets $k_\Delta=0$ and
$\sum_{d\ne\Delta}k_d=n-1$ spread over exactly $\tfrac n2-1$ classes, hence

$$\sum_{d\ne\Delta}(k_d-2)=1 .$$

So $C$ would have to be a convex $(n-1)$-gon with $\mu(C,\Delta)=1$ and $\mu(C,d)=n+1-k_d$ —
generically the profile $(n-1,\dots,n-1,\,n-2,\,1)$.

The rigidity can be pushed one step further, to a statement about every single vertex.

**Proposition 5 (vertex degree profile in the residual case).** *Let $X$ be a counterexample with
$n$ even, $\ell_1=n-1$, $m(L_1)=n/2$; write $C=L_1$, $N=n-1$, and let $p,q$ be the unique diameter
pair. For $v\in C$ and a distance $d$ let $\deg^C_d(v)=\#\{w\in C: \operatorname{dist}(v,w)=d\}$.
Then, summing over the $\tfrac{N-1}2$ non-diameter distances,*

$$\sum_{d\ne\Delta}\bigl(\deg^C_d(v)-2\bigr)=\begin{cases}\ \ 0,& v\in C\setminus\{p,q\},\\[2pt] -1,& v\in\{p,q\},\end{cases}
\qquad\text{and}\qquad \sum_{d\ne\Delta}(k_d-2)=1 .$$

*Proof.* $v\in C\setminus\{p,q\}$ has $\deg^C_\Delta(v)=0$, so its $N-1$ distances inside $C$ are
distributed over the $\tfrac{N-1}2$ non-diameter classes: $\sum_{d\ne\Delta}\deg^C_d(v)=N-1
=2\cdot\tfrac{N-1}2$. For $v\in\{p,q\}$ we have $\deg^C_\Delta(v)=1$, so the sum is $N-2$, one less.
The statement for $k_d$ is the computation above. $\blacksquare$

So *on average every vertex has exactly two partners at every non-diameter distance*, and likewise
$z$ has on average exactly two vertices of $C$ on each of its circles: the configuration would have
to be as close to a regular polygon as the multiplicity data can force, while having a diameter that
occurs **once** — which a regular polygon never does.

**Two routes that do not work (recorded so they are not retried).**

*(b) The Altman zigzag.* The residual case needs a handle on convex polygons that are one distance
above Altman's minimum, so the natural move is to reach for whatever mechanism produces Altman's
$\lfloor N/2\rfloor$. The obvious candidate is the zigzag path
$v_1\to v_2\to v_N\to v_3\to v_{N-1}\to\cdots$, whose lengths in a **regular** $N$-gon are exactly
$d_1<d_2<\cdots<d_{\lfloor N/2\rfloor}$ — verified for $N=7,8,9,12$. But for general convex polygons
the zigzag is only *unimodal*, not increasing, and even its first $\lfloor N/2\rfloor$ terms fail to
increase in about $27\%$ of cases (87 002 failures out of 323 528 random polygon/start-vertex pairs;
an explicit convex octagon with lengths $0.531,\,0.844,\,1.546,\,1.284,\dots$ is in `zigzag2.py`).
So the zigzag gives no near-extremal leverage, and Altman's bound has to be used as a black box.

*(a) Unimodality at a vertex.* One would also like to upgrade
Proposition 5 to "$\deg^C_d(v)=2$ exactly", which needs $\deg^C_d(v)\le2$, and that would follow if
the distances from a vertex of a convex polygon to the other vertices, read in cyclic order, were
always unimodal. **They are not.** An exact integer counterexample: the strictly convex pentagon

$$(-8,-8),\ (-5,-8),\ (5,-5),\ (5,1),\ (-5,2)\quad(\text{counter-clockwise}),$$

read from the vertex $(-5,2)$, gives squared distances $109,\;100,\;149,\;101$ in cyclic order — a
strict interior dip. (In a random sample of 365 718 convex-polygon/vertex pairs, about 13% were
non-unimodal.) Excluding the residual case therefore appears to need a classification of convex
polygons determining $\lfloor N/2\rfloor+1$ distances, which I am not aware of.
**This case is left open and is stated here as open.**

Note that this open sub-case is precisely the one in which the hull is **not** known to be
cocircular; Theorem 3 below disposes of the cocircular alternative.

---

## 4a. Cocircular hulls: a second, wider family

The proof of Theorem 1 used Altman + Fishburn only to *force* cocircularity of $L_1$. Whenever
cocircularity is available directly, the same engine works for more off-hull points.

**Theorem 3.** *Let $|X|=n$, suppose $L_1$ lies on a circle $\Gamma$ with centre $O$, put
$N=|L_1|$ and $j=n-N\ge1$. If $X$ is a counterexample set, then every $z\in X\setminus L_1$ with
$z\ne O$ satisfies*

$$\Bigl\lceil \tfrac N2\Bigr\rceil\ \le\ \#\{\operatorname{dist}(z,v):v\in L_1\}\ \le\ m(X)-1\ \le\ \Bigl\lfloor\tfrac n2\Bigr\rfloor-1 .$$

*Proof.* The lower bound is Lemma E. For the upper bound: by Lemma D no distance from $z$ to $L_1$
equals $\Delta$, so all of them lie among the $m(X)-1$ non-diameter distances of $X$; and
$m(X)\le\lfloor n/2\rfloor$ by Lemma C. $\blacksquare$

**Theorem 3′.** *With the notation of Theorem 3, suppose $X\setminus L_1$ contains a point $z\ne O$
(automatic as soon as $j\ge2$, since only one point can be the centre). If*

$$\Bigl\lceil\tfrac{n-j}2\Bigr\rceil\ >\ \Bigl\lfloor\tfrac n2\Bigr\rfloor-1,$$

*then $X$ is not a counterexample. This inequality holds for* $j=1$ *(every $n$) and for* $j=2$
*with $n$ odd.*

*Proof.* Immediate from Theorem 3. For the last sentence: if $j=1$ and $n$ is odd,
$\lceil(n-1)/2\rceil=(n-1)/2>(n-3)/2=\lfloor n/2\rfloor-1$; if $j=1$ and $n$ is even,
$\lceil(n-1)/2\rceil=n/2>n/2-1$; if $j=2$ and $n$ is odd, $\lceil(n-2)/2\rceil=(n-1)/2>(n-3)/2$.
(For $j=2$ with $n$ even, and for all $j\ge3$, the inequality fails, so the argument stops there.)
$\blacksquare$

**Theorem 4.** *Let $n\ge11$ be odd, $|X|=n$, $|L_1|=n-2$, and suppose $L_1$ attains Altman's bound,
i.e. $m(L_1)=\lfloor|L_1|/2\rfloor$. Then Conjecture 1.1 holds for $X$.*

*Proof.* $|L_1|=n-2$ is odd, so Altman's characterisation of the odd extremal case gives
$L_1=R_{n-2}$, a regular polygon; in particular $L_1$ is cocircular. Since $j=2$, at most one of the
two points of $X\setminus L_1$ is the centre $O$, so some $z\ne O$ exists, and Theorem 3′ applies
with $j=2$, $n$ odd. $\blacksquare$

So: **a counterexample whose hull vertices are cocircular must hide at least two points off the hull,
and at least three when $n$ is odd.** Theorem 1 is exactly the situation in which Altman + Fishburn
*force* cocircularity; Theorems 3′ and 4 are what the same engine gives when cocircularity is
assumed or otherwise available.

---

## 5. Finite verification (checks, not proofs)

Scripts: `verify.py`, `verify2.py`, `verify3.py` in this directory (Python stdlib only; exact
integer arithmetic for all convex-layer computations).

| Check | What | Result |
|---|---|---|
| 1 | Theorem A ($\lambda(p)+\lambda(q)\le k+1$) on 4000 random integer point sets, $4\le n\le14$ | 0 failures |
| 1b | Theorem A on all $a\times b$ integer grids, $2\le a,b\le5$ | 0 failures |
| 2 | Sharpness of Theorem A: equality $\lambda(p)+\lambda(q)=k+1$ | attained for $k=1,2,3$ |
| 3 | Lemma E on random cocircular sets, $N\le20$ | bound always satisfied |
| 3b | Lemma E sharpness on regular $N$-gons, $z$ on an edge-midpoint axis | exactly $\lceil N/2\rceil$ |
| 4 | Multiplicity profiles of $R_N$ ($N$ even and odd) and $R_{N+1}^-$ used in Step 4 | all as claimed |
| 5 | Direct search for a counterexample set with $\ell_1=n-1$, $5\le n\le11$ (37 517 qualifying sets) | none found |
| 6 | Theorem 1's reduction targets $R_{n-1}+z$ and $R_n^-+z$, $n=9,11,13,15$, ~4100 interior $z$ each | min rare-distance count 5 (theorem asserts $\ge2$) |
| 7 | Steps 4–5 arithmetic for every odd $n\in[9,59]$ | contradiction in all cases |
| 8 | [CDL, Thm 1.3] applicability at $\ell_1=n-1,\ell_2=1$ for $n<2000$ | never applies, as claimed |
| 9 | Theorem 3′ inequality $\lceil(n-j)/2\rceil>\lfloor n/2\rfloor-1$, $9\le n\le29$ | holds for $j=1$ (all $n$) and $j=2$ ($n$ odd); fails for $j\ge3$ |
| 10 | Theorem 4 target $R_{n-2}$ plus two points, $n=11,13,15$, ~6000 placements each | min rare-distance count $=n$ |
| 11 | Unimodality of vertex distances in convex polygons, 365 718 (polygon, vertex) pairs | **false** — 49 212 non-unimodal |
| 11b | Exact integer counterexample to unimodality (the pentagon quoted in §4) | reproduced in exact arithmetic |
| 12 | Altman zigzag strictly increasing on its first $\lfloor N/2\rfloor$ terms, 323 528 pairs | **false** — 87 002 failures |
| 12b | Zigzag on regular $N$-gons, $N=7,8,9,12$ | matches $d_1<\dots<d_{\lfloor N/2\rfloor}$ exactly |

These are **finite checks and are not proofs** of the universal statements; the proofs are in §§1–4.

---

## 6. Honest summary of what is and is not established

**Established (proved above):**

1. **Theorem A** — for every $k$, a pair at the $k$-th largest distance satisfies
   $\lambda(p)+\lambda(q)\le k+1$; equivalently the $k$ largest distances of $X$ are confined to
   $L_1\cup\dots\cup L_k$ and are the $k$ largest distances there (Corollary B). This generalises
   [Ve, Prop. 1] and [CDL, Obs. 2]; it may already be known for general $k$ (Vesztergombi's papers
   were not accessible to me).
2. **Theorem 1** — Erdős's Conjecture 1.1 holds for every **odd $n\ge9$** and every $X$ with exactly
   one non-hull point. This case is covered by neither [CDL, Thm 1.2] nor [CDL, Thm 1.3].
3. **Theorem 2** — the same for even $n\ge10$ when $L_1$ attains Altman's bound.
4. **Theorem 3 / 3′** — a counterexample whose hull vertices are cocircular needs $\ge2$ points off
   the hull, and $\ge3$ when $n$ is odd.
5. **Theorem 4** — Conjecture 1.1 holds for odd $n\ge11$ with $|L_1|=n-2$ when $L_1$ attains
   Altman's bound (then $L_1=R_{n-2}$).
6. **Lemma C** — any counterexample determines at most $\lfloor n/2\rfloor$ distinct distances.
7. **Proposition 5** — in the single residual configuration, every hull vertex off the diameter has
   $\sum_{d\ne\Delta}(\deg^C_d(v)-2)=0$, the two diameter endpoints have $-1$, and the off-hull point
   has $\sum_d(k_d-2)=1$.
8. Two recorded dead ends: distances from a vertex of a convex polygon to the other vertices, taken
   in cyclic order, need **not** be unimodal (explicit integer pentagon in §4); and the Altman
   zigzag, though exact on regular polygons, is not increasing on general convex ones even over its
   first $\lfloor N/2\rfloor$ terms, so it gives no near-extremal leverage.

Combining Theorems 1, 2 and 3′, the case $\ell_1=n-1$ now reduces to a single configuration:
$n$ even, $L_1$ **not** cocircular, and $m(L_1)=n/2$ (one more distance than Altman's minimum).

**Not established:**

* Erdős Problem #132 itself remains **open**. This note does not solve it.
* The case $n$ even, $\ell_1=n-1$, $m(L_1)=n/2$, $L_1$ not cocircular is open (§4).
* Nothing here bears on the second half of #132 (whether the number of such distances $\to\infty$).
* **No prize is claimed.** Whether this qualifies as the "nontrivial result" for which Erdős offered
  \$100 is a judgement for the problem's curators, not something I assert. The acceptance route is a
  submission on the problem page at erdosproblems.com (proof-claim / comment form, maintained by
  T. F. Bloom); Erdős prize administration passed from Ron Graham (d. 2020) to the community.

**References**

* T. F. Bloom, *Erdős Problem #132*, <https://www.erdosproblems.com/132>, accessed 2026-09-06.
* F. C. Clemen, A. Dumitrescu, D. Liu, *On the multiplicities of interpoint distances*,
  arXiv:2505.04283v1, 7 May 2025.
* H. Hopf & E. Pannwitz (1934); E. Altman (1963); P. Fishburn; K. Vesztergombi (1985–87) — as cited
  in [CDL].

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
