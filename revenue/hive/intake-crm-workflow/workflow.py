#!/usr/bin/env python3
"""Residential-cleaning intake, local CRM, tasks, and resumable delivery. Python 3.11+."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

FIELDS = ("name", "email", "phone", "address", "service", "preferred_date", "notes")
DEFAULT_MAPPING = {field: field for field in FIELDS}
TASKS = ("Confirm requested service and preferred date", "Assign cleaning team", "Complete cleaning and follow up")
MAX_BODY = 131072


class InputError(ValueError):
    """An intake or configuration needs correction."""


class Conflict(InputError):
    """An operation ID was reused for different contents."""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def object_value(value):
    if not isinstance(value, dict):
        raise InputError("Expected a JSON object.")
    return value


def text(value, label, maximum=4000):
    if not isinstance(value, str) or len(value) > maximum:
        raise InputError(f"{label} must be text of at most {maximum} characters.")
    return value.strip()


def mapping_value(mapping):
    object_value(mapping)
    result = dict(DEFAULT_MAPPING)
    if set(mapping) - set(FIELDS):
        raise InputError("Mapping contains an unknown destination field.")
    for field, source in mapping.items():
        result[field] = text(source, "Source field", 120)
        if not result[field]:
            raise InputError("Source field cannot be blank.")
    if len(set(result.values())) != len(result):
        raise InputError("Each destination needs a distinct source field.")
    return result


def normalize(payload, mapping):
    object_value(payload)
    fields = {field: text(payload.get(mapping[field], ""), field) for field in FIELDS}
    for field in ("name", "email", "address", "service"):
        if not fields[field]:
            raise InputError(f"{field} is required.")
    fields["email"] = fields["email"].casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", fields["email"]):
        raise InputError("Supply a contact email address.")
    if fields["preferred_date"]:
        try:
            parsed = date.fromisoformat(fields["preferred_date"])
        except ValueError as exc:
            raise InputError("preferred_date must be YYYY-MM-DD.") from exc
        if parsed.isoformat() != fields["preferred_date"]:
            raise InputError("preferred_date must be YYYY-MM-DD.")
    return fields


def endpoint_value(endpoint):
    value = text(endpoint, "Delivery endpoint", 2048)
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise InputError("Use an HTTP(S) receiver URL without embedded credentials or fragment.")
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # A redirect is not an acknowledgement of the POST payload.


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    phone TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS intakes (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                    customer_id TEXT NOT NULL REFERENCES customers(id), created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, intake_id TEXT UNIQUE NOT NULL REFERENCES intakes(id),
                    customer_id TEXT NOT NULL REFERENCES customers(id), address TEXT NOT NULL,
                    service TEXT NOT NULL, preferred_date TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    position INTEGER NOT NULL, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(job_id,position));
                CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL REFERENCES jobs(id),
                    payload TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
                    lease_token TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '',
                    delivered_at REAL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS inbox (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES ('mapping',?)", (encoded(DEFAULT_MAPPING),))
            db.execute("INSERT OR IGNORE INTO settings VALUES ('endpoint','\"\"')")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def settings(self):
        with self.connection() as db:
            return {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM settings")}

    def configure(self, value):
        object_value(value)
        if set(value) - {"mapping", "endpoint"}:
            raise InputError("Unknown configuration field.")
        updates = {}
        if "mapping" in value:
            updates["mapping"] = mapping_value(value["mapping"])
        if "endpoint" in value:
            updates["endpoint"] = endpoint_value(value["endpoint"])
        with self.transaction() as db:
            for key, item in updates.items():
                db.execute("UPDATE settings SET value=? WHERE key=?", (encoded(item), key))
        return self.settings()

    def intake(self, request):
        object_value(request)
        ident = text(request.get("id"), "Intake id", 120)
        if not ident or not re.fullmatch(r"[A-Za-z0-9._:-]+", ident):
            raise InputError("Intake id needs letters, digits, dots, underscores, colons or hyphens.")
        with self.transaction() as db:
            mapping = json.loads(db.execute("SELECT value FROM settings WHERE key='mapping'").fetchone()[0])
            source = object_value(request.get("payload"))
            fingerprint = digest(source)
            existing = db.execute("SELECT fingerprint FROM intakes WHERE id=?", (ident,)).fetchone()
            if existing:
                if existing[0] != fingerprint:
                    raise Conflict("This intake id already records different contents; use a new source id for a new job.")
                row = db.execute("SELECT id,customer_id FROM jobs WHERE intake_id=?", (ident,)).fetchone()
                return {"created": False, "intake_id": ident, "job_id": row["id"], "customer_id": row["customer_id"]}
            payload = normalize(source, mapping)
            customer = db.execute("SELECT id FROM customers WHERE email=?", (payload["email"],)).fetchone()
            customer_id = customer[0] if customer else str(uuid.uuid4())
            now = time.time()
            if customer is None:
                db.execute("INSERT INTO customers VALUES (?,?,?,?,?)", (customer_id, payload["email"], payload["name"], payload["phone"], now))
            db.execute("INSERT INTO intakes VALUES (?,?,?,?,?)", (ident, fingerprint, encoded(payload), customer_id, now))
            job_id = str(uuid.uuid4())
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?)", (job_id, ident, customer_id, payload["address"], payload["service"], payload["preferred_date"], "new"))
            tasks = []
            for position, title in enumerate(TASKS):
                task_id = str(uuid.uuid4())
                db.execute("INSERT INTO tasks VALUES (?,?,?,?,0)", (task_id, job_id, position, title))
                tasks.append({"id": task_id, "title": title, "position": position})
            event_id = "intake:" + ident
            event = {"event_id": event_id, "type": "cleaning.job.created", "job_id": job_id,
                     "customer_id": customer_id, "intake_id": ident, "contact": payload, "tasks": tasks}
            db.execute("INSERT INTO outbox (id,job_id,payload,state,created) VALUES (?,?,?,'pending',?)", (event_id, job_id, encoded(event), now))
            return {"created": True, "intake_id": ident, "job_id": job_id, "customer_id": customer_id}

    def complete_task(self, ident, done):
        if not isinstance(done, bool):
            raise InputError("done must be true or false.")
        with self.transaction() as db:
            task = db.execute("SELECT job_id FROM tasks WHERE id=?", (ident,)).fetchone()
            if task is None:
                raise InputError("Task does not exist.")
            db.execute("UPDATE tasks SET done=? WHERE id=?", (int(done), ident))
            remaining = db.execute("SELECT COUNT(*) FROM tasks WHERE job_id=? AND done=0", (task[0],)).fetchone()[0]
            db.execute("UPDATE jobs SET status=? WHERE id=?", ("complete" if remaining == 0 else "in_progress", task[0]))
        return {"id": ident, "done": done}

    def snapshot(self):
        with self.transaction() as db:
            return {table: [dict(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                    for table in ("customers", "intakes", "jobs", "tasks", "outbox", "notifications", "inbox")}

    def retry(self, ident):
        with self.transaction() as db:
            row = db.execute("SELECT state,lease_until FROM outbox WHERE id=?", (ident,)).fetchone()
            if row is None:
                raise InputError("Delivery does not exist.")
            if row["state"] == "delivered":
                return {"id": ident, "state": "delivered"}
            if row["state"] == "sending" and row["lease_until"] > time.time():
                raise Conflict("Delivery is currently in progress.")
            db.execute("UPDATE outbox SET state='pending',next_attempt=0,lease_until=0,lease_token='' WHERE id=?", (ident,))
        return {"id": ident, "state": "pending"}

    def receive(self, event_id, payload):
        ident = text(event_id, "Idempotency-Key", 160)
        object_value(payload)
        if not ident or payload.get("event_id") != ident:
            raise InputError("Idempotency-Key must match event_id.")
        fingerprint = digest(payload)
        with self.transaction() as db:
            row = db.execute("SELECT fingerprint FROM inbox WHERE id=?", (ident,)).fetchone()
            if row and row[0] != fingerprint:
                raise Conflict("This event id already records different contents.")
            if not row:
                db.execute("INSERT INTO inbox VALUES (?,?,?,?)", (ident, fingerprint, encoded(payload), time.time()))
        return {"accepted": True, "duplicate": row is not None, "event_id": ident}

    def process_one(self, now=None, ident=None):
        if ident is not None:
            ident = text(ident, "Delivery id", 160)
            if not ident:
                raise InputError("Delivery id cannot be blank.")
        now = time.time() if now is None else now
        token = str(uuid.uuid4())
        with self.transaction() as db:
            row = db.execute("""SELECT * FROM outbox WHERE
                ((state IN ('pending','retry') AND next_attempt<=?) OR
                 (state='sending' AND lease_until<=?)) AND (? IS NULL OR id=?)
                ORDER BY created,id LIMIT 1""", (now, now, ident, ident)).fetchone()
            if row is None:
                return {"processed": False}
            endpoint = json.loads(db.execute("SELECT value FROM settings WHERE key='endpoint'").fetchone()[0])
            if not endpoint:
                db.execute("INSERT OR IGNORE INTO notifications VALUES (?,?,?,?)", (row["id"], row["job_id"], row["payload"], now))
                db.execute("UPDATE outbox SET state='delivered',attempts=attempts+1,delivered_at=?,last_error='',lease_token='',lease_until=0 WHERE id=?", (now, row["id"]))
                return {"processed": True, "id": row["id"], "state": "delivered", "transport": "local"}
            db.execute("UPDATE outbox SET state='sending',attempts=attempts+1,lease_until=?,lease_token=? WHERE id=?", (now + 60, token, row["id"]))
        error = ""
        try:
            req = Request(endpoint, data=row["payload"].encode(), headers={"Content-Type": "application/json", "Idempotency-Key": row["id"]}, method="POST")
            with build_opener(NoRedirect).open(req, timeout=10) as response:
                if not 200 <= response.status < 300:
                    error = "Receiver returned a non-success status."
                # A 2xx is the receiver's acknowledgement. No response body or URLs are retained.
        except HTTPError as exc:
            error = f"Receiver returned HTTP {exc.code}."
        except (URLError, TimeoutError, OSError, ValueError):
            error = "Delivery did not receive an acknowledgement; retry uses the same event id."
        completed = time.time()
        with self.transaction() as db:
            if error:
                state = "retry"
                delay = min(3600, 2 ** min(row["attempts"] + 1, 11))
                result = db.execute("UPDATE outbox SET state='retry',next_attempt=?,last_error=?,lease_until=0,lease_token='' WHERE id=? AND lease_token=?", (completed + delay, error, row["id"], token))
            else:
                state = "delivered"
                result = db.execute("UPDATE outbox SET state='delivered',delivered_at=?,last_error='',lease_until=0,lease_token='' WHERE id=? AND lease_token=?", (completed, row["id"], token))
            if result.rowcount == 0:
                state = "lease_changed"
        return {"processed": True, "id": row["id"], "state": state, "transport": "http"}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store):
        self.store = store
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Do not put customer input or receiver addresses into request logs.

    def send_value(self, value, status=200, content_type="application/json; charset=utf-8"):
        data = value if isinstance(value, bytes) else encoded(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.send_value(Path(__file__).with_name("index.html").read_bytes(), content_type="text/html; charset=utf-8")
        elif path in ("/api/state", "/api/export"):
            self.send_value(self.server.store.snapshot())
        elif path == "/api/config":
            self.send_value(self.server.store.settings())
        elif path == "/health":
            self.send_value({"ok": True})
        else:
            self.send_value({"error": "Route not found."}, 404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise InputError("JSON body must be between 1 and 131072 bytes.")
            try:
                value = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, UnicodeDecodeError) as exc:
                raise InputError("Supply valid JSON.") from exc
            object_value(value)
            path = urlsplit(self.path).path
            store = self.server.store
            if path == "/api/intakes":
                result = store.intake(value)
                self.send_value(result, 201 if result["created"] else 200)
            elif path == "/api/config":
                self.send_value(store.configure(value))
            elif path == "/api/process":
                self.send_value(store.process_one(ident=value.get("id")))
            elif path == "/api/retry":
                self.send_value(store.retry(text(value.get("id"), "Delivery id", 160)))
            elif path == "/api/tasks":
                self.send_value(store.complete_task(text(value.get("id"), "Task id", 120), value.get("done")))
            elif path == "/api/receive":
                self.send_value(store.receive(self.headers.get("Idempotency-Key", ""), value))
            else:
                self.send_value({"error": "Route not found."}, 404)
        except Conflict as exc:
            self.send_value({"error": str(exc)}, 409)
        except (InputError, ValueError) as exc:
            self.send_value({"error": str(exc)}, 400)
        except sqlite3.Error:
            self.send_value({"error": "Storage operation did not complete; retry this operation with the same id."}, 503)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="workflow.sqlite3", help="Persistent workspace file")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8789)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("file", type=Path)
    config = sub.add_parser("configure")
    config.add_argument("file", type=Path)
    sub.add_parser("export")
    worker = sub.add_parser("work")
    worker.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    store = Store(args.db)
    if args.command == "serve":
        with Server((args.host, args.port), store) as server:
            print(f"Cleaning workflow at http://{args.host}:{server.server_port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    elif args.command in ("ingest", "configure"):
        value = json.loads(args.file.read_text())
        print(encoded(store.intake(value) if args.command == "ingest" else store.configure(value)))
    elif args.command == "export":
        print(encoded(store.snapshot()))
    elif args.command == "work":
        if args.limit < 1 or args.limit > 1000:
            parser.error("--limit must be between 1 and 1000")
        for _ in range(args.limit):
            result = store.process_one()
            print(encoded(result), flush=True)
            if not result["processed"]:
                break


if __name__ == "__main__":
    main()
