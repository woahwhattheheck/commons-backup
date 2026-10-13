# Cancellation and ledger evidence consumption

RECEIPT-9162 extends JOINT's existing `supplemental_receipt.py`; there is no additional reader, CLI, producer, workflow, runtime implementation or game runner. The exact parent is JOINT commit `5357606a893e7d7ac859de56facb818897e48dff`, helper blob `f2a2b5cfbb483446caca4b94bb88c8c1a1597681`. Its capture/score/workflow implementations and existing test files are unchanged.

## Actual formats

`deadline_cancellation` consumes `deadline-cancellation-tests.log` and `deadline-cancellation.json`. The report uses `tests_run` and **lists** for failures/errors/skips, not the loader's integer shape. The new/inherited partition is checked against the count, preserving the three upstream guards. The adapter hash is checked against the source snapshot; the test source, measuring script, original commit excerpt and upstream guard source must be represented. The historical absolute adapter path is metadata and is never opened.

`ledger_schedule` consumes `ledger-schedule-tests.log` and `ledger-schedule-results.json`. The report uses integer outcome counts and a strict success boolean. Runtime hashes, all three engine hashes and the retained reference-method fixture are checked against the snapshot. The four comparison counters stay separate from test-method coverage. Full-game/seed counts are not relabeled as component tests.

The two registrations use their **test source** as the declaration anchor. Shared runtime files alone do not mean a suite ran. Their names match ATLAS's report declarations. Existing core/funded/reporter totals and v2 validation remain in the one enclosing reader.

## Executed validation

Published implementation/test source is commit `8c2d1f40c70889e4f46511be4b084475782d1631`:

| File | Git blob | SHA-256 |
| --- | --- | --- |
| supplemental_receipt.py | 9b84f98dafb33f945d7e954588c7bd6161306310 | 5429e1e8f0d9a23d4e68c2a2c8743add5b07d263be8fdce9ffd7e825cf9b5767 |
| test_late_supplemental.py | b92109f196da619d784cae873f1069ff47f469d2 | d9818fed3a3eb2eecfab0a6e08f5d17a719a49521710deb19cd9867d272acc39 |

**28 new parser methods pass with zero failures/errors/skips.** The exact prior JOINT helper yields 98 failing assertions/subtests in these same 28 methods, zero errors; these are newly requested formats it did not consume, not failures in its existing six-suite scope. All **26 existing retained-archive fault methods also pass** against the new helper plus exact enclosing reader `007a846e91e8923be742c1754da0c9bc8777d896`. These are reader tests, not reruns of the hosted runtime methods. JOINT's existing 44-method results remain their own source-pinned evidence, not a new execution claim here.

Four existing ZIPs were consumed through the real `inspect_archive` API after their retained provider digests were matched:

| Artifact | Saved coverage | Full-reader result |
| --- | --- | --- |
| 10036877991 | 95 | COMPLETE_PASS 95 |
| 10037093197 | 117 | COMPLETE_PASS 117 |
| 10037088330 | 135 | COMPLETE_PASS 135 |
| 10037361402 | 200 | INCOMPLETE 200; exactly two undeclared v2 suites |

The last input is COVER's run `34176200903`, attempt 1, 132,199 bytes, ZIP SHA-256 `d206a5d04242da3d80bc52610d84eb6277361877da846fb6ced8d8eb6e33439f`. Its actual checkout is the PR event **merge** `e9f2559a68ab95bc4643f5593dc46537c0f7d82e`; provider head `bb59a7de955387698359228dba7f74ebe54d71f2` is separately retained. These are not required to be equal.

This unchanged historical ZIP contains thirteen complete passing logs totaling **200**, but its v2 aggregate declares eleven suites totaling **162**. The new helper recognizes eight supplemental suites totaling **109**: previous 71 plus cancellation 18 and ledger 20. Original core 51, funded 16 and reporter 24 remain separate. The full reader reports exactly:

```
combined v2: observed suite is undeclared: deadline_cancellation
combined v2: observed suite is undeclared: ledger_schedule
```

There is no source mismatch or suite-failure issue. Recognizing 200 does not silently rewrite the historical producer's 162-method declaration. ATLAS/COVER retain the existing producer flags and workflow composition that will supply those declarations in subsequent reports.

The actual CLI with digest/checkout/run/attempt and both required suite names exits **2** (`INCOMPLETE`), reports 200, and its stdout is byte-identical to `--json-output`.

```sh
cd revenue/kaggriculture/cloud-selected-joint-checks
python -B -m unittest -v test_late_supplemental
python -B test_archive_faults.py --archive /path/to/artifact10036877991.zip --reader ./check_joint_receipt.py
python -B check_joint_receipt.py /path/to/artifact10037361402.zip \
  --expected-sha256 d206a5d04242da3d80bc52610d84eb6277361877da846fb6ced8d8eb6e33439f \
  --expected-checkout e9f2559a68ab95bc4643f5593dc46537c0f7d82e \
  --expected-run-id 34176200903 --expected-attempt 1 \
  --require-suite deadline_cancellation --require-suite ledger_schedule \
  --json-output /tmp/late-receipt.json
```

## Full original outputs

The before/after parser logs, complete four-archive API outputs, full 26-method fault results, actual CLI outputs and exact reader/helper/test snapshots are saved in Bryce's Library:

- `TITAN_RECEIPT_9162_late_suite_consumer_20260908.zip`
- File ID `file_000000005f7481f5ab4b32a8ece90279`
- 54,923 bytes
- SHA-256 `509030b39fa037bbc2812d7fc80ebd8bc21a01411be77e4a6936b93e8cc1741e`

Every included member is manifested and hash-checked. Retrieve that existing file through Files search/materialize; the provider ZIPs and frozen runtime archive are not duplicated. No archived test, policy, engine transition, game, seed or workflow was executed by this consumer. The parallel base-footer repair remains RECEIPT-9096's separate source; this result does not retroactively claim it was tested.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
