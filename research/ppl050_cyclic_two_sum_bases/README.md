# PPL050: cyclic two-sum bases and periodic lifts

The complete Z/13Z census has 5,097 bases among 8,192 labelled subsets, 689 inclusion-minimal bases, 39 bases of minimum size five, and 156 minimizers of maximum ordered multiplicity four.

[API, proof and scope guide](CYCLIC_TWO_SUM_API.md) explains the finite-group conventions and exact periodic lift B=A+13*N0. Saved residue and carry fibers support huge-target ordered/unordered representation counts, selection and ranking without generating the infinite set. This separate model does not settle the natural-number Erdős–Turán conjecture.

Files:

- [Constructor and saved reader](cyclic_two_sum_bases.cjs)
- [Complete pair catalog, family indexes, signatures and provenance](cyclic13_basis_certificate.json)
- [All 31 saved reader outputs](saved_reader_queries.json)
- [Subset rows 0–2047](subsets_0000_2047.json)
- [Subset rows 2048–4095](subsets_2048_4095.json)
- [Subset rows 4096–6143](subsets_4096_6143.json)
- [Subset rows 6144–8191](subsets_6144_8191.json)

All 212,992 ordered/carry cells are present across the four shards. The once-only constructor and fresh reader are fully banked; no old field, Singer, digital basis or accepted pair computation was replayed. Classical finite-group bounded-representation results remain credited.
