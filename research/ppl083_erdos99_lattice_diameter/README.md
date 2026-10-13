# Erdős 99: a complete finite lattice diameter family

Inside the 37-point triangular-lattice host

\[
H_3=\{(a,b)\in\mathbb Z^2:\max(|a|,|b|,|a+b|)\le3\},
\]

the maximum number of points at diameter at most 4 is **19**. Exactly **seven** subsets attain this value. All seven have minimum distance exactly 1, diameter exactly 4, 42 unit pairs and 24 unit equilateral triangles.

The completed threshold classification also proves that **4 is the minimum diameter for 19-point subsets of this fixed host**, with exactly those seven minimizers. It does not establish the minimum diameter among arbitrary real-plane configurations or resolve Erdős 99's sufficiently-large-cardinality assertion.

The coordinate embedding is \((a,b)\mapsto(a+b/2,\sqrt3\,b/2)\), with exact squared distance \(\Delta a^2+\Delta a\Delta b+\Delta b^2\). The seven saved subsets are the translates \(H_2+c\) for \(c\in H_1\); every coordinate and triangle witness is retained.

## Files

| File | Purpose |
| --- | --- |
| [lattice_diameter_index.cjs](lattice_diameter_index.cjs) | Pure JavaScript compiler, exact proof DAG and saved count/rank/select/profile API. |
| [LATTICE_DIAMETER_API.md](LATTICE_DIAMETER_API.md) | Full recurrence proof, geometric contract, resource limits and source scope. |
| [hexagon3_diameter4_family.json](hexagon3_diameter4_family.json) | Complete input, 666 pair rows, 54 host triangles, all 589 proof nodes, all seven maximum subsets and every saved-reader response. |

## Saved use

With the complete file texts available as `moduleText` and `dataText`:

```js
const module = { exports: {} };
new Function("module", "exports", moduleText)(module, module.exports);
const data = JSON.parse(dataText);
const index = module.exports.openRetainedLatticeDiameterFamily(data.snapshot);

index.summary();
index.page("0", 3, true);
index.select("2");
```

Ranks are zero-based and use deterministic include-first proof-DAG order, not lexicographic vertex order. The loader checks every finite optimization recurrence and pruning certificate relative to the retained pair-distance graph. The geometric distances and completeness of the unit-triangle ledger remain identified premises from the compiler output.

One actual compiler run generated the complete finite family. A fresh reader made nine queries and exported all seven subsets through three pages, recording zero new squared-norm evaluations, triangle-ledger constructions or optimization states. Its checks and query arithmetic are recorded separately. Larger and alternate inputs were source-inspected, not executed.

## Sources

The [FormalConjectures statement of Erdős 99](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/99.lean) was retained in full at blob `df35f07e3d9474e88b6297b9fe25d7c18c9237de`. It requires an attained minimum distance of one and quantifies over every global planar minimizer for sufficiently large cardinalities.

The source credits Erdős's 1994 problem paper and Bezdek–Fodor's 1999 diameter paper. The guide distinguishes the complete formal statement from bibliographic and indexed-abstract evidence whose direct publisher transports were unavailable. The triangular-lattice coordinate convention retains its primary-source attribution. No known packing table, accepted computation, Lean proof or external solution claim was replayed.

Executed module identity: `44a72997f6af110dbb05766c4550119cd65905ac`.
