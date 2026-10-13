# A q=3 cover for two partition-quota families

## Result and explicit generators

Let $E$ be finite. Let $J_1,J_2$ be disjoint finite index sets. Each index $v$ has a quota set $B_v\subseteq E$ and capacity $r_v\in\mathbb Z_{\ge0}$. Within each $J_a$, the sets $B_v$ are pairwise disjoint. Sets on opposite sides may overlap arbitrarily, and either family may omit coordinates or contain empty blocks.

Give coordinate $i$ an independent inclusion probability $p_i\in[0,1]$, and put

$$
D=\{A\subseteq E:|A\cap B_v|\le r_v
\text{ for every }v\in J_1\cup J_2\}.
$$

As in [Talagrand's primary problem](https://michel.talagrand.net/prizes/combinatorics.pdf), let $D^{(q)}$ be the sets that cannot be covered by $q$ members of $D$. For a generator $I$, write

$$
B(I)=\{A\subseteq E:I\subseteq A\},
\qquad
w(I)=\prod_{i\in I}p_i.
$$

Set

$$
\ell=\log(3/2),
\qquad
C=\frac{27}{128},
\qquad
K=\frac{2C}{\ell}=\frac{27}{64\log(3/2)}.
$$

**Theorem.** If $\mu(D)\ge2/3$, the following explicit generator family satisfies

$$
D^{(3)}=\bigcup_{I\in G}B(I),
\qquad
\sum_{I\in G}w(I)
\le K[-\log\mu(D)]
\le\frac{27}{64}<\frac12. \tag{1}
$$

To construct it, collect the coordinates forbidden by zero quotas:

$$
Z=\bigcup_{v:r_v=0}B_v,
\qquad E'=E\setminus Z,
\qquad \widetilde B_v=B_v\setminus Z.
$$

Then take

$$
G=\{\{i\}:i\in Z\}
\ \cup\
\bigcup_{v:r_v\ge1}
{\widetilde B_v\choose3r_v+1}. \tag{2}
$$

All unions of generators are set unions: duplicates are counted once. A subset family above its ambient size is empty. Every generator is nonempty, and zero-weight generators remain in the literal cover.

The number of blocks is unrestricted. Two individual overlapping quotas are a special case, obtained by putting one quota on each side. The mass-dependent bound in (1) is asserted only under the stated hypothesis $\mu(D)\ge2/3$.

## Exact decomposition for every q

For every integer $q\ge1$, write $C_q(D)$ for the sets covered by $q$ members of $D$. We first prove

$$
C_q(D)=
\{X\subseteq E:|X\cap B_v|\le qr_v
\text{ for every }v\in J_1\cup J_2\}. \tag{3}
$$

Necessity follows by adding the $q$ quota bounds. For sufficiency, fix $X$ satisfying the right side.

### Coordinates as edges

Create a bipartite multigraph whose left quota vertices are indexed by $J_1$ and right quota vertices by $J_2$. Each coordinate of $X$ becomes one distinct edge. On a side where that coordinate belongs to a quota block, use its unique quota vertex; where it belongs to no block, give it a private degree-one endpoint on that side.

Pairwise disjointness within a side makes the assigned quota endpoint unique. Different coordinates can join the same two vertices, so parallel edges must remain distinct. There are no loops.

A quota vertex $v$ has degree $|X\cap B_v|\le qr_v$. If $r_v=0$, its degree is zero. If $r_v\ge1$, divide its incident edges into at most $r_v$ bins of at most $q$ edges each, and replace the vertex by one clone for each nonempty bin. Choose the bin at each endpoint independently. Every original coordinate still defines exactly one edge between its two assigned clones or private endpoints.

The resulting finite bipartite multigraph has maximum degree at most $q$. A proper $q$-edge-coloring gives the desired partition: in each color, every clone receives at most one edge, so its original quota vertex receives at most $r_v$ edges. Restricting each color to original coordinate edges yields a member of $D$, and the $q$ color classes partition $X$.

### A complete finite coloring construction

This is the classical bipartite multigraph edge-coloring theorem of Kőnig. For completeness, the regularization and matching construction needed here is explicit.

Pad the two vertex classes with isolated vertices until they have the same size. Their total degree deficits from $q$ are equal, because each side has the same vertex count and the same degree sum. While deficits remain, join a deficient left vertex to a deficient right vertex by a new edge. Parallel dummy edges are permitted. This terminates with a $q$-regular bipartite multigraph.

For any set $S$ of left vertices, its $q|S|$ incident edges end among its distinct neighbors $N(S)$. Those neighbors have total degree $q|N(S)|$, so

$$
q|S|\le q|N(S)|,
\qquad |S|\le|N(S)|.
$$

Hall's matching condition therefore holds. Its finite sufficiency can be seen directly: choose a maximum matching. If it misses a left vertex, explore alternating paths from that vertex, using unmatched edges left-to-right and matching edges right-to-left. No reachable right vertex can be unmatched, since otherwise reversing an augmenting path enlarges the matching. Let $S,T$ be the reachable left and right sets. Then $T=N(S)$, and matching edges pair $T$ with exactly $S$ minus the starting unmatched vertex. Thus $|N(S)|=|S|-1$, contradicting the condition. The matching saturates the left side and, since the sides have equal size, is perfect.

Remove a perfect matching. The remaining graph is $(q-1)$-regular; repeat until every edge belongs to one of $q$ matchings. Their indices are the edge colors. Discard dummy edges and dummy vertices. Properness remains true on the original graph, so the capacity-clone argument proves (3).

The edgeless case is immediate. Empty color classes are allowed. Because $D$ is a downset, an overlapping cover by $q$ members can always be replaced by a partition of $X$ by assigning each covered coordinate to one containing member. Hence the criterion agrees exactly with Talagrand's covering convention.

### Literal obstruction family

Taking the complement in (3) gives

$$
D^{(q)}=
\bigcup_v\{X:|X\cap B_v|\ge qr_v+1\}.
$$

For $q=3$, a set containing a coordinate of $Z$ is already obstructed by the corresponding singleton. For a set avoiding $Z$, each positive quota is equivalent to its restriction to $\widetilde B_v$. This proves the equality in (1) for the generator family (2). It also explains why removing forced-zero coordinates preserves the literal cover.

## Retained analytic inputs

The [accepted disjoint-quota note](PARTITION_MATROID_Q3.md), blob **42fc269e1cc57a4e81fd5778ea76d6c6cea5ab3b**, from [Commons #31037](https://github.com/woahwhattheheck/commons/pull/31037), supplies the following scaling statement. For a positive-capacity quota $r\ge1$ with $F(1)\ge1/2$ and nonzero generator weight, scale its probabilities by

$$
p_i(t)=\min\{tp_i,1\},
\quad
F(t)=\Pr(S_t\le r),
\quad
W(t)=e_{3r+1}(p(t)).
$$

Until the first boundary $F(t)=1/2$, both the failure and weight are positive, the clipped path is continuous, and

$$
\frac{W(t)}{-\log F(t)}
\quad\text{is nondecreasing}. \tag{4}
$$

This is the source's Section 2, equation (16) and its continuation across saturation times. Its zero-weight case also states that $F=1$ forces $W=0$. Here

$$
e_h(p_B)=
\sum_{\substack{I\subseteq B\\|I|=h}}\prod_{i\in I}p_i,
$$

with $e_h=0$ when $h>|B|$.

The [two-overlapping-quota note](TWO_OVERLAPPING_QUOTAS_Q3.md), blob **beced6b1636d83b97955a8e9fb2aedecfa1bc329**, from [Commons #31215](https://github.com/woahwhattheheck/commons/pull/31215), establishes the uniform positive-quota estimate

$$
F\ge2/3,\quad r\ge1
\quad\Longrightarrow\quad
W\le C=\frac{27}{128}. \tag{5}
$$

Its capacity-one argument retains Hoeffding's fixed-mean extremal attribution; larger capacities use the preceding half-mass and clipped-scaling statements. We consume (4) and (5) as proved inputs, without repeating those arguments.

## Normalize one positive quota by its acceptance

Suppose $F\ge2/3$ for a positive-capacity block. If $W=0$, the desired inequality below is immediate. Otherwise the accepted clipped path reaches $F=2/3$ before it reaches $F=1/2$. Let $t_0$ be its first point with $F(t_0)=2/3$; when the initial $F$ is already $2/3$, take $t_0=1$.

By (4) and the boundary estimate (5),

$$
\frac{W}{-\log F}
\le
\frac{W(t_0)}{\log(3/2)}
\le\frac C\ell.
$$

Thus every positive quota with acceptance at least $2/3$ satisfies

$$
W\le\frac C\ell[-\log F]. \tag{6}
$$

The case $F=1$ has zero weight and uses no ratio. Clamping, deterministic coordinates and insufficient positive support are already included in the stated input interface.

## Compose any number of blocks on two sides

First suppose every capacity is positive. Let $A_a$ be the event that all quotas indexed by $J_a$ hold, and let $F_v$ be the individual acceptance probabilities. Disjointness within each side gives

$$
\mu(A_a)=\prod_{v\in J_a}F_v,
\qquad D=A_1\cap A_2.
$$

The two side events need not be independent. Cauchy–Schwarz applied to their indicators yields

$$
\mu(D)^2
\le\mu(A_1)\mu(A_2)
=\prod_vF_v.
$$

Each $F_v\ge\mu(D)\ge2/3$, and all logarithms are defined. Consequently

$$
\sum_v[-\log F_v]\le-2\log\mu(D).
$$

Using (6), with duplicate generators counted only once, gives

$$
\begin{aligned}
\sum_{I\in G}w(I)
&\le\sum_v e_{3r_v+1}(p_{B_v})\\
&\le\frac C\ell\sum_v[-\log F_v]\\
&\le K[-\log\mu(D)]\\
&\le K\ell=\frac{27}{64}.
\end{aligned} \tag{7}
$$

The estimate is independent of the number, sizes and cross-overlap pattern of the blocks.

## Include zero quotas

Let $Z,E'$ be as in (2), and let $D'$ be the positive-quota family on $E'$ after deleting $Z$ from every block. The restricted blocks remain pairwise disjoint within each side.

Write

$$
\alpha=\Pr(\text{no coordinate of }Z\text{ is selected})
=\prod_{i\in Z}(1-p_i),
\qquad
\beta=\mu_{E'}(D').
$$

Independence of $Z$ and its complement gives $\mu(D)=\alpha\beta$. The mass hypothesis makes $\alpha>0$ and $\beta\ge2/3$. The singleton generators have total weight at most

$$
\sum_{i\in Z}p_i
\le-\log\alpha,
$$

the retained zero-quota bound from #31037. The positive-quota construction on $E'$ has weight at most $K[-\log\beta]$ by (7).

The exact comparison from #31215,

$$
\ell=\log(3/2)\le\frac5{12}<\frac{27}{64}=2C,
$$

gives $K>1$. Therefore

$$
\begin{aligned}
\sum_{I\in G}w(I)
&\le-\log\alpha+K[-\log\beta]\\
&\le K[-\log\alpha-\log\beta]\\
&=K[-\log\mu(D)]\\
&\le\frac{27}{64}.
\end{aligned}
$$

This proves the full theorem. Empty families use product one and sum zero. Coordinates of probability one cannot occur in $Z$ under the mass hypothesis, and remain allowed elsewhere. Empty blocks, capacities exceeding block size, missing coordinates and zero-weight generators all retain the meanings in (2) and (3).

## Interpretation, attribution and scope

As a concrete special case, let the coordinates be the distinct edges of a finite bipartite multigraph and put a capacity on each vertex. The family of edge sets satisfying all endpoint capacities is an intersection of two partition-quota families. If its independent-edge product mass is at least $2/3$, (1) provides the stated cover. Capacity one at every vertex gives the family of matchings. Parallel edges remain separate coordinates with their own probabilities.

The graph step is classical. **Dénes Kőnig**, *Über Graphen und ihre Anwendung auf Determinantentheorie und Mengenlehre*, Mathematische Annalen **77**(4) (1916), 453–465, Theorem C, proves the finite bipartite edge-coloring statement; Theorem B gives regular factorization. The [full primary-paper translation by Ágnes Cseh](https://arxiv.org/html/2412.17140v1) explicitly permits finitely many parallel edges in its opening definition. Degrees count those edge copies, and incident parallel edges receive different colors. This is the edge-coloring theorem, distinct from the later matching/vertex-cover duality.

**P. Hall**, *On Representatives of Subsets*, Journal of the London Mathematical Society **s1-10**(1) (1935), 26–30, Theorem 1, gives the finite distinct-representative criterion; [original publisher PDF](https://londmathsoc.onlinelibrary.wiley.com/doi/pdf/10.1112/jlms/s1-10.37.26), [DOI](https://doi.org/10.1112/jlms/s1-10.37.26). The matching formulation uses distinct neighbors in $N(S)$; parallel edges do not create additional neighbors. The regularization and finite alternating-path argument required here are included above.

Kestrel, the October 3 threshold completion, Osprey, LATTICE-73A, Solstice and the original published inputs retain the provenance recorded in the two linked Commons notes. The new composition combines those retained analytic estimates with the classical two-partition decomposition and the two-side probability bound. The capacity-clone/regularization construction and primary-reference retrieval were contributed within this collaboration.

The conclusion covers systems organized into two internally disjoint quota families. It makes no assertion for arbitrary overlapping systems, an arbitrary third partition, general matroids or arbitrary high-mass families. It is an analytic continuation with no priority, optimality, formal-kernel, external-review or sponsor-submission claim. No accepted proof, census or runtime computation was replayed.
