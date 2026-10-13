# Erdős 74: exact finite local bipartization

This package retains the complete local edge-deletion profile of the classical eleven-vertex Mycielski graph obtained from \(C_5\). For subset sizes \(0,\ldots,11\), the maximum minimum number of edges needed to make a subgraph bipartite is
\[
[0,0,0,0,0,1,1,1,2,2,3,4].
\]
The full 20-edge graph needs exactly four deletions, with five distinct minimum deletion sets. All 2,048 induced vertex subsets and 88,574 canonical cuts, including empty, are retained.

The parameter comes from [Erdős–Hajnal–Szemerédi (1982), Definition 3.1](https://renyi.hu/~p_erdos/1982-11.pdf). The graph construction is credited to Mycielski (1955), with its accessible author restatement in [Lin–Liu–Zhu](https://www.calstatela.edu/sites/default/files/multicolomycillz.pdf). Its established triangle-free/four-chromatic properties were not recomputed.

## Files

| File | Purpose |
| --- | --- |
| [local_bipartization_index.cjs](local_bipartization_index.cjs) | Bounded pure CommonJS graph constructor, complete profile compiler and saved subset/cut/deletion-set index. |
| [LOCAL_BIPARTIZATION_API.md](LOCAL_BIPARTIZATION_API.md) | Definitions, source/status boundaries, full derivations, actual profile, API, encodings and reader assurance. |
| [mycielski_c5_local_profile.json](mycielski_c5_local_profile.json) | Complete graph/cut transcript, all minima and profiles, and all 24 fresh-reader responses. |

## Use the saved index

```js
const api = require("./local_bipartization_index.cjs");
const data = require("./mycielski_c5_local_profile.json");
const index = api.openRetainedLocalBipartization(data.snapshot);

index.profile();
index.pageCuts(2047, 0, 8, "deletion_sets"); // all five full-graph witnesses
index.subsetCount({ size: 8, minimum_at_least: 2 }); // count 45
index.budgetReport([0,1,1,1,2,2,2,2,2,3,3,3]);
```

Direct module-text loading in connected V8 is documented in the guide. The saved reader checks the complete encoded transcript without recreating the cut objective table. Returned full cut witnesses additionally inspect the saved graph's edges.

“Optimal vertex bipartitions” and “minimum deletion sets” are separate families. If a nonempty induced graph has \(c\) connected components, each minimum deletion set has \(2^{c-1}\) vertex bipartitions modulo common color reversal. Fixing the least vertex of each component in class A removes this multiplicity. Empty classes and isolated vertices are handled explicitly.

The actual profile retains 5,004 optimal bipartition codes and 3,589 component-normalized minimum-deletion representatives across all subsets. All proper vertex subsets meet the square-root deletion budget; the full graph is the only violating subset. This supplies a finite forbidden host for that local condition, not an infinite-graph solution or a smallest-obstruction classification.

## Status and bounds

The current [FormalConjectures 74 statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/74.lean), blob **bbf29b01a71c08497b96dcff85374dab9e916f07**, marks the original arbitrary-growth question solved with answer False and links an external proof; its local theorem remains a placeholder. The square-root variant is separately marked open. These are observed source annotations. The linked proof was not inspected or rerun.

The generic graph cap is fourteen vertices. The sole actual input is the Mycielski \(C_5\) graph. Its source, blob **a94c4465e7ae7ef0548c2f627edcb46e8f4f4723**, was unchanged between construction and the fresh reader. Complete data is blob **937421e391af3907b184a8ca1bbfbb60da910788**.

No accepted computation, chromatic search, native workflow or published profile was replayed. The result is a complete finite host capability; it makes no novelty, global-resolution or external frontier claim.
