# Competition submission ledger

`submission_ledger.py` is a small append-only guardrail for competition submissions. It prevents a newer run from silently replacing a stronger known final submission.

Each submission record stores the platform submission ID, exact artifact SHA-256, configuration, score direction, public score, and timestamp. Final-slot changes are separate append-only events.

## Slot policy

- `protected-best` is monotonic by default: a replacement must have a strictly better finite public score in the configured direction.
- Other slot names, such as `exploration`, may rotate independently when a competition allows multiple final selections.
- An intentional protected-best downgrade requires `--allow-regression`; the override is recorded in the ledger.
- Submission IDs cannot be reused. Record a new ID for every platform submission.

The ledger does **not** submit to Kaggle, DrivenData, HackerRank, or any other platform. It protects local selection state only.

## Example

```bash
python research/competitions/submission_ledger.py record \
  --ledger research/competitions/arc-agi-2.submissions.jsonl \
  --competition arc-agi-2 \
  --submission-id 334273 \
  --artifact-sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --direction maximize \
  --public-score 0.6937 \
  --config-json '{"model":"v3.1","seed":7}' \
  --recorded-at 2026-10-05T22:00:00Z

python research/competitions/submission_ledger.py select \
  --ledger research/competitions/arc-agi-2.submissions.jsonl \
  --competition arc-agi-2 \
  --submission-id 334273 \
  --slot protected-best \
  --reason "best known public score" \
  --selected-at 2026-10-05T22:01:00Z
```

A worse later score is rejected from `protected-best` and leaves the ledger unchanged. An `exploration` slot can still point at that newer run.

## Focused verification

```bash
python research/competitions/test_submission_ledger.py -v
```

The five focused tests cover immutable submission IDs, maximize/minimize monotonicity, exploration-slot rotation, and explicit audited regression overrides.
