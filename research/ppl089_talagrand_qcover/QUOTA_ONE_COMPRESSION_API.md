# Exact compression of zero/one quota systems

Status: **PUBLIC CONNECTED-V8 API / EXACT REPRESENTATION RECOGNITION / COMPLETE FINITE-FIELD INPUT AND WITNESSES**.

An overlapping list of capacity-one constraints can encode a much simpler disjoint quota system. This module recognizes exactly when that reduction is possible, preserves the source of every forbidden pair, and constructs covers or explicit obstructions for a recognized system. It does not edit the input family to make recognition succeed.

The accepted probability theorems in this directory remain separate premises. The new work is the representation API, its complete combinatorial justification, and one fully retained finite-field incidence application.

## 1. Definitions and exact recognition

Let $E$ be a finite coordinate set. Each input block $B_j\subseteq E$ has capacity $r_j\in\{0,1\}$, and

$$
D=\{A\subseteq E: |A\cap B_j|\le r_j\text{ for every }j\}.
$$

Repeated entries inside a block describe the same set. Repeating a whole constraint also leaves $D$ unchanged, but the API retains its separate source index for provenance.

First form the forced-zero union

$$
Z=\bigcup_{j:r_j=0}B_j,\qquad V=E\setminus Z.
$$

Every admissible set avoids $Z$. For each capacity-one block, use its active part $C_j=B_j\setminus Z$. On $V$, construct a simple graph $G$: distinct coordinates $u,v$ are adjacent exactly when some $C_j$ contains both. All such source-block indices are retained on the one graph edge.

Then

$$
D=\{A\subseteq V:A\text{ is an independent set of }G\}.
\tag{1}
$$

Indeed, two selected coordinates in a capacity-one block give an edge inside $A$. Conversely, a violated capacity-one constraint supplies such a pair. Avoiding $Z$ deals with every zero constraint. This pair characterization depends on the capacities being at most one; higher capacities are outside the input contract.

### Recognition theorem

The family $D$ has an equivalent representation by disjoint zero/one quotas on the same universe if and only if every connected component of $G$ is complete.

If the components are cliques $K_1,\ldots,K_t$, equation (1) gives the exact representation

$$
D=\{A\subseteq E:A\cap Z=\varnothing,\ |A\cap K_i|\le1\text{ for all }i\}.
\tag{2}
$$

The blocks $Z,K_1,\ldots,K_t$ are disjoint and cover $E$. Omit $Z$ if it is empty. An isolated vertex is retained as a singleton capacity-one block; that constraint is vacuous, and the coordinate is explicitly listed as free.

For the converse, suppose a component is not complete. Choose two nonadjacent vertices in it and a shortest connecting path. Its first three vertices $a,b,c$ satisfy

$$
ab,bc\in E(G),\qquad ac\notin E(G).
$$

They are an induced path on three vertices, called $P_3$ here. All three singletons are admissible, and $\{a,c\}$ is admissible, while $\{a,b\}$ and $\{b,c\}$ are forbidden. In any disjoint zero/one representation, none of these coordinates can be forced zero. The two forbidden pairs must therefore put $a,b$ in one capacity-one block and $b,c$ in one capacity-one block. Disjointness makes those the same block, incorrectly forbidding $\{a,c\}$. This proves impossibility, rather than merely reporting failure of one proposed partition.

The API returns the three vertex IDs, the two forbidden edges with every source-block witness, and the compatible endpoint pair. Absence of the endpoint edge refers to the complete compiled pair graph. No graph edge is added, deleted or guessed.

The cluster-graph characterization is established graph theory. Shamir, Sharan and Tsur, [*Cluster graph modification problems*, Discrete Applied Mathematics 144 (2004), 173–182](https://www.cs.tau.ac.il/~roded/jcmod.pdf), printed page 174, define clique components and state the forbidden induced two-edge-path characterization. Their notation counts edges and calls this path $P_2$; this guide counts its three vertices and calls it $P_3$. The API applies that characterization to the exact quota-conflict graph.

### Endpoints and normalization

Zero constraints are combined through a union, so a coordinate in several zero blocks is excluded only once. Deleting that coordinate from every positive block prevents false conflicts involving an impossible selection. The original zero-block indices remain available on its singleton obstruction.

Empty blocks cause no restriction. Positive blocks with at most one active coordinate produce no edges. Isolated coordinates remain in the universe and in the disjoint representation. If all coordinates are forced zero, the family is $\{\varnothing\}$; if the universe is empty, the empty list of compressed blocks is valid. Duplicate block/member handling affects provenance counts, not the family.

## 2. Exact covers after compression

For an integer $q\ge1$, let $C_q(D)$ be the sets covered by the union of $q$ members of $D$. Once equation (2) is recognized,

$$
X\in C_q(D)
\quad\Longleftrightarrow\quad
X\cap Z=\varnothing
\ \text{and}\ 
|X\cap K_i|\le q\text{ for every }i.
\tag{3}
$$

Necessity follows because each covering set avoids $Z$ and contributes at most one coordinate to each clique. For sufficiency, list the selected coordinates within each component in increasing order. Give its first coordinate to class zero, its second to class one, and so on. Each class receives at most one coordinate from each component and none from $Z$. These classes partition $X$ exactly and belong to $D$. Singleton/free components contribute their coordinate to class zero.

Empty classes are permitted because $\varnothing\in D$. Thus an at-most-$q$ cover and exactly $q$ classes with empty classes allowed have the same meaning. The minimum number of nonempty classes is $\max_i|X\cap K_i|$, interpreted as zero for the empty selected set.

A selected forced-zero coordinate gives a singleton obstruction with its zero-quota witnesses. Otherwise, a component load exceeding $q$ gives $q+1$ selected coordinates and references to all their pair-conflict edges. No $q$ admissible classes can accommodate them.

Consequently, the exact upward generators for the complement are

$$
\mathcal G_q=
\{\{z\}:z\in Z\}
\ \cup\
\bigcup_i\binom{K_i}{q+1},
\qquad
2^E\setminus C_q(D)=\uparrow\mathcal G_q.
\tag{4}
$$

A binomial family is empty if its required size exceeds its component. These are literal nonempty generators, with ordinary set union semantics.

### Consuming the accepted probability theorem

For $q=3$, equation (4) uses forced-zero singletons and four-element subsets within the recognized components. The existing [disjoint quota theorem](PARTITION_MATROID_Q3.md), accepted in Commons [#31037](https://github.com/woahwhattheheck/commons/pull/31037), applies directly to equation (2): for arbitrary independent coordinate probabilities in $[0,1]$ and $\mu(D)\ge1/2$, their total product weight is at most $-\log\mu(D)$. In particular, $\mu(D)\ge e^{-1/2}$ suffices for half cost, and the original $2/3$ target does too.

The retained proof is blob `42fc269e1cc57a4e81fd5778ea76d6c6cea5ab3b`. Its authorship, hypotheses and sharpness scope remain with that accepted result. This API neither reruns its proof nor evaluates a probability inequality. It exposes an exact representation that lets a caller use it. No conclusion for arbitrary conflict graphs or arbitrary families follows from a failed recognition.

## 3. Public API

The CommonJS exports are:

- `createQuotaOneIndex(options)`
- `QUOTA_ONE_LIMITS`

The implementation uses standard JavaScript collections and exact bounded integer indices. It needs no dependencies, filesystem, network, native process or general coloring solver. It is usable in connected V8 by evaluating the module source with the standard CommonJS `module` and `exports` objects.

### Input contract

`createQuotaOneIndex({ universe_size, blocks })` uses the universe $E=\{0,\ldots,n-1\}$, where `n = universe_size`. Every block is an object with an integer `capacity` equal to zero or one and a `members` array of coordinate IDs.

IDs must be safe-integer JavaScript numbers in the declared universe. Numeric strings, fractions, infinities and out-of-range IDs are rejected. Values representing zero are normalized to ordinary zero. Repeated member IDs are deduplicated and sorted. Source block order is preserved; equal blocks are not merged in the provenance.

| Bound | Value |
|---|---:|
| Universe size | 0 through 256 |
| Source blocks | At most 4,096 |
| Raw member entries, including duplicates | At most 65,536 |
| Sum of active within-block unordered pairs | At most 262,144 |
| Raw entries in a selected-set query | At most 1,024 |
| Executable cover-class count `q` | 1 through 256 |

The pair bound is checked before pair expansion. It counts a pair again when another source block contains it, because every provenance occurrence is retained. The graph itself has at most $\binom{256}{2}=32640$ distinct edges. Integer operation counts and IDs therefore remain exactly representable as JavaScript numbers.

Malformed object/array/capacity shapes cause `TypeError`; numeric bounds, coordinate errors and resource limits cause `RangeError`. The finite recognition and covering theorems are not restricted to these implementation limits.

### Returned index

`describe()` returns status, statistics, any compression obstruction, limits and actual compilation work.

`snapshot()` returns a complete independent JSON-compatible copy containing:

- normalized original blocks and their active members;
- forced-zero coordinates and all responsible source blocks;
- free coordinates, original/active frequency vectors and component IDs;
- every component and its complete-graph edge count;
- every distinct edge and all source-block indices producing it;
- the exact compressed quota list, or a $P_3$ obstruction;
- limits, statistics and actual work.

Status is `EXACT_DISJOINT_QUOTAS` or `NOT_A_PARTITION_QUOTA_SYSTEM`. In the latter case, `compressed_quotas` is null. Singleton components are included in successful compressed output and marked `is_vacuous: true`. The optional zero-union block has capacity zero and no component ID.

Component IDs are ordered by their least coordinate. Members and edge endpoints are increasing; edge IDs use lexicographic endpoint order. Source-block witness lists preserve increasing input indices. For a nonclique component, the recognizer picks its first nonadjacent pair and uses breadth-first search with increasing neighbors. The first three vertices of that shortest path supply the reported obstruction.

`decompose({ q, selected })` deduplicates and sorts the selected IDs. For a successfully recognized system, it returns:

| Status | Content |
|---|---|
| `COVERABLE` | Exactly `q` class records, allowing empty classes; their disjoint union is the selected set. |
| `NOT_COVERABLE` | A forced-zero singleton or a component's first `q+1` selected coordinates, with retained source-edge references. |

For a nonpartition system, this method throws `NonPartitionQuotaError` and includes the compression obstruction. That exception does not assert that the queried set is uncolorable. The module does not solve general graph coloring.

Returned records are copies of private compilation data; mutating a snapshot or description cannot alter later queries. A snapshot is an export, not a separately authenticated or restorable index. The public constructor consumes the original quota input.

### Work and completeness

The constructor reads every input membership, enumerates every active within-block pair, and merges duplicate edges while retaining all sources. Connected-component traversal then checks whether each simple component has exactly $\binom{|K|}{2}$ edges. A nonclique result needs at most one additional shortest-path search.

Writing $M$ for input membership volume, $P$ for retained pair occurrences and $e$ for distinct edges, sorting plus compilation is bounded by $O(M\log n+P+e\log n+n^2)$. Storage is $O(M+P+n+e)$. No subsets of the universe or candidate colorings are enumerated. Successful cover queries distribute selected coordinates componentwise; obstruction edge IDs are read from the existing graph.

## 4. Actual finite-field consumer

The new input is the affine space $\mathbb F_3^3$, with coordinate IDs

$$
(x,y,z)\longmapsto9x+3y+z,\qquad x,y,z\in\{0,1,2\}.
$$

These are finite-field coordinates. Lines are not ordinary real-plane or integer-grid lines from the separate Erdős 588 work.

Choose one representative of every nonzero direction modulo multiplication by $-1$: its first nonzero coordinate is one. There are $(27-1)/2=13$ directions. For each direction $d$, the cosets

$$
\{a,a+d,a+2d\}
$$

partition the 27 points into nine three-point lines. Arithmetic is coordinatewise modulo three. The source builder visits these cosets and retains all $13\cdot9=117$ lines, sorted by their member IDs.

For distinct $a,b$, the unique third point is $c=-a-b$. It differs from both $a$ and $b$: for example, $c=a$ would give $b=-2a=a$ in characteristic three. Thus every distinct pair lies on exactly one of these lines. The affine collinearity rule and its validity in every dimension are described by Benjamin Lent Davis and Diane Maclagan in [*The Card Game SET*](https://lsgm.uni-leipzig.de/lsgm/Bibliothek/Davis_Maclagan-CardGameSet.pdf), manuscript page 3. The distinct-pair specialization above excludes the all-equal degenerate triple.

Each line receives capacity **one**. Therefore every pair of coordinates conflicts, and the quota system is exactly

$$
D=\{A\subseteq\mathbb F_3^3:|A|\le1\}.
$$

This is a quota representation example; it is not the capacity-two cap-set problem studied elsewhere in the SET literature.

### Retained result

One source construction and one public compiler call produced:

| Quantity | Exact result |
|---|---:|
| Coordinates | 27 |
| Canonical directions | 13 |
| Source line quotas | 117 |
| Normalized source memberships | 351 |
| Frequency of each coordinate | 13 |
| Distinct pair conflicts | 351 |
| Source-line witnesses per conflict | 1 |
| Conflict degree of each coordinate | 26 |
| Clique components | One, with 27 coordinates |
| Compressed quotas | One capacity-one block |
| Compressed coordinate frequency | 1 |
| Forced-zero / free coordinates | 0 / 0 |

The complete dataset is [affine_f3_dimension3_quota_compression.json](affine_f3_dimension3_quota_compression.json). It retains all 27 vectors, 13 directions, 117 lines and original request, the complete compilation snapshot, every pair witness and both actual cover-query results.

The first query selects all 27 coordinates with $q=3$. It returns `NOT_COVERABLE` and the obstruction $[0,1,2,3]$, with all six pair-edge IDs. The second selects the same universe with $q=27$ and returns the complete partition into 27 singleton classes, with minimum nonempty class count 27. No coloring search is performed.

The exact compressed description also gives the following closed-form counts, without enumerating subsets:

$$
|D|=28,\qquad
|C_3(D)|=\sum_{i=0}^3\binom{27}{i}=3304,
$$

$$
|2^E\setminus C_3(D)|=2^{27}-3304=134214424,
\qquad
|\mathcal G_3|=\binom{27}{4}=17550.
$$

The generator count is retained; the 17,550 generators themselves are not enumerated. Every four-element subset is minimal because deleting any member leaves a three-coverable set.

The source builder constructed 117 lines using 234 nonzero scalar point additions. Compilation visited 351 active pair occurrences and 702 neighbor entries. It required no shortest-path search on this clique input. The observed compilation time was 3 ms in this connected-V8 invocation; this is a single observation, not a statistical benchmark. The zero-removal and nonclique-refusal branches are justified above but were not exercised by this zero-free clique consumer.

### Why representation matters

The same elementary finite-field argument works symbolically for $\mathbb F_3^m$: $n=3^m$ points, $n(n-1)/6$ three-point lines, and source frequency $d=(n-1)/2$. Capacity-one line quotas again encode $|A|\le1$.

On this encoding, the bounded-frequency construction's $2d+1$ color bound equals $n$, and covering the whole universe really requires $n$ admissible singleton classes. This explains sharpness of that coloring step on its selected constraint representation. It is not a lower bound on the constant in Talagrand's measure problem.

Exact compression instead exposes a single disjoint quota and lets the accepted $q=3$ probability theorem apply under its stated mass hypothesis. No new computation for another value of $m$ is asserted. A naive attempt to use only within-source-line four-subsets would give no generators at all; for $m\ge2$, it would miss noncoverable four-element sets. The compressed component identifies the required four-element obstructions.

## 5. Connected use

Given the module text and saved dataset obtained through a connected repository read:

```js
const module = { exports: {} };
new Function("module", "exports", moduleText)(module, module.exports);
const data = JSON.parse(datasetText);
const index = module.exports.createQuotaOneIndex(data.affine_input.request);

const description = index.describe();
const fullWitnesses = index.snapshot();
const cover = index.decompose({
  q: 3,
  selected: data.affine_input.points.map(row => row.coordinate_id)
});
```

The saved result is already complete; these calls illustrate the public interface for a later consumer. This delivery executed the new input once and retained it. It replayed no accepted disjoint theorem, finite census, grid configuration or earlier source example. Existing source authorship remains intact; no general-family solution, novelty, external frontier or sponsor action is claimed.
