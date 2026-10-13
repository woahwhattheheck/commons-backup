# GitHub Content-Write Pacemaker

This package coordinates a large cooperative fleet without holding a provider
token or performing network I/O. Callers enqueue exact GitHub mutation intents,
claim one connector-ready envelope at a time, invoke an already-connected
GitHub action, and record the observed provider result.

The state machine provides FIFO pacing, semantic replay collapse, provider
cooldowns, durable pre-dispatch state, and fail-visible reconciliation after an
ambiguous outcome. A timeout or lost response blocks later claims until an
external provider readback is recorded.

When recording a known `rate_limited` result, preserve its canonical UTC
`retry_at` even if that deadline has already elapsed. Delayed result recording
must not turn a known rejection into an uncertain write. The next claim applies
the retained provider deadline and minimum claim interval; a future deadline
still prevents dispatch. Ambiguous outcomes continue to require readback.

It is not caller admission, permission, approval, or distributed consensus.
Raw GitHub writers remain open and can bypass the queue. Cooperating callers
must share one SQLite generation; one database per worker is split brain.

## Dispatch timing hints

When `claim-next` cannot dispatch because a known deadline is still ahead, its
existing exit 4 / `NO_DISPATCH` response includes `retryAt` (canonical UTC seconds)
and `retryAfterSeconds` (remaining whole seconds at the claim observation).
The deadline is the later of the retained provider cooldown and minimum claim
interval. Python callers receive the same values as `retry_at` and
`retry_after_seconds` on `NoDispatchableMutation`.

```json
{"state":"NO_DISPATCH","reason":"provider cooldown is active","retryAt":"2026-10-04T12:00:00Z","retryAfterSeconds":60}
```

Use `retryAt` to defer the next attempt in the existing publisher while doing
other useful work; transport time makes the returned relative delay age.
The hint is a snapshot, not a reservation or a promise that work will remain.
Another cooperative caller or provider result can change the next claim.
If neither pacing deadline is active, both fields are omitted. An uncertain
prior effect still returns exit 5 / `RECONCILE_REQUIRED`, with no timing hint:
elapsed time never replaces readback.
No dispatch, sleep, timer, retry, or provider request is added by these fields.

## SQLite generation custody

The pacemaker database is persistent coordination authority, so initialization
first acquires a concrete local file generation before SQLite may schema-write.
The final parent is opened without following a final symlink and must be owned by
the current user and not group/other writable. A fresh database is reserved
create-exclusively at `0600`; an existing database must be a same-owner regular
single-link file opened without following a final symlink. Permission hardening
uses the verified file descriptor, never a path-following `chmod`.

The acquired database descriptor remains open as the lifetime generation anchor.
SQLite reopens that exact generation through a verified `/proc/self/fd/<n>` or
`/dev/fd/<n>` descriptor URI with `mode=rw`; if the runtime cannot provide an
alias resolving to the acquired `(device, inode)`, initialization fails closed.
The retained descriptor and the visible pathname are checked around each SQLite
open. On the first `store_base` module generation, the SQLite open callable, its
exception type, and row factory are captured in the `StoreBase._connect` closure.
An ordinary `importlib.reload` carries that already-trusted closure into the new
`StoreBase` class instead of recapturing mutable shared `sqlite3` module state;
the temporary handoff and closure factory are deleted after class construction.
Later rebinding of `sqlite3.connect` or creation/rebinding of the predecessor's
`_SQLITE_CONNECT` module global therefore cannot substitute a foreign returned
connection in either the current or an ordinarily reloaded class generation.
Consequently, a path that is swapped to a foreign database only for the open and
restored before return cannot redirect SQLite, while the race hostiles no longer
need a writable production connection authority. A contested generation fails
closed rather than unlinking, replacing, chmodding, or schema-writing a foreign
successor. These checks protect cooperative pacemaker state only; they do not
turn the pacemaker into caller admission, provider authorization, or a Python
sandbox against direct replacement of `StoreBase._connect` or compromise before
the first trusted module generation.

## Example

```bash
python -m tools.github_content_write_pacemaker.cli --db /private/pacer.db init
python -m tools.github_content_write_pacemaker.cli --db /private/pacer.db enqueue --intent intent.json
python -m tools.github_content_write_pacemaker.cli --db /private/pacer.db claim-next
# invoke the connected GitHub action once
python -m tools.github_content_write_pacemaker.cli --db /private/pacer.db record-result \
  --key example-operation-v2 --attempt 1 --classification committed \
  --provider-status 201 --reason 'connector returned success'
```

Receipts omit raw body and description text, retaining only exact SHA-256
commitments and state. Intents are read through one bounded no-follow regular
file descriptor. SQLite integrity and all semantic digests are rechecked by
`verify`.

`list` and `verify` consume stored mutations one row at a time, retaining each
request body only while checking its digests. Listing still returns every
body-free receipt in sequence order; verification returns the same counts and
integrity result without retaining historical request bodies. Both operations
stop on the first invalid row and close their database connection.

## Recover an existing intent

`export-intent` reads an existing mutation and prints its complete canonical
intent, including the original mutation key, description and exact request-body
strings. Its `commons-github-content-write-recovery/v1` envelope contains `intent`
(the normal enqueue shape) and the existing body-free `receipt` from the same
stored row. Stored body and intent digests are checked before any content is
returned.

```bash
python -m tools.github_content_write_pacemaker.cli --db /private/pacer.db \
  export-intent --key existing-operation-id > /private/recovered-intent.json
```

Use the retained shared database, not a newly initialized queue. Unlike
`inspect`, this command exposes the complete request body and description;
keep its output in the existing private cloud carrier rather than a status
post or a public repository. JSON is canonicalized, while strings retain their
original Unicode, newlines and whitespace.

Export makes no provider call and does not enqueue, claim, retry or change a
mutation. `DISPATCHING`, `RECONCILE_REQUIRED`, known rejections and completed
outcomes stay intact. A replacement session can recover the exact request for
provider readback through the existing publication path without issuing another
claim. Continue using the existing result and reconciliation commands with the
same operation ID; an export is not evidence that a write succeeded or failed.

## Verification

```bash
python -m py_compile tools/github_content_write_pacemaker/*.py
python -m unittest -q \
  tools.github_content_write_pacemaker.test_queue \
  tools.github_content_write_pacemaker.test_integrity \
  tools.github_content_write_pacemaker.test_reload_generation
python -O -m unittest -q \
  tools.github_content_write_pacemaker.test_queue \
  tools.github_content_write_pacemaker.test_integrity \
  tools.github_content_write_pacemaker.test_reload_generation
```

The reload-generation hostile runs its import mutation in a child interpreter,
so it proves a fresh public `store.PacemakerStore` generation without leaving
stale class objects in the surrounding test process. The package deliberately
contains no direct HTTP client, token discovery, credential transport, provider
login, or hidden retry loop. The caller must read back uncertain mutations and
explicitly reconcile them before another claim can be issued.
