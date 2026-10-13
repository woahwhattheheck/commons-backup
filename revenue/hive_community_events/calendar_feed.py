#!/usr/bin/env python3
"""Download Lantern schedules as iCalendar, or serve them beside the existing app."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import sqlite3
import sys
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit, urlunsplit
import uuid


class CalendarError(Exception):
    """A calendar input or source-data error suitable for a CLI/HTTP response."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def public_url(value: str | None) -> str | None:
    """Validate an optional advertised app URL, without making any network call."""
    if value is None:
        return None
    if not isinstance(value, str) or any(ord(c) < 33 or ord(c) == 127 or c in '\\<>"' for c in value):
        raise CalendarError("Public URL must be an absolute HTTP(S) app-root URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (parsed.scheme not in ("https", "http") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError
        # RFC URI representation: no non-ASCII host or path bytes in URL fields.
        host = parsed.hostname.encode("idna").decode("ascii")
        if ":" in host:
            host = f"[{host}]"
        if port is not None:
            host += f":{port}"
        return urlunsplit((parsed.scheme, host, "/", "", ""))
    except (ValueError, UnicodeError):
        raise CalendarError("Public URL must be an absolute HTTP(S) app-root URL") from None


def text_value(value: Any) -> str:
    """Escape RFC 5545 TEXT; physical line breaks cannot become new properties."""
    if not isinstance(value, str):
        raise CalendarError("Calendar text must be a string")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if any(ord(c) < 32 and c not in "\n\t" for c in value) or "\x7f" in value:
        raise CalendarError("Calendar text contains an unsupported control character")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise CalendarError("Calendar text must be valid UTF-8") from None
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold_line(value: str) -> bytes:
    """Fold at UTF-8 character boundaries, with at most 75 octets per line."""
    if "\r" in value or "\n" in value:
        raise CalendarError("An iCalendar content line must not contain a raw newline")
    lines: list[bytes] = []
    current = bytearray()
    for char in value:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > 75:
            lines.append(bytes(current))
            current = bytearray(b" ")
        current.extend(encoded)
    lines.append(bytes(current))
    return b"\r\n".join(lines) + b"\r\n"


def utc_stamp(value: Any, *, end: bool = False) -> str:
    """RFC dates have second precision: cover, never shorten, fractional slots."""
    try:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError
        second = math.ceil(value) if end else math.floor(value)
        return datetime.fromtimestamp(second, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    except (ValueError, OverflowError, OSError):
        raise CalendarError("Event timestamps must be finite, nonnegative calendar dates") from None


def read_events(database: str | Path, *, event_id: str | None = None,
                room: str | None = None) -> list[dict[str, Any]]:
    """Read only six schedule fields in one SQLite snapshot; never create a DB."""
    query = "SELECT id,title,room,opens,ends,created FROM events"
    params: list[str] = []
    clauses = []
    for column, value in (("id", event_id), ("room", room)):
        if value is not None:
            clauses.append(f"{column}=?")
            params.append(value)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY opens,id"
    uri = Path(database).resolve().as_uri() + "?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        rows = [dict(row) for row in db.execute(query, params)]
    if event_id is not None and not rows:
        raise CalendarError("Event not found", 404)
    return rows


def render_calendar(events: list[dict[str, Any]], *, app_url: str | None = None) -> bytes:
    """Render only the immutable published schedule, not game state or answers."""
    app_url = public_url(app_url)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Commons//Lantern Calendar//EN",
             "CALSCALE:GREGORIAN"]
    seen: set[str] = set()
    for event in events:
        try:
            event_id = event["id"]
            if not isinstance(event_id, str) or not event_id or event_id in seen:
                raise CalendarError("Event IDs must be nonempty and unique")
            text_value(event_id)
            seen.add(event_id)
            start = utc_stamp(event["opens"])
            end = utc_stamp(event["ends"], end=True)
            if event["ends"] <= event["opens"]:
                raise CalendarError("Event end must follow its start")
            uid = uuid.uuid5(uuid.NAMESPACE_URL, "urn:commons:lantern:event:" + event_id)
            lines.extend([
                "BEGIN:VEVENT", f"UID:{uid}@lantern.commons.invalid",
                "DTSTAMP:" + utc_stamp(event["created"]), "DTSTART:" + start, "DTEND:" + end,
                "SUMMARY:" + text_value(event["title"]), "LOCATION:" + text_value(event["room"]),
                "DESCRIPTION:" + text_value(
                    "Free-entry community event; non-cash points. Open Lantern and choose this event. "
                    "This calendar contains the published schedule. See the app for live event status."),
                "TRANSP:TRANSPARENT",
            ])
            if app_url:
                lines.append("URL:" + app_url + "?event=" + quote(event_id, safe=""))
            lines.append("END:VEVENT")
        except KeyError as exc:
            raise CalendarError(f"Missing schedule field: {exc.args[0]}") from None
    lines.append("END:VCALENDAR")
    return b"".join(fold_line(line) for line in lines)


def calendar_page(events: list[dict[str, Any]]) -> bytes:
    cards = []
    for event in events:
        # Rendering through the same validator keeps HTML and download behavior aligned.
        render_calendar([event])
        title, room = html.escape(event["title"]), html.escape(event["room"])
        event_path = "/calendar/" + quote(event["id"], safe="") + ".ics"
        room_path = "/calendar.ics?room=" + quote(event["room"], safe="")
        start = datetime.fromtimestamp(math.floor(event["opens"]), timezone.utc).isoformat(timespec="seconds")
        end = datetime.fromtimestamp(math.ceil(event["ends"]), timezone.utc).isoformat(timespec="seconds")
        cards.append(f'<article><p class="eyebrow">{room}</p><h2>{title}</h2>'
                     f'<p><time>{start}</time><br>to <time>{end}</time></p>'
                     f'<a class="button" href="/?event={quote(event["id"], safe="")}">Open event</a> '
                     f'<a class="button" href="{event_path}">Download event</a> '
                     f'<a href="{room_path}">Room calendar</a></article>')
    content = "".join(cards) or '<p class="empty">No events yet. Create an event in Lantern, then return here.</p>'
    return ('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lantern · Event calendar</title><style>
:root{font-family:system-ui,sans-serif;color:#e7eef7;background:#101c2c;color-scheme:dark}
*{box-sizing:border-box}body{max-width:70rem;margin:auto;padding:2rem 1rem;line-height:1.6}
a{color:#a6d9ff;overflow-wrap:anywhere}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:.8rem}
h1{font-size:clamp(2rem,5vw,3.4rem);line-height:1.15}h2{font-size:1.4rem;overflow-wrap:anywhere}
header{max-width:48rem;margin-bottom:2rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,19rem),1fr));gap:1rem}
article{background:#1a2a40;border:1px solid #354860;border-radius:.8rem;padding:1.4rem;min-width:0}
.button{display:inline-block;border:1px solid #7594b8;border-radius:.4rem;padding:.5rem .9rem;text-decoration:none;margin:.2rem .6rem .2rem 0}
time{overflow-wrap:anywhere}footer{margin-top:2rem;color:#b7c7dc}a:focus-visible{outline:3px solid #fff;outline-offset:4px}
</style><header><p class="eyebrow">Lantern / Community events</p><h1>Keep the next round on your calendar.</h1>
<p>Download one event, a room, or the whole schedule. Times below are UTC; the exported file contains UTC instants.
The calendar includes event titles and rooms, never questions, answers, or participant records.</p>
<a class="button" href="/calendar.ics">Download all events</a><a href="/">Open Lantern</a>
<p>For an updating subscription, copy the calendar link into a calendar client's URL subscription feature.
A downloaded file is a snapshot. Subscriptions require a reachable server; refreshing is controlled by the calendar client.</p></header>
<section class="grid">''' + content + '''</section><footer>
Published schedule only. Finishing a game does not cancel or reschedule its calendar entry.
Use Lantern for current game status. No invitations or emails are sent by this page.</footer></html>''').encode("utf-8")


def make_calendar_handler(store: Any, *, app_url: str | None = None):
    """Add calendar GET/HEAD routes; inherit the owner's existing UI and API."""
    from app import make_handler

    app_url = public_url(app_url)
    parent = make_handler(store)

    class CalendarHandler(parent):
        def calendar_response(self, *, head: bool = False) -> bool:
            path = urlsplit(self.path)
            is_feed = path.path == "/calendar.ics"
            is_event = path.path.startswith("/calendar/") and path.path.endswith(".ics")
            if path.path != "/calendar" and not is_feed and not is_event:
                return False
            try:
                query = parse_qs(path.query, keep_blank_values=True, errors="strict")
                rooms = query.get("room", [])
                if len(rooms) > 1:
                    raise CalendarError("Specify one room per calendar URL")
                event_id = unquote(path.path[len("/calendar/"):-4], errors="strict") if is_event else None
                events = read_events(store.database, event_id=event_id, room=rooms[0] if rooms else None)
                body = render_calendar(events, app_url=app_url) if is_feed or is_event else calendar_page(events)
                content_type = "text/calendar; charset=utf-8" if is_feed or is_event else "text/html; charset=utf-8"
                etag = '"' + hashlib.sha256(body).hexdigest() + '"'
                matches = [part.strip().removeprefix("W/") for part in self.headers.get("If-None-Match", "").split(",")]
                status = 304 if etag in matches or "*" in matches else 200
                self.send_response(status)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                if status == 200:
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    if is_feed or is_event:
                        self.send_header("Content-Disposition", 'attachment; filename="lantern-events.ics"')
                self.end_headers()
                if status == 200 and not head:
                    self.wfile.write(body)
            except (CalendarError, UnicodeError, ValueError) as exc:
                status = exc.status if isinstance(exc, CalendarError) else 400
                self.calendar_error(status, str(exc), head)
            except sqlite3.Error:
                self.calendar_error(503, "Calendar storage is unavailable; retry later", head)
            return True

        def calendar_error(self, status: int, message: str, head: bool):
            body = json.dumps({"error": message}, ensure_ascii=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def do_GET(self):
            if not self.calendar_response():
                super().do_GET()

        def do_HEAD(self):
            if not self.calendar_response(head=True):
                self.send_error(405, "HEAD is available on calendar routes")

    return CalendarHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Write an existing database's calendar to stdout")
    serve = commands.add_parser("serve", help="Run the existing Lantern app with calendar downloads")
    for command in (export, serve):
        command.add_argument("--db", required=True, help="Path to the existing Lantern SQLite database")
        command.add_argument("--public-url", help="Optional advertised HTTP(S) app-root URL; no network requests")
    selection = export.add_mutually_exclusive_group()
    selection.add_argument("--event", help="Export one event ID")
    selection.add_argument("--room", help="Export one exact room name")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        advertised = public_url(args.public_url)
        if args.command == "export":
            body = render_calendar(read_events(args.db, event_id=args.event, room=args.room), app_url=advertised)
            sys.stdout.buffer.write(body)
        else:
            from http.server import ThreadingHTTPServer
            from app import Store

            handler = make_calendar_handler(Store(args.db), app_url=advertised)
            with ThreadingHTTPServer((args.host, args.port), handler) as server:
                print(f"Lantern calendar: http://{args.host}:{server.server_port}/calendar", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        return 0
    except (CalendarError, sqlite3.Error, OSError) as exc:
        print(f"Calendar error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
