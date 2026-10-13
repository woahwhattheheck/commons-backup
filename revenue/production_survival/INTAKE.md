# Intake and fulfillment — who does what, from checkout to delivered proof

> Status 2026-09-05 (~08:10 ET, SPARK edit on SEXTANT base): `agent-rescue.html` sells the $29
> Agent Failure Autopsy (ASTRA #8889). Autopsy operators: `revenue/agent_failure_autopsy/INTAKE.md`
> + `RUNBOOK.md`. **This file governs only the $2,500 Same-Day Agent Survival Proof.**
> Its Payment Link may still be live in Stripe, but it is **not** sold on `agent-rescue.html`.
> Store-mailbox intake owner for either product until a named seat takes the Autopsy watch row:
> SEXTANT, backup WELD (see Autopsy INTAKE for product-specific takeover).

Operational runbook for the Same-Day Agent Survival Proof (`offer.json`, `acceptance_contract.md`).
It changes no price, term, or acceptance rule. It names the operator for each step and states two
clocks the contract leaves implicit. Originally written 2026-09-05 by SEXTANT (Fable 5.1, owner PC)
for the first X experiment; roles are transferable and the current holder is written here, not assumed.
Page-route truth corrected 2026-09-05 by SPARK (`spark-autopsy-intake-runbook-20260905-01`) so this
file no longer narrates `agent-rescue.html` as the $2,500 checkout surface. Autopsy SKU and
`agent-rescue.html` retired 2026-09-17 (owner directive); the routing warnings below stay — the
page is gone, so Survival Proof buyers have nowhere to land there at all.

## Owners, as of 2026-09-05

| step | current holder | backup | how |
| --- | --- | --- | --- |
| intake watch (store mailbox `tokenjunkielabs@gmail.com`) | SEXTANT | WELD (cloud, same mailbox through its connector) | read buyer mail and available Stripe account mail at least hourly while the ad runs; payment-notification delivery remains unverified (see step 3 below) |
| terms (the written Given/When/Then test) | SEXTANT | WELD | `acceptance.py issue-terms`, sent from the store mailbox as a reply to the buyer |
| written acceptance record | SEXTANT | WELD | `acceptance.py record-acceptance` on the buyer's reply, then `invoice-gate` |
| capture of the authorized $2,500 | SURETY (Stripe connector) or Bryce | Bryce | Stripe dashboard, only after `invoice-gate` passes |
| the proof, inside the agreed business day | SEXTANT | TENON (owner PC, same runner) | `survival_canary.py` pattern + `proof-v1.schema.json`, landed under `proofs/` on main, receipt per `receipt.schema.json` |
| link reactivation after delivery or cancellation | SURETY or Bryce | — | the link is capped at one completed session; Stripe deactivates it after the first |
| CRM row (`crm.md` stages) | LEDGER | — | existing Airtable pipeline; this file does not write it |

Nothing here contacts a buyer or charges anyone. A seat that takes a row above posts the takeover
in the hub with its seat name; silence does not transfer a row.

## What the buyer does, measured 2026-09-05 (page routes)

- **Not on `agent-rescue.html`.** That page carried the $29 Autopsy checkout until the SKU retired
  2026-09-17. Do not send Survival Proof buyers there for the $2,500 Buy button — the page no longer exists.
- **Survival Proof entry.** Buyer starts with one non-confidential failure sentence
  (`My agent should…, but in production it…`). Routes that still apply to this product:
  - the live Stripe Payment Link for the $2,500 authorization (dashboard / SURETY; not pasted here);
  - email to the store mailbox (`tokenjunkielabs@gmail.com`) with the failure sentence;
  - marketplace listings per `marketplaces.md` (Upwork / Contra / Fiverr) when those channels are active.
- `offer.json` records `canonical_page: ""` and
  `canonical_page_state: NO_DEDICATED_PUBLIC_HTML` (SPARK #8904). Its `public_entry_routes`
  identify the store mailbox, marketplace listings, and existing Stripe Payment Link.
  Canonical machine-readable terms remain in `offer.json`; this INTAKE names the operators.

A completed Payment Link checkout (when used) still carries email, name, the required failure
sentence field, and optional public evidence link — so the mailbox operator does not have to
ask for the sentence again.

## What one completed checkout produces

1. Stripe creates the customer and places a **manual-capture authorization for USD 2,500**.
   Nothing is captured. The buyer receives no receipt until capture.
2. The Payment Link **deactivates** (`completed_sessions_limit: 1`). Further Buy attempts on that
   link land on Stripe's "link is no longer active" page. The store-mailbox `mailto:` route keeps
   working. That is the one delivery slot, enforced by Stripe, not by us.
3. Stripe records the session in the dashboard as *Uncaptured*. The store mailbox receives
   Stripe's account mail today (verified historically: 15 Stripe messages in a 21-day window);
   whether an uncaptured authorization sends a mail has **not been observed on this account**,
   because no session has ever completed. Until SURETY confirms the notification setting in the
   dashboard, the intake owner reads both the mailbox and asks SURETY for the dashboard state
   once a day while the experiment runs.
4. The intake owner replies from the store mailbox within one business day with the terms
   (step 3 of `acceptance_contract.md`): the Given/When/Then test, the public-safe environment,
   the exact America/New_York window, the exclusions, the fixed price, and the refund choice.

## Two clocks the contract does not state

- **Capture clock.** A card authorization expires after seven days if not captured (Stripe).
  Terms go out within one business day of checkout; the buyer's written acceptance is needed by
  day five; capture by day six. If there is no acceptance by day six, the authorization is
  cancelled (no charge), the link is reactivated, and the buyer may check out again later.
- **Delivery clock.** Starts only at the agreed `window_start` after confirmed capture
  (contract step 5). One business day is the delivery term. It is not a claim that the buyer's
  production agent runs reliably for a day.

## The reply the intake owner sends (terms)

Subject: `Same-Day Agent Survival Proof — your test, in writing`

> You wrote: "<the failure sentence, verbatim>".
>
> Here is the test we will deliver. Given <public or synthetic input>, when <the named failure>
> is forced, the delivered proof <observable recovery outcome> and its receipt shows <named
> fields>. Environment: <public-safe runtime>. Window: <start> to <end>, America/New_York
> (one business day). Price: USD 2,500, authorized at checkout, captured only after you accept
> these terms in writing. If the test has not passed by the end of the window: refund of the
> captured amount, or one free next-business-day repair attempt, your choice in writing.
> Excluded: credentials, private data, PII/PHI, authentication, billing, production migration,
> ongoing hosting or SLA, model-file work.
>
> Reply "accepted" to these exact terms and the window starts as written.

The reply's bytes are the `--terms` file for `acceptance.py issue-terms`; the buyer's reply is the
`--written-acceptance` file for `record-acceptance`; `invoice-gate` must pass before anyone
captures. All three keep private evidence under the evidence root and write only public-safe
receipts.

## What the buyer receives

Inside the window: a no-login proof URL on provider-controlled infrastructure, the visible
failure or stop path, the rollback or reset path, the durable receipt (`receipt.schema.json`;
`example_receipt.json` is the shape), and the written keep/change/stop handoff. The receipt and
proof land under `revenue/production_survival/proofs/` on main with a commit-pinned URL.

## Open items, named

- SURETY: confirm the account's payment-notification email setting in the Stripe dashboard and
  post the result; until then step 3 above is a daily manual read.
- CLEAT one-slot copy on `agent-rescue.html` was for the old $2,500 link UX; Autopsy page copy
  is owned elsewhere. Do not re-add Survival Proof Buy UX onto Autopsy’s page from this file.
- No completed Survival Proof session, no failure-sentence mail for that product, and no capture
  exist as of this file's date.

## Live cash

Verified Commons product pages only — no invented Stripe links. Survival Proof intake is not Autopsy checkout.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

Survival $2,500: mailbox / marketplaces / SURETY — see README. Cite husk-survival-readme-live-cash-20260909-01 — do not remint. Claim `husk-survival-intake-live-cash-20260909-01`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
