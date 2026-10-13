# Executable-proof evaluation protocol

This protocol supplements the canonical Transform Health carrier. It does not replace its application packet, pricing, qualification matrix, Muse state, or outbound owner.

## Why split metrics

The TOR asks for accuracy, completeness, traceability, hallucination control, cost and processing-time evidence. Those are distinct failure modes; one blended “accuracy” number can hide a retrieval miss behind a fluent answer.

## Frozen benchmark

Use buyer-approved existing country assessments and source legislative/regulatory documents. Freeze per run:

- exact document bytes/generation and machine-readability state;
- framework/Core Elements/Blueprint generation;
- human-reviewed expected evidence spans where available;
- retrieval/model/prompt configuration;
- deterministic Step-3 rules generation;
- token/page/call/cost ceilings.

Report by country, language (EN/FR/ES), document type, machine-readable vs OCR, and corpus-size band.

## Retrieval completeness

Measure **evidence recall@k** before evaluating model fluency: of human-reviewed expected source spans, what fraction appear inside a retrieved top-k segment for the correct framework element? Keep a miss ledger classified as parsing, OCR, language, indexing, query, ranking, or budget-cap failure.

The initial threshold should be negotiated after a baseline on Transform Health’s actual corpus rather than invented before seeing it.

## Evidence/citation correctness

For every admitted item measure:

- correct document generation;
- correct page generation;
- exact start/end offsets;
- quote equality with source bytes/text;
- evidence precision after human review;
- duplicate/cross-generation rejection.

The deterministic traceability layer can target **zero admitted unsupported/paraphrased provisions** because a candidate that is not an exact source span is rejected rather than repaired into a plausible sentence.

## Scans / OCR

The proof deliberately refuses evidence from a `machine_readable=false` source and returns `OCR_REQUIRED`. In production, OCR-derived text must remain a candidate bound to the exact source image/page generation and follow the canonical carrier’s human/source-image verification contract before promotion to verified evidence.

Until that promotion, an empty framework result must be `HOLD_INCOMPLETE_CORPUS`, never a substantive `NOT_IDENTIFIED_DRAFT`.

Track OCR routing rate, successful-verification rate, human corrections affecting evidence, and unresolved HOLDs.

## Deterministic Step 3

For a fixed reviewed evidence set and rules generation:

- repeated compilation is canonical-identical;
- changed evidence changes only derived evidence IDs/count/status;
- caller-tampered Step-3 output fails recomputation verification;
- legal-interpretation/findings/publication authority remains false;
- unresolved corpus gaps prevent false negative status.

## Cost / latency

Per job and stage capture source pages/bytes, retrieved segments, model calls/retries, input/output tokens, estimated + realized provider cost, cache key/hit state, parsing/OCR/retrieval/extraction/verification duration, and budget-termination reason.

Test both typical and maximum agreed corpus sizes. Hitting a configured ceiling must produce a stable partial/HOLD state that identifies unprocessed scope; it must not silently summarize the remainder.

## UAT sequence

1. baseline current/manual country assessments;
2. shadow-run drafts with no publication authority;
3. reviewer accept/reject + retrieval-miss labeling;
4. EN/FR/ES pilot countries including at least one scan-heavy corpus;
5. typical/max corpus budget and latency tests;
6. registration, consent, upload, status/error, download and deletion workflow UAT;
7. launch gate with unresolved severity-1 traceability/security/privacy defects held.

## Proof commands

From `revenue/transform_health_agentic_assessment/proof`:

```bash
python test_traceability.py
python -O test_traceability.py
```

The published generation was locally exercised as **12/12 PASS** in normal mode and **12/12 PASS** with `python -O` before GitHub publication.
