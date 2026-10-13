# T10 land counterfactual callback

`land_counterfactual.py` is a consumer of the existing T10 `labor_capital.project_shift` fork. It compares one explicit, slot-preserving `BUY_LAND` counterfactual with an already-selected incumbent action and returns:

- projected current-shift cash and minimum cash;
- remaining worker-turn capacity and requested productive work;
- actual requested work on the newly unlocked quadrant;
- final productive-state and market-inventory correspondence;
- exact future action divergence;
- optional suppression of the next incumbent `BUY_LAND`, distinguishing **move earlier** from **buy an extra quadrant**.

It does not choose a policy, infer unknown shop or rival behavior, value requested worker turns as successful receipts, or call the live parent a second time. The caller supplies `fork_parent`, which must return an independent continuation snapshot of the already-advanced owner.

## API

```python
candidate = make_land_candidate(selected_action, slot=slot)
report = compare_land_shift(
    labor_capital,
    engine,
    observation,
    parent_after_call,
    selected_action,
    candidate,
    configuration,
    fork_parent=fork_parent,
    suppress_next_land=True,
)
```

The returned report is an input to ECON's prospective payback rule. `land_purchase_successful=False` means the attempted market order did not unlock a quadrant; no land or value is invented.

## Source-bound retained result

Against the exact submitted TITAN checkpoint `7b58fa06…`, retained protocol seed `9922999`:

- moving the incumbent land purchase from step 265 to step 250 produced 156 early-access worker turns and 76 productive requests, but zero requested productive work on the newly unlocked quadrant;
- moving the purchase from 265 to 264 and suppressing the original slot rejoined the incumbent cash, productive state, and market inventory after step 265;
- the complete official-engine both-seat comparison for 250→265 was terminal-neutral (`190319/3550` in both arms), with no new policy claim.

These are one retained episode's conditional mechanics and economic evidence, not a fresh strength panel. Exact trace bytes remain in the separately retained Library packet; this repository delivery publishes the reusable callback, independent unit tests, and compact source/result receipt.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
