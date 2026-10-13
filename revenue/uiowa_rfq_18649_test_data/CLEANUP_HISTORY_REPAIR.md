# Preserve completed cleanup across later attempts

Operation: `uiowa047-cleanup-completion-history-osprey-r2-20260919`.
Repair: ZZ-OSPREY-86C1-CLEANUP-R2 / GPT-6 Astra Pro.
Original implementation: ZZ-TESSELLATE-41, [PR #16208](https://github.com/woahwhattheheck/commons/pull/16208).

## Reproduced defect

In the fictional regression, refresh succeeds at 08:00, a case run succeeds at
09:00, cleanup succeeds at 10:00, and a cleanup retry fails at 11:00; cutoff is
12:00 UTC on 2026-09-19. Before adding the retry, the original assessor reports
`ACTIVE_AFTER_CLEANUP` and zero supported cases. Adding only the failed retry
incorrectly restores one supported case and clears all limitations, without
any recreation or new application run.

The repair separates the latest cleanup attempt from the last demonstrated
successful cleanup and recreation. A failed or unbacked attempt does not undo
an earlier completed lifecycle transition. A subsequent evidenced recreation
changes the generation, but supporting a case still requires a new,
version-aligned post-refresh run. Tied cleanup/refresh timestamps do not prove
subsequent recreation. The completion diagnostic cites the completed cleanup;
`latest_cleanup_at` remains the latest attempt for compatibility.

Input/output schemas, opaque-reference semantics, timezone/cutoff rules,
existing latest-refresh failure treatment, and the original example are
unchanged. No fixture material is created or deleted, no network is used,
and no real institutional findings are inferred.

## Replay

From the repository root:

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_test_data -p 'test_*.py' -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_test_data -p 'test_*.py' -v
python -W error::ResourceWarning -m unittest discover -s revenue/uiowa_rfq_18649_test_data -p 'test_*.py' -v
```

The new test module contains the complete fictional input builder and explicit
cases for retry failure, unbacked events, recreation, stale case runs, retained
cleanup obligations, cutoff equality, timezone equivalence, input order,
unrelated fixtures and non-mutating CLI output. Its independent chronological
state machine checks 343 event histories at three cutoffs (1,029 comparisons),
while production selects the last demonstrated transitions. This is a finite
model comparison, not an exhaustive proof over all possible catalogs.

## Executed evidence

On Python 3.13.5 / Linux x86_64 in the ephemeral cloud source subset:

- Normal: 64 test methods pass.
- Actual `python -O`: 64 test methods pass.
- ResourceWarning as error: 64 test methods pass.
- Negative control against original assessor: 24 new methods produce 91
  assertion/subtest failures; these are not 91 independent methods.
- Existing example: JSON structures equal and 4,494-byte Markdown identical.
- Fresh-directory patch application and exact source-blob verification pass.

Published source identities equal those exercised:

| File | Git blob |
|---|---|
| Repaired assess.py | `1ca0dca80e711b8f900d9bf2f89286aced6111cc` |
| test_cleanup_history.py | `8ee92bc210de5765f3d498709540a540116ef0e9` |
| Unchanged example.py | `d44f954a80c95b2710ea4df552f72548206f2cda` |
| Unchanged test_assess.py | `55cf38b05aebc5d9ce4480f74bdb25f83add875a` |
| Original assess.py | `8ec595c7cdc2dad80d81dbc4b5f203b152b2f1b3` |

[Machine-readable execution record](cleanup_history_execution.json) includes
exact source bindings, reproduction outputs and raw-log digests. Local
execution is not represented as repository-wide or GitHub Actions success.
Provider review, execution and merge states belong to the PR receipts, not
this source document.

## Review

GPT self-review: the repair follows the existing supplied-event model and
preserves original API/schema behavior. No independent reviewer identity is
claimed here. Physical recreation and current case evidence remain distinct:
a successful wrong-version refresh may change physical cleanup state but
cannot pass the independent version-alignment gate. Later failed refreshes
still deny current case support. Original upstream attribution and the
separate fixture-companion/identity-exporter work remain untouched.
