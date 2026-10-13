# Agents for Humans: Reliability Means Testing the Evidence Boundary, Not Just the Happy Path

An agent can look excellent in a demo and still be unsafe in the exact cases that matter: stale offers, late replies, duplicated events, contradictory evidence, future-dated records, or a receipt that verifies only against itself.

For **Commercial Decision Relay**, our AWS Agents for Humans project, we treated those cases as product behavior rather than edge-case cleanup. The goal was to build a professional agent that could reduce commercial busywork without manufacturing certainty.

## Start with the failure you do not want

The failure we care about is not "the model gives a clumsy answer." It is "the system tells a human that a commercial state is settled when the evidence does not support that conclusion."

That threat model changes the tests we write.

The deterministic evidence engine checks identity, thread, offer version, currency, amount, terms digest, source digest, timing, and human review. Exact replay should collapse instead of multiplying work. Conflicting evidence should fail closed. A response to a superseded offer should not resurrect the old commercial state. Future evidence should be quarantined instead of silently accepted.

These are mundane invariants, but they are what turn a persuasive demo into a workflow a professional can reason about.

## Separate integrity from authenticity

The relay emits a deterministic receipt SHA-256. It would be easy to stop there and call the receipt verified.

We did not.

A self-digest can tell you whether bytes changed relative to that digest. It cannot tell you whether the object was the trusted object in the first place. Verification therefore accepts an independent expected digest and the trusted source batch, recomputes the result, and compares the independent commitment.

That same distinction is useful throughout agent design: "internally consistent" is weaker than "bound to trusted evidence."

## Time is part of evidence

Commercial truth is often temporal. An acceptance before an offer expires is not equivalent to the same words after expiry. A late response to a superseded offer is not a current acceptance.

The project models those states explicitly rather than asking the language model to infer whether timing "feels close enough." When a case is late, expired, or contradictory, the useful agent behavior is to surface the blocker and let a person decide what to do next.

## Test the authority boundary too

Reliability also means proving what the agent **cannot** do.

Commercial Decision Relay has no signer/legal authority and no tools for contract execution, invoice or checkout creation, payment/charging, fulfillment start, or revenue recognition. A human-ready decision receipt is evidence for a person; it is not a token that escalates the agent's permissions.

That negative capability is part of the product contract. A professional user should be able to inspect the architecture and see where automation ends.

## Make the judge path reproducible

The repository includes a synthetic fixture, deterministic CLI flow, receipt verification, tests, and a local decision board. That gives reviewers a free path to exercise the central behavior without requiring access to private commercial data.

The Strands integration is implemented in source as the orchestration layer. A provider-backed model run is a separate execution claim and should be demonstrated from an environment where the SDK and chosen provider are actually available, rather than inferred from deterministic-core tests.

## Reliability is a design criterion, not a cleanup phase

The broader lesson we are taking from this project is that agent reliability starts with the boundary between language and authority.

Use the model where flexible reasoning helps. Use deterministic code where exact state matters. Carry evidence through receipts. Recompute rather than trust self-claims. Test stale, late, duplicated, contradictory, and malformed inputs. Make irreversible capabilities explicit—and if the product does not need them, leave them out.

That approach produces a less magical demo. It also produces an agent whose behavior a human can actually interrogate when the situation is no longer the happy path.

Project source: https://github.com/woahwhattheheck/commons/tree/main/revenue/agents_for_humans/commercial_decision_relay

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../../plant-downtime-handoff.html)
