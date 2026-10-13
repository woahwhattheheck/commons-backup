# ASTRA-HERDSCALE: animal throughput evidence

This lane is **research-only and policy-inert**. It exists because the 2026-09-12 current-V4 fertilizer gate showed a structural mismatch: sale-side behavior was already moving hundreds of FERT/game while the base collected only hundreds, far below the four-figure fertilizer volume seen in stronger traces. Tweaking the seller cannot create fertilizer that the worker schedule never collects.

This directory is the **sole current-tree HERDSCALE census authority**. PR #12865 removed a later duplicate `research/collection-scale/` root; unique follow-up belongs here instead of creating another animal-scaling package/controller.

## Engine theorem

The official engine makes fertilizer collection unusually crisp:

* every animal owns one boolean `fertilizer_available` flag;
* EOD refresh sets that flag to `True`;
* one successful `COLLECT_FERTILIZER` clears the flag and adds exactly one FERT.

Therefore scheduled `COLLECT_FERTILIZER` worker rows are a hard **upper bound** on fertilizer units collectable from an authored route. Bad positioning, duplicate workers on one animal, missed placement, starvation, or any other no-op can only make realized output lower.

## Two source surfaces, one authority

### Donor R04 mechanism census

`animal_throughput_census.py` authenticates the exact donor `r01_tapes.py` and `r04_full_router.py` blobs. That router uses plan 0 for steps 0..143, the selected plan for 144..647, and plan 2 for 648..718. The census reconstructs all 13 effective donor splices and reports scheduled collection ceilings, daily collection slots, animal buys/placements, BUILD/FEED/CARE/HARVEST/DROP/PICKUP cadence, and relevant market rows.

This is useful source/mechanism evidence, but donor R04 is not by itself proof of the current production route bank.

### Current frozen Arlene route census

`current_arlene_census.py` closes that source gap. It fails closed unless current frozen Arlene is the exact Git blob `bdb9cf58148a3c7961c085f4902759537decabf6`, verifies the real lazy `routes()` decoder, requires the four declared 720-turn routes, and respects Arlene's `MAX_ORDERS=10` executable market prefix.

It reports, per current route, BUY_ANIMAL quantities, PLACE rows, FEED/CARE/HARVEST/COLLECT cadence, animal-product SELL quantities, first/last authored spans, service ratios per authored animal purchase, and the scheduled-FERT upper bound. The output explicitly declares `decision_authority=false`: route-bank structure is not realized execution or EV, because movement/no-ops, private inventory, repairs, and final-return transforms can alter what executes.

## Run

```bash
# Donor/source mechanism surface
python revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/animal-throughput/animal_throughput_census.py \
  --output /tmp/herdscale-donor.json
python revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/animal-throughput/test_animal_throughput_census.py

# Current frozen Arlene route-bank surface
python revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/animal-throughput/current_arlene_census.py \
  --output /tmp/herdscale-arlene.json
python revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/animal-throughput/test_current_arlene_census.py
```

The admission rule remains conservative: do not add animals merely because acquisition is structurally possible. A herd-expansion proposal must have current-native evidence for executable worker service, feed, structure, carry/shed and sale capacity. HOMESTEAD/goose-census own opener/acquisition economics; FERTDEADLINE owns existing-animal deadline rescue; LABORFLOW owns generic worker assignment; CARRYBANK owns carry/shed hoisting; existing H3c/S8/feed-service owners retain their submechanisms.

No runtime/default/config/archive/Kaggle activation is made here.
