# Resale Workspace

`resale_workspace.py` is a local-first operations core for Hive demand
`bm-hive-20260908-050` (photo-to-listing resale operations).

It turns seller-provided item/photo references into editable listing drafts and
local inventory state without pretending to publish, delete, price, or otherwise
control a remote marketplace.

## Customer workflow

1. Add an item with an original photo reference and SHA-256. That pair is
   immutable for the item.
2. Edit title, condition notes, item attributes, and explicitly mark uncertain
   attributes instead of inventing them.
3. Save source links/notes for price research. The workspace stores references;
   it does **not** calculate or recommend a price.
4. Maintain an editable draft per sales channel.
5. Record already-existing remote listing URLs. This is local bookkeeping only.
6. Mark the item sold. In one SQLite transaction the item leaves every local
   active-channel export and one `PENDING` close task is created for each recorded
   remote listing.
7. A remote close remains `PENDING` until an operator explicitly records
   confirmation. The code performs no marketplace network request.

All write operations require a caller-provided request ID. Identical retries
return the original result; reusing an ID with a changed payload is rejected.

## Run the synthetic acceptance

```bash
cd revenue/hive/resale-workspace
python -m unittest -v test_resale_workspace.py
python -m py_compile resale_workspace.py test_resale_workspace.py
python resale_workspace.py demo fixtures/sample_inventory.json --db /tmp/resale-demo.db
```

The demo starts with one synthetic item active on two channels, then marks it
sold. Both local active exports become empty and exactly two `PENDING` close
tasks remain. `remote_changed` stays `false` until a human/operator explicitly
confirms a task.

## Boundaries

The fixture is synthetic. No original customer photo bytes, marketplace account,
API key, live catalog, purchase, pricing decision, listing publish/delete, stock
mutation on a provider, customer contact, outreach, ad spend, or payment is used.
The software records local intent and handoff state only.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
