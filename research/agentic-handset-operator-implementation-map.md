# Agentic Handset Operator — implementation map

Status date: 2026-08-26
Source pin: [`woahwhattheheck/LocalDeviceAgent@9402ad8820dd447d6cc30b8eb4ff0f659d9cf13d`](https://github.com/woahwhattheheck/LocalDeviceAgent/tree/9402ad8820dd447d6cc30b8eb4ff0f659d9cf13d)
Method: read-only source survey through the authorized GitHub connector. No phone, emulator, Windows process, model inference, or host script was run.

This maps the mechanisms in the Agentic Handset Operator handoff to code that is actually present on the pinned repository head. `IMPLEMENTED` means a concrete runtime path exists in the pinned source. `PARTIAL` means a useful subset exists but not the full claimed mechanism. `GAP` means the mechanism was not found in the handset runtime; it is not an assertion that no local/unpushed artifact exists.

## Executive result

| # | Mechanism | Status | Short reason |
|---:|---|---|---|
| 1 | Model driver / translation layer | IMPLEMENTED | The orchestrator asks the model for one action; the accessibility service translates and executes it. |
| 2 | Efficient fused perception | PARTIAL | Element/state lists, exact text, marks, grid, OCR fallback, confidence-driven compute, and screen signatures exist. A fully fused structured world model and feature queue remain explicitly partial. |
| 3 | Self-routed operator layer with learned `Q(σ,u)` | GAP | No runtime operator object, operator-credit update, model-authored operator retention, or pre-mortem surface was found. Existing observation scores concern UI actions/targets, not reasoning operators. |
| 4 | Always-available action space | IMPLEMENTED | The action prompt exposes navigation, targeting, transfer, verification, drawing, conversation, and control verbs without objective-keyword admission. |
| 5 | Learning from ordinary use | PARTIAL | Observations, nav maps, clean-success playbooks, two-hit proof, strike demotion, freshness decay, and per-task negatives exist. The identical byte-level training contract and trained fast action head do not. |
| 6 | Useful typed failure | PARTIAL | Action outcomes, `[failure]` logs, retry/reorient, stopped-task resume offers, and `blind`/lost recovery behavior exist. A typed `z` taxonomy plus required owner remedy remains an explicit README TODO. |
| 7 | Executor-sovereign safety | IMPLEMENTED | Hard blocks and narrow confirmation live in `performActionJson`; emergency stop, caps, thermal/battery checks, and owner stop surfaces exist outside the model. |
| 8 | Reflex → surfaced operator reward guarantee | GAP | The code has behavior-triggered nudges/reflexes, but no general conversion of a reflex into a declinable scored operator because mechanism 3 is absent. The theorem is not itself a runtime mechanism. |
| 9 | Resource-aware model lifecycle | IMPLEMENTED | Strict idle release, `isGenerating` guards, wake-lock/task ownership, and deferred `closeSafely()` are present. |
| 10 | Reversible on-device parameter consolidation | GAP | Host-side exact-write/Muhlnickel tools exist, but no Android call path, idle consolidation controller, reward/coherence acceptance gate, per-edit handset journal, or app-side byte-exact revert self-test was found. |
| 11 | Owner values layer / bounded autonomy | PARTIAL | Owner primacy, explicit safety precedence, local activation, Learn mode, and no boot persistence exist. A first-class owner-values object, conflict-voicing path, and autonomous-goal envelope were not found. |

## Evidence by mechanism

### 1. Driver / translation split — IMPLEMENTED

- [`AgentOrchestrator.kt`](https://github.com/woahwhattheheck/LocalDeviceAgent/blob/9402ad8820dd447d6cc30b8eb4ff0f659d9cf13d/app/src/main/java/com/local/deviceagent/AgentOrchestrator.kt) (blob `165ba5a0e3d10b83bca66bb8fa4014a5a46bcd5d`) owns perceive → decide → act and calls `brain.decideNextAction(...)` before dispatch.
- [`AgentBrain.kt`](https://github.com/woahwhattheheck/LocalDeviceAgent/blob/9402ad8820dd447d6cc30b8eb4ff0f659d9cf13d/app/src/main/java/com/local/deviceagent/AgentBrain.kt) owns `decideNextAction()` and `makePlan()`.
- [`ActionAccessibilityService.kt`](https://github.com/woahwhattheheck/LocalDeviceAgent/blob/9402ad8820dd447d6cc30b8eb4ff0f659d9cf13d/app/src/main/java/com/local/deviceagent/ActionAccessibilityService.kt) (blob `340c4650e1a1f7213f3125fd8af8fe1c446d83b8`) owns `snapshotScreen()` at line 501 and `performActionJson()` at line 1075.

The deterministic layer still contains behavior-triggered reflexes and action repair. Those surface state or salvage malformed output; they do not replace the model's task choice in the surveyed path.

### 2. Efficient perception — PARTIAL

Concrete code:

- `snapshotScreen()` builds the interactive-node list and separate exact read-only text layer (`ActionAccessibilityService.kt:501–643`).
- Set-of-marks and the shared 8×12 `GridSpec` align visible badges with `tap_grid` (`ActionAccessibilityService.kt:23–26`, `900+`, `1864+`; `AgentBrain.kt:1066+`, `1157+`).
- Targeting supports element id, pixels/fractions, and labeled grid cells.
- `decideNextAction()` has an OCR fallback for accessibility-blind in-app screens and a graceful lean-image retry rather than dropping vision (`AgentBrain.kt:276+`, `313+`, `406+`).
- Model-supplied low/high confidence changes look/verification effort (`AgentOrchestrator.kt:361–380`; action prompt near `AgentBrain.kt:1490`).
- `PixelMap.kt` (blob `b669c6988d8f8749463371f43bc19ade4ef1df84`) provides pixel-change support.

Remaining gap is already acknowledged in the pinned README: the structured screen model is “partial,” the fused representation should become explicit, and the compact feature queue remains unfinished. This mechanism should not be reported as complete end-to-end.

### 3. Learned reasoning operators — GAP

Repository search found the operator concept in documentation but not a handset runtime implementation. There is no discovered type/state for `σ`, no `Q ← Q + λ(M-Q)` update, no model-authored operator admission rule, and no screen-relevant top-k operator surface or plan-time pre-mortem.

Do not mislabel `AgentMemory` observations as this mechanism: their hit/miss scores rank previously successful UI navigation steps and visible targets. They do not represent model-selected reasoning moves.

### 4. Always-available action space — IMPLEMENTED

`buildActionPrompt` exposes click/set/clear/long-press/scroll/swipe, id/pixel/fraction/grid targeting, open/back/home/recents/drawer/split-screen, search/find/copy/paste/read/get-text/device scan/zoom/OCR/reply, assert, draw/sketch, wait/ask/batch/done, and optional confidence. `performActionJson` parses, repairs, validates, gates, and dispatches the selected action.

The source comments explicitly state that tools are agent-chosen and not objective-keyword-gated. Malformed JSON is repaired or returned as usable failure feedback rather than counted as a silent task success.

### 5. Ordinary-use learning — PARTIAL

- [`AgentMemory.kt`](https://github.com/woahwhattheheck/LocalDeviceAgent/blob/9402ad8820dd447d6cc30b8eb4ff0f659d9cf13d/app/src/main/java/com/local/deviceagent/AgentMemory.kt) (blob `220f8f135302454e02fcd006539a73683093b08f`) stores completed playbooks, observations, screen signatures, and nav maps.
- Observations become `PROVEN` only after at least two clean hits and zero misses (`AgentMemory.kt:780–785`); a miss resets confidence and repeated misses drop the entry (`806+`).
- Proven memory loses its pin when stale and must be re-confirmed (`787+`).
- Successful playbooks remain model guidance that must adapt to the live screen (`408–423`), not blind executor replay.

Not found: a stable byte-level `(observation, action, outcome)` training contract shared with a fast action-head trainer, or an on-device training run that consumes it. The README still lists Function-Gemma/action-head work and training-objective design as future work.

### 6. Useful failure — PARTIAL

Present: `ActionOutcome`, action-level failure messages, `[failure]`/`[recover]` logging, accessibility-loss retries, loop/oscillation detection, reorient-from-live-screen, hard caps, and a stopped-task record that only resumes with the owner's say-so.

Missing: a closed typed reason vocabulary `z`, a durable reason field on every give-up, and a required owner-remedy field. The pinned README explicitly lists “Explicit failure taxonomy — classify navigation / visibility / permission / timing / recognition failures” as unfinished. `blind` and `lost` are operationally distinguished in several recovery paths, but not yet expressed as the claimed contract.

### 7. Executor safety — IMPLEMENTED

- Safety enforcement is in `ActionAccessibilityService.performActionJson`, not entrusted to model prose.
- Hard blocks include update/reset/wipe surfaces, external-assistant data exfiltration, on-device arbitrary code/terminal use under the default safety setting, and the agent's own repository.
- `NEEDS_CONFIRM` is intentionally narrow (payment and non-store install).
- [`AgentControl.kt`](https://github.com/woahwhattheheck/LocalDeviceAgent/blob/9402ad8820dd447d6cc30b8eb4ff0f659d9cf13d/app/src/main/java/com/local/deviceagent/AgentControl.kt) (blob `d16d0762f4e4c3b397c116a286974853e01a3544`) provides `emergencyStop()` at line 28.
- `AgentOrchestrator` enforces `HARD_STEP_CAP = 400` and `MAX_RUNTIME_MS = 20 minutes` on the current source; `AgentService.deviceSafetyReason()` owns battery/thermal stops.

Documentation contains older 60-step/5-minute wording, while current code and `CLAUDE.md` name 400/20 minutes. Runtime code is the measured value; the README line is stale.

### 8. Reflex → operator guarantee — GAP

The orchestrator has useful behavior-triggered reflexes (loop/bounce/drift/reply/reorient) that provide feedback and allow the model to choose again. That is compatible with the theorem's direction. However, there is no general reflex-to-operator conversion, learned operator score, or model-authored operator registry. This remains a design principle until mechanism 3 exists.

### 9. Resource lifecycle — IMPLEMENTED

- `AgentService` releases the model only after a strict idle check and confirms `!isGenerating()` (`AgentService.kt:90`).
- Task start cancels release and holds the resource through work.
- Critical memory pressure calls `closeSafely()`; the close is deferred while inference is in flight (`AgentService.kt:1262–1271`).
- `AgentOrchestrator`'s watchdog checks `brain.isGenerating()` and refuses to treat active generation as an idle wedge (`AgentOrchestrator.kt:90–102`).

This directly matches the claimed “never unload mid-task/mid-inference; deferred close; re-warm” mechanism.

### 10. Reversible parameter consolidation — GAP

The repository contains host-side exact-write/Muhlnickel artifacts including `host/titan_exact_write.py`, but source search found no reference from `app/src/main`. No Android service schedules an idle edit, no handset controller evaluates `Rσ` and `C`, no per-edit app journal is committed, and no app-side before/after/reverted checksum self-test is connected.

Therefore, host exact-write capability must not be reported as on-device Agentic Handset Operator consolidation. A future implementation must preserve the model-driver rule: candidate operators come only from owner use, acceptance is bounded and exactly reversible, and screen/external content cannot trigger the edit.

### 11. Values and bounded autonomy — PARTIAL

The current app strongly encodes owner primacy, explicit executor safety precedence, local owner-only activation, opt-in Learn mode, and intentionally no boot persistence. These are necessary pieces.

Not found: a first-class owner-editable values record injected into decision context, a specific “voice the conflict” response path, or a general autonomous goal envelope. Learn mode uses bounded harmless exploration, but it is not the full values mechanism.

## Smallest next build order

1. **Typed failure envelope first:** add a source-only `FailureReason` vocabulary and `{reason, evidence, owner_remedy}` record at task termination without changing device behavior. It closes a real observability gap and improves every later operator metric.
2. **Operator surface second:** represent a reasoning operator as model-authored text + applicability + measured outcomes; only rank/surface it. Never auto-fire it. Add the pre-mortem as another surfaced operator.
3. **Training contract third:** freeze the exact observation/action/outcome bytes and receipts before training anything.
4. **Consolidation last:** wire reversible edits only after the contract and operator scores are real. Keep it idle-only, journaled, and app-visible.
5. **Headless-emulator design remains separate:** first define what can be removed while preserving the same perception/action contract. Do not turn a headless harness into a scripted driver.

## Boundary

This is a pinned source survey, not an on-device test or patent certification. It does not certify the local Windows tree, any unpushed patent bytes, emulator behavior, or physical-device behavior. Bryce's phone remained benched throughout.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

