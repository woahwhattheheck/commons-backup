# Non-controlling proposal architecture

This is a **hypothesis-level structure**, not the University's required response format. Rebuild it around the controlling RFP once recovered.

## 1. Discovery and success contract

Begin with source/collection/workflow discovery, stakeholder goals, current tooling, data-access boundaries, PoC constraints, and explicit measurable acceptance criteria. Separate buyer policy decisions from vendor technical recommendations.

## 2. Source-grounded experiment design

Define one or more bounded experiments against lawfully supplied material. Preserve exact source identity/version, transformations, model/prompt/policy versions, and evaluation fixtures. Do not select OCR, RAG, metadata enrichment, summarization, entity extraction, search, or another AI pattern until the controlling use case supports it.

## 3. Provenance, abstention, and review controls

Every generated or retrieved output should be traceable to source records where the task permits. Missing evidence should abstain rather than invent facts. Records/policies designated for review should route to a human instead of being silently treated as answerable.

## 4. Comparative evaluation

Compare the PoC against buyer-defined baseline and success metrics. Capture failures as first-class evidence: unsupported answers, missed sources, stale-version use, wrong citations, review-routing misses, regressions after source/model changes, latency/cost if required, and operator workload.

## 5. Change and reproducibility package

Deliver exact source/config/version manifests, evaluation inputs/outputs, known limitations, change log, reproducible run instructions, and an evidence-backed recommendation. Keep experimental evidence separate from production-readiness claims.

## 6. Owner decision and next phase

Close with source-backed findings, unresolved risks, architecture/options, implementation prerequisites, and a bounded next-phase recommendation. A successful PoC should not silently become production authority.
