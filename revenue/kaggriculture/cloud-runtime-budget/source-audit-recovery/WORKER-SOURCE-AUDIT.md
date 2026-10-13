# Preserve worker results when the final source audit fails

## Recovery status

Recovered by BRIDGE from FINCH's Library packet on September 8, 2026. FINCH's packet explicitly said it had been prepared and executed locally but was **not posted to Slack, committed, or merged**. Current main was independently checked before this recovery and `profile_saved.py` is still the packet's exact base Git blob `031f14ba3e15dd438f248a58a5f1143fc45f0d4b`.

The exact isolated production hunk is in `source_hunk.patch`. This directory makes the handoff durable; it does **not** claim that current production has adopted the hunk. Apply it through the existing profiler owner after current-source revalidation. DELTA's separately merged timeout/non-UTF8 supervisor work remains distinct.

## Reproduced boundary from FINCH's original packet

`worker()` catches an actor/import exception and starts constructing its report. Its final source inventory then calls `source_rows(source_root)` outside a handler. An ordinary filesystem error at that point escapes and prevents the report from being written. A real subprocess fixture replaces an inventoried `.py` file with a directory and raises `RuntimeError('primary actor failure')`. The original worker exits with the secondary `IsADirectoryError` and no report. Through the existing supervisor, the meaningful actor error becomes `MissingChildReport`.

The controlled filesystem change is a test fixture, not evidence of a prior corrupted TITAN run. It contains no game, network request, account operation, or private-data access.

## Small production change

Catch `OSError` only around the **final** source inventory. Preserve the original actor/import error, all recorded calls, timing records, and available action hashes. Record the additional failure as `source_audit_error`; use `sources_unchanged=null` because the final inventory is unknown, not verified unchanged. A successful actor followed by this audit failure becomes a failed worker report with `SourceAuditError` and exit 2. A pre-existing primary error stays primary.

Healthy reports retain the previous fields and semantics. Readable-but-changed sources still report `sources_unchanged=false`; no audit exception is invented. External `BaseException` cancellation still propagates. No retry is added. The existing supervisor, loaders, input parser, factory/arity selection, and timing observer are unchanged.

This does not make report writing transactional or guarantee recovery if the output filesystem itself is unwritable. It does not catch every possible finalization error or freeze transitive dependencies.

## FINCH's inherited executed acceptance

The same twelve new regression methods ran against baseline and repaired source. Baseline: twelve failed assertions/subtests across eight methods, zero errors. Repaired: twelve methods passed, zero failures/errors. Cases cover complete calls, original body/factory errors, four OS-error forms, sampled profiling, initial audit failure, healthy reports, readable source drift, external cancellation, real filesystem changes, and the actual two-process supervisor. The two-process primary-error fixture keeps exactly one failed actor invocation per worker; the original exception and nonzero exit survive.

Fifty retained compatibility methods also passed. FINCH recorded that the containing command hit its 45-second execution limit after forty-four completed methods; only the six unfinished methods were run in the continuation and the exact union was recorded. No incomplete command was presented as an uninterrupted fifty-method result. Later peer timeout/output methods were not counted as newly executed by FINCH.

One additional real-source compatibility check used the existing PR9997 archive `95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153` and the first three recovered WIDEFIELD observations. Baseline and repaired profilers each used ordinary/instrumented fresh actors: twelve total policy calls, zero game/interpreter calls. All opening actions and selected diagnostics matched the recorded actions and each other; all seventeen runtime Python files remained unchanged. Sequence hash: `01d386f18334aff20d655957af0d7ea9d3994730b6d7c3908efa0eb002113fd5`. This is a short compatibility fixture, not a new full-prefix timing or strength result.

These executions and attribution remain FINCH's. BRIDGE has not rerun them and does not add their counts to any later profiler evidence.

## Original packet

The complete original patch, including FINCH's twelve-method regression source and note, remains in Bryce's Library as `TITAN_FINCH_worker_source_audit.patch`, file ID `file_00000000fb9881f7a7d5ba082a7a00f6`. This repository recovery stores the exact isolated production hunk needed for ordinary source composition while retaining that packet as the full test/evidence source.

No current release, game runner, timing helper, canonical archive, games, seeds, workflow, upload, or spend are changed by this recovery directory.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
