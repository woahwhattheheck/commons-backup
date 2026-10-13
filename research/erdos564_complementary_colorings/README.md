# Finite complementary hypergraph colorings

This exact saved index contains all 118,784 labelled two-colorings of the twenty triples on six vertices with no monochromatic complete four-vertex 3-uniform hypergraph. It intersects the identified #31607 K4-free ZDD with its edge-complement action; the earlier family and #31447 tournament calculations are not rebuilt.

[Read the complete API, derivation, source custody and finite scope](COMPLEMENTARY_COLORINGS_API.md).

The minimum red size is six, attained by thirty colorings; the maximum is fourteen, also attained by thirty. All sixty endpoint colorings, 85 complete reader responses, 31 inverse matches and seven conditional tables are retained. Fixing edge zero blue gives 59,392 representatives under color exchange, without quotienting vertex labels.

Use load_saved_index.cjs with product_manifest.json and its three complete shards, then openIndex from complementary_zdd_colorings.cjs. reader_manifest.json and five reader shards reconstruct the complete first-use packet. Manifests include every path and identity.

This is a finite navigation contribution. It does not establish a new Ramsey threshold, double-exponential lower bound or resolution of Erdős 564. Current formal annotations are reported separately from proof verification.
