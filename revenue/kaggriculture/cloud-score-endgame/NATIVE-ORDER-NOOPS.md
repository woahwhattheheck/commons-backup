# Native terminal-order no-op compatibility

`terminal_inputs.py::_queue_ok` now matches the pinned engine's order-parser
boundary for inherited market orders. A recognized operation whose quantity
raises `TypeError` or `ValueError` during integer conversion is a native no-op,
not a reason to discard the entire receipt table. Unknown list or mapping
opcodes also remain ignored native slots rather than causing hashability errors.

The original order object and its queue position are preserved. This change does
not normalize, delete, or execute a malformed order. `OverflowError` still
stops before a market call, the existing absolute quantity bound remains, and
non-finite JSON receipt documents remain unavailable. No scenario family,
worker stage, solver, sampler, objective, controller, or selected default is
changed.

## Executed validation

The source repair was executed against the pinned official engine and retained
PORT/LARCH/PRISM/POLY/T15 modules before publication:

- 13 new native-parser methods pass. They execute 294 producer market cells and
  277 independent full-interpreter terminal comparisons.
- The existing 20 terminal-input methods pass unchanged, executing 257 producer
  cells and 59 full-interpreter comparisons.
- Four additive checks against the context-bound score selector pass across 20
  transform calls. Identical retries retain one solve and one draw; changed
  parent metadata or visible cash retires the commitment and preserves the
  complete fallback; incomplete tables draw nothing.
- The unchanged original preflight fails the new coverage before the selector
  can run. The looped failures are retained as control evidence, not counted as
  independent test methods.

The constructed two-scenario witness is identical in both player positions.
The supplied baseline cash pairs are `100397/100398` and `100392/100391`; after
native-compatible preflight, the existing selector's chosen queue yields
`100400/100396` and `100392/100390`. The inherited malformed `BUY_SEED` remains
unchanged in slot 9. This is a conditional compatibility witness, not a reached
full-game win, held validation, leaderboard result, or policy-promotion claim.

The branch composes only the `_queue_ok` hunk onto the newer terminal-input
source, preserving its later explicit rival-HIRE support. That later feature was
not part of the original no-op test snapshot; the changed function is shared by
both paths and the rest of the newer source is retained byte-for-byte by the
patch composition.

## Reproduce

Use an existing offline dependency directory containing `terminal_utility.py`,
`score_endgame.py`, `weighted_selector.py`, `selector.py`, and `solver.py`, plus
the pinned engine and loader. The commands do not download inputs and require a
new output filename.

```sh
python3 -B revenue/kaggriculture/cloud-score-endgame/test_terminal_order_noops.py \
  --loader /existing/peer/evaluate.py \
  --engine-dir /existing/engine \
  --consumers /existing/consumers \
  --core-file /existing/cloud-full-support/full_support.py \
  --report /tmp/native-terminal-noops.json

python3 -B revenue/kaggriculture/cloud-score-endgame/check_noop_current_consumer.py \
  --loader /existing/peer/evaluate.py \
  --engine-dir /existing/engine \
  --consumers /existing/current-consumers \
  --core-file /existing/cloud-full-support/full_support.py \
  --report /tmp/native-terminal-noops-current-selector.json
```

Ordinary discovery without those explicit native dependencies skips these
optional integration suites rather than claiming they ran. The test CLIs write
reports exclusively and will not overwrite a retained result.

## Source identities and scope

The executed repaired snapshot had Git blob
`f4b505efea72c23f146e559c5056fbaa9690d168`; the native test is
`19b4a21127891d692897e18567d7e3de6ef96490`, and the current-selector check is
`d87473deaa9a262ebe41bfdf9ad188614c3655a4`. Publication composes that same
function hunk on the current terminal-input source rather than replacing newer
work.

There are zero new full games, gameplay seeds, engine exports, workflows,
uploads, selected-policy changes, or owner-PC actions in this repair. New files
are Apache-2.0 under the directory's existing attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
