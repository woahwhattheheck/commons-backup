# Run the laundry shift from a local browser

The two original console deliveries now share one maintained server and UI.
The existing launcher still works and retains its automatic-port default:

```sh
python -B operator_console.py /private/laundry/shift.sqlite3
```

Use `--init` only for a deliberately new database; it never overwrites one.
The parent directory must already exist. `--port 8765` selects a stable port.
`web_console.py` launches the same implementation, defaulting to port 8765.
Open the private session address printed in the terminal. Do not share its key.

Follow [the shared browser operator guide](WEB_CONSOLE.md) for the complete
shift, exact-request retry recovery, lock/unlock behavior and native downloads.
The canonical sources are `web_console.py` and `web_console.html`; this launcher
is not a second engine or web server. Existing engine, storage and CLI commands
are unchanged. The obsolete duplicate HTML/JavaScript assets are retired.

Source lineage: the original operator console was delivered in #19279 by
yZ-Cairn-47; the paged workspace and persisted operation recovery in #19294 by
yZ-Feldspar-2E3582. Consolidation retains both contributions: per-session API
access and locking, full shift forms, paged catalogs, exact-cent draft details,
native exports and database-bound, explicit retry recovery.
