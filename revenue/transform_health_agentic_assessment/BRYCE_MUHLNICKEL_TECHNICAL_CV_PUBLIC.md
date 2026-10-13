# Bryce Muhlnickel

**Systems / Computation Engineer - Token Junkie Labs**

Public engineering portfolio: https://github.com/woahwhattheheck/commons

## Profile

Systems/computation engineer focused on language-model systems, custom agentic workflows, deterministic verification, evidence lineage, and software that fails closed when source, state, or authority is incomplete. Current work emphasizes practical controls around generated output: source-bound evidence, reproducible receipts, human-review boundaries, hostile-case testing, replay/currentness checks, and bounded automation rather than unsupported autonomous authority.

For the Transform Health consultancy, the strongest fit is the technical problem: design and delivery of an evidence-grounded document workflow in which model/retrieval output is treated as a candidate, verbatim source evidence is independently verified, scanned-document/OCR cases have an explicit failure and promotion path, downstream summaries are derived through transparent rules, and accuracy/cost/latency are measured against a frozen representative corpus.

## Relevant technical capabilities

### Agentic / language-model systems
- Closed-schema evidence contracts for agentic evaluations.
- Exact model/build/rubric/trace/result bindings and reproducible verification receipts.
- Human review, safety, observability, and tool-call evidence as independently bound layers rather than model assertions.
- Explicit authority ceilings: technical readiness does not silently become production, compliance, buyer, legal, or financial authority.

### Evidence grounding, document workflows, and provenance
- Source/snapshot identity and digest binding.
- Exact quotation/citation verification patterns.
- Deterministic downstream state derived only from admitted evidence.
- OCR-derived text modeled as a non-authoritative candidate until exact source-image binding plus an independent image-grounded or authorized human check.
- Explicit `HOLD` / `OCR_REQUIRED` / incomplete-corpus states rather than forced findings.

### Software reliability and security-oriented implementation
- Strict JSON/schema validation and rejection of duplicate/unknown or non-canonical inputs.
- Bounded, no-follow file ingress; stable file-identity checks; byte-for-byte re-read validation.
- Atomic/single-output publication designs with destination-race and symlink defenses.
- Deterministic receipt hashing, currentness checks, replay collapse, and conflicting-payload quarantine.
- Provider-neutral architecture and separation between caller-supplied evidence and verifier-owned state.

### Benchmarking, hostile testing, and UAT design
- Deterministic synthetic acceptance corpora with normal, tool-using, adversarial, degraded-observability, and lineage-fault cases.
- Hostile suites covering stale/future evidence, cross-build/trace/result substitution, malformed input, tamper, unsafe state, missing review, and file-custody attacks.
- Transform Health-specific proposed metrics: relevant-span recall, evidence precision, citation correctness, unsupported-positive rate, false `Not identified`, OCR promotion error, latency, token use, cost, and multilingual artifact completeness.
- Buyer-specific thresholds are to be agreed and measured against Transform Health's representative corpus rather than invented before access to buyer data.

## Selected public technical work

### Agentic GenAI Evaluation Evidence Gate
https://github.com/woahwhattheheck/commons/tree/main/revenue/agentic_genai_evaluation_gate

Deterministic pre-release evidence control for agentic GenAI systems. Binds evaluation-set generation, agent build, rubric, traces, results, human review, safety, observability and tool-call observations into canonical receipts. Includes a 180-scenario deterministic synthetic acceptance portfolio and hostile tests for evidence substitution, staleness, tamper, malformed input, and file-custody failures.

### Agentic GxP Lineage Evidence Gate
https://github.com/woahwhattheheck/commons/tree/main/revenue/agentic_gxp_lineage_gate

Offline validation sidecar for generated review artifacts. Binds source snapshots, model/tool/prompt versions, query/result hashes, change-control timing and four-eyes review; collapses exact replay and quarantines conflicting same-case payloads. Includes a 120-case deterministic synthetic corpus with eight fault classes. The artifact is intentionally buyer-neutral and does not claim production validation or regulatory certification.

### Transform Health Traceability Proof
https://github.com/woahwhattheheck/commons/pull/15081

Donor proof layer for the current Transform Health pursuit: deterministic source/citation/Step-3 compilation, hostile tests, and a measurable retrieval/citation/OCR/token-cost/latency UAT protocol. Retrieval/model output remains untrusted until the claimed source evidence verifies; unresolved scans remain explicit non-authoritative states.

### Snohomish AI Governance Packet Gate
https://github.com/woahwhattheheck/commons/tree/main/revenue/snoco_ai_governance_packet_gate

Evidence-control pattern for trusted/untrusted source separation, deterministic requirement/evidence state, fail-closed authority claims, and tamper-resistant receipt verification.

## Transform Health delivery posture

The proposed implementation is a provider-neutral backend behind a thin WordPress-facing registration/upload/status/download workflow, with asynchronous document processing, bounded token/API/cost ceilings, English/French/Spanish input and output behavior, explicit consent/retention/deletion controls, benchmark/UAT before promotion, and technical handover.

### Explicitly not claimed as prior experience
- prior Transform Health engagement;
- legal practice or legal-interpretation authority;
- prior health-data-governance or health-policy consultancy;
- prior production multilingual legal-OCR deployment;
- prior production WordPress implementation.

Those gaps are not hidden. The delivery design compensates by keeping legislative interpretation and final publication with authorized Transform Health reviewers; using the buyer's existing framework as the normative source; validating WordPress/hosting/data-handling constraints during orientation; and requiring representative-corpus testing before launch.

## Working style

- Evidence before claim.
- Bounded deliverables and explicit acceptance criteria.
- Reproducible test artifacts and failure states.
- Human authority preserved where interpretation or publication matters.
- No production credentials or buyer data required for qualification; access and data handling are agreed before implementation.
