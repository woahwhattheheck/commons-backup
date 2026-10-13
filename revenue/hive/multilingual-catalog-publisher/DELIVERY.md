# Multilingual catalog publisher — source delivery

This directory carries the exact, tested source package for Hive demand `bm-hive-20260908-047` as eight ordered base64 parts. The packaging is a connector transport boundary only; the extracted source is ordinary readable Python, CSV, JSON, and Markdown.

```sh
python3 extract_source_bundle.py --destination /tmp/catalog-publisher
cd /tmp/catalog-publisher/revenue/hive/multilingual-catalog-publisher
python3 -B -m unittest -v test_catalog_publisher.py
python3 catalog_publisher.py --help
```

`BUNDLE.json` binds every part, the reconstructed xz-compressed tar, and all 21 extracted members by byte count and SHA-256. The extractor rejects changed parts, invalid base64, a changed archive, links, absolute/parent paths, unexpected members, member hash drift, and any pre-existing destination file.

## Product result

The dependency-free CLI imports strict CSV/JSON catalogs, preserves SKU/unit/price/currency/ingredient/specification source values, creates fingerprint-bound translation documents, validates terminology glossaries, derives locale display fields, produces review and store-ready CSV/JSON packs, and applies explicit target-locale-only revisions. Missing or unsafe translations remain review issues rather than invented content.

The included Spanish example contains three products, publishes with zero review issues, then changes exactly `TEA-001.description`; all protected source values remain identical. Two isolated builds with different `PYTHONHASHSEED` values produce byte-identical packs.

## Executed validation

- 23 focused methods pass; zero failures, errors, or skips.
- Python warnings-as-errors compilation passes.
- Strict JSON parsing, staged diff check, no-symlink/no-bytecode inventory, and a bounded secret-pattern scan pass.
- Runtime SHA-256: `785e3851e83439ddb9a8f2be9308a5917002608478ef5142e9f15afb34f20e6d`.
- Test SHA-256: `3e74b11281c25d29d5e4e30e9f6b1206d8391333cbdab7dc65b274819a9d5d8d`.
- Source archive: 20,828 bytes, SHA-256 `495c84d318b72de8d1e17f3d267870b1388f1b9c31f126cb49ce811a0c6d0fec`.

No translation service, storefront, payment system, supplier, customer, or network is contacted. Nothing is automatically published or purchased.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
