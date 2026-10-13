# Exact single-edge C4 repairs

Adding point 0–line 0 to the identified order-13 Singer incidence graph creates 14 four-cycles. Keeping that edge requires deleting at least 14 original edges. This index represents all 4,782,969 minimum repairs through one of three choices on each old length-three path.

The package contains the complete 14 cycles, 42 relevant old edges, 680 base coefficients, 120 profiles, both conditional tables and all 25 saved-reader outputs. A profile with type counts (5,4,5) has 252,252 repairs. The declared edge-ID cost has minimum 23 and two minimizers within the minimum-cardinality family.

- [API, proof, input contract and sources](C4_REPAIR_API.md)
- [CommonJS module](single_edge_c4_repair.cjs)
- [Complete finite construction and queries](point0_line0_repairs.json)

Open `package.construction.snapshot` with `openC4Repairs` for count, constrained prefix/rank/select, edge witnesses and cost queries. Conditional coefficients are explicit new query work; the original field, difference-set, point-pair and base-coefficient computations are not replayed.

The old plane is an identified accepted premise from Commons #31474, blob 5561a91eddf8cfd7911641702b60cd51e308078d. Points and lines remain different vertex types. The exact scope is one inserted edge kept and only original edges deleted. The constructor is specialized to a supplied cyclic planar difference set; it does not audit that inherited mathematical premise.

This finite result does not settle either Erdős 713 asymptotic exponent question, establish an unrestricted graph-edit optimum or claim new Singer mathematics. See the guide for the ordinary, non-induced C4 convention and published attribution.
