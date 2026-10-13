# TOWNSELL current-native field receipt

Status: **field-positive, narrow admission target only; no policy activation**.

This packet consumes the merged TOWNSELL source theorem from #12922 inside the existing `candidates/v4/research/market-baseline` authority. It does not create a controller, seller, feature key, runtime hook, default, archive, or Kaggle artifact.

## Current-native census

Authenticated current package: `main.py` Git blob `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`, `titan_runtime.py` `6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0`, scheduler `a483b24dd72b580d7d8811636b54d2d44f391575`, config `3a3bef83899d3010fad623b628d9e95d9978111b`, official engine `3c202c7ee921da239356789e266b694635103fc4`. The runtime was materialized from authenticated artifact 10175943272 / inner SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9` plus the sole later production runtime change, REBIND #12788.

Against the official starter on seeds 17, 101, and 9922999, both candidate seats are symmetric. The current returned stream contains 223/231/235 SELL rows per cell; 18/13/7 of those SELL rows occur immediately before a deterministic town/shop drain, with 7/7/6 positive source-theorem price premiums.

## Repeated clean witness: step 640 WOOL

All six seed×seat cells naturally return `SELL WOOL 8` at step 640. Delaying only that already-authored row to the next callback is legal in all six cells:

- the 8 WOOL units survive through next-callback unit actions;
- the next callback has no executable market row before the deferred sale (seed 17 carries only an empty `[]` row; seeds 101 and 9922999 carry none);
- rival terminal reward is unchanged;
- candidate terminal reward increases by exactly the deterministic TOWNSELL theorem premium: +2 on seed 17, +4 on seed 101, +2 on seed 9922999, for both seats.

This is current-native evidence that the TOWNSELL mechanism is not merely a constructed price theorem. It has a repeated, natural, output-changing cell.

## Required counterexample: step 672 WHEAT

Do **not** generalize this into “delay every pre-drain sale.” On seed 9922999 the current agent naturally returns `SELL WHEAT 23` at step 672 with a +$4 deterministic price shadow. But that callback's market queue is full: the WHEAT sale plus nine HIRE rows. The next callback already authors eight market rows. Removing the WHEAT sale and reinserting the identical row one callback later is mechanically feasible, yet both seats fall from terminal 190363 to 190250: **-113**, with rival reward unchanged.

The live admission therefore needs more than a positive price theorem. It must certify the specific row's custody, next-callback executable market occupancy/order, and downstream state interaction. The step-640 WOOL family is the leading clean admission candidate; the step-672 WHEAT cell is the mandatory rejection witness.

## Ownership and test truth

Existing SELLWINDOW / HARVESTCLOCK / seller owners retain runtime policy ownership. TOWNPROCURE retains WHEAT buy-side timing ownership. This receipt authorizes no mutation.

The original #12922 PR explicitly stated that its authored pinned-engine `test_town_sale_deferral.py` had not been executed from a repo-mounted checkout by that seat. Exact execution of that 7-test normal/optimized suite was separately delegated during this field run. Until that executor returns, this receipt records the source test as unresolved rather than relabeling it green.

Machine-readable hashes, per-cell counts, and branch receipts are in `TOWNSELL-CURRENT-RECEIPT.json`.
