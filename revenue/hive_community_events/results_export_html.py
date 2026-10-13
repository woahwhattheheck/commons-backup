#!/usr/bin/env python3
"""Render a finished Lantern leaderboard as deterministic printable HTML."""
from __future__ import annotations

import argparse
import html
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import Problem
from results_export import ReadOnlyStore, results_document, write_new_output


def _utc(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def render_html(document: dict) -> bytes:
    """Render the current allowlisted result document; never add hidden app state."""
    event = document["event"]
    esc = lambda value: html.escape(str(value), quote=True)
    rows = "\n".join(
        f'<tr><td>{row["rank"]}</td><th scope="row">{esc(row["name"])}</th>'
        f'<td>{row["points"]}</td><td>{row["answered"]} / {event["question_count"]}</td></tr>'
        for row in document["leaderboard"]
    )
    if not rows:
        rows = '<tr><td colspan="4">No participants joined this event.</td></tr>'
    body = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(event["title"])} — Lantern results</title>
<style>
body{{font-family:system-ui,sans-serif;line-height:1.5;margin:2rem auto;padding:0 1rem;max-width:54rem}}
h1{{line-height:1.2;overflow-wrap:anywhere}}header p{{margin:.35rem 0}}
table{{width:100%;border-collapse:collapse;margin:1.6rem 0;table-layout:fixed}}
th,td{{text-align:left;border-bottom:1px solid;padding:.65rem .35rem;overflow-wrap:anywhere}}
th:first-child,td:first-child{{width:12%}}th[scope=row]{{font-weight:500}}
footer{{font-size:.85rem}}@media print{{body{{margin:0;max-width:none}}tr{{break-inside:avoid}}}}
</style>
</head>
<body>
<header>
<p>LANTERN · FINISHED EVENT</p>
<h1>{esc(event["title"])}</h1>
<p>Room: {esc(event["room"])}</p>
<p>{document["participants"]} participants · {event["question_count"]} questions · free-entry, non-cash points</p>
<p>Scheduled window: {esc(_utc(event["opens"]))} — {esc(_utc(event["ends"]))}</p>
</header>
<table><caption>Final standings. Ties share their competition rank.</caption>
<thead><tr><th scope="col">Rank</th><th scope="col">Display name</th><th scope="col">Points</th><th scope="col">Answered</th></tr></thead>
<tbody>{rows}</tbody></table>
<footer>This report contains participant display names. Share only with the intended audience.
It excludes reconnect references, individual answers, question text, and answer keys.
Event reference: {esc(event["id"])}</footer>
</body>
</html>
'''
    return body.encode("utf-8")


def export_html(store, event_id: str) -> bytes:
    return render_html(results_document(store, event_id))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Existing Lantern SQLite database")
    parser.add_argument("--event", required=True, help="Event reference from Lantern")
    parser.add_argument("--output", required=True, help="New .html path; existing paths are never replaced")
    args = parser.parse_args(argv)
    try:
        data = export_html(ReadOnlyStore(args.db), args.event)
        write_new_output(args.output, data)
    except (Problem, OSError, ValueError, sqlite3.DatabaseError) as error:
        print(f"HTML export failed: {error}", file=sys.stderr)
        return 2
    print(f"Exported printable HTML results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
