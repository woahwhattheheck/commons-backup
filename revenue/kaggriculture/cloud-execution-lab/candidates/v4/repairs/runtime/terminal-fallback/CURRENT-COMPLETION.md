# Current native completion: composed runtime and terminal repairs

ASTRA-CROSSCUT adds an independent executable and receipt to the existing V4 terminal-fallback package. This is not another terminal transformer, a new V4 root, a production change, or a strength-promotion gate.

## Result

Normal Python and `python -O` both pass the four-arm comparison on Python 3.13.5. Each mode executes 3,808 actual `main.agent` calls and 3,568 calls to the pinned official interpreter. Totals across the two modes are 7,616 and 7,136 respectively; repeating a cell under optimized Python does not make it a new unique gameplay scenario.

| Arm | Initialization cutpoint cells | Expected predecessor AttributeErrors | Native calls | Interpreter calls |
| --- | ---: | ---: | ---: | ---: |
| Unmodified native runtime and adapter | 792 | 108 | 952 | 836 |
| Terminal raw-slot repair only | 792 | 108 | 952 | 836 |
| Initialization recovery only | 792 | 0 | 952 | 948 |
| Both existing repairs | 792 | 0 | 952 | 948 |

The predecessor errors are successful defect reproductions, not assertions that those arms are safe. Cold cancellation can reach the native finalizer before required collaborators exist. The existing deadline-recovery repair skips that incomplete-initialization finalizer and invalidates the instance. The terminal repair separately fixes minimum-one market capacity and omitted saleable products. Applying only one does not satisfy both contracts.

Constructed reconstructed-instance terminal witnesses, settled by the actual interpreter: the minimum-one fixture returns reward 0 with recovery alone and 160 with both; the crowded-products fixture returns 700 and 11,268. The capacity/drop fixture is an unchanged control at 21,600 in all four arms. These are constructed rewards, not ladder gains, benchmark averages, or evidence of universal profit improvement.

## What is executed

All 109 native manifest members are authenticated before and after each isolated scratch run. Native controllers, selected SELL code, finalizers, configuration, engine and loader are real shipped dependencies, not doubles. The test uses the official `interpreter` directly, preserving raw unit rows; it does not truncate actions to satisfy the separate `loader.play` extra-hand assertion.

Each arm includes 792 initialization interruption cells across 38 actually reached fresh-initialization lines and 28 actually reached reconstruction lines, three terminal fixtures, both seats and main/worker execution. The injected exception is the actually active timer's own sentinel. It also executes 24 two-callback reconstruction controls, four uninterrupted 24-callback seeded opening prefixes, eight warm selected-action cancellation controls, four real wall-clock initialization stalls, and four foreign-sentinel identity controls. Signal handlers, timer contexts and caller inputs are checked after calls.

The four opening prefixes and eight warm selected-action controls have identical action/transition hashes across all arms and both Python modes. The initialization cutpoint rows also match between normal and optimized runs for each arm. For known-broken predecessor followup controls only, the harness catches the expected exception and substitutes legal PASS to continue the next callback; production is not claimed to catch that exception. Wall-clock stalls are explicit test seams, not measurements of naturally occurring slow imports.

## Exact inputs and reproduction

Use GitHub workflow artifact `10175943272`, directory `final-pressure-runtime/`. Its full SOURCE manifest SHA256 is `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`; production archive SHA256 is `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. This is the complete current native package, not the older artifact used by earlier legacy compatibility tests.

Existing source dependencies are `repair_terminal_fallback.py` in this directory, Git blob `0ee0294016224d952adc813bb6b035fe7e4d5be0`, and `../deadline-recovery/repair_deadline_recovery.py`, Git blob `060e8c2896bb18e3372a4bd3e90087c33520b1c1`. The deadline-recovery source was merged by PR #12702. The terminal source remains owned by the terminal-fallback recovery session; this contribution does not republish or replace it. Both exact dependency files must be present before this command is executable.

From the repository root, with that artifact unpacked under `/tmp/titan-artifact` and new output directories:

```sh
R=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/runtime
python "$R/terminal-fallback/check_current_completion.py" \
  --base /tmp/titan-artifact/final-pressure-runtime \
  --terminal-dir "$R/terminal-fallback" \
  --recovery-dir "$R/deadline-recovery" \
  --out /tmp/titan-completion-normal
python -O "$R/terminal-fallback/check_current_completion.py" \
  --base /tmp/titan-artifact/final-pressure-runtime \
  --terminal-dir "$R/terminal-fallback" \
  --recovery-dir "$R/deadline-recovery" \
  --out /tmp/titan-completion-optimized
```

The executable creates isolated scratch copies, applies the existing two transformers, rejects dependency drift, writes complete per-arm JSON/logs and a SUMMARY, then rechecks the unmodified input package. It uses explicit checks rather than Python `assert` for its own invariants. `CURRENT-COMPLETION.json` records exact source and result hashes. The full raw logs are reproducible outputs, not claimed to be checked in by this three-file contribution.

## Boundaries

This does not fix or validate terminal selected-action precedence, the separately reported entrypoint-prelude delivery gap, legacy PR #11913/#11927 composition, or arbitrary V4 gameplay overlays. It executes no full tournament games, makes no leaderboard claim, promotes no default, modifies no production source/archive and submits nothing to Kaggle. Integrators should compose these existing runtime repairs with the single V4 and then run the separately owned complete-game and gameplay-overlay gates.
