# USAC IT-26-139 AI Consulting pursuit carrier

Owner/finalizer: **Z-ArchimedesFurnace-914014-J6R8 (`ZAFU-J6R8`) / GPT-5.6 Sol**  
Operation: `USAC-AI-CONSULTING-QUALIFICATION-ZAFUJ6R8-20260913`  
Issue: `#13985`

This directory is a **qualification and proposal-control carrier** for USAC RFP IT-26-139. It is not a proposal, bid, representation of qualifications, price, signature, submission, contract, award, payment, or revenue claim.

## Dated source follow-up — October 4, 2026

The [revised Q&A delta packet](../rfp_addenda_delta/packets/usac_it_26_139_20261004/README.md) records the later Q113/Q179/Q180 source changes and visible deletions. The September 30 deadline has passed; this source follow-up does not reopen the closed #13985 carrier or establish bidder qualifications.

The example below remains a historical September 13 evaluation. The separate current source-delta evaluation returns `SOURCE_REFRESH_REQUIRED` for an explicitly incomplete source set; the original manifest, qualification inputs and owner lineage remain unchanged.

## Why this carrier exists

USAC's official package makes the practical bidder gates unusually explicit:

- a four-month, FFP, strategic/assessment engagement;
- current-state AI strategy/governance/risk/readiness assessment;
- a three-year implementation strategy spanning statistical, generative and exploratory agentic AI;
- named key personnel including an AI Subject Matter Expert;
- **2–3 recent similar corporate past-performance contracts with reachable references**;
- technical, past-performance and price evaluation;
- four tightly page-limited proposal volumes;
- separate bid-sheet scenarios with and without AI when AI use is proposed;
- no AI tool/service/code use during performance without prior written USAC approval.

The Q&A makes the biggest go/no-go distinction explicit: individual experience at a prior employer is not corporate past performance, while a proposed teaming partner/subcontractor's qualifying corporate past performance may be evaluated.

## Current truthful state

`sample_facts.json` is intentionally non-qualifying. No TokenJunkieLabs/Bryce corporate qualification, reference, key-personnel, pricing, signature, insurance/financial-responsibility, or submission fact is inferred.

The source manifest is **official-URL bound, not exact-byte bound**. The execution environment verified the current USAC procurement listing plus the public RFP/Q&A, but could not materialize every attachment byte. Any real proposal finalization must re-fetch the official procurement page and all attachments, record exact hashes, and reconcile any addenda/currentness.

## Run

```bash
python revenue/usac_ai_consulting/qualification.py \
  --manifest revenue/usac_ai_consulting/source_manifest.json \
  --facts revenue/usac_ai_consulting/sample_facts.json \
  --as-of 2026-09-13T14:45:00Z
```

Expected default decision: `HOLD`.

The compiler can emit `PRIME_READY` only when at least two qualifying **prime-held** corporate past-performance contracts plus mandatory source, identity, US-performance and key-personnel gates are proven. It emits `TEAMING_REQUIRED` when the prime lacks that floor but real qualifying partner/subcontractor corporate past performance can reach it. These labels are bidder-path evidence only: `submission_authority` is always false.

Use `--require-submission-ready` in CI/in a proposal packaging pipeline to fail unless a non-HOLD route also has all local submission-evidence gates completed.

## Files

- `source_manifest.json` — controlling public source inventory and byte-binding truth.
- `requirements.json` — source-located compliance register.
- `sample_facts.json` — deliberately unproven bidder facts.
- `qualification.py` — deterministic fail-closed route/readiness compiler.
- `TECHNICAL_APPROACH.md` — source-mapped technical architecture, not buyer claims.
- `TEAMING_BRIEF.md` — what a partner must actually contribute.
- `PROPOSAL_SKELETON.md` — four-volume assembly plan and no-fabrication rules.
- `tests/test_usac_ai_consulting.py` — hostile qualification tests.
