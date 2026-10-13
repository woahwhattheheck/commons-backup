# TITAN V3 route-checkpoint regret lab — SOL-LEVER

This directory measures the largest explicit discrete policy lever still present in the canonical TITAN producer: the three prefix-compatible route-tail choices inherited from Arlene.

The current producer selects a route continuation only at these public-observation checkpoints:

| turn | public feature | shipped threshold | target tail |
|---:|---|---:|---|
| 226 | unlocked `YARN_STORE` count | 1 | `dc76e4003029ac51` |
| 360 | public `CARROT` price | 42 | `ab9669b9abfbea4e` |
| 433 | public `MILK` market inventory | 10067 | `a84d06f1d12add7c` |

Older `cloud-model-lab/tail_choice.py` observations established only that one route choice can move terminal value by thousands. Those runs used legacy raw Arlene and are **motivation, not current-V3 evidence**. This lab closes that attribution gap.

## What the panel does

For every seed, opponent, seat, and checkpoint, the official pinned interpreter runs three relevant fresh-process games:

1. **AUTO** — untouched current TITAN. It observes the checkpoint but does not mutate the route table or route state.
2. **FORCE** — when the target continuation is prefix-compatible, assign that target immediately before the current TITAN call.
3. **STAY** — temporarily suppress only the matching decision-table row for that call, then restore the exact tuple in `finally`.

One AUTO game is shared by the three checkpoint pairs, so the complete arm set is AUTO plus FORCE/STAY for turns 226, 360, and 433. Every counterfactual game leaves all earlier and later shipped decisions natural.

The evaluator gives every agent a fresh process and private working directory. Before a pair is admitted, the report requires:

- identical public pre-world SHA-256 at the checkpoint;
- identical rival action SHA-256 at that checkpoint;
- identical feature value and source route;
- a prefix-legal switch in both arms;
- successful application and persistence of the requested FORCE/STAY operation; and
- exact full-game action/world/bank reproduction between AUTO and whichever arm represents the shipped threshold choice.

A pair that fails any condition is rejected, named, and excluded. It cannot contribute to threshold selection.

## Threshold screen

`thresholds.py` fits the same monotone rule already used by production: choose the target tail when `feature >= threshold`.

Development and holdout seed sets are explicit and disjoint. Candidate enumeration and selection receive **development rows only**. Objective order is:

1. more wins;
2. fewer losses;
3. more own terminal cash;
4. more terminal margin.

An exact tie retains the shipped threshold. A changed threshold reaches `THRESHOLD_CANDIDATE_SCREEN` only when it strictly improves the development objective and the untouched holdout has:

- no lost wins and no added losses;
- nonnegative own-cash and margin deltas; and
- the same four non-regression conditions independently in both seats and every opponent family.

Even that verdict is only a screen for a separately reviewed runtime patch. This lab never writes a threshold into production.

## Source and execution closure

`SOURCE.json` names commit `2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb` and Git-blob identities for the canonical entrypoint, configuration, runtime, frozen scheduler, producer, evaluator, official engine cache, and opponents. Both the driver and every tested wrapper process fail closed on source drift. The workflow additionally runs `build_integrated.py --check` and rejects changes outside this directory and its own workflow.

Default panel:

- development seeds: `2609104101,2609104102`;
- untouched holdout seeds: `2609104201,2609104202`;
- opponents: exact public Arlene and frozen V1;
- both seats;
- seven route arms;
- 112 complete official games and 48 checkpoint pairs.

Run locally from the repository root after installing the pinned dependency:

```bash
python -m pip install 'kaggle-environments==1.32.7'
python revenue/kaggriculture/cloud-route-regret/run_panel.py \
  --runner-head "$(git rev-parse HEAD)" \
  --development-seeds 2609104101,2609104102 \
  --holdout-seeds 2609104201,2609104202 \
  --output /tmp/titan-route-regret/RESULTS.json \
  --markdown /tmp/titan-route-regret/RESULTS.md
```

## Non-authority boundary

This is an offline development experiment. It does not upload to Kaggle, call a hosted provider, modify the canonical runtime, rebuild a replacement submission, or authorize promotion. Structural workflow success is not a favorable gameplay verdict, and a favorable screen is not merge authority.
