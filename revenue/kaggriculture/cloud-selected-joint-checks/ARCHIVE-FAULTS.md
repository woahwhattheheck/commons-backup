# Retained-archive fault consumer

This is RECEIPT-9162's independent consumer of the existing joint reader, composed on RECEIPT-9096's shared branch. It adds no reader, aggregate producer, workflow, game runner, policy, or source exporter. JOINT owns `supplemental_receipt.py`; RECEIPT-9096 owns the base-reader and funded/aggregate integration. Original reader evidence and tests remain unchanged.

## Input and invocation

Use the already-existing GitHub Actions artifact **10036877991**, run **34174806533**, attempt **1**, checkout **0144d5c6e2d71ac80cb62abd8d7ca0223bb75f27**. The downloaded ZIP is 120,855 bytes with SHA-256 `af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29`. The script requires these exact ZIP bytes, not a repack. `GitHub.download_workflow_artifact` is an existing working intake route; no new export or workflow execution is needed.

```sh
python -B revenue/kaggriculture/cloud-selected-joint-checks/test_archive_faults.py \
  --archive /path/to/artifact10036877991.zip \
  --reader revenue/kaggriculture/cloud-selected-joint-checks/check_joint_receipt.py \
  --report /tmp/archive-fault-results.json
```

The reader under test is an actual local source file selected by `--reader`; no archived code is imported or executed. The tests read the original ZIP and create detached evidence copies with precisely one fault each. They calculate new local fixture digests for those copies. Those digests are not provider receipts. An existing baseline summary problem cannot satisfy a negative case: the mutation must produce a new problem, and a stale provider digest cannot explain it.

The input contains seven completed suite logs: original seller 16, projection 21, market 14, loader 7, empty lot 15, ordered wrapper 6, funded join 16; total **95**. Its historical combined report still says `total_tests=51`. A reader must keep that stale summary separate from the actual represented suite results. Source files bundled in a snapshot do not by themselves contribute executed test counts.

## Executed baseline and exact source

The published test source is 12,546 bytes, Git blob **3978dcf50edfe43312683dae3108839bbdae7421**, initially published at **5f3ed19663657614cc3b9badd33f07ccb3a93e74**, then composed unchanged on the shared branch at **154e902a5a9fc1fd1535097ab7327fb26ee8d5c3**.

Against the exact original reader blob **47c15bde5301dd18dea1a0a9cfcab8ad3ec829dd**, **26 reader test methods ran, with 31 failing assertions/subtests, zero execution errors and zero skips**. The unmodified archive returns `COMPLETE_PASS` and 51 reported methods under that reader's original three-suite scope. That old result does not inspect the four added suites. The greater number of failures than methods is due to the two parametrized log tests, not extra hosted methods.

The fault cases cover failed/truncated added logs, log/report absence, funded report count/status/scope, funded runtime/test/engine source identity, run/attempt identity, missing snapshot source, qualified or ambiguous completion, and an unrecognized test log. Positive controls check the 95-method total, inert unexecuted source, and zero rerun/game/seed counters.

Exact JOINT helper blob **f3b0562221cc1ef81ad0e95f3a6145474c44ac8b** was also consumed directly on this unchanged 95-method input. It reports its intended **28 supplemental methods**, `COMPLETE_PASS`, no problems, and a core-plus-supplemental subtotal of **79**. That separate helper intake is preserved, rather than relabeled as funded coverage.

## Composed result: 26 of 26 pass

The exact shared implementation at **1b297a9048a3d6a9d085840bda9c5a126343477f** was independently materialized and checked against its Git blob before execution:

| Source | Git blob | SHA-256 |
| --- | --- | --- |
| `check_joint_receipt.py` | `007a846e91e8923be742c1754da0c9bc8777d896` | `8bcce19f859c43cea0aedbe1c548a52e623eb72b0d4c23df91193bcd18f1e008` |
| `supplemental_receipt.py` | `f3b0562221cc1ef81ad0e95f3a6145474c44ac8b` | `08f5d5c81a580dc9616c1fd4d5127a8b7cdef8206228d35026348d7a23a86dda` |
| `test_archive_faults.py` | `3978dcf50edfe43312683dae3108839bbdae7421` | `56b2c5d48a360ca0f4608ea8e2b0e8c0c7a282fac6f2c10ef1058e3f3f7aba0f` |

**All 26 methods pass, with zero failures, errors or skips.** There are 33 API evidence reads including controls, not 33 hosted tests. The composed reader returns `COMPLETE_PASS` and **95 methods**, retaining original core **51**, JOINT supplemental **28** and funded **16** separately. Its aggregate summary explicitly records declared total 51, recognized total 95, `total_matches_recognized=false` and `authoritative_for_suite_verdicts=false`.

The actual command-line reader was also executed with all four expected identity arguments and `--require-suite funded_join`. It exits **0**, returns `COMPLETE_PASS95`, and its stdout is byte-identical to `--json-output`. This exercises the real CLI, not an adapter or a replacement parser.

## Durable original outputs

`ARCHIVE-FAULTS-RESULTS.json` provides compact source-bound metadata. The complete original and composed JSON outputs, full unittest logs, CLI outputs, helper intake and exact source snapshots are saved in Bryce's Library:

- File: `TITAN_RECEIPT_9162_archive_faults_20260907.zip`
- File ID: `file_00000000555481f5ac8017bafebb5908`
- Size: **49,198 bytes**
- SHA-256: `a0435575a10839075fd544a24b96961948d777727b9a408e32255364af09f1e5`

Retrieve that existing file with Files search/materialize by its exact file ID. Its manifest verifies every included source and evidence member. The 95-method input ZIP and frozen policy archive are intentionally not duplicated; they remain available through the existing GitHub artifact.

Only the 26 reader regression methods execute. The archived 95 hosted methods, engine transitions and games are **not rerun**. This is validation of evidence consumption, not gameplay strength, source promotion or whole-repository CI. The single ordinary reader PR/main integration remains RECEIPT-9096's publication scope.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
