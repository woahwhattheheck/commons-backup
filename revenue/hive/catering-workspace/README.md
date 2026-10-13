# Catering Workspace

A working, dependency-free browser workspace for one caterer or bakery operator: import a menu, edit an event, prepare a quote, record a confirmation reference, and produce the kitchen sheet from the same revision.

This implements Hive demand `bm-hive-20260908-043`. The sample is synthetic, not a customer order. This release is an offline USD workspace, not a hosted subscription or a payment processor.

## Start and complete an event

Keep `index.html` and `catering.js` together and open `index.html` in a modern browser. A static web server can serve the same folder without an application backend. No installation, account, remote JavaScript, API key, or paid service is needed for the workspace.

1. Replace the sample event details. Set guest count, preparation buffer, dietary requests and service notes.
2. Import menu CSV or JSON, or edit the supplied menu in the expandable editor. Import selects all imported items and resets line overrides; review the selection. Uncheck unused items. Empty per-item Guests follows the event headcount; an explicit zero prepares nothing. A smaller guest count supports an operator-chosen subgroup. Empty Price follows the menu; an explicit 0.00 is free.
3. Edit service, delivery, discount, tax and deposit values. The customer quote and kitchen sheet recalculate together. Use the print buttons for the appropriate document; the browser's print dialog can save PDF. Kitchen CSV carries event details, revision, item IDs, units, portions and supplied notes.
4. Record the customer's confirmation reference after reviewing the actual customer response. It applies only to the current revision. Any edit returns the event to draft; previously exported documents remain unchanged, so replace the customer and kitchen copies after a revision.
5. Enter an existing public payment-provider link to create a handoff. Check its amount separately. The workspace makes no payment request, amount update, verification or reconciliation call. Received amounts are manual operator records.
6. Download the event JSON to retain the complete editable document. Open Event restores it. Save/Restore in this browser uses that origin's local storage on that device; it is not a cloud backup and may be unavailable under browser policy. A download is the portable recovery copy. Browser saves replace the previous saved event; separately downloaded files can retain multiple jobs or versions.

Do not place customer data, exported events, payment-provider secrets or actual kitchen sheets in a public repository. Nothing is automatically uploaded. The payment link opens only when clicked.

## Menu format

CSV columns: `id,name,unit,serves,price,allergens,prep`.

```csv
id,name,unit,serves,price,allergens,prep
SALAD,Garden salad,tray,10,45.00,Review dressing ingredients,Pack dressing separately
ROLL,Bread roll,roll,1,1.50,Wheat; verify supplier label,Pack by service table
```

The first five fields are required. `serves` is the number of portions per selling unit and must be positive; it may have at most two decimal places. `price` is USD per selling unit, with at most two decimal places. IDs must be distinct. The importer supports BOM, CRLF, quoted commas, quoted multiline fields and doubled quotes. Malformed input leaves the existing menu intact. JSON accepts an array of these item objects or an object containing `menu`.

Use the event JSON for exact round-trips. CSV is spreadsheet-friendly: text beginning with formula-like prefixes is prefixed with an apostrophe. This can change such unusual text on a CSV reimport; JSON retains it exactly. The menu editor supports the documented fields; other CSV columns are not retained.

## Calculation contract

For each selected item, prepared units are the ceiling of `guests × (1 + buffer / 100) / portions_per_unit`. The quote bills whole selling units, not fractional trays. Per-item guest counts must not exceed the event headcount. Multiple menu items may serve the same guests; these are selections, not disjoint guest allocations.

Money and percentages are parsed exactly. Arithmetic uses integer cents and BigInt intermediate values. Service is calculated on food subtotal, rounded half-up to a cent. Delivery is then added and discount subtracted. The manually supplied tax percentage applies to that entire amount, rounded half-up; there is no inferred jurisdiction or separate tax treatment per line. The deposit target is the configured percentage of total, rounded half-up. Manual receipts reduce deposit still due and balance still due; overpayment is shown as credit, never as a negative balance. Numeric results exceeding exact integer capacity are reported rather than rounded silently.

Dietary notes do not automatically substitute items or establish allergen suitability. The caterer remains responsible for recipes, supplier labels, preparation and the actual service plan. Missing notes are displayed as missing, not filled with assumed facts.

## Worked synthetic example

At 40 guests and a 10% preparation buffer, the included menu produces 5 salad trays, 5 main-course trays and 44 rolls. Food is $691.00, the 10% service charge is $69.10, delivery is $25.00, discount and tax are zero, and total is **$785.10**. A 30% deposit target is **$235.53**.

Changing headcount to 60 produces 7, 7 and 66 units. Food is $974.00; total including the same service rule and delivery is **$1,096.40**; the deposit target is **$328.92**. Quote and kitchen output share those quantities and the same revision.

## Developer checks

```sh
node --check catering.js
node --test test_catering.cjs
python test_browser.py --chromium /usr/bin/chromium --artifacts /tmp/catering-browser
```

The application has no dependencies. Node is needed only for the 17 calculation/import tests. The browser test additionally needs Python Playwright and Chromium; it starts a temporary loopback HTTP server. `--in-memory` exercises the same DOM/scripts without URL navigation and reports native storage as **not tested**. It does not replace or mock the application's calculation, download, import or print code.

The original build passed 17 Node tests and 15 Chromium in-memory checks, including actual downloads/imports, 40-to-60 recalculation, stale-quote hiding, confirmation invalidation, text rendering, 390px layout and separate print modes. File and loopback browser navigation were rejected by the cloud browser policy; native local-storage persistence and a served end-to-end session were therefore not exercised here. Storage-error presentation was exercised. The app produced zero JavaScript exceptions during those checks and initiated no external request. Print CSS was inspected; a physical print or actual PDF save is not claimed.

The 2026-10-03 native browser continuation opened the retained page through both `file://` and a loopback static server. The synthetic 40-to-60 guest workflow preserved the documented quantities and totals. Save/Restore survived reload and, on the served origin, a complete Chromium process restart. A downloaded event reopened in a new browser context and downloaded byte-for-byte identically; menu CSV round-tripped the retained menu without changing event details, and kitchen CSV matched the same revision. A clearly synthetic manual confirmation was invalidated by the next edit. The 390px viewport fit without page overflow, with zero JavaScript exceptions or external requests.

Open Event and Import Menu now keep their native file inputs keyboard-focusable and show a visible outline on the labeled control. Native Tab followed by Enter or Space opened the actual file chooser and imported the retained downloads. Separate one-page A4 quote and kitchen PDFs were rendered and visually inspected with their correct quantities, revision and authority notes. For this headless capture, DevTools paused the unmodified print-button handler after its mode assignment and before `window.print()`, then Chromium's PDF pipeline captured that mode; resuming cleared it normally. This establishes selected-mode PDF rendering, not an interactive operating-system save dialog or physical printing. No calculator, sidecar, backup, payment or test code changed; no new test suite or dependency was added.

No customer outreach, deployment, processor charge, sale or payment occurred in this build.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
