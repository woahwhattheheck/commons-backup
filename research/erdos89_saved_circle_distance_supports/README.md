# Subset distance supports for sixteen saved rational-circle points

This exact finite consumer uses original E212 vertex IDs 0,4,...,60 from [Commons #31706](https://github.com/woahwhattheheck/commons/pull/31706). It copies saved metric classes and computes every vertex subset's set of positive distance values.

Read [DISTANCE_SUPPORTS_API.md](DISTANCE_SUPPORTS_API.md) for source conventions, inherited pins, the union recurrence, complete minima, distance-budget meaning and API.

The fixed host has 16 points, 120 pairs and 52 distance classes. All 65,536 subsets are retained in sixteen lossless row shards. The first actual reader records 223 responses, 62 matching rank/select comparisons, all 189 fixed-cardinality minimizers, 32 condition caches and three marginal tables. Its complete output is preserved in five ordered text parts and an assembly descriptor.

For eight retained vertices the fixed-host minimum is nine distinct distances, attained once. This is not a global planar extremum or the asymptotic Erdős #89 lower bound. No coordinates, chord lengths, old perimeter work or prior geometry query was recomputed.

Use the saved certificate with createReader; constructor execution is unnecessary for navigation. Numeric-mask order, source distance IDs, empty-family behavior and vertex-deletion budget semantics are explicit in the guide. public_checkpoints.json records native public checkpoint identities.
