"""Creator Desk: durable resource delivery and voluntary follow-up drafting.

No external network calls or email sending. One shared, trusted workspace.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

MAX_FILE_BYTES = 8 * 1024 * 1024
CONSENT_TEXT = "I choose to receive the creator's follow-up emails. I can opt out at any time."


class DeskError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def text(value, label, limit=500, *, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise DeskError(f"{label} must be text" + ("" if empty else " and not empty"))
    value = value.strip()
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise DeskError(f"{label} must be valid Unicode") from None
    if len(value) > limit or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise DeskError(f"{label} is too long or contains control characters")
    return value


def email_address(value):
    value = text(value, "email", 254).lower()
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
        raise DeskError("Enter an email address with a domain")
    return value


def web_url(value):
    value = text(value, "link", 2048)
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or any(c.isspace() for c in value)):
            raise ValueError
        _ = parsed.port
    except ValueError:
        raise DeskError("Links must be complete HTTP or HTTPS URLs without credentials") from None
    return value


def steps(value):
    if not isinstance(value, list) or len(value) > 20:
        raise DeskError("sequence must be a list of at most 20 steps")
    result = []
    for step in value:
        if not isinstance(step, dict):
            raise DeskError("Each sequence step must be an object")
        delay = step.get("delay_minutes")
        if type(delay) is not int or not 0 <= delay <= 525600:
            raise DeskError("delay_minutes must be an integer between 0 and 525600")
        subject = text(step.get("subject"), "subject", 200)
        if "\n" in subject or "\t" in subject:
            raise DeskError("subject must occupy one line")
        result.append({"delay_minutes": delay, "subject": subject,
                       "body": text(step.get("body"), "body", 20000)})
    return result


def require_row(db, table, key):
    # Table names are internal constants, never request data.
    key = text(key, "record id", 160)
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (key,)).fetchone()
    if row is None:
        raise DeskError("Not found", 404)
    return row


class Store:
    def __init__(self, path: str | Path, clock=time.time):
        self.path, self.clock = str(path), clock
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS resources(
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                    kind TEXT NOT NULL, target TEXT NOT NULL, filename TEXT NOT NULL,
                    data BLOB NOT NULL, sha256 TEXT NOT NULL, sequence TEXT NOT NULL,
                    active INTEGER NOT NULL, revision INTEGER NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS members(
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    opted_in INTEGER NOT NULL, revision INTEGER NOT NULL, updated_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS consents(
                    id INTEGER PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id),
                    opted_in INTEGER NOT NULL, wording TEXT NOT NULL, source TEXT NOT NULL,
                    created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS requests(
                    id TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id),
                    resource_id TEXT NOT NULL REFERENCES resources(id), created_at INTEGER NOT NULL,
                    UNIQUE(member_id,resource_id));
                CREATE TABLE IF NOT EXISTS outbox(
                    id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
                    member_id TEXT NOT NULL REFERENCES members(id), step INTEGER NOT NULL,
                    subject TEXT NOT NULL, body TEXT NOT NULL, due_at INTEGER NOT NULL,
                    state TEXT NOT NULL, receipt TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL,
                    UNIQUE(request_id,step));
                CREATE TABLE IF NOT EXISTS inquiries(
                    id TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id),
                    body TEXT NOT NULL, state TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS operations(
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS due_outbox ON outbox(state,due_at);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _new_id():
        return uuid.uuid4().hex

    @staticmethod
    def _resource(row):
        result = dict(row)
        result.pop("data")
        result["sequence"] = json.loads(result["sequence"])
        result["active"] = bool(result["active"])
        return result

    @staticmethod
    def _member(row):
        result = dict(row)
        result["opted_in"] = bool(result["opted_in"])
        return result

    def _consent(self, db, member_id, opted_in, source, now):
        db.execute("UPDATE members SET opted_in=?, revision=revision+1, updated_at=? WHERE id=?",
                   (int(opted_in), now, member_id))
        db.execute("INSERT INTO consents(member_id,opted_in,wording,source,created_at) VALUES(?,?,?,?,?)",
                   (member_id, int(opted_in), CONSENT_TEXT if opted_in else "Follow-up emails stopped.", source, now))
        if not opted_in:
            db.execute("UPDATE outbox SET state='cancelled',updated_at=? WHERE member_id=? AND state='queued'",
                       (now, member_id))

    def mutate(self, action: str, operation_id: str, payload: dict):
        """All mutations are transactional and retry-safe by operation_id.

        A reused operation with changed content is a conflict, never a new write.
        Operation replay does not reapply old consent after a later opt-out.
        """
        operation_id = text(operation_id, "operation_id", 160)
        if not isinstance(payload, dict):
            raise DeskError("payload must be an object")
        try:
            encoded = json.dumps([action, payload], sort_keys=True, ensure_ascii=False, allow_nan=False)
            fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise DeskError("payload must contain JSON values") from None
        now = int(self.clock())
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise DeskError("operation_id already used with different content", 409)
                return json.loads(prior["result"])
            if action == "resource.create":
                result = self._create_resource(db, payload, now)
            elif action == "resource.update":
                row = require_row(db, "resources", payload.get("id"))
                if type(payload.get("expected_revision")) is not int or payload["expected_revision"] != row["revision"]:
                    raise DeskError("Resource changed; reload before saving", 409)
                active = payload.get("active")
                if type(active) is not bool:
                    raise DeskError("active must be true or false")
                db.execute("UPDATE resources SET title=?,description=?,sequence=?,active=?,revision=revision+1 WHERE id=?",
                           (text(payload.get("title"), "title", 160), text(payload.get("description", ""), "description", 4000, empty=True),
                            json.dumps(steps(payload.get("sequence", []))), int(active), row["id"]))
                result = self._resource(require_row(db, "resources", row["id"]))
            elif action == "request":
                result = self._request(db, payload, now)
            elif action == "preferences":
                row = require_row(db, "members", payload.get("member_id"))
                if type(payload.get("expected_revision")) is not int or row["revision"] != payload["expected_revision"]:
                    raise DeskError("Preferences changed; reload before saving", 409)
                if type(payload.get("opted_in")) is not bool:
                    raise DeskError("opted_in must be true or false")
                self._consent(db, row["id"], payload["opted_in"], "preferences", now)
                result = self._member(require_row(db, "members", row["id"]))
            elif action == "outbox.record":
                row = require_row(db, "outbox", payload.get("id"))
                member = require_row(db, "members", row["member_id"])
                if row["state"] != "queued" or not member["opted_in"] or row["due_at"] > now:
                    raise DeskError("Only due, opted-in queued items can be recorded", 409)
                receipt = text(payload.get("receipt"), "external delivery reference", 500)
                db.execute("UPDATE outbox SET state='recorded',receipt=?,updated_at=? WHERE id=?", (receipt, now, row["id"]))
                result = dict(require_row(db, "outbox", row["id"]))
            elif action == "inquiry":
                member = require_row(db, "members", payload.get("member_id"))
                key = self._new_id()
                db.execute("INSERT INTO inquiries VALUES(?,?,?,'open',?)", (key, member["id"], text(payload.get("body"), "request", 4000), now))
                result = dict(require_row(db, "inquiries", key))
            elif action == "inquiry.close":
                row = require_row(db, "inquiries", payload.get("id"))
                db.execute("UPDATE inquiries SET state='closed' WHERE id=?", (row["id"],))
                result = dict(require_row(db, "inquiries", row["id"]))
            else:
                raise DeskError("Unknown operation", 404)
            db.execute("INSERT INTO operations VALUES(?,?,?)", (operation_id, fingerprint, json.dumps(result)))
            return result

    def _create_resource(self, db, payload, now):
        title = text(payload.get("title"), "title", 160)
        description = text(payload.get("description", ""), "description", 4000, empty=True)
        sequence = steps(payload.get("sequence", []))
        kind = payload.get("kind")
        data, filename, target = b"", "", ""
        if kind == "file":
            filename = text(payload.get("filename"), "filename", 180)
            if any(c in filename for c in "/\\\r\n\t") or filename in (".", ".."):
                raise DeskError("filename must be a plain file name")
            encoded = payload.get("data_base64")
            if not isinstance(encoded, str) or len(encoded) > ((MAX_FILE_BYTES + 2) // 3) * 4:
                raise DeskError("File must be base64 and no larger than 8 MiB")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                raise DeskError("Invalid base64 file") from None
            if len(data) > MAX_FILE_BYTES:
                raise DeskError("File is larger than 8 MiB")
        elif kind == "link":
            target = web_url(payload.get("target"))
        else:
            raise DeskError("kind must be file or link")
        key = self._new_id()
        sha = hashlib.sha256(data if kind == "file" else target.encode()).hexdigest()
        db.execute("INSERT INTO resources VALUES(?,?,?,?,?,?,?,?,?,1,1,?)",
                   (key, title, description, kind, target, filename, data, sha, json.dumps(sequence), now))
        return self._resource(require_row(db, "resources", key))

    def _request(self, db, payload, now):
        resource = require_row(db, "resources", payload.get("resource_id"))
        address = email_address(payload.get("email"))
        name = text(payload.get("name", ""), "name", 160, empty=True)
        opt_in = payload.get("opt_in", False)
        if type(opt_in) is not bool:
            raise DeskError("opt_in must be true or false")
        member = db.execute("SELECT * FROM members WHERE email=?", (address,)).fetchone()
        if member:
            existing = db.execute("SELECT * FROM requests WHERE member_id=? AND resource_id=?", (member["id"], resource["id"])).fetchone()
            if existing:
                # A repeat request never enrolls, changes consent, or reschedules.
                return {"request_id": existing["id"], "member_id": member["id"], "resource_id": resource["id"], "reused": True}
        if not resource["active"]:
            raise DeskError("Resource is archived; existing deliveries remain available", 409)
        if not member:
            member_id = self._new_id()
            db.execute("INSERT INTO members VALUES(?,?,?,0,1,?)", (member_id, address, name, now))
        else:
            member_id = member["id"]
        # Unchecked consent does not change an existing preference. Enrollment is
        # explicit; opt-out is a separate intentional preferences operation.
        if opt_in:
            self._consent(db, member_id, True, "resource request", now)
        key = self._new_id()
        db.execute("INSERT INTO requests VALUES(?,?,?,?)", (key, member_id, resource["id"], now))
        # Only this request's affirmative choice schedules this sequence.
        if opt_in:
            for index, step in enumerate(json.loads(resource["sequence"])):
                db.execute("INSERT INTO outbox(id,request_id,member_id,step,subject,body,due_at,state,updated_at) VALUES(?,?,?,?,?,?,?,'queued',?)",
                           (self._new_id(), key, member_id, index, step["subject"], step["body"], now + step["delay_minutes"] * 60, now))
        return {"request_id": key, "member_id": member_id, "resource_id": resource["id"], "reused": False}

    def catalog(self, *, all_resources=False):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM resources" + ("" if all_resources else " WHERE active=1") + " ORDER BY created_at,id")
            return [self._resource(row) for row in rows]

    def member(self, member_id):
        with self.connection() as db:
            member = self._member(require_row(db, "members", member_id))
            member["requests"] = [dict(r) for r in db.execute("SELECT q.id,q.resource_id,q.created_at,r.title,r.kind,r.filename FROM requests q JOIN resources r ON r.id=q.resource_id WHERE q.member_id=? ORDER BY q.created_at,q.id", (member_id,))]
            member["consents"] = [dict(r) for r in db.execute("SELECT opted_in,wording,source,created_at FROM consents WHERE member_id=? ORDER BY id", (member_id,))]
            return member

    def delivery(self, request_id):
        with self.connection() as db:
            request = require_row(db, "requests", request_id)
            return dict(require_row(db, "resources", request["resource_id"]))

    def dashboard(self):
        now = int(self.clock())
        with self.connection() as db:
            rows = db.execute("SELECT o.*,m.email,m.name,m.opted_in FROM outbox o JOIN members m ON m.id=o.member_id ORDER BY o.due_at,o.id")
            outbox = []
            for row in rows:
                item = dict(row)
                item["due"] = item["state"] == "queued" and bool(item["opted_in"]) and item["due_at"] <= now
                outbox.append(item)
            inquiries = [dict(row) for row in db.execute("SELECT i.*,m.email FROM inquiries i JOIN members m ON m.id=i.member_id ORDER BY i.created_at,i.id")]
            counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("members", "requests")}
            return {"resources": self.catalog(all_resources=True), "outbox": outbox, "inquiries": inquiries, "counts": counts, "now": now}

    def email_draft(self, outbox_id):
        """Produce a draft, not a send; recheck consent and due time at export."""
        with self.connection() as db:
            row = require_row(db, "outbox", outbox_id)
            member = require_row(db, "members", row["member_id"])
            if row["state"] != "queued" or not member["opted_in"] or row["due_at"] > int(self.clock()):
                raise DeskError("Draft is not due, was cancelled, or is already recorded", 409)
            message = EmailMessage()
            message["To"] = member["email"]
            message["Subject"] = row["subject"]
            message["X-Unsent"] = "1"
            message["X-Creator-Desk-Reference"] = row["id"]
            message.set_content(row["body"] + "\n\nTo stop follow-up emails, reply 'unsubscribe' or use your Creator Desk preferences.\n")
            return message.as_bytes()
