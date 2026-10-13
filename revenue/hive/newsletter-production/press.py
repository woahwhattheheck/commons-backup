#!/usr/bin/env python3
"""Source-linked newsletter production desk. Standard library; no external sends."""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import io
import json
import re
import sqlite3
import uuid
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from email_handoff import HandoffError, build_email_bundle

HERE = Path(__file__).resolve().parent
MAX_BODY = 2_000_000
IDS = ("week1", "week2", "week3", "week4")

class Invalid(ValueError):
    pass

class Conflict(Invalid):
    pass

class Missing(Invalid):
    pass

def packed(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise Invalid("Use finite, JSON-compatible values") from exc

def text(value, field, limit=100000, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise Invalid(f"{field}: expected {'optional ' if empty else ''}text, maximum {limit} characters")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise Invalid(f"{field}: unsupported control character")
    return value

def schedule(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z", value):
        raise Invalid("Schedule must be UTC YYYY-MM-DDTHH:MM:00Z")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:00Z").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise Invalid("Schedule is not a valid UTC date/time") from exc

def validate(doc):
    if not isinstance(doc, dict):
        raise Invalid("Project must be an object")
    packed(doc)
    text(doc.get("title"), "title", 160)
    text(doc.get("client"), "client", 160)
    text(doc.get("original_interview"), "original_interview")
    text(doc.get("notes", ""), "notes", empty=True)
    brand = doc.get("brand")
    if not isinstance(brand, dict):
        raise Invalid("brand must be an object")
    text(brand.get("name"), "brand.name", 120)
    text(brand.get("footer", ""), "brand.footer", 1000, empty=True)
    if not isinstance(brand.get("accent"), str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", brand["accent"]):
        raise Invalid("Brand accent must be a six-digit hex color")
    sources = doc.get("sources")
    if not isinstance(sources, list) or not 4 <= len(sources) <= 100:
        raise Invalid("Provide between four and 100 source sections")
    source_ids = []
    for src in sources:
        if not isinstance(src, dict):
            raise Invalid("Each source must be an object")
        sid = text(src.get("id"), "source.id", 40)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
            raise Invalid("Source IDs may contain letters, digits, underscore and hyphen")
        source_ids.append(sid)
        text(src.get("text"), "source.text")
        text(src.get("reference", ""), "source.reference", 1000, empty=True)
    if len(set(source_ids)) != len(source_ids):
        raise Invalid("Source IDs must be unique")
    issues = doc.get("issues")
    if not isinstance(issues, list) or len(issues) != 4:
        raise Invalid("A monthly package must contain exactly four issues")
    for issue, iid in zip(issues, IDS):
        if not isinstance(issue, dict) or issue.get("id") != iid:
            raise Invalid("Issue IDs/order must be week1 through week4")
        subject = text(issue.get("subject"), "subject", 200)
        if "\n" in subject or "\r" in subject:
            raise Invalid("Subject must be one line")
        text(issue.get("body"), "body", 100000)
        refs = issue.get("source_ids")
        if not isinstance(refs, list) or not refs or any(not isinstance(x, str) for x in refs):
            raise Invalid("Each issue needs a list of source IDs")
        if len(set(refs)) != len(refs) or not set(refs) <= set(source_ids):
            raise Invalid("Issue references must be unique existing source IDs")
        schedule(issue.get("scheduled_utc"))
    return doc

def fingerprint(doc, issue):
    refs = set(issue["source_ids"])
    data = {"brand": doc["brand"], "subject": issue["subject"], "body": issue["body"],
            "scheduled_utc": issue["scheduled_utc"], "source_ids": issue["source_ids"],
            "sources": [s for s in doc["sources"] if s["id"] in refs]}
    return hashlib.sha256(packed(data).encode()).hexdigest()

def issues_to_review(doc):
    problems = []
    for i in doc["issues"]:
        if i.get("reviewed_hash") != fingerprint(doc, i):
            problems.append(f"{i['id']}: source and copy review needed")
    for field in ("subject", "body", "scheduled_utc"):
        if len({i[field].strip().casefold() for i in doc["issues"]}) != 4:
            problems.append(f"Four distinct {field} values are required")
    return problems

def make_draft(data):
    if not isinstance(data, dict):
        raise Invalid("Intake must be an object")
    interview = text(data.get("interview"), "interview")
    sections = [p.strip() for p in re.split(r"\n\s*\n", interview) if p.strip()]
    if not 4 <= len(sections) <= 100:
        raise Invalid("Separate at least four interview topics with blank lines (maximum 100)")
    try:
        start = date.fromisoformat(data.get("start_date", ""))
        days = [start + timedelta(days=7 * n) for n in range(4)]
    except (TypeError, ValueError, OverflowError) as exc:
        raise Invalid("Choose a valid first issue date with room for four weeks") from exc
    sources = [{"id": f"s{n+1}", "text": part, "reference": f"Interview section {n+1}"}
               for n, part in enumerate(sections)]
    issues = []
    for n, iid in enumerate(IDS):
        chosen = sources[n::4]
        heading = chosen[0]["text"].splitlines()[0].strip()[:160]
        issues.append({"id": iid, "subject": heading, "body": "\n\n".join(s["text"].partition("\n")[2] or s["text"] for s in chosen),
                       "source_ids": [s["id"] for s in chosen],
                       "scheduled_utc": days[n].isoformat() + "T14:00:00Z", "reviewed_hash": None})
    doc = {"title": data.get("title"), "client": data.get("client"), "original_interview": interview,
           "brand": {"name": data.get("brand_name", data.get("client")),
                     "accent": data.get("accent", "#215b55"), "footer": "Draft for editorial review. Not sent."},
           "notes": data.get("notes", ""), "sources": sources, "issues": issues}
    return validate(doc)

class Store:
    def __init__(self, database):
        self.database = str(database)
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS projects(
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history(project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                saved_at TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(project_id,revision));""")
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
    def _write(self, db, pid, revision, doc):
        payload = packed(doc)
        db.execute("INSERT OR REPLACE INTO projects VALUES(?,?,?)", (pid, revision, payload))
        db.execute("INSERT INTO history VALUES(?,?,?,?)", (pid, revision, datetime.now(timezone.utc).isoformat(), payload))
        return self._view(pid, revision, doc)
    def _view(self, pid, revision, doc):
        return {"id": pid, "revision": revision, "document": doc,
                "review_needed": issues_to_review(doc), "delivery_status": "NOT_SENT"}
    def create(self, data):
        doc = make_draft(data)
        with self.connect() as db:
            return self._write(db, uuid.uuid4().hex, 1, doc)
    def get(self, pid, revision=None):
        with self.connect() as db:
            row = db.execute("SELECT revision,payload FROM projects WHERE id=?", (pid,)).fetchone() if revision is None else db.execute(
                "SELECT revision,payload FROM history WHERE project_id=? AND revision=?", (pid, revision)).fetchone()
        if row is None:
            raise Missing("Project or revision not found")
        return self._view(pid, row["revision"], json.loads(row["payload"]))
    def listing(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,revision,payload FROM projects ORDER BY rowid DESC").fetchall()
        return [{"id": r["id"], "revision": r["revision"], "title": json.loads(r["payload"])["title"],
                 "client": json.loads(r["payload"])["client"]} for r in rows]
    def history(self, pid):
        self.get(pid)
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT revision,saved_at FROM history WHERE project_id=? ORDER BY revision DESC", (pid,))]
    def save(self, pid, expected, doc, review=None):
        if type(expected) is not int or expected < 1:
            raise Invalid("expected_revision must be a positive integer")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision,payload FROM projects WHERE id=?", (pid,)).fetchone()
            if row is None:
                raise Missing("Project not found")
            if row["revision"] != expected:
                raise Conflict("A newer revision exists. Reopen before saving; your draft was not overwritten.")
            old = json.loads(row["payload"])
            if review is not None:
                if review not in IDS:
                    raise Invalid("Unknown issue")
                doc = json.loads(row["payload"])
            else:
                validate(doc)
                doc = json.loads(packed(doc))
                if doc["original_interview"] != old["original_interview"]:
                    raise Invalid("Original interview is retained unchanged; edit working source sections instead")
            for current, previous in zip(doc["issues"], old["issues"]):
                current["reviewed_hash"] = (previous.get("reviewed_hash")
                    if fingerprint(doc, current) == fingerprint(old, previous) else None)
                if current["id"] == review:
                    current["reviewed_hash"] = fingerprint(doc, current)
            return self._write(db, pid, expected + 1, doc)

def render(doc, issue, preview=False):
    e = html.escape
    paragraphs = "".join("<p>" + e(p).replace("\n", "<br>") + "</p>" for p in issue["body"].split("\n\n"))
    notice = '<aside style="padding:12px;background:#fff0c2">EDITORIAL PREVIEW — NOT SENT</aside>' if preview else ""
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>{e(issue["subject"])}</title><body style="margin:0;background:#f1f3f2;font-family:Arial,sans-serif;color:#172622">'
            f'<main style="max-width:640px;margin:24px auto;background:white;padding:32px;border-top:6px solid {doc["brand"]["accent"]}">'
            f'{notice}<p>{e(doc["brand"]["name"])}</p><h1>{e(issue["subject"])}</h1>{paragraphs}'
            f'<hr><p style="font-size:13px">{e(doc["brand"]["footer"])}</p></main></body></html>')

def requested_revision(query):
    """Bounded positive revision; duplicate or blank pins are not silently ignored."""
    values = query.get("revision")
    if values is None:
        return None
    if len(values) != 1 or not re.fullmatch(r"[1-9][0-9]{0,8}", values[0]):
        raise Invalid("revision must be one positive integer of at most nine digits")
    return int(values[0])

def email_bundle(view):
    """Compose WREN's unchanged exporter; retain brand originals in the outer ZIP."""
    doc = view["document"]
    footer = doc["brand"]["footer"]
    issues = [{"id": i["id"], "subject": i["subject"],
               "body": i["body"] + ("\n\n" + footer if footer else ""),
               "scheduled_at": i["scheduled_utc"], "source_refs": i["source_ids"]}
              for i in doc["issues"]]
    metadata = {"project_id": view["id"], "source_revision": view["revision"],
                "review_needed": issues_to_review(doc), "delivery_status": "NOT_SENT",
                "original_interview_sha256": hashlib.sha256(doc["original_interview"].encode()).hexdigest(),
                "working_sources": [{"id": src["id"], "reference": src.get("reference", ""),
                                     "sha256": hashlib.sha256(src["text"].encode()).hexdigest()}
                                    for src in doc["sources"]]}
    try:
        return build_email_bundle(issues, publication=doc["brand"]["name"], source_metadata=metadata)
    except HandoffError as exc:
        raise Invalid("Email handoff: " + str(exc)) from exc

def export_package(view, ready=False):
    doc = view["document"]
    validate(doc)
    problems = issues_to_review(doc)
    if ready and problems:
        raise Conflict("Ready export requires current review: " + "; ".join(problems))
    handoff = email_bundle(view)
    out = io.BytesIO()
    manifest = {"project_id": view["id"], "revision": view["revision"], "status": "REVIEWED_HANDOFF" if ready else "DRAFT",
                "delivery_status": "NOT_SENT", "review_needed": problems, "files": {}}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        def add(name, value):
            blob = value.encode("utf-8") if isinstance(value, str) else value
            z.writestr(name, blob)
            manifest["files"][name] = {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
        add("workspace.json", json.dumps(view, ensure_ascii=False, indent=2))
        add("original-interview.txt", doc["original_interview"])
        table = io.StringIO(newline="")
        writer = csv.writer(table)
        writer.writerow(["issue_id", "scheduled_utc", "html_file", "text_file", "delivery_status"])
        calendar = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Commons//Newsletter Production//EN"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for issue in doc["issues"]:
            iid = issue["id"]
            add(f"{iid}.html", render(doc, issue))
            add(f"{iid}.txt", issue["subject"] + "\n\n" + issue["body"] + "\n\n" + doc["brand"]["footer"] + "\n")
            writer.writerow([iid, issue["scheduled_utc"], f"{iid}.html", f"{iid}.txt", "NOT_SENT"])
            calendar.extend(["BEGIN:VEVENT", f"UID:{view['id']}-{iid}@commons.invalid", f"DTSTAMP:{stamp}",
                "DTSTART:" + schedule(issue["scheduled_utc"]).strftime("%Y%m%dT%H%M%SZ"),
                "DURATION:PT15M", f"SUMMARY:Newsletter {iid} editorial handoff", "STATUS:TENTATIVE", "END:VEVENT"])
        calendar.append("END:VCALENDAR")
        add("schedule.csv", table.getvalue())
        add("editorial-calendar.ics", "\r\n".join(calendar) + "\r\n")
        add("HANDOFF.txt", "NOT SENT. Import the four HTML/text files into the client's existing email platform.\n"
            "Check subject, sender, platform unsubscribe/footer merge tags, audience consent/preferences, and UTC schedule there.\n"
            "The calendar contains editorial reminders only; it neither schedules nor sends email.\n"
            "Review labels record operator review of source-linked copy, not automated factual verification.\n")
        with zipfile.ZipFile(io.BytesIO(handoff)) as peer:
            for name in peer.namelist():
                add("email-handoff/" + name, peer.read(name))
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return out.getvalue()

def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def send(self, status, body, mime="application/json; charset=utf-8", filename=None):
            data = (packed(body) if isinstance(body, (dict, list)) else body)
            data = data.encode("utf-8") if isinstance(data, str) else data
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)
        def route(self):
            parsed = urlsplit(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            q = parse_qs(parsed.query, keep_blank_values=True)
            data = None
            if self.command in ("POST", "PUT"):
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError as exc:
                    raise Invalid("Invalid Content-Length") from exc
                if not 0 < size <= MAX_BODY:
                    raise Invalid("JSON request must be between 1 and 2000000 bytes")
                try:
                    data = json.loads(self.rfile.read(size), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                except (ValueError, UnicodeError) as exc:
                    raise Invalid("Invalid JSON") from exc
                if not isinstance(data, dict):
                    raise Invalid("JSON request must be an object")
            if self.command == "GET" and not parts:
                return self.send(200, (HERE / "desk.html").read_bytes(), "text/html; charset=utf-8")
            if parts == ["api", "projects"]:
                if self.command == "GET":
                    return self.send(200, store.listing())
                if self.command == "POST":
                    return self.send(201, store.create(data))
            if parts == ["api", "demo"] and self.command == "POST":
                return self.send(201, store.create(json.loads((HERE / "demo.json").read_text(encoding="utf-8"))))
            if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
                pid = parts[2]
                if len(parts) == 3:
                    if self.command == "GET":
                        return self.send(200, store.get(pid, requested_revision(q)))
                    if self.command == "PUT":
                        return self.send(200, store.save(pid, data.get("expected_revision"), data.get("document")))
                if parts[3:] == ["history"] and self.command == "GET":
                    return self.send(200, store.history(pid))
                if len(parts) == 5 and parts[3] == "review" and self.command == "POST":
                    return self.send(200, store.save(pid, data.get("expected_revision"), None, parts[4]))
            if len(parts) == 3 and parts[0] == "preview" and self.command == "GET":
                doc = store.get(parts[1], requested_revision(q))["document"]
                issue = next((i for i in doc["issues"] if i["id"] == parts[2]), None)
                if issue is None:
                    raise Missing("Issue not found")
                return self.send(200, render(doc, issue, preview=True), "text/html; charset=utf-8")
            if len(parts) == 2 and parts[0] == "export" and self.command == "GET":
                revision = requested_revision(q)
                view = store.get(parts[1])
                if revision is not None and revision != view["revision"]:
                    raise Conflict("A newer revision exists. Reopen before exporting; no different revision was downloaded.")
                return self.send(200, export_package(view, q.get("ready") == ["1"]),
                                 "application/zip", "newsletter-month.zip")
            raise Missing("Route not found")
        def handle_request(self):
            try:
                self.route()
            except Conflict as exc:
                self.send(409, {"error": str(exc)})
            except Missing as exc:
                self.send(404, {"error": str(exc)})
            except Invalid as exc:
                self.send(400, {"error": str(exc)})
            except sqlite3.Error:
                self.send(503, {"error": "Workspace storage unavailable; no success is claimed"})
        do_GET = do_POST = do_PUT = handle_request
    return Handler

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="newsletter.sqlite3")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(Store(args.db)))
    print(f"Newsletter Production: http://127.0.0.1:{server.server_port} (local, unsent)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
