# Canonical lifecycle and economics integration

`integrate.py` runs the existing UIOWA-078 economics and UIOWA-079
lifecycle/evaluation engines. It loads those sibling source files from the same
repository checkout. It performs no network calls and does not copy or replace
their implementations.

```bash
python3 integrate.py --case examples/beneficial.json \
  --cost-assumptions examples/operating_assumptions.json --out integrated/beneficial
python3 integrate.py --case examples/unfavourable.json \
  --cost-assumptions examples/operating_assumptions.json --out integrated/unfavourable
python3 integrate.py --case examples/undecidable.json \
  --cost-assumptions examples/operating_assumptions.json --out integrated/undecidable
python3 integrate.py --case examples/beneficial.json \
  --cost-assumptions examples/operating_assumptions.json \
  --set analyst_hourly_cost=90 --out integrated/rate-change
```

For a partial checkout, `--economics-module` and `--lifecycle-module` accept local
paths to the exact source files. Both SHA-256 digests are checked before importing
either engine. The pinned repository revision is
`4401ee39b6b6ff7debffafc78b27f9b08e21f4e6`; the hashes are in `integrate.py` and
each generated `components.json`. Different source bytes return exit status two
with the expected and actual digest. Repinning is a source change that must
account for upstream contract changes, never an automatic fallback.

## Mapping without double counting

| Economics input | Source |
|---|---|
| Monthly tasks and loaded hourly rate | Named case assumptions, retaining declared ranges |
| Baseline minutes | Entire baseline document lifecycle through recorded acceptance and later work |
| Author minutes | Assisted AUTHOR and GENERATE events |
| Checking minutes | Assisted CHECK events |
| Rework fraction | Fraction of assisted documents with positive recorded repair/maintenance effort |
| Conditional rework minutes | REPAIR, REWORK_AFTER_ACCEPT and MAINTENANCE_EDIT totals among repaired documents |
| Horizon | Explicit positive whole-month assumption with equal low/value/high |
| Other costs and adoption | Separate cost-assumptions document; omitted fields stay UNKNOWN |

Derived time ranges use the fictional records' minimum, mean and maximum.
Rework incidence is the recorded fraction, not a confidence bound. The canonical
economics engine combines the supplied ranges independently, so its envelope
need not match the standalone model's whole-document envelope. Conditional
repair and its incidence are kept separate. Every derived cell names its source
document or assumption IDs and the effective-case hash.

The cost file may supply only fields not derived from the case. Its cells use
the canonical range/unit/basis/source contract. The included fictional file
adds rollout, platform, metered-service, support and workflow-maintenance costs.
It explicitly excludes document MAINTENANCE_EDIT effort from recurring
maintenance, and excludes already-valued integration labor from setup cash.
Its USD label is a fictional currency assumption, not a University quote.
Cash conversion is unknown; it never defaults to zero or one.

## Lifecycle evidence

Document IDs become case IDs. Supplied quality counts yield completeness;
correctness, usefulness and latency remain unknown because the original cases
did not measure them. The full quality and document event records are retained
as a digest-bound source snapshot. Repair metrics include the same repair and
maintenance events used for economics. Each source event retains its ID and
has a referenced source record.

The original cases contain ordinal days, not calendar timestamps. The projection
uses the explicit synthetic anchor `2000-01-01` plus each recorded day solely to
satisfy chronological storage. These dates are not engagement dates. Baseline
and assisted variants have no asserted parent/model-revision relationship.
Original model revisions, prompts, environments, source document bytes and
expected answers remain missing, and the canonical engine reports those gaps.
There is no paired comparison or replay claim: the source did not establish
matched task IDs across variants or retained model outputs.

This integrates the available records, not a complete historical AI execution.
Supplying actual revision relationships and replay evidence remains outside
these original examples; UIOWA-111 should not be closed on that claim.

## Outputs and interpretation

The command writes fourteen files: seven canonical economics reports plus its
input, lifecycle input/JSON/Markdown/comparison CSV, effective source case and
component revisions. The named files are replaced on rerun; use distinct
directories for retained variants. An interrupted write can leave partial
output, so rerun into a fresh directory after an I/O failure. The original case,
cost source and engine paths cannot be overwritten by named outputs.

Actual fictional example outputs are under `integrated/`:

| Case | Economic base | Net capacity hours | External cash cost | Cash-conversion result |
|---|---:|---:|---:|---|
| beneficial | 30,494.96 | 362.8 | 343.04 | UNKNOWN |
| unfavorable | -8,775.04 | -99.2 | 343.04 | UNKNOWN |
| undecidable | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| hourly valuation changed to 90 | 32,308.96 | 362.8 | 343.04 | UNKNOWN |

Economic value is modeled capacity valuation after external cash, not observed
profit or cash savings. Quality remains separate in the lifecycle report and
source records. Changing the hourly valuation leaves the entire generated
lifecycle input byte-identical while changing the economics explanation and
nominal result. Missing effort produces UNKNOWN economics without erasing
known quality observations. All results remain synthetic and modeled; none
authorizes procurement, scheduling, outreach or spending.
