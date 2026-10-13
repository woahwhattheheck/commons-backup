# Website → people → email → book

Explee-style auto-GTM loop as a Commons capability. The **seller website is the
seed**. Drop a public page, extract the product and ICP, qualify external people
who need it from the existing evidence-bound Smart Outreach catalog, draft
emails with a book-a-call CTA, and stage bookings.

Contacts published on the seller website are retained as `seller_contacts`
context and are never treated as prospects. External candidates keep their
first-party evidence, route state, collision receipts, and occupancy decision.
Only `READY_TO_DRAFT` prospects with a verified email route receive a staged
draft. This composes `host/smart_outreach.py` and its checked-in candidates;
it does not mint a second prospect source.

Owner ask: Slack `#commons` `1788068123.766099` (2026-08-30 01:35 ET) —
"Do what these guys are doing" + Explee auto-GTM screenshot. Receipt:
[`p/website-people-email-book-20260830-01.md`](../../p/website-people-email-book-20260830-01.md).
Public door: [`website-people-email-book.html`](../../website-people-email-book.html).
Agent compose/query over this loop and its sibling ledgers:
[`lm-gtm-index.html`](../../lm-gtm-index.html) / [`revenue/lm_gtm_index`](../lm_gtm_index/README.md).
That layer projects existing ids; it does not replace this loop or mint a second CRM.

This does **not** remint:

- `revenue/smart_outreach` — composed evidence-bound discovery, qualification, and collision suppression
- `revenue/subzero_gtm` — SUBZERO SKU architecture; that leftover forbids outreach
- `host/swarm_mail.py` — later exact-once transport after an owner mailbox exists
- `revenue/reply_to_revenue` — inbound cash truth after replies exist

It composes with those roads. Live send is refused here (`--send` exits 3).
Calls booked stay `0` until an owner calendar actually records one. Emails
are never invented. Prospects without a verified first-party email route stay
undrafted.

## Attach owner mail without exposing it

An email address, phone number, or device is private operator capacity, not a
prospect and not a sale. Keep every actual address, credential, DNS value, and
device secret outside Git. After provisioning the existing Codex route through
Swarm Mail, export only its redacted runtime status and let this loop consume
that projection:

```sh
python3 host/swarm_mail.py status --db /srv/commons-mail/private/mail.sqlite3 > /srv/commons-mail/private/status.json
python3 host/website_people_email_book.py run --mailbox-status /srv/commons-mail/private/status.json
```

The loop accepts only `SWARM_MAIL_PRIVATE_RUNTIME_STATUS`, rejects any `@`
character, verifies the measured count against inbox states, and requires one
opaque address reference for the measured `codex-sales` inbox. That changes
mailbox truth from `NEEDS_OWNER_MAILBOX` to `OWNER_MAILBOX_MEASURED`; it
does not send. Exact-once queueing, suppression, dispatch, and replies remain in
Swarm Mail. A phone or physical device may host those private operator surfaces,
but its number, identity, and credentials never belong in this public artifact.

## Commands

```sh
python3 host/website_people_email_book.py run
python3 host/website_people_email_book.py run --url https://example.com
python3 host/website_people_email_book.py validate
python3 -m unittest -v test_website_people_email_book.py
```

`--send` is illegal and exits 3. `--url https://...` fetches a public seller
page. `--prospects` and `--receipts` select the existing Smart Outreach inputs.
The default measured run uses `fixture_seller.html` plus the current checked-in
real prospect catalog. Current truth is four external prospects and one eligible
Composio draft. The need signal comes from Composio's first-party changelog and
the route from its first-party support page. The draft remains `STAGED_NOT_SENT`;
no booking or cash is claimed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
