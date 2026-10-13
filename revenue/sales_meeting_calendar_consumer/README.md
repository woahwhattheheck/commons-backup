# Sales Meeting Calendar Consumer

This is the path-disjoint live integration for the landed
`revenue/sales_meeting_readiness` product. It does **not** rewrite that compiler.

The integration closes one operating boundary:

> After a verified human requests/suggests a meeting, current readiness may be
> computed only from independently retained human-reply authority plus an actual
> read-only Google Calendar free/busy capture for the exact requested window.
> The strongest state is `READY_FOR_OWNER_SCHEDULING_REVIEW`; it never creates,
> updates, deletes, holds, invites, RSVPs, sends, replies, or confirms a meeting.

## Current trust boundary

The current API deliberately does **not** accept caller-supplied "expected
SHA-256" values and does **not** accept caller-selected `as_of`.

`CurrentAuthorityStore` is a protocol implemented by the trusted host. Its two
lookups must be backed by provider evidence retained independently of candidate
trigger/capture bytes:

```python
class CurrentAuthorityStore(Protocol):
    def get_human_authority(self, authority_ref: str) -> Any: ...
    def get_calendar_capture(self, capture_ref: str) -> Any: ...
```

This module ships no JSON/file-backed current store and no current CLI that can
self-populate one. A plain dict is explicitly rejected. In production the host
must bind those lookups to its authenticated provider/capability/evidence store.
Compromise of that trusted host store is outside this compiler's packet threat
model; candidate JSON cannot manufacture a store hit by hashing itself.

The trigger carries only an opaque `human_authority_ref`, not the authority
record itself. The retained human record must independently match exact inbound
provider event id, content SHA-256, observed time, opportunity, thread, and the
verified-human `MEETING_REQUEST` classification.

The Calendar capture is also looked up by an opaque retained reference. The
capture binds the exact plan, provider-result digest, capture time, normalized
busy windows and capture digest. A capture from another human event, request,
thread, opportunity, time range, or timezone cannot transplant.

## Current host sequence

1. A trusted inbound adapter classifies an authenticated provider event as a
   verified human meeting request and retains the exact authority record in the
   host's independent authority store. Candidate packet bytes do not create it.
2. Build the free/busy plan:

   ```python
   plan = build_google_availability_plan(trigger, authority_store=store)
   args = google_tool_args(plan)
   ```

   `args` contains only:

   ```json
   {
     "calendar_ids": ["primary"],
     "time_min": "2026-09-14T17:00:00Z",
     "time_max": "2026-09-14T19:00:00Z",
     "response_timezone_str": "America/Kentucky/Louisville"
   }
   ```

3. The trusted host calls Google Calendar `get_availability` with those exact
   arguments. No mutation tool belongs in this carrier.
4. Immediately normalize that connector result with
   `capture_google_availability(plan, provider_result, captured_at=host_time)`
   and retain the resulting capture independently under an opaque store ref.
   The durable capture keeps busy windows and error presence, not event titles,
   descriptions, attendees, or provider error text.
5. Compile current readiness:

   ```python
   receipt = compile_calendar_consumer_current(
       trigger,
       calendar_capture_ref,
       authority_store=store,
   )
   ```

   Current compilation owns `datetime.now(timezone.utc)` internally. There is no
   public current `as_of` parameter. The landed core still enforces its 30-minute
   availability freshness window and every request/busy/slot binding.
6. Before treating an old receipt as ready, call
   `is_ready_for_owner_review(receipt, trigger, authority_store=store)`. That
   helper reacquires both store records and recompiles against current time; it
   does not trust a historical READY string.

## Historical/offline replay

Historical bytes remain useful for audit, but they cannot become current
scheduling authority.

`compile_calendar_consumer_historical(trigger, human_authority, capture,
as_of=...)` always emits:

- `mode = HISTORICAL_REPLAY`
- `state = HISTORICAL_REPLAY_ONLY`
- `historical_core_state = ...` for audit only
- `owner_review_only = false`
- `historical_replay_only = true`

Even when a backdated historical `as_of` would make the landed core say READY,
the wrapper remains `HISTORICAL_REPLAY_ONLY` and
`is_ready_for_owner_review(...)` returns false before any current authority
claim.

The CLI intentionally exposes **only** this non-authorizing replay:

```bash
python -m revenue.sales_meeting_calendar_consumer.cli \
  --trigger trigger.json \
  --human-authority retained_human.json \
  --capture retained_calendar.json \
  --as-of 2026-09-13T16:26:00Z \
  --markdown
```

There is no JSON current-READY CLI because serialized candidate inputs cannot be
an independent current authority store.

## Calendar semantics

The adapter:

- normalizes RFC3339 offsets to canonical UTC seconds;
- queries the covering min/max envelope but selects slots only inside the exact
  requested windows (never the gap between disjoint windows);
- requires the requested duration to fit wholly in a requested window;
- picks the earliest full-duration free interval;
- returns conflict when no full duration exists and retained busy evidence
  overlaps a reproducible requested slot;
- maps provider errors to `UNKNOWN`, which the landed core turns into
  `CALENDAR_CHECK_REQUIRED`;
- rejects busy intervals outside the exact query bounds;
- binds every capture to the retained human authority SHA and request digest.

## Meeting prep

The trigger must carry complete, PII-minimized prep before the Calendar query is
planned:

- sourced context;
- objective;
- key questions;
- likely asks;
- risks / commitments to avoid;
- recommended opening;
- recommended closing;
- owner actions.

The landed core remains authoritative for freshness, request binding,
busy-digest binding, slot duration/window/overlap semantics, and preparation
completeness.

## Authority ceiling

A current READY receipt means only `READY_FOR_OWNER_SCHEDULING_REVIEW`.
It never authorizes:

- Calendar create/update/delete/hold/invite/RSVP;
- email/Slack/provider send or reply;
- telling a counterparty a meeting is confirmed;
- scope, price, staffing, delivery, legal or commercial commitment;
- payment, settlement, booked revenue or recognized revenue.

## Hostile coverage

The exact-core suite covers normal and optimized Python for:

- fabricated trigger + fabricated empty-busy capture + matching self-derived
  hashes cannot reach current READY without independent store records;
- a plain candidate JSON/dict cannot masquerade as the current authority store;
- human provider-event/opportunity/thread/digest/time transplant;
- current store capture tamper;
- cross-reply capture reuse;
- stale current capture;
- backdated historical `as_of` can never revive current READY;
- readiness helper reacquires store records and current time;
- exact query window/timezone binding;
- wrong calendar id;
- provider busy ranges outside query bounds;
- offset-to-UTC normalization;
- fresh empty-busy READY;
- busy-at-start next-slot selection;
- fully busy conflict;
- provider error -> fresh Calendar required;
- requested window shorter than duration;
- disjoint multi-window selection;
- duplicate JSON keys;
- provider error/event-detail minimization;
- complete prep rendering;
- deterministic capture hashes;
- explicit false mutation/send/commitment authority.

## Validation

The repair was executed against the exact landed #14062 core blob
`13e6f2e5d79674c5c72e11b3fadf448acbec76de` (the same blob on current main),
not a compatibility stub:

```bash
python -m py_compile revenue/sales_meeting_readiness/meeting_readiness.py \
  revenue/sales_meeting_calendar_consumer/*.py
python -m unittest revenue.sales_meeting_calendar_consumer.test_calendar_consumer -q
python -O -m unittest revenue.sales_meeting_calendar_consumer.test_calendar_consumer -q
```

Hosted GitHub Actions truth is reported separately. A queued/unassigned run is
never described as green.
