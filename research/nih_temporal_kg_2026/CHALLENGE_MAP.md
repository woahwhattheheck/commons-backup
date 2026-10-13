# NIH “It’s About Time” challenge map

Official source: https://www.nih.gov/challenges/its-about-time-temporal-reasoning-biomedical-knowledge-graphs-challenge

This document converts the public challenge criteria into **proof gates**. It does not assert registration, eligibility approval, benchmark superiority, biomedical validity, sponsor acceptance, or award status.

## Current challenge economics

The NIH Office of Data Science Strategy lists a **$1,000,000 total prize purse**. Phase 1 (“Innovative Concepts”) is scheduled for **October 5, 2026 through January 15, 2027** and may award **up to ten $25,000 prizes**. Phase 2 is scheduled for 2027–2028 with top awards of **$350,000 / $250,000 / $150,000**.

The challenge asks for approaches that represent and reason over temporal validity, events, evolving evidence, and time-respecting relationships in biomedical knowledge graphs. Phase 2 further expects empirical comparison against a static-KG baseline and rigorous evaluation.

## Criterion → current evidence → missing proof

| Challenge need | Current executable evidence | Missing proof before an external claim |
| --- | --- | --- |
| Represent temporal validity | `Fact.valid_from` / half-open `valid_to`; open-ended intervals | Biomedical schema/ontology adapter and real benchmark corpus |
| Distinguish event/evidence arrival from modeled-world time | Independent `observed_at` knowledge clock | Domain study showing this prevents meaningful biomedical leakage/errors |
| Handle evolving evidence | Append-only retract/supersede events; historical knowledge views remain reconstructable | Realistic guideline, pharmacovigilance, or evidence-update scenarios |
| Prevent future leakage | `known_at` gates every fact and correction | Benchmark quantifying static-baseline leakage vs temporal approach |
| Time-respecting relationships | Directed path search with non-decreasing hop time and per-edge validity checks | Biomedical reasoning task where temporal path validity affects correctness |
| Reproducibility / provenance | Canonical IDs bind source identity + SHA-256; deterministic JSON receipts | External source registry / ontology provenance adapter; signed provenance if authenticity is required |
| Correctness under hostile inputs | Strict JSON, duplicate-key and non-finite rejection, timestamp/source/event consistency checks | Independent benchmark/reference-oracle evaluation |
| Extensibility | Domain-neutral stdlib core; JSONL interchange | RDF*/SPARQL/PROV-O/OWL/BioPortal integration and performance characterization |
| Evaluation rigor | Deterministic tests and exact negative cases | Shared benchmark, static-KG baseline, ablations, seeded repeats, error taxonomy |

## What the current receipt layer proves

The receipt hash proves **self-integrity of the serialized receipt**: if a receipt is changed without recomputing its canonical SHA-256, verification fails. Semantic verification also rejects malformed/tampered fact IDs, non-monotone hop times, invalid intervals, future-observed facts, and other local contradictions encoded in the receipt.

It does **not** prove source authenticity, sponsor provenance, biological truth, or that a negative/no-path result is globally complete without the graph used to derive it. Those require separately bound source material, signatures/authority where appropriate, and benchmark evidence.

## First benchmark order

The next substantial lane should be a **static-vs-temporal benchmark harness**, not more feature surface.

Build a small, fully public/non-PHI temporal evidence corpus with at least three families:

1. **Guideline evolution** — a recommendation is valid for one interval, later superseded, and the test asks both “what was valid then?” and “what was known then?”
2. **Safety-signal evolution** — early weak evidence, later stronger evidence/retraction, with queries designed to expose future leakage.
3. **Temporal relationship chains** — individually valid edges whose naive static composition creates an impossible path because the validity windows do not overlap in time-respecting order.

Run two systems on the exact same query set:

- **STATIC:** collapse all facts/events into an ordinary graph using the latest available view;
- **TEMPORAL:** this bitemporal engine with exact query clocks.

Predeclare metrics before running:

- exact-answer accuracy;
- future-leakage errors;
- temporally impossible path errors;
- stale/retracted-fact errors;
- abstention/no-path correctness;
- deterministic repeat equality;
- runtime and peak-memory on the same host.

### Promotion gate

Do not claim an advantage unless the temporal system materially reduces at least one temporal-error class **without lowering exact-answer accuracy** on the non-temporal controls. If the static baseline ties correctness with materially lower complexity/runtime, treat that as a falsifier and redesign rather than polishing the submission narrative.

## Second integration order

Only after the benchmark gate passes:

- add an RDF*/SPARQL adapter and explicit mapping to W3C PROV-O / OWL-Time concepts where semantically appropriate;
- bind ontology/version provenance by exact digest;
- keep the internal two-clock contract independent of any one biomedical ontology;
- add import/export conformance fixtures rather than trusting parser success as semantic correctness.

## Learned-model order

Temporal embeddings or learned ranking are optional **ranking layers**, not replacements for the temporal truth contract. If added, they should return candidates/evidence into the deterministic layer, which enforces validity/knowledge cutoffs and produces the final auditable receipt.

A learned model is promoted only if it improves a predeclared benchmark metric and does not introduce future leakage or make correction history unreconstructable.

## Submission/readiness ceiling

Current repository state is **SOURCE PROTOTYPE ONLY**.

Still separate and unexecuted:

- NIH account/registration and Participation Agreement;
- definitive entrant eligibility/legal review;
- official benchmark/data acquisition under its terms;
- domain expert review;
- biomedical ontology adapter;
- static-vs-temporal benchmark evidence;
- Phase 1 concept narrative and any external submission;
- Phase 2 prototype evidence;
- any prize, acceptance, payment, or revenue recognition.
