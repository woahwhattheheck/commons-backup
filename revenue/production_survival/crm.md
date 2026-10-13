# Existing Revenue Pipeline map

Use the existing Airtable base `JOJO Revenue Recovery CRM` and its existing `Revenue Pipeline` table. Do not create a second CRM, table, or shadow spreadsheet.

No schema change is required. Use the existing fields this way:

| Existing field | Production-survival use |
| --- | --- |
| Org/Control | Prospect organization |
| Record Type | Prospect |
| Stage | Canonical commercial state below |
| Offer SKU | `same-day-agent-survival-proof` |
| Consumer Fit | Exact first-party pain phrase and why the binary test fits |
| Source URL | First-party pain source |
| Contact Role | Relevant owner of the failing workflow |
| Contact URL | Exact approved contact route |
| Evidence URL | Provider receipt, reply, delivered receipt, or payment evidence |
| Last Result | Timestamped outcome plus provider message ID and dedupe key |
| Next Action | Owner, action, and due time; `DO NOT RESEND` where applicable |
| Owner | Bernays for this offer lane |

## Canonical stages

| State | Existing `Stage` value | Required evidence |
| --- | --- | --- |
| Public pain captured | Prospect | Phrase plus source URL |
| Pain, role, and binary test fit verified | Qualified | Consumer Fit completed |
| Written yes before checkout | Purchase Intent | Reply URL or provider receipt |
| $2,500 scope accepted | Accepted | Accepted sentence, binary test, deadline, refund term |
| Proof and receipt handed off | Delivered | Commit-pinned receipt URL |
| Funds collected | Paid | Payment evidence URL |
| No fit, negative reply, opt-out, or permanent bounce | Disqualified | Exact reason and timestamp |

Contacted, scheduled, and follow-up-due are transport states, not commercial stages. Record them in `Last Result` and `Next Action` without inventing a second pipeline.

## Dedupe invariant

Use `lower(domain)|lower(recipient)|offer_sku|channel` as the dedupe key inside `Last Result`. Before sending, check the row and provider history. Send only when there is no matching provider message ID or scheduled item, the row is not disqualified, and Bernays owns the action.

The current seven-contact GGUF queue is independent: Parallel and NextGen are completed with duplicate history and hard do-not-resend; Ollama and Jan are completed; LM Studio, AnythingLLM, and Lyceum are scheduled behind the mailbox limit. Do not convert those contacts to this SKU or send again merely to populate this lane.

## Weekly funnel

Count first-party signals, qualified signals, unique delivered contacts, positive replies, accepted $2,500 scopes, on-time deliveries, $12,000/$30,000 expansions, and collected cash. Scheduled messages, opens, repository traffic, and duplicate sends are not revenue.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
