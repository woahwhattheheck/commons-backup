# TERMINUS — cash-backed terminal labor surge

One additive source component for the existing `main:candidates/v4` tree. It is **not** a new controller, scheduler family, V4 root, production default, archive, or Kaggle submission.

## Why this lane exists

A live swarm idea proposed blind final-day mass hiring because Kaggriculture's daily Fibonacci wage counter resets and hands disappear at end of day. The current V4 engine blob proves the underlying reset, but also proves four constraints that change the theorem:

1. HIRE cost is `fib(hires_today)`: 16 **total** hires cost `1+1+2+...+987 = 2583`. If one final-day hire already executed, 15 additional hires reach 16 total and cost the remaining 2582.
2. Unit actions execute **before** market HIREs, so a newly spawned hand cannot work until the next callback.
3. Only the raw `market[:maxMarketOrdersPerTurn]` prefix executes (default 10), so a 16-hire vector cannot execute in one default callback.
4. Terminal reward is `farm.money` only. Worker count, stripped tiles, and unsold carried units have no direct terminal score. A marginal hand must create terminal cash that pays for its exact wage.

Exact current V4 official-engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

## Composition seam

This component contains two mutually exclusive, default-OFF experiments behind the already-landed T05 terminal ownership seam. The first consumes the clean pre-terminal step-697 seam recovered from superseded PR #12762; the second is a selected-action + committed-route transform inside T05 from step 698 onward. It consumes the same forward route and before-market shed snapshots exported by `reference/titan-current/terminal_composition.py` (`3c0bb0fe4dfe02f3ec9690b4f5d100fb8bd28f99`). It does not call a parent policy, forecast an opponent, or run another SELL policy.

`propose_preterminal_hire_frontier(...)` acts only at final-day hour 1 (default step 697), one callback before T05 starts. It simulates current own unit rows with the engine atomic seed-demand rule, accepts only an all-HIRE incumbent market prefix, replays exact existing HIREs, then calls the existing `terminal.assign_routes` for the baseline and each additional funded hand. It chooses only the count with the best qualified net current-quote gain after cumulative exact wages. This seam was donated by superseded PR #12762 after its owner yielded to the earlier TERMINUS claim.

`propose_terminal_labor_surge(...)` is the complementary in-owner experiment and only acts inside the existing terminal-owner window. For each possible extra current-callback HIRE, in exact marginal Fibonacci order, it:

- preserves every producer-authored market order and only **appends** into genuinely free raw-prefix capacity;
- rejects current BUY/unknown prefixes rather than assuming funding survives earlier market orders;
- simulates current unit actions and already-authored current HIREs before assigning new worker indices;
- rejects any future executable HIRE because future worker re-indexing is outside this transform's ownership;
- reserves every parent-route HARVEST target and every already-selected new target;
- uses the engine's exact spawned hand position;
- requires an observed mature/yielding target reachable as `spawn -> target -> HARVEST -> shed -> DROP` by terminal step 718;
- requires the producer row at the DROP step to be SELL-only and have a free raw market slot;
- checks the baseline before-market shed snapshot plus simultaneous added deposits against shed capacity;
- appends a same-turn `SELL item quantity` after the DROP, exploiting the verified engine ordering that unit actions precede market processing;
- values the sale at the current quote after charging **all parent terminal SELL volume for that item plus this proposal's own already-planned volume**;
- admits the hand only when that screened value clears its exact wage by `min_quote_surplus`.

The transform stops immediately when the next marginal hand has no profitable executable job. It therefore cannot implement the original blind-16 proposal.

## Relationship to existing V4 work

This reuses rather than replaces:

- T05 terminal routing / terminal composition for committed final-day movement and deposit timing;
- `spatial-hire-prefix` for the raw-prefix interpretation of executable HIREs;
- current `redundant_hire.py` for the general same-day redundancy theorem.

Superseded PR #12762 is explicitly donor-only and must stay closed; its useful step-697 seam is consumed here so a second terminal-labor authority is not created.

The current redundant-hire code can protect at most one productive detour from a trailing redundant set. TERMINUS instead creates only already-job-backed extra terminal hands, with explicit worker actions and same-turn sales, so downstream redundancy logic sees real work rather than an idle mass-hire vector.

## Validation performed

Executed locally on the exact source bytes in this directory:

```text
python test_terminal_labor_surge.py     -> 18/18 PASS
python -O test_terminal_labor_surge.py  -> 18/18 PASS
python -m py_compile ...                -> PASS
```

The tests cover the recovered step-697 frontier (including first-ten cost = 143, non-HIRE refusal, disabled identity and best-cardinality selection) plus profitable multi-hand in-owner admission, exact marginal Fibonacci sequencing after an existing hire, raw cap preservation, zero free slots, outside-window identity, useless final-callback identity, full-shed rejection, parent HARVEST reservation, future-HIRE fail-close, existing-current-HIRE worker indexing, incomplete snapshot fail-close, unprofitable high-wage tail rejection, current BUY-prefix fail-close, and conservative parent terminal sale-volume pricing.

The official engine contract itself was independently read back from exact blob `3c202c7...`: HIRE cost/spawn, daily hand/reset behavior, unit-before-market ordering, and terminal cash-only reward all match the assumptions above.

## Status / non-claim

**Source-ready, default OFF, not runtime promoted.** Current-quote surplus is a conservative own-route screening signal, not a proof against rival future sales or a field-EV claim. The next promotion gate is paired official-engine execution on both seats against the current native entrypoint, comparing terminal reward delta and verifying every added HIRE, HARVEST, DROP, and SELL actually executes. Until that evidence is positive, do not enable this mechanism in production, change defaults, rebuild the archive, or submit it to Kaggle.
