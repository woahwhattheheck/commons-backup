# Singer difference sets and a saved projective-plane index

## Delivered result

The accepted GF(13³) power-cycle record now supports a separate, exact finite
construction. Its trace-zero exponent classes modulo 183 are

\[
D=\{4,7,32,50,52,61,85,91,101,108,122,123,127,135\}.
\]

Every nonzero residue has exactly one ordered representation \(b-a\) with
distinct \(a,b\in D\). All 182 witnesses are retained. All 105 unordered
two-sums, including the 14 diagonal pairs, are distinct modulo 183 and are
also retained.

The positive translation

\[
D-3=\{1,4,29,47,49,58,82,88,98,105,119,120,124,132\}
\]

is an ordinary integer Sidon set. Consequently **\(h(132)\ge14\)**. The
difference-count bound proves that 14 is the maximum size of a Sidon subset
of the cyclic group \(\mathbb Z/183\mathbb Z\). It does **not** prove
\(h(132)=14\).

The translates \(\ell+D\), labelled by \(\ell\in\mathbb Z/183\mathbb Z\),
form the associated finite projective plane: 183 points, 183 lines, 14 points
per line and 14 lines through each point. Its 2,562 incidences are represented
implicitly by \(D\) and modular translation. The artifact does not enumerate
every pair of points or every pair of lines.

These points and lines are finite-field incidence objects. Their integer
residue labels are names, not coordinates of a configuration in the real
Euclidean plane.

## Sources and mathematical scope

This is the classical Singer construction, credited to J. Singer,
[*A theorem in finite projective geometry and some applications to number
theory*](https://doi.org/10.1090/S0002-9947-1938-1501951-4),
*Transactions of the American Mathematical Society* 43(3) (1938), 377–385.
The trace-zero quotient description used here is stated explicitly by
Mészáros, Rónyai and Szabó in
[*Singer difference sets and the projective norm graph*](https://arxiv.org/pdf/1908.05591),
§1.2, printed page 3: the nonzero trace-zero elements of
\(\mathbb F_{q^3}\), modulo multiplication by \(\mathbb F_q^*\), give a cyclic
\((q^2+q+1,q+1,1)\) difference set. The original 1938 paper was not newly read
for this operation; the directly read author account supplies the trace model
and historical attribution.

The [Formal Conjectures statement of Erdős 30](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/30.lean)
defines \(h(N)\) as the largest cardinality of a Sidon subset of
\(\{1,\ldots,N\}\). Its main question is whether, for every
\(\varepsilon>0\),

\[
h(N)=\sqrt N+O_\varepsilon(N^\varepsilon).
\]

It records a separate, stronger \(O(1)\) question. The complete statement file
was read at Git blob `fa05973a5c12c642835b9975a518334f8f166dad`; its
research-open annotations and local placeholders were observed without
executing Lean or reviewing a proof.

The [May 5, 2026 author preprint by Hulak, Ramos and de Queiroz](https://arxiv.org/html/2605.03274v1),
§§1.1 and 1.4, explicitly includes diagonal sums in the Sidon convention,
describes the sharp error-term question as open, and does not claim an
unconditional resolution. This is a dated source statement, not an exhaustive
later-literature assessment.

Here a Sidon set has unique sums of **unordered pairs with repetitions
allowed**. Thus \(a+a\) is included, while \((a,b)\) and \((b,a)\) describe the
same sum representation. Nonzero difference witnesses instead use **ordered,
distinct** elements. This distinction determines the 105 sum rows and the
182 difference rows.

The new finite certificate and saved navigation settle neither asymptotic
question. The numerical example is an application of established
constructions, with no claim of a new Singer theorem, extremal priority,
external record or prize result.

## Identified upstream input

The complete accepted source is:

| Field | Value |
|---|---|
| Repository | `woahwhattheheck/commons` |
| Path | `research/ppl009_erdos241_b3/prime13_cubic_b3_construction.json` |
| Original accepted carrier | [Commons #31278](https://github.com/woahwhattheheck/commons/pull/31278) |
| Pinned commit used here | `435db8587c0934b6f60301a132d437a6ac6f915f` |
| Complete source Git blob | `2b77e0e8dc97c5107ab5a4e5cca162a92c12de38` |
| UTF-8 bytes | 47,929 |
| Relevant field | `result.power_cycle.codes` |

The source was read in full and its independent Git blob identity matched the
accepted pin before the new computation. Its original field construction,
primitivity evidence, degree-three argument and B₃ contribution remain
upstream work.

The retained result specifies \(q=13\), a field of size 2,197, multiplicative
order 2,196, cubic coefficients `[11,0,0]`, and generator code 20. In the
basis \(1,\alpha,\alpha^2\),

\[
\operatorname{code}(c_0+c_1\alpha+c_2\alpha^2)
   =c_0+13c_1+169c_2,\qquad \alpha^3=2.
\]

The accepted table interprets `codes[e]` as \(\theta^e\). This operation does
not re-establish that interpretation by multiplication or reconstruct the
cycle. It uses the table as an identified premise.

For every residue \(e=0,\ldots,182\), the compiler reads exactly three saved
entries, at exponents

\[
e,\quad 13e\bmod2196,\quad169e\bmod2196.
\]

It decodes their coefficient vectors, adds the coordinates modulo 13, and
retains the complete decision for

\[
\operatorname{Tr}(\theta^e)
 =\theta^e+\theta^{13e}+\theta^{169e}.
\]

The source field's zero element is excluded because every table entry is a
nonzero power. Residue **zero** is a different object: it denotes the scalar
coset of \(\theta^0=1\), and is a valid candidate label. It happens not to be in
this \(q=13\) difference set, because its trace is 3. The general adapter does
not prohibit residue zero from the selected set.

The 183 new trace decisions are complete in the derived snapshot. The 2,196
upstream power codes are not duplicated in the new artifact; their immutable
source remains directly usable.

## Why the trace model gives the required finite object

The following explains the cited construction; it is not a new construction
claim.

Write \(K=\mathbb F_{q^3}\), \(F=\mathbb F_q\), and
\(v=q^2+q+1\). The scalar quotient \(K^*/F^*\) is cyclic of order \(v\).
A primitive \(\theta\) identifies its elements with exponent residues modulo
\(v\). Multiplication by a nonzero scalar preserves the equation
\(\operatorname{Tr}(z)=0\), so the trace condition is well-defined on these
cosets.

The trace is an \(F\)-linear map \(K\to F\). It is nonzero: the polynomial
\(X+X^q+X^{q^2}\) is nonzero and has degree \(q^2<q^3\), so it cannot vanish
at every element of \(K\). Its kernel has dimension two over \(F\). The
nonzero elements in that kernel comprise

\[
\frac{q^2-1}{q-1}=q+1
\]

scalar cosets.

Fix a nonidentity quotient element \(tF^*\). The two linear forms

\[
z\longmapsto\operatorname{Tr}(z),
\qquad
z\longmapsto\operatorname{Tr}(tz)
\]

are independent. Otherwise the second would equal
\(c\operatorname{Tr}(z)\) for some \(c\in F\), so
\(\operatorname{Tr}((t-c)z)\) would vanish for every \(z\). Since
\(t\notin F\), multiplication by \(t-c\) permutes \(K\), contradicting the
nonzero trace map.

The common kernel therefore has dimension one. Its nonzero elements give
exactly one scalar coset. In exponent notation this says that for every
nonzero \(r\bmod v\), exactly one ordered pair \(a,b\in D\) satisfies
\(b-a=r\).

The public adapter accepts prime base fields only, with an identified
degree-three source. The cited theorem allows prime powers more generally;
that larger source scope does not imply that this implementation supports
nonprime base fields.

### The explicit certificate supplies its own finite coverage

For the actual result, the compiler separately records every ordered
difference and every unordered sum. The reader checks the arithmetic in
these saved rows. Thus the finite difference-set property can be assessed
from the 14 explicit residues and 182 rows without re-establishing the field
provenance.

There are \(14\cdot13=182\) ordered distinct pairs. The difference table has
one valid row for each residue 1 through 182. Two identical ordered pairs
cannot occur at different residues, so these rows cover all ordered distinct
pairs exactly once.

If \(a+b=c+d\) modulo 183, a nontrivial equality would give the same nonzero
ordered difference \(a-c=d-b\). Uniqueness forces \(a=d\) and \(c=b\), so the
unordered pairs agree. This argument includes diagonal sums.

Conversely, a cyclic Sidon set of size \(s\) has \(s(s-1)\) distinct nonzero
ordered differences. Therefore

\[
s(s-1)\le182.
\]

Size 15 would require 210 such residues. The retained size-14 set reaches
the resulting upper bound. This is an exact optimum **inside the cyclic
group of order 183**.

Any ordinary integer equality between pair sums of \(D-3\) would also be a
modular equality after the common translation cancels. Hence the displayed
positive set is an ordinary Sidon set. Its endpoint 132 is a finite lower-bound
example. No cyclic-cut or affine-orbit optimization was performed, and no
optimality among all integer sets in \([1,132]\) follows.

### Joins and meets from one difference witness

Store a difference row as

\[
r=b-a,\qquad a,b\in D.
\]

For distinct point labels \(x,y\), take the row at \(r=y-x\). Their unique line
is

\[
\ell=x-a=y-b\pmod{183}.
\]

For distinct line labels \(\ell,m\), take the row at \(r=m-\ell\). Their unique
intersection point is

\[
x=\ell+b=m+a\pmod{183}.
\]

This orientation is intentional: joins use the row's `from` offset for the
first point, while meets use its `to` offset for the first line.

Each line \(\ell+D\) has 14 points. The lines through a fixed point \(x\) are
\(x-d\), one for every \(d\in D\), so there are 14 of them. These facts and
the unique join/meet property give the projective-plane incidence structure.
Nondegeneracy also follows: choose two points on a line and one point off it.
The three sides of that triangle contain \(3(q+1)-3=3q\) points, leaving
\((q-1)^2>0\) points outside when \(q\ge2\). An outside point completes a
quadrangle.

No search over the \(\binom{183}{2}\) point pairs or line pairs is required.

## Public API

The module is plain CommonJS without I/O, imports or external dependencies.
It can be loaded directly in the connected V8 runtime.

```js
const moduleBox = { exports: {} };
new Function("module", "exports", moduleText)(
  moduleBox, moduleBox.exports
);
const {
  SINGER_PLANE_LIMITS,
  compileSingerPlaneFromBoseChowla,
  openRetainedSingerPlane
} = moduleBox.exports;
```

### Open the complete saved artifact

The ready-to-use file is `prime13_singer_plane.json`. Its top-level
`snapshot` is the complete derived index.

```js
const saved = JSON.parse(savedArtifactText);
const plane = openRetainedSingerPlane(saved.snapshot);

plane.join(53, 60);          // unique line 135
plane.meet(53, 60);          // unique point 161
plane.pairForSum(8);         // one pair: 4 + 4
plane.linePage(53, { start: 0, limit: 32 });
plane.pencilPage(60, { start: 0, limit: 32 });
```

The reader takes a detached JSON copy. All returned arrays, objects, pages and
snapshots are detached as well. Mutating a result does not change subsequent
queries.

### Compile a new identified source

This is the constructor used once for the recorded consumer:

```js
const built = compileSingerPlaneFromBoseChowla({
  record: JSON.parse(acceptedFieldArtifactText),
  provenance: {
    repository: "woahwhattheheck/commons",
    path: "research/ppl009_erdos241_b3/prime13_cubic_b3_construction.json",
    commit: "435db8587c0934b6f60301a132d437a6ac6f915f",
    git_blob_sha: "2b77e0e8dc97c5107ab5a4e5cca162a92c12de38"
  }
});

if (built.status !== "EXACT_PLANAR_DIFFERENCE_INDEX") {
  // Retain the returned stop/diagnostics. There is no complete index to open.
}
const plane = openRetainedSingerPlane(built.snapshot);
```

`record` may be the recognized
`erdos241.prime13_cubic_b3_run/v1` wrapper or a completed
`erdos241.bose_chowla_b3/v1` result directly, as an object or JSON text.
The direct result form permits other identified prime-cubic source records
within the stated cap. The actual operation exercised the full wrapper at
\(q=13\) only.

The source's assertion that it is a completed field construction is a
mathematical input premise. The public API validates its dimensions, schema,
encoding and accessed code ranges. It does not prove primality,
irreducibility or cycle completeness. The source-reference fields are
structurally checked; the module does not fetch or hash an external file.
This particular run separately read and hashed the full upstream artifact.

### Method contracts and ordering

All point, line, sum and candidate-exponent labels are safe integer Numbers
in `0..modulus-1`. They are canonical residues; the reader rejects negative
or out-of-range labels rather than silently reducing them. Ranks are
zero-based safe integer Numbers.

| Method | Contract |
|---|---|
| `summary()` | Exact finite counts and scope. |
| `source()` | Detached construction header and source identity. |
| `differenceSet()` | Increasing canonical residue array. |
| `traceRow(e)` / `tracePage(options)` | Saved trace records in exponent-residue order. |
| `differenceWitness(r)` | Saved ordered witness for nonzero `r`. Zero is rejected because it has diagonal witnesses rather than a unique distinct pair. |
| `differencePage(options)` | All difference rows in increasing nonzero-residue order. |
| `incidence(point,line)` | Membership of `point-line` in the saved set, including the set index when present. |
| `join(x,y)` | Unique line through two distinct points. Equal points are rejected; use a pencil query for the full family. |
| `meet(l,m)` | Unique point on two distinct lines. Equal lines are rejected; use a line query for their points. |
| `linePage(line,options)` | Incident points in increasing numerical label order, with offsets and ranks. |
| `pencilPage(point,options)` | Incident lines in increasing numerical label order, with offsets and ranks. |
| `selectPointOnLine(line,rank)` | Select one row in that line's numerical point order. |
| `rankPointOnLine(line,point)` | Rank in the same order, or `null` for a nonincident point. |
| `selectLineThroughPoint(point,rank)` | Select one row in the pencil's numerical line order. |
| `rankLineThroughPoint(point,line)` | Rank in the same order, or `null` for a nonincident line. |
| `pairForSum(s)` | Count 0 or 1 and its saved unordered representation, if any. |
| `pairPage(options)` / `selectPair(rank)` | Unordered pairs in lexicographic order of their increasing canonical summands. |
| `rankPair([a,b])` | Same pair rank after ordering the two supplied summands; `null` if either is outside \(D\). Equal summands are allowed. |
| `positiveLift()` | The saved ordinary integer translation beginning at 1, its size and endpoint. |
| `snapshot()` | A detached complete snapshot; no compiler call. |
| `statistics()` | Reader load checks and query counters. |

Page options are `{start,limit}`. The default start is zero and default limit
is 256. A start equal to the family size returns an empty final page.
`next_start:null` denotes the end. Numerical line/pencil order can differ
from the order of the underlying translated elements of \(D\); the explicit
rank fields preserve this distinction.

The diagonal pair \((4,4)\) is rank zero and has sum 8. The pair
\((4,135)\), also accepted when supplied as `[135,4]`, has rank 13.

## Reader validation and limits

The saved reader checks:

- the supported snapshot schema, dimensions, source-reference shape and sorted
  distinct residue set;
- all trace-record shapes and their correspondence to the saved selected-set
  flags, without redoing Frobenius or trace arithmetic;
- every saved nonzero difference row against its two selected residues,
  covering all nonzero labels exactly once;
- every saved unordered sum row and its rank, including complete diagonal
  coverage, distinct residues and the saved sum lookup;
- the positive lift and finite summary identities.

Thus the loader validates the explicit finite difference/sum certificate.
It does not certify that an arbitrary caller-supplied trace code came from
the cited upstream field file. That provenance remains separately identified.
The distinction is useful: the difference certificate supports the finite
incidence structure even when the reader has no field table.

| Resource | Hard limit or behavior |
|---|---|
| Base prime | Identified prime \(2\le q\le31\); nonprime prime-power base fields are unsupported. |
| Cycle codes | At most 29,790, matching \(31^3-1\). |
| Trace rows | At most 993, matching \(31^2+31+1\). |
| Combined difference and sum rows | At most 2,048. |
| JSON input/snapshot | At most 2,000,000 characters. |
| Page size | 1 through 256. |
| Arithmetic | Bounded integer Numbers; all stored arithmetic is below the exact-integer range. |
| I/O or native runtime | None. |

Optional `max_trace_rows` and `max_pair_rows` may lower the compile budgets,
including to zero. Required sizes are known before trace work begins. A
preflight budget refusal returns `INCOMPLETE_BUDGET` and `snapshot:null`
with zero trace lookups. A final snapshot-size refusal retains its work and
stop details but also returns no complete snapshot.

Schema, range and contract violations throw a `RangeError`. Invalid JSON or
an unserializable object may instead propagate the standard JSON error.
Trace inconsistency or an unexpected
selected cardinality returns `INVALID_PREMISE_OR_TRACE_RESULT` with the
new trace records and diagnostics. Difference or sum collisions return
`NOT_A_PLANAR_DIFFERENCE_INDEX` with the resulting records and diagnostics.
None of these states is accepted by the saved reader. No incomplete result
is promoted to a theorem or silently resumed.

Only the identified \(q=13\) source and its saved queries were exercised.
Other supported primes, refusal branches, nonincident/null branches and
invalid-input branches were source-inspected. No synthetic suite or larger
input search was run.

## Complete actual consumer

The source was frozen at Git blob
`171abd0a5332617eb6c3874617e6e1926dd615db` before the single compilation.

| New compilation work | Count |
|---|---:|
| Trace records | 183 |
| Retained power-code lookups | 549 |
| Code decodings | 549 |
| Coefficient sums modulo 13 | 549 |
| Unordered pairs visited | 105 |
| Ordered difference rows | 182 |
| Sum rows | 105 |
| Field multiplications | 0 |
| Primality, irreducibility or generator/cycle tests | 0 |
| Upstream B₃ triple enumeration | 0 |
| Complete point-pair or line-pair enumeration | 0 |

The compact snapshot contains 47,997 characters. One connected V8 observation
took 2 ms for compilation. This single observation is not a benchmark.

A fresh V8 invocation opened the saved snapshot and made exactly 16 queries:

| Query group | Retained result |
|---|---|
| Summary | 183 points and lines; size 14; 105 represented and 78 unrepresented sum residues. |
| Trace at 4 | Exponents \([4,52,676]\), codes \([1469,1196,1898]\), zero trace. |
| Trace at 0 | Exponents \([0,0,0]\), codes \([1,1,1]\), trace coefficient vector \([3,0,0]\). |
| Two difference pages | 96 plus 86 rows: all 182 witnesses, final cursor exhausted. |
| One sum page | All 105 unordered pair rows, final cursor exhausted. |
| `join(53,60)` | Line 135, from the unique difference \(108-101=7\). |
| `meet(53,60)` | Point 161, using the same difference row with the meet orientation. |
| Line 53 and pencil through 60 | All 14 rows from each finite family. |
| Point selection on line 60, rank 7 | Point 112, using offset 52. |
| Rank of line 53 through point 161 | Rank 4. |
| Sum residue 8 | One representation, \(4+4\). |
| Sum residue 1 | One representation, \(61+123=184\equiv1\). |
| Rank of pair `[135,4]` | Rank 13. |
| Positive lift | The complete 14-element set ending at 132. |

The line 53 page contains

\[
\{5,57,60,85,103,105,114,138,144,154,161,175,176,180\}.
\]

The pencil through point 60 contains line labels

\[
\{8,10,28,53,56,108,116,120,121,135,142,152,158,182\}.
\]

Loader work included 182 saved difference arithmetic checks and 105 saved
sum arithmetic checks. The queries returned 315 page rows and formed 56
translated incidence labels. Field multiplication, trace recomputation, cycle
reconstruction and pair enumeration counters all remained zero. Query
arithmetic and loader witness checks are explicitly separate from rerunning
the compiler.

The reader's observed load/query times were 4 ms and 6 ms, respectively.
They are also single observations, with no timing comparison or throughput
claim.

## Files and retained custody

| File | Contents |
|---|---|
| `singer_plane_index.cjs` | Public bounded constructor and saved reader. |
| `prime13_singer_plane.json` | Complete source references, all trace/difference/sum records, positive lift, all 16 query outputs and counters. |
| `SINGER_PLANE_API.md` | Definitions, derivation, contracts, limits, sources and finite result. |
| `README.md` | Entry point and concise scope. |

The complete data has Git blob
`5561a91eddf8cfd7911641702b60cd51e308078d` and 181,456 UTF-8 bytes.
Its top-level `snapshot` is directly accepted by
`openRetainedSingerPlane`. Its `retained_reader.results` includes the
complete exported pages, alongside every other actual query result.

The source, data and guide preserve the original field/B₃ authorship and
classical Singer attribution. No prior finite field construction, accepted
B₃ proof or earlier geometry computation was replayed.
