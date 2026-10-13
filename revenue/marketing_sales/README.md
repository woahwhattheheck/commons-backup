# Marketing and sales scale engine

Fourteen public-pain rows are a seed, not a pipeline. On the 2026-08-30
readback, only three rows name verified organizations, only one carries a
published email, that address has already been contacted once, and no row
identifies a verified economic buyer.

This layer creates a large public **research universe** without turning GitHub
owners, repositories, issue authors, public threads, or drafts into qualified
accounts. The existing Airtable `JOJO Revenue Recovery CRM / Revenue Pipeline`
remains the canonical CRM. Private business routes, provider identifiers, and
contact events stay in the private provider/CRM roads.

## Run

```bash
python3 host/marketing_sales.py discover --max-entities 1000
python3 host/marketing_sales.py compile
python3 host/marketing_sales.py validate
python3 -m unittest -v test_marketing_sales.py
```

Turn a researched account into a bounded internal handoff only after it has a
named decision maker, sourced professional route, current need, narrow $199
diagnostic, binary acceptance test, and exact Commons + Gmail Sent dedupe:

```bash
python3 host/prospect_packet.py path/to/prospect.json
python3 -m unittest -v test_prospect_packet.py
```

The compiler emits `READY_FOR_MASTER_OF_ACCOUNTS` only for a complete packet.
That label is not permission or evidence of contact: the result always records
zero external actions and `transport_permission: false`. Missing evidence,
broad offers, prior transport, or hard suppression produce `SUPPRESSED` with
exact reasons. Master of Accounts owns the final action-time dedupe and any
external send.

`discover` executes every configured GitHub public-repository search without
credentials, clusters results by public owner, then deterministically ranks
and caps the research entities. A GitHub `User` is an entity to research, not
an account; even a GitHub `Organization` remains only an organization
candidate until first-party qualification. `compile` builds a deterministic
public projection and rolling top-50 research queue. Neither command drafts,
sends, books, authorizes, captures, or changes the CRM.

The checked-in discovery manifest is one bounded tranche. Increase `pages` up
to ten or add disjoint source shards to advance toward the operating floor of
10,000 public research entities and 1,000 GitHub organization candidates.
Qualification is a later evidence step: verified
organization, current first-party pain, observable business impact, binary
proof fit, relevant owner, legitimate business route, and no suppression.

## Truth

- A repository owner is a research entity in `RESEARCH_REQUIRED`, never
  automatically a prospect or qualified account.
- A public issue/thread is evidence, not contact permission.
- A draft is not a send; a click is not a booking; an auto-reply is not buyer
  interest; an authorization is not capture; captured gross is not profit.
- This engine performs zero transport actions and claims USD 0 cash.
- The compiler exposes the gap instead of filling it with invented buyers.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
