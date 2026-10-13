# UIOWA-110 — policy-versus-practice disagreement rehearsal

**Status:** fully synthetic integration rehearsal for RFQ 18649 preparation. Nothing in this directory is a University of Iowa finding.

## Purpose

A written rule can be strong evidence of **documented intent** without being proof of execution. This rehearsal gives the merged evidence-confidence and rating components one controlled disagreement:

- a current fictional procedure says a standard service change receives two recorded reviews;
- a fictional participant says that is the normal path but urgent changes may complete with one recorded review;
- a fictional 12-record sample partly supports the procedure: 8 records show two reviews, while 4 show one review and no exception marker.

The correct result is not “policy wins” or “sample wins.” The disagreement remains bounded and unresolved until the exception/effective-scope question is answered.

## Current-main components actually used

| Component | Interface | Rehearsal use |
|---|---|---|
| UIOWA-023 evidence confidence/provenance | `revenue/uiowa_rfq_18649_workshare/methodology/validate_23_evidence_register.py` plus §7/§11 of `23-evidence-confidence.md` | Validates the register; contradictory evidence stays `UNRESOLVED`; policy is indirect evidence for execution |
| UIOWA-022 rating composition | `revenue/uiowa_rfq_18649_rating_model/rating_model.py::compose` | Composes the unresolved criterion without inventing a maturity score or hiding unassessed coverage |
| Review controls | UIOWA-023 §11 | Checks that contradictions, source scope, confidence, and follow-up language survive into the discussion card |

A separate calibrated maturity-anchor component and standalone consolidated-review executable were not present on current `main` when this rehearsal was built. The runner therefore **does not invent an ordinal rank**. It applies the already-merged UIOWA-023 review controls and makes that interface boundary explicit.

## Files

- `evidence-register.csv` — three-source disagreement in the UIOWA-023 schema.
- `run_rehearsal.py` — imports and executes the merged UIOWA-023 validator and UIOWA-022 rating engine.
- `component-results.json` — checked-in expected component result for this synthetic packet.
- `review-discussion-card.md` — facilitator-ready strength / uncertainty / follow-up summary.
- `test_rehearsal.py` — regression checks against the merged component interfaces.

The rating payload is intentionally constructed in memory by the runner. The failed/discarded standalone rating-input draft is not part of the interface.

## Run

From the repository root:

```bash
python revenue/uiowa_rfq_18649_policy_practice_rehearsal/run_rehearsal.py

python -m unittest -v   revenue/uiowa_rfq_18649_policy_practice_rehearsal/test_rehearsal.py
```

Expected semantics:

- UIOWA-023 register validation: **PASS**;
- finding state: **UNRESOLVED**;
- UIOWA-022 composition: **unassessed**;
- assessed coverage: **0%**;
- maturity distribution: **none emitted**;
- review disposition: **TARGETED_FOLLOW_UP_BEFORE_DEFINITIVE_PRACTICE_CHARACTERIZATION**.

## Worked interpretation

### Supported strength

The packet supports two narrow statements:

1. a current documented procedure exists; and
2. most records in the bounded synthetic sample (8 of 12) align with it.

Neither statement establishes universal execution.

### Specific uncertainty

Four sampled records show one review and no exception marker, while the participant says urgent changes may legitimately use a different path. The packet cannot determine whether those four records represent:

- legitimate exceptions with incomplete classification;
- procedure scope/effective-date mismatch;
- incomplete recordkeeping; or
- actual variation from the documented practice.

### Smallest useful follow-up

1. Confirm the procedure’s effective scope and date.
2. Inspect classification and review history for the four one-review records.
3. If a group-wide statement is needed, compare the resolved interpretation against an authoritative change population rather than extrapolating the 12-record sample.

## Guardrails demonstrated

- policy text is not treated as execution evidence;
- interview testimony is not treated as organization-wide fact;
- a bounded sample is not silently generalized;
- contradictory sources remain visible together;
- unresolved evidence does not receive an invented maturity rank;
- missing classification is not rewritten as failure or absence;
- review follow-up discriminates between plausible explanations instead of choosing the most formal source.
