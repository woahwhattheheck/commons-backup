# Gemini EGG town-clock scarcity frontier

Status: **research-only corrected descendant; no activation or optimality claim**.

## What survives from the Gemini exploit

The literal "short squeeze" proposal is not an engine-legal EGG strategy. In the pinned official engine, `BUY_PRODUCT` can buy only `WHEAT` and `FERTILIZER`; an agent cannot buy public EGG inventory into a dark pool. Holding newly produced EGG also does not remove existing public inventory. The finite EGG curve and its outer bounds are already authenticated in `../market-baseline/EGG-ELASTICITY.json` / `egg_elasticity_bound.py`.

The useful residue is **scarcity timing**. Town shops and the town center consume public inventory. The interpreter executes `_process_market(...)` before `_town_consume(...)`, so an EGG sale on a consumption tick is quoted *before* that tick removes supply. A sale moved to a later turn can capture the lower public inventory and higher price, provided rival supply and other state changes do not erase the edge.

That is the corrected descendant implemented here: `gemini_egg_timing.py` searches later placements for one already-planned literal `SELL EGG` and delegates every transition/economic result to the existing pinned full-interpreter `sale_window.compare` harness.

## Sale receipt, not residual cash

The frontier must not confuse a cash-flow side effect with EGG scarcity value. Delaying an early EGG sale can remove cash that would have funded an intervening HIRE/BUY; if that spend then fails, the candidate may finish the window with *more* cash even when the delayed EGG sold at the same or a worse quote.

Therefore `best_positive` is sale-specific:

- baseline source EGG sold units must be positive;
- candidate target EGG sold units must equal the baseline sold units;
- candidate target-row `sale_cash` must be strictly greater than baseline source-row `sale_cash`.

The source and target row metrics are evidence, not defaults. Each requested `(seat,row)` must resolve to exactly one report record and its `sold` / `sale_cash` field must be a non-negative plain integer. Missing, malformed, or duplicate matching records make that candidate receipt-ineligible; they are never coerced to a synthetic zero. A genuine integer zero receipt remains valid evidence.

The report exposes `source_sale_cash`, `target_sale_cash`, `sale_cash_delta`, and `receipt_evidence_valid`. `own_cash_delta`, `window_margin_delta`, and terminal margin remain separate consequence metrics; they can be negative even when a genuine EGG receipt improvement exists, and they are still required for any later economic/policy gate.

## Why this is stronger than a one-step rule

A fixed "wait one turn" patch leaves money on the table when several known town-consumption pulses occur inside the available action tape. The frontier enumerates every legal later PASS/append destination up to a bounded horizon and ranks realized retimings by **sale-specific receipt improvement first**, then window cash/margin as secondary context. A target that changes syntax, changes sold quantity, or merely causes another spend to fail is not scarcity-price evidence.

The full interpreter also captures the important counter-case: rival EGG sales in the fixed tape can overwhelm town depletion and make waiting worse. There is no blanket "always hold EGG" rule.

## Fail-closed boundaries

- Source must be one positive literal `SELL EGG` row. No synthetic EGG buy is created.
- Destination must be a later literal `PASS` slot or an append position inside the live market-order cap; inherited economic rows are never displaced.
- `sale_window.shift_sale` and `sale_window.compare` preserve opponent actions and all non-market actions and run the complete pinned interpreter.
- `best_positive` requires valid unique source/target row metrics, equal positive EGG sold units, and `target_sale_cash > source_sale_cash` in this bounded open-loop tape. Missing, malformed, or duplicate metric evidence is ineligible rather than zero-filled. It is **not** a policy, current-native strength claim, or promotion signal.
- Net window cash cannot substitute for sale-receipt improvement.
- Empty-shed, clipped-row, partial-fill, rival-supply, EOD-delivery and other engine effects remain visible because the full interpreter—not an analytical shortcut—decides fills and money.

## Promotion path

1. Run a current-native/gauntlet census of natural EGG SELL exposures.
2. For filled sources, evaluate bounded later placements with this frontier.
3. Require both-seat sale-receipt improvement **and** non-negative rival-aware window/terminal economics before authoring any native experiment callback.
4. Only then consider extending the opt-in native sale-window target set to EGG. Do **not** widen `native_sale_window.SAFE_PRODUCTS` from elasticity or receipt timing alone.

This keeps the best part of the Gemini idea—the finite price resilience plus town-clock timing opportunity—while killing both the impossible direct market-cornering premise and the false-positive residual-cash attribution path.
