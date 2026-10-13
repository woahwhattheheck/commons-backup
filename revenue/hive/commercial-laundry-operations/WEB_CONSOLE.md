# Browser operations console

The browser console is a local operator interface for the existing laundry desk.
It uses the same SQLite engine and the complete `operate.py` input contract;
it does not replace either CLI or introduce another business-rule engine.

## Start

Use Python 3.11 or newer and a modern Chromium, Firefox, or Safari browser.
There are no package installs, external fonts, remote scripts, or provider services.
Run from this directory:

```sh
# Open an existing desk. Reads never initialize it.
python web_console.py /path/to/laundry-work/shift.sqlite3

# Or deliberately create a NEW desk in an existing directory.
python web_console.py /path/to/laundry-work/new-shift.sqlite3 --init
```

Open the loopback URL printed in the terminal. The default port is 8765;
`--port 0` selects an available port. Keep a consistent port when resuming a
browser's saved request, because browser storage is scoped to its origin.
The server binds only to `127.0.0.1`. The printed private address includes a
fresh per-server session key in its fragment. Do not share that address or key.
The page removes the fragment and retains only the key in tab-scoped session
storage for reload; API reads and writes require it. The unlock form accepts
the current key directly. No account, external login or payment setup is needed.
This is not a public-hosting or LAN-deployment package.
`--init` never overwrites an existing file; startup failures exit nonzero.

The existing `operator_console.py` command launches this same implementation;
its automatic-port default is retained. Use an explicit `--port` for consistent
browser recovery storage. **Lock console** clears displayed records and the
tab's saved key, but deliberately retains any unconfirmed operation in local
storage. Locking does not undo a write or stop the server. Stop with Ctrl+C when
finished. A server restart generates a new session key; reopening the private
address lets you reconcile a pending request for the same database file.

## Record a shift

Use the **Operation** selector to create a customer, site, dated price agreement,
and recurring service plan. Prices are integer cents; weekdays are Monday=0
through Sunday=6. Then create the daily manifest for the plan's route and date.
The setup catalogs display 100 records per page and an exact matching total;
use **Next 100**, **First page**, and the date filter rather than assuming the
first page is the whole database. Catalog identifiers open customer exports,
site agreement entry, or route manifest entry where applicable.

Choose a route and use its stop buttons for pickup, processing, delivery,
exception resolution, and invoice drafting. Quantities use one `ITEM=COUNT`
line per linen item, and containers use one identifier per line. Blank lines
and surrounding whitespace are ignored; identifiers remain case-sensitive.
Quantities and cents must be non-negative integers. Optional blank damage
quantities use the existing engine's zero-damage default; record observed
damage explicitly. Prefilled quantities come from the preceding recorded phase,
not from a new physical measurement. Check them before recording the next phase.

The form shows the exact payload and operation key. **Record operation** is the
only submission action. The result distinguishes `APPLIED`, `REPLAYED`, and
`REJECTED`. Counts, custody differences, resolution notes, and draft line items
remain visible on the route. An unresolved exception still prevents drafting
through the original engine; the console never clears it automatically.
A completed route does not imply invoice readiness or sanitation certification.

## Connection loss and retries

Before sending, the browser saves the exact operation, payload, database-file
identifier, and attempt count in local storage. A reload or browser restart does
not automatically send it. Use **Retry exact request** to reuse the original key
and unchanged payload. A successful replay returns the original result without
another event. A first-attempt validation rejection lets you correct the form;
a rejected retry leaves the earlier unconfirmed outcome intact. A changed
database returns HTTP 409 and does not clear the pending request.

Requests time out after 30 seconds without assuming failure or success. Save the
pending JSON before clearing browser data, moving ports, or changing machines.
It contains operator data: retain it with the same care as the desk itself.
Do not dismiss an unconfirmed request until you have reconciled its original
operation key. Dismissal removes only the browser recovery copy; it does not
undo a recorded operation. The payload can also be retried through `operate.py`
using its original command and operation key. Close the server before replacing
or restoring its database file. An old request is never transferred to a different
file merely because that file has the same display name.

## Handoffs and limits

Route and customer buttons download JSON, CSV, or Markdown directly from the
existing engine's exporters. Downloads do not write server-side export files or
change the source database. Customer CSV and Markdown retain the existing literal
label handling. Keep real customer databases, pending requests, and downloads
outside this repository.

This surface records operator facts and creates invoice **DRAFTS** only. It does
not issue invoices, mutate accounting, collect payment, contact customers,
certify quality, or claim revenue. All eight existing authority flags remain false.
Use the [operator guide](OPERATOR_GUIDE.md) for engine rules and CLI details.

The shared console combines the session boundary and locking from #19279
(yZ-Cairn-47) with the paged workspace and durable retry recovery from #19294
(yZ-Feldspar-2E3582). Both launchers use the same implementation, not competing
web applications. Backup and restore remain in the [existing CLI](BACKUP.md).
