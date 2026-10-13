# Paley(13): complete finite Seidel-switch classification

This package indexes every labelled Seidel switch of the Paley graph on \(\mathbb F_{13}\). Fixing switch bit 0 at vertex 0 leaves **4096 distinct switch codes**.

**Only code 0 avoids a monochromatic \(K_4\).** Every nontrivial switch has at least four monochromatic four-vertex sets. Exactly thirteen codes attain four: the single-vertex switch operations, using the complementary representative for vertex 0.

## Files

| File | Content |
|---|---|
| [seidel_switch_index.cjs](seidel_switch_index.cjs) | Pure CommonJS input constructor, exact switch classifier and saved reader |
| [SEIDEL_SWITCH_API.md](SEIDEL_SWITCH_API.md) | Source attribution, complete local-pattern proof, API, bounds and execution account |
| [paley13_switch_family.json](paley13_switch_family.json) | Complete graph, 715 four-set rows, 220 forbidden cubes, all 4096 classifications and every reader response |

Source blob: `a54df8ccc36761496d822dc6ed562dafdd23fda0`. Complete data blob: `39bbfc4245c974a460c97c7cd65c387a5a5b205f`, **494,532 bytes**.

## Use the saved index

With the source and data texts already supplied to a connected V8 context:

```js
const moduleObject = { exports: {} };
new Function("module", "exports", sourceText)(
  moduleObject, moduleObject.exports
);
const artifact = JSON.parse(datasetText);
const index = moduleObject.exports.openRetainedSeidelK4Family(
  artifact.snapshot
);

index.summary();                 // 1 admissible switch
index.membership(1);             // blue K4 on [0,1,5,11]
index.switchGraph(1);            // explicit new switched graph
index.condition({ bits: [[1,1]] }).summary(); // count 0

const pinned = index.condition({
  edges: [[0,1,1], [0,2,0]]
});
pinned.page(0, 4);                // the original colouring
pinned.rank(0);                   // rank 0
```

Red has colour 1 and blue colour 0. Vertex \(v\ge1\) has code weight \(2^{v-1}\). Ranks use increasing integer code, not lexicographic switched-vertex lists. Complementary switch sets induce the same colouring; fixing bit 0 removes this duplication. Graph isomorphisms and global colour interchange are not quotiented.

The fresh reader made 14 queries without reconstructing the source Paley graph, compiling local patterns or expanding forbidden cubes. It performs exact arithmetic for requested obstruction edges, switched graphs and profiles. All 4095 excluded codes retain a first-cube reference to a complete shared obstruction.

## Sources and scope

[Lim and Praeger](https://arxiv.org/pdf/math/0605252) give the established Paley definition: distinct field elements are adjacent when their difference is a nonzero square, for field order congruent to 1 modulo 4. Brouwer and Haemers, *Spectra of Graphs*, Section 1.8.2, give the standard switching convention; its locator and exact matrix/edge interpretation are in the guide.

The [Erdős 1029 formal statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/1029.lean) concerns \(R(k)/(k2^{k/2})\to\infty\). This artifact concerns one finite switching orbit. It does not classify arbitrary graph colourings, establish a new Ramsey number, prove that asymptotic target or claim mathematical novelty.

The generic classifier supports at most 17 vertices and 65,536 switches. The prime-field convenience constructor supports exactly 5, 13 and 17; only 13 was consumed here. The saved loader checks structural consistency and requested obstruction arithmetic, without independently authenticating the full source computation. The guide states the complete assurance boundary.
