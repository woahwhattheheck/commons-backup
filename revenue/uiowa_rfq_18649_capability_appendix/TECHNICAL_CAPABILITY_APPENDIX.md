# Technical capability appendix — RFQ 18649 support

**TJLabs preparation artifact · UIOWA-137 · source snapshot `04dfec1281f91b4f050e4b93ac49c5925eb02386`**

This appendix shows four concrete technical capabilities relevant to an assessment engagement: organizing evidence, comparing observations without false precision, preserving finding-to-source traceability, and preparing reviewable report language. Each example is working repository material pinned to exact source bytes. The examples are **synthetic rehearsal artifacts and original engineering work**. They are not University of Iowa findings, a client outcome, institutional endorsement, certification, degree, or claim of prior engagement performance.

## 1. Evidence organization that keeps strengths, gaps, and unknowns distinct

**Business use.** An assessment accumulates policies, process records, system evidence, interviews, and examples from different groups. Review becomes unreliable if that material is reduced to prose before its source, scope, and uncertainty are preserved.

The synthetic evidence collection uses stable fact IDs and a source manifest across ESS-, RIS-, and IAM-like fictional services. Provider readback of the pinned files observed **24 facts, 10 evidence documents, and all 12 service × assessment-area cells**. The fact ledger contains **12 synthetic strengths, 9 synthetic gaps, and 3 unknowns**; unknowns remain explicit rather than becoming zero scores or assumed failures.

Pinned sources:

- [fact ledger](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_synthetic_collection/facts.json)
- [evidence manifest](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_synthetic_collection/evidence_manifest.json)
- [12-cell coverage matrix](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_synthetic_collection/coverage_matrix.csv)
- [collection validator](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_synthetic_collection/validate_collection.py)

Reproduce the structural check:

```bash
cd revenue/uiowa_rfq_18649_synthetic_collection
python3 validate_collection.py .
```

**What this demonstrates:** a repeatable way to keep source identity, assessment scope, evidence state, and unknowns available to later analysis. It does **not** demonstrate anything about actual University practice; the collection labels itself `FICTIONAL_REHEARSAL_ONLY`.

## 2. Comparison without hiding a critical gap or weak evidence coverage

**Business use.** A single average can make a mostly strong area look safe even when one critical practice is weak, or can imply maturity when most eligible criteria were never assessed. The comparison model therefore keeps ordinal observations, coverage, confidence, applicability, and material gaps separate.

The pinned worked table contains three deliberately different cases:

| Rehearsal case | Observed coverage | Composition result | Why it matters |
| --- | ---: | --- | --- |
| four high observations + one critical gap | 100% | `critical_gap_present` | the critical weakness is not averaged away |
| only 4 of 10 eligible criteria assessed | 40% | `insufficient_coverage` | strong samples do not become an area-wide conclusion |
| ESS/RIS/IAM observations span ranks 1–4 | 100% | `mixed_practice` | service differences remain visible |

Pinned sources:

- [worked decision table](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_rating_model/22-worked-decision-table.csv)
- [deterministic composition engine](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_rating_model/rating_model.py)

Reproduce one case:

```bash
cd revenue/uiowa_rfq_18649_rating_model
python rating_model.py synthetic_case_critical_gap.json \
  --json-out /tmp/uiowa-137-rating.json \
  --markdown-out /tmp/uiowa-137-rating.md
```

**What this demonstrates:** auditable comparison logic that exposes uncertainty and variation instead of manufacturing a precise composite score. The maturity anchors and evidence-confidence judgments remain separate inputs; the engine does not invent them.

## 3. Finding-to-source traceability

**Business use.** A reviewer should be able to challenge a sentence in a report and follow it back through the finding to the exact evidence records and locators. Recommendations should link to findings rather than replacing the evidence chain with a new narrative.

Provider readback of the pinned rehearsal observed **8 evidence records → 3 findings → 2 recommendations → 5 report statements**. The three fictional cases intentionally include a supported strength, an evidence gap, and a representative-coverage limitation. The source language is narrow: missing retained evidence is not treated as proof that an undocumented activity never occurred.

Pinned sources:

- [evidence register](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_traceability_rehearsal/evidence.csv)
- [findings](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_traceability_rehearsal/findings.csv)
- [recommendations](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_traceability_rehearsal/recommendations.csv)
- [statement trace map](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_traceability_rehearsal/trace-map.csv)
- [trace validator](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_traceability_rehearsal/validate_trace.py)

Reproduce the link check:

```bash
cd revenue/uiowa_rfq_18649_traceability_rehearsal
python validate_trace.py .
```

The checked-in run contract reports `evidence=8 findings=3 recommendations=2 statements=5` followed by `trace validation: PASS`.

## 4. Report preparation that carries evidence limits into leadership language

**Business use.** Executive summaries are most useful when they are shorter than the evidence record without becoming broader than it. The synthetic report bundle keeps stable statement IDs and source references in both executive and detailed language.

Provider readback observed executive statement IDs **S-001 through S-003** and detailed recommendation statements **S-004 and S-005**, all represented in the same five-row trace map. The report explicitly says it is a rehearsal and not a University assessment. Its language distinguishes “evidence not retained” from “activity did not happen” and “representative evidence” from universal coverage.

Pinned sources:

- [synthetic executive summary](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_traceability_rehearsal/executive-summary.md)
- [miniature synthetic report](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_traceability_rehearsal/final-report.md)
- [statement trace map](https://github.com/woahwhattheheck/commons/blob/04dfec1281f91b4f050e4b93ac49c5925eb02386/revenue/uiowa_rfq_18649_traceability_rehearsal/trace-map.csv)

The same `python validate_trace.py .` command checks the ID graph behind both artifacts.

## Reproducibility and claim boundary

Machine-readable details for every capability are in `capabilities.json`. `validate_capabilities.py` recomputes each pinned source's **Git blob SHA from the local bytes** and fails if the referenced source has drifted, disappeared, escaped the repository root, or no longer matches its snapshot URL.

```bash
cd revenue/uiowa_rfq_18649_capability_appendix
python validate_capabilities.py
python -m unittest -v test_validate_capabilities.py
```

This evidence supports a narrow statement: **TJLabs has working engineering artifacts for evidence organization, uncertainty-aware comparison, traceability, and report preparation, with reproducible synthetic demonstrations.** It does not establish prior client outcomes, institutional validation, academic credentials, University-of-Iowa-specific findings, or acceptance of the proposed engagement.
