# COBUY current-native opening guardrail

This is a narrow source-bound follow-through to the existing `COBUY.md` mechanics theorem. It does **not** add a controller or retime any order.

## Exact opening collision

Current Arlene Git blob `bdb9cf58148a3c7961c085f4902759537decabf6` has the same step-0 raw market row on all four routes:

`row 0 = ["BUY_PRODUCT", "WHEAT", 13]`.

Current Apex tape Git blob `00ea34e3a3f340792ff61de0671abb4c1073472a` route 0 step 0 decodes to the same raw row. Current policy blob `ea238366136ce9df06811691831445f183d0b936` resets `selected_route = 0` at step 0. The Python entrypoint remains pinned as `f2ae8d9b229755235b93e98cd216d59ba0af4d9f`; its final market cap is ten rows. The six-day guard source is pinned as `38a75d26cd366e7145dfee86c4c43d53e6b1268f`.

Pinned official engine `3c202c7ee921da239356789e266b694635103fc4` fills all 13 units for both seats under the default opening world. Same-row costs are `$370 / $370`. If our otherwise identical required buy is shifted to raw row 1 while the rival remains on row 0, costs become `$357 / $383` (seat-swapped symmetrically), with the same terminal WHEAT inventory `9974`. Moving our buy one row later therefore costs us exactly **$13** in this cell; it does not change quantity or terminal public inventory.

## Native entrypoint verification

Independent byte-exact execution authenticated Apex from Actions artifact `10030763484` and the official engine from artifact `10175943272`, then invoked the **real compiled Apex agent** in fresh process/state for each seat using the official default opening constructors (two fresh $1000 farms, empty private state, `_new_market()`, no shops). Both seat 0 and seat 1 returned `market[:10] = [["BUY_PRODUCT", "WHEAT", 13]]`; raw row 0 is exact in both cases. This closes the raw-tape-to-postprocessing custody gap for this opening witness.

## Disposition

This is **not new alpha**: current TITAN is already aligned at the favorable row. The result is an anti-regression constraint for TOWNPROCURE/other own-buy retimers: preserve step-0 WHEAT13 row 0 unless a later composer independently proves a larger benefit that pays this exact $13 current-cost loss.

The broader 719-step current-native/replay collision census remains a separate gate. This receipt makes no rival-private-action prediction beyond the deterministic authenticated opening witness, no field-EV claim, and no runtime/default/config/archive/Kaggle activation claim.
