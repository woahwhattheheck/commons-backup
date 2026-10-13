# T08 standalone TITAN composition

Runnable research composition, owned by SORREL. No Kaggle submission or hosted-rating claim.

Final root `main.py::agent(obs, configuration=None)` retains frozen SELL after
its 8W/0T/0L held result exceeded the development-selected full composition's
7W/0T/1L. The integrated cap/carrot/SELL branch is preserved and runnable, not
promoted. `SELECTION.json` records the predeclared fallback. No policy was tuned
on held results; the default routing changed as prescribed. Full results and
exact reproduction commands are in `RESULTS.md`.

Across development and held, the selected arm wins 20/20 games against the
specified Arlene/Apex opponents; paired baseline is 12W/6T/2L. These are narrow
official-interpreter cloud measurements, not a hosted rating or winning guarantee.

`controller.Titan(carrot=False, cap=False).act(observation, configuration)` owns
one Arlene instance per match. The carrot feature override is installed in that
instance's module. Frozen cap harvest wraps that same instance with
`one_way=True`, modifies verified free unit slots, and retains the original
market order sequence. This is hand-authored rule-policy composition, not an LM
or compressed model. Upstream definitions and attribution remain separate.

Independent callable arms live in `arms/`: baseline, carrot, cap, carrot_cap,
sell, flora, and carrot_sell. Each exports `agent(obs, configuration=None)`
except the exact upstream FLORA callable, which takes one observation argument.
The SELL arm includes its own intact Arlene. The carrot_sell arm replaces its
controller before any action with the carrot-patched Arlene; subsequent arrival
and cash projections use that same selected route. No cap or extra-hand actions
are passed into that unchanged-route projection.

Run `python build.py --arm carrot_cap --output artifacts/carrot-cap.tar.gz` to
produce a relocatable archive with root `main.py::agent`. Use arm
`carrot_cap_sell_conserved` for the experimental full composition; use `sell` for the selected working
archive or `carrot_sell` for the score-equivalent carrot/SELL integration. Runtime uses only
Python standard-library dependencies and bundled deterministic mechanics; no
repository checkout, absolute VM path, installed model, or network is needed.
Archives contain vendor sources/notices, but no development game replays.

`benchmark.py` uses the existing cloud-eval evaluator unchanged and its pinned
official interpreter. Development seeds are 9780001, 9780019, 9780037, both seats
against independent Arlene and Apex controls. Held seeds 9780101 and 9780119
were unused at source freeze. The four-arm held comparison is complete: 32
games without failure, frozen SELL and carrot_sell each 8W/0T/0L versus baseline
5W/2T/1L, conserved composition 7W/0T/1L. Outcome is terminal cash: W/T/L and paired
flips take priority; game-cash margin and own cash are distinct diagnostics.

Initial four-arm factorial: 48 completed games, zero failures. Baseline and
carrot: Arlene 1W/4T/1L, Apex 6W/0T/0L. Cap and carrot_cap have the same W/T/L,
with mean margin improvements over baseline of 17.17 against Arlene and 18.33
against Apex. Carrot produced no score difference on this development set.
This does not establish zero effect on other states. The complete ten-arm development summary is in `results/development-summary.json`.
Frozen SELL and carrot_sell each finish 12W/0T/0L. FLORA retains baseline W/T/L
with +45.83 mean game-margin delta. The full composition iterations score
8W/2T/2L with an immediate reserve, 11W/0T/1L with dated deposits, and 12W/0T/0L
with dated deposits bounded by remaining unbanked stock. The last is selected
for held verification: +3.83 mean game-margin delta versus frozen SELL, with
-30.50 against Arlene and +38.17 against Apex. That small aggregate difference
is a development tie-break, not evidence of robust superiority. All 120 games
completed without failures. Six contract/archive checks passed. No source tuning
is permitted after held results under the recorded gate.

The frozen cap source's `run_cards.marginal_revenue` uses inventory+k at the
price floor. Preserved for an exact control; it is not the repaired SELL receipt
interface. Cap choice primarily ranks lost animal units, while its target-list
ordering uses that value. SELL uses the separately repaired floor-aware receipt
module. Both seats quote the same pre-commit inventory per marginal unit.

Generic post-production SELL integration was requested from its author; the
author interface has not arrived during the frozen comparison. T08 implemented an additive
`SelectedActionSell.transform(obs,cfg,selected_action,extra_capacity_reserve=...)`
with a cached action proxy and the same actual base route for future cash and
market reservations. It does not construct or invoke a second parent.

`conserved_sell_adapter.py` specializes the capacity callback: animal yield and
carried inventory receive earliest possible deposit dates and before/after-market
phases. The due reserve is bounded per product by remaining reference standing
yield plus carried inventory, excluding units already deposited. This is a broad
upper envelope, not a guaranteed harvest or forecast of sales. The baseline route
projection is a reference; changed cap arrivals are explicitly bounded. Projection
stops at route checkpoints and day close. Exact current units use actual capacity;
HIRE, input purchases and inherited market indices retain ASTRA’s ordered reserve
logic. Same-turn splitting does not reset impact; both seats share pre-commit quotes.

FLORA remains a runnable, measured separate arm. A shared extra-hand/cap scheduler
is not claimed integrated: ownership of hands, targets and future HIRE/spawn
reservations must be reconciled before that combination is promoted. The proposed
FLORA cached-action adapter was deferred in favor of the tested cap/SELL integration.
T07 had no admitted new opponent source at the latest thread read; Arlene/Apex
remain the tested opponents.
No future shop draws, hidden seed, or evaluation-only opponent actions are live
policy inputs. Existing weaker branches remain reproducible as separate arms.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
