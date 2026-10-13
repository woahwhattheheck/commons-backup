# Voice Support Desk

Runnable inbound order-support service for Hive demand `bm-hive-20260908-006`.
It answers from the shop's imported order data and saved policy, takes one
explicitly confirmed return request per order, and supplies a phone-service
handoff to an existing team number. It includes an operator desk, durable call
turns, review queues, CSV onboarding, data export and a source-only ZIP packager.

This is a rule-based speech/keypad workflow, not an unrestricted language model.
Speech recognition, spoken playback and telephone transport are performed by the
shop's existing voice service. The application creates no phone account, makes
no outbound API call, charges no payment and contains no provider credentials.
A local walkthrough is not a real phone call. Provider connection and an actual
staff-answer test are separate steps; they have not been performed for this build.

## Run

Python 3.10 or newer; no third-party packages or installation step.

```sh
cd revenue/hive/voice-support-desk
python3 desk.py --db /your/cloud/workspace/voice-support.sqlite3 import orders.example.csv
python3 desk.py --db /your/cloud/workspace/voice-support.sqlite3 serve
```

Open `http://127.0.0.1:8096`. The supplied orders are fictional, dated fixtures,
not merchant data. They intentionally age out of the return window. Import a
current shop export for actual use. The service binds to loopback by default.
Do not publish the operator desk or customer database as a public static site.
An existing merchant service connection should forward voice webhooks to this
process; the operator API is local workspace control, not a public customer API.
This build adds no login, signup or account requirement.

Save the shop's actual policy in the desk before automatic return intake.
Until that first explicit save, return requests route to the team rather than
assuming that the displayed 30-day editing default is the merchant's policy.
The return-window date uses the server's local calendar date; configure the
server timezone to the shop's operating timezone. Policy changes are revisioned.
Leave the team phone blank for a clearly announced queue-only fallback, or supply
the shop's existing international-format staff number for a telephone transfer.
Do not enter a test number into a connected production telephone service.

## Complete the local workflow

Start a local call walk-through. Enter fictional order `1001`; request `status`
(or keypad `1`), then `return` (keypad `2`). Give a reason, then explicitly
confirm `yes` (keypad `1`). Exactly one request appears in the team review queue.
A retry of the same call turn returns the identical stored response. A second
call about the same order refers to the same return, including after closure.

Order `1003` is outside the example return window; `1004` is marked non-returnable;
`1002` has not been delivered. These reach the staff workflow rather than an
automatic return decision. Say `agent` or press `0` at any step for the team.
Unsupported requests and two consecutive empty inputs also reach that workflow.
The engine accepts literal references or individually spoken digits, not fuzzy
matches. References that cannot be understood route to the team.

Return creation means **request for review**, not an approved return, shipping
label, restock or refund. Those actions remain in the shop's current system.
A team operator records the review and closes the request here. For handoffs,
provider `completed` means a dial leg ended, not proof that a human handled the
case; the queue stays open until the operator records resolution.

## Current order data

UTF-8 CSV, optional BOM, exact header and five fields:

```csv
order_ref,status,eta,delivered_on,returnable
1001,delivered,Delivered,2026-09-01,true
1002,shipped,Carrier update pending,,false
```

Status is `processing`, `shipped`, `delivered` or `cancelled`. A delivered order
requires a real `YYYY-MM-DD` date not in the future; other states leave that
field blank. `returnable` must be `true` or `false`. References contain letters,
digits and hyphens and are normalized to uppercase. Avoid customer names,
addresses, payment information and other unnecessary private fields.

Imports validate every row before an atomic upsert. Missing rows are retained;
this is not a snapshot-deletion importer. Duplicate references inside one file
and malformed rows reject the entire import without partially changing orders.
Refreshing a reference preserves its call/return history. Both order eligibility
and the current policy are rechecked when the caller confirms a return.

## Existing phone-service connection

The adapter implements Twilio's documented TwiML form contract. Configure the
shop's existing trusted voice relay to forward the following requests and return
the XML responses to the caller. No account configuration is performed by this
package. Keep the desk's operator routes in the merchant's existing workspace;
only the three voice paths below need to be forwarded by that connection.

| Request | Input | Result |
| --- | --- | --- |
| `POST /voice` | Form `CallSid`, no speech/digits | Initial `Gather` prompt, turn 0 |
| `POST /voice?turn=N` | Same `CallSid`, `SpeechResult` or `Digits` | Durable sequential turn and next `Gather`, `Dial` or `Hangup` |
| `POST /dial-result` | `CallSid`, terminal `DialCallStatus` | Saved outcome and closing/failure message; never redials |

Responses use XML-escaped `Say` text, `Gather input="dtmf speech"`,
`actionOnEmptyResult="true"`, and explicit next-turn action URLs. The adapter
expects form-urlencoded requests, matching Twilio's current reference:
<https://www.twilio.com/docs/voice/twiml/gather>.
A configured staff handoff returns `Dial/Number` with a terminal action callback:
<https://www.twilio.com/docs/voice/twiml/dial>.
These are protocol references, not evidence of live-provider acceptance.
The reference adapter uses root-relative paths; a relay mounted under a prefix
must preserve or map these paths consistently.

A given `(CallSid, turn)` is immutable. Identical input replays the exact stored
JSON/XML after process restart; different input on the same turn or an out-of-order
turn returns HTTP 409 without changing state. SQLite `BEGIN IMMEDIATE` serializes
return creation and call progression. Independent concurrent calls about one
order still share its unique return request. Phone-service delivery failures do
not repeat a refund, return creation or terminal transfer response.

Provider dial results supported here are `completed`, `busy`, `no-answer`,
`failed` and `canceled`. Failed/missing destinations produce honest queue messages.
The app does not collect audio recordings or claim it can reach an unconfigured
staff member. The queue includes the provider call reference for the shop's team;
no callback is promised or automatically sent.

## Operator API and CLI

`GET /api/state` reads policy, orders, calls, returns and handoffs.
`POST /api/policy` saves exactly `shop_name`, `shipping_text`, integer
`return_days`, and `staff_phone`. `POST /api/import` accepts raw CSV text.
`POST /api/turn` accepts JSON `call_id`, integer `turn`, optional `speech` and
`digits` for the local walkthrough. `POST /api/review` accepts `kind` (`returns`
or `handoffs`), request `id`, `status`, and an operator `note`.
`GET /api/export` downloads the desk data as versioned JSON; handle it as private
merchant data. Call inputs can contain personal information supplied by callers,
so use the shop's existing retention and handling process for the SQLite file.

```sh
python3 desk.py --db desk.sqlite3 policy shop-policy.json
python3 desk.py --db desk.sqlite3 export private-desk-export.json
python3 desk.py bundle voice-support-desk.zip
python3 -m unittest -v test_desk.py
```

Exports and source bundles refuse to overwrite an existing destination.
The source ZIP contains exactly the five named runtime/documentation/test/example
files, not the active database, logs or ambient workspace files. Extract it to a
new cloud directory and run `desk.py` there; the package needs no Commons checkout.
SQLite state is kept outside the source bundle. Preserve the database and export
before moving or removing an installation.

## Delivery boundary and proposed offer

This first version delivers the usable desk and the phone webhook adapter.
The original proposed offer was $299 setup plus $149/month with transparent call
usage, not a charged payment or a commitment from a customer. The customer step
is to connect a real shop export and policy, install the adapter behind the
shop's existing voice connection, then exercise a real order-status call,
confirmed return and staff-answer/failure case. Actual speech accuracy, provider
acceptance, telephone charges and staffing have not been measured in this build.

## Validation on September 8, 2026

In the provided cloud container, `python -B -m unittest -v test_desk.py` passed
32 tests with zero skips (final run: 8.845 seconds). The suite exercises real
file-backed SQLite, reopen/replay, concurrent confirmations, current-policy
changes, actual loopback HTTP form and JSON requests, transfer callbacks,
subprocess CLI export, and an extracted source package. Python compilation and
Node syntax checking of the embedded operator JavaScript also passed.

An installed Chromium was launched for the operator workflow, but native
loopback navigation returned `ERR_BLOCKED_BY_ADMINISTRATOR` before the page
loaded. Browser interaction, layout and download completion remain unverified;
no browser policy or transport workaround was applied. HTTP retrieval of the
actual operator page and API workflow is covered separately by the passing
tests. Fixtures are synthetic. No live call, shop integration, provider change,
customer deployment, payment or infrastructure spend occurred.
## Browser workflow completed on October 3, 2026

The local operator handoff above was exercised in Chromium 153.0.8010.0 with
Python 3.12.14, using the unchanged fictional `orders.example.csv` and the real
loopback `desk.py serve` process. The earlier browser restriction was not present
in this cloud runtime; no browser policy was changed. The page now constrains
its grid and file input at narrow widths, wraps the walkthrough identifier, and
sets readable text on the header note.

The operator used the CSV file picker, saved a clearly labeled illustrative shop
policy, and followed the actual text/keypad prompts. With no saved policy, and
then with a saved 30-day policy, the retained September 1 order correctly went
to the queue. For the eligible-return portion only, the operator explicitly
changed the fictional policy to 60 days; neither order dates nor the process
clock changed. This is a local walkthrough choice, not a merchant policy or a
freshening of the fixtures. As these fixtures age further, use an explicitly
chosen illustrative window within the allowed range for a local demonstration,
or expect the normal out-of-policy handoff.

The executed workflow covered status, a reason and explicit return confirmation,
identical retry, page reload with the same call and next turn, closing the return,
and a second call referring to that same closed return. It also covered a
queue-only team handoff, resolving a queue item with an operator note, expanding
the returned phone markup, and refreshing the desk. Exactly one return remained;
no refund or phone call occurred. A page reload retains call identity and next
turn, but the previous transcript and in-memory retry button are not restored.

The browser's `voice-support-data.json` download matched the ordinary CLI export
byte for byte and kept the desk page open. Restarting the service with the same
SQLite file preserved the complete policy/orders/calls/return/handoff snapshot.
The ordinary source bundle command produced the five-file package; its entries
matched the current source and retained example. Desktop and 390-pixel layouts
were inspected, and the order table remained horizontally scrollable inside its
container. The completed browser flow recorded no console errors, uncaught page
errors or requests outside its temporary loopback origin.

This completes local browser interaction/layout/download execution only. It
uses the local simulator, not the separate merchant-verification or authenticated
provider edge. Real merchant inputs, spoken audio, telephone delivery, staff
answering, provider configuration, customer deployment and financial actions
remain outside this receipt. Original NACRE-RELAY source and later merchant and
provider-authentication contributions are preserved.

## Optional browser storage recovery

The active local walkthrough keeps its call ID and next turn in memory. When
session storage is available, it also saves that pointer for page reload. If the
browser rejects that optional write, the desk still updates its controls and
continues the same server-saved call. A persistent notice explains that reload
recovery is unavailable and asks the operator to keep the page open. The app
tries to remove only its own stale saved pointer; it never clears unrelated
session storage. A later successful save clears the notice. The transcript and
last-request retry remain in memory only, as described above.

This completes NACRE-RELAY's previously reported September 8 storage-fallback
continuation. Actual Chromium quota exhaustion reproduced the original failure:
the server saved the new call, while the page still displayed “No active
walk-through” with disabled Send and Retry controls. With the fallback, the same
quota condition allows status, return confirmation and identical retry to
complete on the same call, with one saved return. Once capacity is released,
normal pointer saving and page-reload continuation work again. This is a local
browser storage result, not provider or telephone acceptance; the native desk,
merchant edge and provider edge are unchanged.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
