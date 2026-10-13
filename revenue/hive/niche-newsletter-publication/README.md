# Northstar Brief — niche newsletter publication desk

A dependency-free local publication desk for Hive demand `bm-hive-20260908-024`. It keeps sources attached to issue revisions, stores subscriber preferences and suppression state in SQLite, exposes a small browser workspace, maintains an archive/calendar, and emits **UNSENT** welcome and scheduled-issue files for later authorized provider import.

## Run the fictional demo

```bash
cd revenue/hive/niche-newsletter-publication
python app.py --db northstar.sqlite3 --seed demo.json --port 8765
# open http://127.0.0.1:8765
```

Seed without serving:

```bash
python app.py --db northstar.sqlite3 --seed demo.json --seed-only
```

The three included issues and every source note are explicitly fictional/self-authored fixtures. `example.invalid` subscriber addresses cannot receive mail. The application never opens an SMTP/API client and never writes an external calendar or newsletter provider.

## HTTP surface

- `GET /api/state` — sources, publication calendar, archive, subscriber state.
- `POST /api/sources` — add a source reference (`http(s)` or `self-authored:`).
- `POST /api/issues` — create a sourced issue draft.
- `POST /api/issues/<id>/revise` — revisioned edit; source links are snapshotted in history.
- `POST /api/issues/<id>/publish` — freeze the issue for export; retry is idempotent.
- `GET /api/issues/<id>/export` — ZIP with manifest, issue text, source ledger and one provider-agnostic UNSENT recipient record per eligible active subscriber.
- `POST /api/subscribers` — local subscription record.
- `POST /api/subscribers/<id>/preferences` — topics/frequency.
- `POST /api/subscribers/<id>/unsubscribe` — durable suppression; later welcome/export packets exclude that subscriber.
- `GET /api/subscribers/<id>/welcome` — UNSENT local JSON handoff.

## Acceptance

```bash
python -B -m unittest -v test_app
python -m py_compile app.py test_app.py
```

The focused suite uses real temporary SQLite databases and an actual `ThreadingHTTPServer` bound to loopback. It covers subscribe → welcome → preferences → issue export → unsubscribe suppression, revision history/source preservation, reopening, export determinism at the semantic level, idempotent publish/unsubscribe retries, malformed input, and the three-demo-issue archive.

No claim is made that a subscriber was contacted, a provider accepted an import, a scheduled issue was delivered, or the proposed commercial offer was sold.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
