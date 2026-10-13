# Integrated selected-action candidate

`integrated_main.py` is a complete callable with one intact Arlene owned by the
pinned route-aware, one-way `PlanOverlay`. It joins the selected worker action,
ALDER's seed budget, T08's committed-arrival contract and the generic ordered SELL
scheduler. `integrated_parent.py` uses the same producer and seed stage with the
SELL transform disabled. These are new research arms; frozen standalone SELL and
all earlier packages remain unchanged.

## Use

```python
from integrated_selected import make_agent
policy = make_agent()  # one instance per actor/match
out = policy.act(observation, configuration)

# Claude's existing producer can be injected; no new parent is constructed.
policy = make_agent(production=existing_plan_overlay,
                    seed=True, committed=True, sell=True)
# If production already selected the current action, do not call act again:
out = policy.transform(obs, cfg, selected_action,
                       reservations=caller_reservations,
                       fallback_action=valid_fallback)
```

The injected producer is the pinned one-way cap `PlanOverlay`, with its intact
`agent.R`, `agent.cur`, `plans`, `producer_snapshot` and `_next_op` interfaces.
Arbitrary route-rewriting producers need their own explicit continuation adapter.
The wrapper never asks the producer or parent for speculative future decisions.

`seed=False` disables ALDER augmentation. `committed=False` omits only contingent
capacity reservations while retaining the same actual worker continuation and
observed cargo. `sell=False` returns the producer-plus-seed parent control. The
committed switch here is a new ordered-seller ablation; it does not replace
Claude's existing conserved-seller 2×2.

## Execution order

1. Select production once. The complete `act` calls the injected producer once;
   the producer calls its sole Arlene. `transform` calls neither.
2. Apply selected units in official order to copied state using the already
   vendored ATLAS unit primitive. Current PLANT admission and PICKUP/DROP/PLACE
   effects are resolved at actual capacity.
3. Feed those post-unit seeds to unchanged ALDER `SeedBudget.apply`. Its bound
   counts all remaining planting requests across prefix-compatible intact routes.
   Additional current PLANT requests disable trimming. A reduced purchase before
   a later HIRE, land, animal or product acquisition keeps the original queue:
   freeing cash can change that later order's execution. The budget's `events`
   records proposals; `last_seeded` and `seed_reason` identify emitted decisions.
4. Build T08's contract from the producer snapshot of the exact post-unit state.
   Whole pending lots reserve capacity at their actual phase. Existing cargo is
   deposited once; speculative harvested cargo never becomes sale stock.
5. Continue the selected tape and already-committed errands for at most eight
   decisions, stopping at day close, final action, route-choice boundary,
   stock-dependent PICKUP, end of the explicit committed continuation, or any future BUY_PRODUCT. This is a conditional current-route
   continuation, not a forecast of later Arlene repairs, future shops or RNG.
6. Pass the actual reduced market queue, current shed, ordered signed stock
   events and contract into the unchanged generic seller. It preserves economic
   prefixes, stock/cash minima and non-SELL slots. Missing BUY_PRODUCT cash bounds
   or infeasible continuation preserve the supplied fallback (default: the
   producer-plus-accepted-seed action).

The new continuation loop reuses ATLAS `_units`, `_full_market`, `_market` and
`_record`. It starts after current units because ALDER changes the intervening
market queue: future PLANT projection consumes the reduced seed purchases. The accepted OrderedSelectedSell and underlying seller
files are unchanged. No short-horizon salvage or forced unwind is introduced.

## Source and evidence

`runtime/integrated-selected/SOURCE.json` pins all 26 runtime files. Upstream
revisions are ALDER #9936 / d87f5e6e, Claude #9963 / 0a9fbdfb, T08 #9918 /
021c0e60 and the exact ordered-seller dependency set accepted by FINCH #9991.
Apache-2.0 and MIT notices are retained with their source.

Seven new integration methods passed in 0.212 seconds: one actual parent call in
either seat with omitted step; post-PLANT seed reduction; seed/HIRE dependency;
whole pending4 versus carried2; retained midgame667 post-unit/contract parity;
purchase-bound fallback at a route boundary; and the same-producer parent control.
Only two small new market transitions were executed. No previous suite or game
panel was repeated. Reproduction: `python3 -B test_integrated_selected.py`.

The new archive was extracted into a separate cloud directory and every runtime
hash checked. Fresh subprocesses compiled each entrypoint into a namespace without
`__file__`, then called it once: candidate import+construction+first call 0.079928s;
parent 0.054007s. Candidate's initial purchase-bound fallback was retained. These
are two entrypoint cases, not episode maxima or a hosted-runner timing result.
See `ENTRYPOINT-RESULTS.json`; FINCH owns the broader runtime-budget slice.

`build_integrated.py` builds only `exports/integrated-selected-v1.tar.gz` (103527
bytes), containing both entrypoints and their complete runtime closure. Extract
it and give Claude's existing `execute_arm.py` the extracted candidate/control
paths and root as `--sys-path`. No environment package installation is required.

Development proposal is 9902001/9902019, both seats against the four existing
public opponents. Exact Slack searches are clear; GitHub code searches returned
zero with incomplete-results flags. Claude has been asked to check his existing
whole-repository seed census and accept the shard in T08 before games. No seed
has been spent by this VM and no held bank has been designated. Game results and
W/T/L remain unmeasured for this new candidate. No hosted default or upload change.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
