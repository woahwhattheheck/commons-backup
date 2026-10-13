# Six-vertex octahedron and independence index

This consumer classifies all 32,768 labelled simple graphs by ordinary K2,2,2 copies, edge count and independence number. It reuses the complete independent-set bitfields from [#31710](https://github.com/woahwhattheheck/commons/pull/31710), without replaying its graph, adjacency, degree or regularity work.

Exactly **32,692 graphs are octahedron-free**. Their maximum is **13 edges**, attained by **60 graphs**, all with independence number two. The saved reader exports all sixty and all seventy-six containing graphs, with 90 complete responses, 66 inverse rank matches and exact rational density thresholds.

See [OCTAHEDRON_INDEPENDENCE_API.md](OCTAHEDRON_INDEPENDENCE_API.md) for source coverage, input custody, ordinary-versus-induced conventions, correctness, labels and limits. [octahedron_independence_index.cjs](octahedron_independence_index.cjs) is dependency-free CommonJS. [snapshot_manifest.json](snapshot_manifest.json) and four complete row shards reconstruct the full index; all eight condition caches are saved.

The normalization is edge_count/36, matching delta*n² at n=6. These finite results do not prove an asymptotic Ramsey–Turán statement, claim a new record, or imply sponsor/prize progress.
