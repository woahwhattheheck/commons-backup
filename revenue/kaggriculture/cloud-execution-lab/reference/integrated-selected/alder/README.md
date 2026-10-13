# T13: bounded unused-seed recovery

**Use `seed_main.py` for the held-tested seed+SELL candidate.** The file
`main.py` is a separate, experimental weed-recovery arm; it is not the primary
entrypoint and is not composed with seed budgeting. No T08 default or hosted
submission is changed here.

## Runtime contract

`seed_main.make_agent(root, sell=True, enabled=True)` returns a fresh per-match
callable accepting `(observation, configuration)`. `sell=False` applies the same
budget to unchanged Arlene; `enabled=False` preserves the selected parent.
The callable invokes that parent exactly once. It projects the actual owned
unit phase with frozen SELL mechanics before inspecting seed stock.

`SeedBudget` counts every future PLANT request, including potentially inert
requests, across all workers. Its upper bound is the maximum over the current
route and routes sharing its complete already-selected prefix. This follows
intact Arlene's `_switch_ok` contract, rather than assuming which future branch
will win. A BUY_SEED request is reduced only when observed post-unit stock plus
that request exceeds this bound. It never increases a purchase. Zero purchases
become empty market slots: later orders retain their indices and priority.
Earlier planned buys are not assumed fulfilled, since cash limitations and an
intervening sale could make only a later buy executable.

No opponent state, public replay action tape, hidden seed, future draw or price
forecast is used by this budget. Worker actions and non-seed market orders are
unchanged. The bound is specific to intact Arlene/SELL routes. Do not stack it
with an overlay adding PLANT requests or rewriting routes without updating the
demand contract and evaluating that new composition on fresh seeds.

## Actual public losses

ROWAN's exact public replays are retained in the sibling
`cloud-frontier-trace/results/t13-public-inputs/`, source commit
`16a2d4a7675c7e27b97bedc00f8073690bf7a763`. Tests verify their raw SHA256 values.
Our chronological observation probe reproduces all 1,438 recorded own Arlene
actions. The weed candidate intervenes zero times in these two losses.

KESTREL's complete causal evidence is in
[`replay_diagnostics/RESULTS.md`](replay_diagnostics/RESULTS.md), delivered by
PRs #9920 and #9932. In episode 106541578, identical production still loses
984 cash through sales/order and purchase differences. Episode 106540665 earns
more sales but loses 531 after greater investment costs. Both finish with
24 unnecessary WHEAT seeds. At step 600, six seeds already cover six of eight
remaining requests; buying two instead of 17 is sufficient. At 624, no further
WHEAT planting request remains, so buying nine is unnecessary.

The runtime derives those same reductions from its own route and observation,
not from the replay. KESTREL's exact 119-transition fixed-action continuations
save 240 cash in each episode while preserving all compared nonfinancial
state, including random boundary fields. These are recorded-action witnesses,
not responsive-opponent games. Remaining deficits are 744 and 291: the two
hosted losses have not been turned into wins. A blanket market-order sort is
excluded because its retained negative control worsens relative cash by 42.

## Paired evaluation

The runtime was frozen before first use of held seeds 9850101 and 9850119.
All three held arms face unchanged Arlene, original Apex and frozen SELL in
both seats, for 12 games per arm:

| Held arm | Wins | Ties | Losses | Failures |
| --- | ---: | ---: | ---: | ---: |
| Unchanged Arlene | 4 | 4 | 4 | 0 |
| Frozen SELL | 8 | 4 | 0 | 0 |
| Seed budget + SELL | 10 | 2 | 0 | 0 |

Seed+SELL gains 240 own cash in all six cases on 9850101, with unchanged rival
cash. All six 9850119 traces are identical to frozen SELL. Two mirror ties
become wins; no held outcome worsens. On development seeds
9850001/9850019/9850037, the corresponding 18-game panels improve from
12W/4T/2L to 16W/0T/2L. Every development case gains 240 or 340 own cash,
with unchanged rival cash; both previous losses remain losses.

[`results/games.csv`](results/games.csv) retains all 102 valid games, cash,
status, full-trace hashes and maximum policy-call times, including negative
results. The 12-game development Arlene panel faces only Arlene/Apex; all
other development panels also include SELL. These are paired cases using
five seeds, not 102 independent random samples. Two held seeds are too few
for a general win-rate estimate or a hosted-promotion claim.

The 30 seed-vs-SELL pairs preserve both players' unit-action frequencies.
All 1,140 retained timeline snapshots match after excluding only own money,
own seed inventory and the original BUY_SEED slots. This is a sampled-state
check, not an assertion of every-transition full-game equivalence. Full raw
report hashes and the four initial pre-action consumer-loader failures are
recorded in [`results/validation.json`](results/validation.json). The loader
failures are excluded from scores; the corrected imported-module controls
are included. No frozen policy bytes were changed to repair that consumer.

The experimental weed arm has 16 focused tests and an 18-game development
result of 13W/4T/1L versus SELL's 12W/4T/2L. It fixes a real independent weed
plant/water omission, but has no hosted intervention and no held evaluation.
Changed crop occupancy changes subsequent engine RNG consumption, so its
large Apex score swing is not attributed solely to recovered production.
It remains an explicitly separate hypothesis.

## Reproduce in a cloud checkout

Use the existing pinned engine directory (artifact 10005621438), Python 3,
and the retained Apex C++ compiler/toolchain. The engine revision is
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. The scripts reuse the existing
process-isolated evaluator and unchanged offline syscall guard. They do not
fetch Kaggle or require another transport job. The runtime destination must
not already exist.

```sh
R=revenue/kaggriculture
T="$R/cloud-hosted-loss-response"
E=/path/to/retained/engine
W=/tmp/t13-clean-runtime
python -B "$T/tests/test_recovery.py" --source-root "$R" --engine-dir "$E"
python -B "$T/tests/test_seed_budget.py" \
  --replays "$R/cloud-frontier-trace/results/t13-public-inputs"
python -B "$T/prepare_runtime.py" --runtime "$W" --source-root "$R"
for arm in seed sell arlene; do
  python -B "$R/cloud-frontier-policy/next-panel/measure.py" \
    --engine-dir "$E" --candidate "$W/$arm-adapter.py" --runtime "$W" \
    --seeds 9850101,9850119 --opponents arlene,apex,frozen --seats 0,1 \
    --output "$W/results/held-$arm.json"
done
python -B "$T/build.py" --arm seed --output "$W/t13-seed.tar.gz"
```

All 25 ALDER tests passed (nine seed, 16 weed). A newly prepared isolated
runtime reproduced held seed 9850101/Arlene/seat 0 with the exact full trace
`6b2ab99336cb19d50d610e91bd838e144651dad87c5fde595b4ddd8eb2f61e87`.
That repeat is a reproducibility audit, not an additional independent game.
The relocated seed bundle also passes the retained raw-file loader, which
supplies `configuration.__raw_path__` rather than a module `__file__`.

The builder verifies all runtime/dependency hashes in `SOURCE-FREEZE.json`,
then exports the selected entrypoint as `main.py`, its dependency, the unchanged
SELL closure and original notices. `BUNDLE-MANIFEST.json` records exported
bytes. The archive is deterministic. `--arm weed` deliberately exports the
separate experimental arm instead; it does not combine the two policies.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
