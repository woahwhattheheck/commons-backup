# TITAN V3 L02 — ledger-coherent leader tranche

Operation: `titan-v3-l02-ledger-tranche-20260909-01`  
Worker: **SOL-MOMENTUM**

## Objective

Turn the strongest L01 leader-derived gameplay signal into a state-coherent candidate. L01's late sale tranche completed 192/192 development games and posted positive mean margins in all six named opponent strata, but its wrapper edited the action after `TitanAgent.act()` returned. That could leave the emitted SELL queue inconsistent with `FrozenSelected.planned`, `FrozenSelected.pending`, and the runtime's completed seller checkpoint.

L02 installs one bounded selected-action overlay on the canonical one-producer runtime:

- non-operating products are changed inside `FrozenSelected.transform`, then `planned` and `pending` are atomically reconciled before `TitanAgent` builds the seller checkpoint;
- WHEAT is proposed immediately before the existing feed-stock guard, so the canonical reserve certificate can reduce or reject the sale;
- FERTILIZER is untouched because the idle-fertilizer lane owns it;
- inherited market rows never move; only an existing active SELL quantity may grow or a new SELL may append into trailing executable slack;
- all fill/ledger accounting uses only the official `market[:maxMarketOrdersPerTurn]` prefix; inactive tail rows are preserved exactly;
- malformed state fails closed to the unchanged selected action and unchanged seller ledger.

The policy deliberately reproduces the L01 tranche shape rather than inventing a new optimizer: late CARROT is raised toward 32 units, late WHEAT toward 57 before the feed guard, and TOMATO/STRAWBERRY/MELON/EGG/MILK/WOOL are offered in full only when no inherited active SELL for that product exists.

## Evidence contract

`run_panel.py` runs the unchanged canonical entrypoint and L02 in fresh process-isolated official-interpreter cells on the same development opponents, seeds, and both seats. It rejects missing, extra, duplicate, errored, timed-out, nonfinite, or provenance-mismatched cells before reporting paired own-cash and margin deltas. The report binds the Git head, candidate/overlay bytes, canonical producer/runtime/seller/config/source-manifest bytes, evaluator/loader, and opponent entry files.

The default development matrix is 8 seeds × 6 opponents × 2 seats × 2 variants = **192 complete games**. `ADVANCE` is a development decision only; it is not a hosted Kaggle, leaderboard, or automatic canonical-promotion claim.

The hosted workflow still fail-closes on `REJECT` when `candidate.py`, `ledger_tranche.py`, or `run_panel.py` change. `panel_trigger.py` skips only that 192-game matrix when an event did not mutate those executable bytes (GitHub new-branch path filters otherwise re-run the known development REJECT). Unit tests always run. `workflow_dispatch` always runs the panel. ADVANCE vs REJECT is unchanged.

## Local contracts

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_ledger_tranche.py test_panel.py test_panel_trigger.py
```

No canonical runtime, configuration, archive, release pointer, provider state, or Kaggle submission is mutated by this lane.
