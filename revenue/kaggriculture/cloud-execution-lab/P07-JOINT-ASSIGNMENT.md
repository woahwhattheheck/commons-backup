# P07 joint actor assignment witness

Operation: `op:titan-v25-orders-20260909-P07`

This additive module is a conservative refinement seam for the incumbent spatial-tempo producer. It certifies one pairwise exchange of *complete* pickup → service → delivery bundles and returns a single plan that owns both actor continuations atomically.

## Acceptance boundary

A swap is accepted only when all of the following hold:

- the segment stays within one day, does not include EOD, a configured checkpoint, or any market mutation;
- both actors start with empty carried inventory, so no pre-existing cargo is silently reassigned;
- each inherited stream contains exactly one initial `PICKUP`, one final `DROP`, and at least one supported service in between;
- inherited task events remain on their original global steps; only actor identity and just-in-time movement are changed;
- every inherited event deadline and each actor's original end/rejoin position remain reachable;
- the candidate uses fewer joint movement actions than baseline;
- baseline and candidate full pickup quantities are satisfied and every bundle event has a real state effect (no silent no-op acceptance);
- exact sequential unit-order simulation produces identical final farm and private state, including worker positions/inventories and shared shed stock.

## Ownership and collision trace

`JointSwapPlan` has one `owner_key` for both workers. `patches()` always returns both actor actions together at every step; there is no one-sided plan API. Each accepted swap also carries a compact event trace containing step, worker, action and shed-before/after rows so same-step shared-stock ordering is auditable.

## Deliberate non-claims

The module is not default-activated and does not claim a playing-strength improvement. It establishes a fail-closed exact-equivalence primitive for a later canonical spatial-tempo writer to compose with P08 resource reserves, P10/P13 service deadlines and P21 terminal delivery constraints before matched official full-game evaluation.

Focused verification: 17/17 named regressions pass, plus a deterministic 882-case matrix (441 exact-stock accepted swaps and 441 one-unit-short shared-stock rejections).

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
