# Inbound Lead SLA & Response Control

Operation: `INBOUND-LEAD-SLA-CONVERSION-CONTROL-ZSA0445-20260917`  
Commons issue: #15533  
Seat: Z-Sol Asterline-0445 (`ZSA-0445`) / GPT-5.6 Sol

This carrier turns **retained inbound provider truth** into a deterministic,
read-only response queue. It exists because two different revenue failures are
easy to create in a multi-agent fleet:

1. a real human reply sits unanswered until the opportunity cools; or
2. several seats answer the same hot thread and make the organization look
   spammy.

The compiler deliberately solves neither problem by sending a message. It makes
the response edge explicit, retains the provider evidence that produced the
classification, and stops at the authority boundary required for the next
human/provider action.

## State contract

| State | Meaning | Next safe step |
|---|---|---|
| `NEW_INBOUND_UNANSWERED` | Newest genuine human inbound is newer than our newest outbound | `RECENSUS_THEN_MUSE_ARBITRATION` |
| `WAITING_ON_COUNTERPARTY` | We already replied after the newest human inbound | `HARD_DNR_UNTIL_NEW_HUMAN_OR_PROVIDER_EVENT` |
| `CHECK_CALENDAR_REQUIRED` | New inbound asks for a meeting/date | Check real availability, then recensus + Muse |
| `OWNER_DECISION_REQUIRED` | New inbound asks for binding terms/price/acceptance | Owner decision, then recensus + Muse |
| `COLLISION_HOLD` | More than one active writer claims the exact route/thread | Resolve single writer |
| `CENSUS_HOLD` | Provider/coordination census is incomplete or stale | Refresh the census |
| `ROUTE_FAILURE_HOLD` | Authoritative route failure/bounce is latest | Do **not** mechanically hunt an alias |
| `EVIDENCE_HOLD` | Retained chronology/scope evidence is contradictory | Repair evidence first |
| `NO_INBOUND_SIGNAL` | No human inbound is retained for the scope | No action |

A retained `MUSE_SELECTED` row remains **evidence only**. It never changes
`send_authorized=false`, and the normal response state still stops at a fresh
recensus/Muse boundary. This avoids converting a stale lease into a send token.

## Evidence model

One input document contains:

- `as_of_utc`: canonical second-precision UTC replay boundary.
- owner-authored `policy`:
  - response SLA by `HOT | WARM | GENERAL`;
  - maximum census age;
  - maximum writer-claim horizon.
- `census`: explicit provider/coordination/page completeness and observation
  timestamp.
- `leads`: one unique route/thread scope each.
- per lead:
  - retained provider events,
  - retained writer claims.

Provider events carry both a stable `provider_ref` and a semantic content hash.
The compiler rejects:

- duplicate event IDs;
- duplicate `(provider, provider_ref)` identities;
- exact semantic duplicates re-minted under a new ID/reference;
- future-dated retained events or claims;
- wrong route/thread events;
- duplicate lead scopes;
- noncanonical timestamps;
- non-boolean census flags and bool-as-int policy values;
- any two state-driving `HUMAN_INBOUND`, `OUTBOUND_SENT`, or `BOUNCE` facts on
  the same route/thread at the same retained UTC second.

That final fence is intentionally strict. The retained event schema has only
second-precision time and no authenticated provider sequence. Therefore a
same-second pair has no trustworthy causal order. Compilation fails closed with
`InputError` instead of treating list order or a fixed event-kind precedence as
causality. A later generation may preserve both facts once the provider supplies
a finer trusted sequence/key.

The compiled queue retains exact latest inbound/outbound/bounce event IDs and
provider references for reviewer reconstruction whenever chronology is
unambiguous.

## SLA semantics

An SLA breach is a **fact**, not an authorization. For an actionable human
inbound, the compiler reports age and compares it with the owner-authored
priority SLA. A breach can move a row to the top of the deterministic queue,
but it does not create permission to send, accept terms, schedule a meeting, or
recognize revenue.

Queue ordering is deterministic:

1. breached actionable rows first;
2. collision/evidence/calendar/owner-decision/actionable holds;
3. priority (`HOT`, `WARM`, `GENERAL`);
4. older inbound age;
5. stable lead ID.

## CLI

Compile to stdout:

```bash
python -m revenue.inbound_lead_control.cli compile retained_snapshot.json
```

Create new JSON + Markdown artifacts:

```bash
python -m revenue.inbound_lead_control.cli compile retained_snapshot.json \
  --json-out inbound_queue.json \
  --markdown-out inbound_queue.md
```

The CLI uses create-exclusive output semantics and refuses to overwrite an
existing path.

Verify an artifact by exact semantic replay:

```bash
python -m revenue.inbound_lead_control.cli verify \
  retained_snapshot.json inbound_queue.json
```

Successful verification prints `VALID`. The Markdown renderer also verifies the
compiled artifact's self-receipt before rendering.

## Tests

```bash
python -m unittest -v test_inbound_lead_control.py
python -O -m unittest -v test_inbound_lead_control.py
```

The retained suite includes normal and hostile cases for reply/DNR transitions,
new-human reopen, meeting/terms boundaries, simultaneous writers, stale and
incomplete census, future evidence, route-scope transplants, provider-ID and
semantic duplicate remints, bounce quarantine, strict type/timestamp parsing,
receipt tamper, create-exclusive CLI behavior, and same-second chronology
permutations (human intent escalation, inbound/outbound, and inbound/bounce).
The chronology suite also launches a real optimized child interpreter so the
fail-closed fence is exercised even when Python assertions are removed.

## Authority ceiling

This package has **read/compile/triage authority only**.

It does not send Gmail/Slack/forms/comments, choose a new recipient, schedule
or confirm a meeting, mutate a provider, accept pricing/contract terms, assert a
receivable, mark payment, or recognize revenue. A real external response is a
separate last-inch operation with fresh provider/coordination census and Muse
exact-wire arbitration. Meeting confirmation additionally requires verified
calendar availability first.

See `truth.json` for the machine-readable ceiling.
