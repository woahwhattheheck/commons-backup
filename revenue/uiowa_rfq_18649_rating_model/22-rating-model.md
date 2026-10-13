# UIOWA-022 — Rating composition and uncertainty model

**Status:** proposed assessment method for RFQ 18649 preparation.  
**Scope:** composition of already-assessed criterion observations.  
**Non-goal:** define the ordinal maturity anchors themselves; that is a separate method concern.

## Why this model exists

An arithmetic average can hide the exact conditions leaders need to see. A service can have many strong observations and one material weakness in a critical practice. A team can also appear “strong” when only a small fraction of criteria were actually assessed. Evidence confidence can differ even when the observed practice looks similar.

This model therefore keeps five dimensions separate:

1. **maturity** — the externally defined ordinal observation for an assessed criterion;
2. **coverage** — how much of the eligible criterion population was assessed;
3. **confidence** — how well-supported each assessed observation is;
4. **applicability** — whether a criterion legitimately belongs in the denominator;
5. **material gaps** — weaknesses that must stay visible instead of disappearing into aggregation.

The executable reference implementation is `rating_model.py`.

## Input contract

Each criterion requires:

| Field | Meaning |
| --- | --- |
| `criterion_id` | stable criterion identifier |
| `area` | one of the assessment areas or another explicitly configured area name |
| `service` | ESS, RIS, IAM, shared service, or another defined assessment unit |
| `assessment_status` | `assessed`, `unassessed`, or `not_applicable` |
| `criticality` | `supporting`, `important`, or `critical` |
| `maturity_rank` | ordinal integer supplied by the maturity-anchor method; only for assessed criteria |
| `maturity_label` | human-readable label paired with the rank |
| `confidence` | `low`, `moderate`, or `high`; an input, not calculated here |
| `material_gap` | explicit analyst decision that an assessed weakness is material |
| `evidence_ids` | provenance references supporting the observation |
| `applicability_reason` | required when a criterion is not applicable |

### Important boundary with UIOWA-021 and UIOWA-023

This model intentionally does **not** invent the maturity scale and does **not** calculate evidence confidence.

- The maturity rank/label is an input from the common-anchor method.
- Confidence is an input from the evidence/provenance method.
- This model's job is to compose those inputs without conflating them.

That boundary lets the three methods evolve independently while keeping the final characterization reproducible.

## Coverage

For a group:

```text
eligible = assessed + unassessed
coverage = assessed / eligible
```

Not-applicable criteria are excluded from the denominator. Unassessed criteria remain in the denominator because their absence is exactly what coverage must reveal.

Default threshold for an area characterization is **60% coverage**, explicitly configurable through:

```json
{
  "settings": {
    "min_coverage_for_characterization": 0.60
  }
}
```

The threshold is a **proposed TJLabs method choice**, not a NIST or University requirement. It should be confirmed or changed during assessment-method calibration.

## Maturity composition

No mean maturity is calculated.

For each group, the engine reports:

- distribution by ordinal rank;
- distribution by maturity label;
- lowest observed rank;
- highest observed rank;
- ordinal spread.

Default mixed-practice threshold is a spread of **2 ranks**, also configurable.

If a future maturity scale changes from five anchors to four or six, the engine still works because it does not hard-code anchor names.

## Confidence composition

Confidence remains independent from maturity. The engine reports:

- count of low-confidence observations;
- count of moderate-confidence observations;
- count of high-confidence observations;
- minimum observed confidence.

It does **not** turn confidence into a multiplier, discount factor, or maturity adjustment.

A low-confidence high-maturity observation therefore remains exactly that: high observed maturity **with low confidence**.

## Material and critical gaps

A criterion can be marked `material_gap=true`. If the criterion is also `critical`, the area composition becomes:

`critical_gap_present`

This status takes precedence over a coherent maturity pattern. It prevents a critical weakness from being obscured by stronger observations elsewhere.

The engine also retains all noncritical material gaps as named criterion IDs even when they do not determine the composition status.

## Composition precedence

For each area or area/service group:

1. **not_applicable** — no eligible criteria exist;
2. **unassessed** — eligible criteria exist but none were assessed;
3. **insufficient_coverage** — assessed evidence exists, but coverage is below the configured threshold;
4. **critical_gap_present** — coverage is adequate and at least one assessed critical criterion has a material gap;
5. **mixed_practice** — no critical material gap, but observed maturity spread reaches the configured threshold;
6. **coherent_pattern** — none of the preceding cautions apply.

This is not a maturity ranking. It is a statement about how safely the underlying observations can be summarized.

## Worked case A — strong-average / critical-gap trap

Suppose an area contains five assessed criteria:

| Criterion | Rank | Label | Criticality | Material gap |
| --- | ---: | --- | --- | --- |
| A1 | 4 | adaptive | important | no |
| A2 | 4 | adaptive | important | no |
| A3 | 4 | adaptive | important | no |
| A4 | 4 | adaptive | supporting | no |
| A5 | 1 | emerging | **critical** | **yes** |

An arithmetic mean would be 3.4 and could invite a misleading “strong overall” statement.

This model emits:

- coverage: 100%;
- maturity distribution: 1×rank-1, 4×rank-4;
- spread: 3;
- critical gap: A5;
- composition status: **critical_gap_present**.

The material weakness remains explicit.

## Worked case B — low coverage

Ten criteria are eligible, but only four were assessed. All four have rank 4 and high confidence.

The model emits:

- coverage: 40%;
- observed distribution: 4×rank-4;
- six unassessed criterion IDs;
- composition status: **insufficient_coverage**.

It does not label the area “rank 4” overall because most of the eligible population is unknown.

## Worked case C — mixed services

Assume the same area is assessed across ESS, RIS, and IAM:

- ESS observations cluster at ranks 3–4;
- RIS observations cluster at ranks 1–2;
- IAM observations cluster at ranks 3–4.

The area-level distribution retains the full range, while service summaries preserve each service's pattern. The output does not average those into a single number.

If the configured spread is reached, the area is **mixed_practice**.

This makes “uneven practice across services” visible without declaring one technology stack inherently better.

## Not applicable versus unassessed

These states must never be collapsed.

- **Not applicable** means the criterion was considered and legitimately does not apply. A reason is required.
- **Unassessed** means it should apply, but evidence or assessment work is incomplete.

Only the latter reduces coverage.

## Reporting rule

A leadership-facing summary should show at least:

- composition status;
- coverage;
- maturity distribution or range;
- confidence distribution/floor;
- named critical and material gaps;
- named unassessed items;
- service-level differences when they materially affect interpretation.

A report should not replace those fields with a single composite score.

## Uncertainty language

Use language tied to the evidence state:

- “Observed across the sampled evidence…”
- “Coverage is limited because…”
- “This characterization is low/moderate/high confidence because…”
- “Practice differs materially between ESS/RIS/IAM…”
- “A critical gap remains visible despite stronger observations elsewhere…”
- “Not assessed” rather than “absent” when evidence is missing.

Avoid:

- “overall score 3.4/5”;
- “82% mature”;
- “best-performing group” based on this method;
- treating `not_applicable` as a zero;
- increasing maturity because confidence is high;
- reducing maturity because confidence is low.

## Reproducibility

The repository includes:

- `rating_model.py` — deterministic composition logic and CLI;
- `rating_input.schema.json` — machine-readable input contract;
- `synthetic_cases.json` — three requested worked scenarios;
- `22-worked-decision-table.csv` — editable decision trace;
- `test_rating_model.py` — regression tests for precedence and separation rules.

### CLI

```bash
python revenue/uiowa_rfq_18649_rating_model/rating_model.py \
  revenue/uiowa_rfq_18649_rating_model/synthetic_case_critical_gap.json \
  --json-out /tmp/uiowa-022.json \
  --markdown-out /tmp/uiowa-022.md
```

## Acceptance mapping

UIOWA-022 asks for three specific proof cases:

- **strong-average / critical-gap** → demonstrates a critical weakness cannot disappear into an average;
- **low coverage** → demonstrates strong assessed observations do not authorize an area-level maturity claim when most eligible criteria are unknown;
- **mixed service** → demonstrates ESS/RIS/IAM disagreement remains visible.

The engine also handles:

- all-unassessed populations;
- all-not-applicable populations;
- confidence distributions independent of maturity;
- duplicate criterion IDs and malformed states as hard validation errors.

The core principle is simple: **compose evidence without erasing uncertainty.**
