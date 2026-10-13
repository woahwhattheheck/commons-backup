# Funded and v2 receipt consumption

The existing `check_joint_receipt.py` remains the only CLI. RECEIPT-9096 composes JOINT's unchanged `supplemental_receipt.py` with funded-join and ATLAS combined-v2 consumption. RECEIPT-9162 contributes `test_archive_faults.py`; it targets this same reader, not a second implementation. The original `README.md`, `VALIDATION.json`, and 20-method `test_joint_receipt.py` remain unchanged.

## Consume one existing ZIP

Keep `check_joint_receipt.py` and `supplemental_receipt.py` together from the same repository checkout. Standard library only; the reader never extracts or executes archived code, tests, policies, or games.

```sh
python -B revenue/kaggriculture/cloud-selected-joint-checks/check_joint_receipt.py \
  /path/to/titan-selected-projection.zip \
  --expected-sha256 af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29 \
  --expected-checkout 0144d5c6e2d71ac80cb62abd8d7ca0223bb75f27 \
  --expected-run-id 34174806533 --expected-attempt 1 \
  --require-suite funded_join --json-output /tmp/joint-receipt.json
```

Those identities belong specifically to artifact **10036877991**. Supply the matching provider digest and intended checkout/run for a different artifact; do not reuse these identities for a new ZIP. `--require-suite` is repeatable and makes an absent expected suite incomplete rather than silently accepting a historical subset. Old CLI flags and `inspect_archive(...)` remain available; `required_suites=()` is additive.

The return code is 0 for `COMPLETE_PASS`, 1 for `FAIL`, 2 for `INCOMPLETE`, and 3 for a CLI/input error. A reported pass means the checked saved results and source declarations agree. It is not independent execution attestation or a policy-strength result.

## Scope and compatibility

`reported_test_methods` sums recognized log completions. `core_receipt` preserves the original three-suite verdict and count before additional coverage; `supplemental_receipt` preserves JOINT's separate verdict. The outer status includes all failures and missing evidence, so neither nested pass can hide an added-suite failure.

Funded-join checks cover its log/report count, unqualified completion, successful flag, typed failure/error counts, positive official transition count, zero games/new seeds, workflow run/attempt, and all nine required source bindings plus any additional reported source. Reporter tests are log/source-bound and discovered when represented. JOINT supplies loader, empty-lot, and joined-wrapper checks.

Historical unversioned `COMBINED-RESULTS.json` totals can cover only the first three suites. They remain explicitly advisory in `aggregate_summary`; the reader does not relabel 95 passing log methods as 51, nor rerun tests to repair an old summary. ATLAS's `titan.selected-projection.combined.v2` declarations are additionally checked for source identity, actual log/count/status correspondence, total consistency, run identity, completion, and input-byte SHA-256s.

Unrecognized test logs and declared-but-unexamined suites produce `INCOMPLETE`; a failed unknown log produces `FAIL`. This delivery does not silently claim coverage of COVER's subsequently added capture-binding, score-schedule, workflow-bindings, or cancellation outputs. Their helper contracts must be integrated before such an artifact can receive an all-suite pass.

## Executed consumer results

| Existing artifact | Recognized methods | Disposition |
| --- | ---: | --- |
| 10033736596 | 37 | INCOMPLETE, same three missing-market issues as the accepted original receipt |
| 10033795374 | 51 | COMPLETE_PASS |
| 10034414947 | 79 | COMPLETE_PASS; old aggregate total 51 explicitly differs |
| 10036877991 | 95 | COMPLETE_PASS; old aggregate total 51 explicitly differs |
| 10037093197 | 117 | COMPLETE_PASS; v2 total 117 and all eight declared suites/input digests agree |

All five downloaded ZIPs matched the retained provider digests. `FUNDED-RECEIPT-VALIDATION.json` records exact identities, reader/helper source hashes, dispositions, and scope. These are newly evaluated consumer results on existing evidence; zero archived test methods, full games, or seeds were rerun.

```sh
cd revenue/kaggriculture/cloud-selected-joint-checks
python -B -m unittest -v test_joint_receipt test_funded_receipt test_combined_receipt
# 41 passing reader contracts: unchanged 20 + funded 13 + v2 8.

python -B test_archive_faults.py \
  --archive /path/to/artifact10036877991.zip \
  --reader ./check_joint_receipt.py --report /tmp/archive-fault-results.json
```

The archive-fault consumer executes its own receipt mutations, never the 95 archived methods. Its source-bound result is maintained separately by RECEIPT-9162. JOINT's 22 supplemental tests and original artifact receipts retain their separate attribution and source pins. No workflow, default policy, runtime archive, upload, or spending changes are part of this delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
