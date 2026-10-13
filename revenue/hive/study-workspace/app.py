"""Run the shared single-workspace browser application without a cloud dependency."""
from __future__ import annotations

import argparse
import base64
import binascii
import html
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from study import Conflict, MAX_UPLOAD, Workspace

ROOT = Path(__file__).resolve().parent
STATIC = {"/": "index.html", "/workspace.js": "workspace.js", "/style.css": "style.css"}
MAX_BODY = ((MAX_UPLOAD + 2) // 3) * 4 + 4096


def create_server(host: str, port: int, workspace: Workspace) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "HiveStudy/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, fmt, *args):
            # Keep filenames, answers and query strings out of access logs.
            return

        def send(self, status: int, content: bytes, content_type: str = "application/json; charset=utf-8", extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'")
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(content)

        def json(self, status: int, value):
            self.send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode())

        def body(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Invalid JSON body length.") from exc
            if length < 1 or length > MAX_BODY:
                raise ValueError("Send a JSON body containing a file of at most 8 MiB.")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("The request body ended early.")
            try:
                value = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("The request must contain readable JSON.") from exc
            if not isinstance(value, dict):
                raise ValueError("The JSON body must be an object.")
            return value

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def do_DELETE(self):
            self.dispatch("DELETE")

        def dispatch(self, method: str):
            try:
                self.route(method)
            except Conflict as exc:
                self.json(409, {"message": str(exc)})
            except (ValueError, binascii.Error) as exc:
                self.json(400, {"message": str(exc)})
            except KeyError as exc:
                self.json(404, {"message": str(exc).strip("'")})
            except (sqlite3.Error, OSError):
                self.json(503, {"message": "The workspace could not complete this operation. Your existing data is retained; retry after checking the server storage."})

        def route(self, method: str):
            request = urlsplit(self.path)
            path, query = request.path, parse_qs(request.query)
            pieces = path.strip("/").split("/")
            if method == "GET" and path in STATIC:
                file = ROOT / STATIC[path]
                content_type = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[file.suffix]
                return self.send(200, file.read_bytes(), content_type + "; charset=utf-8")
            if method == "GET" and path == "/api/documents":
                return self.json(200, {"documents": workspace.documents()})
            if method == "GET" and path == "/api/capabilities":
                import shutil
                return self.json(200, {"pdf": bool(shutil.which("pdftotext")), "max_upload": MAX_UPLOAD, "generation": "source-bound definition and cloze rules"})
            if method == "POST" and path == "/api/import":
                body = self.body()
                encoded = body.get("data")
                if not isinstance(encoded, str):
                    raise ValueError("The file data must be base64 text.")
                raw = base64.b64decode(encoded, validate=True)
                return self.json(200, workspace.import_document(raw, body.get("filename"), body.get("title", "")))
            if len(pieces) >= 3 and pieces[:2] == ["api", "documents"]:
                document_id = pieces[2]
                if method == "DELETE" and len(pieces) == 3:
                    workspace.delete_document(document_id)
                    return self.json(200, {"deleted": document_id})
                if method == "GET" and len(pieces) == 3:
                    return self.json(200, workspace.document(document_id))
                if method == "GET" and len(pieces) == 4 and pieces[3] == "cards":
                    return self.json(200, {"cards": workspace.cards(document_id, due=query.get("due") == ["1"])})
                if method == "GET" and len(pieces) == 4 and pieces[3] == "export":
                    data = json.dumps(workspace.export(document_id), ensure_ascii=False, indent=2).encode()
                    return self.send(200, data, "application/json; charset=utf-8", {"Content-Disposition": 'attachment; filename="study-workspace-export.json"'})
            if method == "POST" and len(pieces) == 3 and pieces[:2] == ["api", "cards"]:
                return self.json(200, workspace.edit_card(pieces[2], self.body()))
            if method == "POST" and path == "/api/review":
                body = self.body()
                return self.json(200, workspace.review(body.get("card_id"), body.get("answer"), body.get("request_id"), body.get("revision")))
            if method == "GET" and len(pieces) == 2 and pieces[0] in {"source", "original"}:
                document = workspace.document(pieces[1], original=pieces[0] == "original")
                if pieces[0] == "original":
                    kind = "application/pdf" if document["kind"] == "pdf" else "text/plain; charset=utf-8"
                    suffix = ".pdf" if document["kind"] == "pdf" else ".txt"
                    return self.send(200, document["original"], kind, {"Content-Disposition": f'attachment; filename="study-source{suffix}"'})
                title = html.escape(document["title"])
                sections = []
                for number, page in enumerate(document["pages"], 1):
                    lines = "".join(f'<li id="p{number}-l{i}"><span>{html.escape(line) or " "}</span></li>' for i, line in enumerate(page.splitlines(), 1))
                    sections.append(f'<section><h2>Page {number}</h2><ol class="source-lines">{lines}</ol></section>')
                page = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} — source</title><link rel="stylesheet" href="/style.css"><body><main class="source-main"><a href="/">← Workspace</a><h1>{title}</h1><p>Original SHA-256: <code>{document["id"]}</code></p><a href="/original/{document["id"]}">Save original file</a>{"".join(sections)}</main></body></html>'
                return self.send(200, page.encode(), "text/html; charset=utf-8")
            self.json(404, {"message": "This route was not found."})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Hive Study: source-bound practice and saved review.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--data", type=Path, default=Path.home() / ".hive-study" / "workspace.sqlite3")
    args = parser.parse_args()
    server = create_server(args.host, args.port, Workspace(args.data))
    print(f"Hive Study listening at http://{args.host}:{server.server_port}", flush=True)
    print("Shared workspace: everyone who can reach this server can read and edit its data.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
