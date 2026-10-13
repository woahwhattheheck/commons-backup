#!/usr/bin/env python3
"""Northstar: source-linked niche newsletter publication desk, stdlib only."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import re
import sqlite3
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

MAX_BODY = 256_000
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UTC = dt.timezone.utc


class Problem(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise Problem(422, f"{label} must be text")
    value = value.strip()
    if not value or len(value) > maximum:
        raise Problem(422, f"{label} must contain 1–{maximum} characters")
    return value


def optional_text(value: Any, label: str, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value.strip()) > maximum:
        raise Problem(422, f"{label} must contain at most {maximum} characters")
    return value.strip()


def string_list(value: Any, label: str, maximum: int = 12) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise Problem(422, f"{label} must be a list with at most {maximum} items")
    out: list[str] = []
    for item in value:
        item = text(item, label, 80)
        if item.casefold() not in {v.casefold() for v in out}:
            out.append(item)
    return out


def iso_utc(value: Any, label: str) -> str:
    raw = text(value, label, 64)
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Problem(422, f"{label} must be an ISO date-time") from exc
    if parsed.tzinfo is None:
        raise Problem(422, f"{label} must include a timezone")
    try:
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise Problem(422, f"{label} must be an ISO date-time") from exc


def now_iso(clock: Callable[[], float]) -> str:
    return dt.datetime.fromtimestamp(clock(), UTC).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, database: str | Path, clock: Callable[[], float] = time.time):
        self.database, self.clock = str(database), clock
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sources(
              id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
              observed_at TEXT NOT NULL, notes TEXT NOT NULL, synthetic INTEGER NOT NULL,
              created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS issues(
              id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
              subject TEXT NOT NULL, body TEXT NOT NULL, topic TEXT NOT NULL,
              scheduled_at TEXT NOT NULL, state TEXT NOT NULL,
              revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS issue_sources(
              issue_id TEXT NOT NULL REFERENCES issues(id), source_id TEXT NOT NULL REFERENCES sources(id),
              PRIMARY KEY(issue_id,source_id));
            CREATE TABLE IF NOT EXISTS issue_history(
              issue_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
              subject TEXT NOT NULL, body TEXT NOT NULL, topic TEXT NOT NULL,
              scheduled_at TEXT NOT NULL, source_ids TEXT NOT NULL, changed_at TEXT NOT NULL,
              PRIMARY KEY(issue_id,revision));
            CREATE TABLE IF NOT EXISTS subscribers(
              id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, topics TEXT NOT NULL,
              frequency TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS exports(
              export_key TEXT PRIMARY KEY, kind TEXT NOT NULL, issue_id TEXT,
              subscriber_id TEXT, payload_sha256 TEXT NOT NULL, created_at TEXT NOT NULL);
            """)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def source(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = payload.get("id") or uuid.uuid4().hex
        source_id = text(source_id, "Source id", 80)
        title = text(payload.get("title"), "Source title", 160)
        url = text(payload.get("url"), "Source URL", 500)
        if not (url.startswith("https://") or url.startswith("http://") or url.startswith("self-authored:")):
            raise Problem(422, "Source URL must be http(s) or self-authored")
        observed_at = iso_utc(payload.get("observed_at"), "Observed at")
        notes = optional_text(payload.get("notes"), "Source notes", 2000)
        synthetic = payload.get("synthetic", False)
        if type(synthetic) is not bool:
            raise Problem(422, "Synthetic must be a boolean")
        with self.connect() as db:
            try:
                db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?)",
                           (source_id, title, url, observed_at, notes, int(synthetic), now_iso(self.clock)))
            except sqlite3.IntegrityError as exc:
                raise Problem(409, "Source id already exists") from exc
        return {"id": source_id}

    def _source_ids(self, db, raw: Any) -> list[str]:
        ids = string_list(raw, "Source ids", 24)
        if not ids:
            raise Problem(422, "Every issue needs at least one source")
        found = {row["id"] for row in db.execute(
            f"SELECT id FROM sources WHERE id IN ({','.join('?' for _ in ids)})", ids).fetchall()}
        missing = [value for value in ids if value not in found]
        if missing:
            raise Problem(422, "Unknown source ids: " + ", ".join(missing))
        return ids

    def issue(self, payload: dict[str, Any]) -> dict[str, Any]:
        issue_id = payload.get("id") or uuid.uuid4().hex
        issue_id = text(issue_id, "Issue id", 80)
        slug = text(payload.get("slug"), "Slug", 100)
        if not SLUG_RE.fullmatch(slug):
            raise Problem(422, "Slug must use lowercase letters, numbers and hyphens")
        title = text(payload.get("title"), "Issue title", 160)
        subject = text(payload.get("subject"), "Subject", 200)
        body = text(payload.get("body"), "Body", 20_000)
        topic = text(payload.get("topic"), "Topic", 80)
        scheduled_at = iso_utc(payload.get("scheduled_at"), "Scheduled at")
        stamp = now_iso(self.clock)
        with self.connect() as db:
            ids = self._source_ids(db, payload.get("source_ids"))
            try:
                db.execute("INSERT INTO issues VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (issue_id, slug, title, subject, body, topic, scheduled_at,
                            "draft", 1, stamp, stamp))
                db.executemany("INSERT INTO issue_sources VALUES(?,?)", [(issue_id, sid) for sid in ids])
                db.execute("INSERT INTO issue_history VALUES(?,?,?,?,?,?,?,?,?)",
                           (issue_id, 1, title, subject, body, topic, scheduled_at,
                            json.dumps(ids, separators=(",", ":")), stamp))
            except sqlite3.IntegrityError as exc:
                raise Problem(409, "Issue id or slug already exists") from exc
        return {"id": issue_id, "revision": 1}

    def revise(self, issue_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
            if row is None:
                raise Problem(404, "Issue not found")
            if row["state"] == "published":
                raise Problem(409, "Published issues are immutable; create a new issue")
            title = text(payload.get("title", row["title"]), "Issue title", 160)
            subject = text(payload.get("subject", row["subject"]), "Subject", 200)
            body = text(payload.get("body", row["body"]), "Body", 20_000)
            topic = text(payload.get("topic", row["topic"]), "Topic", 80)
            scheduled_at = iso_utc(payload.get("scheduled_at", row["scheduled_at"]), "Scheduled at")
            if "source_ids" in payload:
                ids = self._source_ids(db, payload["source_ids"])
            else:
                ids = [r["source_id"] for r in db.execute(
                    "SELECT source_id FROM issue_sources WHERE issue_id=? ORDER BY source_id", (issue_id,)).fetchall()]
            revision = row["revision"] + 1
            stamp = now_iso(self.clock)
            db.execute("UPDATE issues SET title=?,subject=?,body=?,topic=?,scheduled_at=?,revision=?,updated_at=? WHERE id=?",
                       (title, subject, body, topic, scheduled_at, revision, stamp, issue_id))
            db.execute("DELETE FROM issue_sources WHERE issue_id=?", (issue_id,))
            db.executemany("INSERT INTO issue_sources VALUES(?,?)", [(issue_id, sid) for sid in ids])
            db.execute("INSERT INTO issue_history VALUES(?,?,?,?,?,?,?,?,?)",
                       (issue_id, revision, title, subject, body, topic, scheduled_at,
                        json.dumps(ids, separators=(",", ":")), stamp))
        return {"id": issue_id, "revision": revision}

    def publish(self, issue_id: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM issues WHERE id=?", (issue_id,)).fetchone()
            if row is None:
                raise Problem(404, "Issue not found")
            if row["state"] == "published":
                return {"published": True, "replayed": True}
            db.execute("UPDATE issues SET state='published',updated_at=? WHERE id=?", (now_iso(self.clock), issue_id))
        return {"published": True, "replayed": False}

    def subscribe(self, payload: dict[str, Any]) -> dict[str, Any]:
        email = text(payload.get("email"), "Email", 254).casefold()
        if not EMAIL_RE.fullmatch(email):
            raise Problem(422, "Email must be a valid address")
        topics = string_list(payload.get("topics", []), "Topics")
        frequency = text(payload.get("frequency", "weekly"), "Frequency", 40)
        if frequency not in ("weekly", "monthly"):
            raise Problem(422, "Frequency must be weekly or monthly")
        stamp = now_iso(self.clock)
        subscriber_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,status FROM subscribers WHERE email=?", (email,)).fetchone()
            if row:
                if row["status"] == "unsubscribed":
                    raise Problem(409, "This address is unsubscribed; explicit resubscription is not automated")
                return {"id": row["id"], "replayed": True}
            db.execute("INSERT INTO subscribers VALUES(?,?,?,?,?,?,?)",
                       (subscriber_id, email, json.dumps(topics, separators=(",", ":")), frequency,
                        "active", stamp, stamp))
        return {"id": subscriber_id, "replayed": False}

    def preferences(self, subscriber_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        topics = string_list(payload.get("topics", []), "Topics")
        frequency = text(payload.get("frequency", "weekly"), "Frequency", 40)
        if frequency not in ("weekly", "monthly"):
            raise Problem(422, "Frequency must be weekly or monthly")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM subscribers WHERE id=?", (subscriber_id,)).fetchone()
            if row is None:
                raise Problem(404, "Subscriber not found")
            if row["status"] != "active":
                raise Problem(409, "Unsubscribed preferences cannot be changed")
            db.execute("UPDATE subscribers SET topics=?,frequency=?,updated_at=? WHERE id=?",
                       (json.dumps(topics, separators=(",", ":")), frequency, now_iso(self.clock), subscriber_id))
        return {"updated": True}

    def unsubscribe(self, subscriber_id: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM subscribers WHERE id=?", (subscriber_id,)).fetchone()
            if row is None:
                raise Problem(404, "Subscriber not found")
            replayed = row["status"] == "unsubscribed"
            db.execute("UPDATE subscribers SET status='unsubscribed',updated_at=? WHERE id=?",
                       (now_iso(self.clock), subscriber_id))
        return {"unsubscribed": True, "replayed": replayed}

    def welcome(self, subscriber_id: str) -> bytes:
        with self.connect() as db:
            row = db.execute("SELECT * FROM subscribers WHERE id=?", (subscriber_id,)).fetchone()
            if row is None:
                raise Problem(404, "Subscriber not found")
            if row["status"] != "active":
                raise Problem(409, "Unsubscribed subscribers do not receive exports")
            payload = {
                "schema": "northstar.welcome.v1", "delivery_state": "UNSENT",
                "subscriber_id": row["id"], "email": row["email"],
                "topics": json.loads(row["topics"]), "frequency": row["frequency"],
                "subject": "Welcome to Northstar Brief",
                "body": "Your preferences are saved. This local packet is ready for an authorized provider import.",
            }
        return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

    def issue_export(self, issue_id: str) -> bytes:
        with self.connect() as db:
            db.execute("BEGIN")
            issue = db.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
            if issue is None:
                raise Problem(404, "Issue not found")
            if issue["state"] != "published":
                raise Problem(409, "Only published issues can be exported")
            sources = [dict(row) for row in db.execute(
                "SELECT s.id,s.title,s.url,s.observed_at,s.synthetic FROM sources s JOIN issue_sources x ON x.source_id=s.id WHERE x.issue_id=? ORDER BY s.id",
                (issue_id,)).fetchall()]
            subscribers = db.execute("SELECT * FROM subscribers WHERE status='active' ORDER BY email,id").fetchall()
            eligible = []
            for row in subscribers:
                topics = json.loads(row["topics"])
                if topics and issue["topic"] not in topics:
                    continue
                eligible.append(row)
            manifest = {
                "schema": "northstar.issue-export.v1", "delivery_state": "UNSENT",
                "issue": {k: issue[k] for k in ("id", "slug", "title", "subject", "topic", "scheduled_at", "revision")},
                "sources": sources,
                "recipient_count": len(eligible),
                "recipients": [row["email"] for row in eligible],
            }
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
                archive.writestr("issue.txt", issue["body"] + "\n")
                archive.writestr("sources.json", json.dumps(sources, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
                for row in eligible:
                    packet = {
                        "delivery_state": "UNSENT", "subscriber_id": row["id"], "email": row["email"],
                        "subject": issue["subject"], "scheduled_at": issue["scheduled_at"],
                        "issue_id": issue["id"], "revision": issue["revision"], "source_ids": [s["id"] for s in sources],
                    }
                    archive.writestr(f"recipients/{row['id']}.json",
                                     json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            return buffer.getvalue()

    def snapshot(self) -> dict[str, Any]:
        with self.connect() as db:
            issues = [dict(row) for row in db.execute(
                "SELECT id,slug,title,subject,topic,scheduled_at,state,revision FROM issues ORDER BY scheduled_at,id").fetchall()]
            for issue in issues:
                issue["source_ids"] = [r["source_id"] for r in db.execute(
                    "SELECT source_id FROM issue_sources WHERE issue_id=? ORDER BY source_id", (issue["id"],)).fetchall()]
            sources = [dict(row) for row in db.execute(
                "SELECT id,title,url,observed_at,synthetic FROM sources ORDER BY id").fetchall()]
            subscribers = [dict(row) for row in db.execute(
                "SELECT id,email,topics,frequency,status FROM subscribers ORDER BY email,id").fetchall()]
            for subscriber in subscribers:
                subscriber["topics"] = json.loads(subscriber["topics"])
        return {"issues": issues, "sources": sources, "subscribers": subscribers,
                "archive": [issue for issue in issues if issue["state"] == "published"]}

    def seed(self, fixture: dict[str, Any]) -> dict[str, int]:
        counts = {"sources": 0, "issues": 0, "subscribers": 0}
        for item in fixture.get("sources", []):
            try:
                self.source(item); counts["sources"] += 1
            except Problem as exc:
                if exc.status != 409: raise
        for item in fixture.get("issues", []):
            try:
                created = self.issue(item); counts["issues"] += 1
                if item.get("published"):
                    self.publish(created["id"])
            except Problem as exc:
                if exc.status != 409: raise
        for item in fixture.get("subscribers", []):
            try:
                result = self.subscribe(item)
                if not result["replayed"]:
                    counts["subscribers"] += 1
            except Problem as exc:
                if exc.status != 409: raise
        return counts


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status: int, value: Any, content_type="application/json; charset=utf-8"):
            body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def payload(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise Problem(400, "Invalid content length") from exc
            if not 1 <= length <= MAX_BODY:
                raise Problem(413, "Provide a JSON body of at most 256000 bytes")
            try:
                value = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise Problem(400, "Invalid JSON body") from exc
            if not isinstance(value, dict):
                raise Problem(422, "JSON body must be an object")
            return value

        def route(self, method: str):
            try:
                url = urlsplit(self.path)
                parts = [p for p in url.path.split("/") if p]
                payload = self.payload() if method == "POST" else {}
                if method == "GET" and url.path == "/":
                    return self.send(200, Path(__file__).with_name("index.html").read_bytes(), "text/html; charset=utf-8")
                if method == "GET" and url.path == "/health":
                    return self.send(200, {"ok": True})
                if method == "GET" and parts == ["api", "state"]:
                    return self.send(200, store.snapshot())
                if method == "POST" and parts == ["api", "sources"]:
                    return self.send(201, store.source(payload))
                if method == "POST" and parts == ["api", "issues"]:
                    return self.send(201, store.issue(payload))
                if len(parts) == 4 and parts[:2] == ["api", "issues"]:
                    issue_id, action = parts[2], parts[3]
                    if method == "POST" and action == "revise":
                        return self.send(200, store.revise(issue_id, payload))
                    if method == "POST" and action == "publish":
                        return self.send(200, store.publish(issue_id))
                    if method == "GET" and action == "export":
                        return self.send(200, store.issue_export(issue_id), "application/zip")
                if method == "POST" and parts == ["api", "subscribers"]:
                    return self.send(201, store.subscribe(payload))
                if len(parts) == 4 and parts[:2] == ["api", "subscribers"]:
                    subscriber_id, action = parts[2], parts[3]
                    if method == "POST" and action == "preferences":
                        return self.send(200, store.preferences(subscriber_id, payload))
                    if method == "POST" and action == "unsubscribe":
                        return self.send(200, store.unsubscribe(subscriber_id))
                    if method == "GET" and action == "welcome":
                        return self.send(200, store.welcome(subscriber_id), "application/json; charset=utf-8")
                raise Problem(404, "Route not found")
            except Problem as exc:
                self.send(exc.status, {"error": str(exc)})
            except sqlite3.OperationalError:
                self.send(503, {"error": "Storage is temporarily unavailable; retry the same request"})

        def do_GET(self): self.route("GET")
        def do_POST(self): self.route("POST")

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="northstar.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seed", help="Seed a JSON fixture before serving")
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args(argv)
    store = Store(args.db)
    if args.seed:
        fixture = json.loads(Path(args.seed).read_text(encoding="utf-8"))
        if not isinstance(fixture, dict):
            parser.error("seed must be a JSON object")
        result = store.seed(fixture)
        print(json.dumps(result, sort_keys=True))
    if args.seed_only:
        return 0
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    print(f"Northstar is serving on http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
