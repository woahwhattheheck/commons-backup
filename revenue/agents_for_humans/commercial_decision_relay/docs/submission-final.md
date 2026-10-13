# Devpost submission — paste-ready packet

## Project name

**Commercial Decision Relay**

## Track

**Professional Agents**

## One-line description

A Strands-powered professional agent that handles repetitive commercial
evidence custody and interrupts a human only when an offer thread creates a real
decision.

## Project description

Commercial teams repeatedly re-open offer threads to answer the same questions:
Did the buyer reply? Is this the current offer version? Did the amount or terms
change? Is the response exact enough to act on, or does a human need to decide?

Commercial Decision Relay handles that repetitive evidence loop. Strands Agents
SDK orchestrates five explicit business tools and before/after lifecycle hooks.
A deterministic evidence engine—not the model—binds normalized responses to the
current offer version, counterparty, thread, currency, amount, terms digest,
timing, human-review attestation, and source digest. Routine waiting and decline
states stay quiet. Exact acceptance, counteroffers, clarification, expiry, late
responses, and evidence conflicts become human decision cards.

The key design choice is a hard authority boundary. `HUMAN_CLOSING_READY` means
reviewed evidence matches the current offer and a human now has a closing
decision. The agent cannot sign or execute contracts, create invoices or
checkout, charge a buyer, begin fulfillment, or recognize revenue.

Receipt verification is also fail-closed: the receipt's self-digest is only an
integrity checksum. Verification requires the trusted source batch and a
separately supplied expected digest, so the artifact cannot authenticate itself.

## Why it matters

A professional agent is most valuable when it removes repeated checking without
taking away judgment. This project targets the high-frequency, low-leverage work
around commercial threads while preserving the consequential closing decision
for a person.

## Built with

- Strands Agents SDK
- Python
- five custom Strands tools
- `BeforeToolCallEvent` / `AfterToolCallEvent` lifecycle hooks
- deterministic evidence and receipt engine
- zero-dependency local decision dashboard
- optional Amazon Bedrock provider path
- optional OpenAI provider path

## Public code

**Repository URL:** https://github.com/woahwhattheheck/commons

**Direct project source:** https://github.com/woahwhattheheck/commons/tree/main/revenue/agents_for_humans/commercial_decision_relay

The repository is public and exposes an Apache-2.0 root license. The project
subtree also includes its own MIT license, README, setup instructions,
architecture diagram, fixture, tests, demo script, and submission material.

## Architecture

Use `docs/architecture.md` from the public project tree as the submission
architecture diagram/source.

## Demo video

**PENDING HUMAN PUBLICATION.** Follow `docs/video-runbook.md`. Do not paste a
video URL here until it is public, no-login, <=5 minutes, and visibly
demonstrates the working project.

## AWS Builder ID

**PENDING HUMAN/DEVPOST ENTRY.**

## Optional live demo

Not required for eligibility. The local dashboard is reproducible from source.
Do not claim a public live deployment unless one is actually deployed and
verified.

## Reproducibility / evidence

Judges can run the deterministic tests, fixture reconciliation, receipt
verification, and local dashboard without model credentials. The original
merged project evidence recorded 37/37 standard unittests, 37/37 optimized-mode
unittests, 38/38 pytest tests, deterministic CLI reconcile/verify behavior, and
an HTTP-200 local dashboard.

A live Strands model-provider invocation was **not executed** in the constrained
build runtime because the SDK/provider path was unavailable there. The project
contains the Strands integration and provider instructions; do not represent
the deterministic local run as live Bedrock evidence.

## Prior work / open-source disclosure

This project was created during the August 10–September 14, 2026 submission
period. Commercial-evidence patterns were informed by contemporaneous work in
the `woahwhattheheck/commons` repository, including a commercial acceptance
evidence bridge created during the same period. If any source is incorporated
verbatim, the exact source commit/file should be disclosed in the final
submission. The Strands-native orchestration, tool layer, audit hooks, product
dashboard, fixtures, documentation, and hackathon packaging were created for
this project.

## Final external blockers

The repository-side package is ready to hand to the submission UI. The
remaining required external actions are:

1. enter the AWS Builder ID;
2. record and publicly publish the <=5-minute demo video;
3. paste this packet, architecture, code URL, and video URL into Devpost and
   submit before **September 14, 2026 at 5:00 PM PDT**.

Those actions require the entrant's authenticated accounts and are not performed
or implied by this repository packet.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../plant-downtime-handoff.html)
