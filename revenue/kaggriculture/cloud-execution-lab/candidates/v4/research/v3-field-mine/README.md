# V3 / V3.1 hosted-field snapshot

This research packet freezes the public coordination data posted for TITAN v3 and
v3.1 on 2026-09-11 and makes the small set of conclusions we are actually
entitled to reproduce. It is **not** a live Kaggle scrape, evaluator, promotion
rule, or claim that any V4 mechanism caused a historical result.

The snapshot was captured before a later v3 loss arrived. That later event is
kept in `post_snapshot_events`, so the analyzer deliberately reports
`snapshot_is_current=false`; consumers must not describe the 151-game v3 window
as the current record.

## Reproducible findings

Run:

```sh
python analyze_field_snapshot.py snapshot_20260911.json
python -m unittest -v test_analyze_field_snapshot
python -O -m unittest -v test_analyze_field_snapshot
```

For the frozen v3 close-loss cohort, all 15 recorded losses are within $491;
median deficit is $215, 9/15 are within $250, and 5/15 are within $100. Among
the seven rows with a known opponent rank, the median rank is 86. Those are
**numerical flip targets**, not replay counterfactuals: a +$215 mechanism cannot
be credited with a win unless it actually engages in the same cell and paired
evidence preserves the rest of the game.

The v3.1 snapshot contains 81 games but zero top-20 exposure, with best known
opponent rank 125 and median known opponent rank 543. All four recorded v3.1
losses were against same-day fresh submissions. Conversely, the frozen v3
sample was 0-6 against current top-20 opposition. Aggregate v3.1 W/L therefore
must not be used as evidence of top-field robustness without a deliberately
harder, freshness-aware opponent panel.

A later hosted result, episode `108020335`, arrived after the snapshot: v3
61,766 vs 62,770 (margin -1,004), opponent submission `56146954`. It is retained
only as a drift marker here; the separate replay-autopsy owner owns action-level
diagnosis.

## S2 / dairy boundary

Replay/action data is appropriate for **cohort discovery** (for example, select
dairy-heavy rivals from observed COW buys and MILK sells). It is not sufficient
to establish the S2 cow-to-sheep counterfactual when the rival's behavior would
respond to changed shared-market prices. Freeze a dairy cohort before reading
S2 deltas, then run current baseline/S2 against responsive fixed opponent
artifacts, the same seeds, and both candidate seats through the canonical
`research/paired-field-gate` screen.

No gameplay source, feature default, runtime, archive, materializer, workflow,
or Kaggle submission is changed by this packet.
