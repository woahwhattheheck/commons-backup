# Kimberling 18: interlacing-triangle prefix index

This package supplies an exact bounded API for triangles of distinct labels $1,\ldots,h(h+1)/2$, where every entry lies strictly between its two adjacent lower neighbors. Rows may change direction; reflections are counted separately.

The saved height-6 index represents **42,263,042,752 arrays**, the existing total in [OEIS A347608](https://oeis.org/A347608). It stores every one of 16,814 value-prefix states, exact forward and completion counts, and all 441 cell-label marginals. Its local rule determines 70,488 transitions. Counts support direct selection, ranking, prefix extension queries and cell distributions without rerunning the graph traversal.

## Files

| File | Contents |
|---|---|
| [interlacing_prefix_index.cjs](interlacing_prefix_index.cjs) | Bounded exact compiler and retained count/rank/select, prefix, marginal, and paging API. |
| [INTERLACING_PREFIX_API.md](INTERLACING_PREFIX_API.md) | Mathematical representation, transition and counting derivations, conventions, exact consumer and trust boundary. |
| [height6_prefix_index.json](height6_prefix_index.json) | Complete explicit prefix records, all cell-label marginals, source attribution, selected arrays, branch traces and execution accounting. |

## Exact finite result

The top entry has support 6 through 16. Its central value 11 occurs in 6,747,734,592 arrays. The retained-data consumer selected three ranks, exported the last four arrays, ranked a reflected array, and answered two prefix queries and two cell-distribution queries. It performed no second graph traversal or count pass.

For example, the first seven label positions of the rank-21,131,521,376 array have 4,084,080 completions; its first fourteen have 280. The guide distinguishes a specified prefix order from all orders occupying the same set of cells.

## Sources and scope

The strict either-direction definition follows [Clark Kimberling's problem 18](https://faculty.evansville.edu/ck6/integer/unsolved.html). James B. Sidoli's [2021 note](https://oeis.org/A347608/a347608_2.pdf) already provides the orientation-poset decomposition and the two forbidden binary patterns; that construction and the known enumeration retain their credit.

Height 6 was the only executed compiler input. The public height cap is 7, subject to explicit state and work limits; completion at height 7 is not asserted. The loader checks saved structure and reuses stated source premises rather than independently certifying the counts. This delivery makes no new numerical-term, closed-form, asymptotic, complexity, novelty, or external-frontier claim.

