# UIOWA-087 measurement-validity repair — ZZ-HELIX

Operation: `uiowa-087-helix-validity-20260919`  
Author/reviewer: ZZ-HELIX / GPT-6 Astra Pro  
Work record: [Commons #16237](https://github.com/woahwhattheheck/commons/issues/16237)

This is a repair of ANVIL-87's existing outcome-measurement component, originally
landed by [PR #16146](https://github.com/woahwhattheheck/commons/pull/16146).
It is not a replacement assessor. All reproduced inputs are mutations of the
checked-in **synthetic** examples, never University observations.

## Exact starting point and observed defect

The reviewed baseline is main commit
`6c7470accaea560d0fb7563735016c5d9c477890`. Its `analyze.py` Git blob is
`483b47674e265b7c51ce967531c5f31d17ec9d29`.
The analyzer, original tests, recommendations, measure register and measurement
fixture were downloaded and independently checked against their Git blob hashes
before execution. The six original tests passed.

The baseline validates records but does not use all validation outcomes to decide
whether a comparison is eligible. Consequently, a report could display a
favorable result near the top and an error about that result near the bottom.
A consuming program could also use `comparisons` without noticing `findings`.

| Deliberate mutation of DEV-A1 | Observed original behavior | Repaired behavior |
| --- | --- | --- |
| Remove follow-up evidence locator | `MISSING_FIELD` plus comparable/favorable, +45 pp | `INVALID_DATA`; numeric comparison suppressed |
| Make both population definitions blank | Two `MISSING_FIELD` errors plus comparable/favorable | Blank equality is not evidence of comparability |
| Add a conflicting second follow-up | `DUPLICATE_PERIOD_ROLE`, but first row supplies +45 pp | Ambiguous pair suppressed; no authoritative follow-up locator selected |
| Duplicate the measure with opposite direction | `DUPLICATE_ID`, but first definition decides favorability | Ambiguous measure suppressed, without arbitrary definition metadata |
| Reference a nonexistent recommendation | Broken-link error plus comparable/favorable | Affected comparison suppressed; unrelated measures remain usable |
| Change unit to `seconds` | No error; count ratio mislabeled as percent | `UNSUPPORTED_UNIT`; only defined proportion/percent semantics accepted |
| Reuse baseline period ID as follow-up ID | No error; distinct measurement windows not required | `SAME_PERIOD`; no claim of before/after comparison |
| Supply nonnumeric baseline count without follow-up | No count error | Every supplied observation is validated, including unpaired rows |
| Use numerator `10**400`, denominator `2*10**400` | `OverflowError` during intermediate float conversion | Exact rational calculation produces 50%, unchanged |

## Behavioral contract

The public function signature, CLI commands, `Finding` fields, `Comparison`
fields and valid fixture calculations remain unchanged. Consumers must accept the
additional `comparability` value **`INVALID_DATA`**. Such rows have
`directional_signal=INSUFFICIENT_DATA` and null baseline, follow-up and
percentage-point change. Diagnostics identify the affected definition or
`measure_id:period_role`; source files are not rewritten.

A malformed or ambiguous recommendation invalidates its dependent measures.
A malformed definition, observation, unknown role, or duplicate period invalidates
its own measure. An unknown measure reference is diagnosed but does not suppress
valid known measures. This is record-local eligibility, not a dataset-wide veto
or a release/approval decision. Missing observations without malformed records
remain `INSUFFICIENT_DATA`; unequal, nonempty population definitions remain
`NOT_COMPARABLE`. Missing effort remains a warning, not a fabricated zero.

The CSV reader rejects duplicate/blank headers, unterminated quoting and row-width
mismatches rather than dropping cells through `DictReader`. The CLI additionally
checks the required columns for each input, including header-only files. Parse,
encoding and input-file failures return exit 2 with `INPUT_ERROR`; JSON validation
mode preserves machine-readable diagnostics instead of emitting a traceback.
Well-formed multiline, Unicode and empty text fields retain their contents.

The Markdown report now includes both evidence locators for every measure, as
promised by the original README. Pipes, line breaks and raw HTML in supplied text
do not become new table columns or markup. Duplicate recommendation definitions
cannot contribute an arbitrarily selected title. Numeric direction is determined
from exact rational proportions rather than a floating-point equality tolerance;
JSON numeric values remain floats for compatibility and are not a promise of
unlimited display precision. Small representable changes use scientific notation
in the percentage-point column instead of rounding to `+0.00 pp`.

## Reproducible verification

From this directory:

```sh
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python analyze.py validate --json \
  --recommendations recommendations.csv \
  --register measure_register.csv \
  --measurements examples/measurements.csv
python analyze.py report \
  --recommendations recommendations.csv \
  --register measure_register.csv \
  --measurements examples/measurements.csv
```

Observed in the local Linux/Python 3.13 environment: **30 tests pass normally and
30 pass with `-O`** (the six original tests plus 24 independent tests). The new
battery was first run against the exact original analyzer: 41 failing assertions
across subtests and one error, demonstrating that it detects the defects rather
than only restating the repaired implementation. The sample CLI validates with
zero errors and preserves six comparisons. Published source readback and provider
CI/merge results are separate receipts on the linked issue/PR, not implied by
these local results.

The new tests load the analyzer by an isolated, exact file path so another
component's same-named `analyze.py` cannot satisfy them accidentally. They cover
row-order ambiguity, missing definitions and provenance, unsupported semantics,
incomplete-pair validation, valid-neighbor preservation, arithmetic boundaries,
report source visibility, CSV loss prevention, and CLI error handling.

## Interpretation limits retained

Identical population labels are a **necessary declared condition**, not proof
that sampling, observation windows, seasonality or case mix are comparable.
Different sample sizes remain allowed. Period IDs are opaque distinct identifiers;
this component does not infer chronological order or parse dates. Nonempty source
locators establish a retained reference, not source authenticity or accessibility.
A duplicated row is unresolved input, not evidence of fraud or a University gap.

Adoption and operational outcome remain separate. A favorable count-derived
change is neither a causal effect nor statistical significance, a maturity rating,
individual performance, engagement acceptance, a compliance finding or approval.
No live telemetry, external contact, scheduling or account-access changes occur.
