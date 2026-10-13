---
name: routescout
description: Make one approval-gated CALL-E call to a first-party published procurement, vendor-registration, supplier-support, or partner-program business line to discover the permitted official follow-up route for an already-identified process inquiry. Never market, qualify leads, negotiate, or bypass procurement.
license: MIT
---

# RouteScout

RouteScout is a routing-only CALL-E Agent Skill. It is for the awkward gap where an operator already has a legitimate procurement/vendor-process inquiry, but the organization's permitted contact channel is unclear.

It does **not** ask the callee to consider an offer. It asks only which department/role and which official or voluntarily provided **business** channel should receive the existing inquiry.

## Use only when

- the inquiry kind is `procurement_process`, `vendor_registration`, `existing_supplier_support`, or `partner_program_support`;
- the operator has independently verified the exact E.164 number on a first-party HTTPS page;
- the operator reviews the exact preview and confirmation token; and
- one disclosed phone call is appropriate under the controlling process rules.

Do not use for marketing, lead generation, surveys, political outreach, personal numbers, emergency calls, collections, pricing, negotiation, or attempts to get around a portal/contact restriction.

## Workflow

1. Fill the strict inquiry JSON from a first-party published route.
2. Run `python3 scripts/routescout.py preview inquiry.json`.
3. Review the complete task, masked destination, source URL, one-call side effect, and authority ceiling.
4. If approved, set `CALLE_API_KEY` locally and run the exact preview token with `--confirm-call`.
5. Never blindly retry an ambiguous call. The request uses a deterministic idempotency key; use `resume` with the returned call id when available.
6. Reconcile the terminal result. `task_completed=true` does not prove a route. For offline retained JSON, `provider_binding.verified=true` proves only internal identity-field consistency against the inquiry; it does not authenticate that the local file came from CALL-E.
7. Treat `ROUTE_FOUND` only as evidence of a permitted routing channel. It is never acceptance, procurement permission, or authority to send the follow-up.

## Result states

- `ROUTE_FOUND`: organization + consent + routing answer + permitted business channel + verbatim route proven.
- `DO_NOT_CONTACT`: explicit DNC or declined follow-up.
- `NO_ROUTE`: call completed but no permitted business route proven.
- `HUMAN_REQUIRED`: provider or structured-result failure.

## Side effects and credentials

`preview` and `reconcile` are no-network. `run` can place **one real outbound phone call** and may incur CALL-E charges. The API key is read from `CALLE_API_KEY` and the script sends it only to `https://api.heycall-e.com`. Its HTTP opener rejects every redirect before a second request can be constructed or issued, preventing bearer credentials or request bodies from being forwarded to redirect targets.

There is no scheduler and no automatic retry. Cancel safely by withholding the exact confirmation token. After dispatch, use the provider call id for status/recovery rather than creating a changed inquiry.

## Files

- `scripts/routescout.py` — preview, one-call execution, GET-only resume, and reconciliation.
- `scripts/self_test.py` — standard-library offline contract tests.
- `assets/sample_inquiry.json` and `assets/sample_terminal.json` — fictional/no-call fixtures.
