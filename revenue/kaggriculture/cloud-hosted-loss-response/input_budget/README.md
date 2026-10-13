# T13 final-day input budget — ALDER

Optional research callable; the selected TITAN archive and hosted submission are unchanged. Policy source was frozen before held evaluation at `86b2f8d3d3c1115d558368a5b58d01edd118f901` (core blob `f64e932d`, adapter `5e1f36e2`). Full source, original traces, all attempts and reproducible drivers are retained in the Library ZIP identified by [EVIDENCE.json](EVIDENCE.json).

## Mechanism

The intact routes buy fertilizer at final-day opening 696 and make their last pickup at 697. A naive aggregate cap finds no excess: one reached case has 1 existing + 22 purchased units for 23 pickups. Instead, the last pickup worker collects a visible on-farm fertilizer unit before its first service. One less purchased unit can preserve every authored movement, service and harvest.

`FinalInputBudget.transform(obs, cfg, selected_action, route)` consumes one already-selected action; it never calls the parent or reads rival private state, hidden seeds or future random draws. It reuses the pinned own-unit primitives, parent weed repair, atomic planting rules and decay. Every intermediate unit effect is compared, including a FERTILIZE→WATER→HARVEST same-turn case whose end-of-turn crop removal otherwise hides lost yield. The first physically different lower quantity ends the search. Market slots and all worker actions remain unchanged; a fully canceled order becomes `[]`.

This is a restricted physical comparison, **not a universal financial guarantee**. It applies only to the final-day opening, with deterministically funded hires, one last fertilizer purchase, and no later purchases or depot pickups after the immediate pickup wave. Rival price effects and terminal resale are measured separately.

## Consume

```python
from candidate import make_agent
policy = make_agent(parent=existing_default_titan)  # same parent, called once
result = policy.act(observation, configuration)
# make_agent(enabled=False) is the paired no-trim control.
```

Use a fresh actor per match. Tested producer: PR10177 default-path closure, `consumer='frozen'`, seed/funding enabled, terminal route/history disabled. Do not stack on a changing route or after an action-recording history stage without integration testing. The adapter counts parent elapsed time against the existing deadline; its own expiry returns the intact parent action and unrelated errors propagate.

`entrypoint.py` is the raw Kaggle-file bootstrap. Direct raw execution of `candidate.py` lacks `__file__`; the bootstrap loads the unchanged module normally. This packaging path matched 719/719 expected actions from one retained held stream. It is not another game or source promotion.

## Measured outcomes

| Phase | Seeds / opponents, both seats | Candidate | Paired control | Mean own / rival / margin delta |
|---|---|---|---|---|
| Development | 9852001, 9852019 / Arlene, frozen SELL | 8W/0T/0L | 8W/0T/0L | +1.00 / −1.50 / +2.50 |
| Held | 9852101, 9852119 / canonical default, Apex | 8W/0T/0L | 4W/4T/0L | +1.75 / −2.00 / +3.75 |

[RESULTS.json](RESULTS.json) retains every terminal score by seat. Four held T→W rows represent **two independent mirror-match seeds**, each played in both positions. Apex wins were retained. Held margin effects are only 1, 4 or 6 cash; maximum candidate call was 77.48 ms in this cloud runtime. No hosted rating gain or broad strength claim follows.

All 16 paired cells / 11,504 paired rounds preserve both players' worker actions, physical farms and non-fertilizer private quantities. On development 9852001, reduced cost10 is offset by own resale loss10; rival resale falls1. On 9852019, cost falls5, own resale3, rival resale2. The opening quote is not the aggregate ordered-lot cost.

Development used the earlier physical projection; the strengthened final projection returned the same actions on all eight retained reached decisions. Final core/adapter were published before held games. The evidence retains two excluded complete attempts (one inert wrong-status wrapper, one pre-deadline preview) in addition to the 32 panel games, not 34 scored panel games.

## Checks and reproduction

28 final methods cover queue/physical boundaries, same-turn interactions, atomic planting, no mutation/rival reads, parent-once and actual self-deadline fallback. Eight reached development contexts have 32 official fixed-recorded-action continuations / 736 transitions. All eight original baselines reconcile exactly; one-unit cuts preserve farm state, while every second-unit cut loses harvest value. Recorded future actions are used only offline in these witnesses, never by the runtime.

Repository test: `python revenue/kaggriculture/cloud-hosted-loss-response/input_budget/test_input_budget.py` with the compatible canonical sibling. Exact reproduction uses the pinned Library bundle, avoiding moving-main dependency substitution:

```sh
python work/test_input_budget.py
python work/check_raw_entry.py
python work/counterfactuals.py
python work/run_panel.py --seed 9852001 --seat 0 --arm candidate --opponent sell --output-root reproduced
```

The last command creates a separate output directory, not overwritten historical evidence. ZIP layout is `work/`, `runtime/`, `bank/`, `engine-bank/engine/`, `results/`; its full README gives commands, retained source phases and limits. A fresh extraction verified all 295 manifested members, passed 28 methods and reproduced raw719 correspondence. No new engine game was needed for relocation acceptance.

Official engine pin: Kaggle/kaggle-environments `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; engine SHA256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`. Tested TitanAgent SHA256 `58ea0d32db8e5f40de86f45f3709d065c3ccdb7c09ee11adcae3ebc0ee6ef9d7`. This is source-closure consumption, not materialized-current-tar acceptance. [NOTICE.md](NOTICE.md) preserves upstream lineage. No canonical runtime/package, peer source, owner PC, new spend or Kaggle write was changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
