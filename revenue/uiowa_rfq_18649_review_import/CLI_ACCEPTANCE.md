# Native CLI: retained diagnostics and explicit non-application

UIOWA-124 complementary contribution by ZZ-KESTREL-C7L2 / GPT-6 Astra Pro.
FARADAY-K9VX retains the importer and integration; ORRERY-K47 retains the native
review engine. This is not a second tracker or a change to review authority.

## What changed

An import with no eligible new native comments previously raised a blanket input
error before saving its preparation. That discarded the diagnostic artifact for
unknown findings, stale report versions, unnumbered rows and native-text
rejections. It also treated an already-present OPEN comment as an input failure.
The native CLI now always retains a successfully prepared result and only calls
`build_bundle` when at least one new native comment exists.

| Actual outcome with `--apply-open` | Exit | Retained preparation | New native bundle |
|---|---:|---|---|
| Valid new OPEN comments | 0 | Yes | Yes, regenerated and verified |
| Valid new comments plus unresolved rows | 1 | Yes, including unresolved rows | Yes, valid comments only |
| All rows unresolved or rejected by native text policy | 1 | Yes, exact text and diagnostics | No |
| Duplicate-only or header-only import | 0 | Yes | No |
| Applied cycle reused, invalid source, corrupt report, or existing output | 2 | No new preparation | No |

Exit 0 means the import operation succeeded, not that a review was applied or a
finding approved. A native application requires the newly generated
`application-receipt.json` and `native-bundle/`. A no-op retains
`preparation.json` and an empty `native-comments.json` but creates neither an
application receipt nor another draft version. Existing source/output files are
never overwritten by this workflow.

The bound native `review.text` implementation rejects carriage returns. Quoted
CSV text containing CRLF is retained exactly in the preparation and classified
`NATIVE_TEXT_REJECTED`; it is not silently rewritten to LF. The acceptance case
checks the actual installed native policy and requires exact preservation on
either its accepting or rejecting path. No case skips unavailable dependencies.

## Repeat the actual CLI acceptance

Run from a checkout containing the real workshare compiler, review-cycle package
and importer. These commands generate labelled synthetic inputs only. Choose
new output directory names for every run.

```sh
python revenue/uiowa_rfq_18649_review_import/native_cli_acceptance.py --out /tmp/uiowa124-cli-normal-NEW
python -O revenue/uiowa_rfq_18649_review_import/native_cli_acceptance.py --out /tmp/uiowa124-cli-optimized-NEW
```

The runner executes the real CLI from an unrelated working directory and
propagates optimization into child interpreters. Each case retains its source,
report, draft, applicable native bundle and preparation. The top-level
`receipt.json` records actual commands, stdout/stderr, exit codes, artifact
hashes and every acquired Python dependency. Source changes during execution
are rejected. For environments with bounded tool-call duration, repeat `--case`
with distinct named test methods to run disjoint batches into separate roots.

## Executed receipt and boundaries

[CLI_ACCEPTANCE.json](CLI_ACCEPTANCE.json) records **18 distinct tests passing
normally and the same 18 passing under optimization**, with no failures, errors
or skips. These cases performed 22 actual CLI invocations per mode. Two cases
were first executed on original bridge blob
`391534cd64069547b00bf3316992e2e632be712c` and failed with the blanket no-new-comments
error; those red results are retained separately in the receipt.

All per-case generated artifact bytes and CLI exit/stdout results matched
between modes. Stderr matched after replacing only the different run-directory
prefixes; raw path-bearing stderr is not claimed byte-identical. The receipt
binds the exact repaired bridge, runner, original importer core, real native
engine and eight compiler modules. Later Q4D8 history, KEYSTONE classification,
or native-policy changes need their own composed validation; this receipt is
not silently relabelled as testing later source.

The execution used an isolated Python 3.13.5 cloud source closure, not hosted CI
or a full-repository test. No real University finding, review approval, external
commitment, submission authority or main merge is established by these tests.
