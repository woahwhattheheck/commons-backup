# Opportunity Deadline Command Center

The Opportunity Deadline Command Center is an offline operating surface for a portfolio of evidence-bound RFPs, RFIs, market engagements, registrations, conferences, and similar paid-opportunity deadlines.

It answers a narrow question: **given exact source evidence and a trusted evaluation time, what deserves owner attention next?** It does not qualify a bidder, infer buyer intent, contact a buyer, register for anything, submit anything, price work, sign a contract, spend money, or recognize revenue.

## Why this exists

Buyer-specific qualification packets answer whether an individual opportunity is supportable. A growing portfolio has a different failure mode: controlling dates, source freshness, missing packet/addendum work, and ownership become scattered across threads. This module creates one deterministic cross-opportunity queue without replacing buyer-specific qualification.

A deadline can drive an owner-review state only when it is bound to an `OFFICIAL` source. A date learned from a `SECONDARY` source stays discovery evidence and forces source recovery rather than creating action authority.

## Input contract

The input is strict JSON:

```json
{
  "schema_version": "opportunity-deadline-command-input/v1",
  "opportunities": [
    {
      "opportunity_id": "nhdes-2026-093",
      "buyer": "Example Public Buyer",
      "solicitation_id": "RFP-2026-093",
      "title": "Example systems procurement",
      "owner_ref": "OWNER-REF",
      "route_state": "TEAMING",
      "source_set_complete": true,
      "controlling_source_id": "official-notice-v1",
      "packet_state": "COMPLETE",
      "sources": [
        {
          "source_id": "official-notice-v1",
          "authority": "OFFICIAL",
          "captured_at": "2026-09-13T10:00:00Z",
          "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "url": "https://buyer.example.gov/rfp",
          "label": "Official solicitation notice",
          "generation": 1
        }
      ],
      "deadlines": [
        {
          "deadline_id": "question-v1",
          "kind": "QUESTION",
          "at": "2026-09-24T18:00:00Z",
          "source_id": "official-notice-v1",
          "generation": 1
        },
        {
          "deadline_id": "response-v1",
          "kind": "RESPONSE",
          "at": "2026-10-08T21:00:00Z",
          "source_id": "official-notice-v1",
          "generation": 1
        }
      ],
      "blocker_codes": [],
      "owner_action_refs": ["OWNER-REVIEW"]
    }
  ]
}
```

Supported route states are `PRIME`, `TEAMING`, `PARTNER_REQUIRED`, `HOLD`, `NO_BID`, and `UNKNOWN`. Supported deadline kinds are `QUESTION`, `CONFERENCE`, `RESPONSE`, `MARKET_ENGAGEMENT`, `REGISTRATION`, and `ADDENDA_CHECK`.

A deadline extension is a new deadline generation with a new ID and `supersedes_deadline_id`. Silent mutation of a deadline ID is never accepted. An effective `QUESTION`, `REGISTRATION`, or `ADDENDA_CHECK` date may not fall after the effective response/market-engagement deadline.

## Policy

Policy is also strict JSON:

```json
{
  "schema_version": "opportunity-deadline-command-policy/v1",
  "max_source_age_minutes": 10080,
  "critical_window_minutes": 1440,
  "high_window_minutes": 10080,
  "addenda_review_window_minutes": 20160
}
```

The policy is SHA-bound into every result. `critical_window_minutes` must be less than or equal to `high_window_minutes`.

## Operating states

Each opportunity receives exactly one conservative state:

- `SOURCE_RECOVERY_REQUIRED` — official authority is missing, stale, incomplete, a declared deadline is secondary-only, or no deadline has been supplied. Missing dates carry `NO_DECLARED_DEADLINE`; no closing date is inferred.
- `ADDENDA_REVIEW_REQUIRED` — a bound addenda check is due or addenda remain unchecked near a live response deadline.
- `QUESTION_WINDOW_OPEN` — the next official deadline is a question cutoff.
- `CONFERENCE_ACTION_REVIEW` — the next official deadline is a conference milestone.
- `REGISTRATION_ACTION_REVIEW` — the next official deadline is a registration cutoff.
- `RESPONSE_DUE_SOON` — the next official response/market-engagement deadline is inside the critical window.
- `RESPONSE_WINDOW_OPEN` — a verified official response/market-engagement deadline is live outside the critical window.
- `NOT_YET_OPEN` — the next official deadline carries a future `opens_at`.
- `EXPIRED` — declared deadlines exist, but none remain in the future after the source-quality checks.
- `TERMINAL_NO_BID` — owner route state is explicitly `NO_BID`.
- `HOLD` — route evidence itself is `HOLD` or `UNKNOWN`.

Priority is transparent (`CRITICAL`, `HIGH`, `NORMAL`, `TERMINAL`, `HOLD`) and derived only from state plus policy windows. There is no model score, expected value, win probability, budget inference, or revenue estimate.

## Output integrity

`compile_portfolio()` emits canonical JSON containing:

- input, policy, row, and receipt SHA-256 digests;
- state/priority counts;
- deterministic queue ordering;
- privacy-minimized source/deadline bindings;
- an explicit authority map with every external-action permission false.

`markdown_projection()` and `ics_projection()` are deterministic projections of that result. ICS contains only `OFFICIAL` effective deadlines, no attendees/organizers, and a description that repeats the owner-review-only authority ceiling.

Calendar UIDs bind the opportunity and deadline kind, so an amended date keeps
the same event identity. `SEQUENCE` is the deadline generation minus one; a
generation-1 event starts at sequence 0. Importers can use the retained UID and
increased sequence to recognize an update. The model permits only one effective
deadline per kind. UTF-8 content lines are folded at 75 octets without splitting
characters, following [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545), sections
3.1, 3.8.4.7, and 3.8.7.4.

Migration: older exports used generation-specific UIDs. When replacing an old
import with this format, remove or replace that old imported calendar once to
avoid retaining its separate legacy events. The exporter does not modify a
calendar account, and client-specific import/update behavior still applies.

`verify_result()` first reproduces the exact original result from the original inputs/policy/evaluation time, then recompiles against a separately supplied trusted current time. It fails if the current state/priority/controlling deadline has changed. Mere minute-count drift does not invalidate a result until it crosses an operating or priority boundary.

## CLI

The production CLI does **not** accept a caller-selected current time. It samples UTC internally.

```bash
python -m revenue.opportunity_deadline_command.engine compile \
  --input opportunities.json \
  --policy policy.json \
  --json-out command.json \
  --markdown-out command.md \
  --ics-out command.ics

python -m revenue.opportunity_deadline_command.engine verify \
  --input opportunities.json \
  --policy policy.json \
  --result command.json
```

Inputs are bounded ordinary UTF-8 files. Output publication is create-exclusive and refuses overwrite/final-component symlink following. The module makes no network calls.

Compilation renders all three outputs and checks every destination before
creating files. An existing destination, missing parent directory, or two paths
that resolve to the same destination produces an error without publishing a
partial bundle. Final creation remains exclusive. Unexpected I/O failures or
concurrent filesystem changes during publication can still leave already-written
artifacts; the CLI reports those failures with exit code 2.

## Native Work export

`python -m revenue.opportunity_deadline_command.work_snapshot` prepares selected
deadline-review metadata for the existing command-center Work ingest format.
It preserves partial coverage, separate owner directions, and the underlying
source capture times. Review rows do not count as new work. See
[the native export guide](NATIVE_WORK_EXPORT.md) for the CLI, local ingestion,
exact-payload retry, and retained-selection workflow.

## Authority ceiling

Every state, queue row, Markdown line, and calendar event is **owner-review decision support only**. Nothing here authorizes buyer/partner/sponsor contact, portal login/registration, question submission, conference registration, proposal/RFI/bid submission, signature/certification, pricing/staffing commitment, contract acceptance, spend, payment/provider mutation, award assertion, cash assertion, or revenue recognition.
