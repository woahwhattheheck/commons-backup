# Route-aware feed reallocation

This directory contains an optional selected-action transform for TITAN. It
reassigns one otherwise ineffective animal action to `FEED` only when an exact
current-day projection proves a bounded resource exchange and the unchanged own
route schedules the conserved input no later than the deferred animal product.
Unknown market purchases, route-choice boundaries, malformed state, or a weaker
current quote preserve the complete supplied action.

The transform calls no controller and changes no market slot. `candidate.py`
wraps the canonical `TitanAgent` so the existing deadline, recovery, seller,
seed-funding, and one-parent-call behavior remain authoritative. This source is
not enabled by the canonical configuration.

## Use

```python
from feed_reallocation import propose_feed_reallocation
from scheduler import m, parent

out, report = propose_feed_reallocation(
    m,
    observation,
    configuration,
    selected_action,
    route=controller.R[controller.cur],
    route_switch_steps=[row[0] for row in parent.DECISIONS],
)
```

For a complete optional actor in the repository layout:

```python
from candidate import make_agent
actor = make_agent()
action = actor.act(observation, configuration)
```

## Validation scope

The frozen source passed 12 focused contract/integration methods. Source-fixed
paired development and held execution completed 52 official-engine games with
zero policy errors. Twenty reached pairs changed one unit action: own terminal
cash improved by 37–46, rival cash changed by -6 to -2, and margin improved by
41–48. Every outcome verdict was preserved; there is no rating or default-policy
claim. Null cases remained action-identical. The full private evidence package
retains all rows, action digests, traces, source closure, and negative treatments.

The projection is tested on the canonical configuration, including
`farmHandCostMult=1`. It rejects unresolved product purchases and route
checkpoints before end of day. Current quotes and own route order are bounded
selection evidence, not a calibrated forecast of future rival behavior.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
