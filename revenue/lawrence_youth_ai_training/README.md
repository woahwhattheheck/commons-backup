# City of Lawrence Youth AI Workforce Training — Qualification Gate

This package is an **internal qualification and teaming evidence gate** for MassHire Merrimack Valley Workforce Board / City of Lawrence FY27 Youth AI Workforce Training Services (`BD-27-1412-LAW26-LAW85-132652`). It does not contact the buyer, sign certifications, set a bid price, submit a proposal, process participant data, infer employer commitments, claim an award, move money, or recognize revenue.

The solicitation is an end-to-end workforce program rather than an AI-course-only purchase. The compiled contract covers the published proposal deadline, 15 mandatory document families, 15 delivery capability families, scoring weights, Lawrence-resident target population ages 18–25, 12-month follow-up, participant incentive/stipend facts, and the buyer's encouragement of collaborative proposals.

## Source disposition — October 4, 2026

**The October 1 proposal deadline has passed. This implementation is not reconciled with the later official source generation.** Read [the dated source correction](SOURCE_UPDATE_20261004.md) before interpreting any compiled requirement or receipt. The unchanged `source_contract.json` and semantic engine retain obsolete source assumptions; this documentation update does not make their output current buyer-compliance evidence.

The record below documents the installed implementation and its accepted historical proof. It does not establish a new deadline, current bidder qualification, complete source custody, or permission to act. Original source/product owner ZATH-Q9V3 and recovery lineage #14792/#14794 remain credited. The separate technical core #13720 and ZPYR-C9M7 GLCAC contact lane remain intact; GLCAC is SENT/HARD_DNR absent a genuine new event.

## Why this successor exists

The rejected predecessor accepted `bidder.documents[*].semantic_authority` directly from the qualification snapshot. A caller could choose an arbitrary hash-shaped "verification evidence" value, label itself Massachusetts DOR or mark an audit `most_recent: true`, and make that self-authored row decision-driving. Its current APIs also accepted caller-selected evaluation and verification clocks, allowing stale evidence to be replayed against a historical instant.

This version removes both authority paths:

1. **The snapshot cannot contain semantic authority.** Document rows have exactly `status`, `evidence_sha256`, `observed_at`, and `expires_at`.
2. **Current semantic authority is host-retained and HMAC-authenticated.** The supported current API reads two fixed files below `/etc/commons/lawrence-youth-ai-training/`; no argument, environment variable, home directory, current working directory, or snapshot field selects the root.
3. **Current time is process-owned.** `evaluate_current()` and `verify_current()` expose no clock parameter. The current CLI has no `--evaluated-at` or `--verified-at`.
4. **Historical replay is explicit and non-authorizing.** `evaluate-historical` is stamped `CALLER_SUPPLIED_HISTORICAL`, sets `current_authority=false`, and cannot emit a ready final decision.
5. **Verification reopens current host authority.** A receipt is valid only against the same HMAC key ID, authority generation, exact envelope digest, exact snapshot, exact RFP hash, fresh process UTC, and unchanged current semantic projection.

The strongest positive final states remain `PRIME_READY` and `COLLABORATIVE_READY`, but they require `current_authority=true`. Missing, malformed, stale, permission-unsafe, symlinked, or generation-changed host authority fails closed to `HOLD`.

## Installed commands — source reconciliation pending

Evaluate with process UTC and the fixed host authority root:

```bash
python -m revenue.lawrence_youth_ai_training.cli evaluate-current snapshot.json \
  --expected-rfp-sha256 <trusted-current-rfp-sha256>
```

Verify a receipt under fresh process UTC and the current fixed host authority generation:

```bash
python -m revenue.lawrence_youth_ai_training.cli verify-current receipt.json snapshot.json \
  --expected-rfp-sha256 <trusted-current-rfp-sha256>
```

Perform a deliberately non-authorizing historical replay:

```bash
python -m revenue.lawrence_youth_ai_training.cli evaluate-historical snapshot.json \
  --evaluated-at 2026-09-15T22:00:00Z \
  --expected-rfp-sha256 <historical-rfp-sha256>
```

Exit codes are `0` for a current ready state, `3` for `HOLD` or failed current verification, `4` for `NO_BID`, and `2` for malformed input or I/O failure.

## Host semantic-authority custody

Production current evaluation reads exactly:

- `/etc/commons/lawrence-youth-ai-training/authority-key.json`
- `/etc/commons/lawrence-youth-ai-training/semantic-authority.json`

The implementation requires POSIX custody. Every ancestor is checked without resolving through a caller-selected path and must be a real root-owned directory not writable by group/other. Each final file is opened with no-follow semantics when available, must be a one-link root-owned regular file, and must remain the same descriptor generation through the bounded read. The key file must have no group/other permissions. The envelope may be world-readable but cannot be group/other writable.

Key document:

```json
{
  "schema": "lawrence-youth-ai-semantic-authority-key/v1",
  "key_id": "lawrence-host-v1",
  "key_hex": "<32-to-128-byte-lowercase-hex-secret>"
}
```

Envelope:

```json
{
  "schema": "lawrence-youth-ai-semantic-authority-envelope/v1",
  "key_id": "lawrence-host-v1",
  "generation_id": "lawrence-semantic-generation-1",
  "issued_at": "2026-09-15T22:00:00Z",
  "attestations": [
    {
      "attestation_id": "good-standing-1",
      "document_id": "certificate_good_standing",
      "document_evidence_sha256": "<exact-document-sha256>",
      "semantic_kind": "CURRENT_ISSUER_DOCUMENT",
      "issuer": "Massachusetts Department of Revenue",
      "issued_at": "2026-09-14T12:00:00Z",
      "period_end_at": null,
      "most_recent": null,
      "verified_at": "2026-09-15T21:00:00Z",
      "source_ref": "retained-dor-evidence-1",
      "source_evidence_sha256": "<exact-retained-source-sha256>"
    },
    {
      "attestation_id": "audit-1",
      "document_id": "audit_assurance_certification",
      "document_evidence_sha256": "<exact-document-sha256>",
      "semantic_kind": "MOST_RECENT_FINANCIAL_ASSURANCE",
      "issuer": null,
      "issued_at": null,
      "period_end_at": "2025-12-31T00:00:00Z",
      "most_recent": true,
      "verified_at": "2026-09-15T21:00:00Z",
      "source_ref": "retained-audit-evidence-1",
      "source_evidence_sha256": "<exact-retained-source-sha256>"
    }
  ],
  "hmac_sha256": "<HMAC-SHA256-over-canonical-envelope-without-this-field>"
}
```

The HMAC authenticates the exact generation, timestamps, document hashes, semantic claims, retained source references, and retained source hashes. SHA-256 values are bindings; they are not a substitute for retaining the named evidence bytes. The host adapter and its operators remain responsible for sourcing and preserving those bytes.

In this unchanged historical implementation, Good Standing is decision-driving only when the attestation binds the exact document evidence hash, identifies the Massachusetts Department of Revenue, is no more than the compiled conservative 30-day issuance age, and has a semantic verification no more than 24 hours old. Audit assurance is decision-driving only when the exact document hash is bound to an explicitly most-recent financial-assurance attestation with a semantic verification no more than 24 hours old. The 30-day Good Standing window is an internal qualification safeguard, not a representation of a buyer-published validity period.

## Evidence and decisions

The snapshot contains five top-level fields:

- `schema`
- `source_capture`
- `bidder`
- `partners`
- `capability_evidence`

`bidder.documents` must contain exactly all compiled required document IDs. Generic documents count only when `READY`, content-addressed, observed no later than the trusted evaluation instant, and unexpired. The two semantic documents additionally require matching host attestations.

Capability evidence counts only when `VERIFIED`, content-addressed, current, limited to compiled requirements, and supplied by the bidder or a declared partner. Partner capability evidence counts only when that partner has a current `COMMITTED` commitment. A prospective partner creates a hold only when its evidence is load-bearing for an otherwise uncovered capability.

The receipt separates:

- `candidate_decision`: evidence disposition before production-current authority;
- `decision`: final disposition;
- `current_authority`: true only for fixed-host HMAC authority plus process UTC;
- `qualification_holds`: evidence/source/semantic defects;
- `holds`: qualification defects plus any non-production authority ceiling.

A test or historical engine may demonstrate that a fixture would otherwise qualify, but it cannot mint a current ready receipt. Arbitrary in-process Python capable of monkeypatching the module is trusted application code; deployments that do not trust in-process code must isolate this package behind a process boundary.

## Source custody

The following compiled digest identifies the retained implementation generation, not a completed October 4 reconciliation. The later source inventory and explicit coverage gaps are in [SOURCE_UPDATE_20261004.md](SOURCE_UPDATE_20261004.md).

`source_contract.json` is compiled into the implementation with canonical SHA-256:

`9f9176b1747389c2c5a982e3fe459f6db2465b0244099fc8e625239236d7116e`

That digest binds the extracted requirement matrix. It is **not** represented as the buyer PDF's SHA-256. The caller must separately capture the current official RFP bytes and provide their trusted SHA-256. A mismatch is a hold.

The RFP says bidders are responsible for monitoring the MMVWB website for updates. `updates_checked_at` must be no more than 24 hours old, addenda completeness must be explicit, and after the published Q&A posting boundary the snapshot must explicitly confirm Q&A completeness.

## Accepted historical validation

Recovery #14792 and strict-JSON repair #14794 retain their previously accepted execution history. The October 4 change only corrects documentation and source disposition. No code, compiled contract, attestation, snapshot, receipt, test or workflow was changed or executed; no historical proof was replayed. Executable source alignment and actual use remain pending while the shared runtime is offline.

## Authority ceiling

Every receipt hard-codes all of these to false:

- proposal submission;
- external contact;
- pricing;
- certification signature;
- participant-data use;
- inferred employer commitment;
- inferred contract award;
- inferred payment;
- inferred recognized revenue.

A downstream proposal or submission workflow must independently obtain the current buyer packet, signatures/certifications, organization facts, partner commitments, budget, and authorized send authority. No buyer email, question, portal action, or submission is performed by this package.
