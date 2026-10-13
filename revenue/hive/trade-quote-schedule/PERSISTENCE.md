# Local schedule persistence and retry recovery

The existing `accept` CLI and threaded HTTP server use the same implementation.
The CSV remains the authoritative local schedule with the original columns;
existing quotes, pricing, measurement questions and quote bundles are unchanged.

## Concurrent acceptance

Every participating writer resolves the schedule path, then holds a SQLite
`BEGIN IMMEDIATE` transaction on `.<schedule-name>.lock.sqlite3` in that directory
while it reads, checks and publishes the schedule and receipt. Different schedule
paths use independent sidecars. No booking data is migrated into SQLite. Python's
standard-library SQLite support is required; no third-party package is added.

Keep this sidecar in place while any process can write the schedule. Removing it
can give simultaneous processes different lock files. Manual CSV editors and
older application versions do not participate in this serialization. Stop all
writers before manual maintenance. This is local filesystem coordination, not a
claim about distributed/network-filesystem locking or provider calendars.

## Complete files and retries

Each CSV or receipt is written to a unique temporary file in its destination
directory, flushed and fsynced, then replaced with `os.replace`. Existing file
permission bits are retained. Failed staging/replacement leaves the previous
file intact and removes this operation's staging file. Unrelated adjacent files
are not used as staging names. The transaction is released on failures.

An exact retry for the same quote and booking returns a successful receipt without
adding a second job or rewriting the schedule. It also recreates a missing receipt.
A different slot/details for an already-booked quote produces a collision rather
than creating another job. Overlapping bookings for other quotes are rechecked
inside the transaction, so a delayed contender cannot publish a stale snapshot.

The schedule and receipt are **two separate file publications**, not a crash-atomic
pair. A receipt-write failure can occur after a booking is in the CSV. Retry the
same quote/date/time to finish the receipt; do not switch slots. Filesystem errors
are returned as `QuoteError` by the API and as the existing CLI/HTTP error response.
File fsync is not a guarantee of full power-loss durability across every filesystem.

## Validation

From this directory:

```sh
python -m unittest -v test_trade_quote.py test_schedule_persistence.py
python -m py_compile trade_quote.py test_trade_quote.py test_schedule_persistence.py
```

The cloud Linux run passed all 22 methods (12 new persistence methods and 10
unchanged workflow methods), with no skips. Coverage uses real temporary JSON/CSV
files, separate CLI processes, threads and a real local HTTP server. Controlled
read delays expose stale reads; injected replacement failures exercise recovery.
The same 12 new methods against the original source produced 8 failures and 2
errors. No Windows execution, remote filesystem, browser interaction, customer
installation, external calendar operation, message send or payment is claimed.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
