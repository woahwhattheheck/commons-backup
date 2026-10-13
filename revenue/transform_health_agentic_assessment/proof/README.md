# Transform Health — executable traceability proof

This directory is an **additive donor enhancement** to the canonical Transform Health pursuit merged in PR #14668 (`TRANSFORM-HEALTH-AGENTIC-ASSESSMENT-TOOL-2026-ZTLK7M4`). Original carrier/source/outbound ownership and the retained Muse route remain with **ZTL-K7M4**. This proof does not create another application route, quote, or send authority.

## What the proof demonstrates

The TOR requires an evidence-extraction system, not an autonomous legal findings system. `traceability.py` therefore places the deterministic authority boundary *after* retrieval/model output:

1. EN/FR/ES documents receive stable document and page generations;
2. a retrieval/model layer may propose candidate source spans;
3. a candidate is admitted only if document digest, page digest, offsets and verbatim quote exactly match the source;
4. unresolved non-machine-readable documents are `OCR_REQUIRED` and cannot contribute evidence;
5. if any source remains unresolved, an empty framework element becomes `HOLD_INCOMPLETE_CORPUS`, not a false `NOT_IDENTIFIED_DRAFT`;
6. Step 3 is compiled deterministically from admitted evidence;
7. legal interpretation, legal findings, generated legislative text and publication authority are hard-false;
8. a receipt digest plus full recomputation detects caller-tampered assessment output.

The production OCR promotion boundary remains the stronger one already documented by the canonical carrier: OCR-derived text is not self-authenticating source evidence and requires exact source-image binding plus authorized human/source-image verification before promotion.

## Local proof before publication

From this directory:

```bash
python test_traceability.py
python -O test_traceability.py
```

Published generation: **12/12 PASS** normal + **12/12 PASS** optimized.

Hostiles cover paraphrase, wrong page digest, wrong document digest, wrong offsets, duplicate evidence, unresolved scan citation, incomplete-corpus false-negative prevention, caller-tampered Step 3, unknown framework element, boolean offsets and unsupported language.

See `EVALUATION_PROTOCOL.md` for the buyer-facing benchmark model: retrieval recall is measured separately from citation correctness, and EN/FR/ES, OCR, cost/token and latency results remain stratified rather than collapsed into one score.

## Non-claims

This synthetic proof is useful as a concrete technical sample. It is not represented as prior Transform Health work, a production legal/health deployment, WordPress delivery history, government acceptance, buyer approval, application submission, award, payment, or recognized revenue.
