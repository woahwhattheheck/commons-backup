# TITAN V5 P04 — observable route ranking

This directory is the **P04 matrix consumer**, not another route-force harness. The shared R00–R12 carrier owns the step-144 intervention. This tool only validates and reduces those immutable rows.

## Frozen source facts

- Production candidate: `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`
- Active R04 source SHA256: `41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a`
- Route selection is at step `144`; plan `2` is forcibly restored at step `648`.
- Normal step-144 plans are `0,1,3..12`; plan `2` is matrix-diagnostic only unless later evidence explicitly justifies changing that design.
- Prior deterministic source census: commit `93c9fefa83868d108139e8367d4b99ba6e39dd73`.
- Route crop programs collapse to two known signatures: plans `0,1,3,4,5,6,7,8,10,11` use `W146/C31/S29`; plans `9,12` use `W148/C28/S29`.
- Animal acquisition is the larger static discriminator: plan0 `COW4/SHEEP4/GOOSE3`; plans1/4/5 `COW2/SHEEP8`; plans3/6/7/8/9/10/11 `COW2/SHEEP9`; plan12 `SHEEP12`.

## Required row contract

One JSONL row per forced plan and pre-step144 snapshot:

```json
{
  "seed": 1209131101,
  "opponent": "apex_v7",
  "seat": 0,
  "forced_plan": 7,
  "snapshot": {
    "first_two_shops": ["PIZZA_SHOP", "YARN_STORE"],
    "market": {"prices": {}, "inventory": {}},
    "own": {"cash": 0, "worker_count": 0, "animal_counts": {}, "crop_counts": {}},
    "rival": {"animal_counts": {}, "crop_counts": {}},
    "incumbent_plan": 7
  },
  "snapshot_sha256": "...",
  "terminal_own": 0,
  "terminal_rival": 0,
  "terminal_margin": 0,
  "failures": []
}
```

The reducer fails closed unless all 13 forced plans share the same canonical pre-selection snapshot for each `(seed, opponent, seat)` group. Rival shed/private inventory, future town state, and RNG/future fields are rejected. The incumbent plan is recomputed from the exact `SHOP_PLANS` source mapping rather than trusted from the row.

## Run

```bash
python -B p04_route_ranker.py matrix.jsonl --output p04-report.json
python -B -m unittest -v test_p04_route_ranker.py
python -O -B -m unittest -v test_p04_route_ranker.py
```

The report ranks plans per snapshot, computes incumbent regret and per-plan deltas, and emits low-complexity observation-only feature strata. It **always keeps `policy_ready=false` on discovery rows**. A runtime selector needs a predeclared rule plus fresh held-out native games; fitting the R00–R12 discovery matrix alone is not promotion evidence.
