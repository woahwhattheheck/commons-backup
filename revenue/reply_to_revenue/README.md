# Reply-to-revenue

Always-on inbound composition over roads Commons already has. It does not
replace `host/smart_outreach.py`, Swarm Mail, production-survival reply
intake, acceptance, the Airtable CRM, or `host/cash_now.py`. It reads them
and publishes one public funnel.

## What it does

1. Ingest each inbound event once (`event_ref` + `payload_sha256`).
2. Classify truthfully. Zendesk ticket mail, CSAT surveys, and vendor AI
   assistants are `AUTO_RESPONSE`. They are not buyer interest.
3. Surface a human `POSITIVE_SCOPE` immediately with the exact next action
   `NEEDS_ACCEPTANCE` and a handoff to `revenue/production_survival/acceptance.py`.
4. Keep stale / silent contacts on `MONITOR_NO_RESEND`. Completed sends and
   explicit `do_not_resend` are HARD DNR.
5. Leave cash at USD 0 unless a named payment evidence URL exists.

## Measured 2026-08-28T16:15:00Z

Authorized Gmail pass on `tokenjunkielabs@gmail.com`, two queries, zero
sends. Four attributed inbound events, all auto-acks (Upvest Zendesk ticket
+ CSAT; two Ollama AI-agent placeholders). Zero human-positive. Zero
scope acceptances. Zero payment evidence. USD 0 cash.

A second bounded Gmail pass at 2026-08-28T16:22Z confirmed the same four
inbound auto-acks and zero new human-positive events. Zero sends.

## Commands

```sh
python3 host/reply_to_revenue.py validate
python3 host/reply_to_revenue.py snapshot
python3 host/reply_to_revenue.py surface
python3 host/reply_to_revenue.py classify --markers "ticket has been created,thank you for reaching out"
python3 -m unittest -v test_reply_to_revenue.py
```

`--send` is illegal and exits 3. Public door:
[`reply-to-revenue.html`](../../reply-to-revenue.html).

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
