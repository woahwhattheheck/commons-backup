# Lantern printable HTML results

This is an additive printable-results companion for the existing Lantern result exporter. It does **not** replace or fork the current `results_export.py` JSON/CSV contract or the native browser download routes. It consumes the same `results_document()` allowlist, so ranking, event-finality, privacy fields, and read-only SQLite behavior stay owned by the current exporter.

Run after an event finishes:

```sh
python3 results_export_html.py --db /path/to/events.sqlite3 --event EVENT_ID --output results.html
```

The destination must be new. Publication reuses the current exporter's complete-file same-filesystem hard-link writer; existing files, directories, and dangling symlinks are refused rather than replaced. The SQLite database is opened through the current `ReadOnlyStore` and is not initialized or modified.

The HTML is UTF-8, self-contained, script-free, print-oriented, and deterministic for an unchanged finished event. It includes only the current public result document: event reference/title/room/scheduled window/question count, participant count, and final leaderboard fields `rank`, `name`, `points`, `answered`. It excludes reconnect references, individual answers, question text, and answer keys. Display names remain participant information and are HTML-escaped, not anonymized.

Focused checks:

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_results_export_html.py
python3 -B demo_results_export_html.py /tmp/lantern-results-demo.html
```

The focused suite exercises the real Lantern Store/SQLite path, current result-document semantics, subprocess CLI, complete-file publication, overwrite refusal, dangling-symlink refusal, escaping/privacy, deterministic bytes, empty events, and finality. The demo creates a temporary fictional event through the real loopback HTTP handler, exercises join/answer/retry/finish/reconnect, then runs the printable exporter as a subprocess. It contacts no external service and does not claim browser/printer/platform acceptance.

## Recovery provenance

This successor recovers the unique printable-HTML/demo intent from owner recovery attachment `lantern-results-export.zip` (`F0C0BS0J858`, SHA-256 `f88b3ef436609f92948c891e8ba20693a472f95418fd7eace9f211fcff588eaa`). The recovered packet's literal four-file transplant was intentionally rejected: current main already contained later, stronger result-export work from commit `689a071ec5f91a6c9f5c0a6b624a044fe3f858ed`, followed by native CSV/JSON HTTP/browser integration in `67d967753ff2055a0ba8cfae3869edb1403e88d3`. The old demo expected the superseded positional CLI and old three-format renderer, so it was not copied onto current main.

This file and its companion source/tests/demo are therefore a current-contract adaptation of the recovered **unique HTML value**, while the current JSON/CSV implementation and all existing Lantern peer paths remain untouched.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

