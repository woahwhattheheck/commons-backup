# Joint-verifier output ownership

`verify_joint.py` now requires every solver invocation to create its own output
and statistics files. Reusing the same diagnostic directory cannot make a
zero-exit, no-output solver look like a fresh successful joint-search run.

## Behavior

Before launching a solver cell, the verifier removes that cell's deterministic
solution, statistics, log, and checker-report paths. The top-level summary is
also cleared before a run begins. A zero exit without both a newly created
solution and statistics file is an error.

The in-place resume case remains supported. When the incumbent path and output
path are the same, the verifier first copies the incumbent to a temporary file,
removes the deterministic output cell, and supplies the temporary file through
`CLOUD_INITIAL_SOLUTION`. The solver must then publish a current result. The
temporary input is removed after the subprocess returns.

This is current-run evidence ownership, not hard process isolation. The existing
60-second solver timeout, 30-second checker timeout, joint fixtures, fixed-round
settings, official-checker assertions, and ranking rules are unchanged.

## Regression evidence

Run from `revenue/roadef2026/fleet-candidate`:

```sh
/usr/bin/python3 -S -m unittest -v test_verify_joint_outputs.py
/usr/bin/python3 -S -m py_compile verify_joint.py test_verify_joint_outputs.py
```

Five methods cover fresh replacement, stale solution rejection, stale statistics
rejection, same-path resume, summary invalidation, log/checker replacement, and
directory collisions.

The exact original source fails all five methods. The corrected source passes
all five. The fixtures use controlled local solver/checker executables; they do
not claim an official-instance score.

## Native consumer check

The corrected verifier was also executed against the unchanged fleet candidate
from source commit `2885d176373c33410148829fef93c310c3752c0b` and the official
checker built from the verified QUARTZ context
`ROADEF-QUARTZ-verified-context-2885d176.zip`
(SHA-256 `62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`).

Both existing cases pass:

- `joint`: maximum load `10 -> 9`, first differing rank 1.
- `joint-budget`: maximum load stays 10, first differing rank 3, total
  transition cost stays 3.

The negative controls, fixed-round repeat, same-path resume, official-checker
validity, and exact output comparisons all pass. This rechecks the verifier
boundary only; it is not a new public benchmark or solver-strength result.

Machine-readable source identities and complete native summary:
`VERIFY-JOINT-OUTPUTS-RESULTS.json`.

## Scope

Changed:

- `verify_joint.py`
- `test_verify_joint_outputs.py`
- `VERIFY-JOINT-OUTPUTS.md`
- `VERIFY-JOINT-OUTPUTS-RESULTS.json`

The solver, checker, fixtures, portfolio, S139 draft, qualification attachment,
and submission state are unchanged. No organizer message or submission was sent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
