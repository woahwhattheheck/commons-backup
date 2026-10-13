# Standalone trade quote delivery

The ZIP is a runnable copy of the existing painting workflow, not a second
quoting engine. Its runtime bytes and fictional examples come directly from
this directory. A recipient needs Python 3.10 or newer with the standard
library (including sqlite3), but no Git checkout or third-party package install.

## Build and check

From this directory:

```sh
python3 build_release.py --out /path/to/trade-quote-service.zip
python3 build_release.py --verify /path/to/trade-quote-service.zip
```

The builder includes exactly eight named source/document/example files,
`START_HERE.txt`, and `MANIFEST.json`. It does not traverse directories.
Schedules, generated quotes, receipts, databases, lock sidecars, caches,
customer photos, and other files are not included. Required source files must
be regular files without symbolic links. Keep the included examples fictional; explicitly
review these eight source files before distributing a modified package.

The manifest records byte counts and SHA-256 hashes for every payload file.
Verification checks archive membership and exact payload hashes without
extracting. These hashes detect changed contents relative to the manifest;
they are not signatures or proof of a trusted publisher. ZIP entry order,
timestamps, modes and compression settings are fixed. Identical inputs on
the same Python/zlib implementation produce identical archive bytes. An
unsuccessful build leaves an existing destination archive unchanged.

## Run after extraction

Extract into a new empty directory, open a terminal there, and read
`START_HERE.txt`. On Windows, `py` can replace `python3`.

```sh
python3 trade_quote.py quote --request examples/request.json --rules examples/pricing-rules.json --issued-on 2026-09-08 --out-dir out
python3 trade_quote.py serve --quotes-dir out --schedule out/schedule.csv
```

The sample produces an editable quote JSON and a PDF for USD 1,118.15. Open the
JSON's `acceptance_url` in a browser; for this fixed-date example choose
September 15, 2026 at 09:00. Acceptance creates a local eight-hour job and a
receipt. Stop the server with Ctrl-C. No external messages, calendar writes
or payments occur. The service binds to loopback by default; this package
is not a claim of public deployment or real customer installation.

Use `examples/request-missing.json` in the quote command with a separate
output directory to see the missing-height question. It produces no amount,
acceptance link or PDF. For actual work, enter supplied measurements, review
pricing rules, and use the appropriate issue date rather than the fixed demo
date. The original `README.md` describes the runtime; its test commands apply
to the source tree because tests are deliberately excluded from delivery.

Keep the output workspace when updating the application. Back it up when
all writers are stopped; do not remove active SQLite scheduling sidecars.
The schedule CSV is authoritative, and schedule/receipt files are not a
single crash-atomic transaction. This package changes no runtime behavior.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
