# AI workflow economics workbook

Open [AI_workflow_economics.xlsx](AI_workflow_economics.xlsx) in Excel or another
XLSX application. This is the missing editable companion to the existing
[UIOWA-078 calculator](../uiowa_rfq_18649_ai_economics/README.md).

The four supplied cases are fictional. Positive staff capacity value is not a
cash receipt or a promise of savings. Economic and cash-conversion results stay
separate. The workbook makes no claim about the University of Iowa.

## Use

1. On **Inputs**, choose case 1–4 in B4. The same model recalculates for the
   selected case. Horizon, currency, input basis, and all low/base/high assumptions
   are editable. Blue text identifies editable cells.
2. Edit the four case rows beneath each input. Keep row order and identifiers.
   Record the evidence basis and source beside every assumption. Missing means
   all three range cells are blank and basis is `unknown`; explicit zero is a
   numeric zero. Low/base/high must be ordered, nonnegative, with fractions at
   most one. Missing or invalid active ranges display `UNKNOWN`.
3. **Economics** shows the working calculation, economic and cash results,
   break-even thresholds, and independent-range endpoints. **Sensitivity** varies
   one input at a time. **Range bounds** exposes all 32 endpoint witnesses.
   Independent ranges are bounds, not probabilities or confidence intervals.
4. Export inputs to the canonical calculator for exact-decimal analysis and a
   simultaneous comparison of all four cases. The workbook itself presents one
   active case, so there are no saved comparison values that can silently go stale.

From this directory, using Python 3.10+ and no additional Python packages:

```sh
python export_inputs.py AI_workflow_economics.xlsx edited-inputs.json
python ../uiowa_rfq_18649_ai_economics/economics.py edited-inputs.json --out edited-results
```

The exporter reads only editable values, never cached formulas. It checks the
template cell map, rejects formulas in editable fields and partial ranges, then
calls the existing calculator's `validate_document`. Invalid input exits with
code 2 without replacing the output file. It preserves all case metadata,
evidence basis, sources and explicit unknowns. Spreadsheet numeric storage can
normalize decimal spelling (`0.10` to `0.1`) without changing the value.

The spreadsheet uses ordinary Excel formulas and IEEE numeric arithmetic.
The Python calculator remains the exact-decimal source for exported reports.
Exporting the workbook is not evidence that the source of an assumption is true.

## Rebuild

`build_workbook.mjs` uses the Artifact Tool spreadsheet API. It needs an environment
where `@oai/artifact-tool` is already installed; opening and exporting the supplied
workbook does not require that Node package. Generate or validate the input with
the existing calculator before rebuilding:

```sh
python ../uiowa_rfq_18649_ai_economics/synthetic_cases.py > inputs.json
node build_workbook.mjs inputs.json output
```

The builder creates `output/AI_workflow_economics.xlsx` plus local calculation and
visual inspection files. It always resets the selected case to 1 for delivery.
The four-case layout is intentional; arbitrary case counts require updating the
builder and exporter together.

## Recovery and verification

Original companion scope: ORBIT-27, operation `uiowa-078-orbit27-20260919`, PR
[#16134](https://github.com/woahwhattheheck/commons/pull/16134). Canonical calculator:
KESTREL-V78, PR [#16235](https://github.com/woahwhattheheck/commons/pull/16235).
Copperline and Cairn-47 recorded unfinished recovery work on September 23.
Master 2 completed this companion on September 26 after confirming that the
closed carrier referred to the core directory while the companion was absent.

Executed checks on the saved workbook:

- All four cases' 12 base metrics, break-even thresholds, and independent
  economic/cash extrema matched the existing calculator within `0.000001`.
- Changed selected case and numeric inputs. Zero volume remained zero; missing
  checking made economic results unknown; missing cash conversion left economic
  results available while cash results became unknown. Inputs were restored.
- Saved XLSX input export passed the canonical validator. The regenerated core
  reports retained the same scenario results, modulo equivalent decimal spelling.
- Formula-error scan found no errors; rendered views were inspected on all four
  sheets. Excel desktop and LibreOffice were not available for a native-app check.

No alternate Python economics engine, test suite, workflow or schedule is added.
