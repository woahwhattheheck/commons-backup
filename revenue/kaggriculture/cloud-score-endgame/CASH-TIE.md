# Opt-in cash dominance at an absolute-score tie

The existing absolute-score solver and default baseline-on-tie rule are
unchanged. `solve_absolute` and `make_score_selector` now accept
`tie_break='cash_pareto'` as an explicit alternative. The default is still
`tie_break='baseline'`; no selected TITAN entrypoint is switched by this change.

## Selection rule

First solve the SAME complete terminal win-point matrix through the existing
POLY solver. Only a valid, completed, exact optimum is eligible. If the optimal
absolute floor improves on baseline, preserve the original result and behavior.
If it equals baseline, inspect the real pure actions in the caller's original
order. Select the first action whose absolute own-minus-rival terminal cash is
at least baseline's in EVERY supplied scenario and strictly greater in one.
Otherwise retain baseline. No scenario is removed or assigned a probability.

This is a deliberately small tie rule, not a mean-cash objective, a new mixed
solver, a search for every Pareto-optimal mixture, or a calibrated prediction.
The ordering of supplied actions is the deterministic secondary preference.
Reordering scenario columns cannot change which pure action qualifies.

Cash-margin dominance also preserves terminal win points componentwise. The
chosen pure action must have exactly the already-certified absolute optimum.
Its weights, column expectations and support form a separate primal witness
against the original solved dual. The unchanged certificate verifier checks
that witness before PRISM's unchanged sampler consumes it. `raw_solver` retains
the original provider result; `tie_break_certificate` retains the new witness.
The virtual embedding row has zero weight in both. Absolute `value` is still
win points, not cash improvement or the shifted solver value.

The pure choice still uses the existing one-draw/persistent-plan path. Current
full-action feasibility, parent preservation, completed keys, and no-redraw
behavior remain the existing selector's responsibilities. Missing/nonterminal
receipts, invalid/incomplete solutions, or unknown feasibility retain fallback.

## Use

```python
answer = solve_absolute(document, build_table, solve_full_table,
                        verify_certificate, tie_break='cash_pareto')

score = make_score_selector(WholePlanSelector, make_selector, build_table,
                           solve_full_table, verify_certificate,
                           rng=local_rng, tie_break='cash_pareto')
output = score.transform_terminal(observation, configuration, selected_action,
                                 document=packet['document'],
                                 feasible=current_full_action_check)
```

The CLI accepts `--tie-break cash_pareto` with the existing input/solver files.
No new scenario model, unit projection, or production call is introduced. The
current hypothetical terminal receipts must still correspond to the actual
public/own decision state and complete supplied actions. A guarantee over a
finite scenario table is not a guarantee against omitted real behavior.

## Executed evidence

Twenty original focused methods passed against the actual PORT, POLY, PRISM
and T15 components. After joining ANCHOR PR10127, all 24 methods pass, including
four additional opt-in/context cases. They cover primary-objective precedence, exact rational ties,
strictly positive versus all-zero changes, rejection of one negative column,
separate own/rival cash, fixed original row order, invalid/unfinished/budget
results, data detachment, CLI use, provider certificate remapping, actual
complete-action selection, feasibility, and same-step parent retries.

The decision source was fixed before recorded-rival outcome lookup. The final
composition preserves ANCHOR's context helper and terminal transform unchanged,
and preserves the frozen economic rule unchanged. All 32 decisions are identical
before and after that composition; the four native selected-action receipts
remain evidence for those same actions rather than a second engine execution. All 32
original default result objects match the original module exactly. Applying the
opt-in rule to POLY's already-retained runtime receipt matrices changes four
complete actions. Only after all decisions were written was the existing
native-counterfactual report joined by the selected action ID. The old source
record totals are 28 wins / 4 ties under baseline and 30 wins / 2 ties under the
opt-in variant. The two tie-to-win rows are ONE original development matchup
mirrored, not two independent successes. Two already-winning rows improve
margin without a win-point change; the other 28 actions remain identical.

These are terminal counterfactuals on existing development records, NOT newly
executed full games, held validation, leaderboard results, or a promotion.
The finite default stress family and original production policies are unchanged.
Four selected-action native market checks reproduce the saved cash pairs after
four existing own-unit boundary captures. They consume the already-frozen
decisions; recorded rival private state/action is evaluation-only and never
enters the selection rule. No entire historical panel is rerun.

One initial evaluation attempt stopped at the input-identity assertion because
the checker used sorted serialization. It was corrected to the producer's
order-preserving fingerprint before the completed evaluation; decision source
remained unchanged. Full original attempt log, freeze, decisions, evaluation,
native receipts and dependencies stay in the private Library evidence package.
Git retains source/reproduction and aggregate results only.

## Reproduction with existing local dependencies

```sh
R=revenue/kaggriculture
D=$R/cloud-score-endgame
export PYTHONPATH="$D:$R/cloud-terminal-utility:$R/cloud-full-support:$R/cloud-market-game-theory:$R/cloud-weighted-plan-selector"
python -B -m unittest discover -s "$D" -p 'test_cash_tie.py' -v
```

For the recorded development comparison, materialize and extract the existing
`TITAN-POLY-terminal-inputs-20260907.zip` Library source. Its SHA256 is
`af693707f97eea60e068a094af075255c107407c067eb82977a84a2ad74c1cd4`.
Let `B` be its extraction root; it contains source/, dependencies/, engine/,
inputs/ and evidence/. The original runtime is retained in its dependencies.

```sh
export PYTHONPATH="$D:$B/dependencies:$B/source"
python -B "$D/evaluate_cash_tie.py" "$B" \
  "$B/dependencies/score_endgame.py" /tmp/cash-tie-evaluation
python -B "$D/verify_selected_markets.py" "$B" \
  /tmp/cash-tie-evaluation/decisions.json \
  /tmp/cash-tie-evaluation/evaluation.json /tmp/cash-tie-native.json
```

The first command calls the existing solver/selector on retained matrices but
no engine, controller or scenario generator. The second runs only the four
selected terminal market checks using the existing pinned native helpers.
Neither command uses new seeds, provider requests or historical held games.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
