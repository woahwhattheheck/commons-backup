# Binary linear covering codes in dimension six

This is a complete labelled atlas of all 2,825 linear subspaces of F2^6, with 26,387 cosets and exact nearest-codeword data.

Read [the API, finite completeness argument and source guide](BINARY_LINEAR_COVER_API.md). The [manifest](dimension6_manifest.json) identifies all twelve complete code shards. Assemble them as documented, then open the saved snapshot with [the CommonJS reader](binary_linear_cover_index.cjs).

At radius two the smallest covering codes have four words and density 11/8; all 91 are retained and exported in the reader record. At radius one all 350 smallest codes have 16 words and density 7/4. These are fixed-dimension statements, not values of Green's asymptotic f(r).

[The 62 saved queries](saved_reader_queries.json) include exact conditional families, all selected code records, nearest/within-radius navigation and 12 inverse matches. [All nine condition caches](saved_condition_caches.json) are complete. Query scans and XORs are counted; no RREF, basis reduction, weight or histogram construction was repeated by the reader.

[The input](input6.json) identifies the one ambient dimension and literal inherited binomial row. Code IDs retain coordinate labels, balls may overlap, and the zero subspace's missing nonzero minimum distance has an explicit filter convention. Source attribution and all limits are in the guide.
