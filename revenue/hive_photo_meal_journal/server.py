from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
INDEX = (HERE / "index.html").read_bytes()

from journal import ConflictError, JournalError, MealJournal, NotFoundError

MAX_BODY = 7 * 1024 * 1024

def _strict_json(data: bytes):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise JournalError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(JournalError(f"non-finite JSON number: {token}")),
        )
    except JournalError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise JournalError(f"invalid JSON: {exc}") from exc

def _photo_from_data_url(value):
    if value in (None, ""):
        return None, None
    if not isinstance(value, str):
        raise JournalError("photo_data_url must be text")
    match = re.fullmatch(r"data:(image/(?:jpeg|png|webp|gif|svg\+xml));base64,([A-Za-z0-9+/=]+)", value)
    if not match:
        raise JournalError("photo_data_url must be a supported base64 image data URL")
    try:
        return base64.b64decode(match.group(2), validate=True), match.group(1)
    except ValueError as exc:
        raise JournalError("invalid base64 photo bytes") from exc

def make_handler(journal: MealJournal):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MealFrame/1"

        def log_message(self, fmt, *args):
            return

        def _send(self, status, body=b"", content_type="application/json; charset=utf-8", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if extra:
                for key, value in extra.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, value):
            self._send(status, json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))

        def _assert_browser_write_boundary(self):
            if self.headers.get_content_type() != "application/json":
                raise JournalError("Content-Type must be application/json")

            # Browser-simple cross-origin requests cannot set application/json without
            # preflight. Keep preflight closed and also reject explicit cross-origin
            # metadata so state-changing routes never rely on response CORS alone.
            fetch_site = (self.headers.get("Sec-Fetch-Site") or "").lower()
            if fetch_site in {"cross-site", "same-site"}:
                raise JournalError("cross-origin browser mutation rejected")

            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            if origin is not None:
                if not host or origin != f"http://{host}":
                    raise JournalError("request Origin does not match MealFrame origin")

            # When the listener itself is loopback-only, refuse Host-header rebinding
            # through attacker-controlled DNS names. Normal localhost/127.0.0.1 access
            # remains valid; explicitly shared non-loopback listeners keep their host.
            bound_host = str(self.server.server_address[0]).lower()
            if bound_host in {"127.0.0.1", "::1"}:
                if not host:
                    raise JournalError("Host header required")
                host_name = host.split(":", 1)[0].strip("[]").lower()
                if host_name not in {"127.0.0.1", "localhost", "localhost."}:
                    raise JournalError("loopback MealFrame rejects non-loopback Host")

        def _read_json(self):
            self._assert_browser_write_boundary()
            raw_len = self.headers.get("Content-Length")
            if raw_len is None:
                raise JournalError("Content-Length required")
            try:
                length = int(raw_len)
            except ValueError as exc:
                raise JournalError("invalid Content-Length") from exc
            if length < 0 or length > MAX_BODY:
                raise JournalError("request body too large")
            payload = _strict_json(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise JournalError("request body must be a JSON object")
            return payload

        def do_OPTIONS(self):
            # Deliberately no Access-Control-Allow-* headers. Cross-origin JSON
            # mutation attempts must fail their browser preflight.
            self._json(403, {"error": "cross-origin browser access denied"})

        def do_GET(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._send(200, INDEX, "text/html; charset=utf-8")
                    return
                if parsed.path == "/api/state":
                    self._json(200, journal.state())
                    return
                if parsed.path == "/api/suggestions":
                    query = parse_qs(parsed.query)
                    title = query.get("title", [""])[0]
                    self._json(200, {"suggestions": journal.suggestions(title)})
                    return
                if parsed.path == "/api/export":
                    query = parse_qs(parsed.query)
                    week = query.get("week", [""])[0]
                    fmt = query.get("format", ["json"])[0]
                    if fmt == "json":
                        body = journal.export_week_json(week)
                        self._send(200, body, "application/json; charset=utf-8", {"Content-Disposition": f'attachment; filename="mealframe-{week}.json"'})
                    elif fmt == "html":
                        body = journal.export_week_html(week)
                        self._send(200, body, "text/html; charset=utf-8", {"Content-Disposition": f'attachment; filename="mealframe-{week}.html"'})
                    else:
                        raise JournalError("format must be json or html")
                    return
                match = re.fullmatch(r"/photo/(\d+)", parsed.path)
                if match:
                    photo, mime, sha = journal.photo(int(match.group(1)))
                    extra = {"ETag": f'"sha256-{sha}"'}
                    if mime == "image/svg+xml":
                        # SVG remains a useful exact-byte local photo/demo format but
                        # must never become active same-origin script authority when
                        # opened as its own document.
                        extra["Content-Security-Policy"] = "sandbox; default-src 'none'"
                    self._send(200, photo, mime, extra)
                    return
                self._json(404, {"error": "not_found"})
            except NotFoundError as exc:
                self._json(404, {"error": str(exc)})
            except JournalError as exc:
                self._json(422, {"error": str(exc)})

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                data = self._read_json()
                if parsed.path == "/api/meal/create":
                    photo, mime = _photo_from_data_url(data.pop("photo_data_url", None))
                    result = journal.create_meal(photo=photo, photo_mime=mime, **data)
                elif parsed.path == "/api/meal/update":
                    result = journal.update_meal(**data)
                elif parsed.path == "/api/meal/delete":
                    result = journal.delete_meal(**data)
                elif parsed.path == "/api/recipe/save":
                    result = journal.save_recipe(**data)
                elif parsed.path == "/api/delete-all":
                    result = journal.delete_all(**data)
                else:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, result)
            except ConflictError as exc:
                self._json(409, {"error": str(exc)})
            except NotFoundError as exc:
                self._json(404, {"error": str(exc)})
            except JournalError as exc:
                self._json(422, {"error": str(exc)})
            except TypeError as exc:
                self._json(422, {"error": f"request fields invalid: {exc}"})

    return Handler

def load_demo(journal: MealJournal) -> None:
    svg = (HERE / "demo_meal.svg").read_bytes()
    journal.save_recipe(
        operation_id="demo-recipe-001",
        name="Tomato basil toast",
        ingredients=["sourdough toast", "tomato", "basil", "olive oil"],
        notes="Self-authored demo recipe; adjust ingredients to match the meal actually eaten.",
    )
    journal.create_meal(
        operation_id="demo-meal-001",
        meal_date="2026-09-14",
        title="Tomato basil toast",
        portion_note="Two slices; plain-language note only",
        notes="Self-authored fictional demo entry. Ingredients remain editable.",
        ingredients=["sourdough toast", "tomato", "basil", "olive oil"],
        photo=svg,
        photo_mime="image/svg+xml",
    )

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the local-only MealFrame photo meal journal.")
    parser.add_argument("--db", default="mealframe.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)
    journal = MealJournal(args.db)
    if args.demo:
        load_demo(journal)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(journal))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
