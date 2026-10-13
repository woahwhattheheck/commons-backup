# UIOWA-093 — finding-to-final-report traceability rehearsal

This directory is a fully synthetic miniature assessment bundle for RFQ 18649 preparation. It demonstrates how evidence remains traceable through findings, recommendations, executive language, and the final report. Nothing here is a University of Iowa finding.

## Bundle

- `evidence.csv` — stable evidence IDs and exact locators.
- `findings.csv` — synthetic strengths/gaps with explicit evidence references.
- `recommendations.csv` — recommendation links back to findings.
- `trace-map.csv` — report statement to recommendation/finding/evidence chain.
- `executive-summary.md` — concise synthetic leadership summary.
- `final-report.md` — miniature report body.
- `validate_trace.py` — standard-library link checker.

## Trace rule

Every substantive report statement has a stable statement ID. The trace map connects each statement to one or more finding IDs. Each finding cites one or more evidence IDs. Every evidence row retains a precise source locator. Recommendations may serve several findings, but they never replace evidence for a finding.

## Rehearsal cases

1. Synthetic ESS strength: requirement, integration result, and acceptance record form a retained chain.
2. Synthetic RIS gap: intended reporting handoff and contract evidence exist, while end-to-end propagation evidence is not retained in the packet.
3. Synthetic IAM mixed case: one representative propagation check exists, but the evidence does not establish every dependent application.

Missing evidence is recorded as unknown, not as proof that a practice never occurred.

## Run

```bash
python validate_trace.py .
```

Expected:

```text
evidence=8 findings=3 recommendations=2 statements=5
trace validation: PASS
```

## Guardrails

- Synthetic evidence is not a University finding.
- Executive wording cannot broaden the underlying evidence.
- Recommendation priority is separate from evidence strength.
- A report statement must be traceable without reconstructing provenance by hand.
