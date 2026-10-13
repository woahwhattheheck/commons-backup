# Cross-family catalog currentness auditor

This package audits source-currentness for PRODUCT, SERVICE, EXPERTISE, and DATA catalog evidence without becoming a publication or commercial authority.

A catalog entry binds an immutable release commit, repository-relative source path, source-content SHA-256, source-evidence SHA-256, version, catalog digest, and one explicit currentness policy. Provider snapshots bind a complete default-branch path inventory to an exact head, capture time, and provider-evidence digest. Catalog/provider evidence digests are opaque hashes of externally captured evidence; this offline package binds and compares them but does not authenticate GitHub or another provider. Provider authenticity remains an upstream evidence-capture responsibility.

Policies:

- `FOLLOW_DEFAULT_BRANCH`: the catalog asserts that its source should remain identical to the provider default branch. Source drift or disappearance is a HOLD.
- `PINNED_RELEASE`: the immutable catalog release may remain a valid historical release even after default-branch source advances. Source drift becomes `REVIEW_REQUIRED`, never an automatic withdrawal or update.

The overall strongest state is `READY_FOR_HUMAN_CATALOG_CURRENTNESS_REVIEW`. `REVIEW_REQUIRED` means a pinned immutable release has upstream drift requiring a human decision. `HOLD` means the supplied evidence cannot safely support a currentness review.

Fail-closed boundaries include stale/future/incomplete or ambiguous provider snapshots, unsafe commit/digest/path values, schema drift, bool/int aliasing, duplicate/conflicting identity, missing complete-snapshot paths, and secret/PII-shaped metadata.

`verify_receipt()` recompiles from the original evidence plus the same trusted out-of-band `as_of` instant. A caller-recomputed self-hash cannot turn a modified receipt into valid evidence.

## CLI

```bash
python -m revenue.catalog_currentness.cli fixture.json \
  --as-of 2026-09-13T10:15:00Z \
  --out dist/catalog-currentness
```

Exit 0 is review-ready, 4 is a truthful REVIEW_REQUIRED/HOLD result, and 2 is malformed input. The tool never publishes, updates, withdraws, reprices, contacts a buyer, creates checkout, takes payment, transfers an artifact, establishes acceptance, or recognizes revenue.
