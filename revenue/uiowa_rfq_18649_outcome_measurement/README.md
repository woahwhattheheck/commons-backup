# UIOWA-087 — Improvement outcome-measurement pack

This package turns UIOWA-087 into a reusable, auditable measurement workflow for proposed AIS improvements.

It keeps two questions deliberately separate:

1. **Adoption:** did the intended practice change actually start happening?
2. **Operational outcome:** did delivery quality, security operations, or reliability move in the intended direction?

Neither signal proves that the recommendation caused the change. The tooling reports directional evidence and comparability limits; it does not score individual employees, certify effectiveness, or manufacture causality.

All included records are synthetic. They are not University of Iowa findings.

## Contents

- `recommendations.csv` — three fictional improvement recommendations.
- `measure_register.csv` — recommendation-linked measure definitions, evidence sources, effort, direction, and interpretation limits.
- `examples/measurements.csv` — synthetic baseline and follow-up observations.
- `collection_protocol.md` — repeatable collection and interpretation instructions.
- `analyze.py` — zero-dependency validator and report generator.
- `tests/test_analyze.py` — regression coverage for calculations, comparability, missing data, and adoption/outcome separation.
- `tests/test_measurement_validity.py` — independent malformed-input, ambiguity, arithmetic, report and CLI regression coverage.
- [VALIDITY_REVIEW.md](VALIDITY_REVIEW.md) — reproduced defects, comparison-eligibility contract, verification commands and interpretation limits.

## Quick start

```bash
python analyze.py validate \
  --recommendations recommendations.csv \
  --register measure_register.csv \
  --measurements examples/measurements.csv

python analyze.py report \
  --recommendations recommendations.csv \
  --register measure_register.csv \
  --measurements examples/measurements.csv

python -m unittest discover -s tests -v
```

## Design rules

Each measure records:

- the recommendation it is intended to inform;
- whether it is an `adoption` or `outcome` measure;
- the assessment area it informs;
- a stable numerator and denominator definition;
- the desired direction, when directional interpretation is appropriate;
- a concrete evidence source;
- expected collection effort;
- a collection cadence;
- an interpretation limit.

The analyzer recomputes rates from numerator/denominator values. It will not silently trust a supplied percentage. This component supports `unit=percent` proportions, not duration or event-frequency measures.

A baseline/follow-up pair is considered comparable only when its `population_definition` is identical and nonempty, the period IDs are distinct, and its definitions, links, provenance and counts are valid. Different sample sizes are allowed; a changed population definition is explicitly marked `NOT_COMPARABLE`. Matching labels alone do not prove empirical comparability.

## Output semantics

For each measure, the report emits:

- baseline and follow-up rate;
- absolute percentage-point change;
- `FAVORABLE_DIRECTION`, `UNFAVORABLE_DIRECTION`, `UNCHANGED`, `CONTEXT_ONLY`, or `INSUFFICIENT_DATA`;
- comparability state;
- evidence locators and collection effort;
- the measure's interpretation limit.

Invalid or ambiguous measure inputs yield `comparability=INVALID_DATA`, `directional_signal=INSUFFICIENT_DATA` and null numeric comparisons, with explicit diagnostics. Invalid recommendations suppress their dependent measures; valid unrelated measures remain available. Missing observations without invalid inputs remain `INSUFFICIENT_DATA`. Duplicate records are not automatically reconciled. CLI validation errors return exit 2; malformed CSV or missing required columns return `INPUT_ERROR` rather than a misleading clean result.

Recommendation sections keep adoption and operational-outcome rows separate. There is intentionally no combined score or "effective/ineffective" verdict.

## Boundaries

- Synthetic examples only.
- Team/process measures only; no individual performance ranking.
- Directional movement is not causal attribution.
- A process-adoption increase is not treated as an operational benefit.
- Missing follow-up data remains missing.
- Changed definitions are not normalized away.
- The register is a proposed assessment design, not a University baseline.
