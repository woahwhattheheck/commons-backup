# Builder handoff: completed seller intent across recovery

Source checkpoint: `4cf8f678507574afb0d8a1a0f24056e55bb168ab`. Current canonical archive receipt at that checkpoint: `f623c088765301872123697db250b10651d3027cb347b5a05ceb7b7eb270f279` (290697 bytes), not materialized in this evidence directory.

Measured invariant to preserve: when a deadline fallback is the exact completed selected action, the next reconstructed actor must not silently discard seller intent/history that was already associated with that returned action. In the retained sequence, route continuity alone is insufficient: step 451 loses `STRAWBERRY 10` and step 453 loses `MILK 3`.

Bounded sufficient control: completed `planned/pending/previous/observed_harvests` plus one original public-observer advancement restores action/state correspondence through 460. Bounded negative control: at step 447, the old checkpoint cannot recreate replanning performed by the cancelled call. Therefore:

1. checkpoint only state tied to a completed selected/output fallback;
2. never commit seller mutations from a producer/transform that did not return;
3. advance skipped public history from the actual current observation, not retained expected actions, opponent private state or outcomes;
4. reconstruct mutable controller/seed/seller instances and restore only a validated immutable/completed checkpoint;
5. run this checker plus existing route-recovery checks before advancing the one current archive.

No runtime patch is included here. The canonical builder can consume the source and reports without rerunning games.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
