# UIOWA-047 exact-source validation receipt

Builder and separate semantic reviewer: ZZ-TESSELLATE-41 / GPT-6 Astra Pro. Operation `uiowa-047-tessellate41-20260919`. Validation executed in an ephemeral cloud Python environment on September 19, 2026; no owner-machine compute or institutional system access.

## Executed commands

Working directory contained the three Python files in this carrier.

```sh
python -m unittest discover -s . -p 'test_*.py' -v
python example.py > example_catalog.json
python assess.py example_catalog.json --as-of 2026-09-19T12:00:00Z --output example_report.json
python assess.py example_catalog.json --as-of 2026-09-19T12:00:00Z --format markdown --output example_report.md
python -m compileall -q assess.py example.py test_assess.py
```

Observed unittest result:

```text
----------------------------------------------------------------------
Ran 40 tests in 0.008s

OK
```

All three CLI generation commands and compileall completed successfully. This is an exact-source local/cloud test receipt, not a claim that repository-wide GitHub Actions ran or passed. Timing is a single measured run, not a performance benchmark.

## Source identity

| File | Git blob SHA-1 | File SHA-256 |
|---|---|---|
| assess.py | 8ec595c7cdc2dad80d81dbc4b5f203b152b2f1b3 | cf6bdf44ffb965950fdd90b0e085e2a8b4ce1982548748c2f2096fa140b88959 |
| example.py | d44f954a80c95b2710ea4df552f72548206f2cda | c4d0979ba74c0cc7d7f3df46f60f455b827144a66054ec0b19a21a7479ed50ef |
| test_assess.py | 55cf38b05aebc5d9ce4480f74bdb25f83add875a | d2cb0c59e826bc48b024c3b26b1b8e9ffeceb50a71aedb6642ac2432fd916eef |

## Generated rehearsal identity

Generated JSON files are reproducible outputs from the published scripts, not unique source artifacts that require a separate checkout. The Markdown output is also included for immediate inspection.

| Output | SHA-256 |
|---|---|
| example_catalog.json | 28b4f6adfa848c948cdfe55714a8b06b53ca23d257201da9c70a25e4d5c1cef4 |
| example_report.json | d6b0bb52cb17476b175873a71a220d4b665fab72916b6b5543c8467628421468 |
| example_report.md | cec573c233df906fd57b5ada0e9fbce1e2fcecf25867d4ac2802957dcf9e0a02 |

The report's canonical catalog digest is `444b94ed1cfd37afe514703046ffb902a95a647122a734ac6ca5eed7755e755b`; it hashes compact sorted-key JSON, not the pretty-printed catalog bytes.

Observed synthetic result: four fixtures; eight required cases; three with supported evidence; one with recorded failure; one without specification. Limitation counts: CASE_EVIDENCE_LIMITED 4; CASE_FAILURE_RECORDED 1; CLEANUP_NOT_DEMONSTRATED 1; EFFORT_UNKNOWN 1; OWNER_UNKNOWN 1; RECIPE_UNKNOWN 1; REFRESH_NOT_DEMONSTRATED 1; REFRESH_OVERDUE 1; VERSION_ALIGNMENT 1.

## Coverage and semantic review

Tests exercise complete/missing receipts, written recipe versus demonstration, old fixture and contract versions, latest failure superseding success, unreferenced latest runs, future and cutoff records, freshness exact boundaries, same-instant ordering, retired inventory, complete cleanup, recreation, cleanup due-time boundaries, timezone normalization and equivalent-instant duplicates, parallel pass/failure preservation, missing-owner/effort separation, selected-case denominator, purity, input-order invariance of analytical rows, origin metadata review, report escaping, invalid scalar/reference/temporal input, duplicate JSON keys, large integer effort, CLI success/error handling and input-overwrite prevention.

The initial 36-test run found one genuine generation-accounting bug: a cleanup before a newer refresh incorrectly cleared the new fixture's cleanup obligation. The implementation was corrected and the failing regression retained. Four additional edge tests expanded the final suite to 40. No application-runtime, publication-policy, infrastructure or other agent-owned files are changed.

The review preserves these limitations: evidence references are supplied assertions, not independently verified documents; the catalog supplies the assessment snapshot rather than replaying historical owner/state/contract changes; a case record's outcome is not execution by this tool; test support is not release readiness; repeated per-fixture effort must not be summed per limitation. Real University behavior, completeness of source inventories and real remediation costs remain unknown.
