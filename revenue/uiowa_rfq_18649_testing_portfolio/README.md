# Testing-portfolio evidence workbook

This kit completes the executable companion to the published [045 assessment method](../uiowa_rfq_18649_build_board/45-testing-portfolio.md). It turns an editable inventory of business assertions, check definitions and run records into assertion-specific evidence states, a behavior/layer matrix, duplicate candidates, change-based selection and explicit improvement assumptions. It never runs checks, grants a release approval or fetches evidence.

Open **[testing-portfolio.xlsx](testing-portfolio.xlsx)** for the editable worked example. Every example is fictional, including all `synthetic:` run and resolution locators. The command executions described below are executions of this analyzer, not executions of the checks described by the fictional records. None of the examples is a University finding.

## Run the analyzer

Python 3.10 or later, standard library only. From the repository root:

```sh
python3 revenue/uiowa_rfq_18649_testing_portfolio/portfolio.py analyze revenue/uiowa_rfq_18649_testing_portfolio/worked-input.json --format markdown
python3 revenue/uiowa_rfq_18649_testing_portfolio/portfolio.py analyze revenue/uiowa_rfq_18649_testing_portfolio/worked-input.json --format json
python3 revenue/uiowa_rfq_18649_testing_portfolio/portfolio.py analyze revenue/uiowa_rfq_18649_testing_portfolio/worked-input.json --format csv
```

Copy `worked-input.json` to start an assessment. Preserve its stable identifiers, record genuine source locators, and mark the data's actual synthetic status. JSON output retains the complete accepted input, original source bytes, every assertion, run, selection reason and improvement assumption. CSV is the assertion detail view; Markdown is the compact discussion view. All three generated views for the two supplied inputs are committed beside them. Exit 0 means the report was produced, not that the release is acceptable; invalid input exits 2 with a diagnostic.

## What the actual example produces

| Input | Supported assertions | Open-failure assertions | Untested assertions | Uncertain assertions | Out of scope |
|---|---:|---:|---:|---:|---:|
| `imported-claims.json` | 0 | 0 | 0 | 7 | 0 |
| `worked-input.json` | 4 | 1 | 1 | 1 | 1 |

The worked packet describes four fictional service behaviors, eight assertions, seven checks and eight run records. Six current passes support only four assertions: repeated runs do not create new business coverage, and the nominal notification pass does not resolve its earlier failure. The untested RIS propagation assertion remains visible even though a contract check passed. IAM's stale observation remains uncertain. A deliberately excluded acceptance assertion has an explicit scope reason.

`C01` and `C08` are a duplicate **candidate** because their declared assertion, layer, boundary and equivalence key agree. Other layers of the same enrollment behavior remain distinct. Change selection includes the four enrollment checks plus `C07`'s unresolved notification failure outside the changed scope: 12 known estimated minutes **plus** unknown effort for `C03`, not a 12-minute total. No budget silently drops a selected check.

Proposal `P01` has greater assumed gain and lower assumed effort than `P02` for the exact same assertion set. The analyzer identifies this narrow dominance without comparing unrelated scopes or converting qualitative confidence into a score. `P03` remains `UNKNOWN_ASSUMPTIONS`; zero minutes, if expressly supplied, is a valid value and differs from unknown.

## Preserve the original source

```sh
python3 revenue/uiowa_rfq_18649_testing_portfolio/portfolio.py import-source revenue/uiowa_rfq_18649_testing_portfolio/source-portfolio.csv --source-revision 56a48b18202794bca0ef7fb6397f5b1c0da49cec --as-of 2026-09-26 --required-revision synthetic-release-2 --synthetic
```

`source-portfolio.csv` is byte-identical to the existing seven-row build-board table, Git blob `bb7a0005c3c194af3f5e12f15f6d17420ac6d1d1`. Its original author is Keystone, published in [PR #16115](https://github.com/woahwhattheheck/commons/pull/16115). The importer retains every column, exact source bytes as Base64, SHA-256, Git blob ID, supplied revision and row locators. It does not infer existing check identities, run results, complete inventory or current support from the words `Covered`, `Partial` or `Gap`. Each source row becomes a draft required assertion, with a 30-day freshness assumption, for the analyst to edit; neither setting is inferred institutional policy. The importer requires an explicit `--synthetic` or `--supplied-records` label. With no supplied run records, all seven imported assertion claims remain uncertain. A source-revision string and digest identify the caller-supplied source; they do not authenticate it.

The worked packet is an explicitly new fictional extension of those published behaviors. It is not a reconstruction of the unpublished historical run-record example mentioned in [#16161](https://github.com/woahwhattheheck/commons/issues/16161).

## Evidence rules

- Each run binds to one existing check, assertion and behavior. A copied result with mismatched IDs is rejected. Checks also match the assertion's layer. IDs are unique within their record type; duplicate JSON keys are rejected.
- A supporting run has `result: pass`, the exact required revision, a nonfuture observation within the inclusive `max_age_days` window, and at least one artifact locator. The tool checks supplied metadata, not the artifact's contents or authenticity.
- A failure remains open until that record has a resolution date, source locator and disposition. The date must fall between observation and assessment. A later pass, stale age or different revision never silently closes it. A declared resolution is retained, not independently judged correct.
- A required assertion is `OPEN_FAILURE` if any bound failure is unresolved; otherwise it is `SUPPORTED` if a current supporting run exists. Without support, no declared checks plus an explicitly complete inventory is `UNTESTED`; incomplete inventory, missing execution, stale evidence and blocked/unknown results are `UNCERTAIN`. An excluded assertion is `OUT_OF_SCOPE` and requires a reason. All open failures, including excluded scopes, remain in the report and selection.
- Required assertions are declared explicitly. The matrix covers unit, integration, contract, end-to-end and user-acceptance layers without assuming every behavior needs every layer. Empty matrix cells mean no declared assertion at that layer, not a defect or proof of adequate coverage.
- With known change impact, select checks whose behavior components intersect the declared changed components, plus all unresolved failures. Unknown impact selects the whole supplied inventory. This is an analysis proposal, not execution. Incomplete inventory means the proposal may be incomplete.
- Improvement gain is an explicitly subjective `high`, `medium`, `low` or `unknown` category. Effort is nonnegative integer minutes or null. Dominance requires identical assertion sets, no lower gain, no greater effort and at least one strict improvement. It does not measure probability, expected savings, maturity or release safety.

## Workbook workflow

The five tabs have distinct uses: **Portfolio** contains editable assertions and calculated evidence states; **Checks** contains declared inventory and change-scope selections; **Runs** contains exact run bindings, revision, dates and resolution fields; **Improvements** holds editable gain/effort assumptions; **Original source** preserves the source table separately. Amber cells are editable. The original source claims are kept separate from the calculated state.

The workbook contains native formulas for support, unresolved failures, counts, selection and known versus unknown effort. Input errors stay visible; a resolution date alone does not erase a failure. Complete all three resolution fields when recording a disposition. The workbook is a bounded working view of the supplied example, not an XLSX-to-JSON synchronization layer. For additional records, multi-component change selection or full strict input validation, update JSON, run the CLI and regenerate the workbook. Keep full assertion boundaries and source locators in that JSON. Workbook edits are not automatically written back to it. Do not sort isolated columns away from their record IDs.

`build_workbook.mjs` rebuilds the workbook using `@oai/artifact-tool` in an environment where that package is available:

```sh
node build_workbook.mjs worked-input.json output-directory
```

The analyzer itself has no workbook dependency. The saved workbook can be edited directly in spreadsheet software.

## Delivery execution

The source import and both supplied packets were run through the actual CLI; all six report commands exited 0 without stderr. The exported workbook was recalculated, inspected for formula errors and visually inspected on all five tabs. Its 4/1/1/1/1 assertion totals, six current passes, one open failure, 12 known selected minutes and one unknown effort match the CLI. The saved file was reopened, its fictional failure disposition was entered first incompletely and then completely, and the dependent statuses recalculated; explicit zero effort also differed from blank. Original values were restored. The exported file also recalculated in LibreOfficeDev 26.8: all ten key totals matched, with no formula errors in the primary sheet. Excel-specific behavior was not separately exercised.

Use [interview-guide.md](interview-guide.md) to collect the missing evidence and discuss first-failure triage. The existing source methodology remains unchanged.
