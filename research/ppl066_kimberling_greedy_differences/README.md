# Kimberling Rule 1: exact saved continuation

Continue the canonical a(1)=1,d(1)=0 greedy sequence using ordinary/mirrored position bitsets and separate positive/negative difference bitsets. Every new step retains complete blocking masks for the required negative preference and least admissible magnitude.

The definition is [OEIS A131388](https://oeis.org/A131388), with its signed sequence [A131389](https://oeis.org/A131389). The input is Kimberling's complete published 1,000-pair prefix. It is consumed as an identified premise, not regenerated.

## Delivered result

One continuation adds indices 1001–1256, and one saved-state append adds 1257–1384. The final pair is a(1384)=1532,d(1384)=−658. All 384 new terms, 576 blocking certificates and 1,152 full blocker masks are retained.

New completed sign windows start at 998–1381, with no violation in those 384 windows. Old complete windows were not rechecked, and the final three starts remain incomplete.

A fresh saved reader finds least unvisited position 893, least unused positive difference 657 and least unused negative magnitude 526. It exports every new term and answers 17 queries with zero greedy construction or occupancy rebuild.

These are finite-prefix results. They prove neither infinite permutation claim nor either all-index three-step sign claim.

## Read and use

- [GREEDY_DIFFERENCE_API.md](GREEDY_DIFFERENCE_API.md): canonical convention, linear universe proof, certificate interpretation, API and bounds.
- [greedy_difference_bitset_index.cjs](greedy_difference_bitset_index.cjs): public constructor, saved append and finite occurrence/unused-value navigation.
- [published1000_through1256.json](published1000_through1256.json): complete initial state.
- [published1000_through1384.json](published1000_through1384.json): complete final state, append receipt and all fresh-reader outputs.

Both datasets load directly through their `.snapshot` field. Public exports are `continueGreedyDifferences`, `openRetainedGreedyDifferences` and `GREEDY_DIFFERENCE_LIMITS`.

The guide proves a(j)≤2(j−1) for j≥2 in the canonical construction. This makes the bitset universe exact at a finite term cap. The actual cap is 4,096 with universe bound 8,190; the public maximum is 16,384 terms.

Term indices are one-based; unused-value ranks are zero-based. Negative unused differences are ordered by increasing magnitude, −1,−2,… . Saved loading checks structure and indexes retained data without re-proving the source prefix or certificates. Other inputs and unexercised branches have source inspection only.

Original attribution, source lineage and the infinite questions remain explicit. No accepted recurrence, prior construction or synthetic test suite was replayed.
