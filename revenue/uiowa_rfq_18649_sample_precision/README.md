# Sample precision companion — synthetic assessment examples

This offline companion makes small denominators and missing outcomes visible.
It separates the observed proportion, possible outcomes in the supplied collection,
and an approximate statistical interval under an explicitly declared model.
**Every supplied example is fictional. None describes University of Iowa performance.**

Open the actual [generated reader worksheet](worked_results.md) or
[machine-readable result](worked_results.json), produced from [fixtures.json](fixtures.json).

Three successes out of three and 300 successes out of 300 both give an observed
100%. They contain different amounts of information under the same independent
Bernoulli model. Neither percentage establishes a maturity level or a department ranking.

## Run

From this directory, with Python 3:

```bash
python3 precision.py fixtures.json --format markdown
python3 precision.py fixtures.json --format json
python3 precision.py fixtures.json --format markdown > sample-precision.md
python3 precision.py fixtures.json --format json > sample-precision.json
```

The commands write results to standard output. Redirection saves the requested view;
choose an unused filename if an earlier output needs to be retained. The program
does not retrieve source documents, inspect live systems or collect observations.

## Input contract

The top-level object uses schema `uiowa-sample-precision/v1`, an explicit boolean
`synthetic` (`true` in all fixtures), a `samples` array and optional `confidence`. Confidence defaults to
0.95 and must be a finite number from 0.5 through 0.9999 inclusive; booleans are
not numbers for this contract.

Each sample provides these fields:

| Field | Meaning |
|---|---|
| `id`, `label` | Stable sample identifier and reader-facing description. |
| `unit` | The individual item counted, such as a normal change or prepared case. |
| `outcome` | The precisely defined binary outcome being counted. |
| `observation_window` | The period or fictional batch represented; state unknown explicitly. |
| `eligible` | Total items in the supplied collection, including unknown outcomes. |
| `success`, `failure`, `unknown` | Nonnegative integer counts that partition eligible items. |
| `sampling_design` | One of the design labels below. |
| `design_basis` | The author's explanation of the design declaration and its limitations. |
| `source_refs` | A nonempty list of source-reference strings. |

Counts must satisfy `success + failure + unknown == eligible`, with each count
at most 10¹²; booleans and fractional counts are invalid. Text fields must be
nonempty and sample IDs unique. Additional fields are preserved as input metadata,
not instructions that override calculated results. Declaring `synthetic: false`
does not verify that any record is real or that its provenance is sound.

Design labels are `independent_bernoulli`, `convenience`, `prepared_demo`,
`census`, `clustered` and `unknown`. They are **caller declarations**.
The software cannot verify independence, common outcome probability, selection
mechanisms, source provenance or whether a declared census is complete.

## Three different quantities

Let `s = success`, `f = failure`, `u = unknown`, `N = eligible` and
`n = s + f`.

| Quantity | Calculation | Interpretation |
|---|---|---|
| Observed outcome proportion | `s / n`, when `n > 0` | Success among items whose outcomes are known. |
| Full-collection bounds | `s / N` through `(s + u) / N`, when `N > 0` | Lowest and highest possible success proportions in these eligible items if unknown outcomes are resolved either way. |
| Conditional Wilson interval | Formula below, only for eligible designs | Approximate uncertainty about a common Bernoulli success probability under the declared model. |

The full-collection bounds are exact arithmetic for the supplied counts. They are
**not a confidence interval** and do not cover unsampled people, services or events.
When all outcomes are known, the bounds collapse to the observed proportion;
that does not mean the underlying process probability is known without uncertainty.

With zero eligible items, neither a proportion nor full-collection bounds exists.
With ten eligible items all unknown, no observed proportion exists, while the
full-collection bounds are 0%–100%. Neither situation is ten observed failures.

## When a Wilson interval is shown

An interval is emitted only when all three conditions hold:

- `sampling_design == "independent_bernoulli"`;
- `unknown == 0`;
- `success + failure > 0`.

The assumed model comprises independent binary trials with a common success
probability. The interval is conditional on that model and the supplied counts.
Declaring the design does not demonstrate that the assumption holds.

Convenience samples, prepared demonstrations, clustered observations, a census,
and unknown designs receive descriptive results without a Wilson interval.
Even a declared independent sample with missing outcomes receives no interval:
discarding unknown outcomes would silently require an additional missingness assumption.

### Formula and primary reference

For level `c`, use `z = standard_normal_quantile((1 + c) / 2)` and
`p = s / n`:

```text
d = 1 + z*z/n
center = (p + z*z/(2*n)) / d
halfwidth = z * sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
interval = [center - halfwidth, center + halfwidth]
```

This is the two-sided Wilson score construction described by
[NIST/SEMATECH, §7.2.4.1](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
It differs from the separate exact binomial construction on that page. The stated
confidence level is a nominal repeated-sampling property under the model;
it is not exact guaranteed coverage or a posterior probability for this particular interval.

At 95%, the formula gives approximately 43.8503%–100% for 3/3,
98.7357%–100% for 300/300, and 0%–56.1497% for 0/3. These are fictional
model demonstrations, not measured organizational performance.

## Relationship to the merged theme examples

The example counts are **hand-transcribed**, not automatically parsed, from
[worked_narratives.md at commit 1bafceba3a902acef861c633d251351e0ed51aaf](https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa_rfq_18649_themes/worked_narratives.md).
That document is itself wholly fictional. Its internal evidence IDs identify the
exact passages; the commit pin preserves the generation used.

| Theme passage | Transcribed interpretation |
|---|---|
| SYN-E1-01: shared incident register | 17 timely updates and one late update among 18 incidents. One shared register reaches three groups; it is not three independent samples. Treat as convenience evidence. |
| SYN-E2-02 through SYN-E2-05: normal changes | 14 confirmed pre-deployment peer reviews, no confirmed non-occurrences, one unknown outcome among 15 normal changes. The unavailable RIS-C04 record is not a failed review. The two urgent restorations are excluded from this denominator. |
| SYN-E3-01 and SYN-E3-02: prepared demonstrations | 15 prepared cases satisfy the three agreed outcome checks. Count 15 cases, not 45 independent observations. No population interval is assigned to prepared examples. |

For the peer-review occurrence example, 14/14 known outcomes equal 100%, while
the full 15-item collection can range from 14/15 to 15/15: 93.3333%–100%.
The distinction concerns missing knowledge about occurrence. A separate question
about whether a record was retrievable would require its own explicit outcome definition.

## Interpretation limits

Larger samples do not cure selection bias or dependence. Full-collection bounds
do not fix an incomplete eligible-item list, incorrect classifications or duplicated records.
The tool does not assess the quality of the sources or determine whether a practice is mature.

Statistical confidence is separate from the assessment kit's confidence in evidence.
Do not import these interval levels as maturity scores, evidence-confidence labels,
rankings, significance tests or proof that one group's practice is better.
Preserve denominators, units, observation windows, design assumptions and unresolved
outcomes whenever a result is copied into a report.

## Verification

Run `python3 -m unittest -v test_precision.py` from this directory, or
`python3 -m unittest -v test_uiowa_sample_precision.py` from the repository root.
The independent suite checks frozen numerical endpoints, missingness and design
semantics, invalid inputs, source preservation, Markdown and actual CLI execution.
The JSON result retains all input extension fields; a sample's optional
`retained_limit` is also displayed in the Markdown worksheet.
