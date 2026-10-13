# Covers for quota systems with bounded coordinate frequency

## Theorem and scope

Let $E$ be finite, let $J$ be a finite index set, and give every $v\in J$ a block $B_v\subseteq E$ and an integer capacity $r_v\ge0$. The blocks may overlap arbitrarily. Fix an integer $d\ge1$ such that

$$
|\{v\in J:i\in B_v\}|\le d
\quad\text{for every }i\in E. \tag{1}
$$

Thus $d$ bounds the number of quota blocks containing any one coordinate. It does not bound the size of a block or the number of blocks. Identical indexed blocks count separately in (1); repeated generator sets will be deduplicated.

Give coordinate $i$ an independent inclusion probability $p_i\in[0,1]$, and define the downset

$$
D=\{A\subseteq E:|A\cap B_v|\le r_v\text{ for all }v\in J\}.
$$

For an integer $q\ge1$, let $D^{(q)}$ be the sets that cannot be covered by $q$ members of $D$, using [Talagrand's original convention](https://michel.talagrand.net/prizes/combinatorics.pdf). Write

$$
B(I)=\{A\subseteq E:I\subseteq A\},
\qquad
w(I)=\prod_{i\in I}p_i.
$$

**Theorem.** Put $q=2d+1$. If $\mu(D)\ge1/2$, there is an explicit family $G$ of nonempty generators satisfying

$$
D^{(2d+1)}\subseteq\bigcup_{I\in G}B(I),
\qquad
\sum_{I\in G}w(I)\le d[-\log\mu(D)]. \tag{2}
$$

In particular, under the target hypothesis $\mu(D)\ge1-1/q=2d/(2d+1)$,

$$
\sum_{I\in G}w(I)
\le d\log\left(1+\frac1{2d}\right)
<\frac12. \tag{3}
$$

The same construction has cost at most $1/2$ whenever $\mu(D)\ge\exp(-1/(2d))$. This is a sufficient mass bound, with no optimality assertion.

For a fixed incidence bound $d$, the integer $q=2d+1$ is independent of $|E|$. It depends on $d$. The theorem does not supply a fixed $q$ for unrestricted quota systems or arbitrary families. The case $d=1$ consumes the accepted disjoint-quota theorem; the extension here allows arbitrary overlap of bounded coordinate frequency.

## Explicit generators and zero capacities

First collect the coordinates forbidden by any zero quota:

$$
Z=\bigcup_{v:r_v=0}B_v,
\qquad
E_+=E\setminus Z,
\qquad
J_+=\{v\in J:r_v\ge1\},
\qquad
B_v^+=B_v\setminus Z.
$$

Take

$$
G=\{\{i\}:i\in Z\}
\ \cup\
\bigcup_{v\in J_+}{B_v^+\choose3r_v+1}. \tag{4}
$$

Every union here is a set union, so identical generators count once. A subset family is empty if its requested size exceeds the size of the underlying block. All generators are nonempty. A generator with weight zero remains in the set-theoretic cover.

Removing $Z$ from positive blocks preserves the frequency bound (1). The remaining family is

$$
D_+=\{A\subseteq E_+:|A\cap B_v^+|\le r_v
\text{ for every }v\in J_+\}.
$$

An original set belongs to $D$ exactly when it avoids $Z$ and belongs to $D_+$. Independence therefore gives

$$
\mu(D)=\alpha\beta,
\qquad
\alpha=\prod_{i\in Z}(1-p_i),
\qquad
\beta=\mu_{E_+}(D_+). \tag{5}
$$

Under the theorem's mass hypothesis, $\alpha>0$ and $\beta\ge\mu(D)\ge1/2$. In particular, no probability-one coordinate lies in $Z$. A coordinate contained in several zero blocks contributes only one singleton generator.

## A sufficient covering construction

We prove the deterministic inclusion needed for (2). Suppose $X\subseteq E_+$ satisfies

$$
|X\cap B_v^+|\le3r_v
\quad\text{for every }v\in J_+. \tag{6}
$$

For each quota separately, partition $X\cap B_v^+$ into at most $r_v$ bins of size at most three. Such a partition exists by (6), for example by listing its coordinates and taking consecutive groups of three, with one shorter last group if needed. An empty intersection uses no bins. These choices are independent between different quotas.

Make a simple graph with vertex set $X$. Join two distinct coordinates when they occur in the same bin for at least one quota. A coordinate occurs in at most $d$ quota blocks; in its bin for each such block it has at most two companions. Thus its number of distinct neighbors is at most $2d$. If a pair shares several bins, it is still only one graph edge, so repeated conflicts only lower this degree bound.

Color the graph greedily in any order using colors $1,\ldots,2d+1$. At the moment a vertex is colored, at most $2d$ colors are used by its already colored neighbors. At least one color remains available. This gives a proper coloring.

Every color class meets each bin in at most one coordinate. Since a quota has at most $r_v$ bins, each color class satisfies that quota. Coordinates outside all positive blocks are isolated graph vertices and cause no restriction. Consequently the $2d+1$ color classes are members of $D_+$ and partition $X$.

They also belong to $D$ because they avoid $Z$. Empty color classes are permitted. This proves that every $X$ satisfying (6) is covered by $2d+1$ members of $D$.

Now take $X\in D^{(2d+1)}$. If $X$ meets $Z$, it contains a singleton from (4). Otherwise $X\subseteq E_+$, and the preceding implication forces at least one violation of (6). Such an $X$ contains a $(3r_v+1)$-subset of $B_v^+$, again a generator in (4). Hence

$$
D^{(2d+1)}\subseteq\bigcup_{I\in G}B(I). \tag{7}
$$

This is a sufficient inclusion, not an exact coverability criterion. For example, when $d\ge2$, four coordinates in $E_+$ can always be covered by four singleton members of $D_+$, even if those four coordinates form a capacity-one generator in (4). The allowed upper cover may therefore contain sets that are coverable. Talagrand's covering objective permits this.

Since $D$ is a downset, a cover by $q$ members can also be turned into a partition of $X$: intersect the members with $X$ and assign each covered coordinate to one containing member. The constructed partition consequently uses the original covering convention.

## The accepted one-block analytic input

The [disjoint-quota q=3 note](PARTITION_MATROID_Q3.md), blob **42fc269e1cc57a4e81fd5778ea76d6c6cea5ab3b**, from [Commons #31037](https://github.com/woahwhattheheck/commons/pull/31037), proves the following one-block specialization. For a finite block $B$, capacity $r\ge1$ and arbitrary independent probabilities in $[0,1]$, put

$$
F=\Pr\!\left(\sum_{i\in B}\mathbf1_{\{i\text{ selected}\}}\le r\right),
\qquad
W=e_{3r+1}(p_B)
=\sum_{I\in{B\choose3r+1}}\prod_{i\in I}p_i.
$$

If $F\ge1/2$, then

$$
W\le-\log F. \tag{8}
$$

This includes probability endpoints, empty subset families, insufficient positive support and the case $F=1$, in which $W=0$. The source also supplies the zero-quota singleton estimate

$$
\sum_{i\in Z}p_i\le-\log\prod_{i\in Z}(1-p_i)
=-\log\alpha. \tag{9}
$$

We consume these proved interfaces. Their threshold, clipped-scaling, factorial and sharpness arguments are not repeated here.

## The finite read-d probability inequality

The acceptance events of overlapping blocks need not be independent. We instead use the following finite form of generalized Hölder.

**Lemma.** Let independent coordinates form a finite product probability space. For each $v$, let $f_v\ge0$ depend only on the coordinates in a specified set $S_v$. Suppose each coordinate belongs to at most $d$ of those sets, where $d\ge1$ is an integer. Then

$$
\mathbb E\prod_v f_v
\le\prod_v(\mathbb E f_v^d)^{1/d}. \tag{10}
$$

The expectations are finite for the finite-valued functions used here. The lemma requires independence of the underlying coordinates, not independence of the functions.

### Direct finite proof

Integrate coordinates one at a time. After processing a set $T$ of coordinates, associate to factor $v$ the function

$$
g_{v,T}=
\left(\mathbb E_{S_v\cap T} f_v^d\right)^{1/d}
$$

of its still unprocessed coordinates. At $T=\varnothing$, this is $f_v$.

For a remaining coordinate $i$, at most $d$ factors $g_{v,T}$ can depend on $i$. Holding all other coordinates fixed, apply Hölder with exponent $d$ to those factors. If fewer than $d$ factors depend on $i$, pad the application with constant-one factors. Each added factor has $L^d$ norm one because the coordinate measure is a probability measure. If no factor depends on $i$, integration changes nothing. For $d=1$, the corresponding step is equality.

For every affected factor,

$$
\left(\mathbb E_i g_{v,T}^d\right)^{1/d}
=
\left(\mathbb E_{S_v\cap(T\cup\{i\})} f_v^d\right)^{1/d}
=g_{v,T\cup\{i\}},
$$

by the product structure and interchange of finite sums. Unaffected factors are unchanged. Therefore

$$
\mathbb E_i\prod_vg_{v,T}
\le\prod_vg_{v,T\cup\{i\}}.
$$

Iterate until all coordinates are integrated. The left side is the original expectation, and the right side is the product of the $L^d$ norms in (10). This proves the lemma, including empty supports, repeated supports and the at-most-$d$ condition.

### Apply it to quota acceptance

For $v\in J_+$, let $f_v$ be the indicator that quota $v$ holds in $E_+$, and write $F_v=\mathbb E f_v$. Each depends only on $B_v^+$, so (1) still gives the required frequency bound. Since $f_v^d=f_v$,

$$
\beta=\mathbb E\prod_{v\in J_+}f_v
\le\prod_{v\in J_+}F_v^{1/d},
\qquad
\beta^d\le\prod_{v\in J_+}F_v. \tag{11}
$$

Each $F_v\ge\beta\ge1/2$, so every logarithm is defined and every block is eligible for (8). Taking negative logarithms in (11) gives the needed orientation:

$$
\sum_{v\in J_+}[-\log F_v]\le d[-\log\beta]. \tag{12}
$$

The number of blocks does not appear in this bound.

## Complete the generator-cost estimate

Let $W_+$ be the total weight of the distinct positive-quota generators in (4). Deduplication only decreases the sum, so (8) and (12) give

$$
W_+
\le\sum_{v\in J_+} e_{3r_v+1}(p_{B_v^+})
\le\sum_{v\in J_+}[-\log F_v]
\le d[-\log\beta]. \tag{13}
$$

Add the singleton contribution (9). Since $d\ge1$ and $-\log\alpha\ge0$,

$$
\begin{aligned}
\sum_{I\in G}w(I)
&\le-\log\alpha+d[-\log\beta]\\
&\le d[-\log\alpha-\log\beta]\\
&=d[-\log\mu(D)].
\end{aligned} \tag{14}
$$

Together with (7), this proves (2).

At the target mass, $-\log\mu(D)\le\log(1+1/(2d))$. The elementary strict inequality $\log(1+x)<x$ for $x>0$ proves (3). For the additional sufficient mass $\exp(-1/(2d))$, formula (14) gives cost at most $1/2$ directly. These arguments use the bound only in its established range $\mu(D)\ge1/2$; indeed $\exp(-1/(2d))\ge\exp(-1/2)>1/2$.

The empty quota family has mass one and an empty generator family. Empty blocks, capacities larger than blocks, unused coordinates, coincident blocks and zero-weight generators are included throughout. If no coordinate occurs in any block, the system is trivial; the theorem still applies with the declared bound $d=1$.

## Attribution and relation to the retained results

The probability step is a classical generalized Hölder inequality. **Helmut Finner**, *A Generalization of Hölder's Inequality and Some Probability Inequalities*, Annals of Probability **20**(4) (1992), 1893–1901, [DOI 10.1214/aop/1176989534](https://doi.org/10.1214/aop/1176989534), retains that attribution. An accessible primary restatement is **Jonathan Bennett and Terence Tao**, *Adjoint Brascamp–Lieb inequalities* (2024), [Remark 2.3](https://londmathsoc.onlinelibrary.wiley.com/doi/10.1112/plms.12633). It states the nonnegative coordinate-product inequality with reciprocal exponents summing to one at each coordinate. The finite probability version with incidence at most $d$ is proved above, including the constant-one padding; no uninspected hypothesis of Finner's original text is assumed.

The term “read-$d$” follows the independent-input, bounded-occurrence convention in **Dmitry Gavinsky, Shachar Lovett, Michael Saks and Srikanth Srinivasan**, *A Tail Bound for Read-k Families of Functions*, [authors' primary preprint, Definition 1](https://arxiv.org/pdf/1205.1478). That definition concerns Boolean functions; it is not used as a statement of the arbitrary-nonnegative moment inequality. Only the indicator specialization is needed for the quotas.

Kestrel, the October 3 threshold completion, Osprey, LATTICE-73A, Solstice and the original published inputs retain the provenance recorded in the accepted one-block source. The new composition combines that source with the explicit bounded-degree conflict graph, the finite Hölder argument and the zero-quota decomposition.

For $d=1$, blocks are disjoint and the accepted q=3 logarithmic result is recovered as an input case. For $d=2$, this note supplies q=5 for arbitrary block overlaps with frequency at most two, without requiring a two-family partition. The [two-partition q=3 result](TWO_PARTITION_QUOTAS_Q3.md) remains stronger where its additional structure is available; its exact coverability criterion is not replaced by the sufficient inclusion here.

The result has a declared structural parameter and an explicit construction. It does not resolve the unrestricted dimension-independent problem, improve an established optimal constant, or assert mathematical priority. No accepted proof or census was audited or replayed, and no native computation, formal-kernel verification, external review or sponsor submission was performed.
