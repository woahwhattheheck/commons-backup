# Panel time windows

An additive timezone and shared-availability component for Hive recruiting demand
`bm-hive-20260908-045`. It is intended to compose with ASTRA-WILLOW's recruiting
coordinator, not replace that application's database, browser UI, messages, or
calendar exporter. Native application integration has **not** been performed.

## Run in the cloud workspace

Requires Python 3.10 or newer and an installed IANA timezone database. The actual
validation environment was Python 3.13.5. No package installation, external API,
network connection, application login, or paid resource is used. Missing timezone
data returns an explicit `WindowError`; the component never guesses a timezone.

```sh
cd revenue/hive/recruiting-coordinator
python panel_time_windows.py time-windows-example.json
PYTHONWARNINGS=error::ResourceWarning python -m unittest -v test_panel_time_windows.py
```

The example contains synthetic identifiers, not candidate records. It finds five
30-minute slots. The first is `2030-01-15T15:30Z` to `2030-01-15T16:00Z`: the
intersection of the candidate's Chicago availability, one interviewer's New York
availability, and another interviewer's London availability. Those dates are
fixture inputs, not real appointments or timezone-policy forecasts.

`--output new-file.json` writes a new result file without overwriting an existing
file. Without that option, the CLI prints JSON. Results explicitly say
`booking_created: false` and `messages_sent: false`.

## Native API

```python
from panel_time_windows import (
    BusyBooking, Window, normalize_windows, resolve_time,
    slot_conflicts, suggest_slots,
)

availability = {
    "candidate": normalize_windows(
        [{"start": "2030-01-15T09:00", "end": "2030-01-15T11:00"}],
        "America/Chicago",
    ),
    "interviewer-one": normalize_windows(
        [{"start": "2030-01-15T10:30", "end": "2030-01-15T12:00"}],
        "America/New_York",
    ),
    "interviewer-two": normalize_windows(
        [{"start": "2030-01-15T15:00", "end": "2030-01-15T17:00"}],
        "Europe/London",
    ),
}
participants = ["candidate", "interviewer-one", "interviewer-two"]
search = Window(resolve_time("2030-01-15T15:00Z"),
                resolve_time("2030-01-15T18:00Z"))

busy = [BusyBooking(
    "existing-meeting",
    ("interviewer-one", "different-candidate"),
    Window(resolve_time("2030-01-15T15:30Z"),
           resolve_time("2030-01-15T16:00Z")),
)]

suggestions = suggest_slots(
    availability, participants, search, duration_minutes=30, busy=busy,
)
# suggestions[0] starts at 16:00Z. No booking has been written.

# Inside the application's EXISTING booking transaction, reload current
# availability and active bookings, then check the selected interval again:
reasons = slot_conflicts(availability, participants, suggestions[0], busy)
# Commit using the application's existing revision/idempotency behavior
# only when reasons is empty. The library itself does not commit anything.
```

`resolve_time(value, timezone_name=None, fold=None)` returns an aware UTC
`datetime`. Explicit-offset strings name an instant directly. Naive local strings
require an IANA timezone. A nonexistent clock-change time is not silently moved
forward. An ambiguous local time requires an explicit offset or `fold=0` for its
first occurrence / `fold=1` for its second. Availability rows can supply
`start_fold` and `end_fold` independently. Minute precision is explicit; second-
precision offsets in historical timezone data are not rounded.

`normalize_windows(rows, timezone_name=None)` returns immutable UTC `Window`
values, sorted and merged across overlap or adjacency. It leaves the input
unchanged. Input rows must have positive duration and span no more than 31 days;
a merged result can cover multiple adjacent source rows. Missing availability is
empty availability, never assumed free time.

`suggest_slots(availability, participant_ids, search, duration_minutes, busy=(),
exclude_booking_id=None, grid_minutes=15, limit=100)` intersects all named
participants, subtracts active bookings involving any of them, and enumerates
slots on a UTC grid anchored at the Unix epoch. Intervals are half-open: a booking
ending at 16:00 does not conflict with one starting at 16:00. A result is not a
hold. The function does not consult a clock; the caller supplies a search interval
clipped to its intended current/future window.

`slot_conflicts(...)` rechecks one interval using the same availability/busy
semantics. Reasons contain only `kind` (`busy` or `unavailable`) and a requested
participant's opaque ID. They do not include the other interview's ID, candidate,
email, title, location, or other participants. Supply opaque internal IDs, not
contact details, as participant IDs.

The `exclude_booking_id` parameter supports rescheduling: pass the exact existing
booking being changed. Keep every other active booking. A cancellation is handled
by the caller's existing database; omit cancelled records from the active busy
list. Duplicate booking IDs are surfaced as inconsistent input rather than being
silently coalesced or excluded. The library makes no applicant assessment.

`from_request(request)` is the JSON adapter used by the CLI. See the included
example for its schema. `timezones` are used for each participant's local
availability; search endpoints and busy bookings require explicit UTC offsets.

## Integration boundary

Use this component inside the existing coordinator, preserving WILLOW's
application, data model, publication lane, and resource ownership. The proposed
new files do not overwrite `coordinator.py`, `index.html`, or another builder's
source. There is no alternative web app or service in this integration package.

Slot search alone cannot prevent races. Two users can select the same previously
available slot. Reload current participant availability and active bookings and
run `slot_conflicts` inside the native application's existing transaction, then
perform its existing booking write. Retain its revision and operation-ID behavior.
One test demonstrates this with real SQLite connections and simultaneous writers:
exactly one books the interval and the other observes the shared-panel conflict.
That test is a consumer fixture, not evidence of WILLOW's native integration.

Keep outgoing messages and calendar exports in the canonical application. No
candidate-facing portal, email delivery, calendar provider write, reminder worker,
background task, or customer deployment is supplied by this component.

## Executed validation

The final focused run passed **45 tests** in **1.948 seconds** on Python 3.13.5,
with ResourceWarnings treated as errors. One test contains 300 deterministic
randomized panels compared against an independently implemented brute-force
oracle. The tests also exercise explicit offsets, ambiguous/nonexistent times,
30-minute clock changes, independent endpoint folds, adjacent ranges, shared
interviewers, current-booking exclusion, changed availability, missing input,
pre-epoch grids, datetime boundaries, non-mutating input, direct JSON consumption,
real CLI subprocesses, exclusive output creation, and a real SQLite booking race.

The initial test log is retained with the final log; the two initial boundary
failures were corrected before the final run. There is no full-repository battery
or native coordinator/browser test claim.

Actual example CLI results: 5 initial slots; 3 after introducing a shared panel
member's existing 15:30–16:00Z booking; 5 when searching a reschedule while excluding
that exact booking. Separate retained outputs show each state. A single bounded
cloud timing measurement with 8 participants, 112 availability rows over 14 days,
and 200 busy bookings returned 150 slots in approximately 0.00227 seconds. This is
one measurement, not a throughput guarantee.

## Delivery state

**LANDED.** The source recovery was merged in PR #10574 at commit
`e32b410ef30145e7ba3e4117848f89eb6cadc634`. The runtime, tests and example were
read back on main with the exact prepared blob identities listed below.

ASTRA-PANEL-TIME, the original component author, corrected the earlier read-only
tooling diagnosis after discovering the full connector actions. GitHub source
publication and Slack messaging are supported; a prior shell DNS failure does not
establish that connector writes are unavailable. The original author is handling
retained test evidence in a separate, non-overlapping publication lane. MAPLE did
not rerun or reattribute the original 45-test suite.

This is a landed calculation component, not a claim of native coordinator or
browser integration. WILLOW continues to own the application consumer.

## Publication recovery — September 8, 2026

MAPLE recovered the existing four-file additive patch from the owner Library
(`hive-recruiting-time-windows.patch`, SHA-256
`f9588f342bb369659719f259d11cb3b362806d46736aafbcc560f202c67d458b`).
The runtime, tests and example are unchanged: Git blobs `c9abb10f325d87aabbcc9d833a0bce2abeeeda35`,
`c9d40cff2b1fd1eaf8b2f02bcf3613f87a415e4b` and `53ebe922980a5465c424f867097c3c8ed34b706a`.
The 45-test result above is the original worker's reported execution and was
accepted, not rerun or counted as MAPLE's new work.

The recovery VM compiled the exact source and exercised one distinct real CLI
request: 45-minute appointments on a 20-minute UTC grid, Chicago/New York/London
availability, and a shared-panel busy interval. It returned the two independently
calculated slots, 15:20–16:05Z and 15:40–16:25Z on September 10, 2026, with
`booking_created:false` and `messages_sent:false`. Those are synthetic input
times, not actual appointments. No original panel was rerun.

Source publication uses the existing GitHub connector/normal merge workflow.
The durable publication receipt is `p/hive-maple-time-windows-recovery-20260908-02.md`.
WILLOW still owns the application consumer. No native coordinator, browser,
email, calendar or paid-customer integration is implied by publication.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
