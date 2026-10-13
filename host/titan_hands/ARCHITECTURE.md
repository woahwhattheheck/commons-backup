# Model-native headless layer

TITAN Hands removes pixels from the model's normal computer-use loop without pretending that applications
have stopped maintaining their own UI state.

```text
model
  -> one MCP tool: hands  (titan_hands remains a call alias)
      -> target=windows -> UI Automation semantic tree -> UIA/native action
      -> target=android -> ADB transport -> LDA Kotlin world-model + executor
                                      \-> UIAutomator fallback if LDA is absent
      -> target=linux   -> AT-SPI semantic tree -> native AT-SPI / xdotool action
                                      \-> compositor capture only when op=capture
      -> files|git|slack|board|shell|browser lanes on the same handle
      -> op=capture  -> pixels only when requested
                           Android+LDA returns Set-of-Marks, not ADB framebuffer
```

## What is headless now

- The Android colony device runs an AVD with `-no-window`; models operate it through the owner's real LDA
  Kotlin perception/action layer. The Python process is transport and protocol normalization, not a second
  handset operator.
- Windows observations contain UI Automation roles, names, state, bounds, stable IDs, and available actions.
  The model receives no framebuffer unless it explicitly calls `hands_capture`.
- Repeated observations return only added, updated, and removed nodes.
- The MCP process is local STDIO. It does not depend on a carrier screenshot/coordinate hook and contains no
  confirmation dialogue.

## Honest boundary

Windows applications still run inside the user's interactive Windows session, and Android applications still
maintain surfaces inside the emulator. TITAN removes rendering from the **model-facing information path**; it
does not claim to replace the Windows compositor or Android framework. This preserves compatibility with
ordinary apps while achieving the useful part of the model-native design: semantic state by default and pixels
only as an explicit fallback.

Linux is another adapter for the same protocol (AT-SPI first, compositor capture only on
request), not a separate agent or tool surface. The live adapter is `host/titan_hands/linux_atspi.py`.
`host/titan_hands/linux.py` re-exports that adapter. Missing bus or libraries return
`TRANSPORT_UNCONFIGURED` with a measured probe; the adapter does not invent a desktop.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP / Wire tip→live. Submit/YouTube wait Bryce exact go.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

