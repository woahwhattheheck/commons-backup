# TITAN V3 — market-prefix rescue candidate

Operation: `op:titan-v3-market-prefix-rescue-20260909-01`

## Confirmed mechanism

The canonical feed- and fertilizer-stock guards can fully withhold a selected sale by replacing its market row with the exact placeholder `[]`. The official Kaggriculture engine first truncates the raw market list to `maxMarketOrdersPerTurn`, then parses each retained row. Therefore an empty row inside the live prefix consumes one issued position while a later valid order outside the prefix is silently excluded.

This candidate repairs only that transport interaction under a suffix-only constraint. It stable-packs exact `[]` placeholders that form a contiguous suffix of the live prefix behind all non-empty rows **only when** an engine-executable row whose original index was beyond the cap crosses into the prefix. Every non-empty row keeps the same value and relative order; already-live non-empty rows keep their absolute market indices so they are not retimed against the opponent. Interior blanks are refused. No purchase, sale, quantity, route, asset, or timing decision for already-live rows is invented.

## Scope and safety

- Default-off candidate only; canonical `main.py`, runtime, config, archive, and release pointers are untouched.
- `candidate.py::agent` is submission-compatible and emits no diagnostic fields.
- `candidate.py::instrumented_agent` is evidence-only. The paired runner strips its marker before the official interpreter sees the action.
- Source contract is pinned to fresh main `853c2e3ea5195dbc957f479b87b2f240fa003a2c`, including the exact canonical agent, runtime, stock guard, evaluator, and engine blobs.
- The panel uses the pinned official interpreter, fresh persistent agent processes per game, the same public Arlene opponent, the same seeds, and both seats for baseline and candidate.
- Zero activation must be byte-behavior equivalent: any zero-event trace or score divergence fails the run.
- A positive development result is not sufficient for promotion. It still needs broader opponents and disjoint held seeds through the native paired-game gate.

## Commands

```bash
python -m unittest -v test_market_prefix_rescue.py
python -m unittest -v test_official_engine_contract.py  # needs kaggle-environments==1.32.7
python run_panel.py \
  --seeds 2609099601,2609099602,2609099603,2609099604 \
  --output RESULTS.json --markdown RESULTS.md
```

## Decision use

- `activation_cells == 0`: retire this candidate; the confirmed bug surface is not reached by this control/opponent panel.
- Any failed or incomplete cell: invalid evidence; do not compare scores.
- Negative activated strata: reject or narrow the trigger.
- Positive activated development strata: expand to the current opponent matrix, then freeze selection before any held-seed evaluation.

No Kaggle submission, hosted-score claim, leaderboard claim, spend, or canonical promotion is made here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
