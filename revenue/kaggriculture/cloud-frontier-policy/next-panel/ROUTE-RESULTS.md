# Arlene route and ordered-shed continuation

Continues accepted checkpoint42df8480bedf254b121a179ea5c7b2f51747fb1b. Source checkpoints PR9838 and PR9840 preserve three independent variants. No accepted archive or submission transport was changed. Root/ROWAN owns future selection and account operations.

## Selected research successor: carrot-demand

Exact source208d627ebee0fd3a90e9bd26b444274d72255ac636b22147de301fcb7483ca3a preserves Arlene v14 as an unchanged prefix and appends only one feature predicate plus native entrypoint `lark_carrot_demand_entrypoint`. At the parent's existing turn360 decision, an already visible FARMERS_MARKET can trigger YARN_CARROT before carrot price reaches42. The original price trigger remains available. The controller's `_switch_ok` still requires the entire executed prefix to match; YARN and YARN_CARROT first differ at360. No routes are averaged, no late state reset is invented, and no seed identity or future shops enter the policy.

This is production allocation, not a generic service or immediate-sale overlay. Relative to YARN's remaining tape, the carrot route plans84 more carrot sales,54 fewer milk sales,44 fewer wheat sales and four fewer strawberry sales, plus26 carrot seeds, one fewer wheat seed and eight more fertilizer purchases. These are intended tape quantities, not guaranteed realized revenue. The route retains coordinated capital orders, worker schedules and liquidation. A visible shop is a demand signal, not certainty about future price.

Development seeds9500401,9500419,9500437,9500455,9500473,9500491; both seats against exact Arlene and Apex,24 candidate and24 controls. Candidate source and route-selection.json were frozen before reserved9500503/9500521, both seats,8 candidate and8 controls. No parameter changes followed reserved results.

| Panel / opponent | Candidate W/T/L | Baseline W/T/L | Candidate mean margin | Baseline mean margin | Paired margin change |
|---|---|---|---:|---:|---:|
| Development / Arlene |2/10/0|0/12/0|153.8333|0|153.8333|
| Development / Apex |12/0/0|12/0/0|6,433.1667|6,092.1667|341|
| Reserved / Arlene |2/2/0|0/4/0|1,144.5|0|1,144.5|
| Reserved / Apex |4/0/0|4/0/0|2,552|1,208|1,344|

Reserved exact cash, each row reproduced in both seats:

| Seed | Opponent | Candidate own / rival | Baseline own / rival | Candidate margin | Paired margin change |
|---|---|---|---|---:|---:|
|9500503|Arlene|76,899 /76,899|76,899 /76,899|0|0|
|9500503|Apex|76,737 /75,197|76,737 /75,197|1,540|0|
|9500521|Arlene|80,273 /77,984|78,179 /78,179|2,289|2,289|
|9500521|Apex|80,309 /76,745|78,021 /77,145|3,564|2,688|

Only one of six development seeds and one of two reserved seeds benefited; the remaining games were unchanged. This narrow evidence supports a research successor, not a claim of leaderboard superiority or broad optimality. Against Arlene on9500419, own cash rose2,286 while rival cash rose1,363, yielding only923 margin; own cash and game margin remain separate quantities.

Accepted exporter package: `exports/carrot-demand/submission.tar.gz`,34,313 bytes, SHA256 **5b2626299ec853d40f81d0379c3d07f8236c927968d7eb01e60a46d0520c37cc**. Main SHA256 **208d627ebee0fd3a90e9bd26b444274d72255ac636b22147de301fcb7483ca3a**. Source checkpoint6c6aaa607f72e359914ffdcc9d95cf944d6e33ba. Full Apache-2.0 LICENSE, Arlene attribution and explicit modification notice are included.

Extracted archive through the accepted official native loader reproduced reserved9500521 seat1 versus Apex:80,309/76,745,719 action rounds, no failure. Cold first call96.94ms; separate process startup382.76ms; summed candidate call CPU0.453s; complete-game wall7.065s under concurrent cloud work. Cold loading is included, not excluded from timing. The export replay is packaging verification on a consumed seed, not another held-out win. Raw CPU/RSS counters retain the evaluator's sampling caveats; call CPU and measured wall times are the useful comparisons.

## Rejected current-price allocation gate

`carrot-opportunity-main.py` SHA0461aeee3da71606f109a9b61a125262064896dc89d7d341d803af38abd642d5 valued the entire tail delta at current prices and additionally required positive value before Arlene's carrot switch. Eight development games on9500401/419: two losses/two ties against Arlene, four wins against Apex but substantially worse margin. Reject this gate.

On9500401 it retained dairy when milk was at price1. Executed allocation added54 milk units for only60 extra milk cash but lost84 carrot units/4,812 carrot cash. Own cash fell3,959 against Arlene and4,229 against Apex; margins fell4,612 and4,684 respectively, in both seats. Marking a long production tail at one current price was misleading. Raw failures remain available, not promoted.

## Separate ordered-shed repair: useful mechanics, no demonstrated score gain

Root identified that Arlene projected DROP/PLACE but ignored earlier PICKUP and stopped at an initially full shed. `ordered_shed.py` and independently runnable `ordered-shed-main.py` repair ordered shed transfers, including overflow discarded by DROP and partial PLACE retaining excess. Farmer precedes hands. Animal placement takes precedence over shed fallback. Corrected `proj` feeds the existing sale clamp, dead-stock/terminal logic and day-close capacity guard. Day-close carry accounting uses post-transfer inventories, avoiding double counting dropped goods or resurrecting discarded overflow.

This is a bounded transfer projection, not another simulator. The parent's other day-close production/consumption estimates remain inherited approximations; they are not newly claimed exact. Corrected source SHA **75969124849d58814ac1512e93e267946c77cb7f284616cbd54ed17505ce87aa**, native entrypoint `lark_ordered_shed_entrypoint`. Build with `build_ordered.py`. It is NOT combined into carrot-demand and does not mutate the accepted baseline.

Against the pinned official `_apply_unit_action`,912 existing sampled observations had zero projected-shed mismatches;392 differed from the old projection. Those sampled differences did not coincide with a SELL of the differing item. Root's legal full-shed case also matches: WHEAT10/MILK90, farmer PICKUP WHEAT10 then hand DROP MILK10 produces WHEAT0/MILK100, with farmer carrying10 wheat. Primitive correctness alone is not a performance claim.

Eight full games on9500401/419 against exact Arlene/Apex, both seats, changed traces but produced identical cash and executed unit/market totals to controls. One additional passive same-observation diagnostic identifies the concrete reachable order repair: step697, shed FERTILIZER23; farmer and eight hands PICKUP all23; the parent still emits SELL FERTILIZER23 after SELL WHEAT50. The repair removes that empty sale. Game remains82,016/82,016. This establishes a reachable invalid-order correction, not a terminal-cash gain or a freed slot that was profitably reused.

## Evidence and reproduction

`results/per-game.csv` and experiment-summary.json now cover199 total games across this and the historical frontier work. This continuation adds82 games:24 controls,8 rejected gate,24 carrot-demand development,16 reserved candidate/control,8 shed repair,1 shed diagnostic and1 native export replay. All completed719 rounds without runtime failures. Complete compressed raw reports retain terminal state, action counts, market units/cash, observed conditions and runtime; receipts.json hashes raw/compressed reports and source/evaluator pins. Historical NEXT-RESULTS.md remains the prior117-game selection packet.

From the existing cloud workspace:

```sh
python commons/revenue/kaggriculture/cloud-frontier-policy/next-panel/build_experiment.py carrot-demand --runtime next-panel-runtime
python commons/revenue/kaggriculture/cloud-frontier-policy/next-panel/measure.py --engine-dir engine --runtime next-panel-runtime --candidate next-panel-runtime/carrot-demand-adapter.py --opponents arlene,apex --seeds 9500503,9500521 --output route-reproduction.json
```

Use `arlene-adapter.py` for controls; these seeds are now consumed. `check_ordered.py` reuses the existing pinned engine and compressed baseline observations for the bounded mechanics comparison. `--reference-arlene` enables passive same-observation order diagnostics in the driver; it never feeds actions back to the candidate and adds driver work to that report's timing. Source execution remains under the existing official-loader/offline adapters. No source re-download, new simulator, paid compute, owner-PC work, model-UI action or submission occurred.

Any later public Kaggle distribution should retain CARROT-DEMAND-NOTICE.txt, full license and upstream link, and its actual public forum/code URL should be retained by the account owner. This GitHub checkpoint is not a claim that such an announcement or upload occurred.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
