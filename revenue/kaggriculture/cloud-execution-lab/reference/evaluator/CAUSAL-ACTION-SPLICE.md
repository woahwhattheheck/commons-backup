# First-divergence hybrid action splice

`causal_action_splice.py` answers a narrow counterfactual question:

> On an exactly reproduced pre-world, what happens when the candidate's first
> different returned action is executed in place of the baseline action, and
> vice versa?

This is an offline diagnostic. It uses the pinned official interpreter and the
process-isolated `Actor` from `evaluate.py`. It does not call Kaggle, upload a
submission, or edit canonical gameplay.

## Interpretation boundary

The treatment and ablation are **hybrid output interventions**, not coherent
integrated policies. TITAN can mutate seller/controller state while producing
an action. The baseline process therefore continues with baseline-committed
state after the candidate output is executed, and the candidate process
continues with candidate-committed state after the baseline output is executed.
The report diagnoses an environment/output edge. It cannot by itself attribute
an entire source feature, nominate a package, or predict leaderboard strength.

## Fail-closed experiment

For each seed and focal seat the evaluator runs six games:

1. **Baseline discovery.** Baseline controls the game. Candidate is a shadow on
   the identical focal observations until the first type-sensitive returned-
   action difference. Only baseline output reaches the interpreter.
2. **Baseline replay.** Exact complete-state trace, score, target context,
   focal output, and rival output must reproduce.
3. **Candidate native.** Candidate controls the game and must reach the same
   first-divergence pre-world.
4. **Candidate replay.** Candidate trace, score, target context, and outputs
   must reproduce exactly.
5. **Candidate output on baseline.** Baseline remains the live policy process,
   but the authenticated candidate shadow output is executed at the target.
6. **Baseline output on candidate.** Candidate remains the live policy process,
   but the authenticated baseline shadow output is executed at the target.

Before either intervention, policy and shadow outputs must match byte-for-byte.
At the target, the evaluator requires equality with discovery for:

- step/day position;
- full canonical pre-world, including both agent states and environment info;
- both seat observations;
- the complete pretarget trace;
- baseline and candidate focal outputs;
- the target-step rival output.

A missing target, early terminal, serialization failure, launch drift, source
mutation, target mismatch, or replay mismatch is `failed`/`unstable`, never
economic evidence. Per-step trace custody hashes the complete pre-world,
executed actions, and post-world rather than only terminal bank values.

## Source custody

Every input is first copied into an authenticated regular-file snapshot. Every
actor process then receives a fresh private read-only copy. The complete
normalized file closure, modes, sizes, and SHA-256 hashes are checked before
and after every process and again after the panel. Archives reject:

- absolute/traversing/backslash paths;
- duplicate normalized paths;
- links, devices, and all non-regular members;
- missing root `main.py`;
- oversized members, expanded archives, or member counts.

Directory and entrypoint inputs are snapshotted recursively. The receipt marks
that imports outside an entrypoint's snapshotted parent and installed-package
provenance are not dynamically attested. Archive inputs are preferred for
baseline/candidate evidence.

## Effects and labels

The report retains three metric vectors (`focal_score`, `opponent_score`, and
`margin`):

- `candidate_native_minus_baseline`;
- `candidate_action_on_baseline` (treatment minus baseline);
- `candidate_action_on_candidate` (candidate native minus ablation).

It also records W/T/L transitions. Metric-specific labels are emitted for own
score, margin, and opponent-score reduction. The unqualified cell label is
conservative and explicitly hybrid:

- `hybrid_own_supported`: both own-score estimates are nonnegative, at least
  one is positive, margin is not jointly harmful, and neither outcome worsens;
- `hybrid_own_harmful`: own score is jointly harmful or an outcome worsens;
- `hybrid_neutral`: own and margin estimates are both zero;
- `hybrid_mixed`: everything else;
- `dormant`: no typed returned-action difference appears on the baseline path.

One cell remains one seed/seat/opponent/action diagnostic, not an admission
panel.

## Run

From `reference/evaluator`:

```sh
python -B -m unittest -v test_causal_action_splice.py

mkdir -p /tmp/titan-splice
python -B causal_action_splice.py \
  --baseline ../../exports/integrated-selected-v1.tar.gz \
  --candidate ../../exports/titan-current.tar.gz \
  --opponent official_starter \
  --seeds 2027,6607,104729 \
  --seats 0,1 \
  --output /tmp/titan-splice/report.json
```

`--baseline`, `--candidate`, and `--opponent` accept a deterministic root-
`main.py` archive, an extracted root-`main.py` directory, or an evaluator entry
specification such as `/path/main.py::agent`. `--output` is required, its parent
must exist, and it must be outside every authenticated/executable source root;
direct and same-inode aliases are rejected.

## Receipt

Schema v2 records engine/loader/evaluator hashes; archive and complete closure
hashes; fresh-copy pre/post custody; seed, seat, target position, both
observations, pre-world/prefix/rival-output hashes; typed focal outputs and
structural paths; complete native/replay/treatment/ablation runs; post-world
hashes; own/rival/margin effects; W/T/L transitions; and metric-specific plus
hybrid classifications.

The command exits nonzero for `failed` or `unstable` cells. Completed hybrid,
neutral, mixed, harmful, supported, and dormant measurements do not by
themselves authorize source integration or release.
