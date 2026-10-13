# Commons Product Catalog Bridge

This package implements the **Products** expansion named in `revenue/OFFERING_FAMILIES.md`: bind product-capable repository artifacts to explicit catalog listings without silently upgrading evidence into a sale.

The compiler consumes a strict JSON inventory of immutable repository artifacts, PRODUCT-family catalog listings, and digest-bound verification evidence. It emits a deterministic JSON receipt plus CSV inventory and human Markdown review packet.

## Release state

The strongest state is `READY_FOR_HUMAN_CATALOG_PUBLICATION`. That means only that the supplied inventory is internally complete enough for a human to decide whether to publish/update catalog material. It does **not** publish a listing, create checkout, contact a buyer, sign a contract, take payment, transfer an artifact, deploy software, prove buyer acceptance, or recognize revenue.

A receipt is `HOLD` when catalog coverage or evidence is incomplete. The gate fails closed on:

- missing or cross-mismatched listing coverage;
- mutable/ambiguous source identity (only exact 40-hex commits are accepted);
- content digest mismatch between artifact and verification evidence;
- future or >30-day-old verification evidence;
- failed verification or no current PASS evidence;
- unknown/unverified license state or unsupported transfer boundary;
- duplicate/conflicting repository-path artifact identity;
- secret/API-key/private-key/e-mail shaped metadata;
- unknown fields at every authority-bearing schema boundary.

`verify_receipt()` does not trust the receipt's self-hash. It recompiles from the original inventory and the same trusted out-of-band `as_of` instant, then requires canonical byte-equivalent semantics.

## Input schema

Top level: `schema`, `artifacts`, `listings`, `evidence` only. The schema value is `commons-product-catalog-bridge-input/v1`.

Each artifact binds:

`artifactId`, `repository`, `commitSha`, `sourcePath`, `contentSha256`, `version`, `licenseId`, `licenseEvidenceSha256`, `transferBoundary`, `catalogListingId`.

Each listing binds:

`listingId`, `title`, `family=PRODUCT`, `status`, `version`, `artifactIds`.

Each evidence record binds:

`evidenceId`, `artifactId`, `contentSha256`, `verificationKind`, `outcome`, `capturedAt`, `sourceSha256`.

All authority-driving timestamps require explicit `Z`; host-local parsing is rejected.

## CLI

```bash
python -m revenue.product_catalog_bridge.cli inventory.json \
  --as-of 2026-09-13T10:00:00Z \
  --out dist/product-catalog-bridge
```

Exit 0 = ready for human publication review; exit 4 = well-formed inventory on HOLD; malformed/fail-closed input exits 2.

## Tests

```bash
PYTHONPATH=. python -m unittest -v tests.test_product_catalog_bridge
PYTHONPATH=. python -O -m unittest -v tests.test_product_catalog_bridge
```

The fixtures are synthetic. No buyer/customer data or credentials are required.
