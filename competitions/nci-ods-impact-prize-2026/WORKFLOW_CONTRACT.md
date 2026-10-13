# ReuseLedger downstream workflow contract

This companion extends the existing merged ReuseLedger compiler without changing it. All records are declarations. A local byte/digest match does not establish real-world reuse, credit, rights, consent, scientific impact or source authenticity.

## Commands

Run from this directory with Python 3.10+ (standard library only):

```
python3 reuse_workflow.py init example_outputs.json --out journal-0.json
python3 reuse_workflow.py record example_outputs.json journal-0.json reuse_event_example.json --out journal-1.json
python3 reuse_workflow.py bundle example_outputs.json journal-1.json --out handoff
python3 reuse_workflow.py verify handoff
```

Success exits 0. Invalid input, I/O failures, existing output or inconsistent bundle exits 2 with a readable ERROR message. No input is rewritten. Every output destination must be new. Bundle validation and rendering happen before creating its directory. Receipt is written last; an interrupted filesystem write may leave an incomplete directory which verification rejects. No atomic multi-file publication is promised.

## Event input

Exact keys, no extras; duplicate JSON keys rejected at every nesting level:

```
{
  "schema": "nci-reuseledger-event/v1",
  "id": "urn:reuse-event:fictional-001",
  "state": "reported",
  "recorded_on": "2026-09-19",
  "occurred_on": "2026-09-18",
  "purpose": "Fictional methods comparison",
  "downstream": {"id": "https://example.org/fictional-follow-up", "version": "draft-1"},
  "upstream_ids": ["urn:example:dataset-1"],
  "credit_refs": null
}
```

IDs and credit references must match the core HTTP(S)/DOI/URN identifier syntax. These are declared identifiers; the tool does not fetch or validate their public existence. Strings are trimmed, nonempty and bounded. Downstream version is nonempty text or null (unknown). `upstream_ids` is a nonempty unique array of IDs in the bound manifest, sorted in normalized records. Credit is null (unknown), [] (explicitly none supplied), or a unique list of declared credit identifiers, sorted. These three states remain distinct. At most 1000 upstream IDs and 1000 credit refs per event; at most 10000 entries per journal.

State is exactly `planned` or `reported`. Dates are real calendar dates in exact YYYY-MM-DD form. Planned events require occurred_on=null; reported events require occurred_on <= recorded_on. A journal's recorded_on values must be nondecreasing. No live-clock comparison; replay is deterministic and dates are declarations. Event IDs are unique within a journal. Later entries never silently replace earlier entries. A changed status is a new record with a new event ID; counts describe records, not deduplicated real-world impact.

## API and derived journal

Module reuse_workflow exposes `WorkflowError` (ValueError subclass), `init_journal(manifest, raw_bytes)`, `record_event(manifest, raw_bytes, journal, event)`, `validate_journal(manifest, raw_bytes, journal)` (returns normalized journal or raises), `build_files(manifest, raw_bytes, journal)` (dict filename -> bytes), `verify_bundle(directory)` (returns report dict or raises), and `main(argv=None)`.

The parsed manifest must exactly equal strict JSON parsing of raw_bytes; core.normalize then applies its existing contract. Journal exact keys: schema (`nci-reuseledger-journal/v1`), project, manifest_file_sha256, manifest_semantic_sha256, entries, semantic_sha256. Each entry has sequence (1-based exact integer), event (normalized input), upstream_bindings, previous_entry_sha256 (null at first), entry_sha256. Each upstream binding has output_id, output_metadata_sha256 (SHA-256 of core.canon(normalized output)), declared_fixity (copied from output, including null). Entry digest excludes entry_sha256; journal digest excludes semantic_sha256. Every binding, sequence, link and digest is recomputed; validation does not trust copied summaries. These hashes detect inconsistency relative to supplied inputs; an author able to rewrite every file can recompute them. They are not signatures or external witnesses.

## Portable bundle

Exactly eight regular files: manifest.json (original bytes), packet.json (existing compiler output), journal.json, reuse_report.json, reuse_report.md, reuseledger.py, reuse_workflow.py, RECEIPT.json. Scripts are copied from the running component so the bundle can replay offline. Verification compares the source bytes in the bundle with the verifier's currently loaded source files and fully recomputes every generated file. Run a trusted published version of the verifier; a bundle's own code is not an independent trust anchor. No authenticity claim is made. Unexpected files, symlinks and missing files fail bundle-layout verification.

Receipt schema `nci-reuseledger-bundle/v1` contains files: ordered filename/sha256/bytes entries for the seven other files, and manifest_file_sha256, journal_semantic_sha256. It excludes itself from the inventory. JSON generated files use sorted keys, two-space indentation, UTF-8, trailing newline, finite values only.

The core is compiled from its frozen source bytes. Companion source is captured at startup; bundle operations reject disk changes. Use a fresh direct-script invocation of the trusted published source generation. This does not authenticate package origin or attest arbitrary interpreter/preloaded-module state.

Report schema `nci-reuseledger-reuse-report/v1` contains project, manifest_file_sha256, journal_semantic_sha256, basis (`DECLARED_RECORDS_ONLY`), summary and records. Summary: total_records, planned_records, reported_records, credit_unknown_records, no_credit_refs_records, declared_credit_refs_records. Records preserve event fields and upstream bindings. Markdown shows each record's state, dates, purpose, downstream/version, upstream bindings/fixity, and credit state. No new readiness, impact, scientific or clinical score. The existing compiler's metadata-only score stays only in its retained packet.

## Attribution and scope

Original core: Z-KestrelHelix-V5Q2 and Z-MobiusHarbor-Q8V6, merged PR14069. Companion: ZZ–Trellis. This fulfills an additive offline operator workflow; it does not complete competition registration, eligibility review, submission, award or payment.
