# TITAN Hands

TITAN Hands is a semantic computer-use substrate shared by Windows, Android, and Linux adapters. The model is
the driver. Platform code translates current state into a compact observation, executes the model's selected
action, and returns typed evidence about the outcome.

```text
task -> model -> DeltaUI action -> platform adapter -> application
                 ^                                  |
                 +------ semantic delta + receipt --+
```

## DeltaUI contract

An observation has a monotonic sequence, a base sequence, stable nodes, metadata, and a digest of the resulting
state. After the first full observation, the wire carries only added, updated, and removed nodes. A node can
contain role, name, exact value, state bits, bounds, process/window identity, parent, and executable patterns.

The shared action vocabulary is intentionally direct: invoke, set value, toggle, expand/collapse, select,
focus, click, type text, key, scroll, launch, wait, capture, and done. Adapters return a typed failure instead
of pretending an action succeeded.

## Pixel policy

Screenshots are a model-callable instrument, not the default display. Capture is appropriate when an application
exposes an empty or opaque accessibility tree, two targets remain semantically ambiguous, verification fails,
coverage drops, or the model explicitly asks for pixels. The adapter otherwise transmits no frames.

This avoids model-visible rendering and frame transport. It does not claim that arbitrary legacy applications
stop performing internal layout or composition.

## Platform plan

- Windows: shipped first in `host/titan_hands_windows/` using UI Automation, UIA control patterns, native input,
  and an on-demand window capture fallback.
- Android: reuse the LDA accessibility snapshot/action layer behind the same protocol, initially on a headless
  emulator. No physical phone is part of this phase.
- Linux: AT-SPI adapter at `host/titan_hands/linux_atspi.py` maps nodes/actions into DeltaUI.
  Compositor capture runs only on explicit `capture`. A missing bus returns `TRANSPORT_UNCONFIGURED`.

Commons remains the durable coordination and receipt plane. The Windows hook is a local stdio process; using it
does not require the Commons web page to render or transmit a desktop.

## One model-facing tool

The local one-tool facade (`python -m host.titan_hands.mcp_one`) lists `hands` as the primary tool.
`titan_hands` remains a call alias for that same handle. One call carries `op` plus `target`.
Computer-use keeps the DeltaUI broker: `observe` / `act` / `capture` / `done` on
`target=windows`, `target=android`, or `target=linux`. Capture stays explicit. The original five-tool
server (`hands_observe`, `hands_act`, `hands_capture`, `hands_targets`, `hands_capabilities`) stays as
a compatibility keep.

Additional live targets on the same tool:

- `files` — list/read/write through the existing lane
- `git` — status/diff/log/add/commit through the existing lane
- `slack` — `#commons` `YOUR_CHANNEL_ID`
- `board` — new `p/{id}.md` only
- `shell` — local command
- `browser` — HTTP/page fetch; image bodies stay off the default path

Linux AT-SPI is the live `target=linux` adapter at `host/titan_hands/linux_atspi.py`.
`host/titan_hands/linux.py` re-exports that adapter. A missing bus returns `TRANSPORT_UNCONFIGURED`.
It is not a remint of Windows or Android.

Call `hands` with `op=targets` (or leftover `op=catalog` / `route=catalog`) for the live table.
Do not smash `commons.mno`.
