# TITAN V4 market-regime planting recovery receipt

Recovered from the completed local item-4 work for the Sep. 11 `MARKET-REGIME PLANTING SWITCH` demand in `#titan-kaggriculture` thread `1789177007.731029`.

## What this carrier preserves

- `seed_regime.py`: exact semantic source from the completed research bundle, SHA256 `32f2145a...` in the original delivery manifest.
- `engine_support.py`: exact pinned-engine helper, SHA256 `5b136cbf...` in the original delivery manifest.
- `RESULTS.md`: bounded execution result snapshot, updated only to clarify that later publication does not upgrade the historical evidence into promotion authority.
- Complete local delivery bundle: 116 files, 1,095,794 bytes, SHA256 `79ff50b2108be34b94439035b248b983c57e5f246c57e60a3301b84103f46c53`.
- Original additive patch: 1,026,812 bytes, SHA256 `b068de3a0e401942bf8be77563caeec943d5a6eeb81952fee9807cd62f4700a8`.

The full bundle also contains the source-bound native adapter, 109-file native pin manifest, focused tests, mutation runner, native-game runner, panel runner, validation manifest, and full/summary evidence traces. They are deliberately not asserted as current-main runtime compatibility: the execution was bound to the checked `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9` package.

## Executed evidence

- 35/35 focused tests normal and 35/35 optimized.
- 10/10 deliberately broken semantic variants rejected in each mode.
- 46 complete native games / 33,074 completed callbacks / zero fallbacks.
- Ordinary default panel: 16 seed/seat baseline-vs-gate pairs with identical raw actions, complete states and rewards; zero gate activation.
- Constructed all-cash-crop-price `$1` activation on seed 17 vs official starter: margin delta `+14,239` seat 0 and `+38,118` seat 1, reproduced under `python -O`.

These are research/correctness receipts, not leaderboard-strength or promotion evidence. The combined current V4, strong-opponent gauntlet, held-out natural activation, and route-reallocation economics were not established.

## Safety / integration boundary

The semantic gate is default-OFF. It only considers new cash-crop `BUY_SEED` rows and deliberately excludes WHEAT because feed has operating value outside direct crop-sale revenue. Rejected seed rows are blanked in place rather than compacted. Farmer/hands, already-owned seeds, PLANT, non-seed market rows, runtime configuration, production defaults, release/archive pointers, and Kaggle submission state are outside this carrier.

This recovery branch was cut from literal `main@d2ee894ecd4973ec4495d5dfe9f540bb12ec9baf`; the target path was rechecked absent from current main immediately before publication. The original Slack demand thread had no item-4 claim/completion reply, so this is recovery of stranded completed work rather than a duplicate lane.
