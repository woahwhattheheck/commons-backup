#!/usr/bin/env python3
"""Local browser workspace for the existing purchasing paperwork operator.

The canonical matcher is imported unchanged. All inputs, outputs and revisions
stay in the selected SQLite file. This application never sends or posts them.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import closing
import csv
from decimal import DecimalException
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import parse_qs, urlsplit
import uuid
import zipfile

import purchasing_operator as engine

ROOT = Path(__file__).resolve().parent
SCHEMA = "commons-purchasing-desk-v1"
KINDS = ("vendors", "purchase_orders", "invoices")
MAX_BODY = 12 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024


class DeskError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def text(value: object, name: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise DeskError(f"{name} must be text up to {maximum} characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DeskError(f"{name} must be valid Unicode") from exc
    return value


def file_record(value: object, label: str) -> tuple[dict, bytes]:
    if not isinstance(value, dict):
        raise DeskError(f"{label} must contain a filename and base64 data")
    name = text(value.get("name"), f"{label}.name", 160)
    if not name.strip():
        raise DeskError(f"{label}.name must be nonempty")
    encoded = text(value.get("data"), f"{label}.data", 4 * ((MAX_FILE + 2) // 3))
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise DeskError(f"{label} contains invalid base64") from exc
    if len(raw) > MAX_FILE:
        raise DeskError(f"{label} exceeds the 2 MiB per-file limit", 413)
    return {"name": name, "data": base64.b64encode(raw).decode("ascii"), "sha256": sha(raw), "bytes": len(raw)}, raw


def csv_shape(raw: bytes, kind: str) -> None:
    try:
        content = raw.decode("utf-8-sig")
        if "\x00" in content:
            raise DeskError(f"{kind}: CSV contains a NUL character")
        reader = csv.reader(io.StringIO(content, newline=""), strict=True)
        header = next(reader, [])
        if not header or any(not item for item in header) or len(set(header)) != len(header):
            raise DeskError(f"{kind}: CSV needs distinct nonempty column names")
        for row in reader:
            if row and len(row) != len(header):
                raise DeskError(f"{kind}: CSV row ending at line {reader.line_num} has {len(row)} columns; expected {len(header)}")
    except (UnicodeError, csv.Error) as exc:
        raise DeskError(f"{kind}: expected well-formed UTF-8 CSV ({exc})") from exc


def draft_key(draft: dict) -> str:
    # Covers source hashes and issues, not merely the potentially reused invoice ID.
    return sha(canonical(draft).encode("utf-8"))


def prepare(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise DeskError("request must be an object")
    title = text(payload.get("title", "Untitled packet"), "title", 160).strip()
    if not title:
        raise DeskError("title must be nonempty")
    supplied = payload.get("sources")
    if not isinstance(supplied, dict) or set(supplied) != set(KINDS):
        raise DeskError("sources must contain vendors, purchase_orders and invoices")
    sources, references = {}, {}
    try:
        with tempfile.TemporaryDirectory(prefix="purchasing-desk-") as directory:
            paths = {}
            for kind in KINDS:
                item, raw = file_record(supplied[kind], kind)
                csv_shape(raw, kind)
                sources[kind] = item
                paths[kind] = Path(directory) / f"{kind}.csv"
                paths[kind].write_bytes(raw)
                references[kind] = {"path": f"sources/{kind}.csv", "sha256": item["sha256"]}
            vendors, names = engine.load_vendors(paths["vendors"])
            report, accounting, drafts = engine.reconcile(
                vendors, names, engine.load_purchase_orders(paths["purchase_orders"]),
                engine.load_invoices(paths["invoices"]), vendors_source=references["vendors"],
                po_source=references["purchase_orders"], invoice_source=references["invoices"],
            )
    except (engine.PurchasingError, DecimalException) as exc:
        raise DeskError(str(exc)) from exc

    supplied_attachments = payload.get("attachments", [])
    if not isinstance(supplied_attachments, list) or len(supplied_attachments) > 10:
        raise DeskError("attachments must be a list of at most ten files")
    attachments = []
    for index, value in enumerate(supplied_attachments):
        item, _ = file_record(value, f"attachment {index + 1}")
        suffix = Path(item["name"].replace("\\", "/")).suffix
        suffix = suffix.lower() if re.fullmatch(r"\.[A-Za-z0-9]{1,12}", suffix) else ".bin"
        item["path"] = f"attachments/{index + 1:02d}{suffix}"
        attachments.append(item)
    # Bound total decoded storage even for direct Store callers, not only HTTP.
    if sum(item["bytes"] for item in [*sources.values(), *attachments]) > 8 * 1024 * 1024:
        raise DeskError("combined source and attachment size exceeds 8 MiB", 413)
    edits = payload.get("draft_edits", {})
    if not isinstance(edits, dict) or len(edits) > 10000:
        raise DeskError("draft_edits must be an object of at most 10000 entries")
    accepted_edits = {}
    current_keys = set()
    for draft in drafts:
        fingerprint = draft_key(draft)
        draft["basis_sha256"] = fingerprint
        current_keys.add(fingerprint)
        edit = edits.get(fingerprint)
        if edit is not None:
            if not isinstance(edit, dict):
                raise DeskError("each draft edit must contain subject and body")
            draft["subject"] = text(edit.get("subject"), "draft subject", 400)
            draft["body"] = text(edit.get("body"), "draft body", 20000)
            draft["edited"] = True
            accepted_edits[fingerprint] = {"subject": draft["subject"], "body": draft["body"]}
        else:
            draft["edited"] = False
    stale_edits = sorted(str(key) for key in edits if key not in current_keys)
    return {"schema": SCHEMA, "title": title, "sources": sources, "attachments": attachments,
            "report": report, "accounting": accounting, "drafts": drafts,
            "draft_edits": accepted_edits, "discarded_stale_edits": stale_edits}


class Store:
    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS packets(id TEXT PRIMARY KEY, title TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS versions(packet_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    saved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), payload TEXT NOT NULL,
                    PRIMARY KEY(packet_id, revision));
                CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY, digest TEXT NOT NULL,
                    packet_id TEXT NOT NULL, revision INTEGER NOT NULL);
            """)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _get(connection: sqlite3.Connection, ident: str, revision: int | None = None) -> dict:
        head = connection.execute("SELECT revision FROM packets WHERE id=?", (ident,)).fetchone()
        if head is None:
            raise DeskError("packet not found", 404)
        selected = head["revision"] if revision is None else revision
        row = connection.execute("SELECT * FROM versions WHERE packet_id=? AND revision=?", (ident, selected)).fetchone()
        if row is None:
            raise DeskError("revision not found", 404)
        return {**json.loads(row["payload"]), "id": ident, "revision": selected,
                "current_revision": head["revision"], "saved_at": row["saved_at"]}

    def get(self, ident: str, revision: int | None = None) -> dict:
        with closing(self.connect()) as connection:
            return self._get(connection, ident, revision)

    def list(self) -> list[dict]:
        with closing(self.connect()) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT p.id,p.title,p.revision,v.saved_at FROM packets p JOIN versions v ON v.packet_id=p.id AND v.revision=p.revision ORDER BY v.saved_at DESC,p.id")]

    def save(self, payload: object, ident: str | None = None) -> dict:
        if not isinstance(payload, dict):
            raise DeskError("request must be an object")
        expected = payload.get("expected_revision")
        if ident is not None and (type(expected) is not int or expected < 1):
            raise DeskError("expected_revision must be a positive integer")
        request_id = payload.get("request_id")
        if request_id is not None:
            request_id = text(request_id, "request_id", 120)
            if not request_id:
                raise DeskError("request_id must be nonempty when supplied")
        try:
            digest = sha(canonical({"target": ident, "payload": payload}).encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise DeskError("request must contain JSON values") from exc
        # Read the retry record before recalculation. Accepted input remains replayable
        # even if the imported matching engine changes in a future application release.
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if request_id:
                previous = connection.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
                if previous:
                    if previous["digest"] != digest:
                        raise DeskError("request_id already refers to different input", 409)
                    return self._get(connection, previous["packet_id"], previous["revision"])
            if ident is None:
                ident, revision = uuid.uuid4().hex, 1
            else:
                head = connection.execute("SELECT revision FROM packets WHERE id=?", (ident,)).fetchone()
                if head is None:
                    raise DeskError("packet not found", 404)
                if head["revision"] != expected:
                    raise DeskError(f"saved revision is {head['revision']}; reopen it before applying these edits", 409)
                revision = expected + 1
            prepared = prepare(payload)
            connection.execute("INSERT INTO versions(packet_id,revision,payload) VALUES(?,?,?)", (ident, revision, canonical(prepared)))
            connection.execute("INSERT INTO packets VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,revision=excluded.revision", (ident, prepared["title"], revision))
            if request_id:
                connection.execute("INSERT INTO requests VALUES(?,?,?,?)", (request_id, digest, ident, revision))
            return self._get(connection, ident, revision)


def accounting_csv(packet: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=engine.ACCOUNTING_FIELDS)
    writer.writeheader()
    writer.writerows(packet["accounting"])
    return output.getvalue().encode("utf-8")


def bundle(packet: dict) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifest = {"schema": SCHEMA, "id": packet["id"], "revision": packet["revision"], "files": []}
        for kind, item in packet["sources"].items():
            path = f"sources/{kind}.csv"
            archive.writestr(path, base64.b64decode(item["data"]))
            manifest["files"].append({"path": path, **{key: item[key] for key in ("name", "sha256", "bytes")}})
        for item in packet["attachments"]:
            archive.writestr(item["path"], base64.b64decode(item["data"]))
            manifest["files"].append({key: item[key] for key in ("path", "name", "sha256", "bytes")})
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr("reconciliation.json", json.dumps(packet["report"], indent=2) + "\n")
        archive.writestr("exception_drafts.json", json.dumps({"schema": SCHEMA, "drafts": packet["drafts"]}, indent=2) + "\n")
        archive.writestr("accounting_import.csv", accounting_csv(packet))
        archive.writestr("README.txt", "Unsent, unposted review packet. Sources retain exact bytes. Manifest names map attachments to original filenames. CSV is a raw accounting interchange, not spreadsheet-sanitized. Review imported text before opening it in spreadsheet software.\n")
    return output.getvalue()


def make_server(store: Store, host: str = "127.0.0.1", port: int = 8766) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Do not log customer filenames or packet contents.

        def respond(self, status: int, raw: bytes, content_type: str = "application/json; charset=utf-8", filename: str | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(raw)

        def json(self, status: int, value: object):
            self.respond(status, canonical(value).encode("utf-8"))

        def route(self):
            parsed = urlsplit(self.path)
            parts = parsed.path.strip("/").split("/")
            query = parse_qs(parsed.query, keep_blank_values=True)
            revision = None
            if "revision" in query:
                try:
                    revision = int(query["revision"][0])
                    if revision < 1:
                        raise ValueError
                except ValueError as exc:
                    raise DeskError("revision must be a positive integer") from exc
            return parsed.path, parts, revision

        def do_GET(self):
            try:
                path, parts, revision = self.route()
                if path == "/":
                    self.respond(200, (ROOT / "desk.html").read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/packets":
                    self.json(200, {"packets": store.list()})
                elif path == "/api/example":
                    sources = {}
                    for kind in KINDS:
                        raw = (ROOT / "examples" / f"{kind}.csv").read_bytes()
                        sources[kind] = {"name": f"{kind}.csv", "data": base64.b64encode(raw).decode("ascii")}
                    self.json(200, {"title": "Fictional sample purchasing packet", "sources": sources, "attachments": [], "draft_edits": {}})
                elif len(parts) in (3, 4, 5) and parts[:2] == ["api", "packets"]:
                    packet = store.get(parts[2], revision)
                    if len(parts) == 3:
                        self.json(200, packet)
                    elif len(parts) == 4 and parts[3] == "bundle":
                        self.respond(200, bundle(packet), "application/zip", f"packet-{packet['id']}-r{packet['revision']}.zip")
                    elif len(parts) == 4 and parts[3] == "accounting.csv":
                        self.respond(200, accounting_csv(packet), "text/csv; charset=utf-8", "accounting_import.csv")
                    elif len(parts) == 5 and parts[3] == "sources" and parts[4] in KINDS:
                        item = packet["sources"][parts[4]]
                        self.respond(200, base64.b64decode(item["data"]), "application/octet-stream", parts[4] + ".csv")
                    elif len(parts) == 5 and parts[3] == "attachments" and parts[4].isdigit() and int(parts[4]) < len(packet["attachments"]):
                        item = packet["attachments"][int(parts[4])]
                        self.respond(200, base64.b64decode(item["data"]), "application/octet-stream", f"attachment-{parts[4]}{Path(item['path']).suffix}")
                    else:
                        raise DeskError("not found", 404)
                else:
                    raise DeskError("not found", 404)
            except DeskError as exc:
                self.json(exc.status, {"error": str(exc)})
            except (OSError, sqlite3.Error):
                self.json(503, {"error": "workspace storage or a file is unavailable"})

        def do_POST(self):
            try:
                path, parts, _ = self.route()
                if path != "/api/packets" and not (len(parts) == 3 and parts[:2] == ["api", "packets"]):
                    raise DeskError("not found", 404)
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError as exc:
                    raise DeskError("Content-Length must be an integer", 400) from exc
                if not 0 < length <= MAX_BODY:
                    raise DeskError("request body must be between 1 byte and 12 MiB", 413)
                try:
                    payload = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeError) as exc:
                    raise DeskError("body must be UTF-8 JSON", 400) from exc
                packet = store.save(payload, parts[2] if len(parts) == 3 else None)
                self.json(200, packet)
            except DeskError as exc:
                self.json(exc.status, {"error": str(exc)})
            except (sqlite3.Error, OSError):
                self.json(503, {"error": "workspace storage is unavailable; retry the same request_id"})

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path.home() / ".local" / "share" / "commons" / "purchasing-desk.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    server = make_server(Store(args.database), args.host, args.port)
    print(f"Purchasing desk: http://{args.host}:{server.server_port}/ — local review, nothing sent or posted", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
