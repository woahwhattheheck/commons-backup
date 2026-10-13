# Commons Data License & Sample Pack Desk

Evidence-only tooling for the **Data** offering family described in `revenue/OFFERING_FAMILIES.md`.

It turns recorded provenance, rights evidence, redaction evidence, schema/sample rows and a proposed offer into either:

- `READY_FOR_HUMAN_LICENSE_REVIEW`, with a deterministic sample-pack ZIP and content-addressed receipt; or
- `HOLD`, with fail-closed reason codes and **no sample pack**.

A READY result is deliberately **not** an executed license, transfer authorization, publication authorization, payment authorization, buyer acceptance, or recognized revenue.

## Input contract

`commons-data-license/v1` requires each dataset to bind:

- stable dataset ID + version;
- source SHA-256 + provenance SHA-256;
- recorded rights basis (`OWNED`, `LICENSED_FOR_REDISTRIBUTION`, or `PUBLIC_DOMAIN`);
- license identifier + license-evidence SHA-256;
- explicitly permitted grant types and `transfer_allowed=true`;
- `PUBLIC` or `REDACTED` sensitive-data class;
- verified redaction evidence when data is `REDACTED`;
- bounded schema + synthetic/redacted sample rows;
- exact integer-cent USD offer, grant, term, and expiry.

Unknown/restricted rights, ambiguous transfer rights, missing redaction evidence, PII/secret-shaped fields or values, out-of-schema sample fields, expired offers, or grants outside recorded rights all HOLD.

The evidence digests prove **binding to supplied evidence**, not that a legal conclusion is correct. Human/legal review remains the authority boundary.

Evaluation/verification time is an explicit external `trusted_at` input. Receipts do not get to choose their own clock; verifying later with a post-expiry trusted time fails rather than replaying an old READY state.

## Deterministic pack

Each READY dataset produces `<dataset_id>.zip` with fixed metadata and sorted entries:

- `manifest.json`
- `sample.jsonl`
- `OFFER.md`

The receipt stores the exact sample JSONL digest and ZIP digest. `verify_catalog()` re-evaluates the source document and requires byte-identical packs.

## CLI

```bash
python -m revenue.data_license_desk.cli build catalog.json \
  --receipt out/receipt.json --pack-dir out/packs --at 2026-09-13T10:00:00Z

python -m revenue.data_license_desk.cli verify catalog.json \
  --receipt out/receipt.json --pack-dir out/packs --at 2026-09-13T10:00:00Z
```

Exit codes: `0` READY/verified, `3` truthful HOLD from `build`, `2` malformed/unreadable/failed verification.

Inputs must be ordinary non-symlink files. Outputs are atomically replaced and symlink destinations are refused.

## Validation

```bash
python -m py_compile revenue/data_license_desk/*.py
python -m unittest -v revenue.data_license_desk.test_desk
python -O -m unittest -v revenue.data_license_desk.test_desk
```

Tests cover deterministic pack bytes, rights/redaction/grant/expiry fences, PII/secret guards, exact integer-cent boundaries, duplicate identities, receipt/pack mutation, missing/extra packs, CLI round-trip, and symlink refusal.

## Authority boundary

This package performs no customer contact, provider/API call, dataset publication, file upload, license execution, signature, checkout, payment, transfer, fulfillment, or revenue recognition. It contains synthetic fixtures only and never converts `UNKNOWN` rights into permission.
