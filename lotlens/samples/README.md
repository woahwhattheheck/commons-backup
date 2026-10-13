# LotLens sample answers

Three answers the CLI gives on the synthetic pilot fixture, kept here so a reader can see
what an impact report looks like before importing anything. Each pair is one query:
`.json` is the full report the `--out` flag writes (every hop as an edge object with its
source rows), `.md` is the `--md` rendering of the same report. Open `lotlens/app.html` and
choose a `.json` to read the same answer as a page.

| sample | question | command (after the import below) |
| --- | --- | --- |
| `citric-forward` | supplier lot `LOT-CITRIC-01` has a problem; what did it reach? | `impact sup-acme/lot/LOT-CITRIC-01` |
| `citric-forward-assumed` | the same question with the one shipped assumption switched on | `impact sup-acme/lot/LOT-CITRIC-01 --assume unlinked_package_same_product_day` |
| `ship3-backward` | shipment `SHIP-3` is complained about; what went into it? | `impact pilot-plant/shipment/SHIP-3 --backward` |

Regenerate from any checkout (stdlib Python, seconds, no server):

```
python lotlens/lotlens.py -w .lotlens import lotlens/fixtures/synthetic_pilot --label pilot
python lotlens/lotlens.py -w .lotlens impact sup-acme/lot/LOT-CITRIC-01 --out lotlens/samples/citric-forward.json --md lotlens/samples/citric-forward.md
python lotlens/lotlens.py -w .lotlens impact sup-acme/lot/LOT-CITRIC-01 --assume unlinked_package_same_product_day --out lotlens/samples/citric-forward-assumed.json --md lotlens/samples/citric-forward-assumed.md
python lotlens/lotlens.py -w .lotlens impact pilot-plant/shipment/SHIP-3 --backward --out lotlens/samples/ship3-backward.json --md lotlens/samples/ship3-backward.md
```

`test_lotlens_samples.py` (root, battery-discovered) regenerates all three on every run and
fails if the engine's answer or its `content_sha256` drifts from these files. The only bytes
that differ between runs are the `Generated ...` line, `generated_at`, and `imported_at`; the
hash covers the answer, not the clock.

## Reading a sample

- `KNOWN_AFFECTED` rows have a documented row path; the `evidence` column names every source
  row on it (`file:line` in the import shown under `Imports:`).
- `POTENTIALLY_AFFECTED` rows exist only in `citric-forward-assumed`; the `*` in the `via`
  column marks the hop that needed the assumption, and `Assumptions in force:` names it.
- `Unresolved`, `Coverage gaps`, `Contradictions` at the bottom are what the records cannot
  settle. `PKG-P4-1` has no shipment row: the report says the records stop there, not that it
  was never shipped. `BATCH-P3` consumed 40 kg of a 30 kg lot: both rows are cited, neither
  is dropped.
- The `what` column is display only (material and supplier for a lot, product for a batch or
  package, customer for a shipment); the full attributes stay in the `.json`.

Synthetic data throughout (`lotlens/fixtures/synthetic_pilot/`). Nothing here certifies,
recalls, or releases anything.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
