# Completed physical outcomes in the existing DATE selector

The opt-in `DatedSelector.from_completed_replay` consumes RILL's existing
`replay_routes` report. Both this input path and the original nominal RouteQuote
path use the same `_rank_paired` rule. There is no second selector, route producer,
scenario generator, simulator, native export or selected-policy change.

## Use at the existing callback

```python
from dated_scenarios import DatedSelector

# completed_replay comes from RILL's existing replay_routes, using this same
# pre-action controller state, observation, configuration and offered route bank.
selector = DatedSelector.from_completed_replay(
    completed_replay,
    configuration,
    scenario_ids=tuple(public_scenarios),  # complete declared bank, not surviving cases
)
outer = choose_before_action(
    existing_controller, observation, configuration, mechanics, selector=selector,
)
comparison = selector.last_report
```

Keep `dated_scenarios.py` and `physical_outcomes.py` importable together. Retain
the original RILL report beside `last_report`. The original `DatedSelector` with
`CashScenario` remains unchanged at its public call sites; the nominal JSON CLI
is unchanged. The factory itself runs no simulation and does not call an agent.
Its report reference is read-only input, not a copied result or a cache of a
previous decision. Validation is performed on each invocation.

The caller must supply the full expected scenario set independently of the
report's surviving cases. Missing/duplicate cases, partial execution, a different
initial observation/incumbent, changed offered program across scenarios, or a
nonterminal/mismatched horizon retain the incumbent with an explicit invalid-input
reason. A case has a full chronological market-queue history, consistent cash
before/after/delta, and matching final/gain/minimum values. Nothing converts a
missing future to zero or removes it from the comparison. The caller's
`configuration.get('episodeSteps', 720) - 2` defines the expected final executable
step, matching the existing replay producer when the field is omitted. An
explicit custom value is still checked; null and invalid values are not defaulted.

RILL's report binds the original observation and offered program identities,
not arbitrary hidden controller state or a digest of every configuration field.
The caller must use the same actual producer state and configuration. These
checks do not authenticate externally edited reports or make unrelated replays
interchangeable. The retained input is a conditional own-state model; it is not
interactive two-player execution.

## Distinct accounting, same ranking rule

Executed terminal own cash replaces the original quote's assumed receipts and
fixed costs. Failed purchases are not charged again. Whole-queue cash is **not**
split into guessed per-slot fills. `minimum_after_market_cash` includes initial
cash and the recorded cash after each entire market queue; it is not an intraturn
trough or a certificate that every intended purchase filled.

The comparison uses worst paired own-cash gain against the incumbent over the
explicit bank. A strictly positive gain and nonnegative recorded queue cash are
required to change the route; ties keep the incumbent. This is a chosen robust
own-cash criterion, not calibrated win probability, expected value or rival
margin. The report uses `final_executed_cash` and
`recorded_queue_cash_nonnegative`, not the nominal path's labels. Rival utility
stays null. HAZEL's original outer quote-screen report is still separate.

## Executed retained-data join

RILL PR10083 / merge `99544ba08465a391733a38dcde77c917fd5e651a` supplies four
complete controller continuations from the same conditional state at226 through
718. The consumer reconciles all1,972 recorded market queues without executing a
simulator, parent action or game.

| Explicit future | MAIN terminal own cash | YARN terminal own cash | YARN minus MAIN |
|---|---:|---:|---:|
| Remaining draws BRUNCH | 132,505 | 121,602 | -10,903 |
| First new buyer YARN at288 | 141,093 | 149,667 | +8,574 |

Both columns are consumed together. The existing robust rule retains MAIN at
-10,903 worst paired gain. The deliberately positive-only test changes the
explicit hypothetical bank; it does not claim that future was known at226.
Removing the negative column while still declaring the original two-column bank
is rejected. Additional controls reject missing cases, incomplete execution,
nonterminal results and a changed initial observation. All minima in the retained
report are23, measured after whole queues plus initial cash.

The real Arlene/HAZEL selection seam is invoked once, with no controller action
call or mutation. That binding harness uses a fresh controller instance; it does
not reconstruct the progressed controller state inside RILL's saved experiment.
RILL's original physical results, future-state hypotheses and provenance remain
its evidence. This consumer adds no new physical validation or game panel.

39 unit methods pass: the original23 DATE regressions, including their existing
1,000 integer-oracle cases, plus16 new engine-free input-bridge methods. No old
method is counted as new. `completed-tests.log` is the executed combined log.
`completed-replay-results.json` retains the exact joined report, five negative
controls and measured timing. Fifty existing-report validation/ranking calls
measured median1.729ms and maximum2.541ms here, excluding imports, quoting and
simulation; these are not whole-agent timing bounds.

## Reproduce

Reuse Library `titan-capital-buyer-sensitivity-evidence.zip`, file ID
`file_00000000987c81f5897e1bbd20c2b9e4`, ZIP SHA-256
`1b5f4f7707e71bbd93af5b4e396449ee37c7a17ae921f45dbcd42abbb0d5b1b2`.
Its existing `evidence/shop-sensitivity.json` is3,471,361 bytes, SHA-256
`22276ac78fc06c99fe6e58e878eed24d9f526b68616c3183f1a48e6ddd1f278c`.
Do not rerun its simulator or request another exporter for this check.

```sh
python -B -m unittest discover -p 'test_*.py' -v
python -B check_completed_replay.py \
  --replay /path/to/evidence/shop-sensitivity.json \
  --arlene /path/to/vendor/base/arlene.py \
  --hazel /path/to/cloud-capital-bundles/capital_routes.py \
  --mechanics /path/to/vendor/sell/mechanics.py \
  --output /tmp/completed-replay-results.json
```

The checker verifies original Arlene SHA-256
`1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`,
HAZEL blob `00abee3c99641eb0ab1729fd80e6f9a5c783f373`, and consumed mechanics blob
`044a4f9c0a4a44dde10ada57563238bcaf82075d`. These dependencies already exist in
the source pack used for PR10040; no duplicate source or engine is vendored here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
