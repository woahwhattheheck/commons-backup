# Interpreting assessment-time and coverage evidence

This is an operator guide for the existing UIOWA-047 assessor. It does not inspect
a University system, establish compliance, certify a dataset or authorize a
change. The underlying repair and its historical execution remain in
[PR #16397](https://github.com/woahwhattheheck/commons/pull/16397) and
[issue #16367](https://github.com/woahwhattheheck/commons/issues/16367).

## Dates describe evidence as of the assessment

A date after the assessment does not establish that an activity was completed at
that assessment date. For example, a fictional September 20 refresh cannot
establish September 19 freshness. The record may describe a plan, an incorrect
date or later work; this kit does not choose which explanation is true. It returns
UNKNOWN, preserves the chronology in its explanation and asks for contemporaneous
evidence or a source-supported correction. It does not infer that the practice failed.

Same-day refresh and cleanup dates are usable. Refresh age equal to a declared
positive cadence is not overdue; age greater than that cadence is an OBSERVED_GAP.
Cleanup declared explicitly not required does not acquire a requirement merely
because a date is also supplied. A date does not supply a missing applicability flag.

## Missing inventory is not an empty inventory

With a documented requirement for case `empty`, an absent or null covered-case
inventory leaves coverage UNKNOWN. An explicit `[]` records no covered cases and
exposes an OBSERVED_GAP against that requirement. Neither input is rewritten into
the other. An unknown or unusable requirement inventory precludes a coverage verdict.

Coverage inventories must be lists of nonblank string identities. A string is
not a list of observed cases, a dictionary's keys are not observed coverage, and
integer `1` is not string `"1"`. Malformed evidence remains UNKNOWN rather than
being coerced into a favorable result or crashing the report. Valid duplicate
identities count once. Case, spacing within an identity and Unicode representation
are not silently normalized to make different identifiers agree.

These rules interpret the supplied catalog; they do not authenticate its claims.
EVIDENCED means the supplied record supports the particular check under the field
contract, not that a complete population or independent source has been examined.

## Use the original fictional demonstration

From this component directory:

```sh
python3 test_data_assessor.py fixtures/catalog.synthetic.json --format json
python3 test_data_assessor.py fixtures/catalog.synthetic.json --format markdown
```

See [the demonstration interpretation](synthetic_rehearsal.md) for the three
fictional service records. No record is University evidence. These commands print
results; saving a report has the separate [output contract](OUTPUT_PRESERVATION.md).
Exit 0 means a report was produced, not that every check was evidenced.
