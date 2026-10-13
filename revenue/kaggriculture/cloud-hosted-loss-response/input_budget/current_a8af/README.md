# Current a8af final-input-budget compatibility

This is a source-fixed development comparison of ALDER's existing final-day
fertilizer budget against the exact canonical TITAN package that root submitted
for the September 8 checkpoint. It does not change that package, its configuration,
or the hosted submission.

## Exact composition

The candidate wraps one ordinary canonical parent and then calls the already-landed
`FinalInputBudget.transform` only after the parent returns a completed action.
The wrapper does not construct a second producer and does not read rival-private
state, hidden seeds, or future random events.

- Canonical archive SHA-256:
  `a8af2b834bb5e1d6486245b9538c2de5a041085be38c7707d08e6d49e6149e89`
- Exact packaged `TitanAgent` SHA-256:
  `58ea0d32db8e5f40de86f45f3709d065c3ccdb7c09ee11adcae3ebc0ee6ef9d7`
- Existing wrapper Git blob:
  `19893f2c5d7b4835a14119d2dd489bef819f076d`
- Existing economic core Git blob:
  `f64e932d6c6959a95574d245ab36808a4c4a85e3`
- Existing raw bootstrap Git blob:
  `9b5f2f33c414228a8a52258bbdbf566e85f41eff`

The packaged `TitanAgent` is byte-identical to the runtime in ALDER's original
held evidence. All 28 existing economic/adapter regression methods pass on the
extracted a8af source without an adaptation.

## Fresh development comparison

Development seeds `9852401` and `9852419` were checked in Slack and the current
repository before execution. Each arm played both seats against frozen SELL and
Apex: 16 full games total, eight paired cells.

| Arm | W | T | L | Failures |
| --- | -: | -: | -: | -: |
| Exact a8af control | 7 | 0 | 1 | 0 |
| a8af + final input budget | 7 | 0 | 1 | 0 |

The candidate activates in six of eight pairs and trims exactly one final-day
fertilizer unit. Two pairs remain action-identical. Across all eight pairs:

- mean own cash delta: **+1.375**
- mean rival cash delta: **-1.25**
- mean margin delta: **+2.625**
- paired result flips: **0**
- largest pair: **+3 own / -3 rival / +6 margin**

Against frozen SELL, mean margin delta is +1.25. Against Apex it is +4.0.
Candidate maximum recorded call is 87.68 ms and maximum RPC is 88.99 ms in this
cloud evaluator. This is a small positive economic transfer, not a new win-rate or
leaderboard claim.

## Physical correspondence

`check_current_a8af.py` reads the saved reports; it never calls a policy or game.
Across eight paired games it verifies, for both players at all 719 decisions:

- **11,504 worker-action comparisons** match;
- **11,504 physical-farm comparisons** match after removing money only;
- **11,504 non-fertilizer private-state comparisons** match;
- **11,504 non-fertilizer market comparisons** match;
- **11,504 ordered market-queue shapes** match after abstracting only the
  fertilizer quantity.

Active pairs first differ at the final-day opening, decision 696. Later market
quantity changes reflect the one-unit purchase reduction. No other product order,
worker action, or physical farm state changes. Rival cash can change because the
same rival sale receives a different fertilizer quote.

The official pinned raw-file loader replays 719/719 saved candidate actions with
zero mismatch. That is a **main-thread** packaging check. The separately reported
a8af worker-thread `signal` defect remains owned by the canonical integration
session; this wrapper inherits the parent deadline implementation and is not a
replacement for that repair.

## Reproduce

Use the complete Library evidence package named in `EVIDENCE.json`. It contains the
exact a8af tarball, wrapper/core/bootstrap, evaluator, official engine, Apex source,
all 16 result files and frame streams, interrupted-launch record, source freeze,
logs, and these checks.

```sh
python -B check_current_a8af.py \
  --panel evidence/results/panel-9852401-9852419 \
  --source-freeze evidence/results/source-freeze.json \
  --raw-check evidence/results/RAW-CURRENT-CHECK.json \
  --output /tmp/current-a8af-correspondence.json

python -B test_current_a8af_check.py
```

The first bounded batch ended while one isolated cell had produced no report or
frame bytes. That empty attempt is retained and never counted as a game. The same
identity then completed normally in isolation. No score was invented for the
interrupted attempt.

These seeds are now development history. Any changed candidate needs new seeds and
its own source freeze. This component neither advances the canonical current pointer
nor requests another Kaggle upload.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
