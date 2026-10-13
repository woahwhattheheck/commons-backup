#!/usr/bin/env python3
"""Lantern: persistent, free-entry community trivia; Python standard library only."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import json
import math
import secrets
import sqlite3
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 256_000
HOST_KEY_BYTES = 32
HOST_KEY_MAX = 256


class Problem(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise Problem(422, f"{label} must contain 1–{maximum} characters")
    return value.strip()


def integer(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise Problem(422, f"{label} must be an integer from {low} to {high}")
    return value


def timestamp(value: Any, label: str) -> float:
    if type(value) not in (float, int) or not 0 <= value <= 32_503_680_000 or not math.isfinite(value):
        raise Problem(422, f"{label} must be a finite Unix timestamp")
    return float(value)


def _host_digest(host_key: str) -> str:
    # Generated keys are ASCII. surrogatepass keeps hostile JSON strings on the
    # same generic verification path instead of letting UTF-8 encoding raise.
    return hashlib.sha256(host_key.encode("utf-8", errors="surrogatepass")).hexdigest()


class Store:
    def __init__(self, database: str | Path, clock: Callable[[], float] = time.time):
        self.database, self.clock = str(database), clock
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, room TEXT NOT NULL,
                    opens REAL NOT NULL, ends REAL NOT NULL, closed INTEGER NOT NULL DEFAULT 0,
                    questions TEXT NOT NULL, created REAL NOT NULL, host_hash TEXT);
                CREATE TABLE IF NOT EXISTS members (
                    id TEXT PRIMARY KEY, event TEXT NOT NULL REFERENCES events(id),
                    name TEXT NOT NULL, joined REAL NOT NULL, UNIQUE(id,event));
                CREATE TABLE IF NOT EXISTS answers (
                    member TEXT NOT NULL, event TEXT NOT NULL, question INTEGER NOT NULL,
                    choice INTEGER NOT NULL, points INTEGER NOT NULL, received REAL NOT NULL,
                    PRIMARY KEY(member,question),
                    FOREIGN KEY(member,event) REFERENCES members(id,event));
                CREATE INDEX IF NOT EXISTS members_event ON members(event);
                CREATE INDEX IF NOT EXISTS answers_event ON answers(event);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(events)")}
            if "host_hash" not in columns:
                try:
                    db.execute("ALTER TABLE events ADD COLUMN host_hash TEXT")
                except sqlite3.OperationalError:
                    # Two processes may discover the old schema concurrently.
                    # Suppress only the race where the other migrator won.
                    current = {row["name"] for row in db.execute("PRAGMA table_info(events)")}
                    if "host_hash" not in current:
                        raise

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

    def event(self, db, event_id):
        row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise Problem(404, "Event not found")
        return row

    def phase(self, event, now):
        if event["closed"] or now >= event["ends"]:
            return "finished"
        return "scheduled" if now < event["opens"] else "open"

    def create(self, payload):
        title = text(payload.get("title"), "Title", 120)
        room = text(payload.get("room", "Community"), "Room", 80)
        opens = timestamp(payload.get("opens"), "Start")
        ends = timestamp(payload.get("ends"), "End")
        if ends <= opens or ends <= self.clock():
            raise Problem(422, "End must follow start and be in the future")
        raw = payload.get("questions")
        if not isinstance(raw, list) or not 1 <= len(raw) <= 50:
            raise Problem(422, "Provide 1–50 questions")
        questions = []
        for item in raw:
            if not isinstance(item, dict):
                raise Problem(422, "Each question must be an object")
            choices = item.get("choices")
            if not isinstance(choices, list) or not 2 <= len(choices) <= 6:
                raise Problem(422, "Each question needs 2–6 choices")
            choices = [text(c, "Choice", 300) for c in choices]
            if len(set(c.casefold() for c in choices)) != len(choices):
                raise Problem(422, "Choices within a question must be distinct")
            questions.append({"prompt": text(item.get("prompt"), "Prompt", 1000),
                              "choices": choices,
                              "correct": integer(item.get("correct"), "Correct index", 0, len(choices)-1),
                              "points": integer(item.get("points", 100), "Points", 1, 1000)})
        event_id = uuid.uuid4().hex
        host_key = secrets.token_urlsafe(HOST_KEY_BYTES)
        host_hash = _host_digest(host_key)
        with self.connect() as db:
            db.execute("INSERT INTO events(id,title,room,opens,ends,questions,created,host_hash) VALUES(?,?,?,?,?,?,?,?)",
                       (event_id, title, room, opens, ends, json.dumps(questions), self.clock(), host_hash))
        return {"id": event_id, "host_key": host_key}

    def listing(self):
        with self.connect() as db:
            now = self.clock()
            rows = db.execute("SELECT e.*, (SELECT COUNT(*) FROM members m WHERE m.event=e.id) AS players "
                              "FROM events e ORDER BY created DESC,id DESC").fetchall()
            return [{"id": e["id"], "title": e["title"], "room": e["room"],
                     "opens": e["opens"], "ends": e["ends"], "phase": self.phase(e, now),
                     "players": e["players"], "host_protected": e["host_hash"] is not None} for e in rows]

    def verify_host(self, event_id, host_key):
        with self.connect() as db:
            event = self.event(db, event_id)
            expected = event["host_hash"]
        if expected is None:
            return {"host": True, "legacy": True}
        candidate = host_key if isinstance(host_key, str) else ""
        if len(candidate) > HOST_KEY_MAX:
            candidate = ""
        digest = _host_digest(candidate)
        if not hmac.compare_digest(expected, digest):
            raise Problem(403, "Valid host capability required")
        return {"host": True, "legacy": False}

    def join(self, event_id, payload):
        member_id = payload.get("member_id")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            event = self.event(db, event_id)
            if member_id:
                member = db.execute("SELECT id,name FROM members WHERE id=? AND event=?",
                                    (text(member_id, "Participant reference", 80), event_id)).fetchone()
                if member is None:
                    raise Problem(404, "Participant reference not found in this event")
                return dict(member)
            if self.phase(event, self.clock()) == "finished":
                raise Problem(409, "This event has finished; the results remain available")
            name = text(payload.get("name"), "Display name", 60)
            member_id = uuid.uuid4().hex
            db.execute("INSERT INTO members VALUES(?,?,?,?)", (member_id, event_id, name, self.clock()))
            return {"id": member_id, "name": name}

    def answer(self, event_id, payload):
        member_id = text(payload.get("member_id"), "Participant reference", 80)
        index = integer(payload.get("question"), "Question index", 0, 49)
        choice = integer(payload.get("choice"), "Choice index", 0, 5)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            event = self.event(db, event_id)
            member = db.execute("SELECT 1 FROM members WHERE id=? AND event=?", (member_id, event_id)).fetchone()
            if member is None:
                raise Problem(404, "Participant reference not found in this event")
            prior = db.execute("SELECT choice FROM answers WHERE member=? AND question=?", (member_id, index)).fetchone()
            if prior is not None:
                if prior["choice"] != choice:
                    raise Problem(409, "The first answer is final; a different retry was not recorded")
                return {"accepted": True, "replayed": True, "question": index, "choice": choice}
            if self.phase(event, self.clock()) != "open":
                raise Problem(409, "Answers are accepted only while the event is open")
            questions = json.loads(event["questions"])
            if index >= len(questions) or choice >= len(questions[index]["choices"]):
                raise Problem(422, "Question or choice is outside this event")
            question = questions[index]
            score = question["points"] if choice == question["correct"] else 0
            db.execute("INSERT INTO answers VALUES(?,?,?,?,?,?)", (member_id, event_id, index, choice, score, self.clock()))
        return {"accepted": True, "replayed": False, "question": index, "choice": choice}

    def finish(self, event_id):
        with self.connect() as db:
            self.event(db, event_id)
            db.execute("UPDATE events SET closed=1 WHERE id=?", (event_id,))
        return {"finished": True}

    def state(self, event_id, member_id=None):
        with self.connect() as db:
            db.execute("BEGIN")
            event = self.event(db, event_id)
            phase = self.phase(event, self.clock())
            finished = phase == "finished"
            questions = json.loads(event["questions"])
            visible = [] if phase == "scheduled" else [
                {k: v for k, v in q.items() if finished or k != "correct"} for q in questions]
            member, answers = None, []
            if member_id:
                row = db.execute("SELECT id,name FROM members WHERE id=? AND event=?", (member_id, event_id)).fetchone()
                if row is None:
                    raise Problem(404, "Participant reference not found in this event")
                member = dict(row)
                rows = db.execute("SELECT question,choice,points FROM answers WHERE member=? ORDER BY question", (member_id,)).fetchall()
                answers = [{k: row[k] for k in ("question", "choice", "points") if finished or k != "points"} for row in rows]
            rows = db.execute("SELECT m.id,m.name,m.joined,COALESCE(SUM(a.points),0) AS points,COUNT(a.question) AS answered "
                              "FROM members m LEFT JOIN answers a ON a.member=m.id "
                              "WHERE m.event=? GROUP BY m.id ORDER BY points DESC,m.joined,m.id", (event_id,)).fetchall()
            board = []
            if finished:
                previous, rank = None, 0
                for position, row in enumerate(rows, 1):
                    if row["points"] != previous:
                        rank, previous = position, row["points"]
                    board.append({"rank": rank, "id": row["id"], "name": row["name"], "points": row["points"], "answered": row["answered"]})
            return {"id": event_id, "title": event["title"], "room": event["room"], "opens": event["opens"],
                    "ends": event["ends"], "server_time": self.clock(), "phase": phase,
                    "question_count": len(questions), "questions": visible, "member": member, "answers": answers,
                    "players": len(rows), "leaderboard": board, "host_protected": event["host_hash"] is not None}


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, value, content_type="application/json; charset=utf-8", filename=None):
            body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if filename is not None:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def route(self, method):
            try:
                url = urlsplit(self.path)
                parts = url.path.strip("/").split("/")
                payload = {}
                if method == "POST":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        raise Problem(400, "Invalid content length")
                    if not 1 <= length <= MAX_BODY:
                        raise Problem(413, "Provide a JSON body of at most 256000 bytes")
                    try:
                        payload = json.loads(self.rfile.read(length))
                    except (ValueError, UnicodeError, RecursionError):
                        raise Problem(400, "Invalid JSON body")
                    if not isinstance(payload, dict):
                        raise Problem(422, "JSON body must be an object")
                if method == "GET" and url.path == "/":
                    return self.send(200, Path(__file__).with_name("index.html").read_bytes(), "text/html; charset=utf-8")
                if method == "GET" and url.path == "/health":
                    return self.send(200, {"ok": True})
                if parts == ["api", "events"]:
                    return self.send(201 if method == "POST" else 200,
                                     store.create(payload) if method == "POST" else store.listing())
                if len(parts) == 5 and parts[:2] == ["api", "events"] and parts[3:] == ["host", "verify"]:
                    if method == "POST":
                        return self.send(200, store.verify_host(parts[2], payload.get("host_key")))
                    raise Problem(404, "Route not found")
                if len(parts) in (3, 4) and parts[:2] == ["api", "events"]:
                    event_id = parts[2]
                    if method == "GET" and len(parts) == 3:
                        member_id = parse_qs(url.query).get("member", [None])[0]
                        return self.send(200, store.state(event_id, member_id))
                    if method == "GET" and len(parts) == 4 and parts[3] in ("results.csv", "results.json"):
                        from results_export import Problem as ExportProblem, export_bytes
                        format = parts[3].rsplit(".", 1)[1]
                        try:
                            content = export_bytes(store, event_id, format)
                        except ExportProblem as exc:
                            raise Problem(exc.status, str(exc)) from exc
                        content_type = "text/csv" if format == "csv" else "application/json"
                        return self.send(200, content, content_type + "; charset=utf-8",
                                         "lantern-results." + format)
                    if method == "POST" and len(parts) == 4:
                        if parts[3] == "join":
                            return self.send(200, store.join(event_id, payload))
                        if parts[3] == "answers":
                            return self.send(200, store.answer(event_id, payload))
                        if parts[3] == "finish":
                            store.verify_host(event_id, payload.get("host_key"))
                            return self.send(200, store.finish(event_id))
                raise Problem(404, "Route not found")
            except Problem as exc:
                self.send(exc.status, {"error": str(exc)})
            except sqlite3.OperationalError:
                self.send(503, {"error": "Storage is temporarily unavailable; retry the same request"})

        def do_GET(self):
            self.route("GET")

        def do_POST(self):
            self.route("POST")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="events.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Store(args.db)))
    print(f"Lantern is serving on http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
