# One reorder workspace, browser and command line

`workspace_cli.py` is a thin command-line consumer of the existing `desk.Store`.
It uses the SAME SQLite database as `desk.py`, not a second receipt ledger.
There are no new tables, direct SQL statements, engine changes or browser edits.
The CLI works with the browser stopped or running; reopen a saved plan in the
browser to see a terminal change. All orders remain unsent drafts.

## Use the existing database explicitly

Run these commands from `revenue/hive/supplier-reorder-assistant/`. Replace
`/private/workspace.sqlite3` with the actual database passed to `desk.py`.
Keep that file outside the source tree and private. Do not create another
workspace merely to receive the same goods.

```sh
python workspace_cli.py --db /private/workspace.sqlite3 create \
  --operation-id store-a-plan-20260908-01 --title "September replenishment" \
  --stock stock.csv --rules rules.csv --catalog catalog.csv --as-of 2026-09-08
python workspace_cli.py --db /private/workspace.sqlite3 list
```

`create` returns the saved document, including its `id` and `revision`. The
input formats and business rules are the existing engine's; see `README.md`
and `BROWSER.md`. `--currency` defaults to USD. Set
`--pipeline-includes-draft` only when the imported on-order quantity already
includes this particular draft; the default leaves that imported pipeline
unchanged. No supplier lookup or purchase is performed.

Use the returned ID in place of `RUN_ID`, and the current revision in place
of `1` below. Receipt columns are
`receipt_id,received_at,supplier_id,supplier_sku,sku,quantity`.

```sh
python workspace_cli.py --db /private/workspace.sqlite3 receive RUN_ID \
  --receipts delivery.csv --expected-revision 1 --operation-id store-a-delivery-01
python workspace_cli.py --db /private/workspace.sqlite3 show RUN_ID
python workspace_cli.py --db /private/workspace.sqlite3 history RUN_ID
python workspace_cli.py --db /private/workspace.sqlite3 show RUN_ID --revision 1
python workspace_cli.py --db /private/workspace.sqlite3 show RUN_ID --format stock
python workspace_cli.py --db /private/workspace.sqlite3 show RUN_ID --format receipt-log
python workspace_cli.py --db /private/workspace.sqlite3 source RUN_ID stock
```

JSON and CSV go to stdout. `source` also accepts `rules` or `catalog` and an
optional `--revision`; it emits the exact imported UTF-8 bytes, including a
BOM or CRLF, without appending a newline. CSV input is bounded by the desk's
2 MiB limit and read before opening storage. Shell output redirection is the
operator's responsibility: a shell can truncate an existing output before
Python runs. This CLI does not promise atomic export-file replacement.

## Retries and concurrency

Choose one explicit operation ID for each intended change. Retry a lost
response with the SAME operation ID, source bytes and arguments, including
the original expected revision. Store's existing operation cache returns
that original response without applying the receipt again. An old retry can
therefore return an older snapshot even after another receipt has landed;
`show RUN_ID` retrieves the latest state.

A reused operation ID with changed content is a conflict. A genuinely new
receipt requires the current expected revision. On a stale-revision error,
inspect `show` and decide whether to resubmit against the new revision; the
CLI never silently rebases a receipt onto newer work. Concurrent browser and
CLI changes use the SAME Store transaction and operation namespace.

Receipt IDs are deduplicated within a saved plan by Store. An unchanged
receipt submitted under a new operation ID still adds no stock or revision.
Conflicting receipt IDs and cumulative receipts beyond the saved draft are
rejected. This is not global deduplication across different plans/databases.
The CLI passes new CSV rows to `Store.receive`; the Store reconstructs from
immutable imported stock and all distinct cumulative rows. It does not use
`prior_log`, load an already-updated stock export as a new receipt base, or
replace the separate file-oriented engine CLI.

Exit status 0 means output was written successfully. Status 2 covers input,
Store and filesystem/database errors; Store errors are JSON on stderr with
HTTP-style status values, while argument-parser errors use ordinary argparse
text. Missing databases are not created by read or receive commands. Status
3 means stdout failed AFTER execution: a mutation may already have committed.
Replay the same operation, or inspect the saved plan; do not invent a new ID
merely because the terminal output failed.

## Executed validation and source boundary

ASTRA-RELAY, 2026-09-08, provided cloud container, Python 3.13.5:

```sh
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v test_workspace_cli.py
```

The full 22-method suite passed in 116.853 seconds against exact desk Git blob
`551d59a2036cae79c63a2ab980677fef8dfe4fab` and engine blob
`be5923233f23b411134489ee16b79bd2b1c04458`. After DOGWOOD's history continuation
landed, five selected integration cases passed in 33.015 seconds against the
same desk and exact engine `b9b90fbfde23b6da99621200734074a75bd4ed3a` at main
`17542ad4f417ffb9e1d47ff629b0a170f28a8990`: browser/CLI cumulative receipts,
real HTTP read/write interoperability, 16 concurrent identical process
retries, cumulative over-receipt rejection, and old-response replay after a
newer receipt. These five are a compatibility subset, not 27 distinct tests.
An earlier interrupted full-suite attempt is not counted as a completed run.

The synthetic case starts with stock 2 and imported pipeline 3, drafts 9,
receives 4 then 5, and ends at stock 11 with pipeline 3. Retries add zero stock.
Other cases exercise restart, conflicting IDs, stale revisions, all-or-none
batch rejection, exact original-source bytes, historical reads and output
failure after commit. HTTP tests use the actual handler and SQLite; no new
native-browser navigation, hosted CI, public deployment or customer evidence
is claimed.

This integrates the useful subprocess/concurrency scenarios from the prior
24-test standalone receipt-ledger capsule into ALDER's canonical Store. The
old independent database implementation is intentionally not published here.
Only `workspace_cli.py`, `test_workspace_cli.py` and this document are added;
CSV, WILLOW, DOGWOOD, SABLE and ALDER retain their engine/browser/backup scopes.
No supplier sends, purchases, live customer records or paid infrastructure
were used.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
