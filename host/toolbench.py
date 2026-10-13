#!/usr/bin/env python3
"""Commons Toolbench: persistent evidence instruments, not a task executor.

General utility. No model calls, plans, macros, automatic association, or execution
of imported content. See toolbench/README.md for the HTTP instrument contract.
"""
from __future__ import annotations

import argparse
import base64
import difflib
import hashlib
import io
import json
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 16 * 1024 * 1024


class BenchError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def text(obj: dict, key: str, default=None) -> str:
    value = obj.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise BenchError("INVALID_INPUT", f"{key} must be a nonempty string")
    return value


# These are independent operations. Their order is deliberately not prescribed.
OPERATIONS = {
    "add_job": {"required": ["job_id", "title"], "optional": ["description"]},
    "add_source": {"required": ["source_id", "name", "source_ref"],
                   "optional": ["text", "data_base64", "media_type", "revision_of"],
                   "note": "Exactly one of text or data_base64. Sources are immutable; a revision is a new source."},
    "link": {"required": ["job_id", "source_id", "reason"],
             "note": "An explicit association by the caller; not a verified fact or automatic assignment."},
    "unlink": {"required": ["job_id", "source_id"], "note": "Removes the association and any selection, not the source or history."},
    "select": {"required": ["job_id", "source_ids"],
               "note": "Replace the ordered export selection with these linked sources. No automatic completeness judgment."},
    "annotate": {"required": ["note_id", "job_id", "text"], "optional": ["source_id"]},
    "resolve_note": {"required": ["note_id", "resolution"],
                     "note": "Records the caller's resolution; original question and prior events remain."},
}


class Bench:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(
              id TEXT PRIMARY KEY, name TEXT NOT NULL, source_ref TEXT NOT NULL,
              media_type TEXT NOT NULL, data BLOB NOT NULL, sha256 TEXT NOT NULL,
              revision_of TEXT REFERENCES sources(id));
            CREATE TABLE IF NOT EXISTS links(
              job_id TEXT REFERENCES jobs(id), source_id TEXT REFERENCES sources(id), reason TEXT NOT NULL,
              PRIMARY KEY(job_id,source_id));
            CREATE TABLE IF NOT EXISTS selections(
              job_id TEXT REFERENCES jobs(id), position INTEGER, source_id TEXT REFERENCES sources(id),
              PRIMARY KEY(job_id,position), UNIQUE(job_id,source_id));
            CREATE TABLE IF NOT EXISTS notes(
              id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id), source_id TEXT REFERENCES sources(id),
              text TEXT NOT NULL, resolution TEXT);
            CREATE TABLE IF NOT EXISTS events(
              revision INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT UNIQUE NOT NULL,
              request_digest TEXT NOT NULL, request_json TEXT NOT NULL, at TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
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
    def revision(db) -> int:
        return db.execute("SELECT COALESCE(MAX(revision),0) FROM events").fetchone()[0]

    @staticmethod
    def require(db, table: str, identifier: str):
        # table is an internal constant, never caller SQL.
        if db.execute(f"SELECT 1 FROM {table} WHERE id=?", (identifier,)).fetchone() is None:
            raise BenchError("NOT_FOUND", f"Unknown {table} identifier: {identifier}", 404)

    def apply(self, request: dict) -> dict:
        if not isinstance(request, dict):
            raise BenchError("INVALID_INPUT", "Expected a JSON object")
        op = text(request, "op")
        args = request.get("args", {})
        if op not in OPERATIONS or not isinstance(args, dict):
            raise BenchError("INVALID_INPUT", "Unknown operation or invalid args; inspect /api/operations")
        request_id = text(request, "request_id", str(uuid.uuid4()))
        actor = request.get("actor", "anonymous")  # Optional label, never a credential.
        if not isinstance(actor, str):
            raise BenchError("INVALID_INPUT", "actor must be text when provided")
        actor = actor if actor.strip() else "anonymous"
        expected = request.get("expected_revision")
        if expected is not None and (type(expected) is not int or expected < 0):
            raise BenchError("INVALID_INPUT", "expected_revision must be a nonnegative integer")
        normalized = {"op": op, "args": args, "actor": actor}
        try:
            body = canonical(normalized)
        except (ValueError, TypeError) as exc:
            raise BenchError("INVALID_INPUT", "Input must be finite JSON values") from exc
        digest = hashlib.sha256(body.encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT revision,request_digest FROM events WHERE request_id=?", (request_id,)).fetchone()
            if previous:
                if previous["request_digest"] != digest:
                    raise BenchError("REQUEST_CONFLICT", "This request_id already names a different operation", 409)
                return {"applied": False, "replayed": True, "revision": previous["revision"],
                        "current_revision": self.revision(db), "request_id": request_id}
            current = self.revision(db)
            if expected is not None and expected != current:
                raise BenchError("STATE_CONFLICT", f"State changed: expected {expected}, current {current}; inspect before choosing again", 409)
            for key in OPERATIONS[op]["required"]:
                if key != "source_ids":
                    text(args, key)
            try:
                self._change(db, op, args)
            except sqlite3.IntegrityError as exc:
                raise BenchError("DATA_CONFLICT", "Duplicate identifier or missing referenced object; inspect the current state", 409) from exc
            at = datetime.now(timezone.utc).isoformat()
            cur = db.execute("INSERT INTO events(request_id,request_digest,request_json,at) VALUES(?,?,?,?)",
                             (request_id, digest, body, at))
            return {"applied": True, "replayed": False, "revision": cur.lastrowid,
                    "current_revision": cur.lastrowid, "request_id": request_id}

    def _change(self, db, op, a):
        if op == "add_job":
            description = a.get("description", "")
            if not isinstance(description, str):
                raise BenchError("INVALID_INPUT", "description must be text")
            db.execute("INSERT INTO jobs VALUES(?,?,?)", (a["job_id"], a["title"], description))
        elif op == "add_source":
            if ("text" in a) == ("data_base64" in a):
                raise BenchError("INVALID_INPUT", "Supply exactly one of text or data_base64")
            if "text" in a:
                if not isinstance(a["text"], str):
                    raise BenchError("INVALID_INPUT", "text must be a string")
                data = a["text"].encode("utf-8")
            else:
                try:
                    data = base64.b64decode(a["data_base64"], validate=True)
                except (ValueError, TypeError) as exc:
                    raise BenchError("INVALID_INPUT", "Invalid base64 data") from exc
            media = text(a, "media_type", "text/plain" if "text" in a else "application/octet-stream")
            parent = a.get("revision_of")
            if parent is not None:
                self.require(db, "sources", text(a, "revision_of"))
            db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?)",
                       (a["source_id"], a["name"], a["source_ref"], media, data, hashlib.sha256(data).hexdigest(), parent))
        elif op in ("link", "unlink"):
            self.require(db, "jobs", a["job_id"])
            self.require(db, "sources", a["source_id"])
            if op == "link":
                db.execute("INSERT INTO links VALUES(?,?,?) ON CONFLICT(job_id,source_id) DO UPDATE SET reason=excluded.reason",
                           (a["job_id"], a["source_id"], a["reason"]))
            else:
                db.execute("DELETE FROM selections WHERE job_id=? AND source_id=?", (a["job_id"], a["source_id"]))
                db.execute("DELETE FROM links WHERE job_id=? AND source_id=?", (a["job_id"], a["source_id"]))
        elif op == "select":
            self.require(db, "jobs", a["job_id"])
            ids = a.get("source_ids")
            if not isinstance(ids, list) or any(not isinstance(s, str) for s in ids) or len(ids) != len(set(ids)):
                raise BenchError("INVALID_INPUT", "source_ids must be a list of distinct source IDs")
            linked = {r[0] for r in db.execute("SELECT source_id FROM links WHERE job_id=?", (a["job_id"],))}
            if not set(ids).issubset(linked):
                raise BenchError("UNLINKED_SELECTION", "Selection contains sources not associated with this job")
            db.execute("DELETE FROM selections WHERE job_id=?", (a["job_id"],))
            db.executemany("INSERT INTO selections VALUES(?,?,?)", [(a["job_id"], i, s) for i, s in enumerate(ids)])
        elif op == "annotate":
            self.require(db, "jobs", a["job_id"])
            source = a.get("source_id")
            if source is not None:
                self.require(db, "sources", text(a, "source_id"))
            db.execute("INSERT INTO notes VALUES(?,?,?,?,NULL)", (a["note_id"], a["job_id"], source, a["text"]))
        elif op == "resolve_note":
            self.require(db, "notes", a["note_id"])
            db.execute("UPDATE notes SET resolution=? WHERE id=?", (a["resolution"], a["note_id"]))

    def snapshot(self) -> dict:
        with self.connect() as db:
            db.execute("BEGIN")
            return {"revision": self.revision(db),
                    "jobs": [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY id")],
                    "sources": [dict(r) for r in db.execute("SELECT id,name,source_ref,media_type,sha256,revision_of,length(data) AS bytes FROM sources ORDER BY id")],
                    "links": [dict(r) for r in db.execute("SELECT * FROM links ORDER BY job_id,source_id")],
                    "selections": [dict(r) for r in db.execute("SELECT * FROM selections ORDER BY job_id,position")],
                    "notes": [dict(r) for r in db.execute("SELECT * FROM notes ORDER BY id")]}

    def source(self, source_id: str, *, include_base64: bool = True) -> dict:
        with self.connect() as db:
            self.require(db, "sources", source_id)
            row = dict(db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone())
        data = row.pop("data")
        if include_base64:
            row["data_base64"] = base64.b64encode(data).decode("ascii")
        try:
            row["text"] = data.decode("utf-8")
        except UnicodeDecodeError:
            row["text"] = None
        return row

    def history(self) -> list:
        with self.connect() as db:
            rows = db.execute("SELECT revision,request_id,request_json,at FROM events ORDER BY revision").fetchall()
            return [{"revision": r["revision"], "request_id": r["request_id"], "at": r["at"],
                     "operation": json.loads(r["request_json"])} for r in rows]

    def compare(self, left: str, right: str) -> dict:
        a = self.source(left, include_base64=False)
        b = self.source(right, include_base64=False)
        lines = None
        if a["text"] is not None and b["text"] is not None:
            lines = []
            diff = difflib.unified_diff(a["text"].splitlines(keepends=True),
                                        b["text"].splitlines(keepends=True),
                                        fromfile=left, tofile=right, lineterm="")
            for index, line in enumerate(diff):
                if index < 2 or line.startswith("@@"):
                    lines.append(line)
                    continue
                # Compare original endings, then render one display line per item.
                # Otherwise CRLF and missing-final-newline revisions look identical.
                content = line[1:]
                body = content.splitlines()
                displayed = body[0] if body else ""
                ending = content[len(displayed):]
                lines.append(line[0] + displayed)
                if not ending:
                    lines.append("\\ No newline at end of file")
                elif ending != "\n":
                    lines.append(f"\\ Line ending: {ending!a}")
        return {"left": left, "right": right, "same_bytes": a["sha256"] == b["sha256"],
                "left_sha256": a["sha256"], "right_sha256": b["sha256"], "text_diff": lines}

    def export(self, job_id: str) -> bytes:
        """Copy exactly the chosen sources. Never silently fill a missing attachment."""
        with self.connect() as db:
            db.execute("BEGIN")
            self.require(db, "jobs", job_id)
            job = dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            rows = db.execute("SELECT s.*,q.position,l.reason FROM selections q JOIN sources s ON s.id=q.source_id JOIN links l ON l.job_id=q.job_id AND l.source_id=q.source_id WHERE q.job_id=? ORDER BY q.position", (job_id,)).fetchall()
            notes = [dict(r) for r in db.execute("SELECT * FROM notes WHERE job_id=? ORDER BY id", (job_id,))]
            files, selected = {}, []
            for row in rows:
                record = dict(row)
                data = record.pop("data")
                name = "sources/" + hashlib.sha256(record["id"].encode()).hexdigest() + ".bin"
                files[name] = data
                selected.append({**record, "archive_path": name, "bytes": len(data)})
            selected_ids = {s["id"] for s in selected}
            all_links = [dict(r) for r in db.execute("SELECT * FROM links WHERE job_id=? ORDER BY source_id", (job_id,))]
            manifest = {"format": "commons-toolbench-handover-v1", "revision": self.revision(db),
                        "job": job, "selected": selected, "notes": notes,
                        "linked_not_selected": [r for r in all_links if r["source_id"] not in selected_ids],
                        "coverage": "Caller-selected evidence only; no completeness, approval, or release certification.",
                        "attribution": "Actor labels and association reasons are caller statements, not authenticated identities or verified facts."}
            files["manifest.json"] = (canonical(manifest) + "\n").encode()
            files["READ-ME.txt"] = ("TOOLBENCH HANDOVER\n\n" + job["title"] + "\n" + manifest["coverage"] +
                                     "\n\nOriginal source names, media types, ordering, association reasons and SHA-256 values are in manifest.json.\n"
                                     "The source files are copied byte-for-byte, named by an ID digest to avoid unsafe archive paths.\n"
                                     "Open questions and caller resolutions are retained; no software has decided they are complete.\n").encode()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                archive.writestr(info, data)
        return output.getvalue()

    def checkpoint(self) -> bytes:
        """Committed workspace ZIP for another Toolbench. Does not execute history or choose successor action."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with self.connect() as db:
                try:
                    db.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except sqlite3.Error:
                    pass
                dest = sqlite3.connect(tmp_path)
                try:
                    db.backup(dest)
                    # Read metadata from the copied snapshot, not the live workspace.
                    revision = self.revision(dest)
                finally:
                    dest.close()
            data = Path(tmp_path).read_bytes()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        sha = hashlib.sha256(data).hexdigest()
        manifest = {
            "format": "commons-toolbench-checkpoint-v1",
            "kind": "FULL_WORKSPACE_BACKUP",
            "revision": revision,
            "sha256": sha,
            "coverage": (
                "Committed workspace only; no drafts; does not execute history "
                "or choose successor action."
            ),
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, payload in (
                ("workspace.sqlite3", data),
                ("manifest.json", (canonical(manifest) + "\n").encode()),
            ):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                archive.writestr(info, payload)
        return output.getvalue()


def load_example(bench: Bench, path: Path):
    """Load inert sample objects, not associations, selections, or model decisions."""
    sample = json.loads(path.read_text(encoding="utf-8"))
    for kind, key, identifier in (("add_job", "jobs", "job_id"), ("add_source", "sources", "source_id")):
        for item in sample[key]:
            digest = hashlib.sha256(canonical(item).encode()).hexdigest()
            bench.apply({"op": kind, "args": item, "request_id": f"example:{kind}:{item[identifier]}:{digest}", "actor": "synthetic fixture"})


def server(bench: Bench, host: str = "127.0.0.1", port: int = 18450):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data, media="application/json; charset=utf-8", *, zip_filename=None):
            if not isinstance(data, bytes):
                data = (canonical(data) + "\n").encode()
            self.send_response(status)
            self.send_header("Content-Type", media)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if media == "application/zip":
                name = zip_filename or "toolbench-handover.zip"
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.end_headers()
            self.wfile.write(data)

        def invoke(self, call):
            try:
                call()
            except BenchError as exc:
                self.reply(exc.status, {"error": exc.code, "message": str(exc)})
            except (ValueError, TypeError, KeyError) as exc:
                self.reply(400, {"error": "INVALID_INPUT", "message": str(exc)})
            except sqlite3.Error:
                self.reply(503, {"error": "STORAGE_ERROR", "message": "Storage operation failed; no success claimed. Inspect before retrying."})

        def do_GET(self):
            def run():
                url = urlsplit(self.path)
                q = parse_qs(url.query)
                param = lambda k: q.get(k, [""])[0]
                if url.path in ("/", "/toolbench.html"):
                    self.reply(200, (ROOT / "toolbench.html").read_bytes(), "text/html; charset=utf-8")
                elif url.path == "/api/state":
                    self.reply(200, bench.snapshot())
                elif url.path == "/api/source":
                    self.reply(200, bench.source(param("id")))
                elif url.path == "/api/history":
                    self.reply(200, bench.history())
                elif url.path == "/api/compare":
                    self.reply(200, bench.compare(param("left"), param("right")))
                elif url.path == "/api/export":
                    self.reply(200, bench.export(param("job")), "application/zip")
                elif url.path == "/api/checkpoint":
                    self.reply(200, bench.checkpoint(), "application/zip",
                               zip_filename="toolbench-checkpoint.zip")
                elif url.path == "/api/operations":
                    self.reply(200, {"operations": OPERATIONS, "request": {"op": "operation name", "args": {},
                               "request_id": "optional stable retry ID", "actor": "optional attribution label",
                               "expected_revision": "optional nonnegative integer for concurrent-edit detection"},
                               "read": ["/api/state", "/api/source?id=...", "/api/compare?left=...&right=...", "/api/history", "/api/export?job=...", "/api/checkpoint"],
                               "write": "POST /api/op; one caller-chosen operation per request; no next-step policy"})
                else:
                    self.reply(404, {"error": "NOT_FOUND"})
            self.invoke(run)

        def do_POST(self):
            def run():
                if urlsplit(self.path).path != "/api/op":
                    self.reply(404, {"error": "NOT_FOUND"}); return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    raise BenchError("INVALID_SIZE", f"Request size must be 1..{MAX_BODY} bytes", 413)
                request = json.loads(self.rfile.read(size), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant: {x}")))
                self.reply(200, bench.apply(request))
            self.invoke(run)
    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Persistent SQLite file; choose the working data location")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18450)
    parser.add_argument("--example", action="store_true", help="Load inert synthetic jobs and sources; no associations or selections")
    args = parser.parse_args()
    bench = Bench(args.db)
    if args.example:
        load_example(bench, ROOT / "toolbench/example.json")
    http = server(bench, args.host, args.port)
    print(f"Toolbench: http://{args.host}:{http.server_port} — data persists in the selected SQLite file", flush=True)
    print("No account wall. Everyone who can reach this bench can read and edit it. Keep private data off publicly reachable benches.", flush=True)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()


if __name__ == "__main__":
    main()
