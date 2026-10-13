# Finite append-only Sidon extension navigator

The saved B₂[2] family from [#31744](https://github.com/woahwhattheheck/commons/pull/31744) is incrementally refined to all 5,035 Sidon subsets of [1,19]. It adds 525 two-pair obstructions and 695 nodes while reusing the old pair fibers, nodes and coefficients. No old calculation is replayed.

For N=4, seed {1,2,4}, M=19, the old hole 3 stays forbidden. There are 41 append-only extensions, with two largest total sets of size six: {1,2,4,9,15,19} and {1,2,4,9,13,19}. The entire host has 24 size-six maxima. All 36 fresh reader outputs are retained, including all maxima and eight inverse rank matches.

Read [the API guide](SIDON_REFINEMENT_API.md) for exact base input pins, delta assembly, finite correctness argument, limits, all source qualifications and query accounting. The delta requires the identified immutable #31744 base files; it does not duplicate them.

Yu's B₂[g] convention includes unordered diagonal sums. Formal44 supplies the append-only rule and separately records the asymptotic question. This finite host index claims no general extension theorem, Singer construction or prize result.
