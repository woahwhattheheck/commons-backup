# Local promotion production desk

This dependency-free command converts one reviewed brand file and offer list into a consistent local web/social/print package. Active offers receive matching copy, price, expiry, landing page and real QR SVG. Upcoming offers are held. Expired offers remain in the audit calendar but disappear from every publishable surface on the next atomic rebuild.

```bash
python3 promotion_desk.py --brand examples/brand.json --offers examples/offers.json --as-of 2026-09-08 --base-url https://offers.example.test --out out
python3 -m unittest -v test_promotion_desk.py
```

`out/` contains web landing pages, social/print SVGs, QR SVGs, `expiry-calendar.csv`, and a source-hash manifest explicitly marked `LOCAL_EXPORT_ONLY_UNSENT`. Keep source files outside `out/`; the generator replaces only its own output tree after a complete staged build.

Set `--base-url` to the public URL where `out/site/` will be served. For example, `https://offers.example.test` produces a QR destination of `https://offers.example.test/offers/weekday-lunch.html`, matching the landing page linked from `out/site/index.html`. A site hosted under a path can use that path in the base URL. For a local preview, serve `out/site/` and use that server's origin as the base URL when rebuilding.

Keep `social/`, `print/`, and `qr/` together with their relative paths when previewing or exporting the SVG cards: the cards reference `../qr/<offer_id>.svg`. Open the print SVG in a browser with those files accessible and print at Letter size with backgrounds enabled. Expiry is applied when this command runs with the chosen `--as-of` date; the package does not install a scheduler or publish changes to customer channels.

The fixtures are fictional. No customer channel, provider, sale, payment, or deployment is represented.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
