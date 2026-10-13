# UIOWA-076 source trace and missing-context contract

This is a focused follow-up to COPPERFIN-73's UIOWA-076 kit and PR #16252.
Implementation and independent regression review: **ZZ-ASTRA-FORGE / GPT-6 Astra Pro**.
Operation: `uiowa-076-independent-review-astra-forge-20260919`.
All examples remain fictional preparation, not University findings or a causal AI-effect study.

## What changed

Each analyzed change now carries a detached `source_trace` object:

- `started_at`, `accepted_at`, and `acceptance_evidence_ids` retain the actual observation and acceptance binding.
- `followup` retains the declared days, actual endpoint, coverage, reported fault count and its own evidence IDs.
- `coverage` retains each stage's state, explanatory basis and evidence IDs, separate from the allocated effort's evidence.
- `effort` retains each allocation's unique ID, stage, exact decimal value as a string (or null), and evidence IDs.

The trace is sorted deterministically where order has no meaning. Nulls remain null, exact source-ID spelling and timestamp strings survive, and all copied lists/mappings are detached from the caller. A caller changing an input after `analyze` returns cannot silently edit the issued analysis. The original source registry still includes full-file hashes and exact excerpts. These relationships supplement that registry; they do not authenticate its contents.

Markdown now prints the acceptance and follow-up source references and dates, coverage explanations and allocated effort IDs. JSON carries the complete structured trace. CSV deliberately remains the original summary format; it must not be presented as the lossless evidence interchange. Keep the retained input/source bundle alongside the reports.

## Explicit missing context

For the four context dimensions (`task_fingerprint`, `stack`, `complexity`, `criticality`), null or the explicit word `UNKNOWN` (case-insensitive, surrounding whitespace ignored for this test only) denotes missing context. Original values are retained, not rewritten. Each missing arm/dimension adds a reason such as `assisted_stack_unknown` and suppresses all paired deltas.

A missing comparison context does not erase known effort or fault observations for either individual change. Two unknowns are not a demonstrated match. Other nonempty labels are not guessed from prose: `unknown-runtime-v2` is an ordinary label, not automatically missing. Inputs using other placeholder conventions must explicitly map those placeholders to null or UNKNOWN before assessment. Empty strings, nonstrings and malformed shapes remain input errors.

Known matching context, supported complete records and exact follow-up windows preserve the existing comparison behavior. The original ESS / RIS / IAM numerical examples are unchanged.

## Executed review

Run in this directory:

```sh
python -m unittest -v test_ai_coding.py test_source_trace.py
python -O -m unittest -v test_ai_coding.py test_source_trace.py
python rehearse.py --out /tmp/uiowa076-new-rehearsal
```

The exact published original three Python files were verified against their Git blob hashes before independent execution. The original suite passed 36/36 in each mode. Five separate edits to a source binding, coverage statement, allocation ID or real observation dates produced an identical entire report before this repair. Matching literal UNKNOWN context also yielded a positive pair comparison. The independent suite detects these conditions against that original source.

After repair: **58/58 normal and 58/58 optimized tests pass**, with no skips (36 original plus 22 new methods). Parameterized missing-context coverage spans four dimensions, four missing representations and three arm combinations. The new subprocess acceptance tests inherit the actual optimization flag for both generator and analyzer. Two independently generated rehearsal directories compare byte-identical; manifest hashes are checked against the actual written files.

`source_trace_validation.json` records exact source hashes, commands, counts and before/after observations. This is ephemeral-cloud component execution, not hosted Actions or repository-wide success. No browser rendering or native Windows execution is claimed. The original builder owns the separate import-isolation repair; its generator and test files are not changed by this contribution.

## Interpretation boundary

Changing a citation to another existing registry ID must change the report, even when the numerical outcome remains equal. The analyzer still cannot decide from an ID alone that the new source is relevant. An assessor must read the preserved source binding, its excerpt, coverage qualification and actual observation window before interpreting the outcome. A transparent wrong citation is reviewable; a discarded citation is not.
