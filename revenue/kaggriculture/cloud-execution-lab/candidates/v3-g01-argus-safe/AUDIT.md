# G01 semantic audit

Audit operation: `titan-v3-g01-semantic-safety-20260909-sol-argus-01`

The audit compares PR #11371's candidate overlay against the preserved official
engine and canonical 3b4b seller/runtime source. Severity here means risk of
invalidating a gameplay experiment, not a claim that an observed leaderboard
result is wrong.

| ID | Finding | Evidence | Risk | Disposition |
|---|---|---|---|---|
| A1 | O01 prepends `BUY_LAND`. | Official `_process_market` takes `q[:max_orders]`; atomic `BUY_LAND` executes at its literal order index. | **Blocker.** Can displace inherited order 10 and reorder cash dependencies. | Safe callable appends only when `len(queue) < maxMarketOrdersPerTurn`; no production wiring until capital owner accepts it. |
| A2 | E11 uses `absorption(item, current_step) * steps_left`. | Canonical `absorption()` returns only the count on the supplied step. Shop ticks and center ticks are sparse. | **Blocker.** Zero on most turns; gross overestimate on tick turns. | Sum exact integer ticks across `[current_step, final_action_step]`; reject fractional/negative transition values. |
| A3 | Original E11 hook occurs after seller pending-accounting. | Both seller variants compute `self.pending` from `out['market']` before the G01 insertion point. | **Blocker.** Checkpoint and emitted action disagree after a deferred SELL. | Builder inserts E11 before the pending loop in both seller variants. |
| A4 | O01 and E11 both own SELL removal. | O01 drops matching SELLs without E11's absorption check; `_g01_post` runs after selected transform. | **Blocker.** All-flags composition bypasses the bounded rule and can double-edit. | O01 is classification/land only; dumper reports `E11_OWNS_SELLS`. |
| A5 | E20 removes only `hire_idx[-1]`. | Multiple HIRE orders are legal and execute in queue order; `hires_today < 3` returns before examining them. | **High.** A low-demand action can still create several additional hands. | Preserve queue length and blank every HIRE beyond the remaining low-demand allowance. |
| A6 | E20 contains `if hires_today == 0` after `if hires_today < 3: return`. | Direct control-flow inspection. | **Medium.** Intended first-hire rule is dead and tests do not exercise the real boundary. | Removed unreachable branch; behavior expressed as explicit remaining allowance. |
| A7 | SHOP multiplies exact absorption by `1.5`. | Scheduler subtracts `absorption()` directly from market inventory; engine inventory and consumption are integer counts. | **Blocker.** Produces non-engine fractional state and contaminates exact price projections. | Priority multiplier is scoring-only; `preserve_exact_absorption` rejects non-integer input. No production seam yet. |
| A8 | G01 post-edits run outside selected-action ownership. | `_g01_post` is inserted after selected transform and seller checkpoint work. | **High.** Cash/route/commitment owners do not see added land or removed hire orders. | O01/E20 remain production-quarantined pending owner-bound integration. |
| A9 | Price-drop observation does not prove rival causation. | Public price movement can include both seats' prior sales and town consumption. | **Experimental confounder.** A correct transform can still be strategically wrong. | Report uses `PUBLIC_PRICE_DROP`; gameplay panel must establish value. No rival-causation claim. |

## Required first experiment

Run an **E11-only** paired panel from the same canonical archive and seed registry.
Preserve both seats, the full opponent panel, per-cell error/timeout counts, cash
and win deltas, and exact artifact hashes. Stop on any semantic/runtime failure.
Only after a non-negative development panel should O01 or E20 receive separate
owner-integrated arms. SHOP must not be evaluated by changing `absorption()`.
