#!/usr/bin/env python3
"""Loopback browser operator for the existing Commercial Waste Route Desk."""
from __future__ import annotations

import argparse
import csv
import hmac
import io
import json
import secrets
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from desk_common import DeskError, ValidationError, StateConflict, iso
from desk_migration import WasteRouteDesk
from csv_manifest import preview as preview_csv

ASSETS = Path(__file__).resolve().parent
MAX_REQUEST = 2 * 1024 * 1024


def strict_json(raw: str):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValidationError(f"duplicate JSON member: {key}")
            value[key] = item
        return value

    def bad_constant(value):
        raise ValidationError(f"non-finite JSON number: {value}")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, RecursionError) as exc:
        raise ValidationError("invalid or excessively nested JSON") from exc


def browser_value(value):
    """Keep minor-unit integers exact across the browser's Number boundary."""
    if isinstance(value, dict):
        return {
            key: str(item) if key.endswith("_minor") and type(item) is int
            else browser_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [browser_value(item) for item in value]
    return value


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params)]


def workspace(desk):
    """Read-only, internally consistent projection; mutations stay in the engine."""
    conn = desk.conn
    conn.execute("BEGIN")
    try:
        setting = conn.execute(
            "SELECT value FROM workspace_settings WHERE key='business_timezone'"
        ).fetchone()
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("customers", "sites", "containers", "plans", "routes", "invoice_drafts", "events")
        }
        exception_count = conn.execute(
            "SELECT COUNT(*) FROM stops WHERE status='EXCEPTION_OPEN'"
        ).fetchone()[0]
        return {
            "initialized": setting is not None,
            "business_timezone": setting["value"] if setting else None,
            "business_date": desk.business_date().isoformat() if setting else None,
            "counts": counts,
            "customers": rows(conn, "SELECT id,name,currency FROM customers ORDER BY id"),
            "plans": rows(conn, """
                SELECT p.id,p.weekday,p.service_code,p.price_minor,p.active,
                       c.label container_label,c.container_type,s.name site_name,
                       s.customer_id,cu.name customer_name,cu.currency
                FROM plans p JOIN containers c ON c.id=p.container_id
                JOIN sites s ON s.id=c.site_id JOIN customers cu ON cu.id=s.customer_id
                ORDER BY cu.id,s.id,c.id,p.id
            """),
            "routes": rows(conn, """
                SELECT r.service_date,COUNT(st.id) stop_count,
                       SUM(CASE WHEN st.status='PENDING' THEN 1 ELSE 0 END) pending,
                       SUM(CASE WHEN st.status='EXCEPTION_OPEN' THEN 1 ELSE 0 END) exceptions
                FROM routes r LEFT JOIN stops st ON st.route_id=r.id
                GROUP BY r.id ORDER BY r.service_date DESC LIMIT 120
            """),
            "exception_count": exception_count,
            "exceptions": rows(conn, """
                SELECT st.id stop_id,st.status,st.exception_code,st.customer_id,
                       cu.name customer_name,s.name site_name,c.label container_label,
                       p.service_code,p.price_minor,st.charge_minor,r.service_date
                FROM stops st JOIN routes r ON r.id=st.route_id
                JOIN customers cu ON cu.id=st.customer_id JOIN sites s ON s.id=st.site_id
                JOIN containers c ON c.id=st.container_id JOIN plans p ON p.id=st.plan_id
                WHERE st.status='EXCEPTION_OPEN'
                ORDER BY r.service_date,st.sequence,st.id LIMIT 200
            """),
            "invoices": rows(conn, """
                SELECT d.id,d.customer_id,c.name customer_name,d.period_start,
                       d.period_end,d.total_minor,d.currency
                FROM invoice_drafts d JOIN customers c ON c.id=d.customer_id
                ORDER BY d.rowid DESC LIMIT 100
            """),
            "events": rows(conn, """
                SELECT id,op_key,event_type,entity_kind,entity_id
                FROM events ORDER BY id DESC LIMIT 100
            """),
        }
    finally:
        conn.execute("ROLLBACK")


def execute(desk, body):
    if not isinstance(body, dict) or set(body) != {"action", "args", "op_key"}:
        raise ValidationError("request requires exactly action, args, and op_key")
    action, args, op_key = body["action"], body["args"], body["op_key"]
    shapes = {
        "import": ({"manifest_text"}, set()),
        "route": ({"date"}, set()),
        "record": ({"stop_id", "outcome"}, {"exception_code"}),
        "resolve": ({"stop_id", "resolution"}, {"makeup_service_date"}),
        "invoice": ({"customer_id", "period_start", "period_end"}, set()),
    }
    if not isinstance(action, str) or action not in shapes or not isinstance(args, dict):
        raise ValidationError("unknown action or invalid args")
    required, optional = shapes[action]
    if not required.issubset(args) or set(args) - required - optional:
        raise ValidationError(f"invalid fields for {action}")
    for name, value in args.items():
        if not isinstance(value, str) and not (name in optional and value is None):
            raise ValidationError(f"{name} must be text")
    if not isinstance(op_key, str) or not op_key.strip() or len(op_key) > 128:
        raise ValidationError("op_key must be non-empty text of at most 128 characters")
    if action == "import":
        # Parse original source text here, not a Number-rounded browser object.
        return desk.import_manifest(strict_json(args["manifest_text"]), op_key)
    if action == "route":
        return desk.generate_route(args["date"], op_key)
    if action == "record":
        return desk.record_stop(args["stop_id"], args["outcome"], op_key, args.get("exception_code"))
    if action == "resolve":
        return desk.resolve_exception(args["stop_id"], args["resolution"], op_key, args.get("makeup_service_date"))
    return desk.draft_invoice(args["customer_id"], args["period_start"], args["period_end"], op_key)


def spreadsheet_csv(raw):
    """Neutralize formula-like text only in the downloaded CSV, not stored data."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for record in csv.reader(io.StringIO(raw, newline="")):
        writer.writerow([
            "'" + cell if cell.lstrip().startswith(("=", "+", "-", "@")) else cell
            for cell in record
        ])
    return output.getvalue()


class ConsoleServer(HTTPServer):
    def __init__(self, port, desk):
        super().__init__(("127.0.0.1", port), Handler)
        self.desk = desk
        self.token = secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    server_version = "WasteDesk/1"

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, *_):
        # Do not put customer identifiers or operation keys in access logs.
        pass

    def local_request(self, api=False):
        if self.headers.get_all("Host", []) != [self.server.origin.removeprefix("http://")]:
            raise PermissionError("Open the printed 127.0.0.1 address directly")
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.origin:
            raise PermissionError("Cross-origin requests are not accepted")
        if self.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin"):
            raise PermissionError("Open the console directly, not inside another site")
        if api and not hmac.compare_digest(self.headers.get("X-Console-Key", ""), self.server.token):
            raise PermissionError("Console session changed; reload this page")

    def send_content(self, content, content_type="application/json; charset=utf-8", status=200, filename=None):
        raw = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(raw)

    def send_json(self, value, status=200):
        self.send_content(json.dumps(browser_value(value), ensure_ascii=False, allow_nan=False), status=status)

    def query(self, allowed):
        data = parse_qs(urlsplit(self.path).query, keep_blank_values=True, max_num_fields=8)
        if set(data) - set(allowed) or any(len(v) != 1 for v in data.values()):
            raise ValidationError("unexpected or repeated query parameter")
        return {key: value[0] for key, value in data.items()}

    def invoice(self, invoice_id):
        row = self.server.desk.conn.execute(
            "SELECT payload_json FROM invoice_drafts WHERE id=?", (invoice_id,)
        ).fetchone()
        if row is None:
            raise StateConflict("unknown invoice draft")
        return row["payload_json"]

    def json_body(self):
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit() or self.headers.get("Transfer-Encoding"):
            raise ValidationError("one explicit Content-Length is required")
        length = int(lengths[0])
        if not 0 < length <= MAX_REQUEST:
            raise ValidationError("request must be between 1 byte and 2 MiB")
        if self.headers.get_content_type() != "application/json":
            raise ValidationError("Content-Type must be application/json")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValidationError("incomplete request body")
        try:
            return strict_json(raw.decode("utf-8", errors="strict"))
        except UnicodeError as exc:
            raise ValidationError("request must be valid UTF-8") from exc

    def get(self):
        path = urlsplit(self.path).path
        self.local_request(api=path.startswith("/api/"))
        desk = self.server.desk
        if path == "/":
            page = (ASSETS / "web_console.html").read_text(encoding="utf-8")
            self.send_content(page.replace("__CONSOLE_TOKEN__", self.server.token), "text/html; charset=utf-8")
        elif path == "/web_console.js":
            self.send_content((ASSETS / "web_console.js").read_bytes(), "text/javascript; charset=utf-8")
        elif path == "/api/sample":
            self.send_content((ASSETS / "sample_manifest.json").read_bytes())
        elif path == "/api/state":
            self.query(())
            self.send_json(workspace(desk))
        elif path == "/api/route":
            date = self.query(("date",)).get("date")
            result = desk.route_snapshot(date)
            claims = dict(desk.conn.execute("""
                SELECT il.stop_id,il.invoice_id FROM invoice_lines il
                JOIN stops st ON st.id=il.stop_id JOIN routes r ON r.id=st.route_id
                WHERE r.service_date=?
            """, (date,)))
            for stop in result["stops"]:
                stop["invoice_id"] = claims.get(stop["stop_id"])
            self.send_json(result)
        elif path == "/api/invoice":
            self.send_json(strict_json(self.invoice(self.query(("id",)).get("id", ""))))
        elif path == "/api/operation":
            key = self.query(("key",)).get("key", "")
            row = desk.conn.execute(
                "SELECT action,result_json FROM operations WHERE op_key=?", (key,)
            ).fetchone()
            self.send_json({"found": row is not None, "op_key": key,
                            "action": row["action"] if row else None,
                            "result": strict_json(row["result_json"]) if row else None})
        elif path == "/api/download":
            q = self.query(("kind", "date", "format", "id"))
            kind = q.get("kind")
            if kind == "route":
                date, fmt = iso(q.get("date"), "date"), q.get("format", "json")
                if fmt == "json":
                    raw, mime, ext = json.dumps(desk.route_snapshot(date), ensure_ascii=False, indent=2), "application/json", "json"
                elif fmt == "csv":
                    raw, mime, ext = spreadsheet_csv(desk.route_csv(date)), "text/csv", "csv"
                elif fmt == "markdown":
                    raw, mime, ext = desk.route_markdown(date), "text/markdown", "md"
                else:
                    raise ValidationError("format must be json, csv, or markdown")
                self.send_content(raw, mime + "; charset=utf-8", filename=f"waste-route-{date}.{ext}")
            elif kind == "invoice":
                self.send_content(self.invoice(q.get("id", "")), filename="waste-invoice-DRAFT.json")
            elif kind == "events":
                self.send_content(json.dumps(desk.event_log(), ensure_ascii=False, indent=2), filename="waste-events.json")
            else:
                raise ValidationError("unknown download kind")
        else:
            self.send_json({"error": "NotFound", "message": "Unknown console route"}, 404)

    def post(self):
        self.local_request(api=True)
        path = urlsplit(self.path).path
        if path == "/api/csv-preview":
            body = self.json_body()
            if not isinstance(body, dict) or set(body) != {"csv_text", "timezone_policy"}:
                raise ValidationError("csv preview requires only csv_text and timezone_policy")
            if not isinstance(body["csv_text"], str) or not isinstance(body["timezone_policy"], str):
                raise ValidationError("csv_text and timezone_policy must be strings")
            # manifest_text stays the converter's exact text; do not parse it here.
            self.send_json(preview_csv(body["csv_text"], body["timezone_policy"]))
            return
        if path != "/api/command":
            self.send_json({"error": "NotFound", "message": "Unknown command route"}, 404)
            return
        body = self.json_body()
        result = execute(self.server.desk, body)
        self.send_json({"ok": True, "op_key": body["op_key"], "result": result})

    def run_request(self, method):
        try:
            method()
        except PermissionError as exc:
            self.send_json({"error": "Forbidden", "message": str(exc)}, 403)
        except ValidationError as exc:
            self.send_json({"error": type(exc).__name__, "message": str(exc)}, 400)
        except DeskError as exc:
            self.send_json({"error": type(exc).__name__, "message": str(exc)}, 409)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except sqlite3.Error as exc:
            print(f"Waste console database error: {exc}", file=sys.stderr)
            self.send_json({"error": "DatabaseUnavailable", "message": "Database operation failed. Inspect the server log; keep the operation key for an exact retry."}, 503)
        except Exception as exc:
            print(f"Waste console error: {type(exc).__name__}: {exc}", file=sys.stderr)
            self.send_json({"error": "ConsoleError", "message": "Request failed. Keep the operation key and inspect the server log before retrying."}, 500)

    def do_GET(self):
        self.run_request(self.get)

    def do_POST(self):
        self.run_request(self.post)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Existing or new waste-desk SQLite database")
    parser.add_argument("--port", type=int, default=8786, help="Loopback port (default 8786)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    try:
        with WasteRouteDesk(args.db) as desk:
            with ConsoleServer(args.port, desk) as server:
                print(f"Waste Route Desk: {server.origin}/", flush=True)
                print("Local operator only. Invoice drafts do not send or charge anything. Ctrl-C stops the server.", flush=True)
                server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except (DeskError, OSError, sqlite3.Error) as exc:
        print(f"Cannot open waste console: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
