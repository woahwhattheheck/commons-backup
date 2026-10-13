# Focused actual-state results

16 focused tests pass: 12 contract cases plus 4 direct comparisons with pinned engine
pricing, town consumption, no-future-work crop transitions and floor-aware joint sales. Zero full games and
zero replay transition reruns. FLORA owns integration and simulation ablation.

| Current observation | Current tomato / strawberry | Quote horizon | Tomato scenario range | Strawberry scenario range |
|---|---|---:|---|---|
| leader-day9 / step224 | 68 / 166 | 224 | 68–68 | 166–166 |
| leader-day9 / step224 | 68 / 166 | 409 | 88–88 | 139–197 |
| leader-day9 / step224 | 68 / 166 | 457 | 106–106 | 11–204 |
| leader-day17 / step430 | 94 / 176 | 430 | 94–94 | 176–176 |
| leader-day17 / step430 | 94 / 176 | 601 | 179–245 | 34–233 |
| leader-day17 / step430 | 94 / 176 | 649 | 188–319 | 47–244 |

Only the current-observation column is an observed historical price. All later
columns are counterfactual scenarios under current shop copies and existing crops.
They are not the actual later replay prices and are not target labels used as input.
The two future horizons per case assume planting today, first tomato/strawberry
availability after 8/10 days, then a one-action DROP/SELL delay at an available depot.
No new crop is inserted into predicted supply: FLORA must add its proposed planting
cohort explicitly if comparing investments.

At step224 no already-visible tomato cohort contributes projected tomato sales at
the selected horizons; this does not license reading later tomato planting actions.
Duplicate current pizza shops and the farmers market contribute tomato demand.
Strawberry ranges widen when uncertain care/harvest permits large existing cohorts
to enter the market. Animal output, private stocks, future purchases, future planting
and future shop draws remain omitted rather than misrepresented as known.

Per-case measured cloud Python 3.12 wall time: leader-day9 0.031897s, leader-day17 0.042915s.
These are single measured calls, not a runtime percentile or hosted-runtime guarantee.
Full per-tile contributions/contracts are in results/actual-state-cases.json.gz;
results/summary.json keeps the complete aggregate scenarios and assumptions.

Behavior checks cover copy counts/configured intervals, exact market phase boundaries,
fertilizer coverage on the preceding care day, capacity clipping, delayed harvest
versus prompt harvest, both farms, one-time WATER growth, last-action unreachable
maintenance, last actionable sale, hidden-input invariance and nonmutation.
The four engine comparisons use its exact loaded primitives, not a second game
simulator or a regeneration of accepted herd/plan studies.

Price-floor repair recomputed only these existing current-state forecast calls, not games or replay transitions. Schema-1 strawberry ranges 3–204 at step457, 1–233 at601 and 1–244 at649 are superseded: discarded floor-sale units no longer depress later inventory-derived prices. Current quotes remain unchanged. The new engine comparison invokes the official `_process_market` for two dated batches, with intervening consumption, checking actual cash, stock removal and inventory for one and two active seats. Both seats receive the same pre-commit per-unit quote.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
