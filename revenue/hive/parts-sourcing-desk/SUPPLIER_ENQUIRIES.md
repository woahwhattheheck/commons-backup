# Supplier enquiry exports for the existing Parts Sourcing Desk

This is an additive customer-workflow component for `bm-hive-20260908-044`.
It does not replace SPRUCE's desk or ROWAN's catalog-file importer.

## What it does

`build_from_desk_request()` takes the exact saved request returned by
`Desk.request(id)` / `GET /api/requests/{id}` and prepares one **unsent**
enquiry per selected supplier. Existing option snapshots, source dates,
source notes, serial restrictions and fit-review states remain visible.

The export asks suppliers to clarify missing price, shipping, stock quantity,
lead time, tax and quote validity. It flags future-dated or aged source entries,
contradictory stock records, shortages and stale desk reviews. The default
seven-day age is a configurable operator reminder policy, not a manufacturer
rule or a guarantee that a younger quote is current.

A compatible saved review is retained as compatible. An incompatible or stale
saved review is retained explicitly. The exporter does not decide compatibility,
refresh an option, amend a catalog, place an order, contact a supplier, or write
to the desk database. Existing draft/placed records produce a prominent
do-not-duplicate-order note; cancelled history remains in the desk.

Multiple entries for the same request are **alternatives**, never additive
purchase lines. Unit-price multiplication uses `Decimal`. Different currencies
remain separate. Shipping's charging basis and taxes are not inferred, so no
invented all-in purchase total is generated.

## Download from the browser desk

Open the existing Parts Desk and select a saved workshop job. Attach the options
you want to ask about, then check **Include in supplier enquiry pack** on each
chosen option. The **Supplier enquiry drafts** section shows the selection count,
as-of date and source-age reminder in days. **Download selected enquiries** uses
the same saved-request exporter described below and downloads a ZIP containing
the individual text drafts, internal HTML/JSON and manifest.

Extract the ZIP and review each supplier's own `.txt` file before sharing. The
combined HTML and JSON contain the selected suppliers' alternatives and remain
an internal working pack. The export preserves saved quotes and fit findings,
including stale-source and existing-order notices; it does not refresh them or
write any activity to the desk. An empty browser selection asks you to choose an
option, and invalid server input is returned as a visible error instead of a ZIP.

Selections survive a reload of the same saved job within the page; switching
jobs clears them. The chosen date and reminder remain visible for the next
download. No terminal command or saved-request JSON transfer is needed.

## Run in an existing cloud workspace

Python 3.11+; no third-party dependencies, server or new infrastructure.

From this directory, with a saved JSON response from the existing desk:

```sh
python3 -S supplier_enquiries.py \
  --desk-request request.json \
  --option-id SAVED_OPTION_ID \
  --as-of 2026-09-08 \
  --max-age-days 7 \
  --out /tmp/job-enquiries-001
```

Repeat `--option-id` to include multiple saved options. Omit it to include
all saved options for that one request. No network fetch is performed.
The output directory must be new: an existing pack is never overwritten.

The pack contains individual supplier `.txt` drafts, an internal printable
`index.html`, `enquiries.json` and a SHA-256/size manifest. **Share only the
intended supplier's individual draft after reviewing it.** The combined JSON
and HTML contain all included suppliers' options and are an internal working
pack. Request notes and selected source notes are copied as supplied; review
them before any external use. Nothing is sent by this component.

## Python integration

The canonical desk can pass its already-loaded request without a new API:

```python
from datetime import date
from pathlib import Path
from supplier_enquiries import build_from_desk_request, write_pack

snapshot = desk.request(request_id)
pack = build_from_desk_request(
    snapshot,
    option_ids=[saved_option_id],
    as_of=date(2026, 9, 8),
    max_age_days=7,
)
write_pack(pack, Path("/tmp/job-enquiries-001"))
```

Only chosen option snapshots enter the drafts; unselected supplier quote rows,
full event history and other order documents are not copied into them. The
original saved-request hash and revision bind the input without exposing that
whole record to each supplier. A later catalog update is not silently used
in place of the saved quote. The desk's `catalog_changed`, `request_changed`
and `effective_fit` values are consumed unchanged.

For a pre-save workflow, `build_enquiries(request, rows)` also accepts selected
canonical catalog rows plus this small adapter input:

```json
{
  "id": "job-42",
  "quantity": 3,
  "job_ref": "Shop reference",
  "make": "Supplied make",
  "model": "Supplied model",
  "serial": "",
  "requested_part": "Supplied part",
  "description": "Supplied repair description",
  "notes": ""
}
```

Its CLI equivalent uses `--request adapter-request.json --catalog catalog.json`.
Catalog input may be a row list or the canonical `{"items":[...]}` payload.
This is not a second CSV importer and does not normalize the desk's stored data.

## Scope and measured integration

The new files do not modify `parts_desk.py`, `index.html`, the database schema,
core tests, or the catalog importer.

The actual core used for the new composition tests is:

- Repository: `woahwhattheheck/commons`
- Commit: `687d5eafca97ca04acf36fc9bfb366f2e1807622`
- Path: `revenue/hive/parts-sourcing-desk/parts_desk.py`
- Git blob: `1369aae88363236e49d9ca2e429517cb79739d58`
- SHA-256: `7b63d715ed589dd2c7a5125a040bfb1d92deb77ebfb712d18a8e28e104882e19`
- Size: 30,812 bytes

The full retrieved source matched both hashes. No substitute desk or mock store
was used. The original desk's accepted test panel was not rerun.

```sh
# In the canonical product directory:
python3 -S -B -m unittest -v \
  test_supplier_enquiries test_supplier_enquiries_desk
```

For this standalone delivery bundle, first point the test at its reference copy:

```sh
export PARTS_DESK_SOURCE_DIR="$PWD/reference"
export PARTS_DESK_EXPECTED_SHA256=7b63d715ed589dd2c7a5125a040bfb1d92deb77ebfb712d18a8e28e104882e19
cd revenue/hive/parts-sourcing-desk
python3 -S -B -m unittest -v \
  test_supplier_enquiries test_supplier_enquiries_desk
```

The final run passed **44 tests**: 35 exporter/CLI/file checks and nine new
real-core SQLite/HTTP composition cases. The composition includes review
preservation, changed catalog/request warnings, existing order/draft handling,
cancellation, selected-option isolation, and real HTTP -> actual CLI -> files.
Before/after canonical table contents were identical across exports.

A separate example ran the actual canonical catalog/request/option workflow,
then generated two supplier enquiries. Six Chromium checks passed on the exact
generated HTML loaded in memory: desktop/mobile overflow, two supplier sections,
unsent labeling, print breaks and absence of active scripts. These are not
native browser networking, email delivery or hosted deployment tests.

## Example

`source-quotes.json`, `catalog.json`, and `saved-request.json` under
`supplier_enquiry_examples/` are explicitly fictitious. The saved request was
actually produced by the frozen core. Source-file digests and item positions
in the notes refer to the included synthetic source file.

```sh
python3 -S supplier_enquiries.py \
  --desk-request supplier_enquiry_examples/saved-request.json \
  --as-of 2026-09-08 \
  --out /tmp/parts-example-enquiries
```

Its two line-only calculations are USD 97.35 and EUR 75.33. They are separate
options from separate fictitious suppliers, not revenue, live prices, a
conversion, an order total or evidence of real compatibility.

## Publication and customer-use boundary

This source was implemented and tested in the provided cloud runtime. The
original bundle's claim that GitHub and Slack lacked write actions was incorrect.
Complete connector discovery exposes publication actions. The publication
recovery preserves the exact tested exporter, tests and synthetic examples;
only this obsolete documentation paragraph is corrected.

The source publication record is
`p/parts-enquiry-export-publication-20260908-7c28759a.md` in the same repository.
The associated pull request and its merge status establish repository delivery;
source availability does not imply browser controls or customer deployment.
The canonical desk can consume the Python function or CLI described above.
No supplier message, purchase, payment or customer use is asserted.

A separately preserved early draft application is not part of this integration
and is not proposed as another Parts Desk product.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
