# Procurement loss/debrief remediation

Turn an existing, redacted procurement outcome packet into an internal improvement backlog and a private offline review. This product reuses `tools.procurement_win_loss`; it does not contact buyers, request debriefs, create tasks, connect accounts or infer reasons from free text.

## Prepare, edit, review

From the repository root, with Python 3.10 or later:

```sh
python3 -m tools.procurement_loss_remediation.review prepare /private/outcome.json /private/plan.json
# Edit the three planning arrays in plan.json using the contract below.
python3 -m tools.procurement_loss_remediation.review build /private/plan.json /private/review-new
```

`outcome.json` uses the existing `procurement-outcome-evidence/v1` input contract in `tools/procurement_win_loss/compiler.py`. Preparation compiles that supplied outcome and embeds the resulting native receipt. It does not invent source observations, dates, reasons, classifications, hypotheses or actions. Keep the original outcome evidence separately: generated JSON and caller-supplied hashes do not authenticate its author.

The plan filename and review directory must be **new**, in an existing operator-controlled parent directory. They are never overwritten. Inputs must be regular UTF-8 JSON files of at most 256 KiB; duplicate keys and non-finite values are rejected by the existing reader. A prepared plan that would exceed the same limit is rejected rather than creating unusable input. POSIX output permissions are private (directory 0700, files 0600); filesystem/platform ACLs still apply.

Open `review-new/report.html` locally. It provides searchable tables for every supplied gap version, separately labeled internal hypotheses, retained statement diagnostics, source evidence and native authority fields. Global status and holds stay visible during filtering; printing includes all rows. All displayed input text is escaped. No server, external script, analytics, account or new dependency is required.

The three download links save the exact native report, gap CSV and retained input without leaving the page, including when JavaScript is disabled. Their bytes are embedded in the generated HTML so local-file browser restrictions do not turn JSON downloads into navigation. **The HTML itself therefore contains the complete private input**, as well as the separately saved `input.json`; treat both as private. Opening the report does not send these bytes anywhere. Long hold identifiers wrap within narrow screens.

The directory contains:

- `input.json`: the exact input bytes used for that review, including the complete private packet;
- `report.json`: the unchanged compiler output, including its native integrity fields;
- `gaps.csv`: every submitted gap version, with opportunity, packet timestamp, global status and basis validity repeated on each row;
- `report.html`: the offline reader, written last.

CSV cells beginning with spreadsheet formula markers receive an apostrophe. Import CSV columns as text when exact identifiers matter; `report.json` remains the unmodified machine-readable representation. There is no implicit latest-version selection and no automatic action on a row. On a delivery I/O error, inspect the incomplete private directory and rerun into a new directory; the tool does not delete or overwrite existing work.

## Editing a prepared plan

Keep `schema`, `outcome_record` and `outcome_receipt` together. Changing outcome evidence requires recompiling the outcome receipt; editing a digest is not a substitute. Preparation leaves these three planning arrays empty:

### `buyer_reason_mappings`

Each entry has `reason_id`, `evidence_id`, `source_digest_sha256` and `category`. Bind an explicit retained rationale statement from `outcome_receipt.rationale.statements`; do not classify an unstated reason. Categories are `QUALIFICATION_EVIDENCE`, `SCOPE_TECHNICAL_FIT`, `PRICE_BASIS`, `PROCESS_COMPLIANCE`, `SCHEDULE_CAPACITY`, `PARTNER_WORKSHARE` and `OTHER_STATED`.

The category is an operator classification. The displayed statement is **caller-retained, source-bound, not buyer-authenticated**. Merely labeling a source `BUYER_NOTICE`, or supplying a digest, does not establish who authored it.

### `internal_hypotheses`

Each entry has a unique `hypothesis_id`, `text`, `confidence` (`LOW`, `MEDIUM` or `HIGH`) and nonempty `evidence_basis`. Each basis reference has `evidence_id`, `source_digest_sha256` and `observed_at`, copied exactly from the corresponding `outcome_receipt.known_facts` entry. Every reference must resolve to current, terminal evidence in that packet.

Hypotheses remain internal ideas, not buyer-stated facts or explanations of why a bid lost. Hypothesis/action text is limited to 400 characters and rejects obvious contact/locator-shaped content. That screening is not comprehensive anonymization; redact private material before use.

### `remediation_gaps`

Each entry has `gap_id`, positive integer `version`, `gap_kind`, `rail`, `basis_type`, `basis_id` and `action`. A `(gap_id, version)` pair must be unique. `basis_id` references the chosen namespace, never the other one.

Kinds: `CAPABILITY`, `EVIDENCE`, `PROCESS`, `PARTNER`, `SCHEDULE`, `PRICING`, `OTHER`.

Rails: `SOLICITATION_EVIDENCE`, `RESPONSE_MODULE`, `OPPORTUNITY_QUALIFICATION`, `PARTNER_WORKSHARE`, `DELIVERY_PROCESS`, `PRICING_BASIS`. These are internal classifications, not automatic writes to another tool.

Basis types are `INTERNAL_HYPOTHESIS` and `BUYER_REASON`. The current engine can support internal experimental gaps with valid internal-hypothesis evidence. A `BUYER_REASON` gap cannot be authorized by this product because it has no independent buyer-source authentication; it remains on hold. Do not relabel a purported buyer fact as a hypothesis to imply buyer authentication.

## Interpreting the result

`ACTIONABLE_GAPS` means an internally supported review backlog, not a buyer finding or permission to publish, contact, pay or execute a task. `NO_ACTIONABLE_GAP` means no gap was supplied to an otherwise coherent packet; it does not prove nothing should improve.

`HOLD_SOURCE` indicates unknown or conflicted source outcome. `HOLD_CONTRADICTION` indicates a binding/basis problem or an unauthenticated buyer-reason authorization attempt. `HOLD_UNATTRIBUTED_REASON` means one or more retained rationale statements have no explicit taxonomy mapping. All holds remain visible. A basis-valid row never overrides a global hold.

**Snapshot, not live status:** the preserved engine evaluates chronology/currentness within the supplied outcome packet. Opening or rebuilding an old packet does not refresh its clock, source labels or observations. Obtain and compile an updated source packet when fresh evidence is needed. The report cannot prove that an old `CURRENT` label is still current now.

Existing machine interfaces remain available:

```sh
python3 -m tools.procurement_loss_remediation compile /private/plan.json > /private/report.json
python3 -m tools.procurement_loss_remediation verify /private/plan.json /private/report.json
```

The shell redirection in the legacy compile command can overwrite its target; use the new-directory review command for non-overwriting delivery. Verification recomputes packet binding and semantics, not buyer authenticity. All buyer/debrief/outbound/provider/contract/payment/cash/revenue/causal-inference authority fields remain false.

## Operator execution receipt (2026-10-03)

Python 3.12.14 and Chromium 153.0.8010.0 exercised the actual preparation, review build, native compile/verify and saved `file://` report. Inputs came from the existing synthetic `procurement_win_loss/fixtures.json`: loss with unknown rationale, the retained stated award rationale, and conflicting current terminal evidence. Explicit illustrative plan edits added one separately labeled internal hypothesis with two gap versions, and one buyer-reason gap to observe its required authentication hold. No real buyer record was used.

All four states (`NO_ACTIONABLE_GAP`, `ACTIONABLE_GAPS`, `HOLD_CONTRADICTION`, `HOLD_SOURCE`) verified. Their native JSON, retained input and CSV stayed byte-identical through the renderer repair. Every authority remained false, and the recorded packet time stayed `2026-09-17T03:00:00Z`. Existing plan/output destinations refused overwrite.

Actual desktop and 390-pixel browser flows covered filtering, clearing the search, visible global holds, complete printing and JavaScript-disabled content. Twelve artifact downloads matched the corresponding files exactly; three additional downloads with JavaScript disabled also matched and kept the page open. Before the repair, all eight JSON clicks navigated away instead of downloading, and the two hold pages widened to 474 and 394 pixels. Afterward all four pages stayed at 390 pixels. Print PDFs retained status, holds, actions, rationale and complete digests despite an active no-match filter; returning to screen preserved that filter. No page/console errors or HTTP requests occurred. This is local operator execution evidence, not buyer authentication, live source currentness or authorization to perform the proposed actions.

## Recovery lineage

This is the production continuation of [#15154](https://github.com/woahwhattheheck/commons/issues/15154), preserving Forge, Meridian, Ironwood, Argosy, Cinderline and prior finalizer/reviewer credit. The source was retained in [#15593](https://github.com/woahwhattheheck/commons/pull/15593), [#15711](https://github.com/woahwhattheheck/commons/pull/15711) and [#15716](https://github.com/woahwhattheheck/commons/pull/15716) but stranded when both successor PRs were closed unmerged in favor of each other. The September 2026 recovery retains the existing engine and verifier, without restoring the old test corpus or CI enrollment. The offline operator reader and preparation command are the new delivery layer.
