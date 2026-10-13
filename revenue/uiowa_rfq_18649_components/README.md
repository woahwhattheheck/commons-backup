# UIOWA-056: component maintenance assessment kit

**Fictional rehearsal and interview preparation. Not University findings.**

This offline instrument turns a supplied inventory, support records and advisory dispositions into an evidence-qualified component register and a maintenance decision queue. It is useful when several applications inherit a shared component, support dates are uncertain, or an advisory has a closure label but no closure evidence.

It does not scan systems, fetch advisories, execute dependencies, authenticate evidence, recommend products, send messages or change infrastructure. Component presence, support status, advisory applicability and reported exposure remain separate. Nothing in the output is a compliance certificate, vulnerability severity score or maturity rating.

## Run the complete rehearsal

The core and its verifier require Python 3.10+ and the standard library only. Run from this directory in an isolated working copy:

```sh
python -m unittest -v
python -O -m unittest -v
python example.py
python components.py sample.json --out rehearsal-output
python verify_bundle.py sample.json rehearsal-output
```

`example.py` writes `sample.json` in the working directory. It is a fictional fixture generator, not an importer; do not run it over a real input with that name. The assessment CLI refuses an existing output directory. Choose a new output directory for a subsequent run. Validation completes before that directory is created. An I/O failure during writing can leave a partial directory: never consume a bundle that fails `verify_bundle.py`.

A valid run produces eight files: `assessment.json`, five CSV tables (`components`, `advisories`, `roadmap`, `evidence`, `services`), `summary.md`, and `manifest.json`. CSV values that resemble spreadsheet formulas are emitted as text. Markdown table content is escaped. The JSON is the machine interchange, not a spreadsheet round-trip format.

`manifest.json` identifies the canonical input and output bytes with SHA-256. A manifest is an integrity convenience, not an authority. The verifier independently regenerates all eight expected files from the supplied original input, checks the exact file set, rejects symlink members and compares bounded reads byte for byte. A fabricated report with freshly recomputed manifest hashes still fails. This establishes agreement with this evaluator and this input; it does not establish that the input is truthful.

## Workbook and human decisions

`workbook.py` is an optional presentation adapter. It uses the Python `artifact_tool` SDK when available and falls back to the companion `workbook.mjs` when the runtime provides the JavaScript `@oai/artifact-tool` SDK. Neither SDK is a dependency of the assessment or verifier.

```sh
python workbook.py sample.json --out component-maintenance.xlsx
```

The same command now works in runtimes that provide the JavaScript SDK. Both adapters consume one shared Python presentation payload and the unchanged evaluator; no assessment rules are translated into JavaScript. The fallback uses `CODEX_PRIMARY_RUNTIME_NODE` when set, otherwise `node`, and uses `CODEX_PRIMARY_RUNTIME_PYTHON` when supplied, otherwise the invoking Python executable. The companion can also run directly:

```sh
node workbook.mjs sample.json --out component-maintenance.xlsx
```

Direct JavaScript execution uses `CODEX_PRIMARY_RUNTIME_PYTHON` when set, otherwise `python3`; `@oai/artifact-tool` must already be resolvable by Node. No package is downloaded automatically. Both commands reject an existing output path. The JavaScript writer also uses an exclusive final file create, so a competing file or final symlink is not overwritten.

The workbook retains every native component and advisory column, including component version, inherited ownership, declared support, advisory count, advisory intake date and conflicting-record flags. The original leading columns and eight Overview formulas keep their existing references. The current JavaScript view also displays service/advisory counts and the exact evidence-age/planning-horizon parameters, with typed dates, numeric effort, tables, frozen headers and the existing decision dropdown. Blank effort stays unestimated, and a real zero remains numeric. Manual decision notes do not change assessed states or the native bundle.

The seven sheets are Overview, Components, Advisories, Roadmap, Evidence, Services and Decisions. Overview formulas count the assessed records and sum only known effort bounds. Generated sheets retain evidence IDs and service scope. Blue cells on Decisions are editable human preparation notes: owner role, proposed decision, rationale, source reference and next review date. The decision dropdown is Investigate / Plan / Defer / No change. A spreadsheet selection does not authorize a system change, close an advisory or update canonical assessment data.

The workbook CLI refuses an existing output path. To assess changed data, modify a copy of the canonical input, obtain appropriate source records, and regenerate into a new location. Do not change a generated status cell and present the edited workbook as the output of the verifier. The verifier covers the deterministic eight-file bundle, not manually edited workbooks.

## Record contract: `uiowa.components.v1`

Use the fully populated `example()` factory in `example.py` as the schema example. Unknown fields, missing fields, duplicate IDs, duplicate JSON keys, unresolved references and incorrectly typed scalars are rejected rather than guessed. Input is UTF-8 JSON, limited to 4 MiB. No fallback to pickle, YAML, executable expressions or remote resources exists.

The root contains the schema version, `as_of`, `max_evidence_age_days`, `horizon_days`, `services`, `evidence` and `components`. Services have an ID, a name and a group: ESS, RIS or IAM. Evidence carries an ID, kind, observation date, locator, component scope and (where applicable) advisory ID. Evidence kind is inventory, support, advisory, exposure, closure, exception or update. Locators are retained as supplied text and are never opened.

A component records its name, version, affected service IDs, owner role, whether responsibility is inherited, support state/end/evidence, inventory evidence, review date, last update date, advisory records and a proposed maintenance change with an effort range. Advisory records carry intake date, applicability, reported exposure, disposition, owner role, due date, exception expiry and separate evidence reference lists. An exception or closure reference must have the correct evidence kind, component scope and advisory scope; its observation must not predate advisory intake.

Dates must be exact `YYYY-MM-DD` calendar dates. Future observations, update dates and advisory intake dates are invalid relative to `as_of`; future due dates and support horizons are allowed. Evidence exactly at the configured age limit is current. A support end date and exception expiry are inclusive through the stated day; they expire the following day. A review due today is not yet overdue. These are explicit instrument conventions, not universal policy requirements.

Support evidence must be current to qualify a supplied supported or unsupported claim. Missing or stale support references yield unknown, including a historical unsupported label that no longer establishes today's state. An unsupported declaration with a future support end date is a conflict to reconcile, not an automatic finding. A supported component without an end date remains supported on supplied evidence but receives an action to establish its planning horizon.

Applicability and reported exposure require their own current references. An unsupported component is not automatically exposed. `not_observed` is not proof of absence. A closure label without current scoped closure evidence remains `unverified_closure`. An accepted-risk label becomes a current recorded exception only with current scoped evidence, an owner role and an unexpired date. The exposure record remains visible. Contradictory not-affected and confirmed-exposure records remain a conflict even alongside documented closure.

## Workflow priorities and effort

Priority 1 means review a reported exposure or conflicting applicability/exposure record; priority 2 means time-sensitive maintenance, ownership or advisory review; priority 3 means establish supporting evidence or planning context. These priorities are preparation queues, not a claim that the tool has calculated exploitation risk or approved remediation.

Each component contributes at most one maintenance item. Its service references remain attached, so a shared ESS/RIS component is not counted twice. The proposed change and effort bounds are input assumptions, not calculated engineering estimates. Both effort bounds must be finite, nonnegative and ordered, or both must be null. Known bounds are summed separately from the count of unestimated items. The latter never silently becomes zero. Coordination overhead must be included in the proposed bounds by the person supplying them; the tool does not invent it.

## Worked result, not a University finding

The seven fictional components yield three supported, one ending-soon, one unsupported and two unknown support records. Five supplied advisory records produce five component-level maintenance rows. Known preparation effort totals 9–16 person-days, with one additional unestimated item. That is not a complete project price or duration.

C02 illustrates the shared-component rule: one inherited component supports ESS and RIS, lacks an owner, is unsupported on current supplied evidence and has an affected advisory with unknown exposure. It creates one 5–9 person-day maintenance row, not two rows and not an automatic confirmed-exposure finding. C03 demonstrates an expired exception and unsupported not-affected/exposure claims. C04 demonstrates an approaching support boundary, stale inventory and an unverified closure. C05 demonstrates stale historical unsupported evidence. C06 retains reported exposure while showing a current exception due for review. C07 has documented closure on supplied current evidence, not independently authenticated proof.

See [INTERVIEW.md](INTERVIEW.md) for the facilitator script, source requests, decision record and follow-through workflow.

## Practice reference and limitations

NIST describes the Secure Software Development Framework as outcome-based practices that organizations adapt to their context, rather than a fixed checklist: [official SSDF project](https://csrc.nist.gov/projects/ssdf), [SP 800-218 version 1.1 publication](https://csrc.nist.gov/pubs/sp/800/218/final). This kit uses that contextual, evidence-seeking approach; it does not claim a verified requirement-by-requirement NIST mapping. The fixture's 120-day evidence age and 90-day planning horizon are configurable rehearsal assumptions, not NIST mandates.

A fresh locator does not authenticate a document. Component IDs and referenced evidence are supplied by the preparer; the tool does not discover version applicability, parse vendor lifecycle calendars, validate contracts, collect source content or establish that an advisory feed is complete. `last_update_on` is supplied metadata, not independently verified update evidence. No advisory entries must never be described as no vulnerabilities. Empty inventory must never be described as healthy inventory. A human must resolve missing ownership, conflicting sources, real lifecycle semantics, applicability, exposure and acceptance authority.

## Publication and attribution

Builder: **ZZ-KESTREL-731 / GPT-6 Astra Pro**. Operation: `uiowa-056-kestrel731-20260919`.

Work record: [issue #16113](https://github.com/woahwhattheheck/commons/issues/16113). Code carrier and current review/merge state: [PR #16207](https://github.com/woahwhattheheck/commons/pull/16207). Local execution receipts are separate from hosted GitHub Actions and do not establish that the PR is merged. This module is additive and does not alter the workbench, compiler, credential paths, control-plane policy or other seats' assessment rules.
