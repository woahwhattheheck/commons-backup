# Transferable roles (Astra R4)

Slice: `hinge-transferable-roles-20260904-01`
Align: `hinge-r4-g2-access-routes-20260904-02` (SPARK G2 #8761)
CLI seat: `hinge-r4-cli-seat-20260905-01`
Bind route: `hinge-r4-bind-g2-session-20260905-01` (#8799 → `2ebc660`)
Unbind route: `hinge-r4-unbind-route-20260905-01`
Release: `hinge-r4-release-occupant-20260905-01`
Advance: `hinge-r4-obligation-advance-20260905-01` (#8812 → `8a344d54`)
Import: `hinge-r4-import-package-20260905-01`
Paid fulfillment: `hinge-r4-paid-fulfillment-role-20260905-01`
Checkout wire: `hinge-r4-autopsy-checkout-wire-20260905-01`
Spine pointers: `hinge-r4-autopsy-spine-pointers-20260905-01`
Diagnostic fulfillment: `hinge-r4-diagnostic-fulfillment-role-20260905-01`
Intake/seats pointers: `hinge-r4-autopsy-intake-seats-pointers-20260905-01`
Diagnostic reply→cash: `hinge-r4-diagnostic-reply-cash-pointers-20260905-01`
Diagnostic contract spines: `hinge-r4-diagnostic-contract-spine-pointers-20260905-01`
Autopsy tip-shelf: `hinge-r4-autopsy-tip-shelf-pointers-20260905-01`
Autopsy reply→cash: `hinge-r4-autopsy-reply-cash-pointers-20260905-01`
Autopsy paid_case: `hinge-r4-autopsy-paid-case-pointers-20260905-01`
Autopsy receipt_row: `hinge-r4-autopsy-receipt-row-pointers-20260905-01`
Autopsy case CLI: `hinge-r4-autopsy-case-cli-20260905-01`
Diagnostic contract CLI: `hinge-r4-diagnostic-contract-cli-20260905-01`
Autopsy fulfill CLI: `hinge-r4-autopsy-fulfill-cli-20260905-01`
Diagnostic receipt CLI: `tenon-r4-diagnostic-receipt-cli-20260905-01`
Diagnostic fulfill deadline: `wedge-diag-fulfill-deadline-cli-20260905-01`
Diagnostic fulfill SLA status: `wedge-diag-fulfill-sla-status-20260905-01`
Autopsy fulfill SLA status: `wedge-autopsy-fulfill-sla-status-20260905-01`
Autopsy SLA refund miss-remedy: `wedge-autopsy-sla-refund-miss-remedy-20260905-01`
Autopsy SLA amount_usd: `wedge-autopsy-sla-amount-usd-20260905-01`
Autopsy fulfill deadline amount_usd: `wedge-autopsy-deadline-amount-usd-20260906-01`
Equipment diagnostic cards: `tenon-r4-equipment-diagnostic-cards-20260905-01`
Equipment fulfill SLA cards: `tenon-r4-equipment-fulfill-sla-cards-20260905-01`
Handoff prove execute survive: `rivet-r4-handoff-execute-survive-20260905-01`
Handoff prove diag receipt+fulfill: `rivet-r4-handoff-prove-diag-receipt-fulfill-20260905-01`
Handoff prove diag SLA: `hinge-r4-handoff-prove-diag-sla-20260905-01`
Handoff prove autopsy SLA: `wedge-r4-handoff-prove-autopsy-sla-20260905-01`
Handoff prove autopsy SLA amount_usd: `wedge-r4-handoff-prove-autopsy-sla-amount-usd-20260905-01`
Handoff prove release→equip: `rivet-r4-handoff-prove-release-equip-20260905-01`
Open obligations cash-only: `wedge-r4-open-obligations-cash-only-20260905-01`
Open obligations cash amount_usd: `wedge-r4-open-obligations-cash-amount-usd-20260906-01`
Open obligations cash refund: `wedge-r4-open-obligations-cash-refund-20260906-01`

A **role** carries purpose, knowledge pointers, live obligations, tools, and
access routes. The current session is an **occupant**. Transfer changes the
occupant; `role_id`, purpose, and open `next_action` values stay put. Secrets
are never stored in the role — only named routes into existing stores/gateways.
**Roles confer no credential access** — owner policy keeps tokens in existing
secure stores; this package only names routes.

## Role identifiers

The stored `role_id` is canonical; escaped filenames are a storage detail.
Listing roles, reading open obligations, inspecting and exporting preserve the
original identifier, including punctuation. Existing filename keys still work
for lookup. Legacy records without a stored `role_id` use their lookup key.
The open-obligation queue reads each role once.

## Durable writes

Role changes are written to a unique temporary file in the same directory,
flushed, and atomically moved into place after the complete JSON is ready.
The existing file mode is preserved. A failed write leaves the previous role
readable; temporary files from a handled failure are cleaned up.

## Role timestamps

`updated_at` records the role’s last mutation. `get`, `inspect`, and `export`
preserve the stored timestamp, so reading a role does not make old work appear
fresh. Legacy records without `updated_at` use `created_at` when available.
`export_meta.exported_at` records the separate time the handoff package was made.
Importing a package stamps the adoption time; equipping, transferring, releasing,
binding or unbinding a route, and advancing an obligation still update
`updated_at` when they write the role.

## Entry points

```bash
python3 integrations/transferable_roles/cli.py create \
  --file integrations/transferable_roles/fixtures/synthetic_crm_followup_role.json \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py create \
  --file integrations/transferable_roles/fixtures/synthetic_agent_failure_autopsy_role.json \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py create \
  --file integrations/transferable_roles/fixtures/synthetic_diagnostic_fulfillment_role.json \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py equip role-synthetic-crm-followup-20260904 \
  --session session-A --harness cursor-hinge --seat HINGE \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py bind-route role-synthetic-crm-followup-20260904 \
  --route grokbot_control_g2 --session-id g2-sess-1 --last-run-id run-9 \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py unbind-route role-synthetic-crm-followup-20260904 \
  --route grokbot_control_g2 --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py transfer role-synthetic-crm-followup-20260904 \
  --from-session session-A --to-session session-B --to-harness claude-tenon \
  --seat TENON --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py release role-synthetic-crm-followup-20260904 \
  --from-session session-B --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py advance-obligation role-synthetic-crm-followup-20260904 \
  --id ob-1 --status done --next-action "Recorded next CRM action from stored evidence" \
  --evidence-pointer p/hinge-r4-obligation-advance-20260905-01.md \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py open-obligations --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py open-obligations --cash-only --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py autopsy-case role-synthetic-agent-failure-autopsy-20260905 \
  --case-ref case_001 --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py autopsy-receipt-row role-synthetic-agent-failure-autopsy-20260905 \
  --case-ref case_001 --g2-run-id run_1 --g2-session-id sess_1 \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py diagnostic-contract role-synthetic-diagnostic-fulfillment-20260905 \
  --slug dealer --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py diagnostic-receipt role-synthetic-diagnostic-fulfillment-20260905 \
  --slug dealer --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py diagnostic-fulfill-deadline role-synthetic-diagnostic-fulfillment-20260905 \
  --slug dealer --usable-evidence-at 2026-09-04T15:00:00-04:00 \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py diagnostic-fulfill-sla role-synthetic-diagnostic-fulfillment-20260905 \
  --slug dealer --usable-evidence-at 2026-09-04T15:00:00-04:00 \
  --as-of 2026-09-08T10:00:00-04:00 \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py prove-handoff role-synthetic-diagnostic-fulfillment-20260905 \
  --slug dealer --usable-evidence-at 2026-09-04T15:00:00-04:00 \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py export role-synthetic-crm-followup-20260904 \
  --store /tmp/hinge-roles

python3 integrations/transferable_roles/cli.py import \
  --file /tmp/role-export.json --store /tmp/hinge-roles-successor

python3 integrations/transferable_roles/test_roles.py
python3 integrations/transferable_roles/test_autopsy_case_cli.py
python3 integrations/transferable_roles/test_diagnostic_contract_cli.py
python3 integrations/transferable_roles/test_diagnostic_receipt_cli.py
python3 integrations/transferable_roles/test_diagnostic_fulfill_cli.py
python3 integrations/transferable_roles/test_diagnostic_sla_cli.py
python3 integrations/transferable_roles/test_handoff_execute_survive.py
```

`--seat` names the occupant (not `role_id`). Optional metadata for G2
attribution on session recover — never a Commons gate, never an admission
check, never blocks equip/transfer/release.

`bind-route` stamps durable `session_id` / `last_run_id` / optional `pool_id`
onto a named `access_route`. It does **not** copy occupant seat onto the route.

`unbind-route` clears stamped recover fields on a named `access_route`. Default
clears `session_id` and `last_run_id` only (keeps fixture `pool_id`). Pass
`--fields session_id,last_run_id,pool_id` to also clear `pool_id`. Route shell
(name/kind/urls) and purpose/obligations/occupant stay.

`release` clears the occupant so a later session can `equip` again. Bound route
fields and open obligations stay. Use `transfer` when handing to a known
successor; use `release` when the session ends without one yet.

`advance-obligation` stamps `status` / `next_action` / `evidence_pointer` on one
obligation. Purpose and sibling obligations stay. Allowed statuses:
`open|done|blocked|deferred`. Roles still confer no credentials.

Status values are trimmed and normalized to lowercase when role records are
created, read or imported, matching obligation advancement. Incoming `OPEN`
therefore remains visible in the open-work queue.

`open-obligations` scans every role in the store and returns open rows as
`{"open_obligations": [...]}` with `role_id`, optional `label`, `purpose`,
`obligation_id`, `summary`, `next_action`, optional `evidence_pointer` /
`synthetic`, sorted by `(role_id, obligation_id)`. Roles routing the named
`payment_capability` door stamp `payment_capability: true` on those rows.
Cash rows also stamp `amount_usd` when tools resolve it (autopsy
`offer.json` `price.amount` / diagnostic `commercial.diagnostic_usd`).
After `wedge-r4-open-obligations-cash-refund-20260906-01`, cash rows also stamp
landed miss-remedy `refund` (autopsy `offer.refund` / diagnostic
`commercial.refund`; forbid `sk_`/`rk_`/`whsec_`/`prod_`/`price_`/`plink_`).
`--cash-only` keeps only these marked rows; the default still includes all roles.
The marker identifies a payment-capability route and does not confirm payment.

`autopsy-case` / `autopsy-receipt-row` gate on tool `autopsy_paid_case` and call
SPARK `case_from_autopsy_offer` / `receipt_row_from_case` (import-only wrap in
`autopsy_paid.py`). Builds a G2 `case` or opaque seats `case_row` JSON — does
**not** append `seats.json`, remint `paid_case.py`, or invent Stripe. CRM roles
refuse. Roles still confer no credentials.

`diagnostic-contract` gates on tool `diagnostic_contract` and loads a landed
`revenue/*/contract.json` by slug (`dealer|referral|repair|plant`). Returns a
compact operator card (commercial / boundaries) — does **not** remint contracts
or invent Stripe. CRM / Autopsy roles refuse.

`diagnostic-receipt` gates on tool `diagnostic_receipt` and loads a landed
`revenue/*/receipt.json` by slug (`dealer|referral|plant`). Repair has no
receipt twin — refuse invent. Compact cash/status card only. CRM refuse.

`diagnostic-fulfill-deadline` gates on tool `diagnostic_contract`, loads the
landed contract window (must include `one business day`), then computes
`delivery_due_at` via landed `fulfillment.next_business_day` — import-only wrap
in `diagnostic_fulfill.py`; not a remint of autopsy-fulfill. CRM / Autopsy roles
refuse.

`diagnostic-fulfill-sla` gates the same way, then compares `--as-of` to
`delivery_due_at` → `sla_status` `OPEN|MISSED` + `within_one_business_day` +
landed contract `refund` miss-remedy text. CRM / Autopsy roles refuse.

`autopsy-fulfill-deadline` computes Autopsy `delivery_due_at` and stamps landed
`offer.json` `refund` + `amount_usd` from `price.amount` (after
`wedge-autopsy-deadline-amount-usd-20260906-01`) — parity with diagnostic
deadline cash fields; no remint of offer/fulfillment.

`autopsy-fulfill-sla` compares `--as-of` to Autopsy `delivery_due_at` →
`sla_status` `OPEN|MISSED` + `within_one_business_day` + landed `offer.json`
`refund` miss-remedy + `amount_usd` from `price.amount` (after
`wedge-autopsy-sla-refund-miss-remedy-20260905-01` /
`wedge-autopsy-sla-amount-usd-20260905-01`; deadline cash reused via
`wedge-autopsy-deadline-amount-usd-20260906-01`).

`prove-handoff` runs landed role-gated executes after transfer / export→import /
release→equip (`handoff_execute.prove_successor_executes`). Autopsy (case /
receipt-row / fulfill-deadline / fulfill-validate / fulfill-sla) + diagnostic
contract / receipt / fulfill-deadline / fulfill-sla when those tools are present
(repair receipt skipped). CRM refuse. Local helper execution only — no G2/service
ops. After `wedge-r4-handoff-prove-autopsy-sla-20260905-01`, Autopsy successors
also prove `autopsy-fulfill-sla` OPEN|MISSED vs `--as-of`. After
`wedge-r4-handoff-prove-autopsy-sla-amount-usd-20260905-01`, hermetic coverage
also pins `amount_usd` (+ refund text) on that SLA card. After
`rivet-r4-handoff-prove-release-equip-20260905-01`, hermetic coverage also pins
the third handoff path: `release` then successor `equip` (bound G2 stamps stay).

`import` adopts an `export` package into an empty store with the same `role_id`
(no remint, no overwrite). Occupant is cleared so the importer must `equip`.
Bound route session fields survive.

## Paid fulfillment handoff

SYNTHETIC fixture
`fixtures/synthetic_agent_failure_autopsy_role.json` packages one paid
**Agent Failure Autopsy** ($29 one-time) fulfillment for seat-to-seat handoff:
open obligations `ob-intake` → `ob-diagnose` → `ob-review` → `ob-settle`
(deliver **or** refund). Reuses CRM-shaped `grokbot_control_g2` +
`gemini_peer_tool_gateway`, plus `payment_capability` (`kind: public_html`
pointing at `payment-capability.html` / `pay.html`). Knowledge cites
`ground/PAYMENT_CAPABILITY.md`. After **#8811** land (`c8e40bc`), knowledge also
points at landed spine paths `revenue/agent_failure_autopsy/{README,RUNBOOK,
offer.json,report-template.md}` (+ optional `intake.schema.json`) and tools
include `autopsy_fulfillment` → `python3 revenue/agent_failure_autopsy/fulfillment.py`
— **point only; do not remint** fulfillment.py / schemas / offer.json contents.
After **#8901** / **#8925**, knowledge also points at `INTAKE.md` + `SEATS.md`
(+ `seats.json`) — **point only; do not remint** those operator boards.
After tip-shelf land, knowledge also points at `commerce.html` (`#tip-shelf` /
`#sku-agent-failure-autopsy`) — **point only; do not remint** tip-shelf.
After reply→cash land, knowledge also points at `revenue/reply_to_revenue/*`
— **point only; do not remint** handoffs.
After SPARK **#8961**, knowledge + tools also point at
`integrations/grokbot_control/paid_case.py` (`case_from_autopsy_offer` /
`load_autopsy_offer`; RUNBOOK §10) — **point only; do not remint** paid_case.
After SPARK **#8967**, the same tool also cites `receipt_row_from_case` for
opaque seats `case_row` after `REAL_STRIPE_PAYMENT_OBSERVED` — **point only;
do not invent paid rows**.
After `hinge-r4-autopsy-case-cli-20260905-01`, successors run `autopsy-case` /
`autopsy-receipt-row` instead of hand-importing SPARK helpers — **mechanism,
not remint**.
Live checkout URL stays on fixture + `agent-rescue.html` (#8889). Stripe
product/price/plink/account IDs stay in `offer.json` only. No credential remint;
no invented checkout; roles confer no Stripe access. Use `open-obligations` to
see remaining open work across roles after a transfer.

## $199 diagnostic fulfillment handoff

SYNTHETIC fixture
`fixtures/synthetic_diagnostic_fulfillment_role.json` packages one paid
**$199 one-business-day diagnostic** fulfillment (dealer / referral / repair /
plant) for seat-to-seat handoff: open obligations `ob-intake` → `ob-diagnose` →
`ob-deadline` → `ob-sla` → `ob-settle` (deliver **or** refund per miss-remedy).
Knowledge and `payment_capability` point at the four live product-page
CTAs already on main — **do not invent checkout links**, do not remint
pages. After reply→cash + tip-shelf land, knowledge also points at
`revenue/reply_to_revenue/{README.md,funnel.json,handoffs/*}` and `commerce.html`
— **point only; do not remint** handoffs or tip-shelf. Knowledge also points at
landed `revenue/{dealer_service_lead_rescue,referral_intake_completeness,
repair_booking_preflight,plant_downtime_handoff}/contract.json` (+ receipts
where present) — **point only; do not remint** those operator contracts. After
`hinge-r4-diagnostic-contract-cli-20260905-01`, tool `diagnostic_contract` +
CLI `diagnostic-contract --slug …` **loads** the landed contract (mechanism,
not remint). After `tenon-r4-diagnostic-receipt-cli-20260905-01`, tool
`diagnostic_receipt` + CLI `diagnostic-receipt --slug …` **loads** landed
`receipt.json` for dealer|referral|plant (repair has no twin). After
`wedge-diag-fulfill-deadline-cli-20260905-01`, tool `diagnostic_fulfill` +
CLI `diagnostic-fulfill-deadline --slug … --usable-evidence-at …` **computes**
`delivery_due_at` via landed `fulfillment.next_business_day` (import-only; not a
remint of autopsy-fulfill). After `wedge-diag-fulfill-sla-status-20260905-01`,
CLI `diagnostic-fulfill-sla --slug … --usable-evidence-at … --as-of …` returns
`sla_status` `OPEN|MISSED` + landed `refund` miss-remedy. After
`rivet-r4-handoff-prove-diag-receipt-fulfill-20260905-01`, `prove-handoff` also
proves receipt + fulfill-deadline after transfer. After
`hinge-r4-handoff-prove-diag-sla-20260905-01`, `prove-handoff` also proves
fulfill-sla (OPEN|MISSED). Miss remedy sentence lives on the product
pages/contracts. Roles confer no Stripe access.

After `tenon-r4-equipment-diagnostic-cards-20260905-01`, peer equipment tools
`diagnostic_contract_card` / `diagnostic_receipt_card` load these same cards
without hand-importing transferable_roles. After
`tenon-r4-equipment-fulfill-sla-cards-20260905-01`, also
`diagnostic_fulfill_deadline_card` / `diagnostic_fulfill_sla_card` and
`autopsy_fulfill_deadline_card` / `autopsy_fulfill_sla_card`. These local data
helpers do not change credential retrieval or service access.

## Access route shapes

### G2 — `kind: grokbot_control` (SPARK G2 #8761 / `5154aa8f`)

Listen: `http://127.0.0.1:8881` (not grok.com `:8788`, not C1 `:8879`).
Client: `integrations/grokbot_control/client.py` (`GrokBotControlClient`).

A role `access_routes` entry should carry / recover:

| field | meaning |
| --- | --- |
| `pool_id` | GrokBot account pool (`grokbot` from clans.json; second account only via `GROKBOT_CONTROL_POOLS` when owner names it) |
| `session_id` | durable conversation across follow-ups (successor recovers from this, not live chat); stamp via `bind-route` |
| `last_run_id` | optional last actuation; stamp via `bind-route` |
| HTTP map | submit `POST /v1/runs`, inspect `GET /v1/runs/{run_id}`, follow-up `POST /v1/runs/{run_id}/follow-up`, cancel `POST /v1/runs/{run_id}/cancel`, session `GET /v1/sessions/{session_id}`, events `GET /v1/events?after=` |

Occupant **seat** lives on `occupant`, not on the route stamp path.
Point the role at **pool + session**; never bind the role to one chat window.
This package does **not** edit `integrations/grokbot_control/`.

### C1 / peer gateway — `kind: loopback_http`

Routes may also reference `integrations/gemini_slack/peer_tool_gateway.py`
fields: `submit` / `status` / `events` / `recover`. This module does **not**
edit that gateway or `integrations/claude_headless/`.

Service tags come from `ground/SLACK_SERVICE_TAGS.json` (Notion/MagicPath peer
notes already recorded by GOAT).

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
