# Explicit cash objectives in the existing DATE selector

`DatedSelector` now supports three objectives through the same nominal and completed-replay input paths. The default remains `robust`; existing calls and default report contents are unchanged. No controller, scenario generator, solver, simulator or policy default is added or replaced.

## Callable

```python
# Existing nominal RouteQuote path.
selector = DatedSelector(
    cash_scenarios,
    objective="expected_cash",
    scenario_weights={"no_new_buyer": "3/4", "buyer_288": "1/4"},
)
chosen_route_id = selector(offers, observation)

# Existing completed RILL report path; offers supply route IDs only.
selector = DatedSelector.from_completed_replay(
    replay, configuration,
    scenario_ids=("no_new_buyer", "buyer_288"),
    objective="minimax_regret",
)
chosen_route_id = selector(offers, observation)
```

`compare_routes` and `physical_outcomes.compare_replay` expose the same `objective` and `scenario_weights` keyword arguments. The existing CLI also reads these optional fields from its input JSON. HAZEL's `selector=` seam is unchanged; the selector returns one original route ID. The caller still owns current controller-state compatibility and executable action generation.

## Objective definitions

**robust** retains the existing worst paired own-cash improvement rule, including its existing tolerance and stable ties. No probability weights are used.

**expected_cash** maximizes expected terminal or nominal own cash under the caller's explicitly supplied weights. Weight keys must match EVERY scenario name exactly, values must be nonnegative, and their exact rational sum must equal one. Integers, finite floats, rational strings and `Fraction` values are accepted; floats are interpreted through their decimal string representation. Weights are never normalized, guessed, fitted to the observed outcomes or inferred from repeated scenario labels. Invalid/missing weights preserve the incumbent with `objective_input_invalid`.

**minimax_regret** minimizes the largest shortfall from the best eligible whole route in each supplied scenario. That scenario-wise benchmark is used only to score regret: the selector still chooses ONE route for all scenarios, not a different route after learning an unobserved future. It uses no probabilities and rejects supplied weights instead of silently ignoring them. The result depends on the explicitly supplied feasible route bank.

For both new objectives, the incumbent must have complete coverage and supported nonnegative budget evidence. Alternatives remain eligible only with complete coverage and nonnegative budget evidence in EVERY scenario, including zero-weight scenarios. An unfunded/incomplete alternative cannot set the regret benchmark. Exact score ties retain the incumbent or earlier offered alternative. `minimum_gain` is measured in cash units: expected paired-cash improvement for expected cash, or reduction in worst cash regret for regret. A strict improvement exceeding that threshold is necessary.

Reports retain existing `worst_paired_gain` and input-specific budget labels. New modes add `decision_objective`, `objective_values`, `eligible_routes`, exact rational score strings, and explicit `probabilities_calibrated=False` / `rival_utility=None`. Arithmetic is exact over the decimal representations of validated report values; it cannot recover precision already lost by the existing input cash conversion.

**These objectives may prefer a route that loses cash in one scenario. Neither establishes dominance over the incumbent, a calibrated buyer probability, paired rival margin, or a higher game win rate.** Missing/nonterminal physical evidence still returns the original input-validation fallback. Completed whole-market cash is not a per-slot minimum or a fill certificate.

## Saved-report consumer

Use RILL's already completed report, not another simulation. `check_objectives.py` imports only the existing cash selector and standard library. The example scenario name below is the exact name in RILL's reached-integrated package.

```sh
D=revenue/kaggriculture/cloud-capital-scenarios
python -B "$D/check_objectives.py" \
  --report /path/to/work/reached-final.json \
  --vary-scenario hypothetical_yarn_288_no_rival \
  --probabilities '0,1/4,5251/14509,1/2,1' \
  --output /tmp/cash-objectives.json
python -B -m unittest discover -s "$D" -p 'test_objectives.py' -v
python -B -m unittest discover -s "$D" -p 'test_dated_scenarios.py' -v
python -B -m unittest discover -s "$D" -p 'test_physical_outcomes.py' -v
```

The consumer preserves all four existing outcomes and all 1,972 recorded market rows. On that two-scenario own-cash table, SHEEP-minus-MAIN is `-5251` without the added buyer and `9258` with the declared hypothetical YARN buyer. Expected paired cash is `-5251 + 14509*p`; the exact zero-gain boundary is `5251/14509`. At that boundary the incumbent remains selected. Minimax regret reduces the worst declared cash regret from `9258` to `5251`. These are calculations over retained conditional outcomes, not new rollouts or probability estimates.

## Evidence and attribution

DATE's original selector and completed-replay validation remain the input and default. PRISM supplies only objective options in its existing ranker and argument forwarding in the physical reader. Original dependencies were materialized byte-for-byte from the saved PR10098 package: `dated_scenarios.py` blob `5e418aeca191e71d281f669a9fdd9f4b0730617f`, `physical_outcomes.py` blob `a9a0a1fc0662182b14528ad5667ef64e65b0ad08`. The final physical reader composes DATE/REPEAT's default-horizon correction, original blob `56e34211f35c3633bb4d5deb1836c9e41eda50ff`; three omitted-default objective joins match the explicit-horizon reports.

RILL's original natural-input conditional execution is PR10220; its saved archive SHA256 is `6f0b1db42c16ded162c748911167e97e9cbdcc16317d5b4f843e0b7d18e9b16e`. Its 191 manifested payloads were verified, not re-executed. Runtime source, executed tests and results are recorded in `OBJECTIVE-VALIDATION.json`; full local evidence is retained privately. No game, actor, engine or simulation execution occurs in this addition. The default selected TITAN policy and all prior experimental freezes remain unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
