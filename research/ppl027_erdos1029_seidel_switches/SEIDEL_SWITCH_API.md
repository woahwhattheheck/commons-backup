# A complete finite Seidel-switch index for Paley(13)

## Result and delivered scope

The calculation classifies all **4096** Seidel switches of the labelled Paley graph on \(\mathbb F_{13}\), after fixing the switch bit at vertex 0 to zero. **Only code 0 avoids a monochromatic \(K_4\)**. Every nonzero code creates at least **four** monochromatic four-vertex sets, and exactly **13** codes attain four.

This is a finite obstruction to obtaining another admissible colouring within this particular switch orbit. It is not a classification of all two-colourings of \(K_{13}\), all graph-isomorphism classes, or all Ramsey constructions.

The complete record contains:

- The source graph, its six square-residue witnesses and all 39 red edges.
- Every one of the \(\binom{13}{4}=715\) four-vertex rows.
- All 130 locally switchable four-sets and their 220 forbidden switch patterns.
- The monochromatic-four-set count and first-obstruction index for every one of the 4096 switch codes.
- The complete count histogram and all 13 minimum nonzero codes.
- Fourteen fresh saved-reader responses, including explicit six-edge obstructions and conditional-family queries.

| File | Purpose |
|---|---|
| [seidel_switch_index.cjs](seidel_switch_index.cjs) | Pure CommonJS source-family constructor, switch classifier and saved reader |
| [paley13_switch_family.json](paley13_switch_family.json) | Complete input, local patterns, classification and query records |
| [README.md](README.md) | Entry point and concise result |

The executed source blob is `a54df8ccc36761496d822dc6ed562dafdd23fda0`. The complete data blob is `39bbfc4245c974a460c97c7cd65c387a5a5b205f`, occupying **494,532 bytes**. The source was unchanged after the consumer.

## Mathematical sources and the original question

Lim and Praeger, [*On Generalised Paley Graphs and Their Automorphism Groups*](https://arxiv.org/pdf/math/0605252), Introduction, give the classical Paley definition over a finite field \(\mathbb F_q\) with \(q\equiv1\pmod4\). Its vertices are the field elements, and distinct \(x,y\) are adjacent when \(x-y\) is a nonzero square. The square set equals its negative, making the graph undirected. Their Section 2.1 uses finite simple undirected graphs.

The switching convention is the standard one described in Brouwer and Haemers, *Spectra of Graphs* (2012), Section 1.8.2, [indexed primary-book text](https://citeseerx.ist.psu.edu/document?doi=8d952820b03b6688ce2a62a8e0fe1842691e079c&repid=rep1&type=pdf): complement edges across a chosen vertex subset and its complement while leaving the two induced subgraphs unchanged. In Seidel-matrix notation, \(S=J-I-2A\) changes to \(DSD\), where the selected diagonal entries of \(D\) are \(-1\). These definitions retain their prior attribution; the finite index makes no formula-novelty claim.

The [FormalConjectures statement of Erdős problem 1029](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/1029.lean), observed at Git blob `1822dfad226c16436872a5610d95ae77c25ce671`, asks whether
\[
\frac{R(k)}{k\,2^{k/2}}\longrightarrow\infty.
\]
Here \(R(k)\) is the least number of vertices forcing a monochromatic \(K_k\) in every two-colouring of the distinct pair-edges of a complete graph. The observed formal file has a research-open annotation and a placeholder proof. That annotation is source metadata, not an independently established current literature frontier.

The present compiler explores a fixed finite switch orbit. It does not prove an asymptotic bound for \(R(k)\), calculate a new Ramsey number, or claim that all possible edge completions lie in that orbit.

## Labels, colours and the switch-set quotient

The graph has fixed labels \(0,\ldots,n-1\). Its supplied red edges have colour 1; every other unordered pair of distinct vertices has colour 0, called blue. Loops are excluded. Duplicate red-edge input records are deduplicated and do not create multiple edges.

For a switch assignment \(s:V\to\{0,1\}\), write
\[
e^s_{uv}=e_{uv}\mathbin{\oplus}s_u\mathbin{\oplus}s_v,
\]
where \(\oplus\) is addition modulo 2. Thus precisely the edges crossing the switch cut change colour.

Replacing every switch bit by its complement produces the same colouring. Conversely, if two assignments produce the same colour on every pair, their difference \(r\) satisfies \(r_u\oplus r_v=0\) for every pair. It is constant, so the two assignments are equal or complementary. Fixing \(s_0=0\) therefore represents each switch colouring exactly once. The one-vertex case has one assignment as well.

This quotient does **not** identify graph isomorphisms or global colour interchange. The API retains the given vertex labels and the red/blue convention. For \(n=13\), it examines \(2^{12}=4096\) colourings within the much larger set of \(2^{78}\) arbitrary labelled two-colourings.

Vertex \(v\ge1\) has code weight \(2^{v-1}\). Ranks follow **increasing integer code**. That order is different from lexicographic order on the lists of switched vertices. Code 1 switches vertex 1; code 4095 switches all vertices except 0 and represents the same operation as switching vertex 0.

## Exact four-vertex reduction

For each increasing four-set \(Q=(a,b,c,d)\), retain its six original edge bits in the order
\[
ab,\ ac,\ ad,\ bc,\ bd,\ cd.
\]
Retain the parity of each of its four triangles:
\[
abc,\ abd,\ acd,\ bcd.
\]
A switch adds each vertex bit twice to a triangle edge sum, so every triangle parity is invariant.

If the switched four-set is monochromatic with colour \(t\), every triangle parity is \(t\), because three copies of \(t\) sum to \(t\) modulo 2. Thus all four original triangle parities must agree.

This condition is also sufficient. Choose the local bit at \(a\), denoted \(\varepsilon\), and set
\[
s_b=\varepsilon\oplus e_{ab}\oplus t,\qquad
s_c=\varepsilon\oplus e_{ac}\oplus t,\qquad
s_d=\varepsilon\oplus e_{ad}\oplus t.
\]
The three edges incident to \(a\) then have colour \(t\). For another edge, such as \(bc\),
\[
e_{bc}\oplus s_b\oplus s_c
=e_{bc}\oplus e_{ab}\oplus e_{ac}=t
\]
by the corresponding triangle parity. The other edges follow identically.

Therefore a four-set with mixed triangle parities can never become monochromatic by switching. A four-set whose parities all equal \(t\) has exactly two complementary local switch assignments yielding a monochromatic four-set, both of colour \(t\). If it contains vertex 0, only the assignment with \(s_0=0\) is retained.

The actual source graph has 130 switchable four-sets and 585 four-sets with mixed parity. Forty switchable sets contain vertex 0 and supply one retained pattern each. The other 90 supply two, giving \(40+2\cdot90=220\) forbidden patterns. Every four-set remains in the saved record, including those with no forbidden pattern.

## From local patterns to complete classification

A forbidden pattern is stored as a cube \((m,r)\), where \(m\) marks the constrained nonzero vertices and \(r\) gives their required switch bits. A full switch code \(z\) matches exactly when
\[
z\mathbin{\&}m=r.
\]
Unconstrained bits are free. The compiler enumerates their subsets once for each cube, marking all matching full codes.

For each code, it increments the monochromatic-four-set count and retains the first matching cube in deterministic four-set/phase order. The two cubes belonging to one four-set are disjoint. Thus a code is incremented exactly once for each monochromatic four-set, not once per an ambiguous witness representation.

Every possible monochromatic \(K_4\) has a four-vertex set and hence appears among the compiled rows. The local argument proves that its switch must match one of that row's cubes. Conversely, each cube produces the claimed monochromatic four-set. It follows that the expansion classifies every switch, and a code is admissible precisely when its count is zero.

Each switchable four-set covers exactly one eighth of the gauge-fixed switch universe: either one pattern constrains three variable bits, or two patterns constrain four. Consequently the actual expansion has
\[
4096\cdot130/8=66560
\]
code/cube incidences. This replaces testing all 715 four-sets separately in each of the 4096 switched graphs. The compiler still retains every code's complete count and first witness.

The saved first-witness index is an explicit shared certificate: it identifies a stored cube, that cube identifies its stored four-set and colour, and the source adjacency is retained. A reader can reconstruct the six coloured edges for that witness without re-expanding the switch family.

## Complete result

The full histogram counts monochromatic four-sets of **both** colours together.

| Monochromatic four-sets | Switch codes |
|---:|---:|
| 0 | 1 |
| 4 | 13 |
| 8 | 78 |
| 10 | 78 |
| 12 | 156 |
| 13 | 208 |
| 14 | 390 |
| 15 | 364 |
| 16 | 468 |
| 17 | 988 |
| 18 | 624 |
| 19 | 624 |
| 20 | 26 |
| 22 | 78 |

The unique admissible code is 0. The nonzero minimum is four, attained at codes
\[
1,2,4,8,16,32,64,128,256,512,1024,2048,4095.
\]
These represent the thirteen single-vertex switch operations, using the complement representative for vertex 0. The list is read from the retained complete classification; it was not obtained by a second switch calculation.

The complete family being a singleton, all switch bits are forced to zero in its normalized representation and every pair colour equals the original colour. This is an outcome of the whole switch classification, not an assumption imposed on the input.

For code 1, the saved reader reconstructs a **blue \(K_4\) on \([0,1,5,11]\)**:

| Pair | Original colour | Endpoint switch bits | New colour |
|---|---:|---|---:|
| 0,1 | 1 | 0,1 | 0 |
| 0,5 | 0 | 0,0 | 0 |
| 0,11 | 0 | 0,0 | 0 |
| 1,5 | 1 | 1,0 | 0 |
| 1,11 | 1 | 1,0 | 0 |
| 5,11 | 0 | 0,0 | 0 |

It also reconstructs code 4095's blue \(K_4\) on \([0,1,3,9]\), and a third obstruction for code 2047. These are fresh six-edge query calculations using saved witnesses, not repeated four-set or switch enumeration.

The condition \(s_1=1\) has no admissible completion **within this orbit**, because the complete admissible family is \(\{0\}\). The condition that pair \(0,1\) remain red and pair \(0,2\) remain blue retains the original colouring. The single code-1 witness is an example of exclusion; the emptiness statement for all assignments with \(s_1=1\) rests on the full classification.

## Public constructor and reader

The module exports:

- `paleyPrimeGraph(prime)`, a convenience input constructor for exactly the fixed primes 5, 13 and 17.
- `compileSeidelK4Family(graph)`, the complete bounded switch classifier.
- `openRetainedSeidelK4Family(snapshot)`, the saved reader.
- `SEIDEL_SWITCH_LIMITS`, the explicit runtime contract.

The convenience function is a prime-field specialization, not a general finite-field constructor. The actual call used prime 13, evaluated the six nonzero-square representatives \(1^2,\ldots,6^2\), and obtained residues \(\{1,3,4,9,10,12\}\). It checked the 78 distinct pairs to build 39 red edges. The generic compiler also accepts another supplied labelled simple graph; it does not require its original colouring to be admissible.

A graph input has this shape:

```js
{
  order: 13,
  red_edges: [/* unordered distinct pairs, labels 0..12 */],
  provenance: "identified source",
  source_details: {/* optional bounded JSON metadata */}
}
```

The API has no dependencies or I/O. With the source and artifact texts already supplied to a connected V8 context:

```js
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);
const artifact = JSON.parse(datasetText);
const index = loaded.exports.openRetainedSeidelK4Family(artifact.snapshot);

index.summary();                 // global admissible count 1
index.membership(1);             // explicit blue K4 witness
index.switchGraph(1);            // this new switched graph
index.condition({ bits: [[1,1]] }).summary(); // count 0

const pinned = index.condition({
  edges: [[0,1,1], [0,2,0]]
});
pinned.page(0, 4);                // one retained assignment
pinned.rank(0);                   // rank 0
```

A genuinely new graph can be passed to the compiler. Loading the delivered snapshot does not invoke either constructor.

| Method | Result |
|---|---|
| `summary()` / `count()` | Current conditional family and global orbit scope |
| `select(rank)` / `rank(code)` | One assignment or its rank in the current admissible view |
| `page(start,count)` | Up to 64 consecutive admissible assignments |
| `membership(code)` | Global admissibility, condition status and saved obstruction |
| `obstruction(code)` | Six exact switched-edge calculations for the first witness, or null |
| `switchGraph(code)` | All red edges and degrees of the requested switch, even if excluded |
| `condition({bits,edges})` | Append switch-bit and pair-colour constraints to the current view |
| `profile()` | Every switch-bit and pair-colour frequency, with forced values |
| `quadruplePage` / `cubePage` | Retained local certificates |
| `classificationPage` | Counts and first-cube indices for consecutive universe codes |
| `snapshot()` / `work()` | Detached global snapshot / current reader counters |

Bit constraints are `[vertex,bit]`; pair constraints are `[u,v,color]`. Conditions append to their parent view and only filter its stored admissible codes. Conflicting requirements produce an empty view with an explicit conflict record. A requested bit 1 at vertex 0 conflicts with the fixed normalization. Loops are not valid pair constraints.

A condition does not relax the no-monochromatic-\(K_4\) requirement or admit colourings outside the switch orbit. For an empty view, every `forced` field is null; the API does not declare both values forced by vacuity. The actual bit-1 condition exercises this empty-family profile.

## Retention, bounds and assurance

The snapshot includes the labelled graph, coordinate conventions, every four-set, every cube, all per-code counts, every first-witness reference, sorted admissible codes and full histograms. Counts and codes are exact bounded integers; no floating-point approximation is used. Large-integer inputs are accepted only when they represent a value inside the stated finite integer range.

The loader checks the complete dimensions, graph symmetry, agreement of red-edge and adjacency representations, unique ordered four-sets, cube-coordinate and reference structure, per-code first-witness matches, and classification-summary consistency. It then evaluates the six actual edges of any requested obstruction. It does not regenerate the Paley graph, recompile triangle-parity patterns or expand every forbidden cube. Those structural checks do not independently authenticate the full mathematical provenance or exclude every possible corrupted source-level assertion.

The limits are 17 vertices, 65,536 switch codes, 512 input edge records before deduplication, 64 page rows, 64 bit-condition records and 256 edge-condition records per request, 20,000,000 cube visits, 11,000,000 profile cells and 8,000,000 snapshot characters.

The worst possible cube-visit count at 17 vertices is
\[
2^{16}\binom{17}{4}/8=19496960,
\]
within the declared cap. Local compilation uses \(O(\binom n4)\) rows. Expansion uses exactly \(2^{n-1}t/8\) visits for \(t\) switchable four-sets, followed by one pass through the code universe. Retained storage is \(O(\binom n4+2^{n-1})\). Conditional views scan only their parent's saved admissible codes. Profiles have a separate explicit pair/bit-cell cap.

## Executed work

| Activity | Recorded work |
|---|---:|
| Paley square evaluations / pair evaluations | 6 / 78 |
| Source red edges | 39 |
| Compiled four-sets | 715 |
| Base edge reads / triangle XOR operations | 4,290 / 5,720 |
| Switchable four-sets / forbidden cubes | 130 / 220 |
| Cube-assignment visits | 66,560 |
| Classified codes / excluded first witnesses | 4,096 / 4,095 |
| Fresh reader loaded four-set / cube / code rows | 715 / 220 / 4,096 |
| Reader adjacency cells / first-cube matches | 169 / 4,095 |
| Fresh query responses | 14 |
| Queried obstruction edges | 18 |
| Queried switched-graph edges | 78 |
| Profile bit / pair cells | 13 / 78 |
| Conditional candidate-code visits | 2 |
| Reader Paley construction, local compilation, cube expansion | 0 / 0 / 0 |

The unformatted snapshot is 132,790 characters. In this observation, the source graph and complete switch classification took 10 ms, the fresh load 5 ms and the query sequence 6 ms. These timings are individual connected-V8 observations, not a statistical benchmark.

One new Paley(13) instance and one complete switch-family computation were run. The source colouring appears as code 0 inside that complete family; there was no separate baseline checker or Ramsey-number search. Other graph inputs, the convenience cases 5 and 17, larger caps and contradiction/refusal branches were source-inspected rather than exercised in a synthetic suite. The delivered result preserves the singleton-family outcome and its complete finite obstruction evidence.
