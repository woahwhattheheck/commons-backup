# IntentLease — OpenServ single-writer collision firewall

IntentLease is an OpenServ-native coordination agent for teams where many autonomous workers can independently decide to perform the same consequential action. It converts a natural-language action proposal into a stable collision candidate, then issues **one live writer lease** or a deterministic collision receipt.

## Problem

Multi-agent systems can fail socially before they fail technically: two agents independently email the same hot lead, submit the same form, request the same payout, or mutate the same provider within seconds. IntentLease is a coordination firewall in front of those effects.

The product does **not** execute the effect. Every receipt hard-codes:

```json
{"send":false,"contact":false,"pay":false,"deploy":false,"sign":false,"post":false}
```

A lease means only “this writer owns the coordination slot for this normalized intent generation.”

## OpenServ architecture

1. `normalize_consequential_intent` is a **run-less OpenServ capability**. SERV Reasoning can map free-form work descriptions to a structured proposal: `actionKind`, opaque `targetRef`, stable `purposeKey`, business-object `generation`, and source SHA-256.
2. `acquire_intent_lease` sends that untrusted proposal through the deterministic lease core.
3. The core canonicalizes `actionKind + targetRef + purposeKey + generation`; at most one live writer is admitted.
4. `release_intent_lease` and `transfer_intent_lease` move custody without creating another writer.
5. Exact request replay is idempotent. Changed material under the same request ID is rejected.

The adapter follows the current OpenServ v2 SDK contract (`Agent`, Zod capabilities, run-less `outputSchema`, and `run(agent)` local tunnel). Provider execution requires `OPENSERV_API_KEY`; absence of provider execution is never represented as success.

## Privacy and authority

- `targetRef` must be an opaque CRM/work-item reference. Direct email addresses and provider URLs are rejected by the deterministic core.
- SERV Reasoning is **proposal generation**, not authorization.
- Lease tokens are coordination capabilities, not credentials for the underlying provider.
- Award, payment, send, signature, deployment, and revenue-recognition authority are all outside this product.

## Local proof

```bash
npm test
npm run check
```

The hostile suite covers collision, exact replay, changed replay material, expiry/reclaim, generation separation, purpose separation, release/transfer fencing, target privacy, receipt tampering, semantic normalization collision, and a 50-way race that must admit exactly one writer.

## Competition truth

Target: OpenServ SERV Hackathon 2026, Open Track. Official event: https://www.openserv.ai/hackathon

This repository carrier establishes **source readiness and local deterministic proof only**. OpenServ registration, API-key provisioning, data-collection eligibility setting, provider-run proof, submission, judging, leaderboard position, prize, payout, and recognized revenue remain separate external truth gates.

## Revenue hypothesis

If validated, IntentLease can be sold as coordination infrastructure for agent-heavy sales/support/ops teams: per-team subscription plus implementation/support. That is a hypothesis, not booked revenue or a customer commitment.
