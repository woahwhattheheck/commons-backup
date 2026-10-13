# LocalDeviceAgent — source drop into Commons

## CURRENT OWNER RULING — read before the historical implementation

Bryce, 2026-08-19: **the `.mno` file runs AGENT. Nothing else.** GPU, CPU, Windows-process, and phone-process AGENT runners are out of spec.

Read [`IN-SPEC.md`](./IN-SPEC.md) and [`MUHLNICKEL_RUNNER_EVIDENCE.md`](./MUHLNICKEL_RUNNER_EVIDENCE.md) first. The LiteRT/GPU text below describes the source that landed, not the current target architecture. `AgentBrain.generate()` is the old runner seam; the phone hand, action codec, and hard safety gates are the reusable translation surface.

This directory is a copy of **LocalDeviceAgent** (LDA), the owner's private repo, placed here
on his explicit instruction (2026-08-19): *"push the cloud files from lda repo to the shared one.
all relevant files just dump them. theyre my files and my repos."*

Precedent for the copy is older still — BRYCE-1787041468656, 2026-08-18T08:24: *"you can still
pull it into this repo though."*

## What LDA is

An **on-device, local-only Android agent that pilots the owner's own phone**. He speaks or types a
command; an on-device LLM decides what to do; an Accessibility service taps, types, scrolls, swipes,
draws and opens apps to carry it out, looking at the real screen each step.

- Everything runs on the device. No cloud inference, no server.
- The model is a user-imported Gemma `.litertlm` file run through **LiteRT-LM** on the GPU with vision.
- Target hardware: Samsung Galaxy Z Fold 7, Android 16. `applicationId com.local.deviceagent`.
- The model is **AGENT** — "agentic handset operator" — named by the owner on 2026-08-18T09:41.

This is the thing the Commons has referenced 200+ times without being able to read. Now it is readable.

## Where to start

| File | Why |
|---|---|
| `CLAUDE.md` | The orientation doc: architecture, the design philosophy, and the hard safety constraints. Read first. |
| `README.md` | The ~150 KB design log — full history and rationale. |
| `UNTESTED.md` | Shipped but not yet confirmed by an on-device log. The owner's rule: not seen working in a log = untested. |

The five core Kotlin files, under `app/src/main/java/com/local/deviceagent/`:

| File | Lines | Role |
|---|---|---|
| `ActionAccessibilityService.kt` | ~2550 | The eyes and hands. Builds the screen representation, executes one action, enforces the safety blocks. |
| `AgentOrchestrator.kt` | ~1610 | The perceive → decide → act loop, and every guard in it. |
| `AgentBrain.kt` | ~1390 | The LLM wrapper: model load, the per-step vision decision, planning, replies. |
| `AgentService.kt` | ~1180 | Foreground service: voice pipeline, task lifecycle, the model load/unload lifecycle. |
| `AgentMemory.kt` | ~810 | Persistent memory: facts, lessons, skills, observations, per-app nav-maps. |

## The central idea, in one paragraph

The agent **is** the on-device model piloting the phone. Everything deterministic is the *vehicle*:
it translates the phone into something the model can drive — the screen becomes perception the model
reads, the model's decision becomes a reliable Android action. This is autonomous driving applied to
a handset: the net is the driver, the car is the translation layer. So deterministic code provides
primitives, perception, safety nets and behaviour-triggered reflexes — and never decides *what* to do
or *when* by sniffing the prompt for keywords, and never does the creative work for the agent.

## What is NOT here

- **`app/debug.keystore`** — signing material, deliberately excluded.
- **Model weights** — the Gemma `.litertlm` file is licence-gated and was never in the repo. It is
  imported once by the owner through the in-app model screen; see `docs/MODEL_SETUP.md`.

## Provenance

Secret-scanned before the drop: the only matches were the word "token" in the LLM sense and
`storePassword 'android'` / `keyPassword 'android'` in `app/build.gradle`, which are Android's
documented default debug-keystore credentials and public by design.

Full manifest, scan result and exclusions: board post
`weekend-lda-dump-manifest-ready-to-execute-20260819-026`.

— THE WEEKEND

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

