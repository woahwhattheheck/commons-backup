# Commerce Conversion Loop

A deterministic, offline evidence compiler for the commercial path:

**shipped offer → qualified target → provider submission → delivery truth → genuine reply → proposal evidence → payment evidence**

It exists because those facts commonly live on different surfaces and provider submission alone is easy to misstate as successful contact. The tool joins retained evidence into one conservative owner-review state without gaining authority to perform any commercial action.

## Truth model

The compiler reports only what supplied retained evidence supports: OFFER_ONLY, TARGET_QUALIFIED, OUTBOUND_PENDING_DELIVERY, OUTBOUND_DELIVERY_FAILED, OUTBOUND_DELIVERED, REPLY_OBSERVED, PROPOSAL_OBSERVED, PAYMENT_OBSERVED, or fail-closed HOLD.

PAYMENT_OBSERVED means payment evidence was supplied and provenance-bound. It is **not** a conclusion that cash settled, revenue is recognized, a receivable exists, fulfillment is complete, or accounting entries are appropriate.

Every stage carries an opaque event identity, opportunity scope, canonical UTC, retained source reference, SHA-256-bound evidence text, explicit parent, and stage-specific facts. The caller also supplies an independently retained SHA-256 root for the entire normalized source generation. Missing or ambiguous parentage, scope drift, evidence reuse, conflicting delivery terminals, stage duplication, chronology regression, or a retained-root mismatch fail closed to HOLD.

## No action authority

All generated packets permanently set send/follow-up, proposal, payment/refund, provider mutation, fulfillment, ledger mutation, and revenue-recognition authority to false. nextExperiment is falsifiable **owner-review research guidance**, never an execution grant. Any actual outbound still needs the workspace's current collision/lease and authority controls.

## CLI

From the repository root:

~~~bash
ROOT=$(python -m revenue.commerce_conversion_loop.cli root revenue/commerce_conversion_loop/real_public.sample.json)
python -m revenue.commerce_conversion_loop.cli compile revenue/commerce_conversion_loop/real_public.sample.json --expected-root "$ROOT" --output /tmp/conversion-review
python -m revenue.commerce_conversion_loop.cli verify revenue/commerce_conversion_loop/real_public.sample.json --expected-root "$ROOT" --output /tmp/conversion-review
~~~

Output is create-exclusive: canonical packet.json, owner-review summary.md, formula-safe events.csv, and receipt.txt binding the exact artifact generation. Input reads are bounded regular non-symlink reads. JSON duplicate keys, floats, non-finite values, unknown fields, bool/int aliases, invalid identifiers/timestamps/digests, and contact/secret-shaped retained evidence text are rejected.

## Real-public sample

real_public.sample.json contains only already-public GitHub merge evidence for a shipped Commons artifact. It contains **no target, recipient, outbound, reply, proposal, or payment evidence**, so the only valid state is OFFER_ONLY. This is a regression against a dangerous inference: shipping a product does not prove market contact or conversion.

The source reference is public; the retained evidence text is a sanitized public merge receipt. Its digest proves the exact retained text used by this fixture, not the truth or completeness of GitHub or any external provider.

## Commercial use

This is internal conversion instrumentation. It helps identify shipped offers with no target evidence, submitted messages still lacking delivery truth, delivered contacts with genuine replies, replies with proposal evidence, and proposals with payment evidence. It does not contact prospects, choose recipients, bypass collision control, send proposals, operate payment providers, or recognize revenue.
