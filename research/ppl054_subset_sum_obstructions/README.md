# Subset-sum obstruction index

A finite positive-integer host can have equal sums from subsets of different cardinalities. This package stores every subset sum, explicit minimal collision supports, and all sum-distinct subfamilies, then navigates those saved families without rebuilding the sums.

For the retained host

`[1,13,32,66,169,174,396,416,756,858,915,1016,1044]`,

the complete 8,192-subset calculation finds **6,047 sum-distinct subfamilies**. The largest have **nine elements**, with **61 maximizers**. There are 64 inclusion-minimal obstructions and 258 inclusion-maximal good subfamilies; maximality by inclusion differs from maximum cardinality.

The fiber at 409 contains both `{66,169,174}` and `{13,396}`. Every rejected host subset carries a contained disjoint equal-sum witness. The complete data and 28 saved-reader queries are included.

| File | Purpose |
| --- | --- |
| [subset_sum_obstruction_index.cjs](subset_sum_obstruction_index.cjs) | Bounded exact compiler and separate saved-table reader. |
| [SUBSET_SUM_API.md](SUBSET_SUM_API.md) | Proof, API, limits, source qualification and all result counts. |
| [thirteen_host_subset_obstructions.json](thirteen_host_subset_obstructions.json) | Complete input, subset cells, fibers, supports, classifications and query outputs. |

This consumes 378 identified low-order cells from [#31527](https://github.com/woahwhattheheck/commons/pull/31527) and forms 7,814 new sums. No old pair/triple addition, field construction or B3 proof was replayed.

The current FormalConjectures Erdős 1 source marks the historical exponential lower-bound conjecture false/research solved. Its local placeholder and uninspected external proof are explicitly distinguished in the guide. This package establishes only the fixed-host classification, not an unrestricted extremal value, a new global disproof or a novelty claim.
