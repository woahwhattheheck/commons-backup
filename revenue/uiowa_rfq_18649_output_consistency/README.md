# UIOWA-117 — Cross-output consistency checker

This directory contains a dependency-free, offline checker for agreement across four RFQ 18649 delivery surfaces:

1. assessment matrix,
2. recommendation register,
3. executive-summary source records, and
4. presentation source records.

The included examples are **synthetic preparation data, not University of Iowa findings**.

## Why this exists

A delivery can be individually well-formed and still disagree across outputs. Typical drift includes:

- a finding shown as `PARTIAL` in the matrix but `SUPPORTED` in a presentation;
- a recommendation moved to a different roadmap phase in one artifact;
- effort/estimate ranges copied incorrectly;
- a summary declaring a different recommendation count than the register;
- a slide citing a finding ID that does not exist.

`check.py` reports those disagreements at the artifact / entity / field level. It does not choose which value is correct. The accountable source record must be corrected or regenerated.

## Published-schema anchor

The synthetic IDs `F-001` through `F-003` and `R-001` through `R-002` intentionally align with the merged `uiowa_rfq_18649_traceability_rehearsal` bundle. The additional `F-004`, planning phases, and numeric estimate ranges exist only to exercise this checker.

Existing source schemas inspected before implementation:

- `revenue/uiowa_rfq_18649_traceability_rehearsal/findings.csv`
- `revenue/uiowa_rfq_18649_traceability_rehearsal/recommendations.csv`
- `revenue/uiowa_rfq_18649_workshare/fixtures/synthetic_packet.json`
- `revenue/uiowa_rfq_18649_workbench/README.md`

The checker does not replace any of those components.

## Run the regression suite

```bash
python -m unittest -v test_consistency.py
python -O -m unittest -v test_consistency.py
```

Expected: `5/5` pass in both modes.

## Regenerate the worked examples

```bash
python generate_examples.py fixtures/corrected
python generate_examples.py fixtures/mismatch --mismatch
```

Then check them:

```bash
python check.py fixtures/corrected \
  --json-out fixtures/corrected/report.json \
  --md-out fixtures/corrected/report.md

python check.py fixtures/mismatch \
  --json-out fixtures/mismatch/report.json \
  --md-out fixtures/mismatch/report.md
```

The corrected command exits `0` with `PASS / 0 diagnostics`. The mismatch command deliberately exits `1` with `FAIL / 5 diagnostics`.

## Deliberate mismatch example

The mismatch fixture contains exactly five controlled disagreements:

| Diagnostic | Artifact | Entity | Field |
|---|---|---|---|
| `COUNT_MISMATCH` | executive summary | bundle | recommendation count |
| `FIELD_MISMATCH` | executive summary | R-001 | low estimate |
| `FIELD_MISMATCH` | matrix | F-002 | finding state |
| `UNKNOWN_REFERENCE` | presentation | S-999 | finding ID |
| `FIELD_MISMATCH` | recommendation register | R-002 | phase |

The corrected fixture is regenerated from `canonical.json`; it then returns zero diagnostics.

## Guardrails

- `UNKNOWN` is a literal state. It is never converted to zero, false, a gap, or a maturity score.
- Missing or dangling identifiers remain explicit diagnostics.
- The checker never auto-resolves a disagreement.
- Every diagnostic names the conflicting artifact, entity ID, field, expected value, and observed value.
- Synthetic examples never become University findings simply because they are internally consistent.
