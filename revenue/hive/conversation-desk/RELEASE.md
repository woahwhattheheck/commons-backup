# Conversation Desk standalone release

`build_release.py` creates a deterministic, code-only ZIP that can be extracted
and run without a Commons checkout. The allowlist is intentionally only:

- `app.py`
- `index.html`
- `desk.js`
- `README.md`

The builder adds `START_HERE.md` and `manifest.json`. It never recursively walks
the product directory, so SQLite databases/WAL files, screenshots, JSON exports,
logs, caches, secrets, restore artifacts, tests and arbitrary customer files are
not distribution inputs.

Build from a clean trusted checkout:

```sh
cd revenue/hive/conversation-desk
python3 -B build_release.py --out /private/output/conversation-desk.zip
```

The destination must not exist. Publication uses an exclusive hard link from a
fully written/synced same-directory staging file so a competing existing output
is preserved instead of replaced. This is per-file publication, not a guarantee
against power loss or a cryptographic signature.

Verify the focused release and current application source:

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_release_package
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_app
node --check desk.js
```

`test_release_package` builds and extracts the real current product into a fresh
temporary directory, starts only the extracted `app.py`, creates a fictional
conversation, obtains three template drafts, saves one, exports the workspace,
restarts against the same SQLite database, reopens the draft, and erases the
workspace. It also verifies the curated member set and manifest hashes.

This release is a local shared-workspace tool, not an authenticated hosted SaaS.
It includes no checkout/payment, automatic message sending, external language
model, customer data, real chat, image, database, deployment or revenue claim.
Optional OCR still depends on a separately installed local Tesseract executable;
manual transcript entry works without it. `README.md` remains the product's
source of truth for data handling, revisions, deletion and browser-test limits.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
