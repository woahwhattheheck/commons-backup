# Finite weak vertex-color partition index

This package compiles weak vertex colorings for every edge-deleted subhost of one identified six-vertex, ten-edge hypergraph copied from [#31875](https://github.com/woahwhattheheck/commons/pull/31875).

- Complete 1,024-subhost coefficient table and 203 canonical vertex partitions.
- Full host: weak chromatic number 3, coefficient vector [0,0,0,45,55,15,1], 45 minimum partitions, 270 labelled three-colorings.
- Every proper edge-deleted subhost is two-colorable.
- 140 saved reader responses, 39 matching inverse comparisons, seven partition conditions and four subhost conditions.
- Exact palette counting/ranking includes palette 10^30+7 without palette enumeration.

Read [WEAK_VERTEX_COLORS_API.md](WEAK_VERTEX_COLORS_API.md) for the explicit graph, source qualification, counting argument, API order and finite-only limits. [input.json](input.json) binds the two acquired #31875 blobs and actual saved selection record. [certificate.json](certificate.json) and [saved_reader.json](saved_reader.json) contain the full construction and reader evidence.

The old red/blue edge-coloring computation was not replayed. The currently observed Formal593 main statement is research open and has a local placeholder; a mentioned resolution claim was not audited. This finite package does not characterize obligatory hypergraphs of uncountable chromatic number. The exact failed ownership PR query remains held and coverage incomplete.
