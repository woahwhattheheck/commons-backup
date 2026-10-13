# Agents for Humans: Why Commercial Automation Needs Proof-Carrying Receipts

Commercial work has an awkward shape for AI. Most of the labor is repetitive: watch for replies, match a response to the current offer, notice an expiry, compare terms, and surface the few cases that actually deserve a person's attention. But the last step is consequential. A model that turns ambiguous language into signing, charging, or revenue authority is not an assistant; it is an uncontrolled decision maker.

For the AWS Agents for Humans hackathon, we built **Commercial Decision Relay**, a Strands-powered professional agent around one design rule: automate the evidence work, not the human's authority.

## The split that makes the product useful

The relay has two layers with deliberately different jobs.

**Strands handles orchestration.** The agent can call a small allowlisted tool surface to ingest normalized evidence, reconcile it, inspect the decision queue, explain a blocker, and verify the current receipt.

**A deterministic engine handles commercial state.** It checks the identity of the offer and counterparty, offer version, thread, currency, amount, terms digest, timing, source digest, and human-review attestation. Those checks decide whether evidence is routine, contradictory, expired, or ready to be placed in front of a human closer.

This separation matters because language models are good at deciding *what work to do next* while deterministic code is better at enforcing exact invariants. The model can orchestrate the workflow without getting to redefine what counts as an exact acceptance.

## A receipt is evidence, not authority

Every reconciliation produces a deterministic receipt and SHA-256. That digest is useful for integrity and replay detection, but the digest does not authenticate itself. Verification therefore takes an independently supplied expected digest and the trusted source batch, then recomputes the receipt.

The distinction sounds subtle, but it prevents a common failure mode: treating "the object says its own hash is X" as proof that the object is trusted. In Commercial Decision Relay, self-consistency is not the same thing as provenance.

The same principle applies to business authority. A state named `HUMAN_CLOSING_READY` means only that reviewed evidence exactly matches the current offer and should interrupt a person. It grants no power to sign a contract, create an invoice or checkout, charge a customer, start fulfillment, or recognize revenue. Those capabilities do not exist in the project.

## Quiet by default, interrupt on decisions

A useful professional agent should reduce interruption rather than create a new notification stream.

Routine states such as `AWAITING_RESPONSE` and `DECLINED` stay quiet. Exact acceptance, counteroffers, clarifications, expiry, late responses, and evidence conflicts become decision cards. That makes the agent's output proportional to the human value of the decision instead of the volume of the inbox.

The local decision board is intentionally simple. It can run against a synthetic fixture without a model credential, which gives judges and developers a reproducible way to inspect the product behavior and the authority boundary.

## Why this is an Agents for Humans pattern

The interesting part of agentic software is not giving a model more permissions. It is deciding where autonomy stops.

For commercial operations, the pattern we found useful is:

1. Let the agent coordinate repetitive work.
2. Put exact state transitions behind deterministic tools.
3. Make evidence provenance explicit.
4. Make consequential authority absent unless it is intentionally designed and separately granted.
5. Surface only the small set of cases where a person can add judgment.

Commercial Decision Relay is our attempt to make that boundary visible in the architecture, code, receipts, tests, and user experience. The result is not a robot closer. It is a system that can do more of the tedious commercial evidence work while making the human decision point harder to miss and harder to fake.

## Reproduce the deterministic path

The public project includes a synthetic fixture, unit tests, a command-line reconciliation/verification path, a local decision board, an architecture diagram, and the Strands integration source. The deterministic core and board can be exercised without provider credentials. Provider-backed Strands execution requires the relevant SDK/provider environment and should not be inferred from the offline path alone.

Project source: https://github.com/woahwhattheheck/commons/tree/main/revenue/agents_for_humans/commercial_decision_relay

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../../plant-downtime-handoff.html)
