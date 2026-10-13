# Fleetline customer request portal

This is an additive customer-request rail for the existing Fleetline operator workspace. It deliberately **does not** expose the operator desk and **does not** turn a request into a reservation by itself.

## Run locally

From `revenue/hive/rental-operations/`:

```sh
python customer_portal.py --db /path/to/private/fleet.sqlite serve --port 8087
```

Open `http://127.0.0.1:8087`. The portal binds only to loopback. A future hosted deployment needs an explicit HTTPS/auth/privacy deployment design; this delivery does not claim one.

## Customer contract

The browser can query date-bounded availability and current quote components. The API intentionally omits reservation IDs, conflicting-record details, operator notes, the full schedule, audit history, and every other customer's information. A submission creates only a `pending` request in additive tables. It does not insert a Fleetline reservation, hold inventory, send a message, or record payment.

The browser creates a high-entropy status capability and sends it with the request and any exact retry. Fleetline stores only its SHA-256 digest. Status lookup is a POST body rather than a URL token, wrong request/token pairs return the same generic 404, request paths are not logged, and responses are `no-store` with same-origin browser guardrails.

A stable `request_key` makes an exact retry return the same pending request. Reusing that key for changed content fails closed. The stored idempotency receipt contains the token digest, never the plaintext capability.

### Lost responses and page reloads

Before sending, the page saves the exact request fields, request key and private
status capability in this browser's local storage. If that write fails, no
request is sent. Only one submission can be in flight from this page.

After a lost response or a reload, **Retry saved request** sends those same saved
bytes through the existing server retry operation. It works without filling the
form or checking availability again. Editing the form does not alter the saved
request; recover it before submitting different details. An explicit server
input/conflict refusal clears that rejected attempt so the form can be corrected;
network, malformed-response and server failures retain it for recovery.

After the server identifies the request, the browser saves its ID, private
capability, request key and a fingerprint of the submitted fields, then removes
the full saved form. Repeating the unchanged latest submission reuses that key
and capability. **Refresh my last request** reads the current status, including
an operator decision; an exact submission retry returns the original receipt.
Older saved ID/capability records remain usable for status lookup.

Local storage is private browser data, not encrypted storage or a server backup.
Keep it while a request needs recovery. Clearing it, changing browsers or using
a different origin loses that local recovery information. The one-in-flight
guard coordinates this page, not independent browsers. No retry is sent merely
by opening or reloading the page.

## Operator contract

List pending requests:

```sh
python customer_portal.py --db /path/to/private/fleet.sqlite pending
```

Accept one:

```sh
python customer_portal.py --db /path/to/private/fleet.sqlite approve REQUEST_ID
```

Reject one without creating a reservation:

```sh
python customer_portal.py --db /path/to/private/fleet.sqlite reject REQUEST_ID --note "Requested dates unavailable"
```

Approval is the only bridge into the canonical Fleetline reservation table. Approval runs in one `BEGIN IMMEDIATE` transaction: it rechecks availability and every quoted commercial component, then invokes Fleetline's existing `Store.save_reservation()` business logic and writes the same deterministic operation receipt shape used by `Store.command()`. If the asset's rate, unit, minimum, booking fee, security deposit, or resulting amount changed, the whole transaction rolls back and the request stays pending for a new quote. If another reservation took the interval, approval is blocked. Deterministic operation and reservation IDs make an ambiguous retry return the same accepted request instead of creating a second booking.

Two customers may submit pending requests for the same currently-open interval because a request is not a hold. Only the first accepted request can reserve the interval; Fleetline's existing transactional collision check rejects the later approval.

## Boundaries

This rail uses the same private SQLite workspace as the operator desk and only synthetic data in tests. It does not deploy publicly, contact a customer, send email/SMS, charge a card, integrate a calendar/provider, infer taxes or legal terms, or perform owner-device work. Quoted taxes/delivery remain unconfigured exactly as in Fleetline's current commercial-terms contract.
