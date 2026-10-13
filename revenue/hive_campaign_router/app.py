# SPDX-License-Identifier: Apache-2.0
"""RouteFoundry: stable campaign links, offer routing, and attribution."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
    from qrcode.image.svg import SvgPathImage
except ImportError as exc:  # pragma: no cover - exercised by installation, not product logic
    raise SystemExit("RouteFoundry requires qrcode 8.x. Run: python -m pip install -r requirements.txt") from exc

from campaign_router import (
    Store,
    ValidationError,
    append_utm,
    short_url,
    validate_public_base_url,
)

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
MAX_BODY = 128 * 1024


@dataclass(frozen=True)
class Settings:
    store: Store
    public_base_url: str
    brand_name: str
    public_only: bool = False
    access_log: bool = True


def qr_svg(value: str) -> bytes:
    """Return a deterministic, scanner-compatible SVG QR payload."""
    code = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=8, border=4)
    code.add_data(value, optimize=0)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    return output.getvalue()


def offer_html(settings: Settings, link: dict[str, Any], click_event_id: str) -> bytes:
    brand = escape(str(link["brand"]))
    headline = escape(str(link["headline"]))
    body = escape(str(link["body"])).replace("\n", "<br>")
    cta = escape(str(link["cta_label"]))
    campaign = escape(str(link.get("utm_campaign") or "direct"))
    source = escape(str(link.get("utm_source") or "direct"))
    slug = escape(str(link["slug"]), quote=True)
    event = escape(click_event_id, quote=True)
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{headline} · {brand}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body class="offer-page">
  <main class="offer-shell">
    <p class="eyebrow">{brand}</p>
    <h1>{headline}</h1>
    <p class="offer-copy">{body}</p>
    <a class="primary-button" href="/convert/{slug}?click={event}">{cta}</a>
    <p class="source-note">Campaign: {campaign} · Source: {source}</p>
  </main>
</body>
</html>"""
    return page.encode("utf-8")


class RouterServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], settings: Settings):
        self.settings = settings
        super().__init__(server_address, RouterHandler)


class RouterHandler(BaseHTTPRequestHandler):
    server: RouterServer
    protocol_version = "HTTP/1.1"
    server_version = "RouteFoundry/1.0"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        if self.settings.access_log:
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    @property
    def settings(self) -> Settings:
        return self.server.settings

    def _headers(self, content_type: str, length: int, status: int = 200, *, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )
        if self.close_connection:
            self.send_header("Connection", "close")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()

    def _send(self, body: bytes, content_type: str, status: int = 200, *, extra: dict[str, str] | None = None) -> None:
        self._headers(content_type, len(body), status, extra=extra)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, value: Any, status: int = 200) -> None:
        body = (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
        self._send(body, "application/json; charset=utf-8", status, extra={"Cache-Control": "no-store"})

    def _redirect(self, location: str, status: int = HTTPStatus.FOUND) -> None:
        self._send(b"", "text/plain; charset=utf-8", int(status), extra={"Location": location, "Cache-Control": "no-store"})

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValidationError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValidationError("Content-Length is invalid") from exc
        if not 0 <= length <= MAX_BODY:
            raise ValidationError(f"request body must be at most {MAX_BODY} bytes")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("request body must be a UTF-8 JSON object") from exc
        if not isinstance(value, dict):
            raise ValidationError("request body must be a JSON object")
        return value

    def _safe(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except ValidationError as exc:
            self._json({"error": "validation_error", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
        except KeyError:
            self._json({"error": "not_found", "message": "resource not found"}, HTTPStatus.NOT_FOUND)
        except sqlite3.Error as exc:
            self.log_error("database error: %s", exc)
            self._json({"error": "database_error", "message": "database operation failed"}, HTTPStatus.INTERNAL_SERVER_ERROR)
        except BrokenPipeError:
            pass
        except Exception as exc:  # keep an ordinary malformed request from killing the server thread
            self.log_error("unhandled error: %s", exc)
            self._json({"error": "internal_error", "message": "request could not be completed"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_HEAD(self) -> None:
        self._safe(self._do_head)

    def _do_head(self) -> None:
        path = unquote(urlsplit(self.path).path)
        if path.startswith("/r/"):
            slug = path.removeprefix("/r/")
            link = self.settings.store.get_link(slug, active_only=True)
            if link is None:
                raise KeyError(slug)
            if link["route_mode"] == "redirect":
                return self._redirect(append_utm(link["destination"], link))
            body = offer_html(self.settings, link, "head_preview")
            return self._send(body, "text/html; charset=utf-8", extra={"Cache-Control": "no-store"})
        if path.startswith("/convert/"):
            slug = path.removeprefix("/convert/")
            link = self.settings.store.get_link(slug, active_only=True)
            if link is None:
                raise KeyError(slug)
            return self._redirect(append_utm(link["destination"], link))
        self._do_get()

    def do_GET(self) -> None:
        self._safe(self._do_get)

    def _do_get(self) -> None:
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query, keep_blank_values=True)
        if self.settings.public_only and (
            path == "/" or path == "/static/app.js" or path.startswith("/api/")
        ):
            raise KeyError(path)
        if path == "/":
            return self._static("index.html", "text/html; charset=utf-8")
        if path == "/health":
            return self._json({"ok": True, "service": "routefoundry"})
        if path == "/api/state":
            return self._json(self.settings.store.list_state(self.settings.public_base_url))
        if path in {"/api/report", "/api/report.csv"}:
            for key in ("start", "end", "view"):
                if len(query.get(key, [])) > 1:
                    raise ValidationError(f"{key} must be supplied at most once")
            start = query.get("start", [None])[0]
            end = query.get("end", [None])[0]
            if path == "/api/report":
                return self._json(self.settings.store.report(start, end))
            view = query.get("view", ["campaigns"])[0]
            body = self.settings.store.report_csv(view, start, end).encode("utf-8")
            return self._send(
                body,
                "text/csv; charset=utf-8",
                extra={
                    "Content-Disposition": f"attachment; filename=routefoundry-{view}.csv",
                    "Cache-Control": "no-store",
                },
            )
        if path == "/api/export":
            body = self.settings.store.export_json().encode("utf-8")
            return self._send(
                body,
                "application/json; charset=utf-8",
                extra={"Content-Disposition": "attachment; filename=routefoundry-export.json", "Cache-Control": "no-store"},
            )
        if path.startswith("/static/"):
            name = path.removeprefix("/static/")
            types = {"app.js": "text/javascript; charset=utf-8", "styles.css": "text/css; charset=utf-8"}
            if name not in types:
                raise KeyError(name)
            return self._static(name, types[name])
        if path.startswith("/q/") and path.endswith(".svg"):
            slug = path.removeprefix("/q/")[:-4]
            link = self.settings.store.get_link(slug)
            if link is None:
                raise KeyError(slug)
            body = qr_svg(short_url(self.settings.public_base_url, slug))
            return self._send(body, "image/svg+xml; charset=utf-8", extra={"Cache-Control": "public, max-age=300"})
        if path.startswith("/r/"):
            slug = path.removeprefix("/r/")
            link = self.settings.store.get_link(slug, active_only=True)
            if link is None:
                raise KeyError(slug)
            click = self.settings.store.record_event(slug, "click", referrer=self.headers.get("Referer"))
            if link["route_mode"] == "offer":
                if not link.get("headline"):
                    raise ValidationError("offer route is missing its offer")
                body = offer_html(self.settings, link, click.event_id)
                return self._send(body, "text/html; charset=utf-8", extra={"Cache-Control": "no-store"})
            return self._redirect(append_utm(link["destination"], link))
        if path.startswith("/convert/"):
            slug = path.removeprefix("/convert/")
            link = self.settings.store.get_link(slug, active_only=True)
            if link is None:
                raise KeyError(slug)
            parent = query.get("click", [None])[0]
            requested = query.get("event_id", [None])[0]
            self.settings.store.record_event(
                slug,
                "conversion",
                requested_event_id=requested,
                parent_event_id=parent,
                referrer=self.headers.get("Referer"),
            )
            return self._redirect(append_utm(link["destination"], link))
        raise KeyError(path)

    def _static(self, name: str, content_type: str) -> None:
        path = STATIC / name
        if not path.is_file() or path.parent != STATIC:
            raise KeyError(name)
        self._send(path.read_bytes(), content_type, extra={"Cache-Control": "no-cache"})

    def do_POST(self) -> None:
        self._safe(self._do_post)

    def _do_post(self) -> None:
        path = urlsplit(self.path).path
        if self.settings.public_only:
            self.close_connection = True
            raise KeyError(path)
        payload = self._read_json()
        routes: dict[str, Callable[[dict[str, Any]], Any]] = {
            "/api/products": self.settings.store.create_product,
            "/api/offers": self.settings.store.create_offer,
            "/api/presets": self.settings.store.create_preset,
            "/api/links": self.settings.store.create_link,
        }
        if path in routes:
            return self._json(routes[path](payload), HTTPStatus.CREATED)
        if path == "/api/events":
            result = self.settings.store.record_event(
                payload.get("slug"),
                payload.get("event_type"),
                requested_event_id=payload.get("event_id"),
                parent_event_id=payload.get("parent_event_id"),
                referrer=payload.get("referrer"),
            )
            return self._json({"event_id": result.event_id, "created": result.created}, HTTPStatus.CREATED if result.created else HTTPStatus.OK)
        raise KeyError(path)

    def do_PATCH(self) -> None:
        self._safe(self._do_patch)

    def _do_patch(self) -> None:
        path = urlsplit(self.path).path
        if self.settings.public_only:
            self.close_connection = True
            raise KeyError(path)
        if not path.startswith("/api/links/"):
            raise KeyError(path)
        slug = unquote(path.removeprefix("/api/links/"))
        self._json(self.settings.store.update_link(slug, self._read_json()))


def make_server(
    *,
    db_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    public_base_url: str | None = None,
    brand_name: str = "RouteFoundry",
    public_only: bool = False,
    access_log: bool = True,
) -> RouterServer:
    brand = brand_name.strip()
    if not brand or len(brand) > 80:
        raise ValidationError("brand_name must be 1-80 characters")
    placeholder = Settings(Store(db_path), "http://127.0.0.1", brand, public_only, access_log)
    server = RouterServer((host, port), placeholder)
    actual_host, actual_port = server.server_address[:2]
    if public_base_url is None:
        visible_host = "127.0.0.1" if actual_host in {"0.0.0.0", "::"} else actual_host
        public_base_url = f"http://{visible_host}:{actual_port}"
    server.settings = Settings(placeholder.store, validate_public_base_url(public_base_url), brand, public_only, access_log)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    try:
        default_port = int(os.environ.get("PORT", "8080"))
    except ValueError:
        default_port = 8080
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("ROUTEFOUNDRY_DB", HERE / "routefoundry.db")))
    parser.add_argument("--host", default=os.environ.get("ROUTEFOUNDRY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--public-base-url", default=os.environ.get("PUBLIC_BASE_URL"))
    parser.add_argument("--brand-name", default=os.environ.get("ROUTEFOUNDRY_BRAND", "RouteFoundry"))
    parser.add_argument("--public-only", action="store_true",
                        default=os.environ.get("ROUTEFOUNDRY_PUBLIC_ONLY", "").lower() in {"1", "true", "yes"})
    parser.add_argument("--quiet-access-log", action="store_true",
                        help="Suppress per-request access log lines; errors still use stderr.")
    args = parser.parse_args(argv)
    try:
        server = make_server(
            db_path=args.db,
            host=args.host,
            port=args.port,
            public_base_url=args.public_base_url,
            brand_name=args.brand_name,
            public_only=args.public_only,
            access_log=not args.quiet_access_log,
        )
    except (OSError, ValidationError, sqlite3.Error) as exc:
        print(f"startup error: {exc}", file=sys.stderr)
        return 2
    print(f"RouteFoundry listening on {server.settings.public_base_url} (db={args.db})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
