# ARC-AGI-3 episode replay trace

Offline public-safe trace schema, validator, failure/budget profiler, and A/B trace comparator.

## Validate one episode

```bash
python competitions/arc-agi-3/validate_arc3_trace.py \
  competitions/arc-agi-3/fixtures/valid_episode.jsonl
```

The validator enforces contiguous sequence numbers, exact state continuity, action and wall-clock budgets, terminal/failure semantics, and optional canonical digests.

## Profile failure clusters and budget waste

```bash
python competitions/arc-agi-3/profile_arc3_runs.py \
  competitions/arc-agi-3/fixtures/valid_episode.jsonl \
  competitions/arc-agi-3/fixtures/profile_stalled.jsonl \
  competitions/arc-agi-3/fixtures/profile_action_budget.jsonl
```

Directories are also accepted and expand to their immediate `*.jsonl` files. Every trace is validated before it enters the report; one invalid trace fails the profile instead of silently contaminating aggregate metrics. Use `--output report.json` for a durable report.

The profiler reports:

- success/failure counts and failure-class clusters;
- action and wall-clock utilization plus remaining headroom;
- the fraction of all actions spent in failed episodes;
- failures that terminate at or above 80% of their declared action or wall-clock budget;
- exact `state == next_state` transitions as a structural no-progress signal;
- action-type counts when an action object has a string `type` field.

The synthetic three-episode smoke produces 1 success / 2 failures, 7 actions total, a failed-episode action share of `0.714286`, one near-action-budget failure, and 3 exact no-progress actions.

## Compare a candidate against a baseline

```bash
python competitions/arc-agi-3/compare_arc3_runs.py \
  competitions/arc-agi-3/fixtures/compare_baseline \
  competitions/arc-agi-3/fixtures/compare_candidate \
  --fail-on-success-regression \
  --max-action-regression-pct 0 \
  --max-wall-regression-pct 0
```

The comparator validates every trace first, requires identical episode IDs, declared budgets, and initial states, then reports per-episode success/failure changes plus aggregate action and wall-time deltas. Optional thresholds make it usable as a submission preflight: validation errors exit 2 and a threshold breach exits 3.

The synthetic pair improves one stalled episode to success while reducing total actions from 3 to 2 and total wall time from 700 ms to 400 ms, so all zero-regression gates pass.

These measurements are descriptive diagnostics, not causal claims. In particular, a failed-episode action is not automatically a useless action, exact state equality is not proof that an environment interaction was semantically wasted, and lower action/wall counts are not sufficient evidence of a stronger policy. Feed real public-environment traces into the same schema before making policy or submission decisions.
