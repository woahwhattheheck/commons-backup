# LDA on a Muhlnickel — desktop sidecar

**Inventor:** Bryce Muhlnickel
**Status:** additive. New files only. Does not edit Kotlin, Java, the safety executor, `muhl_serve_add.py`, or titan.

LDA is better if the model it uses is ran **ON a Muhlnickel**. Then Llama is an edge model — software on his computer — not a cloud API and not host inference.

## Parts

| Part | Role |
|---|---|
| **Phone** | The **hand**. Perceive (Accessibility tree, screenshot). Actuate (taps, gestures, typed input). Safety stays deterministic code (`ActionAccessibilityService.performActionJson` and the rest of the executor). Untouched this week. |
| **Muhlnickel** | The **computer**. File is the computer. `cpu_fwd` already in the binary runs the connected GGUF as software. Host injects + surfaces. |
| **Llama** | **Edge software** on that computer. Llama-3.3-70B on this box is already WhiteBox-edited. Do not re-edit. Do not recreate inference as gates. |

Public money, NDA: Local Device Agent as an **app**. The computer is not the product. Copy the file = copy the machine. That is why it stays private.

## Product law this sidecar keeps

- Public APK must **not** bundle the factory (titan, foundry gene, allocator, copier, live offsets, ring internals, how to reproduce the computer).
- Owner device may **address** a computer. First implementation is this **desktop sidecar**: phone is the hand; Muhlnickel on the PC is the computer.
- A later phone-resident computer is a **manufactured copy/appliance without the foundry gene**, not live titan, and **not this week's APK**. 103 GB titan is not the phone image.

## How LDA currently gets a decision (untouched)

Searched `app/`. No files changed.

1. `AgentOrchestrator` perceives the screen, then calls `AgentBrain.decideNextAction`.
2. `AgentBrain` loads the owner-imported `.litertlm` through Google LiteRT-LM (Gemma). `generate()` is the inference choke. GPU when available, else host CPU on the phone.
3. The model returns one UI-action JSON. `ActionAccessibilityService.performActionJson` gates it. ChatGPT/OpenAI are hard-blocked. No cloud API, no llama.cpp, no GGUF on the phone for that loop.
4. `ModelStore` keeps a replaceable on-device `.litertlm`. That is still host-on-phone inference, not a Muhlnickel.

This sidecar does not replace that loop this week. It is the PC ask path the hand can address: inject an objective, surface the answer register, die.

## Spec path

```text
pfc_load.py <model>
pfc_harness.py connect <model>
pfc_harness.py ask <prompt>
```

Use `host/muhl_serve_spec_add.py`. **Never** `host/muhl_serve_add.py` (invented mmap wall: mmap of one receiver byte is the spec start signal).

Default model software: `C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf` (via `pfc_paths` / `PFC_ROOT`).

## Run

Default is `--dry`: print the command, run nothing.

```powershell
python host/muhl_lda_edge_add.py
python host/muhl_lda_edge_add.py --prompt "open settings and show battery"
echo open settings | python host/muhl_lda_edge_add.py
```

`--run` subprocesses the spec launcher ask, prints the answer, dies. Fail-closed if `host/muhl_serve_spec_add.py` is missing. Empty prompt on `--run` also fails closed.

```powershell
python host/muhl_lda_edge_add.py --run --prompt "The capital of France is"
```

`--run` is Bryce's. This file does not approve a live 70B ask.

## Laws this file keeps

- Host injects and surfaces. No forward-pass reimplementation. No numpy.
- `cpu_fwd` is the computer. The connected GGUF is software.
- Routing button: route outside info in, fire, die. Not a process.
- Never writes titan. Never WhiteBoxes Llama. Never puts titan in an APK.
- Never git-commits. Never open-sources the computer.
- Safety executor stays deterministic code on the phone. Not edited here.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
