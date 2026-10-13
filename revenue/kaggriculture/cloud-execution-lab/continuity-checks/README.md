# Frozen-control continuity: retained consumer evidence

This directory completes source delivery of the existing CONTINUITY claim
1788835596.563439. It does not introduce another TITAN runtime or submission.
The four prepared checker, input-control, pin and result files are preserved
byte-for-byte from the retained delivery package.

## Result and limits

The historical PR10144 frozen control, `TitanAgent(Features(seed=False))`,
matches the original persistent `SellScheduler` on all four retained DELVE
SELL prefixes: two already-exposed development seeds, both seats, 719 decisions
each. The detailed saved reports contain 2,876 action/state pairs, 5,752 actual
parent calls across candidate and reference, four candidate initializations,
and zero recorded discrepancies. The checker compares complete actions,
planned/pending/previous/harvest/diagnostic state, full parent state, caller-input
preservation, one producer call and persistent ownership after every decision.

Nine checks per pair are 25,884 assertions, not 25,884 independent experiments.
The four streams are two seed regimes, not four independent strength samples.
A separate saved 12-method input-boundary run passed. Rehashed corrupt streams
are rejected; modifying rival-private observations and rival current actions
does not change the actor-input packets.

This is the reachable nine-file closure at PR10144 merge
`4f743f8ec29bddc36220b2169a2609fe159776e2`, not current-main runtime, enabled seed
recovery/funding, main.py loading, complete-package, timing, gameplay or hosted-CI
proof. Source pins deliberately prevent silently treating later code as this
historical result. The one current TITAN package remains with its existing builder.

## Publication recovery

The retained `TITAN-CONTINUITY-handoff.zip` is 339,569 bytes, SHA-256
`5c929bf071537681c2ea47af4d28e413d3ee2f9b2ea88368e9e31d9cdc01d520`.
Recovery readback verified all 30 manifested members, all nine source hashes,
each of the four complete 719-row reports, every row's nine true checks,
parent/initialization counts and each compact result's detailed-report digest.
The existing input-control log reports 12 completed methods with OK.
No policy, engine, game, prefix or timing experiment was rerun for this delivery.

The original attempt record is retained: an outer tool interruption discarded
one unsaved cell report; only that missing cell was rerun during the original
work. Completed-cell counts do not include inferred progress from that attempt.
The previous branch/file attempts did not create a branch. This publication uses
an explicitly created branch and ordinary PR; completion requires its actual
merge/source readback, not the earlier handoff wording.

## Reproduction

Reuse the preserved historical runtime directory from the continuity evidence
package, or obtain the nine files listed in SOURCE-PINS.json from the exact
PR10144 source. Do not point this historical pin file at the evolving current
runtime and then bypass the mismatch.

Input is the existing Library `TITAN-DELVE-funded-seed-evidence.zip`, file ID
`file_000000008fe481f58309a3cfde721385`, SHA-256
`aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`.
Its 218 manifest members are verified before policy execution.

```sh
python -B check_frozen_continuity.py \
  --runtime /path/to/preserved/runtime \
  --delve-archive /path/to/TITAN-DELVE-funded-seed-evidence.zip \
  --output /path/to/new-evidence

python -B check_input_controls.py \
  --delve-archive /path/to/TITAN-DELVE-funded-seed-evidence.zip
```

`--cell` selects one exact retained cell, allowing a missing cell to be run
without repeating completed ones. Existing per-cell output paths are not
overwritten. The worker has a 90-second outer timeout; run cells separately
when the enclosing harness has a shorter aggregate time limit. That timeout
is not an agent performance claim.

The checker runs two persistent actual policies in one fresh subprocess per
cell, uses the retained evaluator RNG settings, counts call events without
replacing method bodies, and verifies sources before and after execution.
Only public/own observations and configuration are passed to the actors;
recorded expected actions are comparator labels, not actor arguments. Detailed
per-action hashes/logs remain in the private evidence package; this directory
publishes only source and the compact source-bound result.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
