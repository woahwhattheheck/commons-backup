# Green 24 finite affine-copy family index

The package classifies all **524,288 subsets of {1,...,19}** by cardinality and the number of signed nondegenerate {0,1,3} copies. It counts ordered pairs x≠y with 3y−2x in the set, including both signs of y−x.

There are 102 host patterns and 283 exact family buckets. Nine-element subsets have maximum 19 copies, attained by 52 subsets; exactly 17 nine-element subsets contain no copy. Both ten-element minima have one copy. These are fixed-host statements, not unrestricted integer-set extrema or an asymptotic result.

The [API guide](AFFINE013_FAMILY_API.md) gives the source attribution, input lineage, counting recurrence, finite profile, navigation order and limits. [affine013_family_index.cjs](affine013_family_index.cjs) is dependency-free CommonJS. [snapshot_manifest.json](snapshot_manifest.json) and eight complete bucket shards reconstruct the entire index. [saved_reader_queries.json](saved_reader_queries.json) retains 65 full responses and 36 rank/select inverse matches; all 16 family caches are included.

Only literal host and binomial-row premises were reused from earlier packages. Old restricted-sum, AP, Pascal and sum-product computations were not repeated. Green's primary passage and the exact Formal24 counting contract are distinguished. No new gamma=1/3 proof, novelty, prize or sponsor claim is made.
