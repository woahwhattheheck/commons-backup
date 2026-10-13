# Agentic handset operator — selective reconciliation

This is a tracked-source comparison, not a filesystem dump. Build products, model files, archives,
local properties, device state, and untracked work are outside the comparison by construction.

- Commons: `94db2d956719de86345995dcbd092bf5073ba146` under `lda/`
- Source: `4eab3d2fef8a9d44e202fcc48b874be955368db2`
- Scope: `app/build.gradle`, `app/src/main`, `app/src/test`, `build.gradle`, `gradle.properties`, `settings.gradle`
- Result: 61 same, 21 different, 7 source-only, 0 Commons-only

## Selective queue

| status | recommendation | path |
|---|---|---|
| different | review-semantic-diff | `app/build.gradle` |
| different | review-semantic-diff | `app/src/main/AndroidManifest.xml` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/AgentApp.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/AgentControl.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/AgentMemory.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/ChatActivity.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/ConfirmationOverlay.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/DebugLogActivity.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/DeviceStats.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/FloatingButtonService.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/MainActivity.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/MemoryActivity.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/PixelMap.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/SettingsActivity.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/SettingsManager.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/TaskDetailActivity.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/TaskHistory.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/TaskLogActivity.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/TrainingActivity.kt` |
| different | review-semantic-diff | `app/src/main/java/com/local/deviceagent/TrainingData.kt` |
| source_only | candidate-resource | `app/src/main/res/xml/data_extraction_rules.xml` |
| different | review-semantic-diff | `app/src/main/res/xml/file_paths.xml` |
| source_only | candidate-test | `app/src/test/java/com/local/deviceagent/AgentLanguageTest.kt` |
| source_only | candidate-test | `app/src/test/java/com/local/deviceagent/MechanismRouterTest.kt` |
| source_only | candidate-test | `app/src/test/java/com/local/deviceagent/PromptBudgetTest.kt` |
| source_only | candidate-test | `app/src/test/java/com/local/deviceagent/ReasoningOperatorsOracleTest.kt` |
| source_only | candidate-test | `app/src/test/java/com/local/deviceagent/ScaleBakeNibbleTest.kt` |
| source_only | candidate-test | `app/src/test/java/com/local/deviceagent/ScreenClassTest.kt` |

## Reconciliation outcome

The inventoried queue has now been reconciled from the owner's clean `app/` tree at
`4eab3d2fef8a9d44e202fcc48b874be955368db2`: all 21 semantic differences and all seven source-only
tests/resources were imported. Nothing outside the listed queue, and no archive, build directory, model,
local property, or unrelated dirty owner-repository file was copied.

TITAN adds only the receiver transport and the optional `titanHandsAbi=x86_64` build property. The ordinary
owner build remains arm64-only. The reconciled application compiles and assembles, installs on the headless
API 34 emulator, binds its accessibility service, emits the native numbered Kotlin screen, executes a native
Kotlin click, and produces a changed semantic post-action digest. No physical phone was connected or actuated.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

