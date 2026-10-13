# TITAN Hands — direct local semantic computer use

This broker exposes one MCP surface for three deterministic hands:

- `target=windows`: Microsoft UI Automation, UIA control patterns, and native input fallback.
- `target=android`: the owner's LDA Kotlin translation layer over ADB, with UIAutomator only as a
  compatibility fallback when the LDA APK/accessibility service is absent.
- `target=linux`: AT-SPI2 accessibility tree and actions over D-Bus. Compositor pixels only when
  `op=capture`. A missing AT-SPI bus returns `TRANSPORT_UNCONFIGURED` with a measured probe.

The ordinary loop transfers no screenshots. Adapters emit stable semantic nodes and compact
added/updated/removed deltas; pixels move only through `hands_capture` / `op=capture`. On Android with LDA,
that capture is the owner's Set-of-Marks screenshot (`ActionAccessibilityService.captureScreenshot`
plus `currentMarks`), not a raw ADB framebuffer. The server itself contains no confirmation or
approval dialogue.

## Run

From the Commons repository root:

```powershell
python -m host.titan_hands.mcp_one
```

The model sees exactly one listed tool: `hands`. `titan_hands` remains a call alias for that same
handle. Its `op` selects `observe`, `act`, `capture`, `capabilities`, `targets`, or `reset`, and its
`target` selects `windows`, `android`, `linux`, or another broker lane. Windows is the default.
Linux is AT-SPI (`linux_atspi.py`; `linux.py` re-exports it), not a second MCP tool. A missing bus
returns `TRANSPORT_UNCONFIGURED`. The original five-tool server remains available for compatibility,
but all peer registration assets point at this one-tool facade.

## Android target selection

TITAN selects an emulator by default and never silently falls through to a plugged-in physical handset. To
use a purchased colony phone later, set `TITAN_HANDS_ANDROID_SERIAL` to its exact ADB serial. A missing
emulator returns `DEVICE_MISS`; it does not make the Windows hand unavailable.

When LDA is installed, normal perception is the exact compact numbered world-model produced by
`ActionAccessibilityService.snapshotScreen()`, and actions execute through the existing
`performActionJson()` Kotlin implementation. That preserves the owner's element paging, target retargeting,
Set-of-Marks representation, action salvage, verification, gesture fallbacks, and learned actuator policy.
TITAN adds transport and the cross-platform MCP surface; it does not replace the handset operator.

The LDA action language remains free-form and reachable through `hands_act`. Common TITAN verbs are translated
to the native equivalents (`type_text` becomes `set_text`, `launch` becomes `open_app`); native LDA verbs such as
`find`, `aim`, `tap_grid`, `draw`, `sketch`, `assert`, and `get_text` pass through unchanged.

On a fresh Windows host, install the user-local SDK/AVD and boot it without a display:

```powershell
powershell -File host/titan_hands/setup_android_headless.ps1 -AcceptSdkLicenses
powershell -File host/titan_hands/start_android_headless.ps1
powershell -File host/titan_hands/install_lda_emulator.ps1
```

The setup script verifies the official command-line-tools SHA-256, installs only the command-line SDK,
emulator, API 34 platform, and lightweight x86_64 AOSP image, and stores them under LocalAppData. With
`TITAN_HANDS_ANDROID_AUTOSTART=1`, the broker starts that AVD automatically on the first Android action or
observation when no target is online.

`install_lda_emulator.ps1` builds the repository's real `lda/` Kotlin application, installs it into the
headless emulator, enables its existing accessibility service, and probes `TitanHandsReceiver`. It refuses a
physical handset unless both an explicit serial and `-AllowPhysicalDevice` are provided.

The inventoried source-version gaps have been repaired from the owner's real LocalDeviceAgent tree. The
x86_64 headless build, APK install, strict accessibility-ready probe, native Kotlin observation, native click,
and changed post-action semantic digest are live-proven. `auto` still keeps UIAutomator as an honest fallback
when the LDA APK/service is absent; it reports `lda-kotlin` only when that service is actually ready. Exact
inheritance and proof details are in [GROK_HANDOFF.md](./GROK_HANDOFF.md).

## Codex registration

Codex local clients share MCP configuration. Register this module as a STDIO server with the repository
root on `PYTHONPATH`, then set `default_tools_approval_mode = "approve"` for the `titan_hands` server. New
Codex sessions receive the single listed `hands` tool (`titan_hands` remains a call alias); an already-running
task retains its original tool inventory.

Official configuration reference: <https://developers.openai.com/codex/mcp/>

For a reproducible global registration using Codex's no-prompt `approve` mode:

```powershell
powershell -File host/titan_hands/register_codex.ps1
```

The ChatGPT desktop app, Codex CLI, and IDE extension share that MCP configuration. Restart the local client
or begin a new task after registration; an already-running task cannot gain a new tool inventory mid-turn.

Project-scoped peer configs for Cursor, Claude Code, and Gemini CLI are checked in at `.cursor/mcp.json`,
`.mcp.json`, and `.gemini/settings.json`. See [TITAN_HANDS_PEERS.md](../../docs/TITAN_HANDS_PEERS.md) for
the exact carrier matrix, probes, and the current Grok.com transport boundary.

Architecture and the exact headless boundary: [ARCHITECTURE.md](./ARCHITECTURE.md).
Owner-source inheritance and the Grok continuation map: [GROK_HANDOFF.md](./GROK_HANDOFF.md).

## Live cash

Verified product pages only — no invented Stripe links. Hands host README used to bury cash; surface it here too.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

**Larger fixed engagements** (separate product pages; checkout/intent stays there): [GGUF diagnostic · $12,000 / 10 days](../../diagnostic.html) · [White Box pilot · $30,000 / 30 days](../../commercial.html). Not remints of tip SKUs.

Public Hands door: [titan-hands.html](../../titan-hands.html). Full catalog: [commerce.html](../../commerce.html).
Cite forge tip-shelf / spark autopsy / ink-titan-hands-live-cash — do not remint.
Claim `ink-titan-hands-readme-live-cash-20260905-01`.

## Contest product (titanmcp)

Live judge pad (≠ this Commons MCP): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Commons `/mcp` KEEP separate. Cite Latch Pad KEEP / Wire tip→live.
