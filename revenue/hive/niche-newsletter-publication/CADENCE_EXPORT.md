# Northstar cadence export

`cadence_export.py` is an additive provider-handoff utility for the landed Hive024 Northstar publication desk. Northstar stores each active subscriber's `weekly` or `monthly` preference. This utility turns one **published** issue into a deterministic ZIP for exactly one requested cadence while preserving the existing topic and unsubscribe rules.

It does not edit Northstar state, send mail, contact a provider, or change `app.py`. The SQLite database is opened read-only and every generated recipient record is explicitly `UNSENT`.

## Use

```bash
cd revenue/hive/niche-newsletter-publication
python cadence_export.py \
  --db northstar.sqlite3 \
  --issue issue-003 \
  --cadence weekly \
  --output issue-003-weekly.zip
```

Run again with `--cadence monthly` and a different output path for the monthly audience. Existing output files are never overwritten. The CLI prints only issue/cadence/output metadata, byte count, and the ZIP SHA-256; it does not print recipient addresses.

## Selection contract

A recipient is included only when all of these are true:

- subscriber state is `active`;
- stored frequency exactly equals the requested `weekly` or `monthly` cadence;
- topic preferences are empty (all topics) or contain the issue's topic;
- the issue state is `published` and it retains at least one source link.

Unexpected stored frequency/status values or malformed topic JSON fail closed rather than being silently routed. Recipient filenames use a deterministic hash of the internal subscriber ID, so database identifiers cannot become ZIP paths.

## Acceptance

```bash
python -B -m unittest -v test_cadence_export
python -m py_compile cadence_export.py test_cadence_export.py
```

The focused tests use a real temporary SQLite database with the same source/issue/subscriber fields consumed from Northstar. They cover weekly/monthly separation, topic filtering, unsubscribe suppression, UNSENT recipient packets, byte determinism, read-only behavior, draft/missing issue rejection, persisted-state validation, and output collision refusal.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
