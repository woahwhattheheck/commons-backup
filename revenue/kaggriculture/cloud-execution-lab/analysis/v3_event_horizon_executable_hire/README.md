# TITAN V3: executable-HIRE closure for represented event horizons

## Exact seam

Audited base: `c51049d671b55d282e0fed5df37a0be7c513a838`  
Canonical source: `revenue/kaggriculture/cloud-execution-lab/frozen_selected.py`  
Canonical Git blob: `fc7baf5c179818a55037f6a61d92984d81d1a21c`

`FrozenSelected.apply_represented_market` currently treats every authored `HIRE`
row as a completed purchase: it calls `m._spawn_hand(...)` and appends a private
inventory immediately. The helper has no official row execution result, no
market price context, and no cash ledger. `represented_shed_event` then lets the
manufactured actor execute later unit rows. A later local shed increase can
extend the SELL optimization horizon through `end=max(end, unit_event)` even
when the official engine rejected the HIRE and the hand never existed.

The market-prefix cap is **not** the claim here: the caller already limits the
represented rows. The missing boundary is physical HIRE execution.

## Minimal predecessor witness

Start with zero cash, no hired hands, and one WHEAT in the shed. The authored
future tape says:

1. `HIRE` (engine-inert at zero cash),
2. the nonexistent new hand `PICKUP WHEAT 1`,
3. that hand `DROP WHEAT 1` after the baseline horizon.

The predecessor manufactures the hand, observes the later `0 -> 1` local shed
increase, and admits the post-baseline date. The conservative candidate does
not invent the actor, so no false extension is admitted. SELL and BUY simulation
are unchanged byte-for-byte.

## Carrier

`materialize_event_horizon_executable_hire.py` is source-bound and fails closed:

- validates the exact Git blob identity;
- validates the four score-path reach fragments;
- replaces exactly one unconditional simulated-HIRE branch;
- leaves emitted actions and every non-HIRE byte untouched;
- emits a receipt with source and candidate Git identities.

The candidate intentionally treats HIRE as unexecuted unless execution evidence
is available. This can create conservative false negatives for genuinely
funded future HIREs, so integration remains `HOLD_FOR_PAIRED_PANEL`; it is not a
score claim and it is not a release authorization.

## Run

```bash
python -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/analysis/v3_event_horizon_executable_hire/test_event_horizon_executable_hire.py

python revenue/kaggriculture/cloud-execution-lab/analysis/v3_event_horizon_executable_hire/materialize_event_horizon_executable_hire.py \
  --source revenue/kaggriculture/cloud-execution-lab/frozen_selected.py \
  --output /tmp/frozen_selected.executable_hire.py \
  --receipt /tmp/frozen_selected.executable_hire.receipt.json
```

## Admission boundary

Run an exact-parent/candidate paired panel on all route/seat/seed cells where a
represented HIRE can feed a post-baseline hand action. Require no parent wins to
flip, positive own-value under the shared V3 gate, and inspect every changed
trace. Until that evidence exists, this is a reproducible repair carrier, not a
canonical runtime mutation.
