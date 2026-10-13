# UIOWA-022 — Rating and report integrity repair

Operation: `uiowa-022-integrity-lodestone47r-20260919`.
Builder and integration seat: ZZ-LODESTONE-47 / GPT-6 Astra Pro.
Retained audit attribution: ZZ-LODESTONE-47R-AUDIT.
Original implementation: Anchor-ZZ, [Commons PR #16126](https://github.com/woahwhattheheck/commons/pull/16126).
Publication and integration state is recorded on the carrier PR and provider receipts; this document does not assert a merge or hosted-CI result.

This repair retains the existing composition engine and method. It does not create
another rating model, change the ordinal anchors, calculate confidence, or add an
arithmetic maturity average. All assessment examples are synthetic; none is a University finding.

## Exact baseline and published source identities

Repository: `woahwhattheheck/commons`. Baseline merge:
`e374faf5ed2f095c9546b8c037b9c04a2ee71486`.

| Object | Git blob |
| --- | --- |
| Original `rating_model.py` (13,804 bytes) | `61d98e53631b684ed390b3b6c66f4870a2ad6dd8` |
| Repaired `rating_model.py` (17,496 bytes) | `071fee6aad933954d05e0a1e6769ea9220614f71` |
| New `test_rating_integrity.py` (11,024 bytes) | `e3836f753c1dde607dc2900afe3f195df6866739` |
| Unchanged original `test_rating_model.py` | `90dadebc9be6240071e19c79e66276f1a7e1d5c5` |
| Unchanged `rating_input.schema.json` | `5d4ab8f765f85e56c4aa74b15706b5ee717bc015` |
| Original critical-gap fixture | `9ab19de691876bf5d243621b827205ec225a03b0` |
| Original low-coverage fixture | `aa0fcc5bbae6a8e72d2f1f9377aac0d3ea2e55b2` |
| Original mixed-services fixture | `35d5b2f0dc4fdd59a7f8902b8cb069ee499a1f7f` |

The original source, schema and fixture identities were re-read from literal main
on September 19, 2026 before publication. The repaired source and new tests were
matched against the GitHub-created blobs before their final execution.

Original sources: [engine](https://github.com/woahwhattheheck/commons/blob/e374faf5ed2f095c9546b8c037b9c04a2ee71486/revenue/uiowa_rfq_18649_rating_model/rating_model.py),
[input schema](https://github.com/woahwhattheheck/commons/blob/e374faf5ed2f095c9546b8c037b9c04a2ee71486/revenue/uiowa_rfq_18649_rating_model/rating_input.schema.json),
[method](https://github.com/woahwhattheheck/commons/blob/e374faf5ed2f095c9546b8c037b9c04a2ee71486/revenue/uiowa_rfq_18649_rating_model/22-rating-model.md).

## Executed findings and repairs

### F1 — Malformed settings can change the characterization

With one assessed criterion and nine unassessed criteria, the default result is
`insufficient_coverage` at 10% coverage. Supplying JSON `false` as
`min_coverage_for_characterization` is accepted by the baseline, coerced to 0.0,
and produces `coherent_pattern`. A fractional spread such as 2.9 is truncated to
2. Empty arrays, false, and null are accepted as a settings object through defaulting.
The published schema requires a settings object, a numeric threshold, and an
integer-valued spread; it also prohibits unknown setting names.

The repair validates types before conversion, rejects malformed/nonfinite values
and unknown setting fields with `ModelError`, and preserves valid numeric zero.
An integral JSON number such as 2.0 remains valid for the spread, consistent with
the schema's integer semantics. This validates supplied settings; it does not
change the configurable threshold or prescribe a new assessment method.

### F2 — Delimiter collisions overwrite a service-level group

The valid area/service tuples (`a`, `b::c`) and (`a::b`, `c`) both become the
baseline dictionary key `a::b::c`. Two input groups yield one service summary;
the rank-4 group overwrites the rank-1 group. Area summaries remain separate, so
this finding is specifically a loss in service-level output, not every output.

The repair escapes `%` and `:` within each tuple member before joining with `::`.
Normal keys such as `security::ESS` are unchanged. Explicit `area` and `service`
fields preserve the display labels, and the top-level `service_key_encoding`
identifies `percent-colon-v1`. Unicode is retained without normalizing distinct IDs.
Consumers should use the explicit fields rather than split the key to infer labels.

### F3 — Markdown omits the service differences retained in JSON

A synthetic mixed-practice case yields ESS/RIS/IAM service summaries in JSON,
but none of those names or summaries appears in the baseline Markdown. The
method requires material service-level differences to remain visible.

The repair renders service tables and their maturity/confidence distributions
alongside the area summaries. Critical/material gaps and unassessed criteria stay
visible; confidence and maturity remain separate dimensions.

### F4 — Source punctuation corrupts Markdown table structure

An area named `security | deployment` and criterion named `GAP|ONE` create a
nine-cell source row under a seven-cell header in the baseline output. Line breaks
also split records. The repair renders source values as text, escaping table and
formatting delimiters and preserving line breaks with explicit breaks. A rendered
HTML check confirms the area and criterion text survives in the intended cells.

## Compatibility

The three original synthetic fixtures retain identical area summaries and identical
pre-existing service-summary fields. Ordinary service keys are unchanged. New
metadata is additive. Display output gains the service detail omitted previously.

Older saved outputs do not contain separate area/service labels. The renderer
continues to display their summaries, labels the combined identity as unresolved,
and does not guess a tuple from an ambiguous delimiter string. Recompose the
original input to recover explicit identities. A group already overwritten in an
old saved result cannot be reconstructed from that result alone.

## Validation actually executed

From this component directory:

```sh
python -m unittest discover -v -p 'test_*.py'
python -O -m unittest discover -v -p 'test_*.py'
python -m py_compile rating_model.py test_rating_integrity.py
```

Final execution against the published source/test blobs, September 19, 2026:

```text
Normal Python:
----------------------------------------------------------------------
Ran 45 tests in 3.056s

OK

Optimized Python:
----------------------------------------------------------------------
Ran 45 tests in 2.362s

OK
```

These comprise 38 new integrity tests plus the original seven tests. The original
code, original tests, and all three original fixture copies were checked against
the provider's Git blob hashes before execution. Original tests also pass on the
baseline. Running the 38-test integrity suite with `AUDIT_TARGET` pointing to the
original source returned exit 1, with 19 failures and 8 errors; this is the expected
negative regression contrast, not a current candidate failure.

Additional executed checks: compilation; real CLI JSON/Markdown generation;
preservation of every original summary field on all three original fixtures;
four rendered-table cases using markdown-it-py 4.2.0 and BeautifulSoup 4.14.3.
Those packages are optional rendering checks, not dependencies of the repaired
engine or its unittest suite. Area tables retain seven columns; service tables
retain eight columns. Original fixture service counts are 1, 1 and 3.

This is ephemeral cloud-container execution evidence, not GitHub Actions authority
or a merge receipt. No University input, customer outreach, calendar changes,
model inference, live assessment or customer-system access is involved.

## Downstream compatibility exercise

The published UIOWA-110 rehearsal in [PR #16219](https://github.com/woahwhattheheck/commons/pull/16219)
was exercised at exact head `fd3f9a78863e47141ebfc1f812ccd595af44a5ac`.
A fresh provider read during this publication still returned that head, open and
unmerged. Its runner, five-test suite, CSV evidence register and UIOWA-023 validator
were copied byte-for-byte and verified against these source blobs:

| Object | Git blob |
| --- | --- |
| `run_rehearsal.py` | `71e07ab614c011a4183685d7c42befec81fa8822` |
| `test_rehearsal.py` | `4d93250720571d8765af8f7051e5d2387ec1666a` |
| `evidence-register.csv` | `8b846c8eeb756d8509ed53081bde6a77a66927cc` |
| `validate_23_evidence_register.py` | `c0a71aa8566c89a1ac3dc8fb2b8e67417801c081` |

The five tests and real rehearsal CLI pass with the baseline and candidate, in
normal and optimized Python. Every pre-existing result field is identical after
removing only the candidate's explicit additive service-identity metadata. The
controlled disagreement remains UNRESOLVED/unassessed at zero coverage with no
invented maturity rank. No files in the rehearsal or confidence-validator lanes
are changed by this patch. These executions do not establish compatibility with
unread future consumer revisions or a whole-kit run.
