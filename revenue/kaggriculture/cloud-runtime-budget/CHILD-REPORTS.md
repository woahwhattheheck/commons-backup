# Saved-profile child-report recovery

Operation: `astra-delta-profiler-child-report-recovery-20260908-01`.
Consumer: the existing FINCH/TRACE saved-observation profiler used to measure the
next exact TITAN artifact. This is not a second profiler, policy, or integrator.

## Reproduced behavior

Baseline `profile_saved.py` is the source-binding repair already landed by PR10118,
Git blob `51319f112497720f19403c26da549143fb0a0a39`. A real subprocess writes the
10 bytes `{"status":`, prints to stdout/stderr, and exits 7. The existing supervisor
raises JSONDecodeError after that first child, before retaining its log or the
final summary. Its malformed child file remains, but the process diagnostics do
not reach a usable result.

The repaired source classifies this exited child's output as `process_error` /
`InvalidChildReport`, preserves the raw bytes separately, retains stdout/stderr
and exit 7, finishes both separately planned modes without retrying either child,
and writes a final summary with false instrumentation parity and supervisor exit 2.
The retained malformed bytes have SHA-256
`29c4ee76f0ca251d68310ac4b2467307746fbab53504dbd80417aee62b6a6bad`.
This is a constructed process-transport witness, not a game or actor evaluation.

## Change and limits

The new local helper `read_child_report` is called from the existing supervisor.
It recognizes missing/unreadable files, invalid JSON or encoding, wrong root or
status shapes, malformed call rows, nonfinite values, and excessive JSON nesting.
The fields used by the supervisor's next-mode selection are checked before use;
the eventual finite JSON encoding is checked before rewriting a valid report.

Invalid returned bytes are retained using exclusive create at
`<basename>.<mode>.invalid.bin`. Their path, byte length, and SHA-256 are included
in the normalized error record. The supervisor's existing-output check includes
these raw files, so a repeated basename cannot replace earlier evidence. Valid
actor-error payloads retain their original status/error, and valid complete
reports retain their existing fields and parity checks.

This preserves diagnostic evidence from exited children with malformed reports.
The pre-existing timeout handling is unchanged; universal recovery from storage
failure, process launch failure, or concurrent filesystem mutation is not claimed.
The helper is transport recovery, not a complete proof of report authenticity.
The loaded-source importer, worker, timing boundaries, policy calls, and native
TRACE inputs are unchanged from PR10118. No historical report or running panel is
rewritten, and no game, seed, upload, paid compute, or owner-PC action was used.

## Executed checks

Python 3.13.5 in isolated cloud execution. The final nine-method new suite on the
exact baseline reports 8 failed assertions and 17 errors across its subtests;
the process returns 1. The identical suite on the submitted source passes all
nine methods. It includes real subprocesses for truncated and invalid-encoding
files, malformed object/call shapes, NaN/overflow metadata, deeply nested JSON,
missing reports, original actor errors, coherent transport fixtures, and
pre-existing raw-output preservation. One child per mode is asserted.

The 41 prior profiler/native-input/source-binding methods pass unchanged on the
same final source. Thus **50 distinct methods pass across two test invocations**:
9 new recovery methods plus 41 existing methods. Compilation passes. AST comparison
against the baseline finds only `supervise` changed and `read_child_report` added.
The separately retained final-source witness preserves both exact raw files,
both logs, both original exit codes, and the final failure summary.

Run all focused methods from the repository root:

```sh
D=revenue/kaggriculture/cloud-runtime-budget
PYTHONPATH="$D" python -B -m unittest discover -s "$D" -p 'test_*.py' -v
```

Final source blob: `8ae01c736bd44ffc424f91f657c2861126115d24`.
Final test blob: `0f7b1cacba615b614ae2b93833c53a87bd6567df`.
Source and test commits: `f8bb52aaa268ec6ce2648fd390443e78bc9689ed` and
`c210f0c3d9ffa7b3fecd797a0aba7a02c516f2b0`.
Focused local tests are separate from hosted guards and full-repository CI.

FINCH retains the profiler, TRACE the recorded-input work, and TANDEM the timing
observer. PR10118's direct-source binding remains intact. Existing TITAN integration
and profiling owners can consume this same CLI at the merged revision on their
next ordinary invocation; no new consumer wrapper or competing build is required.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
