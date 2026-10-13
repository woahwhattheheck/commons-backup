# Preserve verifier timeout evidence

This follow-through composes on PR10303's current-run output ownership fix. It does not change any solver, checker, objective, time allowance, fixture, or submission artifact.

`verify_joint.py` previously used `subprocess.run(..., timeout=...)` for both the solver and official checker. `TimeoutExpired` is raised before the subsequent log/report writes, so captured stdout/stderr could disappear even though the verifier correctly stopped. The verifier now writes the bytes already carried by that exception before re-raising the same exception:

- solver timeout: existing `<case>.log` receives exact captured stdout+stderr bytes;
- checker timeout: existing `<case>-checker.json` receives exact partial stdout and new `<case>-checker.log` receives exact stderr;
- `<case>-timeout.json` records stage, requested timeout, exact byte lengths, and SHA-256 digests.

All deterministic evidence cells, including the new timeout/checker-log cells, are cleared before a run. A stale sidecar therefore cannot be attributed to a new invocation. Normal successful execution follows the same source path as PR10303, aside from writing checker stderr to its dedicated log. Timeout handling re-raises the original `subprocess.TimeoutExpired`; it does not retry, extend a budget, score a partial result, or treat a timeout as a valid outcome.

## Focused execution

`python -B -m unittest -v test_verify_joint_timeout.py`

Four methods pass: solver timeout stream/receipt preservation, checker timeout preservation after a successful solver, byte/text normalization, and stale timeout-sidecar replacement. The solver/checker programs are controlled subprocess-boundary fixtures; this is not an official-instance benchmark, Docker result, or competition-strength claim.

Source base: merged PR10303 verifier. The stale-output ownership semantics from that PR are retained unchanged. S139 qualification remains unsent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
