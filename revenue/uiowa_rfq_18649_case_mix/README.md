# Case-mix comparison lab

This offline, dependency-free Python tool makes aggregate benchmark reversals visible. It preserves event, non-event and unknown counts; compares groups under an explicitly chosen common category mixture; and reports exact bounds when outcomes or categories are missing. It is descriptive arithmetic on supplied records, not a statistical, maturity, causal, procurement or institutional conclusion.

## Run it

From the repository root:

```sh
python3 revenue/uiowa_rfq_18649_case_mix/case_mix.py demo
python3 revenue/uiowa_rfq_18649_case_mix/case_mix.py compare revenue/uiowa_rfq_18649_case_mix/examples/reversal.json --format json
python3 revenue/uiowa_rfq_18649_case_mix/case_mix.py compare revenue/uiowa_rfq_18649_case_mix/examples/missing-category.json --format markdown
```

Each editable input in `examples/` has the actual CLI-generated `.report.json` and `.report.md` beside it. Copy an input, edit its definitions/counts/source locators and reference rationale, then run `compare`. All four provided examples are explicitly fictional. JSON retains every accepted input field. The reports contain a digest of canonical JSON, not a hash of the original file bytes or proof of source authenticity. The CLI never connects to a service or alters its input.

`demo --case NAME --format input` exports any built-in example. Available names: `reversal`, `missing-outcomes`, `missing-category`, `incompatible-definition`. Exit 0 means a report was produced, including a valid `NOT_COMPARABLE` report; exit 2 means unreadable or invalid input. Consumers must inspect each pair's `eligibility` and `reasons`, not only the exit code.

For Python callers:

```python
from revenue.uiowa_rfq_18649_case_mix.case_mix import analyze, loads
from pathlib import Path
report = analyze(loads(Path("my-comparison.json").read_bytes()))
```

## Worked results

The examples describe fictional routine-heavy A and complex-heavy B samples. A has 90/100 routine events and 1/10 complex events; B has 19/20 routine events and 50/100 complex events. B has a higher event fraction in **both** categories, while A has the higher raw aggregate because its sample contains many more routine changes.

| Input | A raw rate | B raw rate | A common-mix rate | B common-mix rate | Pair result |
|---|---|---|---|---|---|
| `reversal.json` | 91/110 | 23/40 | 1/2 | 29/40 | Raw A higher; common mix B higher |
| `missing-outcomes.json` | 91/110 | [23/40, 89/120] | 1/2 | [29/40, 33/40] | Same ordering throughout these outcome bounds |
| `missing-category.json` | 91/110 | 19/20, supplied routine rows only | 1/2 | [19/40, 39/40] | Common-mix ordering unresolved |
| `incompatible-definition.json` | Individually reported | Individually reported | Individually reported | Individually reported | No pair comparison: follow-up definition differs |

All examples use caller-selected weights of 1/2 routine and 1/2 complex. In the complete example the exact first-minus-second raw difference is 111/440; its common-mix difference is -9/40. These are differences of event fractions, not likelihoods of superiority. `A_HIGHER` means the numerically higher fraction; it does not mean better when `direction` is `lower_is_better`.

## Input contract

Schema: `tjlabs.case-mix.input/v1`. The examples are complete editable templates. The parser requires exactly the documented fields, rejects duplicate JSON keys and nonfinite numbers, and limits input to 256 KiB.

| Object | Required fields and meanings |
|---|---|
| Root | `schema`, boolean `synthetic`, `population_note`, `reference`, `groups` |
| Reference | `rationale`; `weights` maps every category name to an exact rational string such as `"1/2"` or `"0.25"` |
| Group | Unique stable `id`, human `label`, `metric`, `rows` |
| Metric | `event_definition`, `eligible_definition`, `strata_definition`, `unit`, `window_start`, `window_end`, `direction`, `measure_class` |
| Row | Unique `stratum` within group, nonnegative integer `events`, `non_events`, `unknown`, nonempty list of `sources` locators |

There must be 2–20 groups and 1–64 reference categories. Counts are integers from 0 to 1,000,000,000, not booleans or percentages. Each row has 1–20 nonempty source locators. Rows can be absent, but cannot name a category outside the reference universe. Every reference weight is nonnegative, no greater than one, and the weights must sum **exactly** to one; the engine never invents a mixture, drops a missing category, or renormalizes weights. Zero-weight categories do not widen common-mix bounds. Fraction denominators are at most 1,000,000,000.

Dates use `YYYY-MM-DD` and a positive start-inclusive/end-exclusive window. `direction` is `higher_is_better` or `lower_is_better`; `measure_class` is `observed_outcome`, `target` or `unknown`. Pairwise comparisons require exact equality of **all eight** metric fields and `observed_outcome` in both groups. Different units, eligibility definitions, category definitions, follow-up rules, windows or directions produce `NOT_COMPARABLE`. Equality is only the caller's declaration of compatibility; it cannot establish that collection procedures truly matched.

## Arithmetic and limits

For each supplied category, let `n = events + non_events + unknown`. If `n > 0`, the rate bounds are `[events/n, (events+unknown)/n]`. An absent category or a category with no eligible records contributes `[0,1]`. The common-mix bounds are the sums of each category's lower and upper bounds multiplied by the declared reference weight. A point estimate appears only when the resulting endpoints agree. All analytical operations use rational arithmetic; percentages in Markdown are rounded display values.

The raw rate uses only supplied rows, including their unknown outcomes. It does not infer the workload of absent categories. `reference_coverage` is the sum of weights with at least one supplied eligible record; it measures category coverage, **not** completeness of follow-up outcomes. Pair differences use `[A_low - B_high, A_high - B_low]`. Overlapping bounds produce `UNRESOLVED`, not equality. `uniform_reversal` requires every reference category to have eligible records in both groups and all category differences to oppose the raw difference throughout their supplied outcome bounds.

These bounds do not measure sampling uncertainty, dependence, selection bias, outcome misclassification, uncaptured records, or effects of unmeasured categories. They are not confidence intervals. Different reference scenarios can give different descriptive answers. The inputs' selection and provenance still require human assessment; use `reviewer-worksheet.csv` to record it.

## Reuse the published metric-comparability table

```sh
python3 revenue/uiowa_rfq_18649_case_mix/case_mix.py peer-table revenue/uiowa_rfq_18649_workbench/19-metric-comparability.csv
```

This command retains every source row and adds a next-input prompt. It deliberately does not reverse-engineer counts or category mixtures from a percentage, target, policy, median or scale example. It does not fetch or reverify the cited pages.

The actual command was run on the 26-row 019 table at repository commit `802c3a9be338e130127ec4c31f3d64c421d85ef3`, source blob `4812b28161f8955f5d23bbe1464033e6578f09c3`: all 26 rows were retained and every conversion state was `NOT_ATTEMPTED`. The four editable input files were each run through the JSON and Markdown CLI formats, producing the committed reports. All nine commands exited 0 without stderr.

## Recovered work

Completes work item [#16206](https://github.com/woahwhattheheck/commons/issues/16206). The calculation engine and built-in examples are the original work of ZZ-MERIDIAN-47, recovered from branch `swarm-zz/case-mix-meridian47-20260919`, commit `0718ac4e7b1201e815767f8dcc639ccdb8e0418a`, original source blob `a920e610d740844919af374785732bb677ae0eaa`. This completion preserves that engine and adds its operator guide, reusable reviewer worksheet, editable input exports and actual output reports. The only engine change makes invalid text encoding follow the existing CLI input-error path. Existing assessment/comparison engines are unchanged.
