# Exact RFP / Addenda Delta Desk

A buyer packet is not static. Base solicitations gain addenda, Q&A, revised pricing
forms, replacement exhibits, deadline changes, and corrected mandatory requirements.
Reusing an old compliance matrix after one of those changes is a commercial failure
mode.

This package is an **offline evidence product** that compares two supplied exact
buyer-source generations and produces a deterministic owner-review delta. It answers:

- which controlling documents were added, removed, or changed;
- which requirement identities were added, removed, changed, or unchanged;
- whether same-ID or replacement-document changes have exact supersession lineage;
- which prior human review decisions remain attached to identical live requirements
  and inside the fixed review-freshness window; and
- which current rows must be reviewed again before later bid/submission work continues.

It does not prove that the live buyer portal universe is complete. `OFFICIAL`,
`complete`, document hashes, and extracted requirement rows are supplied evidence;
upstream source-capture authority remains responsible for proving live provenance.
The desk never contacts a buyer, acknowledges an addendum, signs a form, submits a
bid, commits price/staffing, moves money, or recognizes revenue.

## Retaining source snapshots

Before versioning captured website HTML, remove credential-bearing website
configuration, including API-key values in hidden inputs and embedded scripts.
Retain the procurement content, source URLs, capture time and reading scope. Do not
copy credential values into the source manifest, reports, commit text or logs.

Record the original capture's byte count and SHA-256 separately from the published
sanitized artifact's byte count and SHA-256. The manifest must identify the
retention transform, affected field and replacement marker, and the number of
replacements. A sanitized HTML snapshot is a derivative; document captures that
were not transformed keep their exact source hashes. Check the outgoing retained
HTML for remaining credential values and verify its published digest before it
enters Git.

The San Leandro packet uses `original_capture` for the original HTML digest and
`retention_transform` for the `GoogleMapsKey` redaction. Its top-level artifact hash
and byte count identify the sanitized retained file.

## Schemas and lineage

`commons-rfp-source-generation/v1` carries one opportunity/generation, its exact
source inventory, and normalized requirement identities. Requirements may bind only
to `OFFICIAL` documents. `SECONDARY` sources may be retained as discovery metadata
but cannot control a requirement.

A controlling document change reusing the same `document_id` must carry the exact
prior document SHA-256 in `supersedes_sha256`. A buyer may publish a replacement
under a new document ID only when the new row names the exact SHA-256 of one and only
one removed predecessor. One-to-many successors and digest-ambiguous predecessors
are `CONFLICT`. A requirement change reusing the same `requirement_id` must carry the
exact prior statement SHA-256 in `supersedes_sha256`; quiet rewrites are `CONFLICT`.

Removed requirements remain in historical delta evidence but are not current review
obligations. Their removal is still a material packet change, so the generation is
not labeled `NO_MATERIAL_CHANGE` merely because the removed row no longer needs a
current owner decision.

`commons-rfp-review-decision/v1` is optional prior review evidence. It binds the old
opportunity, old source generation, exact normalized requirement identity, decision
ID/time, and evidence digest. It is never inferred from prose.

## States

- `NO_MATERIAL_CHANGE`: supplied source semantics are materially unchanged and every
  non-informational live requirement has valid carried review coverage from a
  complete prior generation inside the fixed review-freshness window.
- `REVIEW_REQUIRED`: material packet/requirement movement occurred or current
  non-informational requirements lack exact current review coverage.
- `SOURCE_REFRESH_REQUIRED`: the new supplied source set is declared incomplete or
  its capture is older than the fixed seven-day evidence ceiling.
- `CONFLICT`: exact supersession/source continuity is broken.
- `HOLD`: fail-closed analysis that cannot establish current authority, including
  every caller-supplied historical clock.

An incomplete-old → complete-new transition is material and old review coverage
cannot carry across it. Review decisions older than seven days at evaluation are
listed in `stale_review_decisions` and become `REVIEW_REQUIRED`.

A `NO_MATERIAL_CHANGE` receipt is evidence-only and relative to the supplied source
generation. It is never submission authority.

## Clock authority

Current evaluation is mechanically process-clock-owned.

- `compile_current(...)` accepts no time argument and samples process UTC internally.
- `compile_historical(..., trusted_as_of=...)` is deterministic analysis only; every
  result is stamped `CALLER_SUPPLIED_HISTORICAL` and forced to `HOLD`.
- No production callable accepts both caller-selected time and a current-authority
  clock label. The explicit-time semantic primitive returns only a non-authoritative
  projection: no schema, evaluation time, clock authority, or receipt digest.
- `verify_report(...)` accepts no verifier-time argument. It reacquires process UTC,
  accepts only `PROCESS_UTC` receipts no more than five minutes old, verifies the
  digest, recomputes all retained-time semantic fields, then recomputes current
  disposition/review/staleness/conflict fields at process time.

Deterministic current-clock tests patch the process-clock seam; they do not pass a
caller time into an authority function.

## CLI

```bash
python -m revenue.rfp_addenda_delta.cli compile \
  --old old-generation.json \
  --new new-generation.json \
  --decisions prior-decisions.json \
  --out-json delta-receipt.json \
  --out-md delta-report.md

python -m revenue.rfp_addenda_delta.cli verify \
  --old old-generation.json \
  --new new-generation.json \
  --decisions prior-decisions.json \
  --report delta-receipt.json
```

The current-work CLI owns process UTC. It accepts bounded regular files, preflights
both output paths before publishing either artifact, and writes create-exclusively.
Existing paths, duplicate output paths, and final-component symlinks are refused. A
late filesystem race can still yield a truthful partial publication; the CLI never
pathname-deletes a created artifact during rollback.

Exit codes for `compile`: 0 only for `NO_MATERIAL_CHANGE`, 3 for a truthful non-green
review state, 2 for malformed/custody failure. `verify` returns 0 only for an exact,
current, process-clock-authoritative receipt.

## Validation

Focused hostile coverage exercises addenda/form additions, exact source/requirement
supersession, deadline/mandatory/route/cure drift, source-set shrink,
incomplete-old→complete-new transitions, stale/future/cross-generation decisions,
caller-clock downgrade, stale current receipts, direct-submodule current-authority
mint attempts, duplicate IDs/JSON keys, bool/int aliases, noncanonical timestamps,
URL credential injection, order determinism, receipt tamper/reseal,
create-exclusive output, and final-component symlink refusal.

Synthetic acceptance:

```bash
python -m revenue.rfp_addenda_delta.synthetic_acceptance
```

Expected semantics: unchanged reviewed generation => `NO_MATERIAL_CHANGE`; a newly
added controlling addendum/mandatory row => `REVIEW_REQUIRED`; a superseded changed
mandatory row => `REVIEW_REQUIRED`.

## Commercial use

This can support a bounded **RFP/Addenda Delta Review** service: ingest two supplied
buyer-controlled packet generations, publish an evidence-bound change report, and
hand the client exact live rows requiring renewed technical/commercial/legal/security
review. Price, contract scope, source-capture authority, and buyer/client authority
remain owner decisions; this repository does not claim a sale merely because the
product exists.

## Real source application

[San Leandro CAD/RMS — October 3, 2026](packets/san_leandro_20261003/README.md)
retains official documents and a sanitized buyer-page snapshot, and applies this existing CLI to the original
baseline and the two subsequent addenda. It records exact Attachment D replacement
lineage, revised deadlines and source contradictions while keeping both partial
generations incomplete and preserving original pursuit ownership.
