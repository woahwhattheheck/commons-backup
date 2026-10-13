# TITAN V4: replay feedback integrity

**Status: built and executed locally; NOT posted to Slack, committed, pushed, or merged.**
The session exposed read-only GitHub and Slack actions. This directory is an additive research delivery for the sole `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4` workspace. It is not another V4, a gameplay controller, a production install, or a new opponent policy.

## Finding

A fixed action tape can substantially overstate performance against the adaptive policy that produced it. Using the authenticated current native package as an opponent whose live policy is available, replacing its original starter rival with another native TITAN produces the following controlled comparisons. Margin is target-player terminal cash minus opponent terminal cash.

| Environment seed | Target seat | Native vs recorded native tape | Native vs live native | Replay minus live |
|---|---:|---:|---:|---:|
| 9922023 | 0 | +5,085 | +123 | +4,962 |
| 9922023 | 1 | +4,849 | -123 | +4,972 |
| 9922999 | 0 | +3,536 | 0 | +3,536 |
| 9922999 | 1 | +3,536 | 0 | +3,536 |

These are two seeds, both seats, and one known policy—not four independent samples, a population bias estimate, a leaderboard result, or a measurement of the entire assembled V4. Do not subtract these amounts from unrelated replay scores. They are counterexamples to identifying a replay opponent with its original adaptive policy.

For seed 9922023 / target seat 0, the taped opponent's actual step-0 WHEAT purchase costs 370 instead of the recorded 357. Its post-transition production state first diverges at step 150: the relevant shed FERTILIZER count is 0 instead of 1. This is not just a different final score: the same future action tape is now operating with different cash and physical inputs. The first town divergence is also retained, separately from private production. The diagnostic does not claim that the first witness alone explains the entire terminal-margin difference.

## Experiment and controls

Each seed/seat cell runs four complete official-interpreter games:

1. **Reference:** the current native policy occupies the opponent seat and plays the official starter. Both raw action streams and complete transition records are retained.
2. **Exact replay control:** both reference tapes are replayed against each other using the same engine, configuration, environment seed, and seat assignments. The complete before/action/after/market-receipt/status/reward trace must exactly reproduce the reference. Both audit reports must contain zero changed callbacks.
3. **Counterfactual replay:** the target starter is replaced by live native TITAN, while the opposing native policy's recorded actions remain frozen. Every changed input, actual receipt, and production-state witness is audited.
4. **Closed-loop comparator:** both seats execute the live native policy in independent workers, with the same per-role policy RNG assignments.

All eight exact replay controls—four cells in each audit mode—reproduced their reference traces exactly. All 32 completed game runs have 719 official transitions; 32 initializations are separate. The normal and optimized audit/engine runs have identical semantic hashes in every arm. There were 23,008 official transitions, 23,008 native-policy callbacks, and 5,752 starter callbacks in this sealed panel. The numerical equality between transition and native-callback counts is incidental to this four-arm design.

The original process-isolated `evaluate.py::Actor` is reused. **Native workers remain in normal Python mode even when the parent auditor/engine runs with `-O`.** This is not native-worker optimized-mode coverage. Native internal deadline fallback is not instrumented; complete worker responses must not be presented as proof of zero internal fallback. Actor shutdown exit codes are cleanup telemetry, not a replacement for per-call completion records.

Several exploratory bulk tool calls reached the tool execution limit. Only fully completed arms are included here. Final normal cells were rerun individually with the exact delivered source; optimized completed cells match them exactly. Additional preliminary games are excluded from the stated 32-run count. Reproduce one cell per process with the script below.

## What was built

`tape_integrity.py` provides strict engine/configuration binding, sequential raw tape consumption, detached action copies, per-seat transition comparison, and transparent actual-market receipt instrumentation. It neither repairs nor trims actions. Empty market rows retain their positions; unreachable suffixes, future fields, and extra hand rows remain intact. Missing/repeated/out-of-order/exhausted tape callbacks fail rather than receive implicit PASS actions.

`MarketRecorder` observes the official engine's actual `_commit_unit`, `_do_hire`, and `_do_buy_land` functions and restores them even on exceptions. It does not reimplement market pricing or order parsing. Receipt `attempts` means calls to those official functions, **not all raw requested rows or requested quantities**. An unsupported product request can be rejected before the commit function and therefore have no receipt. Actual filled units, successful hires/land purchases, and cash changes are reported separately.

The audit runs outside contestant workers. Diagnostic access to a seat's own recorded private state is not exposed to the opposing contestant. A corpus missing original private observations cannot certify full private-state replay fidelity; do not fabricate those observations or silently treat missing fields as a passing control.

`run_counterfactual_probe.py` is the four-arm diagnostic adapter around the existing Actor and official interpreter, not an alternative game model. `check_replay_integrity.py` exercises the pure audit contracts and full-engine behavior. `check_mutants.py` proves that deliberate audit defects trigger named behavioral assertion failures.

## Executed regression evidence

Python 3.13.5 on Linux, no network or new Actions dispatch:

- **43/43 tests in normal mode and 43/43 under `-O`; zero errors or skips.** Each mode includes 240 randomized full-interpreter instrumented/plain transition pairs and 770 interpreter invocations including initialization and focused cases. The complete state/environment and raw actions remain identical in each instrumented/plain pair.
- **Eight of eight deliberate defects rejected by named assertions in each mode**, not merely import failures or exceptions: raw-slot compaction, input aliasing, invented product fills, hidden production drift, overwritten first witness, repeated callback acceptance, invented hire fills, and reversed cash signs.
- Both-seat engine witnesses cover unaffordable and unsupported buys, partial fills, successful/failed hires and land purchases, raw empty-slot caps, the minimum-one market slot, floor sales, and extra ghost PLANT rows. The last case confirms that trimming nonexistent hand actions can alter real actors' atomic seed validation.

These checks validate this diagnostic, not every upstream TITAN regression or an integrated V4 release. The randomized engine fixtures are constructed tests, not a natural-engagement corpus.

## Exact input custody

The native input was recovered from existing Actions artifact **10175943272**, not a newly dispatched workflow.

```
artifact ZIP SHA256  3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8
native archive      b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9
SOURCE.json SHA256  e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2
engine Git blob     3c202c7ee921da239356789e266b694635103fc4
evaluator SHA256    e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c
```

All 109 runtime-map members are authenticated before execution. The evaluator also verifies the pinned engine, specification, utilities, and loader. Final GitHub readback still identified b567 as `runtime/integrated-selected/CURRENT-ARCHIVE.json`. The numerous unassembled repairs on canonical main are deliberately **not** represented as part of this tested archive. Production/default/config/archive/Kaggle were untouched.

## Reproduce on the existing isolated worker host

The delivery does not redistribute the native package. `NATIVE` must be an already extracted, authenticated b567 package with `SOURCE.json`, `main.py`, and `checks/reference/`. The runner fails closed on different bytes.

```bash
# From this research directory; output is separate from the native input.
python check_replay_integrity.py --native "$NATIVE" --report "$OUT/tests-normal.json"
python -O check_replay_integrity.py --native "$NATIVE" --report "$OUT/tests-optimized.json"
python check_mutants.py --native "$NATIVE" --output "$OUT/mutants-normal"
python -O check_mutants.py --native "$NATIVE" --output "$OUT/mutants-optimized"
./reproduce.sh "$NATIVE" "$OUT/panel"
```

`reproduce.sh` runs each cell in a fresh foreground process. It starts no service, schedule, network request, workflow, or competition submission. Results include source hashes, complete terminal outcomes, raw-action preservation diagnostics, first witnesses, per-arm trace hashes, and explicit limitations. Timing/resource fields need not match across repetitions; semantic trace hashes should.

`RESULTS.json` seals the measured findings. `EVIDENCE.json` identifies 84 evidence files by size and SHA256. The ZIP's separate `evidence/` directory contains normal-mode full reference corpora, both modes' complete arm summaries, component logs, and all mutation logs/reports. Optimized reference corpora are omitted as redundant; their full semantic hashes match the normal controls. The source-only patch includes the evidence manifest and result receipt, while the ZIP carries the larger raw evidence.

## Consumption and ownership

This complements COHORT's paired-result schema/ranker and SQUALL's adaptive adversarial profiles. It does not replace them or claim their data. Riot's actual top-30 corpus and newest composed V4 were not available to this session, so this result is **not** a declaration that their measured gauntlet margins have a particular bias.

For a replay-driven benchmark, retain replay scores as fixed-action scenario results, preserve the original replay control, record actual fills and trajectory drift, and use available live policies for closed-loop comparison. The module is ready to be consumed by that existing evaluator without altering a gameplay controller. Publishing and integration remain uncompleted in this session because write actions were not exposed. No duplicate build demand or remote claim was posted.
