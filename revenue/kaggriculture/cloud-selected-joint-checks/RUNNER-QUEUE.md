# Runner and queue-copy receipt consumption

RECEIPT-9162 extends the existing supplemental reader to consume the five suites delivered by STRESS-JOIN PR10143 and HAZEL-CI PR10150. The existing enclosing `check_joint_receipt.py` API and CLI, prior suite handlers, producer, workflow, canonical runtime and release archives are unchanged.

## Contracts

| Suite | Methods in the retained artifact | Evidence |
| --- | ---: | --- |
| stress_runner_boundary | 20 | stress-runner-boundary-tests.log and stress-runner-boundary.json |
| stress_runner_existing | 2 | stress-runner-existing-tests.log |
| stress_runner_reporter | 13 | stress-runner-reporter-tests.log |
| queue_copy | 23 | queue-copy-tests.log and queue-copy-results.json |
| queue_copy_reporter | 14 | queue-copy-reporter-tests.log |

The new 72 methods join the previous 210, producing 282. The three upstream guard methods already belong to cancellation coverage; the runner subset contributes only its two remaining methods. `test_runner.py` was already bundled by the cancellation suite, so its source presence alone does not declare that the separate runner subset executed. Its actual log or an enclosing required/declaration check establishes that scope.

The boundary runner report has list-valued failures/errors/skips and `actual_source=false`. This preserves the hosted twenty-method scope without importing the three separate local actual-state methods. Runner, adapter and test hashes are matched to the snapshot. The queue-copy report has `methods`, `passed`, integer outcome fields and an embedded original unittest log. Both its embedded and outer completion must agree; comparison counters are not test-method counts. Unknown future suite logs remain unexamined rather than acquiring a pass.

## Executed source

Code checkpoint: `186ed45257c513711aa7ffdd47469b884ab6e060`.

| File | Git blob |
| --- | --- |
| supplemental_receipt.py | aebe5d01a65133833a3b2792f9e849bde2f833e5 |
| test_runner_queue_receipts.py | d9f2f174162ecd699621a763cd2861f4a25e5c9c |
| check_runner_queue_archive.py | 770b1ff86f8efb20e360f60953c9f958c1d75afa |
| unchanged check_joint_receipt.py | 0cc4b4ab6b3db350b06ec24bd63068b13ae17946 |

The helper is an additive extension of `9b84f98dafb33f945d7e954588c7bd6161306310`. Full SHA-256 identities and output metadata are in `RUNNER-QUEUE-VALIDATION.json`.

## Validation results

**32 new unit methods and 9 new actual-archive methods pass**, with zero failures/errors/skips. The changed composition also passes the **28 retained late-format methods and 26 retained archive-fault methods**. These are 95 distinct reader/consumer methods, not a rerun of the 282 hosted runtime methods.

The actual-archive negative controls remove the aggregate report before making detached mutations, then supply locally calculated fixture digests. A stale aggregate input digest therefore cannot mask a missing semantic check. All five added logs are tested for failure or absence; runner hashes, mode, scope and outcome arrays are altered separately; queue hashes, count, success and embedded-log faults discriminate. The shared-source-only control remains COMPLETE_PASS210, and an attempted five-method runner subset is rejected instead of double-counting the cancellation guard methods.

The unmodified HAZEL artifact is **10039313918**, run **34182300969**, attempt **1**, 141,039 bytes, SHA-256 `fe33a36cebf521ee4188609fc68a1739c68bbbb26e99f9ef87e3b7abbe91000b`. Its actual tested event-merge checkout is `fc2c8a3b515d771c5b918ad3476d916d2ca801e9`, separate from provider PR head `b903585df40ae86edef6b79292e42a5a6700a506`.

Before the extension, that ZIP returned INCOMPLETE210 with five unknown logs and five unexamined v2 declarations. The new reader returns **COMPLETE_PASS282, zero problems**, with all eighteen declarations and required input digests checked. Supplemental181, original core51, funded16 and reporter34 are kept distinct. The actual CLI with all five new suites required exits0; stdout is byte-identical to its JSON output.

Six saved artifacts were read through the same real API: 95, 117, 135, 210 and 282 retain COMPLETE_PASS at their own source identities. Historical200 remains INCOMPLETE200 with exactly its two undeclared cancellation/ledger issues. No historical report was rewritten or relabeled.

```sh
cd revenue/kaggriculture/cloud-selected-joint-checks
python -B -m unittest -v test_runner_queue_receipts test_late_supplemental
python -B check_runner_queue_archive.py --archive /path/to/artifact10039313918.zip --report /tmp/runner-queue-faults.json
python -B test_archive_faults.py --archive /path/to/artifact10036877991.zip --reader ./check_joint_receipt.py
python -B check_joint_receipt.py /path/to/artifact10039313918.zip \
  --expected-sha256 fe33a36cebf521ee4188609fc68a1739c68bbbb26e99f9ef87e3b7abbe91000b \
  --expected-checkout fc2c8a3b515d771c5b918ad3476d916d2ca801e9 \
  --expected-run-id 34182300969 --expected-attempt 1 \
  --require-suite stress_runner_boundary --require-suite stress_runner_existing \
  --require-suite stress_runner_reporter --require-suite queue_copy \
  --require-suite queue_copy_reporter --json-output /tmp/receipt-282.json
```

## Complete evidence

The original logs, all saved-artifact API results, actual-archive mutations, CLI outputs and exact source snapshots are saved in Bryce's Library as `TITAN_RECEIPT_9162_runner_queue_20260908.zip`, file ID `file_00000000895081f581aeb92bed901ce2`. Size 104,774 bytes; SHA-256 `cf2aab27627e90fec973dc2ee15fb8680e7861594b4d036b843794d6f20d8fe4`. All 26 payload members are manifested and hash-checked (27 ZIP members including the manifest). The provider ZIPs and frozen runtime are intentionally not duplicated.

This is evidence-consumer implementation and execution, not independent attestation of hosted execution, policy strength, canonical package acceptance or whole-repository CI. No archived method, producer, engine transition, game or seed was executed; no workflow dispatch, release or provider upload was performed. Current BIRCH/COVER workflow additions remain separate until their actual source and output contracts are consumed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
