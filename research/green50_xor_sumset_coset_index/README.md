# XOR sumsets and affine cosets in F₂⁶

This saved index covers fourteen fixed generator sets: {2,3,5,7,11,13,17,19,23,29,31,37,41} and each single deletion. All repeated-sumset lengths 0 through 10, 9,856 ordered representation coefficients and 39 support profiles are retained. The identified 26,387 affine cosets are reused from #31804; their generation and earlier covering calculations are not replayed.

[Read the API guide](XOR_SUMSET_COSET_API.md) for exact source conventions, lineage and limits. [load_saved_index.cjs](load_saved_index.cjs) reconstructs both complete objects from their manifests and six shards. [xor_sumset_coset_index.cjs](xor_sumset_coset_index.cjs) supplies saved growth, tuple prefix counts/rank/select, sumset navigation and coset witnesses. [saved_reader_queries.json](saved_reader_queries.json) retains all 105 actual responses and 23 inverse matches, with zero reader convolution or profile compilation.

The full set reaches all 64 outputs at length four. Deleting 2 leaves alternating least-significant-coordinate hyperplanes from length three. In dimension six, tenfold sumsets already equal the span of the translated generator set by an elementary padding argument; the guide makes this limitation explicit. No uniform asymptotic, semantic-audit replay, novelty or award is claimed.
