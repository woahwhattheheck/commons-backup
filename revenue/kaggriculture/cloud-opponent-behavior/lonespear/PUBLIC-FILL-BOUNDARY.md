# Preserve public-fill input boundaries

This is a narrow repair to the existing lonespear public-behavior component,
not a new opponent, agent, policy selector, or release. It is prepared locally
and has **not been published or merged**.

## Behavior change

`observed_fill` returns its existing `status="unknown", fills=None` result when
an observation is not a mapping, the public farm list is not a two-player list
or tuple, or the selected actor's farm is not a mapping. The current peer's
clock/configuration normalization and ordinary exception handler are preserved.
Cancellation derived from BaseException still propagates.

Valid outputs retain the exact existing schema. Input state is never mutated.
The other player's farm fields, private inventories, actions and outcome labels
are not inspected. Prediction, source identity, request counts, timing rules,
feed intervals, sale proposals and the whole-queue comparator are unchanged.

This base already includes the clock/configuration repair claimed in Slack at
`1788842666.523579` / checkpoint `1788842887.292029`, read from main as Git blob
`08cce4e9e340da8d0f16541e0cc63ff219d8f550`. Its explicit/public clock handling,
optional configuration, and zero-cost hire support stay intact. This patch
adds **no separate clock normalization**. Preserve any still-later owner changes
rather than replacing a newer complete behavior.py file.

## Reproduction

From this directory:

```sh
python test_public_fill_boundary.py
python test_public_fill_boundary.py --source /path/to/original/behavior.py
python verify_fill_continuity.py \
  --before /path/to/original/behavior.py --after behavior.py \
  --development-dir /path/to/original/development
```

The second command is an intentional negative control and exits nonzero on the
current peer source. Its 14 test methods produce two failing subcases and eight
error subcases on current peer Git blob `08cce4e9e340da8d0f16541e0cc63ff219d8f550`.
These are multiple malformed-input cases, **not ten independent defects**.
All 14 methods pass on the composed repair, including 16 explicit/mixed/sparse/
null clock combinations across both actor positions and two day lengths.

The six retained development traces have 4,314 observations and 4,308 adjacent
frame pairs. The repaired function returns exactly the prior output on every
pair: 4,134 known within-day results and 174 unknown day-boundary results,
zero output differences and zero input mutations. The AST comparison preserves
all seven other function bodies. No game, policy or market engine is run by this
regression or continuity check.

`PUBLIC-FILL-BOUNDARY.json` records exact source hashes and actual results.
The private delivery archive carries the original six development traces and
full test logs; they are not added to the repository patch. These are repeated
observations from the original development dataset, not independent performance
samples, fresh held evaluation, a new rating, or evidence of a stronger policy.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
