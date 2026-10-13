# Public market-flow intervals for the one TITAN V4

Status: locally built and verified; **not published, merged, activated, or evaluated for game strength**.
Destination: `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/public-market-flow/`.
No successor V4 branch, materializer invocation, feature key, default flip, workflow dispatch, or Kaggle upload is part of this contribution.

## Purpose and existing ownership

This is an additive evidence utility for existing L3/B10/C5 research, not another controller or a replacement for their source owners. Prior L3 work already established the positive rival-supply lower bound. This extends that accounting to two-sided effective-net-supply intervals, gross-sale/buy lower bounds, and explicit ambiguity. The current C5 oracle lane retains its owner. This package does not assert that any existing controller is incorrect without testing that controller's exact source.

B10's missing-current-order boundary remains real. Completed-turn observations can yield useful training/evaluation labels, but do not identify the rival's current market row or forecast the next action. A regression demonstrates two different rival row positions producing identical observed outcomes.

## Supported interface

```python
from public_market_flow import infer_public_market_flow

receipt = infer_public_market_flow(
    previous_observation,
    next_observation,
    exact_final_own_action_submitted_between_them,
    configuration,
)
if receipt['status'] == 'ok':
    milk = receipt['products']['MILK']
    # Bounds refer to the COMPLETED turn only.
    lower = milk['rival_net_supply_lower']
    upper = milk['rival_net_supply_upper']
    # An exact gross quantity is conditional and can be None.
    exact_sales = milk['rival_exact_sales']
```

Required public fields: `player`, `step`, `market.inventory`, `market.prices`, and the previous observation's `town.unlocked_shops`. Full observations may be supplied; private/farm/current-opponent-action fields are never read. Tests put access-raising objects in those fields.

The caller must bind both observations to the **same episode** and provide the actual final submitted own action, not an earlier planner proposal. Consecutive step numbers alone cannot prove episode identity. The utility rejects gaps, repeats, invalid player changes, inconsistent quotes, unsupported price curves, and malformed supported inputs. It does not maintain cross-episode memory.

Supported numeric domain is deliberately conservative: default engine price curves; public inventory integers from -1e9 through +1e9 (negative public stock is legal); 1..100 market slots; positive shop/center periods through 1e6; 2..1e6 episode steps. Unsupported configurations return `status=unknown`, not a guessed signal. Official raw-row truncation occurs before parsing. Integer coercion for ordinary JSON order quantities follows the pinned engine, including numeric strings, floats and booleans; configuration and observation integer fields reject booleans.

## Accounting proof

For each product, let

`D = after_inventory - before_inventory + exact_town_consumption`.

The pinned interpreter executes market orders before town consumption, so

`D = own_effective_net_supply + rival_effective_net_supply`.

Effective supply is +1 for a successful SELL quoted above $1, 0 for a $1 SELL, and -1 for a successful BUY_PRODUCT. Own requested quantities only provide upper bounds on executed units. If `S` and `B` are capped own SELL and BUY_PRODUCT request totals, then

`D - S <= rival_effective_net_supply <= D + B`.

The implementation intersects this interval with the engine's per-row iteration ceiling and with nonnegativity for products the engine cannot buy. It never combines marginal intervals into an invented executable joint path.

For sell-only products, public market supply is monotone within a market phase. When the final **pre-town** quote exceeds $1, every successful sale changed public supply, so the effective-supply interval is also a gross-sale interval. Otherwise floor-price sales can be invisible. For WHEAT/FERTILIZER, netting purchases against sales is an additional ambiguity; zero net supply cannot establish zero trading.

### Three important witnesses

1. Eight MILK units can sell at the $1 floor, leave public inventory unchanged, and then town consumption can raise the next observed quote above $1. Looking only at the next quote falsely uncensors those sales.
2. An own SELL request for 20 units can execute zero because the shed is empty. Treating the requested quantity as an executed receipt invents negative rival supply.
3. Ten malformed raw market rows exhaust the default cap. An eleventh SELL cannot be resurrected by filtering out malformed rows before counting slots.

Repeated shops consume separately. End-of-day newly unlocked shops are excluded from the already-completed turn's consumption. Consumption uses the completed step, not the next observation's step. The exact tests exercise those boundaries.

## Reproduce

No Kaggle package or network is required for the test harness. Supply the exact pinned `kaggriculture.py` file. A checksum mismatch stops execution. The companion delivery bundle includes that reference and its license; they are not duplicate additions to the repository patch.

```sh
python test_public_market_flow.py --engine /path/to/kaggriculture.py --cases 12000 --report normal.json
python -O test_public_market_flow.py --engine /path/to/kaggriculture.py --cases 12000 --report optimized.json
python check_mutations.py --engine /path/to/kaggriculture.py --report mutations.json
```

The tests execute the actual official `interpreter`, `_process_market`, `_commit_unit`, town consumption, and end-of-day routines on initialized synthetic states. A recording wrapper calls the original `_commit_unit` and records successful ground-truth fills; it does not substitute simulated commits. The sole dependency shim is `resolve_episode_seed`, which raises if called and is not reached in initialized fixtures.

Observed local execution: Python 3.13.5; 24/24 tests normal and optimized; 12,000 generated full-interpreter transitions per mode; both player perspectives; 216,288 product certificates checked per mode including focused fixtures; 60,723 exact-sale certificates checked per mode; 2,340 quote comparisons per mode. Seven deliberately incorrect variants were rejected in both modes, all by test failures rather than harness errors. The optimized run repeats the same deterministic corpus; it is not another independent 12,000-case sample.

These are synthetic engine-semantic tests, not hosted replay differential, held-out opponent, runtime integration, production-release, or game-strength evidence. No dollar/rating improvement is claimed.

## Safe intake

The delivery includes an additive repository-relative patch. Re-read current `CANONICAL.json` and this destination before intake; an equivalent existing implementation should win over duplicate publication. Apply only to the existing main-line workspace. The patch touches no pre-existing file and no runtime seam. Do not execute the retired V3/V4 materializer against production as an intake shortcut.

## Provenance

- Canonical contract observed: Git blob `00142be0ff2314dcb23068c8133b34d290661923`.
- Official engine: Git blob `3c202c7ee921da239356789e266b694635103fc4`, 40,356 bytes.
- Engine recovered from existing GitHub artifact `10285621024`, run `34654498000`; no workflow was dispatched.
- Source/transport metadata in that artifact names checkout `8250aec877974e9a1feba2b8e33fcd51000857d4`. That is engine evidence, NOT a V4 integration base.
- Earlier B10 boundary: Slack `C0C0Z8AHGP2`, timestamp `1789118802.891929`.
- Earlier L3 lower-bound work: Slack `C0C0Z8AHGP2`, timestamp `1789118052.464839`; review `1789118219.429099`.
- Latest active C5 oracle observed during this work: Slack `C0C0Z8AHGP2`, timestamp `1789178581.648109`.

See `VERIFICATION.json` and `MUTATION-RESULTS.json` for machine-readable execution receipts. This session's available connectors were read-only and the container had no outbound network; no Slack claim or handoff message was sent.
