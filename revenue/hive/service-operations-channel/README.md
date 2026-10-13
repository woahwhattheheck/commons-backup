# Hive023 · service-operations tutorial channel

This package turns the landed Hive09 intake/CRM workflow into a ten-episode operator tutorial channel. The first three episodes are publish-ready **local demo assets**: MP4 recordings, WebVTT captions, editable scripts/descriptions, and editable SVG thumbnails. They use synthetic records only. Nothing in this package posts to a platform, contacts a customer, changes an account, or claims external publication.

## Source boundary

The recordings are generated from the existing application in `revenue/hive/intake-crm-workflow/`; this package does not fork or modify it. The build pins the exact landed source used for these recordings:

- `workflow.py` Git blob `da339d714fd610689dafaca5a2e47c57d772edce`
- `index.html` Git blob `62f98f0bfd798d8b5abe74094337fea3af7c991a`
- selected-event retry behavior landed through PR #10513

`build_media.py` refuses to render against different source bytes so the shipped videos remain source-bound evidence rather than a floating claim about a later UI.

## Rebuild

From repository root, with Python 3.11+, Chromium, `ffmpeg`, `ffprobe`, and the Python `playwright` package installed:

```bash
python revenue/hive/service-operations-channel/build_media.py \
  --repo-root . \
  --out revenue/hive/service-operations-channel
```

The script verifies the exact landed source, separately exercises its real `/health` HTTP handler over loopback, then drives the exact landed UI and `Store` implementation with a temporary SQLite workspace for each episode. In this builder environment Chromium blocks direct loopback navigation by administrator policy, so the capture harness loads the exact `index.html` with a build-time `<base>` tag and deterministic `crypto.randomUUID` polyfill required by the non-secure `about:blank` capture origin, and intercepts its otherwise unchanged API fetches into the landed `Store` methods. It captures four live UI states per episode, encodes a 16-second H.264 recording, writes aligned WebVTT captions, and validates every video with both `ffprobe` and a full `ffmpeg` decode. This is not claimed as browser validation of the production HTTP transport, and it leaves the source app untouched.

## Editorial assets

- `EPISODES.md` — ten-episode slate plus editable scripts/descriptions for episodes 1–3.
- `episode_specs.json` — synthetic fixtures, titles and caption text consumed by the builder.
- `captions/` — WebVTT sidecars for the first three recordings.
- `thumbnails/` — editable SVG source graphics.
- `media/` — validated H.264 MP4 recordings generated from live local app sessions.
- `validation.json` — exact source pins, media hashes, codec/duration/dimensions, and validation boundary.

These are local production deliverables, not proof of external publication, audience reach, customer adoption, booking, payment, or provider integration.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
