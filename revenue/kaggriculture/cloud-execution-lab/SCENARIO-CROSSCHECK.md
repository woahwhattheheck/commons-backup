# Bounded SORREL scenario-adapter cross-check

Three fixed development-trace cases passed. Adapter and frozen v3 MarketPath
agree exactly on both players' baseline/candidate sale receipts and their
relative cash changes. Zero full games, optimizer searches or held-out reads
were performed; the candidate source remains unchanged.

Run `python -B scenario_crosscheck.py`; add `--write-report` to refresh this report.

| Seed9600803 case | Fixed own plan | Baseline own/rival | Candidate own/rival | Own delta | Rival delta | Relative delta |
| --- | --- | --- | --- | --- | --- | --- |
| 195 MILK vs arlene | 8 at 195; 4 at 197 | 2237/2237 | 2223/2259 | -14 | +22 | -36 |
| 600 MILK vs arlene | 9 at 600; 8 at 601 | 222/222 | 240/222 | +18 | +0 | +18 |
| 625 STRAWBERRY vs apex | 24 at 629 | 1981/171 | 2074/309 | +93 | +138 | -45 |

The step600 MILK case includes floor admission: the baseline sells17 each but
admits only10 each; splitting9/8 preserves the exact paid-versus-admitted
distinction. Step625 again shows why an own-receipt gain can lose relative
cash: own +93 accompanies rival +138.

## Interface and assumptions

- `infer_rival_flow` uses adjacent public market/town observations and own
  orders. These three checks supply focal own sale counts reconstructed from
  exact post-unit own shed minus the next observed own shed. Neither rival
  actions nor rival stock labels enter inference. It preserves floor-sale
  ambiguity instead of identifying gross sales from admitted flow.
- `supply_scenarios` consumes only completed inference history: here each
  transition is used from its after-observation. It produces unweighted
  no-supply, recent lower/upper persistence, and two hypothetical full-shed
  order-alignment cases. Those broad scenarios differ from v3's visible
  crop/harvest magnitude and explicit next-turn/delayed-batch hypotheses.
- `score_paired_plans` accepts full SELL-only queues, keeps duplicate slots,
  recomputes both seats' fills/admission and applies supplied arrival capacity.
  It performs no optimization and no wages/buys/production simulation.
- This check explicitly projects only the focal non-buyable product's SELL
  slots; other slots become PASS. Their expenses and production effects are
  outside this bounded receipt comparison. Actual baseline focal receipts
  reconcile exactly, and all initial/final focal stocks obey capacity.
- Fixed realized rival sales are offline evaluation labels. They are not
  forecasts, private-stock inference or permitted future runtime features.
- Adapter scores cash receipts only. MarketPath additionally values retained
  stock at short artificial boundaries. Every compared fixed plan sells its
  complete focal lot, making that continuation term zero in these cases.
  General cash-only adapter output must not replace v3's continuation value.
- Adapter arrivals occur before each supplied turn's market; an EOD receipt
  available next turn must be dated accordingly by its caller.

Source: Commons `0a1f0ec35e903c4b6052681ecf976705a29ab902`,
`revenue/kaggriculture/cloud-frontier-decision/execution/scenarios/adapter.py`.
The adapter imports only standard-library `math.ceil`; this cross-check
supplies the already-preserved exact engine quote and town constants.
Apache-2.0 notices are retained under `reference/scenario-adapter/`.

Elapsed local cross-check time: 0.4076 seconds.

## Exact receipts and source hashes

```json
{
  "cases": [
    {
      "step": 195,
      "product": "MILK",
      "opponent": "arlene",
      "horizon": 197,
      "quantity": 12,
      "candidate_fixed_plan": [
        [
          195,
          8
        ],
        [
          197,
          4
        ]
      ],
      "rival_alignment": "paired",
      "baseline_cash": [
        2237,
        2237
      ],
      "candidate_cash": [
        2223,
        2259
      ],
      "own_delta": -14,
      "rival_delta": 22,
      "relative_delta": -36,
      "own_admissions_baseline": 12,
      "own_admissions_candidate": 12,
      "rival_admissions_baseline": 12,
      "rival_admissions_candidate": 12,
      "public_flow_inference": {
        "status": "identified_interval",
        "market_delta_plus_town": 24,
        "known_town_units": 0,
        "own_market_supply_units_range": [
          12,
          12
        ],
        "own_buy_units_range": [
          0,
          0
        ],
        "rival_net_market_flow_range": [
          12,
          12
        ],
        "rival_market_supply_units_range": [
          12,
          12
        ],
        "rival_sale_units_range": [
          12,
          12
        ],
        "floor_nonadmission_possible": false,
        "rival_stock": "unknown",
        "order_alignment": "unknown",
        "gross_buy_sell_ambiguity": false
      },
      "generated_hypothesis_ids": [
        "no_rival_supply",
        "recent_lower",
        "recent_upper",
        "competitive_stock_slot_0",
        "competitive_stock_slot_1"
      ],
      "trace": "baseline-arlene-9600803-seat0.jsonl.gz",
      "trace_sha256": "19116ea19778349c0ba6368877b3bef6959ed30715261b004b27829698070a0d",
      "agreement": "actual baseline receipts and both fixed-plan MarketPath cash vectors match exactly"
    },
    {
      "step": 600,
      "product": "MILK",
      "opponent": "arlene",
      "horizon": 601,
      "quantity": 17,
      "candidate_fixed_plan": [
        [
          600,
          9
        ],
        [
          601,
          8
        ]
      ],
      "rival_alignment": "paired",
      "baseline_cash": [
        222,
        222
      ],
      "candidate_cash": [
        240,
        222
      ],
      "own_delta": 18,
      "rival_delta": 0,
      "relative_delta": 18,
      "own_admissions_baseline": 10,
      "own_admissions_candidate": 13,
      "rival_admissions_baseline": 10,
      "rival_admissions_candidate": 10,
      "public_flow_inference": {
        "status": "identified_interval",
        "market_delta_plus_town": 20,
        "known_town_units": 4,
        "own_market_supply_units_range": [
          0,
          17
        ],
        "own_buy_units_range": [
          0,
          0
        ],
        "rival_net_market_flow_range": [
          3,
          20
        ],
        "rival_market_supply_units_range": [
          3,
          20
        ],
        "rival_sale_units_range": [
          3,
          100
        ],
        "floor_nonadmission_possible": true,
        "rival_stock": "unknown",
        "order_alignment": "unknown",
        "gross_buy_sell_ambiguity": false
      },
      "generated_hypothesis_ids": [
        "no_rival_supply",
        "recent_lower",
        "recent_upper",
        "competitive_stock_slot_0",
        "competitive_stock_slot_1"
      ],
      "trace": "baseline-arlene-9600803-seat0.jsonl.gz",
      "trace_sha256": "19116ea19778349c0ba6368877b3bef6959ed30715261b004b27829698070a0d",
      "agreement": "actual baseline receipts and both fixed-plan MarketPath cash vectors match exactly"
    },
    {
      "step": 625,
      "product": "STRAWBERRY",
      "opponent": "apex",
      "horizon": 629,
      "quantity": 24,
      "candidate_fixed_plan": [
        [
          629,
          24
        ]
      ],
      "rival_alignment": "after",
      "baseline_cash": [
        1981,
        171
      ],
      "candidate_cash": [
        2074,
        309
      ],
      "own_delta": 93,
      "rival_delta": 138,
      "relative_delta": -45,
      "own_admissions_baseline": 24,
      "own_admissions_candidate": 24,
      "rival_admissions_baseline": 3,
      "rival_admissions_candidate": 3,
      "public_flow_inference": {
        "status": "identified_interval",
        "market_delta_plus_town": 27,
        "known_town_units": 0,
        "own_market_supply_units_range": [
          24,
          24
        ],
        "own_buy_units_range": [
          0,
          0
        ],
        "rival_net_market_flow_range": [
          3,
          3
        ],
        "rival_market_supply_units_range": [
          3,
          3
        ],
        "rival_sale_units_range": [
          3,
          3
        ],
        "floor_nonadmission_possible": false,
        "rival_stock": "unknown",
        "order_alignment": "unknown",
        "gross_buy_sell_ambiguity": false
      },
      "generated_hypothesis_ids": [
        "no_rival_supply",
        "recent_lower",
        "recent_upper",
        "competitive_stock_slot_0",
        "competitive_stock_slot_1"
      ],
      "trace": "baseline-apex-9600803-seat0.jsonl.gz",
      "trace_sha256": "aad58be37ffdf6691d5ab89b43a1484181f358b2e653fc1a0d8b87c7e0ca1c85",
      "agreement": "actual baseline receipts and both fixed-plan MarketPath cash vectors match exactly"
    }
  ],
  "full_games_run": 0,
  "optimizer_calls": 0,
  "adapter_sha256": "d90b343162b6092101d6200a851ab07128bb8d829ecb5c50bf73dd1d7a556552",
  "frozen_scheduler_sha256": "32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9",
  "mechanics_sha256": "579965e589237d1e5bbcc8b8448188f91b173d4480430d34b3a7f0e07e0c48d3",
  "elapsed_seconds": 0.4075505129949306
}
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
