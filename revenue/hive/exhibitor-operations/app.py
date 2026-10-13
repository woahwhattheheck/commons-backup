#!/usr/bin/env python3
"""Exhibitor Operations: a dependency-free, single-organizer event workspace."""
from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from email.policy import SMTP
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote, urlsplit
import uuid
import zipfile

MAX_ASSET = 8 * 1024 * 1024
MAX_BODY = 12 * 1024 * 1024
ROOT = Path(__file__).resolve().parent


class DeskError(ValueError):
    status = 400


class Missing(DeskError):
    status = 404


class Conflict(DeskError):
    status = 409


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text(value, name, *, required=False, limit=5000) -> str:
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise DeskError(f"{name}: expected text of at most {limit} characters")
    value = value.strip()
    if required and not value:
        raise DeskError(f"{name} is required")
    return value


def integer(value, name, maximum=1_000_000) -> int:
    if isinstance(value, str) and len(value) <= 32 and value.isascii() and value.isdigit():
        value = int(value)
    if type(value) is not int or not 0 <= value <= maximum:
        raise DeskError(f"{name}: expected a whole number from 0 to {maximum}")
    return value


def dimension(value, name) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise DeskError(f"{name}: expected metres")
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise DeskError(f"{name}: expected metres") from exc
    if not d.is_finite() or not Decimal("0.1") <= d <= 100 or d.as_tuple().exponent < -2:
        raise DeskError(f"{name}: use 0.1–100 metres, at most two decimal places")
    return format(d.normalize(), "f")


def instant(value, name) -> str:
    value = text(value, name, required=True, limit=50)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("offset required")
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OverflowError) as exc:
        raise DeskError(f"{name}: use an ISO date/time with a time-zone offset") from exc


def event_fields(data) -> dict:
    if not isinstance(data, dict):
        raise DeskError("Event must be an object")
    result = {k: text(data.get(k, ""), k, required=k in ("name", "venue"))
              for k in ("name", "venue", "brief")}
    if any(c in result["name"] for c in "\r\n"):
        raise DeskError("name: use one line")
    result.update({k: instant(data.get(k, ""), k) for k in ("starts_at", "deadline_at")})
    if result["deadline_at"] > result["starts_at"]:
        raise DeskError("Materials deadline must not be after the event starts")
    return result


def exhibitor_fields(data) -> dict:
    if not isinstance(data, dict):
        raise DeskError("Exhibitor must be an object")
    result = {k: text(data.get(k, ""), k, required=k in ("company", "contact_name", "email"))
              for k in ("company", "contact_name", "email", "booth_code", "notes")}
    email = result["email"]
    if len(email) > 254 or not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", email):
        raise DeskError("email: enter one email address")
    for key in ("company", "contact_name", "booth_code"):
        if "\n" in result[key] or "\r" in result[key]:
            raise DeskError(f"{key}: use one line")
    result["booth_code"] = result["booth_code"].upper()
    for key in ("width_m", "depth_m"):
        result[key] = dimension(data.get(key, ""), key)
    result["power_w"] = integer(data.get("power_w", 0), "power_w")
    return result


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exhibitors (
 id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id), revision INTEGER NOT NULL,
 booth_code TEXT NOT NULL, document TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS booth_per_event ON exhibitors(event_id, booth_code) WHERE booth_code <> '';
CREATE TABLE IF NOT EXISTS changes (
 id TEXT PRIMARY KEY, exhibitor_id TEXT NOT NULL REFERENCES exhibitors(id),
 base_revision INTEGER NOT NULL, before_document TEXT NOT NULL, proposed_document TEXT NOT NULL,
 reason TEXT NOT NULL, status TEXT NOT NULL, resolution TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS assets (
 id TEXT PRIMARY KEY, exhibitor_id TEXT NOT NULL REFERENCES exhibitors(id),
 filename TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
 data BLOB NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(exhibitor_id, filename, sha256));
"""


class Store:
    def __init__(self, database):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self, *, write=False):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def record(row):
        if row is None:
            raise Missing("Record not found")
        result = dict(row)
        result.update(json.loads(result.pop("document")))
        return result

    def _event(self, db, event_id):
        return self.record(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone())

    def _exhibitor(self, db, event_id, exhibitor_id):
        return self.record(db.execute("SELECT * FROM exhibitors WHERE event_id=? AND id=?",
                                      (event_id, exhibitor_id)).fetchone())

    @staticmethod
    def _same_revision(record, expected):
        expected = integer(expected, "expected_revision")
        if record["revision"] != expected:
            raise Conflict(f"This record changed. Reopen revision {record['revision']} before saving.")

    def list_events(self):
        with self.connection() as db:
            return [self.record(row) for row in db.execute("SELECT * FROM events ORDER BY updated_at DESC, id")]

    def save_event(self, data, event_id=None):
        fields = event_fields(data)
        with self.connection(write=True) as db:
            revision = 1
            if event_id:
                previous = self._event(db, event_id)
                self._same_revision(previous, data.get("expected_revision"))
                revision = previous["revision"] + 1
                db.execute("UPDATE events SET revision=?, document=?, updated_at=? WHERE id=?",
                           (revision, json.dumps(fields), now(), event_id))
            else:
                event_id = uuid.uuid4().hex
                db.execute("INSERT INTO events VALUES (?, ?, ?, ?)",
                           (event_id, revision, json.dumps(fields), now()))
            return self._event(db, event_id)

    def _write_exhibitor(self, db, event_id, fields, exhibitor_id=None, expected=None):
        self._event(db, event_id)
        try:
            if exhibitor_id:
                old = self._exhibitor(db, event_id, exhibitor_id)
                self._same_revision(old, expected)
                db.execute("UPDATE exhibitors SET revision=?, booth_code=?, document=?, updated_at=? WHERE id=?",
                           (old["revision"] + 1, fields["booth_code"], json.dumps(fields), now(), exhibitor_id))
            else:
                exhibitor_id = uuid.uuid4().hex
                db.execute("INSERT INTO exhibitors VALUES (?, ?, ?, ?, ?, ?)",
                           (exhibitor_id, event_id, 1, fields["booth_code"], json.dumps(fields), now()))
        except sqlite3.IntegrityError as exc:
            raise Conflict("That booth code is already assigned in this event") from exc
        return self._exhibitor(db, event_id, exhibitor_id)

    def save_exhibitor(self, event_id, data, exhibitor_id=None):
        fields = exhibitor_fields(data)
        with self.connection(write=True) as db:
            return self._write_exhibitor(db, event_id, fields, exhibitor_id, data.get("expected_revision"))

    def detail(self, event_id, exhibitor_id=None):
        with self.connection() as db:
            event = self._event(db, event_id)
            if exhibitor_id:
                exhibitors = [self._exhibitor(db, event_id, exhibitor_id)]
            else:
                exhibitors = [self.record(row) for row in db.execute(
                    "SELECT * FROM exhibitors WHERE event_id=? ORDER BY booth_code, id", (event_id,))]
            for ex in exhibitors:
                ex["assets"] = [dict(r) for r in db.execute(
                    "SELECT id,filename,kind,sha256,size,created_at FROM assets WHERE exhibitor_id=? ORDER BY created_at,id",
                    (ex["id"],))]
                ex["changes"] = []
                for r in db.execute("SELECT * FROM changes WHERE exhibitor_id=? ORDER BY created_at,id", (ex["id"],)):
                    change = dict(r)
                    change["before"] = json.loads(change.pop("before_document"))
                    change["proposed"] = json.loads(change.pop("proposed_document"))
                    ex["changes"].append(change)
            return {"event": event, "exhibitors": exhibitors}

    def request_change(self, event_id, exhibitor_id, data):
        fields = exhibitor_fields(data.get("proposed"))
        reason = text(data.get("reason", ""), "reason", required=True)
        with self.connection(write=True) as db:
            old = self._exhibitor(db, event_id, exhibitor_id)
            self._same_revision(old, data.get("expected_revision"))
            old_fields = exhibitor_fields(old)
            if fields == old_fields:
                raise DeskError("Change request has no changed requirements")
            change_id = uuid.uuid4().hex
            db.execute("INSERT INTO changes VALUES (?,?,?,?,?,?,?,'',?,NULL)",
                       (change_id, exhibitor_id, old["revision"], json.dumps(old_fields),
                        json.dumps(fields), reason, "pending", now()))
            return {"id": change_id, "status": "pending", "base_revision": old["revision"]}

    def resolve_change(self, event_id, exhibitor_id, change_id, data):
        decision = data.get("decision")
        if decision not in ("apply", "dismiss"):
            raise DeskError("decision must be apply or dismiss")
        resolution = text(data.get("resolution", ""), "resolution", required=True)
        with self.connection(write=True) as db:
            self._exhibitor(db, event_id, exhibitor_id)
            row = db.execute("SELECT * FROM changes WHERE id=? AND exhibitor_id=?", (change_id, exhibitor_id)).fetchone()
            if row is None:
                raise Missing("Change request not found")
            if row["status"] != "pending":
                raise Conflict("This change request has already been resolved")
            if decision == "apply":
                self._write_exhibitor(db, event_id, json.loads(row["proposed_document"]),
                                     exhibitor_id, row["base_revision"])
            status = "applied" if decision == "apply" else "dismissed"
            db.execute("UPDATE changes SET status=?,resolution=?,resolved_at=? WHERE id=?",
                       (status, resolution, now(), change_id))
            return {"id": change_id, "status": status}

    def add_asset(self, event_id, exhibitor_id, data):
        filename = data.get("filename", "")
        text(filename, "filename", required=True, limit=240)  # Validate without changing the original filename.
        if any(c in filename for c in ("/", "\\", "\r", "\n")) or filename in (".", ".."):
            raise DeskError("filename must be a plain file name")
        kind = text(data.get("kind", "asset"), "kind", required=True, limit=80)
        encoded = data.get("base64")
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_ASSET + 2) // 3):
            raise DeskError("Asset exceeds the 8 MiB per-file limit")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise DeskError("Asset is not valid base64") from exc
        if not payload or len(payload) > MAX_ASSET:
            raise DeskError("Asset must contain 1 byte to 8 MiB")
        digest = hashlib.sha256(payload).hexdigest()
        with self.connection(write=True) as db:
            self._exhibitor(db, event_id, exhibitor_id)
            db.execute("INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?,?,?)",
                       (uuid.uuid4().hex, exhibitor_id, filename, kind, digest, len(payload), payload, now()))
            row = db.execute("SELECT id,filename,kind,sha256,size,created_at FROM assets WHERE exhibitor_id=? AND filename=? AND sha256=?",
                             (exhibitor_id, filename, digest)).fetchone()
            return dict(row)

    def asset(self, event_id, exhibitor_id, asset_id):
        with self.connection() as db:
            self._exhibitor(db, event_id, exhibitor_id)
            row = db.execute("SELECT * FROM assets WHERE exhibitor_id=? AND id=?", (exhibitor_id, asset_id)).fetchone()
            if row is None:
                raise Missing("Asset not found")
            return dict(row)

    def packet(self, event_id):
        # The read transaction holds one coherent snapshot for manifest and original bytes.
        with self.connection() as db:
            event = self._event(db, event_id)
            exs = [self.record(r) for r in db.execute("SELECT * FROM exhibitors WHERE event_id=? ORDER BY id", (event_id,))]
            files = {"event.json": json.dumps(event, ensure_ascii=False, indent=2).encode(),
                     "exhibitors.json": json.dumps(exs, ensure_ascii=False, indent=2).encode(),
                     "floor-plan.csv": floor_csv(exs), "deadlines.ics": calendar(event)}
            changes, assets = [], []
            for ex in exs:
                files[f"reminders/{ex['id']}.eml"] = reminder(event, ex)
                for row in db.execute("SELECT * FROM assets WHERE exhibitor_id=?", (ex["id"],)):
                    files[f"assets/{ex['id']}/{row['id']}/{row['filename']}"] = row["data"]
                    assets.append({k: row[k] for k in row.keys() if k != "data"})
                for row in db.execute("SELECT * FROM changes WHERE exhibitor_id=? ORDER BY created_at,id", (ex["id"],)):
                    changes.append(dict(row))
            files["assets.json"] = json.dumps(assets, ensure_ascii=False, indent=2).encode()
            files["changes.json"] = json.dumps(changes, ensure_ascii=False, indent=2).encode()
            manifest = {path: {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()} for path, value in sorted(files.items())}
            files["MANIFEST.json"] = json.dumps(manifest, indent=2).encode()
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
                for path, value in sorted(files.items()):
                    z.writestr(path, value)
            return output.getvalue()


def csv_cell(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def floor_csv(exhibitors) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["exhibitor_id", "company", "booth_code", "width_m", "depth_m", "area_m2", "power_w", "requirements", "revision"])
    for ex in exhibitors:
        row = [ex["id"], ex["company"], ex["booth_code"], ex["width_m"], ex["depth_m"],
               format(Decimal(ex["width_m"]) * Decimal(ex["depth_m"]), "f"), ex["power_w"], ex["notes"], ex["revision"]]
        writer.writerow([csv_cell(v) for v in row])
    return out.getvalue().encode("utf-8-sig")


def ics_escape(value):
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold_line(line):
    pieces, chunk = [], ""
    for char in line:
        if len((chunk + char).encode()) > 75:
            pieces.append(chunk)
            chunk = " "
        chunk += char
    pieces.append(chunk)
    return "\r\n".join(pieces)


def calendar(event) -> bytes:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Commons//Exhibitor Operations//EN", "CALSCALE:GREGORIAN"]
    for key, title in (("deadline_at", "Exhibitor materials due"), ("starts_at", "Event begins")):
        stamp = datetime.fromisoformat(event[key]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        updated = datetime.fromisoformat(event["updated_at"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines += ["BEGIN:VEVENT", f"UID:{event['id']}-{key}@exhibitor-operations", f"SEQUENCE:{event['revision']}",
                  f"DTSTAMP:{updated}", f"DTSTART:{stamp}", "SUMMARY:" + ics_escape(f"{event['name']}: {title}"),
                  "LOCATION:" + ics_escape(event["venue"]), "DESCRIPTION:" + ics_escape(event["brief"]), "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(fold_line(line) for line in lines) + "\r\n").encode()


def reminder(event, ex) -> bytes:
    msg = EmailMessage(policy=SMTP)
    msg["To"] = ex["email"]
    msg["Subject"] = f"{event['name']}: exhibitor materials deadline"
    msg["X-Unsent"] = "1"
    msg.set_content(f"Hello {ex['contact_name']},\n\nThe current materials deadline for {event['name']} is {event['deadline_at']} (UTC).\n"
                    f"Event begins: {event['starts_at']} (UTC)\nVenue: {event['venue']}\n"
                    f"Booth: {ex['booth_code'] or 'Not assigned'}; {ex['width_m']} × {ex['depth_m']} m; power {ex['power_w']} W.\n"
                    f"Requirements: {ex['notes'] or 'None recorded'}\n\n{event['brief']}\n\n"
                    f"Draft generated from event revision {event['revision']} and exhibitor revision {ex['revision']}.\n"
                    "Please replace the sender/signature and review before sending.\n")
    return msg.as_bytes()


def handler_for(store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ExhibitorDesk/1.0"

        def log_message(self, fmt, *args):
            pass  # Operational customer records are not copied into request logs.

        def response(self, body, kind="application/json; charset=utf-8", status=200, filename=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename, safe=""))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.dispatch(False)

        def do_POST(self):
            self.dispatch(True)

        def dispatch(self, write):
            try:
                parts = [p for p in urlsplit(self.path).path.split("/") if p]
                data = None
                if write:
                    length = self.headers.get("Content-Length", "")
                    if not length.isascii() or not length.isdigit() or not 0 < int(length) <= MAX_BODY:
                        raise DeskError("Request body must contain 1 byte to 12 MiB")
                    if self.headers.get_content_type() != "application/json":
                        raise DeskError("Use application/json")
                    self.connection.settimeout(15)
                    raw = self.rfile.read(int(length))
                    if len(raw) != int(length):
                        raise DeskError("Incomplete request body")
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise DeskError("Request body must be an object")
                if not write and (not parts or parts == ["index.html"] or parts == ["desk.js"]):
                    filename = "desk.js" if parts == ["desk.js"] else "index.html"
                    return self.response((ROOT / filename).read_bytes(), "text/javascript; charset=utf-8" if filename.endswith("js") else "text/html; charset=utf-8")
                if parts == ["api", "events"]:
                    return self.response(store.save_event(data) if write else store.list_events())
                if len(parts) >= 3 and parts[:2] == ["api", "events"]:
                    event_id = parts[2]
                    if len(parts) == 3:
                        return self.response(store.save_event(data, event_id) if write else store.detail(event_id))
                    if len(parts) == 4 and not write:
                        if parts[3] == "packet.zip":
                            return self.response(store.packet(event_id), "application/zip", filename="exhibitor-packet.zip")
                        detail = store.detail(event_id)
                        if parts[3] == "floor-plan.csv":
                            return self.response(floor_csv(detail["exhibitors"]), "text/csv; charset=utf-8", filename="floor-plan.csv")
                        if parts[3] == "deadlines.ics":
                            return self.response(calendar(detail["event"]), "text/calendar; charset=utf-8", filename="deadlines.ics")
                    if len(parts) >= 4 and parts[3] == "exhibitors":
                        if len(parts) == 4 and write:
                            return self.response(store.save_exhibitor(event_id, data))
                        if len(parts) >= 5:
                            exid = parts[4]
                            if len(parts) == 5:
                                return self.response(store.save_exhibitor(event_id, data, exid) if write else store.detail(event_id, exid))
                            if len(parts) == 6:
                                if parts[5] == "changes" and write:
                                    return self.response(store.request_change(event_id, exid, data))
                                if parts[5] == "assets" and write:
                                    return self.response(store.add_asset(event_id, exid, data))
                                if parts[5] == "reminder.eml" and not write:
                                    detail = store.detail(event_id, exid)
                                    return self.response(reminder(detail["event"], detail["exhibitors"][0]), "message/rfc822", filename="reminder-draft.eml")
                            if len(parts) == 7:
                                if parts[5] == "changes" and write:
                                    return self.response(store.resolve_change(event_id, exid, parts[6], data))
                                if parts[5] == "assets" and not write:
                                    asset = store.asset(event_id, exid, parts[6])
                                    return self.response(asset["data"], "application/octet-stream", filename=asset["filename"])
                raise Missing("Route not found")
            except DeskError as exc:
                self.response({"error": str(exc)}, status=exc.status)
            except (json.JSONDecodeError, UnicodeError, ValueError):
                self.response({"error": "Invalid UTF-8 JSON"}, status=400)
            except (TimeoutError, ConnectionError):
                self.close_connection = True
            except sqlite3.OperationalError:
                self.response({"error": "Database unavailable; retry the operation"}, status=503)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(Path.home() / ".exhibitor-operations" / "events.sqlite3"))
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--demo", action="store_true", help="Seed one clearly synthetic event when the database is empty")
    args = parser.parse_args()
    store = Store(args.database)
    if args.demo and not store.list_events():
        event = store.save_event({"name": "SAMPLE — Makers Expo", "venue": "Example Hall (synthetic)",
                                  "starts_at": "2026-10-15T09:00:00-04:00", "deadline_at": "2026-10-01T17:00:00-04:00",
                                  "brief": "Synthetic demonstration only. Upload a logo and specify power and loading requirements."})
        store.save_exhibitor(event["id"], {"company": "Sample Ceramics", "contact_name": "Example Coordinator",
                                            "email": "coordinator@example.invalid", "booth_code": "A01", "width_m": "3", "depth_m": "3",
                                            "power_w": 500, "notes": "One table; step-free loading requested."})
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(store))
    print(f"Exhibitor Operations: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
