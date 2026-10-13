# PPL033 / Erdős86: finite hypercube square covers

This directory provides an exact bounded optimizer for `C4`-free edge subgraphs of a hypercube, plus a resumable search snapshot and saved graph/certificate reader.

The new recorded `Q4` consumer keeps **24 of 32 edges**. Its eight deleted edges hit all 24 coordinate squares. Each edge lies in three squares, so at least eight deletions are necessary. The retained witness attains that global bound and certifies the finite value `ex(Q4,C4)=24`.

The open Erdős86 question concerns the asymptotic edge-density threshold in large dimensions. This finite result is a method and software deliverable, with no new-priority or asymptotic claim.

## Files

| File | Contents |
|---|---|
| [cube_square_cover.cjs](cube_square_cover.cjs) | Dependency-free constructor, exact bounded search, saved reader |
| [CUBE_SQUARE_COVER_API.md](CUBE_SQUARE_COVER_API.md) | Full formulation, proofs, API, limits, work ledger and provenance |
| [q4_square_cover.json](q4_square_cover.json) | Complete new Q4 universe, paused frontier, continuation, six incumbents, 174 nodes and 16 fresh-reader queries |

The implementation used for the recorded computation is blob `617edf7561bf6cc982aaf48b2e895eee4d50976c`, 51,024 UTF-8 bytes. It was fixed before the first constructor and remains unchanged.

## Recorded progress

| Stage | Kept edges | Search state |
|---|---:|---|
| Classical alternating-layer baseline | 16 | One pending root |
| Greedy seed and one processed node | 20 | Four pending children saved |
| Fresh continuation | 24 | Root-wide lower bound attained; complete |
| Fresh saved reader | 24 | Sixteen recorded queries; zero new search advances |

The constructor ran once. The continuation reused the saved universe, greedy trace and processed root. Across both advances, 156 nodes were processed: 52 branches, 97 bound prunes and seven complete-cover leaves. Another 18 pending nodes were closed explicitly by the attained global bound. Every generated node and pruning witness remains available.

Deleted edge IDs are `[0,7,10,13,19,20,26,29]`. Their endpoint pairs are `(0,1), (14,15), (4,6), (9,11), (3,7), (8,12), (2,10), (5,13)`. The guide and data retain all square incidences and hit witnesses.

## Inspect saved evidence

~~~javascript
const { openCubeSquareCover } = require("./cube_square_cover.cjs");
const evidence = require("./q4_square_cover.json");

const reader = openCubeSquareCover(evidence.fresh_reader.snapshot, {
  source_id: "my-study/Q4/inspection"
});

const result = reader.assess({});
const firstSquare = reader.getSquare({ square_id: 0 });
const neighbours = reader.vertexNeighbours({ vertex_id: 0 });
const page = reader.pageEdges({ view: "kept", offset: 0, limit: 24 });
~~~

The source also exposes `compileCubeSquareCover` and `advanceSearch` for new bounded computations. Dimensions 1–6, finite search budgets, session/event bounds, page bounds and aggregate copy bounds are explicit in the API guide. An unfinished frontier remains incomplete.

The saved loader checks shapes, IDs, masks, partitions and references. It does not independently reprove coordinate semantics, coverage unions, pruning bounds or search completion. The mathematical certificate remains a retained compiler/search premise. The fresh reader's structural work and actual binary-search/assignment checks are counted separately from its zero new topology, search and cover-proof work.

## Sources and scope

[Rahil Baber, *Turán densities of hypercubes*, arXiv:1201.3587v2](https://arxiv.org/pdf/1201.3587), Introduction, supplies the cube/layer conventions and the established alternating-layer baseline. The exact set-cover reduction and finite certificate are explained in the guide.

[Formal Conjectures, Erdős86](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/86.lean), observed blob `9893cdbc1cc5534dd0c912c63693c98642d0a249`, specifies arbitrary simple edge subgraphs on the full Boolean cube. The observed theorem is marked open and contains `sorry`; no Lean proof was run.

Equal-size branches may be pruned, so the output is one optimum witness rather than an enumeration of all maximizers or isomorphism types. No larger uncomputed dimension, current best bound, prize eligibility or sponsor action is established.
