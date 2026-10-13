# Apparel Catalog Image Studio — Hive007

A local, deterministic catalog-production desk for independent apparel brands. It accepts an **authorized RGBA PNG garment source**, records its exact SHA-256 and actual item metadata, audits declared colors/detail pixels, and produces a consistent ten-image pack against selectable generated mannequin/background scenes.

The renderer does **not** redraw the garment. It places the source at 1:1 pixel scale. Fully opaque garment pixels are copied exactly and then re-read from the output; soft-alpha edge pixels use deterministic source-over compositing without resampling. The original source is preserved in every catalog ZIP.

## Offer represented by this build

- ten-image catalog pack: **$99 proposed**
- recurring catalog work: **$299/month proposed**

Those are editable commercial offers, not claims of a sale, customer approval, or external delivery.

## Run the included synthetic mini-catalog

```bash
python -B studio.py sample ./demo-run
```

This creates an original synthetic navy tee, audits body color, bottom seam, gold logo, size tab, source dimensions and source hash, then builds ten 720×720 PNGs plus `manifest.json`, `catalog.csv`, and deterministic `catalog.zip`.

To audit or build an authorized garment manually:

```bash
python -B studio.py audit ./my-item/garment.json
python -B studio.py catalog ./my-item/garment.json ./my-item/brand-preset.json ./delivery-001
```

`garment.json` pins `source_sha256`, `[width,height]`, actual SKU/name/size, declared colors, and any pixel-level detail checks the operator chooses from the real item. The strict shipped codec accepts 8-bit non-interlaced RGBA PNGs so fidelity is testable without hidden image libraries.

## Browser desk

```bash
python -B app.py --workspace ./workspace --host 127.0.0.1 --port 8878
```

Open `http://127.0.0.1:8878` and:

1. import an exact PNG garment source;
2. enter SKU/name/actual size and optional declared-color/detail checks;
3. create a project with a ten-scene brand preset;
4. save revisioned background/mannequin choices;
5. render the latest revision or build the complete ten-image catalog.

The server refuses non-loopback binding. Imports, SQLite revisions, rendered images and catalog ZIPs stay in the selected local workspace. No provider account, remote model, upload, scheduling, tracking, or CDN is used.

## Faithfulness contract

The tool is intentionally conservative:

- source PNG bytes are retained and hashed;
- dimensions must match the garment spec;
- every declared exact color must occur in an opaque source pixel;
- named seam/logo/size-tab checks point to exact source coordinates/colors;
- source is never rescaled in faithful mode;
- every fully opaque source pixel is copied byte-for-byte into each rendered PNG and verified after encoding/decoding;
- soft-alpha edges are composited source-over, without interpolation;
- generated mannequins/backgrounds are procedural scene elements behind the garment, not claims of real people;
- catalog manifests bind every output to the same source hash and size.

For a real client, use only sources the client owns or is authorized to provide. An operator still needs to choose meaningful checks against the physical/listing item; this software does not infer whether a label or size statement is truthful from pixels alone.

## Tests

```bash
python -B -m unittest -v test_studio.py
```

The suite exercises PNG CRC/filter decoding, source tamper rejection, color/detail checks, ten distinct actual PNG renders, pixel fidelity, deterministic rebuilds/ZIPs, revision persistence/conflicts, path confinement, and the real loopback HTTP import → project → revise → render → catalog workflow. The browser JavaScript is also syntax-checked with Node when available; otherwise that one check is explicitly skipped.

## Delivery boundaries

The included demo garment is synthetic original source. No external customer, brand partnership, sale, generated human likeness, platform upload, provider mutation, or customer acceptance is claimed. The browser/API creates local artifacts only.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
