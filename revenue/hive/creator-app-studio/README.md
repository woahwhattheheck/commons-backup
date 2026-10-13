# Creator App Studio — Hive016

A working local studio for a creator-branded **workshop kit and shared-supplies planner**.
It saves versioned briefs in SQLite and exports a standalone browser app plus
editable launch assets. This is the reusable delivery slice of Hive demand016,
not a claim that a creator has been interviewed, partnered with, or sold an app.
The supplied workshop brief is explicitly synthetic.

## Run

Python 3.10 or newer is sufficient for the studio. No runtime packages, accounts,
external model, customer data, payment connection or provider setup are needed.

```sh
cd revenue/hive/creator-app-studio
python studio.py --db ./creator-studio.sqlite3 --port 8765
```

Open `http://127.0.0.1:8765`. Keep the server on its default loopback interface;
this is a local operator application, not a hosted multi-tenant service.

Edit the creator, audience, problem, onboarding, proposed pricing, support route
and material defaults. Save the brief, open the working app, or export its launch
ZIP. Reopen an existing project to save another revision. Competing stale edits
receive an explicit conflict instead of overwriting the current revision.

The ZIP contains `index.html`, `brief.json`, `revisions.json`, `START-HERE.md`,
`launch-copy.txt` and `SHA256SUMS`. Open its `index.html` directly. No CDN or network
request is needed by the exported app. Brief wording and defaults are editable;
another type of audience workflow still needs real implementation rather than
just changing its name.

## Complete reference workflow

Enter 12 attendees, leave Demo kits and Spare kits at zero, and enter two card
sheets per kit, a ten-percent reserve, and ten sheets per pack. The actual
planner calculates 26.4 required sheets, three packs, and
30 purchased sheets. Edit the attendee count to 20, save a named plan, reload,
and reopen it: the result becomes 44 required sheets, five packs, and 50 purchased.
Export CSV for editing or JSON for portable saved-plan backup. Re-importing an
identical backup does not duplicate plans; conflicting plan IDs are rejected
without changing existing data. A save is only reported after browser storage
actually succeeds.

Material quantities use exact scaled-integer arithmetic, including fractional
pack boundaries such as three times 0.1 fitting one 0.3 pack. Every quantity is in
the explicitly entered unit; there is no implicit unit conversion. Reserve can
range from zero to 100 percent. Resource bounds are 1–1,000,000 attendees,
0–1,000,000 demo kits, 0–1,000,000 spare kits, 1–50 materials, six decimal places
per material input and 10,000 saved plans. All three kit counts must be whole
numbers. Suggested usage
targets remain advisory; reaching a pricing-plan target does not lock the app.

## Demo kits and spare kits

Keep participant attendance separate from the instructor's demonstration kits
and the extra complete kits you want ready. The planner displays all three
counts and their computed total:

**Total kits = Attendees + Demo kits + Spare kits.**

For materials with **Per kit** selected, the entered quantity is multiplied by
that total. The material's reserve percentage is applied afterward, followed by rounding the purchase up
to whole packs. A spare kit is an extra complete kit; the reserve percentage is
an additional allowance on each material's resulting quantity.

For a workshop walkthrough, enter 12 attendees, one demo kit and two spare kits.
Add pens at two per kit and sheets at five per kit. Set both materials' reserve
to zero and pack size to one. Save a named plan, reload, and reopen it. Then
change only attendance to 13, save, and reopen again. The expected results are:

| Attendees | Demo kits | Spare kits | Total kits | Pens | Sheets |
| --- | --- | --- | --- | --- | --- |
| 12 | 1 | 2 | 15 | 30 | 75 |
| 13 | 1 | 2 | 16 | 32 | 80 |

The saved plan retains the separate counts. CSV download includes **Demo kits**,
**Spare kits**, **Total kits**, **Quantity basis**, and the entered **Quantity**.
Use JSON download/import to retain and move the saved plans themselves. Leave
both extra counts at zero for the original attendance-only workflow above.

## Fixed shared supplies

Each material has a **Quantity basis** selector. Choose **Per kit** for quantities
used by every attendee, demonstration and spare kit. Choose **Once per workshop**
for a fixed shared-supply quantity, such as the total reusable brushes you want
ready for the event. Enter that workshop total directly; the planner does not
infer how many attendees can share a tool.

| Quantity basis | Base required quantity |
| --- | --- |
| Per kit | Entered quantity × total kits |
| Once per workshop | Entered quantity once |

The same reserve percentage and upward whole-pack rounding apply after this
calculation in both modes. Changing attendance, demo kits or spare kits changes
per-kit quantities while fixed workshop quantities stay unchanged. The results
and CSV identify each row's basis explicitly.

Continue the 15-to-16-kit walkthrough above with the existing **Brush** material:
select **Once per workshop**, quantity one, reserve zero and pack size one. It
requires one brush before and after the kit-count change, while pens change
from 30 to 32 and sheets from 75 to 80. Save and reopen the mixed plan, export its
CSV and JSON, then restore its JSON in the downloaded standalone app to keep the
same basis and quantities.

For creator defaults, the editable material JSON accepts an optional
`quantity_basis` of `per_kit` or `per_workshop`; omitted values preserve the
original per-kit behavior. These defaults persist with the brief revision and
travel in the launch ZIP. For compatibility, material-default and saved-plan
JSON retain the existing `per_attendee` field name for the entered **Quantity**;
the selected basis determines whether it is per kit or once per workshop.

## Persistence and privacy

The studio database stores brief revisions, not end users' saved workshop plans.
The generated app stores plans in its browser's local storage, scoped by project
ID. The studio preview and a downloaded file are different browser storage
locations. Use JSON export/import to move plans between them. Moving a local file,
using another browser, or clearing browser data may remove access to old plans.
Export backups first. Unreadable storage is not overwritten or exported as a
successful empty backup. Use one editing tab per project; cross-tab simultaneous
editing is not a transactional collaboration feature.

The updated planner reads existing browser plans and schema 1 or 2 JSON backups.
Missing material `quantity_basis` values default to `per_kit`. Schema 1 may omit
`demo_kits` and `spare_kits`, which default to zero; schema 2 and 3 require both
counts. New JSON backups use **schema 3**, with an explicit quantity basis for
every material. Schema 3 imports require those bases, so missing or unsupported
values do not silently change a fixed supply into a per-kit quantity. Project
IDs and duplicate/conflicting-plan behavior are preserved. Use the updated app
for schema 3 backups: an older app rejects the version instead of importing a
plan while losing its fixed quantities.

Pricing and launch copy are drafts. Support is operator-provided text. There is
no checkout, paid-plan enforcement, outbound messaging, analytics, deployment or
claim that commercial fulfillment has happened. Audience-demand notes are not
independently verified. Actual creator discovery, a source-supported niche,
a real support route and a target user's acceptance remain commercial next steps.

## Tests

```sh
python -B -m unittest discover -v
```

The shipped suite has 26 methods: real temporary SQLite files, restart and revision
history, threaded competing writes, live HTTP endpoints, packages/checksums,
input-shape handling, shipped JavaScript parsing and 500 deterministic JavaScript
arithmetic cases compared with Python Decimal. Node is required for the seven
JavaScript test methods; those are explicitly skipped when Node is absent.

Optional complete browser check:

```sh
python -m pip install playwright==1.57.0
python -m playwright install --with-deps chromium
python -B browser_check.py --output browser-results
```

This check exercises the real studio, saved-plan reload, CSV/JSON downloads,
retry-safe import, and the actual exported standalone app. It writes screenshots
and a result JSON. Existing Chromium can be selected with `--chromium PATH`.

Development execution on September 8, 2026: **26/26 methods passed, zero skips**.
The provided container's Chromium rejected local navigation with
`ERR_BLOCKED_BY_ADMINISTRATOR` before any browser check ran. That is not a browser
pass. No browser policy or host controls were changed. The included narrowly
path-scoped `.github/workflows/hive-creator-app-studio.yml` runs the same suite and
browser check through normal GitHub Actions and retains its actual result.

The browser CI setup follows the Playwright Python browser-installation guide:
https://playwright.dev/python/docs/browsers . It is a test dependency only.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
