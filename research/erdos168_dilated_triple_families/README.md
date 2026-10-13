# Finite subsets avoiding dilated triples

This exact saved index represents every subset of [1,96] avoiding simultaneous n, 2n and 3n. It excludes those specific triples, rather than all three-term arithmetic progressions.

- [API, correctness argument and source limits](DILATED_TRIPLE_FAMILIES_API.md)
- [Constructor and saved reader](dilated_triple_families.cjs)
- [Complete component and coefficient index](interval96_family_index.json)
- [All 36 original reader outputs](saved_reader_queries.json)
- [Finite-prefix limiting-density enclosure and proof](DENSITY_ENCLOSURE.md)

The 268-node diagram represents 1,877,043,752,444,810,703,667,200,000 subsets. Maximum cardinality is 77, with 37,908 maximizers. Exact BigInt coefficients support conditioned counts, rank/select and pages; all nine actual inverse ranks match.

No earlier AP, sieve or accepted calculation was replayed. The historical scan supplied no readable statement; the fully read Formal168 defines the finite problem. The exact limiting density and its irrationality remain undetermined here.

A separate saved-reader consumer reuses nine component degree differences and adds eleven previously uncomputed prefix conditions. It certifies `451/576 <= lambda <= 197/243`, with exact width `431/15552`, without rebuilding the finite family. The linked note proves the finite-to-limit bridge and retains every new query output.
