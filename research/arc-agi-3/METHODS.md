# Methods-ready note — deterministic frontier world model

## Objective

ARC-AGI-3 evaluates agents that must learn unknown interactive environments rather than solve a static grid. A useful baseline therefore needs to do more than random action selection while remaining generic enough not to hard-code public game solutions. This version treats each observation as a state in an online transition graph, exhausts untried legal state/action frontiers deterministically, and uses learned transitions to route back toward reachable unexplored frontiers. Novelty/progress reward is retained as a fallback rather than the primary navigation rule.

## Observation representation

The policy consumes only the public frame contract. If a response contains multiple 2-D frame arrays, the latest array is used. Grids are validated as rectangular, at most 64x64, and restricted to integer colors 0..15. The visual state key is a SHA-256-derived signature of the normalized grid. Available actions are normalized to the currently legal subset of ACTION1..ACTION7; the policy never intentionally emits an unavailable action.

This representation is intentionally lossless at the grid level. No semantic labels such as "player", "door", or "goal" are assumed before interaction evidence exists.

## Transition learning

For each state/action pair the agent records visits, successor states, changed-cell counts, novel successors, and level advances. A transition receives a small penalty when the display is unchanged, positive reward when visible state changes, an additional novelty bonus when a previously unseen state is reached, and a much larger bonus when `levels_completed` increases.

When a state is revisited, any still-untried legal action is selected first. Once a state is locally exhausted, breadth-first search over learned non-self-loop transitions finds the nearest visited state with an untried action and emits the first action on that shortest route. This turns repeated observations into purposeful navigation instead of repeatedly rewarding whatever changes pixels nearby. If no reachable frontier exists, a deterministic upper-confidence score over observed reward is used as fallback. The harness exposes frontier-route counts, learned-edge counts, and self-loop observations for measurement.

## Coordinate action

ACTION6 requires coordinates but the API does not identify active click regions. Candidate coordinates are generated without privileged information: first from the centroid and a bounded sample of cells that changed since the prior frame, then from centers of non-background connected components, then from the grid center and corners. Candidate visits are tracked per state so repeated coordinate exploration walks through distinct salient points before repeating them. Coordinates are always clamped to the official 0..63 range.

## Reset and termination

The organizer specifies that GAME_OVER accepts RESET only. The policy therefore emits RESET immediately for NOT_PLAYED or GAME_OVER states and the official adapter terminates on WIN. Episode-pending state is cleared on reset while accumulated transition evidence is retained, allowing retries to benefit from prior exploration.

## Reproducibility

The core is Python standard library only and deterministic for an identical observation/action sequence. The official adapter is intentionally thin and pinned to the public ARC-AGI-3 Agents interface. Synthetic unit tests cover frame validation, current-action constraints, deterministic exploration order, coordinate selection and bounds, transition reward, level-progress reward, shortest learned routing to an unexplored frontier, self-loop rejection, diagnostics serialization, and repeatability. The frontier implementation is clean-room and copies no third-party solver source.

## Limitations and planned ablations

Frontier coverage is still not the same as task progress. Full-grid hashes cannot yet recognize structurally equivalent states after an object translates, learned edges model only observed one-step outcomes, and the policy does not yet infer persistent object roles or latent mechanism state. The next empirical work should therefore measure: (1) v1 novelty/UCB versus v2 frontier routing on identical public game versions, (2) full-grid identity versus role-free object-centric abstraction, (3) observed one-step graph routing versus learned action-effect planning, and (4) coordinate salience heuristics versus systematic coordinate-region exploration. Any improvement should be accepted only on reproducible public/local ARC runs, not on synthetic fixtures alone.

No leaderboard, milestone placement, submission, or award is claimed in this note.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

