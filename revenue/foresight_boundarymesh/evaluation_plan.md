# BoundaryMesh evaluation plan

## Threat model

BoundaryMesh is evaluated under benign concurrency, accidental faults, partial observability, strategic gaming, and bounded collusion. It does not assume every agent is honest, identical, synchronized, or connected to one central supervisor. The project studies coordination infrastructure, not model-weight alignment.

Key failure classes: duplicate custody, scope escape, stale-state actions, replay ambiguity, forged/unverifiable receipts, verifier disagreement, expired authority, self-approval of protected actions, correlated/colluding attesters, information overload presented as human oversight, and recovery after a conflicting action proposal.

## Experimental conditions

Every scenario is run under at least these coordination conditions where feasible:

1. **No protocol** — agents receive only task text and shared provider access.
2. **Central coordinator baseline** — one privileged coordinator serializes or approves work.
3. **BoundaryMesh** — agents use explicit boundaries, state fences, independent attestations, transcript verification, challenges, and handoffs.
4. **BoundaryMesh + adaptive human-control policy** — protected decision classes retain or release human control under a pre-registered rule.

Model evaluation should span at least three distinct model families or capability tiers, and at least three topologies: independent peers, hierarchical delegation, and coalition/market-style routing. Exact providers are selected later and disclosed in the reproducibility manifest.

## Metrics

Safety/coordination: boundary-violation rate, unsafe-action accept rate, stale-state commit rate, forged-receipt accept rate, duplicate-work rate, verifier disagreement, and conflict recovery time.

Usefulness: benign-action false-hold rate, task completion rate, latency, token/compute cost, and coordination throughput.

Decentralization: fraction of protected actions whose disposition can be independently recomputed from public evidence; number of privileged components whose compromise is sufficient to authorize a protected action; resilience as faulty/colluding-agent count increases.

Human empowerment: outcome delta, latency delta, and reversibility under human-required vs delegated conditions. A human click is not counted as meaningful oversight if the approval packet lacks the evidence necessary to contest the action.

## Pre-registered success and negative-result rule

Engineering acceptance requires deterministic transcript receipts and zero false acceptance in the deterministic hostile conformance suite.

Empirical target: at least 50% lower boundary-violation rate than the no-protocol baseline across at least three model families/topologies while keeping median throughput loss at or below 25%. This is a target, not a claimed result. If it is not met, publish the negative result, scenario traces, and failure taxonomy rather than tuning the benchmark after seeing outcomes.

## Milestones

- **M0 / month 1:** threat model, protocol primitives, baseline harness, 24 seed scenarios, preregistration draft.
- **M1 / month 2:** protocol v0.1 and deterministic transcript/verifier format.
- **M2 / month 4:** simulator + adapter SDK + >=60 scenarios; no-protocol and central-coordinator baselines.
- **M3 / month 7:** >=150 scenarios, collusion/partial-observability suite, multiple topologies.
- **M4 / month 9:** multi-model empirical run + human-control experiments; public intermediate report.
- **M5 / month 12:** v1.0, >=200 scenarios, reproducibility bundle, technical report, and public challenge set.

## Reproducibility and safety boundaries

All grant-funded protocol code, benchmark data, scenario generators, manifests, and aggregate outputs are intended for public release. Provider credentials, private customer data, unrelated internal systems, and security-sensitive secrets are excluded. External actions in the benchmark are simulated or sandboxed unless a separately approved harmless test environment is explicitly documented.
