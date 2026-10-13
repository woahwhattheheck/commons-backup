# UIOWA-112 — outcome comparison with explicit rating observations

This offline integration joins the existing UIOWA-026 cross-stack comparison and
UIOWA-022 rating-composition interfaces. It does not introduce another rating
engine. A manual, automated or shared-service implementation receives no rank
from its label. Outcome comparison, maturity, evidence confidence and coverage
remain separate and visible in the output.

## Run with existing published inputs

Use Python 3.10+ from the Commons repository root. The only dependencies are the
standard library and the two sibling source components. No network access is used.

```sh
python revenue/uiowa_rfq_18649_cross_stack/examples.py --out /tmp/uiowa112-input
python revenue/uiowa_rfq_18649_equivalent_outcomes/compare_outcomes.py \
  /tmp/uiowa112-input/synthetic.json > /tmp/uiowa112-report.json
python revenue/uiowa_rfq_18649_equivalent_outcomes/compare_outcomes.py \
  /tmp/uiowa112-input/synthetic.json --format markdown > /tmp/uiowa112-report.md
```

The first command is the existing component's example generator; choose a new
directory. Its unchanged cases span ESS, RIS and IAM, retaining manual, automated,
hybrid and shared-service contexts. The manual 4/4 and automated 40/40 review
samples retain their native `EQUIVALENT_OUTCOME_IN_SUPPLIED_SAMPLE` verdict and
exact descriptive rates. Dissent, absent evidence, differing context and differing
measurement windows retain the native engine's distinctions. These are fictional
records, not University findings or a population-equivalence claim.

No calibrated maturity observations are present in that input. Every practice is
therefore passed to the real rating model as `unassessed`, including practices
whose supplied outcome was met. This is missing calibration, not a low rating or
a claim that the outcome evidence is absent.

## Supply calibration separately

Generate an editable, snapshot-bound ratings input:

```sh
python revenue/uiowa_rfq_18649_equivalent_outcomes/compare_outcomes.py \
  /tmp/uiowa112-input/synthetic.json --format ratings-template > /tmp/uiowa112-ratings.json
python revenue/uiowa_rfq_18649_equivalent_outcomes/compare_outcomes.py \
  /tmp/uiowa112-input/synthetic.json --ratings /tmp/uiowa112-ratings.json \
  --format markdown > /tmp/uiowa112-calibrated-report.md
```

The unedited template remains unassessed. An authorized assessor supplies real
calibration references and observations in their private working environment.
Do not manufacture ranks to make a comparison look equal.

The ratings envelope contains:

| Field | Contract |
|---|---|
| `schema` | `uiowa-equivalent-outcomes/v1/ratings` |
| `comparison_input_sha256` | Exact native comparison input digest; stale or unrelated inputs are rejected |
| `calibration` | `null` for unassessed-only input, otherwise nonblank `reference` and `version` |
| `criteria` | Native rating rows bound to compared practice IDs; omitted practices remain unassessed |
| `settings` | Optional native rating-model settings |

Each native row uses `criterion_id` equal to the practice ID, `area` equal to the
comparison area, and `service` equal to the practice's ESS/RIS/IAM group. This is
an explicit grouping adapter, not an assertion that a group is a single service.
The native model composes all declared practices, including ones outside a pair.

Use native `assessment_status` values `unassessed`, `assessed` or `not_applicable`.
Assessed rows require an explicit maturity rank/label, confidence and one or more
unique evidence IDs already retained by that practice. Native criticality,
material-gap and applicability fields retain their existing meaning. Non-assessed
rows cannot carry ranks or confidence. Both assessed and not-applicable decisions
require a calibration reference/version. No maturity, confidence, applicability
or criticality is inferred from the comparison claim or implementation style.

The native default criticality is immaterial for an unassessed row; no material
gap or rank is assigned to it. Supply the intended criticality for assessed rows.
The adapter validates references and snapshot identity, but does not authenticate
calibration, evidence documents or an assessor's interpretation. Supplied ratings
remain visible beside native dissent/unknown outcomes; they do not override them.

## Output and interpretation

JSON retains the complete native `comparison` and `ratings` reports, the exact
`rating_input`, explicit-versus-default observation metadata, supplied calibration,
input digests, actual native source SHA-256 values and a paired `review_table`.
The Markdown table compares implementation styles, native outcome verdicts,
explicit rating states and exact measurement fractions. It includes the full
native reports below the table, preserving source locators, denominators, windows,
context decisions, dissent and follow-up questions.

Exit 0 means both native interfaces accepted the input and output was generated.
It does not mean that every outcome met its criterion or that ratings were
available. Invalid inputs or filesystem errors exit 2 without a partial report.
Output goes to stdout; choose distinct redirected paths to preserve earlier work.

Original UIOWA-026 comparison and UIOWA-022 rating-model authorship is retained.
This completes the runtime integration seam of Commons #16199 using existing
published examples. No new demonstration corpus, customer contact, commercial
event, release decision or institutional finding is asserted.
