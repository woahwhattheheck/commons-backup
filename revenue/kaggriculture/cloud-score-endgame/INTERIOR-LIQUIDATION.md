# Interior terminal-liquidation stress experiment

This is a bounded research comparison for the existing terminal-input producer.
It adds no controller, predictor, solver, release archive or default-policy change.
The single canonical TITAN release stays with its integration owner.

## Concrete question and fixed family

The completed history ablation (PR10158) found that ordinary same-hour history
often omitted the rival's actual final liquidation. This experiment tests one
narrower possibility on the already-exposed PR10099 development bank: whether
adding interior sale positions to the existing finite stress family changes
terminal decisions. It does not attempt to recover hidden rival inventory.

`interior_liquidation_scenarios(mechanics, observation, configuration)` retains
all 21 original `stress_scenarios` entries, including their IDs and provenance.
It then adds a full-capacity sale for each of the nine products at market slot
`maxMarketOrdersPerTurn // 2`, followed by two mixed-product queues. The mixed
lot is the existing evenly distributed capacity allocation in current-price
rank order; sale sequences alternate highest/lowest rank, then reverse that
interleaving. Identical added shed/queue pairs are omitted. The default family
has exactly 32 columns, within the current 8-real-plan/32-stream interfaces.

The rule was frozen before the selection pass. Only the current public market,
final-step marker and configuration determine the hypotheses. Private rival
stock, authored rival actions, game labels and future outcomes are not inputs.
These are explicit current-snapshot stress assumptions, not calibrated
probabilities, history-complete possibilities or an exhaustive uncertainty set.
Every hypothesis obeys the shared shed capacity and fixed market-slot positions.
The complete own-plan family and the default absolute win-point objective remain
unchanged. There is no trimming of unfavorable columns to fit the budget.

## Executed result

Eleven new focused methods pass, with zero failures, errors or skips. Sixty-six
new cash-pair comparisons agree with the complete pinned native terminal
interpreter across both player positions. A separate manufactured MILK case
shows that the middle-slot cash pair differs from both extreme-slot pairs:
these new columns are not merely renamed copies. Small capacity/order limits,
nonmutation, exclusion of private fields, original-cell retention and partial
extra-family fallback are also covered.

The existing bank contains 32 records, 24 distinct observation payloads and
only two previously exposed development seeds. All 4,452 original native
receipt cells were consumed without recomputation. The new columns add 2,332
native market calls and 32 own-unit boundary captures. The actual current
LARCH/ANCHOR score consumer (blob `f8219d69985f4fe5a92e688a42507c5294db5744`)
was called on both old and expanded tables: 64 first-call selections, **zero
changed complete actions**. The old-table actions match the saved original
outputs, preserving the source-comparison control.

The extra columns lower the worst modeled cash margin for at least one plan
in eight records, including the original plan in two records. Nevertheless,
no baseline worst terminal-point value changes and no improved absolute
optimum causes a different action. Thus these interior patterns alone do not
resolve the economic activation gap on this bank.

Only after `decisions.json` was written did the separate evaluation command
open recorded rival actions and terminal outcomes. Sixty-four final native
transitions reconcile every historical cash pair and preserve every selected
cash pair: the old source-record accounting remains 28 wins and four ties.
Those are reused historical records, **not 32 new independent games**. No full
episode, actor reconstruction, held panel or new gameplay seed was executed.

A read-only stress check of LARCH's four already-frozen cash-Pareto selections
also retains their all-column cash dominance. Each of the eleven added columns
has exactly zero candidate-minus-baseline margin change for those actions.
This does not create new selections or re-establish game strength; it merely
checks the prior choices against the newly computed cells. Their original
mirrored-match interpretation remains with PR10132.

## Use and reproduce

Place this directory and the existing `cloud-score-endgame` source on the
module path. The callable passes its output straight to the existing producer:

```python
from interior_liquidation import interior_liquidation_scenarios
from terminal_inputs import build_terminal_inputs

family = interior_liquidation_scenarios(mechanics, observation, configuration)
packet = build_terminal_inputs(
    mechanics, observation, configuration, selected_action,
    post_unit_observation=the_same_selected_unit_snapshot,
    scenarios=family,
)
```

A caller must still preserve its complete fallback for an incomplete table.
The helper does not recompute units or certify the supplied snapshot. Do not
activate it in the canonical release on the basis of this negative experiment.

The private evidence package supplies `work/`, `source/`, `dependencies/`,
`current_dependencies/`, `engine/`, `inputs/` and `results/`. From its root:

```sh
export PYTHONPATH="$PWD/source:$PWD/work"
python -B work/test_interior_liquidation.py \
  --loader dependencies/engine_loader.py --engine-dir engine \
  --consumers dependencies --core-file dependencies/full_support.py \
  --score-file current_dependencies/score_endgame.py --output /tmp/interior-tests-new.json
python -B work/check_interior_liquidation.py select \
  --archive inputs/development-records.json.xz --saved-report evidence/reached-first.json \
  --loader dependencies/engine_loader.py --engine-dir engine \
  --consumers dependencies --core-file dependencies/full_support.py \
  --score-file current_dependencies/score_endgame.py --output /tmp/interior-decisions-new.json
python -B work/check_interior_liquidation.py evaluate \
  --archive inputs/development-records.json.xz --decisions /tmp/interior-decisions-new.json \
  --loader dependencies/engine_loader.py --engine-dir engine \
  --consumers dependencies --core-file dependencies/full_support.py \
  --score-file current_dependencies/score_endgame.py --output /tmp/interior-evaluation-new.json
```

Output paths must be new files. Selection and outcome evaluation are separate
invocations. `extend_packet` checks original-plan and post-unit state identity,
preserves every original receipt, and cannot pass an unfinished new family as
a complete table. The runner is an offline comparison on this retained source
bank, not a new game runner or an automatic selector of terminal models.

`INTERIOR-RESULTS.json` contains compact counts and exact source/evidence
identities. Detailed observations, modeled receipts, frozen selected actions,
recorded rival actions and outcome comparisons remain in private Library
storage. Native engine source is the retained Kaggle commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; its exact three hashes are retained.
Runtime dependencies are reused from PR10099 and the current score consumer,
not copied or changed in the public source tree. The generator was unchanged
through the experiment; the runner's initial schema/printing corrections were
made before selection and recorded in `SELECTION-FREEZE.json`.

The next consumer is the canonical builder's terminal-model work: keep the
current release unchanged and use this fixed negative result to avoid treating
these eleven additional patterns as an established improvement. The broader
terminal-special-case and floor-censoring issues from PR10158 remain open.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
