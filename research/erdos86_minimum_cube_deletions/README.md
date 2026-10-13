# Minimum Q4 deletion-family index

This continues the identified [#31442 input](https://github.com/woahwhattheheck/commons/pull/31442) with a capability its optimizer did not supply: the complete family of minimum deletions. Its topology, square reduction and eight-edge optimum remain accepted premises; none is recomputed.

There are exactly **eight labelled minimum deletion sets**. Every set deletes two edges in each direction and is a perfect matching of the sixteen vertices. Every cube edge belongs to two of the sets. The 212-node exact-cover DAG, all eight exports, all 32 participation counts, 61 complete reader responses and complete conditional caches are saved.

See [MINIMUM_CUBE_DELETION_API.md](MINIMUM_CUBE_DELETION_API.md) for attribution, correctness argument, input lineage, rank order, API, actual work and limits. [minimum_cube_deletion_index.cjs](minimum_cube_deletion_index.cjs) is dependency-free CommonJS. Open [q4_minimum_deletion_index.json](q4_minimum_deletion_index.json) to query the retained family; [input_q4.json](input_q4.json) isolates the literal premises.

These are finite Q4 family/navigation results. The existing optimum is credited to the prior package. The general Erdős86 statement remains separately annotated research open in the actually read formal source; no proof execution, asymptotic, priority or prize claim is made.
