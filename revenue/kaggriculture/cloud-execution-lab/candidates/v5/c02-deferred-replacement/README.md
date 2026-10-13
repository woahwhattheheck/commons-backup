# C02: defer delivery-carrot wheat replacement

C02 changes one line in the exact production20f V5 control. After a delivery-carrot lot is sold, `delivery_choice.py` currently buys the full displaced-wheat quantity as soon as the debt is due. C02 suppresses that helper-generated purchase. Existing R04 and baseline market logic can still buy wheat; carrot planting, harvest and sale remain active.

The trigger trace showed the replacement orders arriving with 19–27 wheat already in the shed and below-stock same-day pickup demand. A first matched local screen found a positive or inert change in all 12 cells: six engaged cells improved by `+43`, `+135`, or `+275` relative margin and six cells were byte-identical. Across six distinct seed worlds the mean improvement was `+75.5`; there were no win-to-loss flips. [`LOCAL-SCREEN.json`](./LOCAL-SCREEN.json) records the exact cells and evidence boundary.

This signal is useful but small. It is a candidate component for the cumulative V5 frontier, not a champion or rating claim. Native tests against Apex_v7 and Arlene_v14 remain required, along with the top-30-union gauntlet. The canonical default and Kaggle submission stay unchanged.

## Build the exact candidate

The builder authenticates the 92-member production20f archive at SHA256 `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`, authenticates the target member, changes exactly one source seam, and emits a deterministic archive plus a create-exclusive receipt. The resulting candidate archive is SHA256 `8c294b6dbe296c6b822eaeccab8e3ecb3fbfc7854b50d6f584d9bd6da26e6d61`; its `delivery_choice.py` postimage is SHA256 `f367b527c8570d3f9bdfe5c1062f58fb2b7636f31f035f9a4587bc35a1b292b3`.

The exact postimage is also available as the staging component [`c02-deferred-replacement-v1`](../selective-carrot/components/c02-deferred-replacement-v1/COMPONENT.json). It touches only `delivery_choice.py`, so it composes directly with the checked-in future-own-supply seller component. Either component order deterministically produces the same 93-member interaction archive, SHA256 `3bd665c3a88425964b396703f3531a93d68b9e67680b3fbff812a2d2fa9f3778`; that interaction archive is unmeasured and remains held.

```bash
python build.py \
  --baseline /path/to/titan-v5-production-recovery-v3.tar.gz \
  --tar /fresh/path/titan-v5-c02-deferred-replacement.tar.gz \
  --receipt /fresh/path/titan-v5-c02-deferred-replacement.json
python -m unittest test_build.py
```

For the native split, run seeds `2051966578,1209125501,1209131101,1209131102`, both seats, against Apex_v7 and Arlene_v14. Compare candidate-only games with existing exact-production20f controls only when opponent, seed, seat, engine and execution settings match. Report raw scores, terminal status, failed FEED/PICKUP counts, animal survival and archive SHA in `#sim-data`.
