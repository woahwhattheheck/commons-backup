# Exact navigation in a five-piece triangle hierarchy

This package gives exact finite navigation for one explicitly declared five-piece substitution of a right triangle with side lengths 1, 2 and sqrt(5). At depth 26 it represents
\[
5^{26}=1,490,116,119,384,765,625
\]
labelled leaf triangles using 2,754 saved orientation-count cells. There are 206 distinct orientation classes at that depth. The package supports addresses, exact rational coordinates, orientation-restricted rank/select and point location, including all triangles touching a boundary point.

It does not enumerate those leaf triangles, classify every possible triangle dissection, or claim a new admissible dissection number.

## Source and observation boundary

Radin and Sadun, *An Algebraic Invariant for Substitution Tiling Systems*, Geometriae Dedicata 73 (1998), 21–37, printed page 22, describe a five-piece pinwheel substitution followed by expansion by sqrt(5), repeated on every tile. The construction is credited to Conway and Radin. Radin's *The pinwheel tilings of the plane*, Annals of Mathematics 139 (1994), 661–702, is the original paper locator. The independently indexed author passage gives the 1–2–sqrt(5) right-triangle shape.

Readable primary source: https://web.ma.utexas.edu/users/radin/papers/invariant.pdf .
Original paper locator: https://web.ma.utexas.edu/users/radin/papers/pinwheel.pdf .
Original DOI: https://doi.org/10.2307/2118575 .

The readable source identifies Figure 2 as the substitution diagram, but the screenshot tool returned only an ImageDisplayed text placeholder, not an image payload. No visual diagram comparison was obtained. The matrices and child ordering below are explicitly supplied by this package and proved directly to partition its triangle. They are not asserted to be a literal transcription of the source diagram or its markings. The original paper's full text was not relied on for these affine matrices. A separate Gazette PDF request exceeded the provider's content-length limit and remains held; its indexed attribution is not a full-paper read.

The PPL079 catalogue asks for the integers n for which some triangle can be dissected into n congruent triangles: https://prizeproblems.org/problems/079/ . The attempted FormalConjectures/ErdosProblems/634.lean route returned 404 and was not retried. No independently refreshed general problem status is claimed. This finite coordinate realization and its exact navigation neither classify all n nor establish priority for five-piece substitutions.

## Fixed coordinate template

Let T have vertices O=(0,0), U=(2,0), V=(0,1), and let
\[
A=\begin{pmatrix}2&-1\\1&2\end{pmatrix},\qquad
A^{-1}=\frac15\begin{pmatrix}2&1\\-1&2\end{pmatrix}.
\]
A is a similarity of scale sqrt(5), rotating through theta=atan(1/2). The expanded triangle AT has vertices (0,0), (4,2), (-1,2).

The five expanded children are:

| Child | Right vertex | Long-leg endpoint | Short-leg endpoint |
|---|---|---|---|
| 0 | (0,2) | (0,0) | (-1,2) |
| 1 | (0,1) | (2,1) | (0,0) |
| 2 | (2,2) | (4,2) | (2,1) |
| 3 | (0,1) | (2,1) | (0,2) |
| 4 | (2,2) | (0,2) | (2,1) |

Every child has perpendicular legs of lengths 2 and 1. They partition AT: child 0 is the left portion x<=0; child 1 is the lower portion with 0<=x<=2 and y<=1; child 2 is the portion x>=2. The remaining rectangle [0,2] by [1,2] is divided by the segment from (0,2) to (2,1) into children 3 and 4. The interiors are disjoint, and boundaries may be shared. This is an elementary coordinate partition, not an inference from an unavailable image.

Write each expanded child as R_i T+t_i. The five isometries are declared in the input and retained in the certificate:

| i | R_i | t_i | Quarter turn j_i | Reflection e_i |
|---|---|---|---:|---:|
| 0 | [[0,-1],[-1,0]] | [0,2] | 3 | 1 |
| 1 | [[1,0],[0,-1]] | [0,1] | 0 | 1 |
| 2 | [[1,0],[0,-1]] | [2,2] | 0 | 1 |
| 3 | [[1,0],[0,1]] | [0,1] | 0 | 0 |
| 4 | [[-1,0],[0,-1]] | [2,2] | 2 | 0 |

Here R_i = Rot(j_i*pi/2) diag(1,(-1)^e_i): the rightmost horizontal reflection acts first when e_i=1. Normalize each child back into T:
\[
F_i(x)=A^{-1}(R_ix+t_i)=(B_ix+b_i)/5.
\]
All B_i and b_i have integer entries. The certificate stores these matrices, the normalized vertex numerators, B_i^T B_i=5I and det B_i=+/-5. The compiler's five similarity and containment rows accompany the analytic partition above; area plus containment alone is not used as a substitute for disjointness.

Replacing each triangle F_w(T) by F_w F_i(T) repeats the same partition. Induction gives 5^d congruent triangles of area 5^-d at depth d. Shared boundaries are permitted by the dissection convention.

## Input lineage and bounded construction

Depth 26 is selected from record.modulus in the released unary certificate:

- https://github.com/woahwhattheheck/commons/pull/31589 .
- Merge 11a30052a4bbc1a5faeb702971d09b0f8d2d78f6.
- research/ppl053_unary_frobenius/unary_dictionary_certificate.json.
- Blob 96489f065d98eb60a09c40ece49ae5494e85c440.

Only the scalar parameter is reused. No semigroup, shortest-path or earlier geometric calculation is used or repeated. The complete new input is retained in the construction record, with content identity 97e700fdd3bcea80f2d159204fc71d36eae3e037 (964 bytes). The API accepts this fixed template and a depth at most 128; it does not accept an arbitrary unproved substitution.

## Exact orientations

An orientation is recorded as [k,j,e], meaning Rot(k*theta+j*pi/2) diag(1,(-1)^e). The rightmost horizontal reflection acts first. The angle theta is symbolic: no trigonometric approximation is computed. Composition obeys
\[
(k,j,e)(k',j',e')=
(k+(-1)^e k',\,j+(-1)^e j'\pmod4,\,e\mathbin{\mathrm{xor}}e').
\]
Each child has step [-1,j_i,e_i]. The five address symbols are distinct even when two children have the same orientation step.

These descriptors distinguish actual orthogonal orientations. If theta/pi were rational, z=exp(2i theta)=(3+4i)/5 would be a root of unity. Then z+z^-1=6/5 would be a rational algebraic integer and therefore an integer, a contradiction. Thus different k cannot be absorbed into quarter turns; j is reduced modulo four, and reflection parity is separated by determinant. This elementary argument justifies the geometric interpretation of the finite descriptor classes. No theorem about dense orientations of an infinite plane tiling is needed.

Starting with count one at [0,0,0], the compiler appends each of the five child steps and adds counts of coincident resulting descriptors. The complete tables for every depth 0,...,26 are retained. Their sums are 5^d. This recurrence counts addresses, not graph-isomorphism classes, rigid-motion equivalence classes of tilings, or separately marked versions of a leaf.

For a prefix orientation p and a desired target t, the required remaining orientation is p^-1 t. Looking that value up in the saved table for the remaining depth gives the exact number of allowed suffixes. This supports orientation rank/select and prefix conditioning without another count recurrence. At depth 26, target [0,0,0] has 35,621,244,278,709,341 addresses.

## Addresses and rational leaf geometry

An address is a string over digits 0,...,4. Its length is its depth, and its zero-based rank is the base-five value of that string, retaining leading zeroes to specify depth. Ordering is lexicographic in addresses. Geometry is not ordered by position.

Starting from M=I, v=0 and D=1, appending child (B,b)/5 gives
\[
M'=MB,\quad v'=Mb+5v,\quad D'=5D.
\]
The previous M is used in both formulas. At depth d, D=5^d, and F_w(x)=(Mx+v)/D. The three exact vertex numerators are v, v+2M[:,0] and v+M[:,1], over the common denominator D. Fractions need not be reduced.

Induction gives M^T M=DI. Every leaf therefore has squared side lengths 1/D, 4/D and 5/D and area 1/D. The returned affine trace records each requested composition. It describes only the selected address; it does not imply that all sibling coordinates were compiled or stored.

## Closed-boundary point location

A point is supplied as integer numerators (x,y) over one positive denominator q. It belongs to T exactly when x>=0, y>=0 and x+2y<=2q. To test child i, use
\[
F_i^{-1}(p)=R_i^T(Ap-t_i).
\]
The inverse matrix and translation are integers, so the local numerator changes but its denominator q remains fixed. A branch is traversed only when its local point satisfies the three closed inequalities.

This returns **every** depth-d triangle containing the point, including all triangles sharing a vertex or edge. A point on a boundary is not assigned arbitrarily to one owner. Each match retains its address/rank, final local numerators and which canonical boundary equalities hold. A point outside T returns an empty complete result.

A visit cap is explicit. If reached, locate returns complete:false, the matches found so far and its unresolved frontier. Such a result must not be described as exhaustive. All seven actual calls completed within the default 20,000-visit limit.

## Public API

~~~javascript
const { openIndex } = require('./five_piece_triangles.cjs');
const certificate = require('./depth26_triangle_certificate.json');
const reader = openIndex(certificate.record);

reader.summary();
const address = reader.selectAddress(26, '343');
reader.geometry(address);
reader.selectOrientation(26, [0,0,0], '0');
reader.locate(26, {x:'1', y:'2', den:'5'});
~~~

| Method | Meaning |
|---|---|
| buildIndex(input) | Construct the fixed template records and all orientation tables through input.depth. |
| openIndex(record) | Structurally load the saved record and index its retained rows. |
| summary() | Maximum depth, total triangles, orientation classes and original construction work. |
| histogram(depth) | Full saved orientation count table for a requested depth. |
| selectAddress(depth,rank) | Convert a bounded rank into its fixed-length base-five address. |
| rankAddress(address) | Convert an address into a decimal rank. |
| orientation(address) | Compose its symbolic orthogonal descriptor. |
| geometry(address) | Compute requested exact affine coordinates, side/area formulas and trace. |
| selectOrientation(depth,target,rank) | Select within one orientation family using saved suffix counts. |
| rankOrientation(address) | Its rank among addresses with the same orientation. |
| countPrefix(depth,target,prefix) | Count target-orientation completions of a given address prefix. |
| locate(depth,point,limit?) | Exhaustive closed-boundary location, or an explicit incomplete cap result. |
| work(), snapshot() | Return copies of reader counters and the saved construction. |

Ranks and coordinates use canonical decimal strings; signed point numerators are allowed. Numeric strings are capped at 1024 digits. Depth is a safe integer through the saved depth, at most 128; j is in 0,...,3 and e in {0,1}. The point-location visit limit is an integer from 1 through 100,000. Empty address denotes the whole initial triangle at depth zero.

Structural loading does not independently authenticate a foreign record, reprove a supplied partition or recompute its orientation recurrence. Use the matching trusted record. Returned arrays are copies. Larger depths and incomplete-cap branches were source-inspected, not exercised.

## Actual retained evidence

Frozen source: b8676dd52aef7c186e72b205ef4f278f335adfac, 9,162 bytes.
The sole construction produced 2,754 orientation cells and 12,740 transition updates, together with five base similarity records. It enumerated zero leaf triangles. Its complete 61,783-byte outcome was banked as e4685ac854ae28d1830b551e8d2a22308ecbc894.

A fresh reader instance produced 30 complete query outputs, banked as 4fcf23aec98c5c0649da3bc355ff3c277c44e2e4 (47,659 bytes). It returned four full saved histograms; five selected addresses and their geometries; three orientation selections and inverse ranks; another selected geometry; one prefix count; and seven point-location results.

| Point | Number of containing depth-26 leaves | Visited nodes | Child tests |
|---|---:|---:|---:|
| (0,0) | 2 | 53 | 255 |
| (2,0) | 1 | 27 | 130 |
| (0,1) | 1 | 27 | 130 |
| (1/5,2/5) | 8 | 204 | 980 |
| (2/3,1/3) | 2 | 51 | 245 |
| (1/5,1/5) | 8 | 197 | 945 |
| (2,1), outside T | 0 | 0 | 0 |

Reader work totals: 405 orientation lookups, 237 orientation-composition steps, 156 affine-composition steps, 559 point nodes and 2,685 child tests. Saved orientation cells indexed: 2,754. Orientation recurrence updates and base-template reconstruction in the reader: zero.

These are finite outputs for the declared coordinate system and address order. Neither the 5^26 count nor the source attribution is a new dissection theorem or novelty claim. The unavailable diagram, held Formal634 route and original PDF access limits remain explicit. No native executor, source-paper proof audit, accepted calculation replay or sponsor submission occurred.

Publication uses guarded serial Contents operations with exact text, lineage, preimage and expected-head checks. File modes and the whole repository tree are not independently verified by that method.
