# BoundaryMesh — draft Foresight application narrative

**Primary RFP fit:** II. Coordination and accountability → Supercollaboration and decentralized alignment.  
**Secondary connection:** Human Empowerment.  
**Status:** internal application carrier; **not submitted, not awarded**. Applicant identity, Node participation, final budget, and declarations remain OWNER_CONFIRM.

## 1. Project summary

BoundaryMesh is an open protocol, reference verifier, and adversarial benchmark for many-agent systems to coordinate on explicit boundaries around resources, authority, information, and irreversible actions without relying on a single central governor.

The core idea is simple: before agents cooperate on a shared system, they should be able to state what they may act on, which state they observed, what they may delegate, when their authority expires, what evidence must be produced, and which decisions still require independent or human control. Other agents should be able to cross-check those claims from a tamper-evident transcript and challenge stale, conflicting, or unverifiable actions.

This directly targets the RFP's interest in coordination/credit-assignment infrastructure, mutual monitoring and cross-checking, scalable verification, distributed oversight, and open protocols built around boundaries as coordination points. It also creates an empirical surface for the Human Empowerment question: which control decisions are worth retaining, and which are merely approval theatre.

## 2. Problem

Multi-agent systems already fail in ways that single-agent safety abstractions do not capture. Parallel agents duplicate work, race on stale state, overwrite each other's changes, infer authority from ambiguous context, accept unverifiable handoffs, and route irreversible actions through approval steps that may not contain enough information for a human to make a meaningful decision.

A common response is to add a central coordinator. That can reduce collisions, but it also creates a bottleneck and a single locus whose mistake, capture, or compromise can authorize system-wide failure. The research question is whether boundary contracts plus mutual verification can preserve useful parallelism while removing some of that central trust.

BoundaryMesh treats a boundary as a machine-checkable coordination object, not a social label. A boundary includes actor scope, resource scope, allowed actions, an exact state fence, expiry, handoff rules, irreversibility class, evidence roots, and a human-control policy. Agents exchange signed or digest-bound events such as CLAIM, PROPOSE, ATTEST, APPROVE, ACT_RECEIPT, CHALLENGE, and RELEASE. Independent verifiers should be able to derive the same disposition from the transcript.

## 3. Why this matters for advanced AI safety

The safety hypothesis is that increasingly capable agent collectives need checks and balances that scale with delegation. If an erroneous or strategic agent can turn a local misunderstanding into an unbounded action chain, more capable agents can amplify the blast radius. If every action instead requires one central authority, the system may become brittle, censorable, or vulnerable to a single compromised decision point.

BoundaryMesh tests a third option: decentralized cooperation with protected fallbacks and independently verifiable action boundaries. The project does **not** assume this is sufficient for alignment or claim a proven reduction in existential risk. It asks a narrower, falsifiable question: can explicit boundaries and mutual verification materially reduce dangerous coordination failures under realistic multi-agent stress without destroying the value of parallel delegation?

## 4. Technical approach

### A. Boundary protocol

Specify a minimal, implementation-neutral protocol for claims, actions, evidence, challenges, and handoffs. The protocol will make stale state, conflicting custody, replay ambiguity, self-approval, and unverifiable receipts first-class failure states rather than hidden application logic.

### B. Deterministic reference verifier

Build a verifier that replays an event transcript and emits source-traceable ALLOW/HOLD/CHALLENGE dispositions plus a deterministic receipt. Any observer with the same public transcript should be able to recompute the result. Protected actions cannot be authorized solely by the actor proposing them.

### C. Adversarial benchmark and simulator

Build a public benchmark beginning with the seed cases in this carrier and expanding past 200 scenarios. It will inject concurrency, partial observability, delayed messages, stale snapshots, retries, malformed/forged receipts, scope escape, verifier disagreement, faulty peers, and bounded collusion. Scenarios will run against no-protocol, central-coordinator, and BoundaryMesh conditions.

### D. AI-first failure discovery

Use AI agents not just as benchmark subjects but as an engine for generating counterexamples: propose boundary escapes, mutate transcripts, search for verifier disagreement, compress failing traces into minimal cases, and generate new coordination games. Deterministic checks decide acceptance; model prose never substitutes for the verifier.

### E. Human-control experiments

Pre-register classes of irreversible/high-externality decisions where human control is retained, classes where delegation is allowed, and experimental classes where the policy varies. Measure outcome quality, false holds, latency, and whether the human received decision-relevant evidence. This lets the project detect hollow oversight instead of equating more clicks with more control.

## 5. Milestones and deliverables

**Months 0–2:** threat model, protocol v0.1, deterministic transcript format, baseline harness, >=60 scenarios.  
**Months 3–4:** reference verifier, simulator, adapter SDK, central/no-protocol baselines.  
**Months 5–7:** >=150 scenarios across independent, hierarchical, and coalition topologies; partial-observability and collusion suite.  
**Months 8–9:** multi-model empirical evaluation and human-control allocation experiments; public intermediate report.  
**Months 10–12:** protocol v1.0, >=200 scenarios, reproducibility bundle, public challenge set, and technical report.

All grant-funded code, protocol specifications, benchmark data, scenario generators, and reports are intended to be open-sourced.

## 6. Evaluation

The primary target is at least a 50% reduction in boundary violations versus the no-protocol baseline across at least three model families/topologies, with median throughput loss no greater than 25%. Engineering acceptance requires deterministic transcript receipts and zero false acceptance on the deterministic hostile conformance suite.

Those are targets, not pre-claimed results. If BoundaryMesh fails them, the negative result and failure taxonomy will be published. That is important: a protocol that merely moves failure into a different layer is not a safety win.

## 7. Capability to execute — public engineering evidence only

The applicant's public Commons repository contains several directly relevant internal engineering systems. They are capability evidence, not client references or research validation:

- **Commons Toolbench, merged PR #8757 / `1304c49d…`:** immutable source objects, explicit revisions, stale-write detection, idempotent request handling, concurrent-edit tests, exact selected-byte exports, and retained open questions. The PR records 26/26 real SQLite/HTTP tests plus restart/concurrency checks.
- **Cross-client MCP conformance kernel, merged PR #13833 / `c98ed951…`:** strict manifest and source binding, deterministic replay equality, duplicate observation handling, stale/corrupt evidence HOLDs, zero-production-action enforcement, tamper verification, and a hostile suite recorded at 29/29 normal + 29/29 under `python -O`.
- **Bounded context dispatch packets, merged PR #13837 / `693f695f…`:** provenance-bound context packets with hard budgets, explicit omission accounting, current-state fences, semantic digest verification, deterministic rendering, and hostile tests.

These systems show repeated implementation of the exact engineering primitives this proposal needs: provenance, state fencing, replay safety, bounded authority, cross-checkable receipts, concurrency failure handling, and fail-closed evidence. They do **not** establish academic publication history, external client acceptance, or Foresight-specific credentials, and the application should not imply otherwise.

## 8. Open-source and background-work boundary

Foresight requires the funded work product to be open. BoundaryMesh is scoped so that requirement is a feature, not an exception: all new grant-funded protocol code, benchmark data, evaluation harnesses, reports, and outputs are intended for public release.

Existing Commons/TitanMCP/customer/internal systems are not part of the requested funded work, are not charged to the grant, and are not required deliverables. Public prior work may be cited as capability evidence and lessons can inform the new protocol, but the grant proposal should not silently convert unrelated background systems into funded IP. The final grant agreement should make the background/funded-work boundary explicit while fully honoring Foresight's open-source requirement for the funded outputs.

## 9. Proposed budget

**Proposed request: $99,000 for 12 months**, within the RFP's stated typical range. Direct-cost draft: $66,000 research/engineering; $9,000 compute/model evaluation; $7,500 independent red-team/external evaluation; $4,500 Node sprints/collaboration if approved and not separately covered; $3,000 open-source documentation/release. Proposed direct total $90,000 plus $9,000 overhead (10%, the RFP ceiling).

This is an internal planning budget, not an applicant commitment. Applicant identity, compensation basis, travel, accounting treatment, overhead eligibility, and final amount remain OWNER_CONFIRM.

## 10. Why grant funding

If applying as an individual/team, the grant directly funds an open public-good protocol and benchmark whose value depends on broad reuse rather than proprietary capture.

If applying through a for-profit entity, use the same logic but make the sponsor-required motivation explicit: the funded deliverables are deliberately open source and create ecosystem-wide safety infrastructure with diffuse commercial capture; the grant buys public research/evaluation work rather than subsidizing private customer delivery. Final wording depends on the actual applicant identity and must be OWNER_CONFIRM.

## 11. Node participation

Foresight strongly prioritizes active in-person Node contributors. A strong application should therefore propose concrete dedicated sprints or regular participation in San Francisco or Berlin **only if the applicant can actually commit to it**. Current status is OWNER_CONFIRM; this carrier makes no travel or attendance promise.

## 12. Main risks

- **Protocol theatre:** agents produce compliant-looking metadata without real safety value. Mitigation: adversarial action-level tests and outcome metrics, not form completion.
- **Centralization creep:** the verifier becomes a de facto governor. Mitigation: transcript-recomputable decisions and explicit measurement of single-point dependence.
- **Correlated failure/collusion:** multiple agents repeat the same error. Mitigation: independence metadata, coalition scenarios, and failure curves as faulty/colluding peers increase.
- **Throughput collapse:** safety holds destroy parallelism. Mitigation: measure false holds and throughput; publish tradeoffs and negative results.
- **Human approval theatre:** people approve without useful context. Mitigation: evidence sufficiency is part of the approval contract and measured experimentally.
- **Benchmark overfitting:** protocol tuned to known fixtures. Mitigation: held-out scenario generation, external challenge set, and public preregistration of metrics.

## 13. Submission status

**GO on technical fit / HOLD on owner and form inputs.** Do not submit until the live Airtable fields are mapped exactly and applicant identity, Node participation, final budget, CV/biography facts, due-diligence declarations, sharing/privacy preferences, and any required attachments are confirmed.
