# Empty-lot selected-action fallback

`test_empty_lot.py` covers the selected-action path with no available non-operating product lot. It is additive to `check_market_contracts.py`; the existing market-contract source and validation record are unchanged.

## Behavior

The optimizer previously performed no feasibility evaluation in this case, allowing an inherited HIRE, seed purchase, operating-stock sale, or future commitment to bypass the ledger and ignore a supplied fallback. For example, HIRE with cash 100 and an after-market minimum of 100 leaves 99 in the pinned official market. The corrected wrapper checks the literal unchanged queue when no optimizable lot exists and returns the caller's fallback when that queue fails. Valid queues retain their original positions. It does not invoke a dummy optimization or construct a controller.

The literal queue is evaluated by `ProjectionLedger.feasible(None, ())`. Normal product-plan evaluation is unchanged. ATLAS's ordered transfer checks and the terminal stock-reservation fix remain intact, including two new combined-path discriminators. A fallback remains caller-owned; returning it is not a claim that unavailable resources were created. When omitted, the original action is still returned with fallback diagnostics.

## Run

Use the existing engine artifact 10005621438 and source/loader artifact 10030763484, or equivalent exact pinned files. No new export workflow or game panel is needed. Extract the engine ZIP; extract `titan-reusable-sources.tar` from the source ZIP. From a Commons checkout containing this change:

```sh
export TITAN_SELL_FILE="$PWD/revenue/kaggriculture/cloud-execution-lab/selected_action_sell.py"
export TITAN_SELL_SUPPORT_DIR="$(dirname "$TITAN_SELL_FILE")"
export TITAN_ENGINE_FILE="/path/to/engine-extract/engine/kaggriculture.py"
export TITAN_UPSTREAM_DIR="/path/to/source-extract/revenue/kaggriculture/cloud-pack/upstream"
python revenue/kaggriculture/cloud-selected-market-checks/test_empty_lot.py
```

The suite uses only the standard library. Its isolated loader executes the unchanged pinned market module and compiles the unchanged `resolve_episode_seed` definition from the upstream utility source; it does not substitute a seed helper, initialize an episode, or import unused framework schema/network machinery. Seed selection is never called. Native `_process_market` executes the synthetic purchases, sales and hires. Future event tests exercise the caller's conditional ledger, not a new game trace.

## Validation

Fifteen methods pass on the candidate. The exact pre-change current-main seller fails eleven assertions/subtests across ten methods, with no execution errors. This baseline already includes the preceding ordered-transfer and terminal-stock fixes. Positive controls cover exact cash thresholds, distinct phase minima, seed storage outside shed capacity, fully reserved product normalization, non-SELL positions, and input immutability.

`EMPTY-LOT-VALIDATION.json` records exact source hashes, artifact reuse, baseline and candidate counts, and validation limits. These are focused contract tests, not whole-repository CI, scored games, held panels, or a policy promotion. Frozen optimizer and standalone source bytes remain unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
