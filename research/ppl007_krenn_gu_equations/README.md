# Krenn–Gu universal equation atlas

This package stores the complete inherited-coloring amplitude equations for **six labeled vertices and three declared colors**. It provides exact symbolic navigation over the saved equations without rebuilding their pairing or monomial tables.

The delivered atlas has **135 complex weight coordinates, 15 vertex pairings, 729 equations and 10,935 cubic monomials**. Three constant-color amplitudes have right-hand side one; the other 726 amplitudes have right-hand side zero. These are formal polynomial equations. The package does not assign numerical weights or decide whether the system has a solution.

## Start here

Read [EQUATION_ATLAS_API.md](EQUATION_ATLAS_API.md) for the mathematical contract, complete API, proofs of representation and finite-table completeness, actual query results, limits and primary references.

| File | Contents |
|---|---|
| [equation_atlas.cjs](equation_atlas.cjs) | Dependency-free CommonJS compiler and saved-record reader |
| [six_vertex_three_color_atlas.json](six_vertex_three_color_atlas.json) | Complete atlas, 22 recorded queries, work counters, execution context and custody |
| [EQUATION_ATLAS_API.md](EQUATION_ATLAS_API.md) | Mathematical interpretation, source identities and full interface |
| [README.md](README.md) | This entry point |

A future consumer can open the delivered record as follows. Opening creates another reader session on a detached copy; these example calls were not executed as an additional delivery run.

```js
const {openAtlas} = require("./equation_atlas.cjs");
const evidence = require("./six_vertex_three_color_atlas.json");
const reader = openAtlas(evidence.record);

const equation = reader.lookupColoring({colors: [0, 0, 1, 1, 2, 2]});
const expression = reader.formatEquation({equation_id: 44, form: "equation"});
const saved = reader.snapshot();
```

Each successful query returns its result, exact arguments, event reference and logical work counters. The reader supports bounded pages, coloring lookup, monomial membership, variable and joint incidence, formal derivatives, expansion around one vertex, zero-channel restriction profiles and vertex/global-color permutation maps.

## What the recorded execution contains

One compiler invocation built the complete six-vertex, three-color atlas. One fresh saved reader then completed 22 queries. The data contains their complete receipts, including all 15 terms of equations 0 and 44, every monochromatic equation, selected incidence pages, a derivative chain, a full restriction profile and all 15 term correspondences for a specified symmetry.

For the coloring `[0,0,1,1,2,2]`, equation 44 contains the monomial `x0*x85*x134`. Differentiating that amplitude with respect to variables 0, 85 and 134 yields the constant one. This is a formal polynomial identity: an equation holding at a point does not require its derivatives to vanish at that point.

Setting the 90 channels with different endpoint colors to zero leaves **405 formal monomials**. Across all 729 equations, the surviving-term counts are:

| Terms remaining | Equations |
|---:|---:|
| 0 | 546 |
| 1 | 90 |
| 3 | 90 |
| 15 | 3 |

The three 15-term equations are the constant-color equations. No unit-right-hand-side equation immediately becomes zero under this restriction. That observation does not establish solvability; retained terms still depend on complex weights and can cancel after specialization.

The reader reports **zero pairing enumeration, monomial construction, incidence construction or numerical weight evaluation**. It traverses stored structures and creates the requested symbolic outputs. The guide defines the counter units and records all actual arguments and timings; timings are individual observations, not benchmarks.

## Scope and custody

Parallel edges with the same endpoint colors are represented by their summed complex weight. Distributivity proves that these aggregate coordinates preserve every inherited-coloring amplitude. They need not preserve the original edge identities or structural matching multiplicities.

The saved reader checks the complete finite atlas through canonical rows, valid distinct pairings, exact counts, term references and incidence coverage. It does not authenticate a record's external origin, replay historical queries or solve the equations. The final record containing the 22 receipts was exported without another reopening.

The source blob is `f6a1ff5130bc9270977240ddd82502772a0d7083` (39,245 bytes). The complete data blob is `ec31f122997614857bf69758b2f6bb3fa34e5569` (571,006 bytes). Source and data were frozen before publication.

This is a finite symbolic research interface. It supplies no proof or counterexample to the Krenn–Gu conjecture and makes no award or novelty claim for the underlying graph model. The guide cites the primary papers and the sponsor's current terms.

Operation: `KRENN-GU007-UNIVERSAL-EQUATION-ATLAS-20261005-7CA6`.
