# Native UIOWA-039 bridge

This extends the retained UIOWA-124 carrier #16188. The original bridge publication left review-cycle and compiler source unchanged. It used the published contract from ZZ-ORRERY-K47's UIOWA-039/094 source: `review.py` blob `9bf19ae0c022c936e0591a171fa4496f1cb6b282`, `parent_adapter.py` blob `269ed1386917b88cdce79ae4f9c2531d73662176`, branch `swarm-zz/uiowa-039-094-orrery-k47-review`. This supersedes the README's first-publication note that the source was unavailable. The paired-CRLF compatibility update below changes native text validation and Markdown display; bridge, staging-core and compiler behavior remain unchanged.

## Preparation and actual native application

```sh
cd revenue/uiowa_rfq_18649_review_import
python native_bridge.py comments.csv original-draft.json original-report.json \
  --source-id review-round-one --cycle-id REVIEW-ROUND-ONE \
  --new-version DRAFT-2 --out /tmp/uiowa124-preparation
```

Add `--apply-open` to apply the imported OPEN comments through the actual native `build_bundle`, then independently call native `verify_bundle` on the written result. Native parent inspection verification and document validation happen before any output is written. The compiler report is unchanged; no finding, recommendation, evidence, approval, or proposed change is inferred from CSV columns. Native input restrictions are reported, never bypassed or silently normalized.

A complete repository checkout with the native review-cycle and workshare compiler is required for these commands. The bridge creates a new directory and never overwrites an original draft. If no new native comment is available, `--apply-open` creates no empty draft revision. Exit 1 means a written preparation/application still contains unresolved source/native inputs; the full records remain in `preparation.json` alongside every successful mapping. Exit 2 is a structural/dependency/application error.

## Source fields versus native fields

Catalog entries are derived from exact native finding IDs, document version and source index; they carry the native document digest. The native canonical digest includes a final LF, unlike the staging-core digest; this difference is implemented and unit-tested explicitly. Stable native comment IDs are `IMP-` plus the SHA-256 of the logical `(source_id, comment_id)` pair. Unusual source IDs remain untouched in the sidecar instead of being mangled into native identifiers.

`comment_kind` must be one of native `factual`, `evidence`, `wording`, `interpretation`, `priority`; missing/unknown kinds remain unresolved. Original text is passed verbatim to native `comment`. Reviewer roles survive in `mapped[].reviewer_role` and the complete source values. They do not automatically become disposition owners: `owner_role` is `UNASSIGNED` unless explicitly supplied. Source `decision`, `supplied_decision`, `proposed_edit`, and arbitrary extra columns stay in provenance; native `decision` is always `OPEN`, and `proposed_changes`/`source_ids` are empty until actual downstream review.

Same-ID pending native comments with matching target/text are reported `ALREADY_IN_REVIEW`; different text becomes `NATIVE_ID_CONFLICT`. Reapplying an already recorded cycle ID is rejected by native history. Keep each application receipt and use stable cycle IDs; creating a new cycle ID intentionally begins a different review operation. Changed source variants remain unresolved in core state rather than overwriting an earlier import.

Native `text()` now accepts paired CRLF line endings in retained text, alongside the existing LF and TAB support. Validation inspects a temporary line-break view; it does not replace or return normalized text. Native JSON, provenance, hashes and unresolved comments keep the original CRLF characters. Markdown displays each CRLF pair as one `<br>`. Bare CR and the other previously forbidden control characters still fail validation, and the 12,000-character bound still applies to the original string.

The original `review.py` blob above rejected every CR, so the bridge reported `NATIVE_TEXT_REJECTED` for otherwise valid quoted CRLF comments. This update resolves the compatibility request in [#16139 comment5742526634](https://github.com/woahwhattheheck/commons/issues/16139#issuecomment-5742526634) without hidden LF conversion. The published native rehearsal still uses quoted multiline LF comments and CRLF CSV record terminators.

### Executed native workflow, 2026-10-03

The existing `REV-SYN-01` comment from `rehearsal.synthetic_inputs()` was attached to the existing illustrative native draft from `native_rehearsal.py` by specifying that draft's exact finding ID, version and namespace. Original comment text, role, source comment ID, proposed-edit field and synthetic label were retained. The draft report came from the actual parent compiler using the existing `synthetic_packet.json` and `synthetic_authority.json`. This was an illustrative operator execution, with no University input or approval.

Running `native_bridge.py ... --apply-open` on that same input before the change exited 1 with `NATIVE_TEXT_REJECTED` and no native bundle. After the change it exited 0 with one OPEN comment, no native unresolved input, and an 11-file native bundle. Running `review.py verify` on that bundle exited 0 with exact regeneration. The original proposed edit remained provenance only; native `proposed_changes` and `source_ids` stayed empty, all authority flags stayed false, and the compiler receipt stayed unchanged.

The comment's SHA-256 was `d4b35c6a57a5b99ba6df49f1e3917599f98e4bc0726645d6beebe2d7330eefe8` in the input CSV, preparation, native cycle, audit response and revised draft's unresolved record. The source CSV digest survived in provenance, and the Markdown response contained one line break without a stray carriage return. The existing five-row LF input also retained identical preparation bytes and all 11 native bundle members byte-for-byte before and after the change; its two intentionally unresolved source references remained visible. No suite or test files were run or added for this update.

## Full real-parent rehearsal — not a stub

```sh
python native_rehearsal.py --out /tmp/uiowa124-native-normal
python -O native_rehearsal.py --out /tmp/uiowa124-native-optimized
```

This compiles the existing `synthetic_packet.json` and `synthetic_authority.json` with the real parent compiler, validates the real report, builds a native synthetic draft, imports five source rows, then exercises actual native application, rendering and regeneration. Expected preparation: two OPEN comments, two unresolved references, one duplicate source occurrence. A separate, explicitly labelled synthetic disposition fixture accepts one title edit and retains one interpretive disagreement. Neither that fixture nor a supplied CSV decision is used to infer real acceptance. The generated native response bundle must preserve original comment text, retain one unresolved disagreement, keep source/compiler states unchanged, and regenerate byte-for-byte.

The output includes full preparation/provenance, the explicit synthetic review fixture, the native original/revised/response bundle, and a receipt binding actual parent source files and output digests. Any missing real dependency fails nonzero; nothing is silently skipped. `test_native_bridge.py` tests schema preparation with deliberately minimal native-shape objects and an explicit text-rejection callback, not parent integrity. Executed local scope at publication: 48/48 unit/CLI/adapter tests normally and under `-O`; compilation passed. Full-parent execution must be recorded separately before representing the end-to-end path as verified.
