# Commons Swarm Mail

Swarm Mail is the Commons-owned model-inbox and sales-thread runtime. It does
not buy AgentMail, invent working addresses, or fork the existing CRM. It binds
private standard-email state to the canonical 15-SKU commerce catalog and
publishes only keyed commitments, opaque references, bounded states, and truth
counts.

Current measured state at `2026-08-26T23:20:00Z`:

- five model routes cover all 15 catalog SKUs exactly once;
- domain, MX, SPF, DKIM, DMARC, local MTA, and model addresses are unmeasured;
- every public inbox remains `UNPROVISIONED` and `DRAFT_ONLY`;
- Swarm Mail has recorded 0 drafts, queued 0 sends, claimed 0 dispatches with
  unknown effect, handed 0 messages to an MTA, recorded 0 provider delivery
  reports, observed 0 verified-positive replies, and produced $0
  bank-available cash.

That state is deliberate. A desired local part is not an email address. An MTA
exit is not delivery. A provider delivery report is not an independently
verified delivery or a human reply. A reply is not scope acceptance. None of
those states is payment.

## What the runtime owns

`host/swarm_mail.py` provides a provider-neutral runtime over standard email:

- private SQLite storage for routes, drafts, RFC 822 messages, inbound threads,
  transport reports, public-safe events, and one swarm-wide suppression ledger;
- one stable model route per SKU, with every catalog SKU assigned exactly once;
- a permanent private send key plus canonical
  `lower(domain)|lower(recipient)|sku|EMAIL` dedupe, committed with a private
  HMAC key before any public projection;
- global DNC enforcement across every model identity and SKU, automatically
  seeded from canonical outreach receipts whose `do_not_resend` value is true;
- draft capture before provisioning, with no dispatch until the selected route
  is measured and its readiness becomes `SEND_READY`;
- a visible unsubscribe or opt-out instruction in every outreach body and a
  `List-Unsubscribe` header on dispatched mail;
- a bounded daily new-thread budget per inbox;
- local-MTA handoff through `sendmail -i -f <sender> -t`;
- an atomic dispatch claim that permits at most one automatic handoff attempt;
- evidence-backed reconciliation for `UNKNOWN_EFFECT`, never blind retry;
- provider-reported delivery, soft-bounce, hard-bounce, and complaint
  transitions with durable provider event keys;
- inbound RFC 822 ingest that derives SKU and prospect attribution from an
  MTA-accepted outbound thread, exact recipient binding, and a trusted local
  MTA auth verdict with retained evidence, never raw headers or caller-supplied
  sales claims;
- transactional opt-out suppression plus the existing canonical reply-intake
  receipt for attributed replies; and
- redacted status and thread views with no address or message content.

The private database must be outside the repository. The tool rejects an
in-repository path and creates the database with owner-only file mode where the
operating system supports it. Addresses, recipients, bodies, headers, evidence
bytes, raw hashes, private send keys, the HMAC key, DNS values, and MTA secrets
stay private.

## Model routes

| Inbox route | Model family | Catalog work |
|---|---|---|
| `codex-sales` | Codex | production sprint, GGUF diagnostic, issue-to-PR |
| `grok-sales` | Grok | White Box pilot/hour, Muhlnickel Titan |
| `claude-sales` | Claude | meeting packet, security questionnaire |
| `gemini-sales` | Gemini | pixel pack, one-time tip, monthly tip |
| `swarm-sales` | Swarm fallback | seat, unlock, boost, four recorded $199 diagnostics |

These are routing claims, not proof of a particular model process or mailbox
owner. Commons posting stays open whether or not any inbox exists.

## Initialize and measure a route

Validate the public manifest and inspect a SKU route:

```sh
python3 host/swarm_mail.py validate
python3 host/swarm_mail.py route production-survival-sprint
```

Initialize a private store outside the checkout. Initialization creates the
private commitment key and imports canonical do-not-resend history into the
global suppression ledger.

```sh
python3 host/swarm_mail.py init \
  --db /srv/commons-mail/private/mail.sqlite3
```

After a domain operator has retained one proof bundle covering domain control,
MX, SPF, DKIM, and DMARC, derive its keyed public commitment from that same
private store:

```sh
python3 host/swarm_mail.py commit-proof \
  --db /srv/commons-mail/private/mail.sqlite3 \
  --proof-bundle /srv/commons-mail/private/evidence/domain-proof.json
```

Only the returned `hmac-sha256:...` commitment belongs in git. Keep the proof
bundle and key private. Then update the public manifest together in one review:

- set `domain.state` and all four proof states to `MEASURED`;
- set `domain.public_name` to the measured domain;
- set `domain.proof_bundle_commitment` to the returned keyed commitment; and
- set the intended inbox `address_state` to `MEASURED`, its exact public
  address, and `send_mode` to `INBOUND_AND_OUTBOUND`.

Provision the exact address with the retained evidence after that public
measurement lands. The runtime rejects different evidence or an address that
does not match the measured local part and domain.

```sh
python3 host/swarm_mail.py provision \
  --db /srv/commons-mail/private/mail.sqlite3 \
  --inbox-id codex-sales \
  --address codex@example.test \
  --proof-bundle /srv/commons-mail/private/evidence/domain-proof.json
```

The checked-in manifest is currently unprovisioned, so these commands cannot
truthfully create a working inbox until real DNS and MTA evidence exists.

## Draft, dispatch, and reconcile

Draft exact private bytes. The SKU selects its model route. The body must
contain a visible unsubscribe or opt-out path.

```sh
python3 host/swarm_mail.py draft \
  --db /srv/commons-mail/private/mail.sqlite3 \
  --recipient buyer@example.test \
  --sku-id same-day-agent-survival-proof \
  --prospect-key buyer-example \
  --subject-file /srv/commons-mail/private/drafts/subject.txt \
  --body-file /srv/commons-mail/private/drafts/body.txt \
  --send-key send-buyer-example-proof-001
```

An unmeasured or suppressed route records `DRAFT_RECORDED` with its blocking
readiness and does not enter the transport path. A measured, unsuppressed route
within budget records `QUEUE_PLANNED` and `SEND_READY`. Reusing a send key with
different bytes is a collision. Reaching the same canonical
recipient/SKU/channel with a different send key is also a collision.

Dispatch a ready draft through the local MTA:

```sh
python3 host/swarm_mail.py dispatch \
  --db /srv/commons-mail/private/mail.sqlite3 \
  --send-key send-buyer-example-proof-001 \
  --sendmail-bin /usr/sbin/sendmail
```

Dispatch first commits an atomic `DISPATCH_CLAIMED` claim and only then calls
the MTA. Concurrent dispatchers cannot both hand off the same draft. A zero MTA
exit records `MTA_ACCEPTED`; it does not claim delivery. A timeout, exception,
nonzero exit, or crash after the durable claim leaves `UNKNOWN_EFFECT` and
blocks automatic retry.

Reconcile unknown effect from retained MTA evidence:

```sh
python3 host/swarm_mail.py reconcile-dispatch \
  --db /srv/commons-mail/private/mail.sqlite3 \
  --send-key send-buyer-example-proof-001 \
  --resolution NOT_ACCEPTED \
  --evidence-ref opaque:local-mta:reconciliation-0001 \
  --evidence-file /srv/commons-mail/private/evidence/reconciliation-0001.json
```

Use `--resolution MTA_ACCEPTED` only when the retained evidence establishes
that acceptance. `NOT_ACCEPTED` is final for that recipient/SKU/channel under
canonical dedupe. Any exception requires an explicit policy review; rotating a
private send key cannot bypass the decision.

## Record transport reports

Provider transport reports are separate, idempotent transitions. They require a
durable provider event key, an opaque external reference, and retained evidence
bytes:

```sh
python3 host/swarm_mail.py record-transport \
  --db /srv/commons-mail/private/mail.sqlite3 \
  --send-key send-buyer-example-proof-001 \
  --transport-event-key provider-event-0001 \
  --event-type PROVIDER_DELIVERY_REPORTED \
  --evidence-ref opaque:provider:delivery-0001 \
  --evidence-file /srv/commons-mail/private/evidence/provider-event-0001.json
```

Allowed report types are `PROVIDER_DELIVERY_REPORTED`,
`SOFT_BOUNCE_REPORTED`, `HARD_BOUNCE_REPORTED`, and `COMPLAINT_REPORTED`.
A hard bounce or complaint suppresses the recipient across all model inboxes
and SKUs. A soft bounce does not. Reusing one transport event key with different
evidence is a collision.

## Ingest and attribute replies

Inbound MTA routing can retain one RFC 822 message plus its envelope evidence
and invoke:

```sh
python3 host/swarm_mail.py ingest \
  --db /srv/commons-mail/private/mail.sqlite3 \
  --inbox-id codex-sales \
  --eml /srv/commons-mail/private/inbound/message.eml \
  --classification QUESTION \
  --mta-envelope-ref opaque:local-mta:inbound-0001 \
  --mta-evidence-file /srv/commons-mail/private/evidence/inbound-0001.json \
  --mta-auth-verdict PASS
```

The caller supplies a requested reply class, not sales attribution. Swarm Mail
derives the SKU and prospect only when `In-Reply-To` or `References` links to a
message that this runtime recorded as MTA-accepted, the sender exactly matches
that outbound recipient, and the trusted local MTA adapter supplies
`--mta-auth-verdict PASS` with retained evidence. Raw message
`Authentication-Results` headers are untrusted and ignored.

Anything else is recorded as unattributed `NEEDS_HUMAN` with no public SKU,
prospect, or send reference. It cannot create commercial attribution or a
suppression by asking to be classified as `OPT_OUT`. An attributed `OPT_OUT`
records the inbound message and the global suppression in one transaction;
idempotent replay repairs a missing suppression before returning. Attributed
replies also produce the canonical production-survival reply receipt.

Inspect private state only through redacted projections:

```sh
python3 host/swarm_mail.py status --db /srv/commons-mail/private/mail.sqlite3
python3 host/swarm_mail.py threads --db /srv/commons-mail/private/mail.sqlite3
```

## Deployment and commercial boundary

Swarm Mail owns identity routing, private state, thread linkage, canonical
dedupe, suppression, reply attribution, and evidence transitions. A local MTA
such as Postfix, OpenSMTPD, or Stalwart owns SMTP delivery, DKIM signing,
inbound MX handling, queues, and bounce generation. That boundary keeps the
core vendor-neutral without pretending deliverability exists before a real
domain and network endpoint.

Inbound email is untrusted data. Models may summarize and classify it, but mail
content never changes price, contract, payment destination, execution scope, or
commercial state by itself. `POSITIVE_SCOPE` stops at the existing acceptance
boundary. The commerce chain remains the source of truth through
`BANK_AVAILABLE`.

Targeted outreach only: verify business relevance, identify the actual sender,
avoid duplicates, include a working opt-out path, honor canonical and runtime
DNC globally, and stop after the bounded follow-up policy in
`revenue/production_survival/crm.md`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
