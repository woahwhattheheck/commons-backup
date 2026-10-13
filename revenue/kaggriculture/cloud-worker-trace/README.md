# Worker deadline trace compatibility repair

Operation: `titan-worker-trace-lines-20260908-01`. Consumer: WIDEFIELD / T08.
This directory publishes an additive, tested patch and standalone checks. It does
not replace the canonical runtime, rebuild CURRENT, or create another TITAN.

## Repair

A previous tracer can disable `frame.f_trace_lines`, suppressing the worker
guard's cancellation checks in Python loops. The patch restores line events for
the guard while preserving the previous tracer's event preferences, callback
replacement/clearing, exception identity, and suspended-generator state. It also
retains a fast path when no caller tracer exists. Only worker enter/trace/exit
methods change; main-thread signal handling and controller/fallback logic do not.

Target: `revenue/kaggriculture/cloud-execution-lab/reference/titan-current/deadline_adapter.py`.
Fresh-main compatibility was checked at `1a4c1da3f5caa0f832de5b2e1773bc8583b69cec`:
its blob `184ff5354451d764df95ffb5c952eecd0f4266f0` exactly matches the original
validated source. Baseline SHA256 is
`6e677016ac93350a5eb0b6f3345fb94726e78d5416d20bb81e7e5bc8ffdc8da2`.
Patched SHA256 is
`7f70a25dfb703f50aa83cd281a9722d575571da1073e605c5927fc35453ab486`
(15,458 bytes; Git blob `664aa4f8a21368c388dfa6714406519b6535ef7f`).

## Reproduce without modifying a working runtime

Run from a checkout containing the verified base commit:

```sh
lab="$PWD/revenue/kaggriculture/cloud-worker-trace"
target=revenue/kaggriculture/cloud-execution-lab/reference/titan-current/deadline_adapter.py
work=$(mktemp -d)
mkdir -p "$work/$(dirname "$target")"
git show "1a4c1da3f5caa0f832de5b2e1773bc8583b69cec:$target" > "$work/$target"
python3 -B "$lab/trace_compatibility_check.py" \
  --source "$work/$target" --report "$work/baseline.json"
# Expected baseline result: 23 tests, 9 failures, nonzero exit.
git -C "$work" apply --check "$lab/worker-trace-lines.patch"
git -C "$work" apply "$lab/worker-trace-lines.patch"
python3 -B "$lab/trace_compatibility_check.py" \
  --source "$work/$target" --report "$work/candidate.json"
# Observed candidate result: all 23 pass.
sha256sum "$work/$target"
```

These are deliberately invoked standalone CLI checks, not pytest-importable
modules. The adjacent `probe_trace_flags.py` is required. Linux / CPython 3.13.5
was tested. A subprocess watchdog bounds the muted-loop cases; opcode comparison
includes a reference-only priming call to avoid cold instrumentation differences.

## Evidence and limits

The publication rerun reproduced 9 baseline failures and 23 candidate passes,
zero errors. `VALIDATION.json` binds source, test, patch and completed-report
hashes. The outer combined shell call reported a timeout, but both complete JSON
reports and final unittest summaries were retained; its exit status is not
presented as a successful receipt.

Earlier retained evidence comprises six reset-controller entrypoint calls per
arm with identical actions and all 80 frozen runtime files unchanged. Those
calls were not rerun for publication. No full games, seed reservations, strength
claim, hosted-loss attribution, or broad latency claim are added. Raw game
observations/actions and private runtime evidence are deliberately excluded.

The trace guard cannot interrupt a native call until Python execution resumes
and does not protect against deliberate `sys.settrace(None)` in the guarded
body. Preserve the external whole-call timeout. Provider interpreter parity was
not tested. Full integration/repackaging remains with WIDEFIELD/T08; reconcile
any newer target blob instead of overwriting it. Patch and check code are
Apache-2.0, consistent with the existing source SPDX and repository license.

The original conversation bundle's not-published status is historical. Actual
GitHub publication/merge and Slack delivery receipts belong to the publishing PR
and the T08 thread; this document does not claim canonical consumption.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
