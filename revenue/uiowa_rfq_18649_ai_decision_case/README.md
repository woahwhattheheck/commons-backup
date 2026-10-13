# Synthetic AI document decision case

Recovered from source commit `b8852a92085dca71231034d1eef1d5781fd079b3` for
UIOWA-111. The original implementation was absent from main. This directory
preserves its lifecycle ledger, quality summary, interval model, cited
explanation and sensitivity tools, with portable exports and nominal results.

Every input is fictional. There are no University findings, prices, document
measurements, vendor recommendations or spend authorizations here. The program
uses only the Python standard library and performs no network or model calls.

## Run

From this directory:

```bash
python3 ai_decision_case.py --case examples/beneficial.json --sweep --out out/beneficial
python3 ai_decision_case.py --case examples/unfavourable.json --sweep --out out/unfavourable
python3 ai_decision_case.py --case examples/undecidable.json --out out/undecidable
python3 ai_decision_case.py --case examples/beneficial.json \
  --set analyst_hourly_cost=90 --diff --format json --out out/rate-change
```

`--out` writes `decision.json`, `explanation.md`, `effective_case.json`,
`summary.csv`, `lifecycle.csv`, `quality.csv` and `assumptions.csv`. Existing
files with those names are replaced. Use a separate output directory for each
scenario. The effective case can be passed back to `--case` to reproduce a run.
`--format json --diff` emits one JSON document with an `explanation_diff` array.
Exit status is zero for a completed run (including a correctly reported
UNDECIDABLE result), one for a failed explanation citation audit, and two for
invalid input, overrides or output errors.

## What the result means

The source records describe manual and assisted versions of a document workflow.
The ledger includes authoring/generation, checking, repair, acceptance and work
after acceptance. A missing duration or acceptance event makes the comparison
UNDECIDABLE; it is never silently excluded or treated as zero.

| Example | First-draft speedup | Capacity-value classification |
|---|---:|---|
| beneficial | 15.75x | BENEFICIAL |
| unfavourable | 22x | UNFAVOURABLE |
| undecidable | UNKNOWN | UNDECIDABLE |

The unfavorable example has faster initial drafting but more checking and
post-acceptance rework. Labels do not determine these classifications.
BENEFICIAL means a positive signed labor-capacity valuation within this limited
model; it is not a full investment decision or an endorsement of output quality.

Quality completeness and fabricated-reference counts remain separate from
effort and money. No combined quality/economics score is calculated.

Capacity hours use the recorded mean difference in minutes per document,
multiplied by assumed monthly volume and horizon, divided by sixty. Nominal
capacity value multiplies those hours by the assumed hourly labor valuation.
The value range uses the observed spread in the fictional document records
and every corner of the declared assumption ranges. These bounds are not
confidence intervals or probabilities.

Cash cost, cash savings and realized opportunity value are explicitly UNKNOWN.
The original model has no integration, platform, service cost, utilization or
cash-conversion inputs. Positive capacity value cannot establish cash savings.
All source records are marked synthetic, calculated outputs modeled, and
missing values `null` in JSON or `UNKNOWN` in CSV/Markdown.

## Changed assumptions

`--set` changes a copied assumption while keeping document and quality records
intact. Declared bounds widen only if the new value is outside the range. A
within-range change therefore updates nominal value while preserving the range.
For the beneficial case, changing the hourly valuation from 85 to 90 changes
nominal capacity value from 33,558 to 35,532; recorded quality, lifecycle events
and the 17,640–58,740 value interval remain unchanged. These are fictional
currency units, not a University rate or cash result.

`--sweep` evaluates each assumption at its declared endpoints, holding that
assumption at the endpoint and retaining other uncertainty. It also searches
for a checking-effort change that changes the classification. Missing records
yield an UNDECIDABLE sensitivity result. The explanation audit checks that
rendered quantity lines have record citations and that cited IDs exist; it
does not establish the truth of fictional measurements.

## Integration status

The standalone command above preserves the recovered case engine. The separate
[canonical integration command](INTEGRATION.md) maps these records into the
existing UIOWA-078 economics and UIOWA-079 lifecycle/evaluation engines, with
exact source pins, explicit operating assumptions and separate cash outcomes.
It emits missing-evidence gaps for model revisions, document bytes and paired
evaluation tasks that the original examples did not record. It does not invent
that history or establish a fully replayable AI workflow.

`model.py`, `case.py`, `explain.py` and `sensitivity.py` retain the original
runtime design. `export.py` provides the tabular and effective-input outputs.
The three original fictional product examples are retained under `examples/`.
