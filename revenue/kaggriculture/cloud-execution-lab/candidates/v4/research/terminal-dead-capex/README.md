# ASTRA-DEADCAP — terminal acquisition cash-path oracle

Status: **donor defect proven; one authenticated current-native cell is negative; global current-native engagement remains unmeasured; evidence-only.**

This package lives inside the one canonical TITAN V4 research tree. It does not add a controller, feature key, runtime hook, default, archive, or Kaggle change.

## The invariant

The official engine awards terminal reward as player cash. A purchase is therefore strictly dominated by keeping its spend when the purchased asset has no causally reachable path to later cash.

DEADCAP is deliberately conservative. The first certified subfamily is seeds only: a seed purchase is called dead only when even a generous authored-route over-approximation cannot find a later `PLANT <crop>` followed, after the crop's official first-yield age, by any later `SELL <crop>`. HARVEST/DROP feasibility is not required by the oracle, so uncertainty biases toward **REFUSE**, not toward deleting a purchase.

HIRE is explicitly out of scope. Product/animal/land rows are counted for the broad census but are not certified dead by this first package.

## Exact source custody

- donor `r01_tapes.py`: 32,955 bytes, Git blob `a43289b9cc5e34a2481fddf652762a7d92f427ef`, SHA256 `4a60e775e52905048257aff4871a11c5ba49de6ba464177ed6ae4d9bd3120e18`
- official engine: Git blob `3c202c7ee921da239356789e266b694635103fc4`
- authenticated foundation artifact: `10175943272`, archive SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`
- current production pins used by the native probe: `main.py` `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`, `titan_runtime.py` `6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0`, config `3a3bef83899d3010fad623b628d9e95d9978111b`

Post-merge custody repair #12943 makes the current-native regression call `authenticate_current()` and assert all three exact Git blobs before invoking `current_native_probe()`. A moving checkout therefore fails closed on production-source drift.

## Donor census

Across the exact 13 × 719 donor tapes:

- `BUY_SEED`: 2,330
- `BUY_PRODUCT`: 724
- `BUY_ANIMAL`: 159
- `BUY_LAND`: 26
- BUY rows at step >= 480: 929

The seed cash-path oracle returns exactly one candidate:

`TAPE 12 / STEP 284 / ROW 0 / BUY_SEED MELON 1`

There is **no later `PLANT MELON` at all** in tape 12, so the purchased seed cannot enter a crop/cash path.

## Exact-engine donor witness

Tape 12 vs tape 0, seed 0, seat 0:

- cash before step-284 market: `$11,021`
- the MELON seed buy executes: cash becomes `$10,941`
- MELON seeds: `0 -> 1`
- terminal MELON seeds: `1`
- baseline terminal reward: `$52,429`
- replacing only that row with `[]`: `$52,509`
- own delta: **+$80**
- rival delta: **$0**

A broader fixed-route donor differential ran 104 cells: all 13 donor opponents × seeds 0..3 × both seats. Every cell is exactly `+$80` own and `$0` rival.

## Current-native truth scope

The authenticated production replay measures exactly **one current-native cell**: seat 0, seed 0, rival tape 0, through step 284. In that cell the returned market is `SELL WHEAT 9`, not the exact historical witness `BUY_SEED MELON 1`; MELON seed stock remains zero.

That is valid negative evidence for this exact donor witness, but it is **not a global COLD census**. The probe does not search both seats, a multi-seed/opponent panel, or arbitrary current-native dead-seed acquisitions at other callbacks.

Therefore the authoritative disposition is:

**ONE-CELL DONOR WITNESS ABSENT / GENERAL CURRENT-NATIVE DEAD-SEED ENGAGEMENT UNMEASURED.**

No runtime guard is authorized from this package. A global COLD statement requires a separately declared authenticated current-native panel whose returned actions are scanned with the generic dead-seed cash-path theorem rather than exact equality with one historical row.

## Reproduce

From this directory:

```sh
python -B -m unittest -v test_deadcap_oracle.py
python -O -B -m unittest -v test_deadcap_oracle.py
```

For the full 104-cell donor matrix, call `deadcap_oracle.result_bundle(..., full_matrix=True)` against the pinned donor tape and official engine.

Scope limit: this proves one historical seed dead-capex defect, its exact fixed-route economics, and one authenticated negative current-native cell. It does **not** prove global current-native COLD and does not authorize removing buys without a current returned-action cash-path certificate.
