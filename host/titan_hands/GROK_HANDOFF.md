# Grok handoff: TITAN Hands inherits LDA

## Owner ruling

The Android hand is the owner's existing LDA build, not reference material for a parallel executor. TITAN adds
the MCP/ADB transport, Windows adapter, headless emulator, and cross-target delta surface. New Android behavior
belongs in the Kotlin translation layer first.

## Governing design inherited from the handset-operator patent

- The model is the driver; deterministic code translates perception and actuation without choosing the goal.
- The normal path is compact structured perception; pixels/vision are an explicit slower path.
- Actions remain broadly available and model-chosen; malformed actions become useful corrective feedback.
- Perceive -> decide -> one action -> re-perceive is the loop, with change detection and honest verification.
- Operator/world-model learning credits mechanisms that cause measured progress.

These are already concrete in the owner's Kotlin. Do not reimplement them in Python.

## Exact inherited seams

| Capability | Owner implementation TITAN calls |
|---|---|
| Compact numbered perception, paging, exact values, marks | `ActionAccessibilityService.snapshotScreen()` |
| Forgiving native action language and retargeting | `ActionAccessibilityService.performActionJson()` |
| Reliable text targeting | `set_text` branch and `setInputText()` |
| Semantic click/scroll plus gesture fallback | `click()`, `scroll()`, `tapAtPoint()`, gesture helpers |
| Pixel change signal | `PixelMap` |
| Learned actuator preference | `ShellInput.noteA11yRefusal()` / `preferShell()` |
| Observe-decide-act, verification, useful failure | `AgentOrchestrator` |
| World-model/operator learning | `WorldModel`, `ReasoningOperators`, `MechanismRouter` |

`TitanHandsReceiver.kt` is intentionally thin: base64 JSON over an explicit ADB broadcast, then direct calls to
the two owner seams above. `host/titan_hands/lda_bridge.py` only transports and normalizes that result for MCP.
`host/titan_hands/android.py` selects `lda-kotlin` first and retains the prior UIAutomator road as fallback.

## Build and proof

### Current source-tree status

The source-version skew is repaired from the owner's real `Desktop/LocalDeviceAgent` tree at
`4eab3d2fef8a9d44e202fcc48b874be955368db2`. Commons now contains the 21 inventoried semantic differences and
seven source-only tests/resources from that clean `app/` tree, including the complete `SettingsManager`,
`AgentMemory`, `TaskHistory`, owner UI surfaces, pinned LiteRT/coroutines dependencies, and Shizuku support. No
replacement stubs or parallel operator were introduced.

The normal owner build remains arm64-only. `-PtitanHandsAbi=x86_64` is the isolated colony-emulator override;
`install_lda_emulator.ps1` supplies it automatically and refuses physical devices by default.

Verified on the headless AOSP API 34 emulator:

- `:app:compileDebugKotlin` and `:app:assembleDebug` completed successfully;
- the APK installed and the strict receiver probe returned `accessibility_ready=true`;
- live observation returned `implementation=lda-kotlin`, source
  `ActionAccessibilityService.snapshotScreen`, and the native numbered screen;
- native action `{type: click, id: lda:1}` returned `CONTINUE`, summary `clicked element 1 (Wait)`, and changed
  the semantic digest from the system dialog to nine Launcher nodes.

```powershell
powershell -File host/titan_hands/setup_android_headless.ps1 -AcceptSdkLicenses
powershell -File host/titan_hands/start_android_headless.ps1
powershell -File host/titan_hands/install_lda_emulator.ps1
powershell -File host/titan_hands/register_codex.ps1
py -3 -m unittest discover -s host\titan_hands\tests -t .
```

Use `install_lda_emulator.ps1 -SkipBuild` to reinstall and re-run the strict service-ready probe against an
already assembled APK. It fails rather than overclaiming success if the accessibility service does not bind.

Then start a fresh Codex task, call `hands_capabilities(target="android")`, and require
`implementation=lda-kotlin` before testing native actions. Observe first; use the `[N]` element from the LDA
screen; act; observe again; require exact semantic evidence rather than trusting an action-return boolean.

## Useful next work

1. Add a receiver operation for the LDA's optional marked screenshot so `hands_capture` can return the same
   Set-of-Marks visual rather than a raw ADB framebuffer.
2. Carry the LDA world-model transition credit into the shared TITAN delta receipt so Android and Windows learn
   from the same screen -> action -> screen evidence.
3. Port LDA target-retargeting and post-action verification patterns into the Windows adapter without narrowing
   either platform's action space.

Do not create another Android executor, do not make UIAutomator primary again, and do not attach a personal phone
unless the operator supplies its exact serial. Purchased colony devices are explicit targets.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP / Wire tip→live. Submit/YouTube wait Bryce exact go.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

