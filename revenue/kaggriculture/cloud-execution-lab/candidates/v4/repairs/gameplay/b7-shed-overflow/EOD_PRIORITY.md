# B7 end-of-day priority: a narrow repair, not activation clearance

**B7 remains unpromoted. The immediate EOD gate does not establish multi-turn safety.**

This packet belongs to the existing canonical `main:candidates/v4/repairs/gameplay/b7-shed-overflow` package. It adds no gameplay key, controller, production root, or sibling V4. The raw donor, original oracle, and peer portable-runner work remain unchanged.

## Confirmed counterexample

Using exact official engine `3c202c7e`, both seats independently reproduce this at step 263 (hour 23): the shed holds 100 CARROT; the farmer carries 10 WHEAT and a later hand carries 10 MILK. Commands are farmer DROP, hand PASS, then SELL CARROT 10.

The parent deletes the overflowing wheat during unit execution. The market sale then opens ten shed spaces, and the hand's milk enters at EOD. B7 replaces DROP with PASS, retaining wheat; the EOD inventory-order sweep now deposits that wheat first and discards all ten milk units. First-turn cash is identical. After identical WHEAT/MILK sell orders on step 264, parent cash is 4,834 versus B7 cash 3,565: **a 1,269-coin loss in this constructed case**. This is not an estimate of field frequency or expected value.

`compose_b7_eod_gate.py` accepts only exact donor `a27da659`, adds a strict day-boundary check, and produces blob `d7fc5688`. Unknown/malformed clocks and all EOD turns return the exact parent action. Other valid turns keep the donor's behavior. The composer never installs or enables the result; an optional output must be a new scratch file.

## Remaining multi-turn risk

Moving the initial DROP to step 262 defeats an immediate-turn-only remedy. Wheat retained on step 262 persists until step 263. Even though the new EOD veto correctly returns the parent action on step 263, earlier retained wheat still crowds out milk. The same 1,269-coin loss remains in both seats. `test_b7_carryover_risk.py` deliberately confirms this negative evidence and emits `activation_authorized: false`.

Any future current-ABI port must retain this hold until it proves multi-turn inventory-priority/cargo custody and passes natural-engagement/economic gates. The gate is conservative and can also suppress beneficial EOD retention; it is not an optimal allocator.

## Executed checks

On Python 3.13.5, the repaired full-turn suite passes 19/19 in normal and optimized modes, with byte-identical JSON stdout: 2,592 non-EOD differential cells, 96 EOD identity cells, and 7,980 calls to the unchanged official interpreter per mode. Cases cover both seats, all four shed-access positions, several actor indices, all nine products, rival sells, multiple day lengths, and terminal reward handling. The original 128-cell/5-boundary oracle also remains green. Selecting the predecessor instead yields 122 failing subcases in each mode. Three incorrect-behavior controls are detected. The separate carry-over test passes by confirming the unresolved loss, not by declaring safety.

```sh
B7=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/b7-shed-overflow
python "$B7/test_b7_full_turn_eod.py"
python -O "$B7/test_b7_full_turn_eod.py"
B7_TEST_ARM=donor python "$B7/test_b7_full_turn_eod.py"  # expected nonzero
python "$B7/test_b7_carryover_risk.py"                  # expected residual-risk confirmation
python -O "$B7/test_b7_carryover_risk.py"
python "$B7/compose_b7_eod_gate.py"                    # hashes only; no write
```

The tests verify exact donor, oracle, engine, JSON specification, and read-only runtime hashes. The engine executes units, market, town, decay, EOD, and terminal rewards unchanged. Only the unused seed-resolution import is supplied by a temporary raising shim; all real interpreter turns make zero calls to it. Existing imports are restored. There is no game initialization, runtime import, market substitute, whole-season evaluation, hosted Python 3.11 result, or deadline-performance claim.

See `EOD_PRIORITY_RECEIPT.json` for exact source hashes and numerical results. Production defaults, archive, legacy materializer, Actions dispatch, and Kaggle state are untouched.
