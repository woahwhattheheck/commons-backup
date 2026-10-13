# Triangle-free edge partitions of one K₂,₂,₂

This exact finite index retains all 4,096 edge-subgraph rows of the identified twelve-edge host from #31834. It has 53,248 partition coefficients and 184,072 saved branches. The full graph has 3,391,470 unlabelled triangle-free edge partitions; 225 use the minimum two blocks, giving 450 labeled two-colorings without a monochromatic triangle.

[The API guide](TRIANGLE_FREE_EDGE_PARTITIONS_API.md) defines covers, nonempty blocks, unused palette labels and rank order. [load_saved_index.cjs](load_saved_index.cjs) reconstructs the complete snapshot from its manifest and three state shards. [triangle_free_edge_partitions.cjs](triangle_free_edge_partitions.cjs) provides saved partition navigation and arbitrary finite palette counts/rank/select. All 69 actual reader responses, 21 inverse matches and all 225 minimum partitions are in [saved_reader_queries.json](saved_reader_queries.json).

The original infinite Erdős595 question and known finite Folkman theorem remain separate. No old graph census, independence calculation, octahedron classification or known construction/proof was replayed. This is a finite capability, with no novelty, sponsor or prize claim.
