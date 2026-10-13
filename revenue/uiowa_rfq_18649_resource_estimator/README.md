# UIOWA-086 — Resource and adoption estimator

Offline preparation tool for recommendation-linked effort and specialist-role capacity.
All three worked cases are **fictional**, not University findings, observed staffing,
productivity benchmarks, prices, or a promised maturity improvement. The blank worksheet
is unassessed. This package adds no service calls, purchases, calendar events or scheduling.
It does not replace the assessment compiler or workbench.

Operation: `uiowa-086-kestrel42-20260919`. Builder: ZZ-Kestrel-42 / GPT-6 Astra Pro.
Source work order: UIOWA-086, tracked in Commons issue #16117.

## Run immediately

From the repository root, using Python 3.10 or newer and no third-party packages:

```sh
python revenue/uiowa_rfq_18649_resource_estimator/estimator.py --demo release --output-dir /tmp/uiowa086-release
python revenue/uiowa_rfq_18649_resource_estimator/estimator.py --demo security --output-dir /tmp/uiowa086-security
python revenue/uiowa_rfq_18649_resource_estimator/estimator.py --demo reliability --output-dir /tmp/uiowa086-reliability
python revenue/uiowa_rfq_18649_resource_estimator/estimator.py --input revenue/uiowa_rfq_18649_resource_estimator/worksheet.json --output-dir /tmp/uiowa086-worksheet
python -m unittest discover -s revenue/uiowa_rfq_18649_resource_estimator -p 'test_*.py' -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_resource_estimator -p 'test_*.py' -v
```

Each output directory must be new. Choose a different directory for a later run;
existing files are never overwritten. On Windows replace `/tmp/...` with a new directory
under a suitable temporary working location. Tests use the running Python executable.

Each successful run writes `input.json` (the editable worksheet), `estimate.json`
(the full machine-readable result), `activities.csv` (a spreadsheet-friendly activity
ledger), and `estimate.md` (the operator report). Invalid plans exit 2 before creating
the output directory. File-system errors can leave a partial directory; do not treat
its presence alone as a completed run. Success exits 0. Copy/edit `input.json` or the
blank `worksheet.json`, then rerun with `--input` into another new directory.

Do not commit real University, personnel, prime, or confidential engagement data to
this public repository. Use appropriately controlled engagement storage outside the repo.

## What the model computes

For each activity and each low/central/high point:

`person-hours = units × hours_per_unit`

An activity is either one-time (`implementation`, `process_change`, `training`) or
recurring (`maintenance`, with units measured **per month**). The model reports:

- One-time effort, separated by kind and role.
- Recurring maintenance in person-hours/month, never silently added to one-time effort.
- Recurring effort over the explicit horizon, assuming recurrence in every month.
- A combined horizon envelope, only when the modeled scope and all efforts are known.
- Required specialist skills, separately allocated capacity, and unresolved constraints.
- Adoption notes and future success-evidence requests attached to each recommendation.

Ranges are **conditional planning scenarios, not probability distributions or confidence
intervals**. The central point is not a statistically estimated mean. Positive factors
are combined pointwise; the envelope assumes their stated extremes can occur together.
Correlations, risk occurrence probabilities, elapsed lead time, seasonal variation,
procurement delay and critical-path scheduling are not modeled.

Learner attendance is person-hours: 12 learners × 1.5 hours = 18 person-hours.
Facilitator preparation/instruction is a separate activity. A shared workshop linked
to two recommendations has one activity ID and is counted once. Do not duplicate it
with a second ID. IDs cannot detect that two differently named activities describe
the same work; an analyst must reconcile that semantic overlap.

### Capacity is a skill-specific feasibility envelope

Enter net available monthly person-hours **after unrelated commitments**. Implementation
and maintenance capacity must be separate, nonoverlapping allocations, not two copies
of the same staff hours. The model cannot independently verify this assumption.

Implementation demand is compared with implementation capacity × planning months.
Recurring demand is compared with monthly maintenance capacity. Capacities from another
role are not substituted. These checks are necessary workload comparisons, not sufficient
proof of an achievable schedule: prerequisites, timing, simultaneous demand and staff
availability can still matter. Dependencies are checked for unknown IDs/cycles and
ordered for reading; no dates are assigned.

| Capacity status | Meaning |
|---|---|
| `UNKNOWN_DEMAND` | At least one relevant estimate or overall scope is incomplete. |
| `NO_DEMAND` | All relevant activity estimates are known and zero. |
| `UNKNOWN_CAPACITY` | Positive demand is known, but role capacity is unassessed. |
| `UNRESOURCED` | Positive demand is known and maximum stated capacity is zero. |
| `EXCEEDS_EVEN_OPTIMISTIC_CAPACITY` | Lowest demand exceeds highest capacity. |
| `FITS_ALL_STATED_SCENARIOS` | Highest demand does not exceed lowest capacity. |
| `SCENARIO_DEPENDENT` | Demand and capacity envelopes overlap. |

`COMPLETE_INPUTS` means all modeled activities have effort inputs and every recommendation
has an activity. It does **not** mean capacity is known, scope is factually sufficient,
an engagement is approved, or the proposed work will fit. Read the capacity statuses too.

### Missing does not mean zero

Use JSON `null` for an unassessed range, never 0. Reports retain `known_hours` separately
from `total_hours`. A missing activity estimate makes the affected complete total null;
a recommendation with no activities makes all complete totals unknown because its role
and effort distribution are unscoped. Known subtotals still help discovery, but are not
a complete estimate. Zero is reserved for an explicitly assessed zero quantity/effort.

## Input contract: `uiowa.resource-plan/v1`

`worksheet.json` is the editable, unassessed template; `example_plans.py` supplies three
complete structures. Object fields are exact, unknown fields and duplicate IDs/JSON keys
are errors. All identifiers are nonempty strings and references must resolve within the
plan. Input row order is preserved except recommendation prerequisites are topologically
ordered with lexical tie-breaking.

| Object | Required fields |
|---|---|
| Plan | `schema`, `plan_id`, `title`, `evidence_class`, `planning_months`, `assumptions`, `roles`, `recommendations`, `activities` |
| Assumption | `id`, `text`, `source` |
| Role | `id`, `name`, `skills`, `implementation_hours_per_month`, `maintenance_hours_per_month`, `assumption_ids` |
| Recommendation | `id`, `title`, `group_id`, `area`, `dependencies`, `adoption_notes`, `success_evidence` |
| Activity | `id`, `description`, `recommendation_ids`, `role_id`, `kind`, `unit_label`, `units`, `hours_per_unit`, `assumption_ids` |
| Range | `low`, `central`, `high`, or replace the entire range with `null` |

At least one role and recommendation are required. Roles need at least one skill and
assumption; activities need at least one recommendation and assumption. Recommendation
links are descriptive, not allocations. `area` and `group_id` preserve the caller's
namespace; no cross-component or University taxonomy is silently inferred.

`planning_months` is an integer 1–120. `evidence_class` is `SYNTHETIC` or
`USER_PROVIDED_UNVERIFIED`; it is a supplied label, not authenticated source provenance.
Decimal strings are recommended, e.g. `{"low":"0.5","central":"1","high":"1.5"}`.
Finite nonnegative JSON numbers are also accepted, with at most six decimal places,
exponents -6 through 9, each factor <= 1,000,000,000, and low <= central <= high.
Booleans are not numeric inputs. Calculations use Decimal with a local precision of 80;
output ranges use decimal strings to avoid binary-float rounding in exchanges.

For training, use units = participant count and hours/unit = each participant's time.
For a variable workload use three quantity points as well as three unit-effort points.
For maintenance, put monthly frequency in `units`; do not pre-multiply by the horizon.
Describe the scenario basis, evidence locator, collection date and unresolved questions
in the assumption register rather than presenting judgement as measured data.

## Output contract and integration with UIOWA-105

`estimate.json` has schema `uiowa.resource-estimate/v1`. Use this JSON, not Markdown or
CSV, as the canonical interchange. Key fields:

| Output | Use |
|---|---|
| `one_time`, `monthly_maintenance` | Separate `known_hours`, `total_hours`, missing activity IDs and unscoped recommendation IDs. |
| `horizon_maintenance_hours`, `horizon_total_hours` | Nullable envelopes for the stated planning-month assumption. |
| `by_kind` | Separate implementation/process/training/maintenance subtotals; maintenance is still monthly. |
| `roles` | Role skills, effort subtotals, horizon/monthly capacity, constraint status and capacity assumption IDs. |
| `activities` | Stable activity/role/recommendation IDs, quantities, unit effort, calculated effort, period, assumptions and missing inputs. |
| `recommendations` | Original group/area, dependencies, adoption/evidence prompts, activity IDs and shared-activity IDs. |
| `assumptions` | Original text and source descriptors. |

Namespace an external join with both component/schema and `plan_id`; the same spelling
of a recommendation in another component does not prove identity. Preserve original
IDs, evidence class and assumptions. Aggregate activities once by their unique IDs
within a plan; do not sum recommendation-linked views. This package has **no cash cost,
hourly rate, money savings or released-capacity output**. Labor effort is not money;
capacity available for this work is not capacity released by it. A downstream adapter
must retain these distinctions and unknowns.

`activities.csv` is an analyst export, not a complete plan schema or lossless JSON representation.
Unknown numeric ranges become empty cells and missing-input names stay explicit. Lists
are semicolon-joined; use JSON when identifiers contain semicolons. Formula-looking text
is prefixed with an apostrophe for spreadsheet display, while canonical JSON retains
the original text. Unicode, quotes, commas and multiline descriptions use normal CSV
quoting. No formulas or linked workbooks are generated.

### Bring numeric spreadsheet edits back into a plan

Keep the exported `input.json` as the base plan. Edit only these six columns in a
copy of its `activities.csv`: `units_low`, `units_central`, `units_high`,
`hours_per_unit_low`, `hours_per_unit_central`, `hours_per_unit_high`. Then run:

```sh
python revenue/uiowa_rfq_18649_resource_estimator/estimator.py \
  --input /tmp/uiowa086-release/input.json \
  --activities-csv /tmp/edited-activities.csv \
  --output-dir /tmp/uiowa086-release-revised
```

The overlay updates quantity and unit-effort ranges by stable activity ID, then
uses the existing estimator to recalculate effort, aggregates and role capacity.
It preserves the base plan's recommendations, role allocations, assumptions,
source descriptions, links, planning horizon and row order. Row order in the CSV
may change. Every original row must still appear exactly once; missing, duplicate,
unknown or ambiguously spreadsheet-escaped IDs fail explicitly.

For an UNKNOWN range, leave **all three** cells blank. Three numeric zero cells
mean an explicitly estimated zero. A partly blank range, formula, nonfinite or
out-of-range number is rejected. The original decimal precision, bounds and
low/central/high ordering rules still apply. Unchanged numeric values retain the
original JSON representation, including existing null ranges.

All other CSV columns must equal the base plan's exported display, including
derived effort and `missing_inputs`; they are recalculated after import. Do not
edit them in the spreadsheet. Change metadata, assumptions, recommendations or
capacity directly in the source JSON and export a new sheet. Numeric edits do
not automatically update the stated assumption basis: review that basis before
using the resulting plan.

The revised export contains the usual four files plus `source-input.json` (the
exact previous plan bytes) and `activity-edits.json` (changed activity/range values
and SHA-256 bindings for source JSON, edited CSV and updated JSON). These are
lineage records, not independent evidence authentication. The original directory
is never overwritten. CSV input is UTF-8, optionally with a BOM, and limited to
2 MiB; CSV parsing errors return exit 2 before output creation.

Actual worked continuation used the existing release plan. Changing only
REL-INVENTORY's hours-per-unit from 1/2/3 to 2/3/4 produced one-time
60/92/136 person-hours and three-month 78/122/184 hours. All nonnumeric metadata
and exact source-plan bytes were retained. The existing reliability plan's
unchanged sheet round-tripped to byte-identical `input.json` and remained
INCOMPLETE, preserving its unknown effort. These are fictional planning edits,
not measured staffing or a new test corpus.

## Three worked planning conversations

See `sample-results.md` for actual generated results and interpretation. In an engagement:

1. **Release handoff:** identify shared training and process work, confirm the eight-app
   scope, and discuss the scenario-dependent operations allocation before proposing timing.
2. **Secure-development practice:** specialist capacity is the constraint. Consider
   sequencing fewer applications, reallocating an appropriate specialist, or a longer
   planning horizon; none is represented as an approved staffing decision.
3. **Operational reliability:** investigate missing instrumentation effort and reserved
   operations maintenance capacity first. Do not turn the known subtotal into a quote.

Before using any estimate, replace synthetic counts with supported scope, resolve activity
overlap, confirm specialist skills and net allocations, validate recurring frequency and
adoption effort, then review dependencies and the unmodeled calendar constraints. Expected
success evidence is a collection prompt, not a result the tool claims to have achieved.
