# UIOWA-031 — Evidence register and document manifest

**Status: PROPOSED ASSESSMENT TOOLING / NOT A UNIVERSITY FINDING.**
Everything in `packet/` is fiction — synthetic documents written so the register has real bytes to
point at. No University document, account, name or date appears anywhere.

Work order: *"Extend the existing workshare tools with an evidence register covering source ID,
group, assessment area, owner, supplied date, version, document location, excerpt locator, and the
practice it supports. Provide CSV and JSON interchange plus a populated synthetic packet. …
Complete when: Every example document can be found from its register entry; a round trip preserves
IDs, versions, and locators, including documents used by more than one assessment cell."*

## Run it

```bash
cd revenue/uiowa_rfq_18649_evidence_register

python3 make_packet.py                          # rebuild the synthetic packet
python3 evidence_register.py --validate         # every document + excerpt resolves
python3 evidence_register.py --round-trip /tmp/rt
python3 evidence_register.py --show-excerpts    # print what each locator resolves to
python3 evidence_register.py --export-json /tmp/packet.json
python3 -m unittest -v test_evidence_register.py   # 45 tests
```

Both checks exit non-zero on failure. Python 3 standard library only; no network.

## Two tables, because of one requirement

*"Documents used by more than one assessment cell"* decides the shape. A single flat register
repeats a document's location, version and owner on every row that cites it, and the moment one copy
is edited the register disagrees with itself about what was supplied.

- **`manifest.csv`** — one row per document: `source_id`, `title`, `document_location`,
  `document_version`, `owner`, `supplied_date`, `source_type`, `sha256`, `retention_note`.
- **`register.csv`** — one row per evidence item: the full UIOWA-023 field set plus `source_id`,
  `excerpt_locator`, `practice_supported`.

`SRC-SYN-006` (the Joint Controls Memo) is cited by **ESS/SD** and **IAM/SEC**, from two different
sections. One manifest row, two register rows. Its version cannot drift between them because it is
written down once. `SRC-SYN-005` (an interview note) is likewise cited from ESS/SD and ESS/AI.

## Field names extend the existing convention

The register carries every field name from
`uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv` **verbatim** —
`evidence_id`, `observation_id`, `finding_id`, `group`, `area`, `source_type`, `source_ref`,
`captured_at`, `represented_period`, `claim`, `scope_limit`, the five confidence dimensions,
`evidence_state`, `confidence`, `conflict_group`, `universe_definition`, `enumerator_authority`,
`completeness_basis`, `follow_up`. `test_register_keeps_every_023_field_name_unchanged` reads that
file and asserts the list matches, so the convention cannot be forked by accident.

This order's three additions are new columns: `source_id`, `excerpt_locator`, `practice_supported`.
The document-level attributes it names — owner, supplied date, version, document location — live on
the manifest, and a test asserts they are **not** duplicated onto the register.

### Current UIOWA-023 custody fields

The current common 023 register adds `custodian_or_owner` and `content_digest` after `source_ref`.
The native 031 packet materializes those field names from the one authoritative manifest row:
`custodian_or_owner == manifest.owner` and
`content_digest == "sha256:" + manifest.sha256`.
Validation rejects nonblank values that drift from the manifest. This reconciles the current common
register contract without moving document location, version, supplied-date, owner, or digest
authority out of the manifest. GRANITE's six fictional source documents remain byte-identical.

## Locators that actually resolve

A locator nobody can follow is not a locator, so all four forms are resolved against the real bytes:

| Form | Resolves to | Used by |
|---|---|---|
| `lines:8-10` | that line range | interview note (`.txt`) |
| `section:Required checks` | that markdown heading and its body | standards (`.md`) |
| `key:summary` | that path into the JSON | inventory query export (`.json`) |
| `row:CHG-SYN-2044` | the CSV row with that first-column value | deployment log (`.csv`) |

The packet ships documents in four formats on purpose — a locator design that only works on
markdown does not survive a real engagement.

`--show-excerpts` prints the text each entry resolves to, which is the quickest way to see that the
register points where it claims.

## What the validator fails on

`MISSING_DOCUMENT` · `DANGLING_SOURCE_ID` · `UNRESOLVED_LOCATOR` · `BAD_LOCATOR_SYNTAX` ·
`DIGEST_MISMATCH` · `DUPLICATE_ID` · `ORPHAN_DOCUMENT` · `UNKNOWN_FIELD` (warning — the column is
preserved, not dropped).

`DIGEST_MISMATCH` is the one worth naming. The manifest records the sha256 of the bytes as supplied,
so a document edited after registration is **detected** rather than assumed intact — the difference
between citing *a* document and citing *the document that was supplied*.

The locator range check earned its place during development: it caught `lines:17-19` against a
document with 18 lines, in this packet, before anything was committed.

## Round trip

`--round-trip` writes CSV → JSON → CSV and then compares what the order names: every `source_id` and
`evidence_id` still present, every `document_version` and `document_location` unchanged, every
`excerpt_locator` unchanged, and **every multi-cell document still cited by the same set of cells**.
The round-tripped packet is then re-validated against the original documents, so the locators must
still resolve afterwards — not merely still be present as strings.

An unrecognised column survives the round trip rather than being dropped; an unknown field is
somebody's data. It is reported as `UNKNOWN_FIELD` so nothing validates it silently.

## What is real, what is draft

**Real and runnable now:** the schema, the CSV and JSON importer/exporter, document and excerpt
resolution, digest checking, the validator, round-trip verification, the packet, and 45 tests.

**Draft:** the locator grammar is a proposal. It covers text, markdown, JSON and CSV; a real
engagement will also receive PDF and office formats, which need a page/anchor form this does not
have. The packet is fiction.

## University inputs that stay UNKNOWN

- Every real document, its owner, its supplied date and its version. All six here are invented.
- The document locations the University will actually use, and whether sensitive locators must be
  replaced with controlled internal references in deliverables.
- Which practices are in scope, so `practice_supported` currently holds proposed wording.
- The retention and return/destruction terms that `retention_note` should carry.
- Whether a PDF/office locator form is needed, and what it should look like.

## Files

```
evidence_register.py       schema, CSV/JSON interchange, resolution, validation, round trip
make_packet.py             writes the synthetic documents, manifest and register
test_evidence_register.py  45 tests
packet/manifest.csv        6 documents
packet/register.csv        8 evidence entries across 5 assessment cells
packet/docs/               the documents themselves (.md, .txt, .json, .csv)
```
