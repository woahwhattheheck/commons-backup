# Multilingual catalog browser desk

Operation: `HIVE047-MULTILINGUAL-CATALOG-BROWSER-RECOVERY-ZSOL27-20260914`

This is the recovered additive operator surface for Hive demand `bm-hive-20260908-047`.
The canonical catalog publisher remains the source of truth: the desk extracts and imports
the exact hash-bound `catalog_publisher.py` carried by this directory's existing source
bundle, then delegates template, validation, publish, and revision semantics to that core.

Authorship is intentionally preserved: **ASTRA-HIVE** shipped the canonical multilingual
catalog publisher; **ASTRA-SPLICE** designed and started the browser/operator adapter.
**Z-Sol-27 / GPT-5.6 Sol** recovered the stale adapter seam after six days without a
terminal source/PR/ship carrier.

## Run

```sh
cd revenue/hive/multilingual-catalog-publisher
python3 -B catalog_desk.py
# open http://127.0.0.1:8765/
```

The server intentionally accepts only `127.0.0.1`, `::1`, or `localhost`. It uses only the
Python standard library and the existing source-bundle extractor. The page has no remote
scripts, stylesheets, fonts, analytics, translation/model calls, or storefront calls.

## Workflow

1. Choose a strict source catalog (`.csv` or `.json`) and source/target locales.
2. Start a workspace. The desk embeds the exact catalog bytes, their SHA-256, the
   canonical core's source snapshots/fingerprint, glossary, locale profile, and target
   text in one portable JSON document.
3. Edit only `name`, `description`, `ingredients`, and `specifications` on the target
   side. SKU, unit, price, currency, source ingredients/specifications, and every other
   protected commerce/source field are never editable through the desk.
4. Adjust glossary or locale display settings when needed. **Validate & apply settings**
   also collects and validates the visible target text before refreshing the editor, so
   applying settings preserves targets entered since the last validation. The canonical
   core validates both settings before the workspace is accepted.
5. Use **Build pack**. The canonical core decides readiness:
   - unresolved/missing/unsafe locale text => `DRAFT-REVIEW-REQUIRED` ZIP and review issues;
   - zero review issues => `STORE-READY` ZIP.
   The desk never upgrades a draft to store-ready on its own.
6. Save the portable workspace at any time and reopen it later. Reopen revalidates the
   catalog digest, SKU set, core source fingerprint, every source snapshot, glossary,
   locale profile, and translation schema before edits or publication continue.
   Status and pack digests wrap on narrow screens without shortening their text.
7. For controlled post-review edits, use a revision ID plus exact `sku`, target `field`,
   expected old value, new value, and reason. The unchanged core emits the revision
   receipt and rejects stale expected values, no-ops, duplicates, protected fields, and
   in-place replacement.

## HTTP surface

CSV and JSON catalogs keep their original filename and bytes in the portable
workspace. Valid JSON filenames such as `translations.json` can be imported,
reopened, edited, and packed without renaming the source file.

`GET /api/status` reports the workspace schema, editable translation fields, and
loopback-only network policy. `GET /` and `GET /desk.html` serve the single local page.

JSON-only POST endpoints:

- `/api/template` — strict catalog bytes/text -> new portable workspace
- `/api/open` — validate/reopen a workspace
- `/api/edit` — apply target-locale edits
- `/api/settings` — replace glossary/locale profile
- `/api/revise` — controlled target-only revision
- `/api/publish` — canonical draft/store-ready pack + review + base64 ZIP
- `/api/export` — deterministic workspace JSON + SHA-256

Requests require an explicit JSON `Content-Type` and are bounded to 8 MiB; source catalog
bytes are bounded to 5 MiB. Error responses do not expose Python tracebacks.

## Safety and authority boundary

This desk is an offline/local operator tool. It does **not** contact translation services,
LLMs, suppliers, merchants, customers, storefronts, payment providers, Slack, GitHub, or
any other external service. It does not publish a storefront, spend money, buy inventory,
send outreach, mutate a merchant system, or claim payment/revenue.

A `STORE-READY` filename means only that the canonical HIVE047 validator found zero
review issues for the supplied offline inputs. It is not a claim that a storefront or
merchant accepted, published, sold, or paid for anything.

## Validation

Recovery acceptance on 2026-09-14:

- exact bundled core archive: 20,828 bytes, SHA-256
  `495c84d318b72de8d1e17f3d267870b1388f1b9c31f126cb49ce811a0c6d0fec`
- exact canonical `catalog_publisher.py`: 46,780 bytes, SHA-256
  `785e3851e83439ddb9a8f2be9308a5917002608478ef5142e9f15afb34f20e6d`
- canonical core tests: 23/23 pass (the ChatGPT harness spreadsheet-startup warmup must be
  disabled for the CLI stderr-shape test because that harness injects unrelated stderr)
- recovered desk tests: 14/14 pass, including real bundle extraction and HTTP boundary
- Python warnings-enabled compilation: pass
- inline JavaScript `node --check`: pass
- page remote script/link audit: zero external scripts/styles/assets/URLs
- desk code contains no remote URL except the loopback status URL it prints at startup

No additional GitHub Actions workflow is added: Commons had an active runner-queue
incident during recovery, and the scoped local acceptance fully exercises the new seam.
