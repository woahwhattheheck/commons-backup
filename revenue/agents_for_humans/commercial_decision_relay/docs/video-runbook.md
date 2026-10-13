# Demo video runbook — target 3:45, hard cap 5:00

The official Agents for Humans submission requires a public demo video of no
more than five minutes. Slides, screen recordings, and voiceover are allowed;
on-camera appearance is not required.

This runbook is a capture plan only. It does not publish a video or claim a live
provider execution.

## Preflight

From the project directory:

```bash
PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONPATH=src python -m decision_relay.cli reconcile \
  --batch fixtures/demo-batch.json \
  --output /tmp/decision-relay-receipt.json
PYTHONPATH=src python -m decision_relay.web_demo \
  --batch fixtures/demo-batch.json
```

Have these files open before recording:

1. `README.md`
2. `docs/architecture.md`
3. `src/decision_relay/strands_app.py`
4. local dashboard at `http://127.0.0.1:8080`
5. `/tmp/decision-relay-receipt.json`

Do not show credentials, environment variables, private evidence, email, Slack,
or unrelated Commons files.

## Shot list

### 0:00–0:30 — Problem and user

Narration:

> Commercial teams waste time rereading offer threads just to learn that
> nothing changed. Commercial Decision Relay handles that repetitive evidence
> loop and interrupts the closer only when there is a real decision.

Show the README title and one sentence identifying the Professional Agents
track.

### 0:30–1:05 — Architecture and Strands

Show `docs/architecture.md`, then briefly show
`src/decision_relay/strands_app.py`.

Narration points:

- Strands orchestrates five explicit tools.
- Before/after tool hooks produce hash-only audit records.
- A deterministic engine, not the model, decides evidence state.
- The agent has no signing, checkout, charging, fulfillment, or recognized
  revenue capability.

Do not claim a live Bedrock call unless one was actually captured.

### 1:05–1:55 — Reproducible fixture

Show the reconcile command and its receipt.

Narration:

> The same synthetic batch produces a deterministic, content-addressed receipt.
> Identity, offer version, thread, amount, terms, timing, review attestation,
> and source digest all have to bind. Replay and conflicting evidence fail
> closed.

Show the receipt digest and the all-false authority section.

### 1:55–2:55 — Human interruption demo

Switch to the local dashboard.

Show at least:

- an exact-acceptance decision card;
- a counteroffer or clarification card;
- a routine decline/waiting item that does not create a closing card.

Narration:

> Routine states stay quiet. Exact acceptance is not auto-close: it becomes a
> human closing decision. Counteroffers, ambiguity, expiry, late responses, and
> conflicts also surface instead of being silently guessed through.

### 2:55–3:25 — Verification boundary

Show the independent verification command or the verifier source.

Narration:

> The receipt's self-hash proves integrity, not authenticity. Verification also
> requires the trusted source batch and an independently supplied expected
> digest, so a receipt cannot authenticate itself.

### 3:25–3:45 — Close

Narration:

> Commercial Decision Relay removes repetitive checking without moving judgment
> or commercial authority into the model. The human keeps the consequential
> decision; the agent does the evidence work.

Show the public source-tree URL in the README or judge quickstart.

## Publication checklist

Before using the URL on Devpost:

- video is <= 5:00;
- video is publicly accessible without login;
- working project is visibly demonstrated, not only slides;
- problem, user, and why it matters are said explicitly;
- no secrets/private evidence appear;
- any live-provider claim shown in the video is backed by the recording itself;
- URL is copied into the submission manifest only after publication.

Until those conditions are true, `public_demo_video` stays `HUMAN_PENDING`.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../plant-downtime-handoff.html)
