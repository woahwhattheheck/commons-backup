# Native no-op × explicit rival-HIRE × current score consumer

This is a source-specific compatibility follow-through for three already-landed
TITAN components. It adds no runtime behavior. The executed source combination is:

- terminal-input producer blob `e0e3b52dddcef31f4d07c77daf3cdf0f5921a8b5`,
  which combines explicit rival `HIRE` hypotheses with native no-op order parsing;
- current score consumer blob `859907e9ad13fe5b831a5d52e39926b612750fbd`,
  including cash-Pareto opt-in selection, economic-context binding, and complete
  parent-action retirement;
- unchanged PORT, POLY, PRISM, T15, loader, and pinned native-engine dependencies
  named in the adjacent result file.

## Result

All **64 distinct methods** pass with zero failures, errors, or skips. The source-
bound executions comprise:

| Slice | Methods | Producer cells | Full native terminal comparisons | Selector transforms |
| --- | ---: | ---: | ---: | ---: |
| Existing terminal-input suite | 20 | 257 | 59 | — |
| Explicit rival-HIRE suite | 18 | 63 | 32 | included in suite |
| Native no-op suite | 13 | 294 | 277 | 3 direct consumer calls |
| Current context/parent consumer | 4 | 74 | 8 | 20 |
| New joined no-op + HIRE cases | 9 | 90 | 64 | 20 |

Totals are **778 producer market cells**, **14 original-producer comparison cells**,
**440 independent full-interpreter terminal comparisons**, and **40 transforms**
in the two dedicated current-selector checks. These counts overlap constructed
fixtures and are not independent game samples.

The joined discriminator keeps an inherited malformed `BUY_SEED` unchanged in
slot 9 while evaluating complete rival `SELL` and `SELL → HIRE` hypotheses. In
both player positions, native cash remains:

| Own plan | Rival sells only | Rival sells then attempts HIRE |
| --- | ---: | ---: |
| Original delayed MILK sale | 156 / 377 | 156 / 0 |
| Early MILK sale | 160 / 375 | 160 / 375 |

The sale-only table selects the early sale with one solve and one draw. Keeping
both explicit hypotheses retains the original action with no draw because the
blocked costly hire reverses the terminal result. The malformed own order remains
a native no-op in every plan and slot; it neither disappears nor becomes a sale.

This is a constructed conditional mechanism, not a reached full-game result,
hidden-opponent observation, calibrated scenario model, held validation, or
leaderboard claim. The default terminal-history feature remains unchanged.

## Current-contract correction

The first rerun found one stale expectation in
`check_noop_current_consumer.py`: after the later parent-retirement repair, changed
complete parent metadata is deliberately retired as `terminal_parent_changed`
before evidence-context parsing. The older optional check expected
`terminal_context_changed`. Runtime output, fallback, solve count, draw count, and
native cash were already correct. This follow-through updates only that test
expectation and adds the joined check; it does not change production source.

The new check separately verifies:

- identical same-context retry keeps one solve, one draw, parent binding, and the
  exact chosen queue;
- changed parent metadata retires the active decision before reuse;
- changed visible cash with an unchanged parent retires the evidence context;
- missing cells or an expired deadline preserve the complete fallback and invoke
  no provider/draw;
- `TypeError`/`ValueError` quantities and unhashable unknown opcodes remain native
  no-ops even with explicit HIRE columns;
- numeric overflow still stops before native market execution; and
- one supplied post-unit snapshot is consumed without a second unit stage.

## Reproduce

Use the explicit dependency paths; the checks do not download or mutate inputs.
Each report path must be new.

```sh
python3 -B revenue/kaggriculture/cloud-score-endgame/test_terminal_inputs.py \
  --loader /existing/evaluate.py \
  --engine-dir /existing/engine \
  --consumers /existing/consumers \
  --core-file /existing/cloud-full-support/full_support.py \
  --output /tmp/terminal-input-current.json

python3 -B revenue/kaggriculture/cloud-score-endgame/test_rival_hire.py \
  --context /existing/rival-hire-context \
  --runtime-file revenue/kaggriculture/cloud-score-endgame/terminal_inputs.py \
  --score-file revenue/kaggriculture/cloud-score-endgame/score_endgame.py \
  --original-file /existing/original-terminal-inputs.py \
  --output /tmp/rival-hire-current.json

python3 -B revenue/kaggriculture/cloud-score-endgame/test_terminal_order_noops.py \
  --producer-file revenue/kaggriculture/cloud-score-endgame/terminal_inputs.py \
  --loader /existing/evaluate.py \
  --engine-dir /existing/engine \
  --consumers /existing/consumers \
  --core-file /existing/cloud-full-support/full_support.py \
  --report /tmp/noop-current.json

python3 -B revenue/kaggriculture/cloud-score-endgame/check_noop_current_consumer.py \
  --producer-file revenue/kaggriculture/cloud-score-endgame/terminal_inputs.py \
  --loader /existing/evaluate.py \
  --engine-dir /existing/engine \
  --consumers /existing/consumers \
  --core-file /existing/cloud-full-support/full_support.py \
  --report /tmp/noop-current-consumer.json

python3 -B revenue/kaggriculture/cloud-score-endgame/check_native_noop_rival_hire_join.py \
  --producer-file revenue/kaggriculture/cloud-score-endgame/terminal_inputs.py \
  --score-file revenue/kaggriculture/cloud-score-endgame/score_endgame.py \
  --rival-test-file revenue/kaggriculture/cloud-score-endgame/test_rival_hire.py \
  --cases-file revenue/kaggriculture/cloud-score-endgame/terminal_input_cases.py \
  --loader /existing/evaluate.py \
  --engine-dir /existing/engine \
  --dependencies /existing/consumers \
  --core-file /existing/cloud-full-support/full_support.py \
  --report /tmp/noop-hire-current-join.json
```

Generic discovery without the explicit native dependency setup skips the optional
checks rather than claiming native coverage. No full game, gameplay seed, export,
workflow, current release, upload, spending action, or owner-PC execution occurred.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
