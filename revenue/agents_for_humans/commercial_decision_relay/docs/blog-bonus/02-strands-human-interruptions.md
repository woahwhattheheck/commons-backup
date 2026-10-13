# Agents for Humans: Designing a Strands Agent That Interrupts Only for Real Decisions

Many workplace agents are optimized for one visible behavior: answer every request. Commercial operations often need the opposite. The best outcome for most events is **no interruption at all**.

That was the product constraint behind **Commercial Decision Relay**, our Professional Agents entry for the AWS Agents for Humans hackathon. We used Strands as the orchestration layer, but designed the tool surface so the model cannot convert fluent language into commercial authority.

## Five tools, each with a narrow job

The Strands layer exposes five business tools:

- `ingest_batch` normalizes and deduplicates evidence without external side effects.
- `reconcile_evidence` asks the deterministic engine to produce the decision receipt.
- `decision_queue` returns only the states that should interrupt a human.
- `explain_blocker` explains why one series is not ready.
- `verify_current_receipt` checks the receipt against an independently supplied commitment and trusted source.

A small tool surface helps in two ways. It gives the agent enough freedom to coordinate a workflow, while making the authority boundary inspectable. There is no hidden sixth tool that signs, charges, invoices, fulfills, or recognizes revenue.

## Orchestration is not truth

A model is useful for selecting and sequencing work. It is not the source of truth for whether two offers are commercially identical.

The deterministic engine checks exact fields such as offer version, counterparty, thread, currency, amount, terms digest, evidence timing, source digest, and human-review attestation. The agent can call that engine; it cannot rewrite the engine's rules.

This lets the conversational layer stay flexible without making the business semantics fuzzy.

## Lifecycle hooks without leaking commercial content

The Strands integration also subscribes to before/after tool-call lifecycle events. Instead of logging raw commercial evidence, the audit path records hashes and tool-level metadata. That makes the orchestration observable while reducing the chance that an audit stream becomes a second uncontrolled copy of sensitive deal content.

Tool allowlisting is equally important. If the model tries to invoke something outside the intended surface, the design should fail closed rather than silently broadening its capabilities.

## Human interruption as a product primitive

The most important output is not a paragraph. It is the decision queue.

`AWAITING_RESPONSE` is routine. A clean decline is routine. Those do not need another notification.

An exact reviewed acceptance before expiry is different: a person may now have a real closing decision. A counteroffer or clarification is different: someone needs to decide whether the new terms are acceptable. An expiry, late response, or evidence conflict is different: continuing automatically could create a false commercial state.

By treating interruption as a scarce resource, the product becomes less like a chatbot and more like a relay between machine-scale monitoring and human judgment.

## The local judge path

A hackathon project should be inspectable without requiring judges to recreate the developer's private environment. Commercial Decision Relay includes a synthetic batch and a zero-dependency local decision board. The deterministic path can be run without a model credential, and the project source separately contains the Strands agent integration.

That distinction is deliberate: offline reproducibility should not be mislabeled as proof that a provider-backed model invocation ran. The source, deterministic execution path, and provider-backed path are separate evidence claims.

## What we would carry into production

The pattern generalizes beyond sales:

- use the agent for workflow selection and coordination;
- make state-changing business truth deterministic and testable;
- keep the permission surface smaller than the reasoning surface;
- audit tool use without unnecessarily duplicating raw business data;
- reserve human attention for exceptions and consequential decisions.

The promise of Agents for Humans is not that the agent replaces every human step. It is that software can absorb the repetitive work and make the remaining human step more informed, more explicit, and less noisy.

Project source: https://github.com/woahwhattheheck/commons/tree/main/revenue/agents_for_humans/commercial_decision_relay

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../../plant-downtime-handoff.html)
