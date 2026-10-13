# LotLens import contract v1 (`commons-lotlens/v1`)

One import is one directory of CSV exports. Every file is optional; unknown
columns are kept on the raw row and shown by `inspect`. Line 1 is the header.
Identifiers are never rewritten and never merged across namespaces: `L-7` in
`sup-acme` and `L-7` in `pilot-plant` are two different things forever.

| file | required columns | optional columns | what it states |
| --- | --- | --- | --- |
| `lots.csv` | `namespace, lot_id` | `supplier, material, quantity, unit, received_at` | a supplier lot exists |
| `splits.csv` | `namespace, lot_id, child_lot_id` | `quantity, unit` | part of a lot became a child lot (both must be in `lots.csv`) |
| `batches.csv` | `namespace, batch_id` | `product, formula_id, formula_version, produced_at, quantity, unit` | a production batch exists |
| `consumption.csv` | `namespace, batch_id, input_namespace, input_kind, input_id` | `quantity, unit` | a batch consumed an input; `input_kind` is `lot` or `batch` (a blend consumes a batch) |
| `rework.csv` | `namespace, rework_id, from_batch_id, into_batch_id` | `quantity, unit, date` | material from one batch went into a later batch |
| `packages.csv` | `namespace, package_id` | `batch_id, product, quantity, unit, packed_at` | a finished package exists; an empty `batch_id` is a fact, not an error |
| `shipments.csv` | `namespace, shipment_id, package_id` | `customer, quantity, unit, shipped_at` | a package went out on a shipment |

## What the engine derives, and what it refuses to derive

- **Edges** only from rows: `split`, `consumed`, `rework`, `packed`, `shipped`.
  Every edge carries the file, line and import version of every row that
  states it.
- **Unresolved** facts when a row points at something no row defines
  (`package_batch_not_in_records`, `consumed_input_not_in_records`,
  `shipment_package_not_in_records`, `split_*_not_in_records`,
  `rework_batch_not_in_records`, `package_without_batch_link`). The row is
  kept; the edge is not invented.
- **Contradictions** when rows disagree: `over_consumption` (consumed more of a
  lot than the lot's quantity), `unit_mismatch`, `multiple_shipped_links`
  (one shipment naming two packages), `multiple_packed_links`,
  `duplicate_link_different_quantity`. All rows involved are cited; nothing is
  dropped or averaged.
- **Coverage gaps** when the records simply stop:
  `package_without_shipment`, `batch_without_package_or_consumer`. The report
  says so per item; it never reads a missing row as "not affected".
- **Cycles** among batches (rework loops) are reported and traversed once.
- **Assumptions** are named rules that are off until an investigator asks
  (`impact --assume NAME`). An edge created by one carries `status: potential`
  and the assumption's name, and the item it reaches is
  `POTENTIALLY_AFFECTED`, never `KNOWN_AFFECTED`. Version 1 ships one:
  `unlinked_package_same_product_day`.

## Versions, reimport, comparison

An import version is the sha256 of the file names and file hashes. Importing
the same bytes again records another sighting and changes nothing.
Importing changed exports creates a new version; `graph` uses the latest by
default, `--versions V1 V2` loads several, and `compare V1 V2` lists the rows
present in only one of them. Copied source files live under
`<workspace>/imports/<version>/` and are never edited.

## Annotations

`annotate namespace/kind/id "text" --by NAME [--supersedes ID]` appends to
`<workspace>/annotations.jsonl`. Revisions are numbered per target; a
superseded annotation stays in the file and is marked `current: false`.
Annotations are exported beside observations, never mixed into them.

## Quantities and units

Quantities are compared only when units agree (case-insensitive). A missing
quantity is a missing quantity; it does not become zero.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
