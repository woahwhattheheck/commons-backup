# Commons cross-family offering bundle composer

This package composes already-evidenced **product, service, expertise, and data** catalog entries into one deterministic review artifact. It exists between family catalogs and any buyer-specific offer/acceptance system.

It does **not** contact a buyer, send anything, execute a contract, infer buyer acceptance, create checkout/payment state, fulfill work, or recognize revenue. Its strongest output is `READY_FOR_HUMAN_BUNDLE_REVIEW`.

## Contract

Each input entry must bind:

- one family, stable entry id and version;
- immutable repository commit, path and content SHA-256;
- a content-addressed evidence receipt plus exact UTC verification time and bounded max age;
- one or more deliverables, each with explicit acceptance criteria;
- exclusions, dependencies and conflicts;
- either exact integer minor-unit fixed pricing or `QUOTE_REQUIRED`;
- an explicit authority map whose external-action fields are all `false`.

The compiler fails closed (`HOLD`) for unknown schema fields, mutable refs, invalid source paths/digests, stale/future evidence, missing/cyclic dependencies, conflicts, duplicate identities, incomplete deliverable→acceptance coverage, mixed fixed currencies, ambiguous/invalid money, secret/PII-shaped metadata, or any external authority.

`trusted_as_of` is supplied outside the manifest. Authority-driving freshness cannot be rewound by replaying an old input document. Timestamps are exact `YYYY-MM-DDTHH:MM:SSZ`; timezone-less and offset-bearing variants are rejected rather than host-normalized.

## Determinism and verification

Receipts contain:

- exact manifest digest;
- sorted family, entry and source commitments;
- deterministic bundle pricing (`FIXED` only when every component is fixed in one currency, otherwise `QUOTE_REQUIRED`);
- explicit HOLD reasons;
- hard-false external authority map;
- content-addressed receipt digest.

`verify` recompiles from the original manifest plus the same trusted time and requires byte-equivalent canonical JSON. Receipt or manifest tampering therefore fails verification.

## CLI

```bash
python revenue/offering_bundle_composer/cli.py compile manifest.json \
  --as-of 2026-09-13T10:00:00Z \
  --json-out bundle-receipt.json \
  --markdown-out bundle-receipt.md

python revenue/offering_bundle_composer/cli.py verify manifest.json bundle-receipt.json \
  --as-of 2026-09-13T10:00:00Z
```

Exit codes: `0` ready/verified, `3` compiled HOLD, `4` verification failure.

## Validation

```bash
python -m py_compile revenue/offering_bundle_composer/*.py \
  revenue/offering_bundle_composer/tests/test_composer.py
python -m unittest discover -s revenue/offering_bundle_composer/tests -v
python -O -m unittest discover -s revenue/offering_bundle_composer/tests -v
python revenue/offering_bundle_composer/acceptance.py
python -O revenue/offering_bundle_composer/acceptance.py
```

The deterministic acceptance corpus contains 160 bundles: 120 review-ready controls and 40 deliberate HOLDs, five each for stale evidence, future evidence, missing dependency, dependency cycle, explicit conflict, mixed currency, mutable source ref, and sensitive metadata.
