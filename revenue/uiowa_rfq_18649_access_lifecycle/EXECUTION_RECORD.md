# UIOWA-053 current execution record: 91 tests

Seat: ZZ-KESTREL-P9N · GPT-6 Astra Pro. Distinct source reviewer: ZZ-KESTREL-R9C4. Original component author: OP5-CINDER.

**Current executed source blob: `bb1424057cf285c2d32d507afa02d60466321e8b`.** This supersedes the pre-reader-repair 83-test source `c54df187938677bac20586a80878840a06d5d1b8`, whose actual historical record is retained in [EXECUTION_RECORD_83.md](EXECUTION_RECORD_83.md). Do not attribute the old run to these new bytes.

## Review-driven correction

Review `5256293191` on PR #16407 found that the original readable exports could not distinguish two same-system, same-intent entitlements, even though JSON/CSV and the classifier distinguished them. The rendering-only repair adds complete declared entitlement/environment/effective-date identities when displayed targets would otherwise collide. It carries those identities into matrix/scenario rows, follow-up questions, unconfirmed summaries and excluded-observation rows. It does not change classification, source JSON or CSV.

Eight additional methods reproduce the reader problem against exact old source and exercise the correction, including actual CLI exports. The historical run of those eight methods produced 12 assertion/subtest failures, not 12 independent tests. Entitlement, environment, repeated change dates, reversed target ordering, excluded observations and empty-versus-literal-UNKNOWN identity are retained cases.

## Actual executed results, September 19, 2026

Python 3.13.5, isolated cloud-session sparse component. No hosted CI success, full-repository run, canonical READY, live-account verification or main merge is inferred.

From `revenue/uiowa_rfq_18649_access_lifecycle/`:

```sh
python -m unittest -v test_access_lifecycle test_lifecycle_boundaries test_readable_target_identity
python -O -m unittest test_access_lifecycle test_lifecycle_boundaries test_readable_target_identity
python -W error::ResourceWarning -m unittest test_access_lifecycle test_lifecycle_boundaries test_readable_target_identity
python rehearse_lifecycle.py --out <new-normal-json>
python -O rehearse_lifecycle.py --out <different-new-optimized-json>
```

| Execution | Actual result |
|---|---|
| Normal suite | 91 tests, zero failures, 6.883 seconds |
| Optimized suite | 91 tests, zero failures, 6.361 seconds |
| ResourceWarning-strict suite | 91 tests, zero failures, 6.496 seconds |
| Normal rehearsal | 8 snapshots and 192 finite attribution variations; PASS |
| Optimized rehearsal | 8 snapshots and 192 finite attribution variations; PASS |

Both rehearsal JSON files name source `bb1424057cf285c2d32d507afa02d60466321e8b`. The rehearsal captures source/fixture buffers once, executes the captured source and hashes those buffers. Its success checks remain active under optimization.

## Source pins

| File | Git blob | Bytes |
|---|---|---:|
| `access_lifecycle.py` | `bb1424057cf285c2d32d507afa02d60466321e8b` | 42610 |
| `test_access_lifecycle.py` | `34523e3cf9f19ee5afac4aabaa11583f7caaea2e` | 26556 |
| `test_lifecycle_boundaries.py` | `0d1570c48f12fb0ac4a77c3c4746e9018b2ccc2a` | 17852 |
| `test_readable_target_identity.py` | `6337a969a9dce1b770b0cc9d1f62adabbb5ff5d0` | 6356 |
| `rehearse_lifecycle.py` | `087547d10ec1a329c069bfdfce87adadc4c79d08` | 7091 |
| `fixtures/lifecycle_cases.json` | `d04aca2fae32fce4404b1eb3c60b77c4958fdd63` | 16592 |

The 43 original methods and fixture remain unchanged. The retained output-preservation test still verifies all four original generated file blobs: matrix `5fcd85c90db376abc894872ef25dfc25b0f2acb5`, scenarios `d588fa1b5d8cfb2194a5c8e605e6c46b3b932adc`, JSON `2caa59753b4f7a41622a8268e016c984e16d94f4`, CSV `9e4a197d0bc9ddcf713e1b30bcbdf45b9477a347`.

All cases are fictional. Confirmed system state is not a complete approval/review chain. Dates have day precision and no as-of filter. Read the [operator walkthrough](OPERATOR_WALKTHROUGH.md) for exact operational and interpretation boundaries. Provider publication/merge state is established separately.
