# Repository Estate Rationalizer

Read-only decision support for reducing the private-repository / private-CI cost surface without turning repository names or inactivity into publication authority.

## What it does

`rationalizer.py` consumes two explicit inputs:

1. a canonical repository snapshot (`commons.repo-estate.snapshot/v1`), and
2. explicit per-repository owner/evidence rows (`commons.repo-estate.evidence/v1`).

It emits one deterministic packet plus Markdown with one state per repo:

- `PUBLIC_ALREADY`
- `KEEP_PRIVATE`
- `PUBLICATION_REVIEW`
- `ARCHIVE_REVIEW`
- `HOLD`

A positive `PUBLICATION_REVIEW` is deliberately expensive: it requires exact current branch identity, a source-trusted owner-authority reference, a fresh exact-commit secret scan, public-release content classification, clear legal/IP review, and fresh open-work/dependency observations. `ARCHIVE_REVIEW` additionally requires a source-trusted archive-authority reference and no open PR/issue/claim or active consumer. Caller-supplied `owner_authorized` / `archive_authorized` booleans are assertions, not trust roots. The shipped generation has no production authority refs source-trusted by default, so private publication/archive requests remain `HOLD` until an exact authority reference is deliberately bound by a reviewed source generation. The tool never mutates GitHub.

`PUBLICATION_REVIEW` / `ARCHIVE_REVIEW` mean “evidence is sufficient for a separate human/operator review,” not “safe to execute automatically.”

## Current estate snapshot

`fixtures/account_snapshot_20260918.json` is a privacy-safe snapshot made from the authenticated GitHub repository inventory on 2026-09-18. It contains repository name, visibility, archive bit, default branch and the exact default-branch SHA for the 15 private repositories. It contains no credentials or repository contents.

Snapshot count at capture: **43 repositories / 15 private / 28 public**.

The checked-in `empty_evidence.json` intentionally supplies no publication or archive authority. Therefore every current private repo evaluates to `HOLD`; the fixture is an estate/cost-surface census, **not** a claim that any private repository is safe to publish.

## CLI

```bash
python tools/repo_estate_rationalizer/rationalizer.py compile \
  --snapshot tools/repo_estate_rationalizer/fixtures/account_snapshot_20260918.json \
  --evidence tools/repo_estate_rationalizer/fixtures/empty_evidence.json \
  --out /tmp/repo-estate.json \
  --markdown /tmp/repo-estate.md

python tools/repo_estate_rationalizer/rationalizer.py verify \
  --snapshot tools/repo_estate_rationalizer/fixtures/account_snapshot_20260918.json \
  --evidence tools/repo_estate_rationalizer/fixtures/empty_evidence.json \
  --packet /tmp/repo-estate.json \
  --markdown /tmp/repo-estate.md
```

Production compile and verify use process-owned current UTC. Historical/frozen-time compilation remains internal to tests.
The production generation also owns a frozen validator/hash/time dependency graph, so post-import rebinding of schema helpers or policy constants cannot widen freshness, shape, or authority admission.

## Evidence shape

Each evidence row binds one exact repository generation and carries:

- explicit intent: `keep_private`, `review_public`, or `review_archive`;
- owner authorization + retained reference;
- exact-commit secret-scan result, time and retained reference;
- content classification and legal/IP review references;
- fresh open PR / issue / active-claim census;
- fresh consumer/replacement relation census;
- explicit archive authority when archive review is requested.

Missing, stale, conflicting, generation-mismatched, or merely caller-asserted authority produces `HOLD`. `keep_private` is intentionally conservative and does not require publication authority. Evidence rows are canonicalized by repository identity before the source digest is computed, so semantically identical row ordering cannot change the packet receipt.

## Authority ceiling

This package cannot change visibility, archive/delete a repository, move refs, alter Actions, spend money, or certify that publication is legally/safely complete. The emitted authority ceiling is captured from a source-literal immutable generation rather than the exported mutable compatibility dictionary. It reports evidence state only.

The dedicated test workflow is retained as `ci/workflow-recipes/repo-estate-rationalizer.yml` rather than an active `.github/workflows` slot. This avoids raising the Commons active-workflow ceiling while preserving an exact reusable recipe for normal and real `python -O` proof.

## Public CLI refusal boundary

The CLI normalizes malformed public JSON shapes and local filesystem/encoding failures into a typed `REFUSED:` result with exit code 2. Those public-boundary failures must not escape as Python tracebacks. The underlying descriptor-based readers/writers keep their conservative no-overwrite and partial-file retention behavior; this normalization does not widen repository publication, archive, delete, branch, Actions, billing, or spend authority.
