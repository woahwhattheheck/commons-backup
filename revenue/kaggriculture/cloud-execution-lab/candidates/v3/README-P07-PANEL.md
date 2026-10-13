# P07 observation-bound actor assignment panel

This evidence lane closes the gap between the replay finding and the current P07
implementation. It does not add another actor-assignment policy.

The supplied top-five study established the exact discriminator:

- top-five leaders: 17,256 observation-bound decisions, zero worker-action
  cardinality overages;
- submitted TITAN episode `107130860`, seed `539131249`: 45 overage rows, 45
  unreachable worker commands, 26 unreachable non-`PASS` commands.

`p07_actor_binding_panel.py` materializes the exact P07 candidate from the exact
canonical archive and delegates gameplay to the existing source-bound paired
official-engine runner. A narrowly patched evaluator records, before each
interpreter call:

1. the candidate action digest for all 719 decisions;
2. the physical hand count in the immediately preceding observation;
3. every returned `hands` suffix beyond that count;
4. how much of that unreachable suffix is non-`PASS` work.

The panel rejects missing/duplicate/incomplete cells, malformed instrumentation,
nonfinite scores, action-count drift, provenance drift, score changes without a
candidate-action change, any cell with increased actor overage, any own-cash or
margin regression, any new loss, and any lost win.

Outcomes are intentionally separated:

- `REJECT_NO_DEFECT_WITNESS`: the tested cells never reproduce the cardinality
  defect, so they cannot validate P07;
- `REJECT_DORMANT_OR_UNBOUND`: the candidate does not remove the witnessed defect
  or evidence is not action-bound;
- `ACTIVE_BUT_REJECT_SCORE_SAFETY`: physical closure activates but score safety
  fails;
- `ACTIVE_PARITY_EXTEND_PANEL`: the defect is removed at exact score parity;
- `ADVANCE_TO_DISJOINT_HOLDOUT`: physical closure is score-safe and produces a
  strict own-cash or margin gain in at least one cell.

The workflow uses the exact replay seed plus two independent fixed seeds, Arlene
and the submitted V1 reference, and both candidate seats. This is development
evidence only. It does not mutate canonical runtime/config/archive pointers,
submit to Kaggle, or claim hosted-rating/leaderboard strength.
