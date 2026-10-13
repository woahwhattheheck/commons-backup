#!/usr/bin/env python3
"""Office workspace: explicit actions, cited source excerpts, and unsent drafts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

HERE = Path(__file__).resolve().parent
STOP = set("a an and are as at be by can do does for from how i in is it of on or our the this to was we what when where which who will with you your".split())
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,source_key TEXT NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,version INTEGER NOT NULL,UNIQUE(workspace_id,source_key));
CREATE TABLE IF NOT EXISTS versions(source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,version INTEGER NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,PRIMARY KEY(source_id,version));
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,source_version INTEGER NOT NULL,line INTEGER NOT NULL,owner TEXT NOT NULL,due TEXT NOT NULL,description TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'open',revision INTEGER NOT NULL DEFAULT 1,current INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,recipient TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS draft_requests(workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,request_id TEXT NOT NULL,draft_id TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,fingerprint TEXT NOT NULL,PRIMARY KEY(workspace_id,request_id));
"""


class Problem(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def text(value, name: str, limit: int = 200, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise Problem(f"{name} must be {'nonempty ' if not empty else ''}text, at most {limit} characters")
    return value


def revision(value) -> int:
    if type(value) is not int or value < 1:
        raise Problem("revision must be a positive integer")
    return value


def actions(body: str) -> list[dict]:
    result = []
    for line, raw in enumerate(body.splitlines(), 1):
        if not raw.strip().startswith("ACTION:"):
            continue
        parts = raw.strip()[7:].split("|", 2)
        if len(parts) != 3:
            raise Problem(f"line {line}: use ACTION: owner | YYYY-MM-DD or - | task")
        owner, due, description = (part.strip() for part in parts)
        text(owner, "action owner")
        text(description, "action description", 2000)
        if due != "-":
            try:
                if date.fromisoformat(due).isoformat() != due:
                    raise ValueError()
            except ValueError:
                raise Problem(f"line {line}: due must be YYYY-MM-DD or -") from None
        result.append(dict(line=line, owner=owner, due=due, description=description))
    return result


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connection() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            else:
                db.execute("BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def workspace(db, wid):
        text(wid, "workspace_id")
        if not db.execute("SELECT 1 FROM workspaces WHERE id=?", (wid,)).fetchone():
            raise Problem("workspace not found", 404)

    def list_workspaces(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM workspaces ORDER BY name,id")]

    def create_workspace(self, name):
        name = text(name, "name").strip()
        wid = uuid.uuid4().hex
        with self.connection(True) as db:
            db.execute("INSERT INTO workspaces VALUES (?,?)", (wid, name))
        return dict(id=wid, name=name)

    def snapshot(self, wid):
        with self.connection() as db:
            self.workspace(db, wid)
            result = {"workspace_id": wid}
            for table in ("sources", "tasks", "drafts"):
                result[table] = [dict(r) for r in db.execute(f"SELECT * FROM {table} WHERE workspace_id=? ORDER BY id", (wid,))]
            return result

    def import_source(self, wid, source_key, title, kind, body, expected_version=0):
        if type(expected_version) is not int or expected_version < 0:
            raise Problem("expected_version must be a nonnegative integer")
        source_key = text(source_key, "source_key").strip()
        title = text(title, "title").strip()
        if kind not in ("meeting", "document"):
            raise Problem("kind must be meeting or document")
        body = text(body, "text", 100000)
        found = actions(body) if kind == "meeting" else []
        with self.connection(True) as db:
            self.workspace(db, wid)
            old = db.execute("SELECT * FROM sources WHERE workspace_id=? AND source_key=?", (wid, source_key)).fetchone()
            if old:
                previous = db.execute("SELECT * FROM versions WHERE source_id=? AND version=?", (old["id"], old["version"])).fetchone()
                if (previous["text"], previous["title"], previous["kind"]) == (body, title, kind):
                    return dict(source_id=old["id"], version=old["version"], repeated=True)
            if expected_version != (old["version"] if old else 0):
                raise Problem("source changed; reload before importing a new version", 409)
            sid = old["id"] if old else uuid.uuid4().hex
            version = old["version"] + 1 if old else 1
            if old:
                db.execute("UPDATE sources SET title=?,kind=?,version=? WHERE id=?", (title, kind, version, sid))
            else:
                db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?)", (sid, wid, source_key, title, kind, version))
            db.execute("INSERT INTO versions VALUES (?,?,?,?,?)", (sid, version, title, kind, body))
            db.execute("UPDATE tasks SET current=0,revision=revision+1 WHERE source_id=? AND current=1", (sid,))
            seen = set()
            for item in found:
                identity = json.dumps([sid, item["owner"], item["due"], item["description"]], ensure_ascii=False)
                tid = hashlib.sha256(identity.encode()).hexdigest()
                if tid in seen:
                    continue
                seen.add(tid)
                db.execute("""INSERT INTO tasks(id,workspace_id,source_id,source_version,line,owner,due,description)
                    VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET source_version=excluded.source_version,line=excluded.line,current=1,revision=tasks.revision+1""",
                    (tid, wid, sid, version, item["line"], item["owner"], item["due"], item["description"]))
            return dict(source_id=sid, version=version, repeated=False)

    def source(self, wid, sid, version):
        text(sid, "source_id")
        version = revision(version)
        with self.connection() as db:
            self.workspace(db, wid)
            row = db.execute("SELECT v.* FROM versions v JOIN sources s ON s.id=v.source_id WHERE s.workspace_id=? AND s.id=? AND v.version=?", (wid, sid, version)).fetchone()
            if not row:
                raise Problem("source version not found", 404)
            return dict(row)

    def ask(self, wid, question):
        terms = set(re.findall(r"[^\W_]+", text(question, "question", 1000).casefold())) - STOP
        with self.connection() as db:
            self.workspace(db, wid)
            rows = db.execute("SELECT s.id,v.* FROM sources s JOIN versions v ON v.source_id=s.id AND v.version=s.version WHERE s.workspace_id=? AND s.kind='document' ORDER BY s.id", (wid,)).fetchall()
        matches = []
        for row in rows:
            for number, line in enumerate(row["text"].splitlines(), 1):
                words = set(re.findall(r"[^\W_]+", line.casefold()))
                score = len(terms & words)
                if score:
                    matches.append((score, dict(title=row["title"], source_id=row["id"], version=row["version"], line=number, excerpt=line, url="/api/source?" + urlencode(dict(workspace_id=wid, source_id=row["id"], version=row["version"])))))
        matches.sort(key=lambda item: (-item[0], item[1]["source_id"], item[1]["line"]))
        citations = [item[1] for item in matches[:5]]
        return dict(status="excerpts" if citations else "no_answer", answer="Matching source lines; review them in context." if citations else "No matching current source. Ask the document owner; no answer was generated.", citations=citations)

    def update_task(self, wid, tid, expected, state):
        text(tid, "task_id")
        expected = revision(expected)
        if state not in ("open", "done"):
            raise Problem("state must be open or done")
        with self.connection(True) as db:
            self.workspace(db, wid)
            row = db.execute("SELECT * FROM tasks WHERE workspace_id=? AND id=?", (wid, tid)).fetchone()
            if not row:
                raise Problem("task not found", 404)
            if row["revision"] != expected or not row["current"]:
                raise Problem("task changed or was superseded; reload first", 409)
            db.execute("UPDATE tasks SET state=?,revision=revision+1 WHERE id=?", (state, tid))
        return {"revision": expected + 1}

    def save_draft(self, wid, recipient, subject, body, did=None, expected=None, request_id=None):
        recipient = text(recipient, "recipient", 254).strip()
        if not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", recipient):
            raise Problem("recipient must be one email address")
        subject = text(subject, "subject", 300)
        if "\r" in subject or "\n" in subject:
            raise Problem("subject must be one line")
        body = text(body, "body", 100000)
        if request_id is not None:
            request_id = text(request_id, "request_id").strip()
            if did is not None:
                raise Problem("request_id is only for creating a draft; edits use revision")
        fingerprint = hashlib.sha256(json.dumps([recipient, subject, body], ensure_ascii=True).encode()).hexdigest()
        with self.connection(True) as db:
            self.workspace(db, wid)
            if did is not None:
                text(did, "draft_id")
                expected = revision(expected)
                row = db.execute("SELECT revision FROM drafts WHERE workspace_id=? AND id=?", (wid, did)).fetchone()
                if not row:
                    raise Problem("draft not found", 404)
                if row["revision"] != expected:
                    raise Problem("draft changed; reload first", 409)
                db.execute("UPDATE drafts SET recipient=?,subject=?,body=?,revision=revision+1 WHERE id=?", (recipient, subject, body, did))
                return dict(id=did, revision=expected + 1, state="unsent")
            if request_id is not None:
                previous = db.execute("SELECT * FROM draft_requests WHERE workspace_id=? AND request_id=?", (wid, request_id)).fetchone()
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise Problem("request_id already belongs to different draft content; reopen the saved draft or start a new draft", 409)
                    saved = db.execute("SELECT revision FROM drafts WHERE id=?", (previous["draft_id"],)).fetchone()
                    return dict(id=previous["draft_id"], revision=saved["revision"], state="unsent", repeated=True)
            did = uuid.uuid4().hex
            db.execute("INSERT INTO drafts(id,workspace_id,recipient,subject,body) VALUES (?,?,?,?,?)", (did, wid, recipient, subject, body))
            if request_id is not None:
                db.execute("INSERT INTO draft_requests VALUES (?,?,?,?)", (wid, request_id, did, fingerprint))
        return dict(id=did, revision=1, state="unsent", repeated=False)

    def export(self, wid, kind, did=None):
        data = self.snapshot(wid)
        if kind == "tasks":
            out = io.StringIO(newline="")
            fields = ["owner", "due", "description", "state", "source_id", "source_version", "line"]
            writer = csv.DictWriter(out, fields, extrasaction="ignore")
            writer.writeheader()
            for row in data["tasks"]:
                if row["current"]:
                    safe = {k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for k, v in row.items()}
                    writer.writerow(safe)
            return out.getvalue().encode(), "text/csv; charset=utf-8", "tasks.csv"
        if kind == "draft":
            row = next((r for r in data["drafts"] if r["id"] == did), None)
            if row is None:
                raise Problem("draft not found", 404)
            mail = EmailMessage()
            mail["To"], mail["Subject"], mail["X-Unsent"] = row["recipient"], row["subject"], "1"
            mail.set_content(row["body"])
            return mail.as_bytes(), "message/rfc822", "draft.eml"
        raise Problem("export kind must be tasks or draft")


def make_server(store, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not put client identifiers or query strings into access logs.

        def send(self, data, status=200, content_type="application/json; charset=utf-8", filename=None):
            raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(raw)

        def dispatch(self, post=False):
            try:
                host = self.headers.get("Host", "")
                allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
                if host not in allowed or self.headers.get("Origin", "http://" + host) != "http://" + host:
                    raise Problem("use this workspace's local origin", 403)
                url = urlsplit(self.path)
                args = {key: values[-1] for key, values in parse_qs(url.query).items()}
                if post:
                    if self.headers.get_content_type() != "application/json":
                        raise Problem("Content-Type must be application/json", 415)
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        raise Problem("invalid Content-Length") from None
                    if not 0 < length <= 1048576:
                        raise Problem("request body must be 1 to 1048576 bytes", 413)
                    try:
                        args = json.loads(self.rfile.read(length))
                    except (ValueError, UnicodeError):
                        raise Problem("invalid JSON") from None
                    if not isinstance(args, dict):
                        raise Problem("JSON body must be an object")
                wid = args.get("workspace_id")
                if not post and url.path == "/":
                    return self.send((HERE / "index.html").read_bytes(), content_type="text/html; charset=utf-8")
                if not post and url.path == "/api/workspaces":
                    result = store.list_workspaces()
                elif not post and url.path == "/api/workspace":
                    result = store.snapshot(wid)
                elif not post and url.path == "/api/source":
                    try:
                        ver = int(args.get("version", ""))
                    except ValueError:
                        raise Problem("invalid version") from None
                    result = store.source(wid, args.get("source_id"), ver)
                elif not post and url.path == "/api/export":
                    raw, mime, name = store.export(wid, args.get("kind"), args.get("draft_id"))
                    return self.send(raw, content_type=mime, filename=name)
                elif post and url.path == "/api/workspaces":
                    result = store.create_workspace(args.get("name"))
                elif post and url.path == "/api/import":
                    result = store.import_source(wid, args.get("source_key"), args.get("title"), args.get("kind"), args.get("text"), args.get("expected_version", 0))
                elif post and url.path == "/api/ask":
                    result = store.ask(wid, args.get("question"))
                elif post and url.path == "/api/task":
                    result = store.update_task(wid, args.get("task_id"), args.get("revision"), args.get("state"))
                elif post and url.path == "/api/draft":
                    result = store.save_draft(wid, args.get("recipient"), args.get("subject"), args.get("body"), args.get("draft_id"), args.get("revision"), args.get("request_id"))
                else:
                    raise Problem("not found", 404)
                self.send(result)
            except Problem as exc:
                self.send({"error": str(exc)}, exc.status)
            except sqlite3.Error:
                self.send({"error": "database operation failed; no partial write was committed"}, 503)

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch(True)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="office-workspace.sqlite3")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(Store(args.db), args.port)
    print(f"Office workspace: http://127.0.0.1:{server.server_port} (local, no email sending)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
