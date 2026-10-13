# Type II circulant coordinate-erasure families

A complete finite index for the 16 Type II codes among all 256 binary systematic [I8|A] candidates with A circulant. The codes have length 16. PPL158's separate [72,36,16] existence question is not searched or resolved here.

All 1,048,576 labelled (seed,erasure-mask) pairs are retained through complete coordinate-span profiles. The reader navigates shortening/puncturing dimensions, unique versus ambiguous erasure patterns, coordinate constraints and full compatible-codeword fibers. Its first use saved 151 responses, 39 matching inverse ranks, 18 conditions, four marginals and all 448 minimal-size ambiguous patterns.

Read [CIRCULANT_ERASURES_API.md](./CIRCULANT_ERASURES_API.md) for source definitions, finite proofs, order and limits. [profile_index.json](./profile_index.json) supplies exact direct/assembled loading identities for every profile. Assemble the reader text parts using saved_reader_manifest.json. A particular received word may be inconsistent even when its erasure pattern has zero ambiguity; the API keeps these outcomes separate.
