# TITAN current consumer

Run `main.py::agent(observation, configuration)`. The archive is standalone Python
with no third-party runtime dependencies. `TITAN-CONFIG.json` fixes the default:
frozen SELL, ALDER seed recovery, JUNIPER fixed-order funding and ECON deadline.
`TitanAgent(Features(...))` exposes deterministic research configurations.

Exactly one production action is selected, then `transform_selected` dispatches
that action. The frozen transform is mechanically extracted from the preserved
frozen scheduler, changing only its signature and removing its parent call.
Its production and SELL valuation remain the basis of the stronger comparison.
Seed proposals follow frozen SELL, as in JUNIPER's shipped seed_main. Funding uses
the resulting actual ordered queue; it does not merge a second stock/cash ledger.
The ordered experiment instead uses its existing current integrated transform,
post-unit projection, committed arrival envelope and bound funding callback once.
Future pending receipts are capacity obligations, not currently saleable stock.

`consumer="parent", seed=false` is intact Arlene; `consumer="frozen", seed=false`
is the frozen SELL control. `terminal_route=true` selects T05's tested terminal
owner over the same parent. `consumer="ordered"` selects the current ordered/cap
experiment. PR9997's exact prior archive remains `integrated-selected-v1.tar.gz`;
the current ordered experiment has changed source and cannot inherit its results.
Adaptive T15, score-endgame and capital search remain owner experiments; they are
not called by this release. Their results guide the default and next integration.

The default choice uses Claude's 384-game comparison: frozen SELL beat PR9997
31–9 development and 13–3 held. JUNIPER's six games preserved ALDER's +240 cash
case, without an additional funding win flip. T05's 64-game composition improved
cash without a WTL change, so remains opt-in. These are component comparisons,
not game results for this new archive or a hosted win.

The main-thread deadline covers lazy parent construction and selected dispatch.
Before production completes, timeout returns legal PASS (visible whole-lot DROP
and liquidation on final step 718). After selection it returns that exact action.
Only the owned deadline exception is consumed; caller timers remain intact.
Cancellation discards possibly partial internal ledgers before the next action.
The cold entrypoint import and fallback overhead are included in external tests.

Build with `python build_integrated.py --release`; verify the exact relocated
archive with `python test_titan_archive.py`. Full-game execution belongs to
Claude/WIDEFIELD after archive-hash readback and disjoint T09 seed assignment.
No Kaggle submission/public notebook write is part of this release.

Licenses: Commons/SELL/Arlene, ALDER/JUNIPER and ECON carry Apache-2.0;
OSPREY terminal composition/routing carry MIT; Claude producer dependencies
retain their supplied MIT/Apache notices. Full texts and original distribution
notice/UPSTREAM files are included, alongside source hashes in SOURCE.json.

## History terminal increment (v2)

`titan-history-v2.tar.gz` adds the shipped CEDAR own-fill bridge, T12 history,
SORREL interval inference, JOINT scenario family, POLY native terminal receipts,
PORT utility, LARCH/ANCHOR selector, PRISM sampler and existing T15/POLY solvers.
`main.py` retains the frozen default. Instantiate
`TitanAgent(Features(**json.load(open('TITAN-HISTORY-CONFIG.json'))))` for the
explicit history experiment; its slot order and quiet operating-stock hypothesis
are declared finite hypotheses, not inferred facts. Supply a separately named
configuration to test other operating-stock hypotheses. The sampling stream is
explicit `random.Random(0)` per actor and used only for a certified plan mixture.

The history path receives the same unit snapshot already computed by SELL.
It records the final returned market queue, then reconciles that record on the
next observed turn. Timeout with a completed snapshot records the actual selected
fallback. Timeout before a snapshot leaves history unknown. Final worker actions,
seed/hire acquisition receipts and non-SELL slot positions are preserved. Changed
queues with BUY_PRODUCT, BUY_ANIMAL or BUY_LAND retain the baseline because this
receipt interface does not expose those per-order acquisition witnesses.

Only a complete joint history family reaches terminal input generation. Only a
complete native receipt table reaches selection. Both run inside the existing
whole-action deadline. No current rival private stock or replay action enters
the runtime. Terminal results are conditional on the explicit finite family.

Five new methods cover six cases including both seats. In the constructed
WHEAT-17 hypothesis case, actual history-backed dispatch changes MILK/WHEAT to
WHEAT/MILK: native final cash 100394/100398 becomes 100397/100396, with one parent
and one unit stage. This is a mechanism result, not a full-game improvement.
The original PR10144 archive `70554dc0…` stays byte-for-byte intact for WIDEFIELD.

## Entrypoint clock increment (v3)

`titan-entry-clock-v3.tar.gz` passes the canonical entrypoint's first-call clock
into the existing `TitanAgent.act` timer. Path resolution, configuration loading
and cold imports now consume that same action budget. If the prelude already
exhausted it, no producer is constructed or called. Fallback elapsed diagnostics
include their final deepcopy; `act_cpu_seconds` separately measures CPU within
TitanAgent.act, while `entrypoint_prelude_seconds` reports the preceding wall time.

Two new boundary tests measure delayed entrypoint preparation and post-timer
fallback copying. This repairs those measured boundaries; it does not diagnose
the independent 70554dc0 step569 RPC timeout. The 10ms reserve remains unchanged.
Request encoding, transport, worker decoding, response encoding/flush and OS
scheduling remain outside this agent timer. Full RPC timing belongs to the
external evaluator; the guard does not guarantee RPC completion within one second.
Claude/WIDEFIELD retain the original failed cell and own its reproduction.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
