# Evidence-bound expertise catalog

`commons.expertise-catalog/v1` turns bounded, source-evidenced expertise offers into deterministic machine JSON plus a buyer-facing Markdown review packet. It directly implements the Commons offering-family directive that expertise should be explicit catalog entries rather than hidden inside implementation work.

## What it proves

A compiled offer binds an exact repository commit, path and SHA-256 digest; one or more exact evidence artifacts; an explicit included/excluded scope; exact integer-cent price and currency; canonical UTC validity; a bounded delivery window; and one deterministic offer digest. Input ordering does not affect catalog ordering. Exact duplicate versions collapse; changed duplicates fail closed. Secret-shaped strings, email-shaped PII, path traversal, unpinned commits, unsafe money, malformed timestamps, conflicting evidence IDs, and ambiguous scope all fail closed.

The strongest descriptive state is `CATALOG_REVIEW_PACKET_READY`; it is a packaging/result label only, never an approval, permission, admission, or publication gate. `HOLD` is emitted for an otherwise-valid offer that is not yet active or has expired against the caller-supplied trusted `--as-of` clock.

## Authority ceiling

The compiler never publishes a listing, contacts a buyer, creates a checkout, charges/refunds money, signs/amends a contract, schedules or starts delivery, infers buyer acceptance, or recognizes revenue. Every compiled offer and the catalog envelope set those authority flags to `false`.

## CLI

```bash
python -m revenue.expertise_catalog.cli compile \
  --input offers.json \
  --as-of 2026-09-13T10:00:00Z \
  --out-json expertise-catalog.json \
  --out-md expertise-catalog.md

python -m revenue.expertise_catalog.cli verify \
  --manifest expertise-catalog.json \
  --markdown expertise-catalog.md \
  --expected-catalog-digest <independently-retained-sha256>
```

The verifier always recompiles the normalized offer material and checks the exact schema, derived states, counts, ordering, authority ceilings, and canonical digests. Self-contained hashes establish internal integrity, not external authenticity: when detecting a coherently rewritten catalog matters, pass an independently retained `--expected-catalog-digest`.

The compile input is exactly:

```json
{"offers": [ ... ]}
```

Each source/evidence reference is `repository + full 40-hex commit + repository-relative path + sha256`. The compiler intentionally accepts no floating-point money and no provider/network credentials.

## Validation

```bash
python -m py_compile revenue/expertise_catalog/catalog.py revenue/expertise_catalog/cli.py revenue/expertise_catalog/test_catalog.py
python -m unittest revenue.expertise_catalog.test_catalog -v
python -O -m unittest revenue.expertise_catalog.test_catalog -v
```
