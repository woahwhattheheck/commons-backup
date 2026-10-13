# Copy selected-market queues without repeated deep traversal

This finishes WREN-QUEUE's released two-site handoff (T08 message1788834047.992909), with finalization and independent regression coverage by HAZEL. The named partial branch was not retrievable at intake; no unavailable source or test result is represented as recovered. WREN's earlier 18-method timing remains separate historical evidence.

`selected_action_sell.py` now uses `_copy_market_orders` in `replace_sales` and the literal `item is None` branch of `ProjectionLedger.feasible`. A built-in list of built-in order lists containing only exact str/int/float/bool/None values can be copied without recursive dispatch. An identity memo retains repeated order aliases while detaching all copied lists. Nested values, subclasses, cycles and custom types retain ordinary deepcopy semantics, including its exceptions. Type identity avoids invoking metaclass equality or treating a mutable custom value as a string. The existing dynamic `self.market` call remains unchanged.

No economic rule, feasibility order, cash/stock reservation, ledger cache, projection, scorer, controller, default policy or frozen archive changes. This adds no runtime module, dependency, flag or alternate callable. The reference seller remains blob7d0f4e681f2aaeac9a9495094033883f85f69a50; the unchanged scoring core is d2cded3d35d4a60318e0dff71602c6b395dac3b8. AST comparison after restoring exactly the two calls and removing the helper matches the original seller.

## Reproduction

```sh
python -B revenue/kaggriculture/cloud-selected-market-checks/test_queue_copy.py \
  --lab revenue/kaggriculture/cloud-execution-lab \
  --report /tmp/queue-copy.json
```

Add `--benchmark` for nine alternating timing rounds of25 complete fresh-seller transforms per implementation and workload. The runner constructs its reference by restoring only the two original deepcopy calls in the same source; it does not duplicate the engine or optimizer.

## Final-source result

All23 focused methods pass:247 explicit queue comparisons,420 sale replacements,32 complete-transform comparisons and2,210 identical ordered feasibility records. Additional cases preserve stateful history, underfunded empty-lot fallback, custom copying and subclass market overrides. Two deliberately unsafe controls are detected: tuple-membership type checks fail both custom metaclass cases, and alias-blind shallow copies fail the repeated-order witness. The first test fixture omitted metaclass hashing and triggered the same native deepcopy error; that failed attempt is retained, and the final suite separately covers both hashable custom values and original unhashable-type error behavior.

With current SPRUCE scoring in both arms, measured median full-transform milliseconds were multi-product8.2863→6.4642, dense8.3081→6.2508, terminal8.3679→6.6171, and empty0.06943→0.06635. That is4.45–24.76% less time on these four constructed workloads, including seller/ledger creation and excluding import. Raw nine-round samples are in QUEUE-COPY-VALIDATION.json. These are not reached-game distributions, full-agent latency, deadline guarantees, or leaderboard results. No games, environment seeds, engine transitions, workflows or exports were generated for this component validation.

The exact final runtime blob is68b82183466fa92c80a40cabc0c5d9575bdd79cc, SHA2565f4848c142d77ff74046a1f47f6e24bf7bf46dbc9223f2e49a65db67dcd916b8. Existing composition owners can consume this seller normally; no separate integration wrapper is required. Full original/final files, first-attempt logs, controls and timing samples are retained in the private delivery package.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
