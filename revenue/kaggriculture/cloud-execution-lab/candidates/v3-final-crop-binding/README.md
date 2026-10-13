# TITAN V3 final crop-binding candidate

Operation: `op:titan-v3-final-crop-binding-20260909-01`

## Defect

The enabled crop-release path creates receipt-critical market edits in
`SpatialTempo.crop_market()`:

- an appended `BUY_PRODUCT WHEAT` lot, or
- exact-index reductions of existing `SELL WHEAT` lots.

`TitanAgent._finish_production()` currently calls
`guard_crop_returned()` before `_early_capital_selected()`. The canonical
entrypoint then uses that early-capital seam to apply final market pressure.
Those late transforms may reorder the exact rows after the guard has accepted
them.

`commit_input_repair()` correctly refuses to attribute a receipt to a changed
queue. If the WHEAT buy or changed sale rows remain executable, it marks
`input_repair_unknown`; future repair is then suppressed to avoid duplicate
purchases. The result is legal gameplay but stranded crop-recovery state.

## Candidate

`FinalCropBindingAgent` makes a live crop input repair the sole owner of that
decision's market queue. Feed stock already declines this ownership collision;
the candidate extends the same rule to early-capital and final pressure. It
also moves the crop binding guard after all market-edit seams and before every
receipt/history commit.

Ordinary decisions retain the exact canonical order:

`feed stock -> early capital -> final pressure -> receipt commits`

Crop-repair decisions use:

`repair-owned queue -> final binding guard -> receipt commits`

No route, quantity, product choice, feature default, canonical source, archive,
release pointer, or provider/Kaggle state is changed by this candidate.

## Acceptance

The focused suite:

1. proves current-source finalizer order guards before the late mutator;
2. constructs an appended WHEAT repair that remains executable after reordering
   but poisons the receipt state as `input_repair_unknown`;
3. proves the same exact queue binds a pending fill receipt under the candidate;
4. repeats the receipt-critical proof for WHEAT-sale withholding;
5. proves ordinary actions still execute capital then final pressure;
6. proves the candidate binding guard sees the exact final queue.

Run from the candidate directory with the lab on `PYTHONPATH`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="../..:." \
  python -m unittest -v test_final_crop_binding.py
```

This is a source-correctness challenger. Full matched official-engine games,
not these contracts, decide playing-strength promotion.
