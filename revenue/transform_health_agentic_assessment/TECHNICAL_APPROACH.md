# Technical approach — evidence-grounded legislative assessment agent

## 1. Design objective

Build a low-volume, maintainable document-intelligence service that helps a human reviewer populate Transform Health's existing Step 2 assessment and derive Step 3 summaries without turning an LLM, parser, or OCR system into a legal decision-maker or source authority.

The system should answer one mechanical question reliably:

> What source text in the uploaded corpus is relevant to each pre-defined assessment element, where exactly did it come from, and what deterministic worksheet state follows from the verified extraction?

It should not answer:

> What does the law ultimately mean, or what legal conclusion should a country adopt?

That authority remains with the human reviewer and Transform Health's framework.

## 2. Architecture

### 2.1 WordPress-facing layer

Keep WordPress thin:

- registration / access-request form;
- authenticated upload page;
- consent and retention acknowledgement;
- job-status page;
- result download page;
- administrator approval / revocation controls where required.

Document processing should run behind a narrow authenticated API rather than inside the WordPress PHP request lifecycle. This keeps long-running parsing/LLM jobs, secrets, retries, and provider-specific SDKs out of the CMS.

Suggested integration shapes, selected after environment review:

1. small custom WordPress plugin using REST endpoints and signed job IDs; or
2. theme-independent shortcode/block backed by a separate API service.

No model/provider key should be exposed to the browser or stored in page source.

### 2.2 Backend services

A deliberately small service boundary:

1. **Ingress service**
   - accepts Step 1 worksheet plus supported source documents;
   - validates content type, extension, size/page limits, malware-scan outcome where available, and per-user/job quotas;
   - computes content digests and assigns immutable source IDs.

2. **Document normalizer**
   - extracts machine-readable text when available;
   - detects scanned / non-machine-readable pages;
   - preserves the original source page or image identity, page boundaries, original-language content, parser/OCR version, and source coordinates;
   - routes scanned pages through the approved OCR path only as a derived representation;
   - records a separate digest for OCR output and never treats OCR text as self-authenticating source text;
   - if the source image cannot be retained or reviewed under the agreed environment, marks the page `UNPROCESSABLE` rather than manufacturing source fidelity.

3. **Retrieval / candidate-evidence service**
   - segments documents with page-aware boundaries;
   - combines deterministic lexical retrieval with semantic retrieval so recall does not depend on one embedding query;
   - associates each query with a fixed Core Element / standard-interpretation identifier;
   - records candidate-set provenance and retrieval scores;
   - supports a high-recall fallback when confidence/coverage is insufficient.

4. **Evidence extractor**
   - provider-neutral model adapter;
   - structured output schema only;
   - may return candidate verbatim evidence spans plus source coordinates and extraction confidence;
   - may return `NOT_IDENTIFIED` when no support is found;
   - must not create or paraphrase legislative provisions;
   - labels candidates from OCR-derived text as `OCR_DERIVED_CANDIDATE`, never directly as verified source evidence.

5. **Evidence verifier**
   - for native machine-readable text, independently checks that every quoted span exists text-normalization-equivalently in the named source page;
   - for scanned/image pages, binds the candidate to the exact source-image/page digest and requires a separate image-grounded verification step or explicit human visual confirmation against the source image before promotion;
   - an OCR span that only matches OCR output remains `OCR_DERIVED_CANDIDATE` / `NEEDS_HUMAN_REVIEW`; OCR confidence alone is never promotion authority;
   - if image-grounded verification or human confirmation cannot be obtained, the candidate remains non-authoritative or the page becomes `UNPROCESSABLE` rather than `VERIFIED_EVIDENCE`;
   - rejects missing, altered, cross-document, cross-page, or out-of-range citations;
   - rejects unrecognized assessment IDs and unknown schema fields;
   - requires every positive Step 2 entry to carry at least one source-verified evidence span;
   - preserves the exact source-language quotation even when a translated reviewer aid is also shown.

6. **Deterministic Step 3 reducer**
   - consumes only Step 2 states whose evidence reached `VERIFIED_EVIDENCE` under the native-text or image/human verification path;
   - never consumes a bare OCR-derived candidate;
   - applies Transform Health-approved, versioned deterministic rules;
   - does not ask the generative model to decide the final summary state;
   - includes the rule-set version/digest in generated outputs.

7. **Artifact renderer**
   - creates the draft Step 2 worksheet, Step 3 worksheet, and human-readable summary report;
   - supports English, French, and Spanish input **and output** workflows in the initial version;
   - preserves original-language source quotations while localizing framework labels, status text, instructions, and generated report structure into the selected output language;
   - includes source IDs, page references, source-representation type (`NATIVE_TEXT` or `SOURCE_IMAGE_WITH_VERIFICATION`), and evidence quotations;
   - marks draft / human-verification status prominently.

8. **Job ledger**
   - records state transitions, model/provider/version, prompt/rule version, source digests, page/image digests, OCR-derived digests where applicable, verification method, processing time, token counts, estimated/actual API cost, errors, retry count, and deletion state;
   - stores no more document content than the approved retention policy requires.

### 2.3 Storage and queues

For low/intermittent volume, prefer managed primitives over a large always-on cluster:

- encrypted object storage for bounded upload/result retention;
- small relational store for users, jobs, source metadata, and audit state;
- managed queue/background worker for asynchronous processing;
- application-level retention/deletion worker;
- structured logs and metrics with document text excluded by default.

The exact cloud is intentionally not prescribed before reviewing Transform Health's hosting, residency, privacy, and cost constraints.

## 3. Evidence contract

A positive extraction should be impossible to persist without a citation object equivalent to:

```json
{
  "assessment_element_id": "stable-framework-id",
  "source_id": "sha256-bound-document-id",
  "source_digest": "sha256:...",
  "page": 12,
  "source_representation": "NATIVE_TEXT",
  "normalized_span_start": 3812,
  "normalized_span_end": 4094,
  "verbatim_quote": "...",
  "parser_version": "...",
  "language": "fr",
  "extraction_state": "EVIDENCE_CANDIDATE"
}
```

For native text, promotion to `VERIFIED_EVIDENCE` requires the verifier to re-open the source bound by digest and prove the quote and coordinates agree.

For a scanned page, the candidate additionally binds the exact source-image/page digest and OCR derivation metadata. A mere match against OCR text is insufficient. The candidate stays `OCR_DERIVED_CANDIDATE` until either (a) a separately designed image-grounded verifier validates the cited source image under the agreed acceptance criteria, or (b) an authorized human visually confirms the quote against that exact image/page. The verification method and actor/system evidence are retained. Without one of those paths, the candidate cannot feed positive Step 2 or Step 3 state.

A model-produced paraphrase or machine translation can be displayed only as a clearly separate reviewer aid if Transform Health wants it; it must never replace the source quotation or satisfy the evidence requirement.

## 4. Hallucination and unsupported-output controls

Layer controls rather than relying on one prompt:

- closed JSON schema with stable framework IDs;
- fixed system instructions that extraction is non-interpretive;
- source-aware retrieval and bounded context;
- exact/verifiable quotation requirement;
- independent post-model citation verification;
- OCR provenance gate that prevents OCR output from self-certifying source fidelity;
- deterministic Step 3 reducer;
- fail-closed handling for unknown IDs, malformed citations, missing source spans, unverified OCR spans, parser failures, and quota exhaustion;
- reviewer-visible `NOT_IDENTIFIED`, `OCR_DERIVED_CANDIDATE`, `UNPROCESSABLE`, and `NEEDS_HUMAN_REVIEW` states instead of forced completion;
- no autonomous publication of a country assessment;
- explicit human verification before a draft can be treated as reviewed.

## 5. Retrieval and recall strategy

The buyer explicitly asks for a trade-off between token efficiency and missed relevant text. Treat that as a measured engineering problem.

### Candidate generation

For each assessment element:

1. lexical search over normalized text using framework terms, known synonyms, and jurisdiction-neutral legal vocabulary;
2. semantic retrieval using a provider-swappable embedding adapter;
3. union, de-duplication, and page-neighbor expansion;
4. optional document-level synopsis only for retrieval planning, never as evidence;
5. bounded model extraction over the candidate set.

### Recall backstop

If candidate coverage is below an agreed threshold, or a benchmark shows systematic misses, use one or more escalation modes:

- wider top-k;
- section-aware expansion;
- second independent query formulation;
- document sweep for short corpora;
- reviewer flag that the automated result is incomplete rather than silently returning `NOT_IDENTIFIED`.

### Measurement

On a gold set of existing country assessments, measure:

- relevant-span recall;
- evidence precision;
- assessment-element coverage;
- citation correctness;
- unsupported-positive rate;
- false `NOT_IDENTIFIED` rate;
- OCR/image-verification error rate separately from native-text extraction;
- cost and latency by page count/language.

The proposal should not promise a numeric target before Transform Health supplies representative assessment data. Targets should be agreed at design stage, measured against the same frozen benchmark, and reported with confidence intervals where useful.

## 6. Multilingual handling

Initial languages: English, French, Spanish for both inputs and outputs.

Rules:

- preserve original-language source text and citation;
- language-detect per document/page where necessary;
- use multilingual retrieval or language-specific query expansion;
- keep any translated reviewer aid separate from the evidentiary quote;
- version prompts/rules per language when they diverge;
- render downloadable Step 2, Step 3, and summary-report labels/instructions in the selected supported output language while preserving original-source quotations;
- include language-stratified benchmark results so acceptable aggregate performance cannot hide one failing language.

## 7. Scanned / non-machine-readable documents

A scanned-document pathway must be explicit rather than magical:

1. detect text insufficiency per page;
2. bind the exact source-image/page bytes to a digest before OCR;
3. route to the approved OCR engine if OCR is enabled for that tenant/job;
4. retain page-level OCR confidence, OCR-engine/version metadata, OCR-output digest, and source-image digest;
5. classify extracted OCR spans as `OCR_DERIVED_CANDIDATE`, regardless of OCR confidence;
6. require independent image-grounded verification or authorized human visual confirmation against the exact bound source image before `VERIFIED_EVIDENCE`;
7. flag low-confidence or structurally ambiguous pages for human review even if an automated image-grounded check exists;
8. if OCR is unavailable, the source image cannot be retained/verified, or verification fails policy, return `UNPROCESSABLE` / `NEEDS_HUMAN_REVIEW` with page range and reason.

OCR confidence is routing metadata, not source-fidelity authority. The renderer must distinguish native text from OCR-derived candidate text, and Step 3 must never consume unverified OCR-derived evidence.

## 8. Cost controls

Every assessment receives a configurable budget envelope:

- maximum documents;
- maximum total pages;
- maximum file size;
- maximum OCR pages;
- maximum retrieval candidates per element;
- maximum model tokens and model calls;
- absolute API-cost ceiling;
- maximum runtime/retry count.

The orchestrator checks projected and consumed cost before each expensive stage. Crossing the cap produces a durable `COST_CAP_REACHED` job state with completed partial stages preserved for diagnostics; it does not continue charging or fabricate a complete assessment.

Where provider capabilities allow it, use prompt caching and asynchronous/batch execution only when they measurably reduce cost without weakening isolation or traceability.

Commercially, the proposed **USD 15,000** is the total professional implementation fee for the stated consultancy deliverables. Any buyer-procured or buyer-approved third-party model, OCR, hosting, storage, translation, or messaging service is outside that professional fee only if Transform Health agrees the service and a written operating-cost cap/change order in advance. No uncapped or surprise operating cost is committed.

## 9. Provider-neutral model interface

Define a narrow adapter contract such as:

```text
extract_evidence(request, schema, budget) -> structured extraction
embed(text_batch) -> vectors
```

Provider-specific request/response objects stay behind the adapter. Persist provider/model/version in the job ledger, but do not encode model-specific fields into the Step 2/Step 3 domain schema.

This allows model changes without redesigning the assessment framework and supports A/B benchmarking before a provider switch.

## 10. Security / privacy baseline

Final controls depend on Transform Health's hosting and data classification, but the design baseline is:

- least-privilege service identities;
- separate browser, WordPress, API, worker, and storage trust boundaries;
- encrypted transit and storage;
- secrets only in managed secret storage / server-side runtime;
- signed/bounded upload and download access;
- explicit user consent and retention policy;
- configurable deletion schedule and administrator deletion path;
- audit events for registration approval, upload, processing, download, retention extension, and deletion;
- no provider training/data reuse unless contractually permitted by Transform Health;
- no document text in routine analytics/error logs;
- dependency and image patching process;
- abuse/rate limits even at low expected volume.

## 11. Accuracy / UAT plan

Freeze a benchmark set with Transform Health before tuning.

Each benchmark case should bind:

- exact input document digests;
- exact source-image/page digests for scanned cases;
- reference Step 2 evidence spans;
- expected Step 3 deterministic output;
- language and scan/native-text category;
- known hard cases / ambiguous examples.

Test classes:

1. happy-path native text;
2. scanned/OCR cases, including deliberately high-confidence OCR substitutions that must not self-certify as source evidence;
3. multilingual input and output cases;
4. long-document retrieval misses;
5. semantically similar but irrelevant text;
6. missing evidence / legitimate `NOT_IDENTIFIED`;
7. malformed or unsupported files;
8. citation transplantation/tamper attempts;
9. cost-cap termination;
10. provider/model version change regression;
11. OCR candidate without image/human verification, which must remain non-authoritative.

Report at minimum precision, recall, citation correctness, unsupported-positive rate, processing time, token consumption, and cost per assessment, stratified by language and native-text/OCR path. UAT feedback is tracked separately from benchmark scoring so user preference does not silently rewrite accuracy criteria.

## 12. Milestone plan

### By 30 October 2026

- environment and framework review;
- threat/data-flow model;
- frozen domain schemas;
- access/consent/retention decisions;
- provider-neutral architecture;
- hosting recommendation;
- benchmark/test-plan agreement;
- OCR source-fidelity verification design;
- multilingual input/output contract;
- cost model.

### By 30 November 2026

- ingestion/normalization;
- retrieval;
- structured evidence extraction;
- native-text citation verifier;
- scanned-page OCR candidate + image/human verification gate;
- deterministic Step 3 reducer;
- cost-cap enforcement;
- command/API-level acceptance tests.

### By 18 December 2026

- WordPress-facing registration/upload/status/download flows;
- authenticated API integration;
- English/French/Spanish input and output UX paths;
- administrative job visibility and error handling.

### By 31 January 2027

- frozen benchmark results;
- OCR/scanned-path evaluation;
- language-stratified accuracy report;
- UAT;
- remediation and regression run;
- actual cost/latency report.

### By 26 February 2027

- production deployment in agreed environment;
- user guidance;
- operator runbook;
- technical documentation;
- maintenance/monitoring recommendations;
- handover session.

## 13. Questions to resolve at inception

1. What file formats and maximum corpus sizes occur in real country assessments?
2. Are uploaded laws/regulations always public, or can drafts/confidential documents appear?
3. What retention/deletion window is acceptable, including for source-page images needed to verify OCR-derived candidates?
4. What is the current WordPress host and can it run a custom plugin / outbound API calls?
5. Is a separate cloud account/project available for document processing?
6. What existing Step 2/Step 3 file formats must be preserved exactly?
7. Are historical country assessments available as a benchmark/gold set, with source documents?
8. How should conflicting/overlapping provisions be represented without turning extraction into legal interpretation?
9. Is machine translation acceptable as a reviewer aid, and if so which provider/data terms are acceptable?
10. What registration approval and publication-consent workflow does Transform Health want?
11. Which providers/regions are disallowed for uploaded documents?
12. What operating-cost ceiling per country assessment should terminate a job?
13. What source-image review or image-grounded verification method is acceptable before OCR-derived text can become verified Step 2 evidence?
14. Should users choose one output language per assessment, or should the system emit parallel English/French/Spanish Step 2, Step 3, and report artifacts?

These are design inputs, not reasons to delay the application. The proposal can state explicit assumptions and bind final implementation choices to the orientation milestone.
