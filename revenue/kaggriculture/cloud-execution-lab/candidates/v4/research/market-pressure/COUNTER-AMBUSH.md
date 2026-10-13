# TITAN V4 COUNTERAMBUSH — Apex anti-clone market response

`apex_counter_ambush.py` source-binds the public Apex V7 anti-clone market behavior and asks a narrow question before TITAN adopts any counter-policy: **does front-running the front-run actually create an opponent-conditioned economic edge under the official market interpreter?**

This package is evidence-only inside the existing `research/market-pressure/` authority. It does not change runtime, controller, config, defaults, archive, evaluator, or Kaggle behavior.

## Authenticated mechanism

The oracle refuses source drift from:

- official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`;
- Apex `main.py` SHA-256 `1f7cd5fb8a16585936d2562a3667f85bb6661688718ef58f73006de66148354a`, also required to match `REFERENCE-POLICIES.json`.

On those exact bytes Apex latches `is_clone` during steps 2–10 when the opponent has at least 3 hands and at least one COOP/PASTURE. Its extra anti-clone sales are bounded: MELON step249 max12; STRAWBERRY step381 max8, step403 max8, steps499–501 max8; FERTILIZER step522 **max4** via `min(fert - 16, 4)`.

The official market quotes both players from the same pre-commit inventory for each unit, then commits both. SELL and BUY_PRODUCT execute per-unit. BUY_PRODUCT FERTILIZER quotes at post-buy inventory. A successful SELL at the $1 floor removes the seller's stock and pays $1 but does **not** add that unit to market inventory.

## Result

### FERTILIZER SPONGE — falsified as an Apex-specific “massive subsidy”

Across start inventory 9000–10600, the direct next-turn quote advantage from buying exactly the four units Apex can at most add is at most **$4**. At neutral inventory 10000 it is **$3**. At the FERTILIZER $1 floor (inventory 10493 in the exact engine) Apex's sell adds **zero** market units, so the opponent-attributable subsidy is **$0**.

Buying more than the units Apex actually added may still be a separate fertilizer/crop policy, but it is not an Apex-subsidized counter and must prove its own cash, shed-capacity, crop-yield, and terminal-value economics.

### STRAWBERRY 380/402 CUT — mechanically real, policy unproven

For two isolated eight-unit SELL blocks, moving our block before Apex redistributes cash toward us and away from Apex. At neutral inventory 10000 the transfer is **+$121 to us / -$121 to Apex** with the same final inventory. In the bounded 9800–10080 sweep the largest observed transfer is **$193** at inventory 9992. Once STRAWBERRY is at its $1 floor (inventory 10062), the transfer is zero.

That is only gross market-order advantage. It does **not** prove TITAN should liquidate strawberries at 380/402: the field gate still has to price current stock, shop demand, authored-sale displacement, future rebound, row budget, and both-seat terminal margin.

## Run

From repository root:

```bash
python -B revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/market-pressure/apex_counter_ambush.py --json
python -B revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/market-pressure/test_apex_counter_ambush.py
python -O -B revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/market-pressure/test_apex_counter_ambush.py
```

## Handoff

Do **not** field the FERTILIZER sponge as an Apex-specific response. The surviving execution demand is strawberry-only: current-native BASE vs opponent-conditioned 380/402 candidate, both seats, against authenticated Apex, preserving existing row-cap/ordering owners and reporting natural trigger rate, displaced sales/shop consumption, own cash, Apex cash, final market inventory, and terminal margin.
