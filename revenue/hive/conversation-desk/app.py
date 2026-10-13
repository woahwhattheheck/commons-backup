#!/usr/bin/env python3
"""Conversation Desk: local screenshot/text intake and user-led reply drafting."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
MAX_IMAGE = 6 * 1024 * 1024
MAX_BODY = 9 * 1024 * 1024
FIELDS = {"title": 120, "transcript": 30000, "context": 10000,
          "intent": 30, "reply": 4000, "question": 1000, "draft": 6000}
INTENTS = {"respond", "follow_up", "invite", "boundary", "close"}


class DeskError(ValueError):
    status = 400


class Missing(DeskError):
    status = 404


class Conflict(DeskError):
    status = 409


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_fields(value):
    if not isinstance(value, dict):
        raise DeskError("The conversation must be a JSON object.")
    out = {}
    for key, limit in FIELDS.items():
        if key not in value:
            continue
        text = value[key]
        if not isinstance(text, str) or len(text) > limit or "\x00" in text:
            raise DeskError(f"{key} must be text, at most {limit} characters, without NUL.")
        try:
            text.encode("utf-8")
        except UnicodeError:
            raise DeskError(f"{key} contains invalid Unicode.") from None
        out[key] = text
    if "title" in out and not out["title"].strip():
        raise DeskError("Give this conversation a title.")
    if "intent" in out and out["intent"] not in INTENTS:
        raise DeskError("Choose a supported drafting intent.")
    return out


def sentence(text):
    text = text.strip()
    return text if not text or text[-1] in ".!?…" else text + "."


def suggestions(conversation):
    """Use only the user's proposed words; never invent facts from a transcript."""
    value = validate_fields(conversation)
    intent = value.get("intent", "respond")
    reply = sentence(value.get("reply", ""))
    question = value.get("question", "").strip()
    if question and question[-1] not in "?!…":
        question += "?"
    if not reply and intent != "follow_up":
        raise DeskError("Write the point or proposal you want to communicate first.")
    if intent == "follow_up" and not question:
        raise DeskError("Write the follow-up question you want to ask.")
    core = " ".join(part for part in (reply, question) if part)
    if intent == "respond":
        texts = [f"Thanks for the message. {core}", core, f"My take: {core}"]
    elif intent == "follow_up":
        texts = [f"I'd like to hear more. {core}", core, f"Now I'm curious: {core}"]
    elif intent == "invite":
        core = " ".join(part for part in (reply, question or "Would that work for you?") if part)
        texts = [f"I'd enjoy meeting up. {core}", core, f"Here's an idea: {core}"]
    elif intent == "boundary":
        texts = [f"I want to be clear and considerate. {core}", core,
                 f"Just to be clear about what works for me: {core}"]
    else:
        texts = [f"Thanks for the conversation. {core} Take care.", f"{core} Take care.",
                 f"{core} Wishing you well."]
    tones = ["Warm", "Direct", "Gentle" if intent in {"boundary", "close"} else "Light"]
    return {"engine": "local-templates-v1", "suggestions": [
        {"tone": tone, "text": text} for tone, text in zip(tones, texts)],
        "note": "Templates use your proposed words, not inferred personal facts. Review against the transcript before sending."}


def image_bytes(value):
    if not isinstance(value, dict) or not isinstance(value.get("data_base64"), str):
        raise DeskError("Choose a PNG, JPEG or WebP image.")
    try:
        data = base64.b64decode(value["data_base64"], validate=True)
    except (ValueError, binascii.Error):
        raise DeskError("The image is not valid base64.") from None
    if not data or len(data) > MAX_IMAGE:
        raise DeskError("Image size must be between 1 byte and 6 MiB.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise DeskError("Only PNG, JPEG and WebP screenshot bytes are supported.")
    name = value.get("name", "screenshot")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise DeskError("The image name must be 1–200 characters.")
    try:
        name.encode("utf-8")
    except UnicodeError:
        raise DeskError("The image name contains invalid Unicode.") from None
    return data, mime, name


def transcribe(data):
    executable = shutil.which("tesseract")
    if not executable:
        raise DeskError("Local OCR is unavailable. Enter or paste the transcript manually, or install Tesseract with English data.")
    with tempfile.TemporaryDirectory(prefix="conversation-ocr-") as folder:
        path = Path(folder) / "screenshot"
        path.write_bytes(data)
        try:
            result = subprocess.run([executable, str(path), "stdout", "-l", "eng", "--psm", "6"],
                                    capture_output=True, timeout=20, check=False)
        except subprocess.TimeoutExpired:
            raise DeskError("Local OCR timed out; enter or paste the transcript manually.") from None
        except OSError:
            raise DeskError("Local OCR could not start; enter or paste the transcript manually.") from None
    if result.returncode:
        raise DeskError("Local OCR could not read this image. Try a clearer PNG/JPEG or enter the transcript manually.")
    text = result.stdout.decode("utf-8", errors="replace").strip()
    if len(text) > FIELDS["transcript"]:
        raise DeskError("OCR text exceeds the transcript limit; use a smaller screenshot.")
    return text


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS conversations(
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, transcript TEXT NOT NULL,
                    context TEXT NOT NULL, intent TEXT NOT NULL, reply TEXT NOT NULL,
                    question TEXT NOT NULL, draft TEXT NOT NULL, revision INTEGER NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS images(
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, mime TEXT NOT NULL, data BLOB NOT NULL,
                    sha256 TEXT NOT NULL);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _read(self, db, cid):
        row = db.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        if row is None:
            raise Missing("Conversation not found.")
        value = dict(row)
        value["images"] = [dict(r) for r in db.execute(
            "SELECT id,name,mime,sha256,length(data) AS size FROM images WHERE conversation_id=? ORDER BY rowid", (cid,))]
        return value

    def _revision(self, db, cid, expected):
        value = self._read(db, cid)
        if type(expected) is not int or expected != value["revision"]:
            raise Conflict("This conversation changed. Reload it before saving or deleting; your edits have not been applied.")
        return value

    def list(self):
        with self.db() as db:
            return [dict(r) for r in db.execute(
                "SELECT id,title,revision,updated FROM conversations ORDER BY updated DESC,id")]

    def get(self, cid):
        with self.db() as db:
            return self._read(db, cid)

    def create(self, values):
        fields = {key: "" for key in FIELDS}
        fields.update(title="Untitled conversation", intent="respond")
        fields.update(validate_fields(values))
        cid, stamp = uuid.uuid4().hex, now()
        with self.db() as db:
            db.execute("INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (cid, *(fields[k] for k in FIELDS), 1, stamp, stamp))
            return self._read(db, cid)

    def update(self, cid, values, expected):
        fields = validate_fields(values)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._revision(db, cid, expected)
            if fields:
                db.execute("UPDATE conversations SET " + ",".join(k + "=?" for k in fields) +
                           ",revision=revision+1,updated=? WHERE id=?", (*fields.values(), now(), cid))
            return self._read(db, cid)

    def add_image(self, cid, values, expected):
        data, mime, name = image_bytes(values)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._revision(db, cid, expected)
            db.execute("INSERT INTO images VALUES(?,?,?,?,?,?)",
                       (uuid.uuid4().hex, cid, name, mime, data, hashlib.sha256(data).hexdigest()))
            db.execute("UPDATE conversations SET revision=revision+1,updated=? WHERE id=?", (now(), cid))
            return self._read(db, cid)

    def image(self, cid, iid):
        with self.db() as db:
            row = db.execute("SELECT * FROM images WHERE id=? AND conversation_id=?", (iid, cid)).fetchone()
            if row is None:
                raise Missing("Screenshot not found in this conversation.")
            return dict(row)

    def delete_image(self, cid, iid, expected):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._revision(db, cid, expected)
            if db.execute("DELETE FROM images WHERE id=? AND conversation_id=?", (iid, cid)).rowcount != 1:
                raise Missing("Screenshot not found in this conversation.")
            db.execute("UPDATE conversations SET revision=revision+1,updated=? WHERE id=?", (now(), cid))
            return self._read(db, cid)

    def delete(self, cid, expected):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._revision(db, cid, expected)
            db.execute("DELETE FROM conversations WHERE id=?", (cid,))
        return {"deleted": True}

    def erase(self):
        with self.db() as db:
            db.execute("DELETE FROM conversations")
        return {"deleted": True, "conversations": 0}

    def export(self):
        with self.db() as db:
            db.execute("BEGIN")
            conversations = [self._read(db, row[0]) for row in db.execute("SELECT id FROM conversations ORDER BY id")]
            images = []
            for row in db.execute("SELECT * FROM images ORDER BY id"):
                image = dict(row)
                image["data_base64"] = base64.b64encode(image.pop("data")).decode("ascii")
                images.append(image)
            return {"format": "conversation-desk-export-v1", "exported": now(),
                    "conversations": conversations, "images": images}


def server(store, host="127.0.0.1", port=8769):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Conversation paths and contents do not go to access logs.

        def send(self, status, body, mime="application/json; charset=utf-8", download=False):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=True, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if download:
                self.send_header("Content-Disposition", 'attachment; filename="conversation-desk-export.json"')
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            if self.headers.get_content_type() != "application/json":
                raise DeskError("Use application/json.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise DeskError("Invalid body length.") from None
            if not 0 < length <= MAX_BODY:
                raise DeskError("Request is empty or larger than 9 MiB.")
            try:
                def reject_constant(_):
                    raise ValueError("non-finite constant")
                result = json.loads(self.rfile.read(length), parse_constant=reject_constant)
            except (ValueError, UnicodeError, RecursionError):
                raise DeskError("The request is not valid JSON.") from None
            if not isinstance(result, dict):
                raise DeskError("Send a JSON object.")
            return result

        def dispatch(self):
            path = urlsplit(self.path).path
            if self.command == "GET" and path in {"/", "/index.html", "/desk.js"}:
                filename = "desk.js" if path == "/desk.js" else "index.html"
                mime = "text/javascript" if filename.endswith(".js") else "text/html"
                return self.send(200, (HERE / filename).read_bytes(), mime + "; charset=utf-8")
            if self.command == "GET" and path == "/api/state":
                return self.send(200, {"conversations": store.list(), "ocr_available": bool(shutil.which("tesseract"))})
            if self.command == "GET" and path == "/api/export":
                return self.send(200, store.export(), download=True)
            data = self.body() if self.command in {"POST", "DELETE"} else {}
            if path == "/api/erase" and self.command == "POST":
                if data.get("confirmation") != "ERASE":
                    raise DeskError("Type ERASE to delete the complete workspace.")
                return self.send(200, store.erase())
            if path == "/api/conversations" and self.command == "POST":
                return self.send(201, store.create(data))
            parts = path.strip("/").split("/")
            if len(parts) >= 3 and parts[:2] == ["api", "conversations"]:
                cid = parts[2]
                revision = data.get("expected_revision")
                if len(parts) == 3:
                    if self.command == "GET":
                        return self.send(200, store.get(cid))
                    if self.command == "POST":
                        return self.send(200, store.update(cid, data, revision))
                    if self.command == "DELETE":
                        return self.send(200, store.delete(cid, revision))
                if len(parts) == 4 and self.command == "POST":
                    if parts[3] == "suggest":
                        value = store.get(cid)
                        if type(revision) is not int or revision != value["revision"]:
                            raise Conflict("Reload the changed conversation before drafting.")
                        return self.send(200, {**suggestions(value), "revision": value["revision"]})
                    if parts[3] == "images":
                        return self.send(201, store.add_image(cid, data, revision))
                if len(parts) in {5, 6} and parts[3] == "images":
                    iid = parts[4]
                    if len(parts) == 5 and self.command == "GET":
                        image = store.image(cid, iid)
                        return self.send(200, image["data"], image["mime"])
                    if len(parts) == 5 and self.command == "DELETE":
                        return self.send(200, store.delete_image(cid, iid, revision))
                    if len(parts) == 6 and parts[5] == "ocr" and self.command == "POST":
                        value = store.get(cid)
                        if type(revision) is not int or revision != value["revision"]:
                            raise Conflict("Reload the changed conversation before transcription.")
                        return self.send(200, {"text": transcribe(store.image(cid, iid)["data"]),
                                               "revision": value["revision"], "image_id": iid})
            raise Missing("Route not found.")

        def handle_request(self):
            try:
                self.dispatch()
            except DeskError as exc:
                self.send(exc.status, {"error": str(exc)})
            except sqlite3.OperationalError:
                self.send(503, {"error": "The workspace is busy or unavailable. Retry after checking the database path."})
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = do_POST = do_DELETE = handle_request

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="conversation-desk.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8769, type=int)
    args = parser.parse_args()
    httpd = server(Store(args.db), args.host, args.port)
    print(f"Conversation Desk: http://{args.host}:{httpd.server_port} (shared local workspace; no automatic sends)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
