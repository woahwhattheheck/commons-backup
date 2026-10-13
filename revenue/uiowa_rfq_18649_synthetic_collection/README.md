# SYNTHETIC AIS evidence collection — UIOWA-091

> **SYNTHETIC EVIDENCE — FICTIONAL AIS-LIKE SCENARIO. Not University of Iowa evidence or a finding.**

This directory is a coherent fictional evidence corpus for exercising RFQ 18649 assessment tooling without importing private customer evidence.

## Design

1. facts.json is the canonical synthetic fact ledger with stable IDs, service, assessment area, and strength/gap/unknown state.
2. evidence_manifest.json maps every source document to the fact IDs it can support or qualify.
3. Human-readable artifacts provide fictional organization/stack overviews, process documents, release examples, runbooks, interviews, AI-readiness records, and postmortems.
4. coverage_matrix.csv indexes the full 3-service by 4-area surface.

## Evidence discipline

- strength means supported only inside this fictional corpus.
- gap means another artifact establishes the synthetic expectation and the corpus contains evidence of a mismatch.
- unknown means the corpus cannot establish the proposition; consumers must not coerce UNKNOWN into a low score or gap.
- Interview statements remain interview evidence and may corroborate or conflict with documents without becoming verified facts automatically.
- Absence from this collection is not evidence of absence in a real environment.

## Validate

From this directory, run:

```sh
python3 validate_collection.py .
```

The validator checks file presence, manifest/fact referential integrity, explicit SYNTHETIC labeling, 12-cell coverage, and fact-state counts.

The label check reads the first 500 text characters of each document through a
bounded stream read. It avoids loading the entire document just to inspect its
heading. This excerpt check does not validate the complete document's UTF-8
encoding.

## Downstream handoff

UIOWA-092/093/097-style rehearsals should ingest evidence_manifest.json and facts.json directly rather than scraping conclusions from prose. Stable IDs let downstream tools preserve provenance and disagreement.

No customer submission, approval, payment, scheduling, access change, or live-system action is represented here.
