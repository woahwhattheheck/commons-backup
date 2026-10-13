# Trade quote-to-schedule service

A dependency-free painting workflow that turns a structured customer request and photo references into an editable, rules-priced quote, a valid PDF, a link-backed acceptance flow, and a collision-checked local job schedule. Missing measurements produce explicit questions and no calculated price.

## Run the included workflow

```bash
python3 trade_quote.py quote \
  --request examples/request.json \
  --rules examples/pricing-rules.json \
  --issued-on 2026-09-08 \
  --valid-days 14 \
  --base-url http://127.0.0.1:8080 \
  --out-dir out
```

The command emits an editable quote JSON and a single-page PDF. The JSON contains its acceptance URL and token. Start the included acceptance endpoint with:

```bash
python3 trade_quote.py serve --quotes-dir out --schedule out/schedule.csv
```

The same acceptance can be exercised without a browser:

```bash
python3 trade_quote.py accept --quote out/Q-….json --token TOKEN --date 2026-09-15 --start 09:00 --schedule out/schedule.csv
```

`examples/request-missing.json` demonstrates the no-guess boundary: it requests the missing room height, emits no amount, and creates no acceptance URL or PDF. `examples/site-photo.svg` is explicitly a synthetic intake-file fixture, not a customer photograph.

All source inputs and photos are retained by path and SHA-256. Pricing is editable in `pricing-rules.json`; changing it creates a new quote ID and acceptance token. Acceptance writes only the local schedule and receipt. It sends no customer message, writes no external calendar, collects no payment, and does not claim customer acceptance.

## Verify

```bash
python3 -m unittest -v test_trade_quote.py
python3 -m py_compile trade_quote.py test_trade_quote.py
```

Offer reference: Hive demand `bm-hive-20260908-039`, advertised at $499 setup plus $149/month. This is a runnable delivery checkpoint, not a subscription sale or payment claim.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
