# Erdős 357: finite consecutive-sum prefix tree

This exact finite index classifies increasing sequences from {1,…,19} with distinct sums over consecutive index intervals. It retains **24,698 sequences**, **17,856 rejected appends with collision witnesses**, and exact prefix-completion coefficients. The largest sequences have length **10**, with **five maximizers**, establishing the finite value f(19)=10 under the retained monotone definition.

Use [CONSECUTIVE_SUM_API.md](CONSECUTIVE_SUM_API.md) for the source distinction, completeness argument, input limits, complete five-witness list and saved API. [snapshot_manifest.json](snapshot_manifest.json) identifies all 25 complete node shards and the exact original serialization. [saved_reader_queries.json](saved_reader_queries.json) retains all 35 fresh responses and their work counters.

The reader uses saved records for counts, ranks, selections and collision explanations. It does not repeat interval sums or coefficient construction. This is an explicitly enumerated finite prefix tree, not an infinite-density result or an arbitrary-subset-sum classification.

FormalConjectures supplies the actually read definition. Hegyvári's bibliography was located, but its direct DOI was inaccessible; no independent full-paper conventions or proof review are claimed. No record, asymptotic, priority or prize assertion is made.
