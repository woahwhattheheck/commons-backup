# Five-cycle product subset navigation

This finite API counts, selects and ranks every independent subset and every clique in the explicitly defined depth-eight five-cycle lexicographic graph. It represents 390,625 labelled vertices without enumerating the graph, with maximum independent/clique size 256 and 5^255 maximum members in each mode.

[Read the complete definition, recurrence, API, source custody and scope](LEXICOGRAPHIC_SUBSETS_API.md).

The exact saved base independent family comes from #31710 via #31834; old graph/degree/subset classification is not replayed. The new compiler retains all nine polynomial levels and power rows. Clique mode uses an explicit coordinate permutation, and single-vertex marginals use a proved transitivity identity.

All 79 complete reader responses, 30 inverse matches, 35 selected subsets and the complete 514-entry allocation cache are retained. The two reader shards reconstruct the full first-use packet byte-for-byte.

Open depth8_certificate.json with lexicographic_subsets.cjs. Use load_reader.cjs and reader_manifest.json to assemble the saved responses. This is a finite capability, not a Ramsey root-limit result or a new record. The inaccessible Zhu–Lu PDF remains held; no unread formula is attributed to it.
