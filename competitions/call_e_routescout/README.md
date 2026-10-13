# RouteScout — CALL-E procurement/vendor-process route discovery

RouteScout places **one operator-approved CALL-E call** to a first-party published business number and asks one narrow question: *what official business route is permitted for this already-identified procurement/vendor-process inquiry?*

It is intentionally not a sales dialer. The input contract only accepts:

- `procurement_process`
- `vendor_registration`
- `existing_supplier_support`
- `partner_program_support`

Marketing, lead generation, pricing, negotiation, procurement bypass, private-contact harvesting, and automatic retries are out of scope and mechanically or prompt-level blocked.

## Why

A real opportunity can stall even when the underlying work is strong: an RFP points to a generic procurement desk, a vendor-registration route is unclear, a partner program has a switchboard but no usable intake channel, or a supplier-support question bounced through a generic inbox. RouteScout converts one **published organizational phone route** into a structured, evidence-preserving routing receipt without pretending the call itself authorizes follow-up.

A `ROUTE_FOUND` receipt means only that the callee explicitly supplied or permitted a business follow-up route. It does **not** mean the organization accepted a proposal, invited a sale, waived procurement rules, or owes anything.

## Modes

### Preview — zero network, zero call

```bash
python3 routescout.py preview fixtures/sample_inquiry.json
```

Preview prints:

- the exact task text;
- the masked destination;
- SHA-256 of the canonical inquiry;
- a deterministic `ROUTESCOUT-...` confirmation token;
- the exact CALL-E idempotency key;
- the closed recipient result schema; and
- the fixed authority ceiling.

Any change to the inquiry changes both the approval token and idempotency key.

### Offline reconcile — zero network

```bash
python3 routescout.py reconcile fixtures/sample_inquiry.json fixtures/sample_terminal.json
```

Possible outputs:

- `ROUTE_FOUND` — correct organization + consent + routing answer + permitted business channel + verbatim route;
- `DO_NOT_CONTACT` — explicit DNC or declined follow-up;
- `NO_ROUTE` — call completed but no permitted business route was proven;
- `HUMAN_REQUIRED` — provider failure/non-terminal/unusable structured result.

A provider `task_completed=true` is never enough by itself.

`provider_binding.verified=true` in an **offline** receipt means only that the caller-supplied retained JSON has internally consistent call/inquiry identity fields matching the exact inquiry being reconciled. It does **not** authenticate that the local JSON was retrieved from CALL-E; a local file can be forged. Provider-origin evidence must come from a live fetch over the guarded CALL-E transport or from separately authenticated provider evidence.

### Live — one real CALL-E phone call

1. Verify `source_url` is the organization's first-party page that published the exact business number.
2. Review the complete preview.
3. Set `CALLE_API_KEY` locally. Never commit it.
4. Run with the exact preview token:

```bash
export CALLE_API_KEY='...'
python3 routescout.py run fixtures/real_inquiry.json --confirm-call ROUTESCOUT-EXACTTOKENFROMPREVIEW
```

The code sends credentials only to `https://api.heycall-e.com`, creates exactly one recipient, and sends a deterministic `Idempotency-Key` bound to the canonical inquiry. The HTTP transport refuses every redirect before urllib can construct or issue a redirected request, so the bearer credential and request body are never forwarded to a redirect target. It then polls the returned call id.

If creation or polling becomes ambiguous, **do not change the inquiry and retry**. Use the same exact inquiry/idempotency key or provider call id to recover state. The `resume` command performs GET/poll only and cannot create a new call:

```bash
python3 routescout.py resume fixtures/real_inquiry.json call_...
```

## Input contract

Every key is required; unknown and duplicate JSON keys fail closed.

```json
{
  "schema_version": 1,
  "inquiry_id": "route-001",
  "caller_org": "Example Integrations",
  "target_org": "Example Manufacturing",
  "phone_e164": "+15551234567",
  "region": "US",
  "locale": "en-US",
  "source_url": "https://example.com/procurement",
  "inquiry_kind": "procurement_process",
  "inquiry_reference": "RFP-123 vendor question",
  "inquiry_topic": "Official process for submitting a clarification question",
  "requested_function": "Procurement or solicitation Q&A desk",
  "operator_approved": true,
  "published_business_route": true
}
```

`source_url` must be HTTPS and cannot contain credentials, query parameters, or fragments. Prompt-bound strings are single-line strict data. `operator_approved` and `published_business_route` must be JSON booleans `true` — integers such as `1` are rejected.

## What the call may ask

RouteScout may ask only which department/role and which official or voluntarily supplied **business** channel should receive the existing inquiry.

It may not:

- market, qualify a lead, or pitch;
- ask for pricing or buying decisions;
- negotiate or accept terms;
- claim procurement eligibility;
- bypass a portal, blackout period, or solicitation contact rule;
- ask for personal/mobile/private contact details;
- open/close/change a case or account;
- send the discovered follow-up;
- make medical, legal, financial, or emergency decisions.

The callee can say “do not contact us”; that dominates all other fields and returns `DO_NOT_CONTACT`.

## Local verification

```bash
python3 -m unittest -v test_contracts.py test_results_provider.py
python3 -O -m unittest -v test_contracts.py test_results_provider.py
python3 -m py_compile routescout.py routescout_core/*.py test_support.py test_contracts.py test_results_provider.py
```

The focused suite covers strict JSON, bool/int aliasing, prompt injection, source URL token leakage, one-recipient creation, exact idempotency, official-origin credential handling, fail-closed redirect containment, DNC/declined dominance, route-proof requirements, no-call fences, and result fail-closed behavior.

## Competition packaging

This source carrier is for the CALL-E Global Call for AI Agents competition. `SUBMISSION.md` separates completed software from external submission facts that must not be invented. `upstream/skills/routescout/` is an upstream-ready Agent Skill contribution for `CALLE-AI/awesome-phone-call-agents`.

No repository fixture is evidence that a real CALL-E call occurred.
