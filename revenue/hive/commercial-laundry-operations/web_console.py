"""Local browser operator surface for the existing LaundryDesk engine.

No second state machine, invoice arithmetic, provider client, or scheduler.
Run: python web_console.py /path/to/desk.sqlite [--init] [--port 8765]
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import hmac
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit

import operate
from laundry_desk import LaundryDesk, LaundryDeskError, ValidationError

PAGE_SIZE = 100
CATALOGS = {
    "customers": ("customers", "customer_id", "customer_id,name"),
    "sites": ("sites", "site_id", "site_id,customer_id,name"),
    "agreements": ("agreements", "agreement_id", "agreement_id,site_id,item_code,unit_price_cents,active_from,active_to"),
    "plans": ("service_plans", "plan_id", "plan_id,site_id,route_code,weekday,stop_sequence,active_from,active_to"),
    "routes": ("routes", "route_id", "route_id,service_date,route_code,state"),
}
FORMATS = {"json": ("application/json", "json"), "csv": ("text/csv", "csv"),
           "markdown": ("text/markdown", "md")}


class ConsoleDenied(LaundryDeskError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class DatabaseChanged(LaundryDeskError):
    """A pending request may refer to a previous database; preserve it."""


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, database: Path, port: int):
        operate._regular_database(database)
        LaundryDesk.open_read_only(database)
        self.database = database.absolute()
        self.token = secrets.token_urlsafe(32)
        self.identity = self.file_identity()
        # Not a credential: binds a browser's pending operation to this file,
        # including across server restarts, rather than merely its display name.
        self.database_key = hashlib.sha256(
            f"{self.database}:{self.identity}".encode("utf-8")).hexdigest()
        self.html = Path(__file__).with_name("web_console.html").read_bytes()
        scripts = re.findall(rb"<script>(.*?)</script>", self.html, flags=re.S)
        script_sources = " ".join("'sha256-" + base64.b64encode(
            hashlib.sha256(script).digest()).decode("ascii") + "'" for script in scripts)
        self.csp = ("default-src 'self'; script-src " + script_sources + "; "
                    "style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'; "
                    "frame-ancestors 'none'; form-action 'self'")
        super().__init__(("127.0.0.1", port), ConsoleHandler)

    def file_identity(self) -> tuple[int, int]:
        operate._regular_database(self.database)
        info = self.database.stat()
        return info.st_dev, info.st_ino

    def desk(self) -> LaundryDesk:
        if self.file_identity() != self.identity:
            raise DatabaseChanged("database file changed; restart the console before continuing")
        return LaundryDesk.open_read_only(self.database)


class ConsoleHandler(BaseHTTPRequestHandler):
    server: ConsoleServer
    server_version = "LaundryConsole/1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, format: str, *args: object) -> None:
        # Access logs must not print customer IDs, notes, or request bodies.
        pass

    def send_bytes(self, status: int, body: bytes, content_type: str,
                   filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.server.csp)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, value: object) -> None:
        self.send_bytes(status, json.dumps(value, ensure_ascii=True, allow_nan=False,
                                          separators=(",", ":")).encode(), "application/json")

    def browser_origin(self, *, api: bool, mutate: bool) -> None:
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        supplied_hosts = self.headers.get_all("Host", [])
        if len(supplied_hosts) != 1 or supplied_hosts[0] not in hosts:
            raise ConsoleDenied(403, "open the printed loopback URL directly")
        origin = self.headers.get_all("Origin", [])
        expected_origin = "http://" + supplied_hosts[0]
        if (origin and origin != [expected_origin]) or (mutate and not origin):
            raise ConsoleDenied(403, "a same-origin browser request is required")
        if api:
            supplied = self.headers.get_all("Authorization", [])
            expected = ("Bearer " + self.server.token).encode("ascii")
            if len(supplied) != 1 or not hmac.compare_digest(supplied[0].encode("utf-8"), expected):
                raise ConsoleDenied(401, "unlock with the current console session key")

    def run_request(self, mutate: bool = False) -> None:
        try:
            parsed = urlsplit(self.path)
            self.browser_origin(api=parsed.path != "/" or mutate, mutate=mutate)
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8)
            if any(len(values) != 1 for values in query.values()):
                raise ValidationError("query parameters must occur once")
            args = {key: values[0] for key, values in query.items()}
            if mutate:
                self.apply_operation(parsed.path)
            elif parsed.path == "/":
                self.send_bytes(200, self.server.html, "text/html")
            elif parsed.path == "/api/info":
                self.server.desk()
                self.send_json(200, {"database": self.server.database.name,
                    "database_key": self.server.database_key, "authority": operate.authority(),
                    "commands": {name: {"required": {k: t.__name__ for k, t in required.items()},
                        "optional": {k: t.__name__ for k, t in optional.items()}}
                        for name, (_, required, optional) in operate.COMMANDS.items()}})
            elif parsed.path.startswith("/api/catalog/"):
                self.catalog(parsed.path.removeprefix("/api/catalog/"), args)
            elif parsed.path in ("/api/route", "/api/customer"):
                desk = self.server.desk()
                method = desk.route_snapshot if parsed.path == "/api/route" else desk.customer_snapshot
                self.send_json(200, method(args.get("id", "")))
            elif parsed.path == "/api/export":
                self.export(args)
            else:
                self.send_json(404, {"status": "REJECTED", "message": "unknown endpoint"})
        except ConsoleDenied as exc:
            self.send_json(exc.status, {"status": "LOCKED", "message": str(exc)})
        except DatabaseChanged as exc:
            self.send_json(409, {"status": "DATABASE_CHANGED", "message": str(exc),
                                 "authority": operate.authority()})
        except (LaundryDeskError, ValueError, UnicodeError) as exc:
            # The existing engine rolls rejected operations back. A lost
            # response is still ambiguous to the browser; the same key can retry.
            self.send_json(400, {"status": "REJECTED", "error_type": type(exc).__name__,
                                 "message": str(exc), "authority": operate.authority()})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except (sqlite3.Error, OSError, OverflowError) as exc:
            self.send_json(503, {"status": "UNAVAILABLE", "error_type": type(exc).__name__,
                "message": "Local storage unavailable. Keep the operation key and retry the exact request; inspect the server terminal.",
                "authority": operate.authority()})
            print(f"laundry console: {type(exc).__name__}: {exc}", file=sys.stderr)
        except Exception as exc:
            self.send_json(500, {"status": "UNAVAILABLE", "error_type": type(exc).__name__,
                "message": "Unexpected local error. Preserve this operation key; do not submit a new copy."})
            print(f"laundry console: {type(exc).__name__}: {exc}", file=sys.stderr)

    def do_GET(self) -> None:
        self.run_request()

    def do_POST(self) -> None:
        self.run_request(mutate=True)

    def catalog(self, section: str, args: dict[str, str]) -> None:
        if section not in CATALOGS:
            raise ValidationError("unknown catalog")
        table, key, columns = CATALOGS[section]
        after = args.get("after", "")
        if len(after) > 255:
            raise ValidationError("catalog cursor is too long")
        where, params = "1=1", []
        day = args.get("date", "")
        if day:
            if section != "routes" or date.fromisoformat(day).isoformat() != day:
                raise ValidationError("date filter requires a canonical route date")
            where, params = "service_date=?", [day]
        with closing(self.server.desk()._connect()) as conn:
            conn.execute("BEGIN")
            total = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]
            rows = [dict(row) for row in conn.execute(
                f"SELECT {columns} FROM {table} WHERE {where} AND {key}>? ORDER BY {key} LIMIT ?",
                [*params, after, PAGE_SIZE + 1])]
        more = len(rows) > PAGE_SIZE
        rows = rows[:PAGE_SIZE]
        self.send_json(200, {"section": section, "rows": rows, "total": total,
            "page_size": PAGE_SIZE, "next": rows[-1][key] if more else None,
            "observed_at": datetime.now(timezone.utc).isoformat()})

    def apply_operation(self, path: str) -> None:
        command = path.removeprefix("/api/operate/")
        if not path.startswith("/api/operate/") or command not in operate.COMMANDS:
            raise ValidationError("unknown operation")
        if self.headers.get("X-Laundry-Database") != self.server.database_key:
            raise DatabaseChanged("this request belongs to another database; reopen the printed console URL")
        if self.headers.get_content_type() != "application/json":
            raise ValidationError("send application/json")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
            raise ValidationError("one Content-Length is required; streaming bodies are not supported")
        length = int(lengths[0])
        if not 0 < length <= operate.MAX_INPUT_BYTES:
            raise ValidationError("operation exceeds the existing one-megabyte input limit")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValidationError("incomplete request body")
        self.server.desk()
        # Use the existing adapter's complete UTF-8/JSON/type/structure contract.
        # Temporary inputs are private and removed; the SQLite engine is the
        # only persistent writer and retains the original idempotency behavior.
        with tempfile.TemporaryDirectory(prefix="laundry-operation-") as directory:
            payload = Path(directory) / "operation.json"
            payload.write_bytes(raw)
            result = operate.execute(str(self.server.database), command, str(payload))
        self.send_json(200, result)

    def export(self, args: dict[str, str]) -> None:
        kind, format_name, object_id = args.get("kind"), args.get("format"), args.get("id", "")
        if kind not in ("route", "customer") or format_name not in FORMATS:
            raise ValidationError("export requires route/customer and json/csv/markdown")
        desk = self.server.desk()
        exports = desk.render_route_exports(object_id) if kind == "route" else desk.render_customer_exports(object_id)
        mime, suffix = FORMATS[format_name]
        filename = f"{kind}-{hashlib.sha256(object_id.encode()).hexdigest()[:16]}.{suffix}"
        self.send_bytes(200, exports[format_name].encode("utf-8"), mime, filename)


def main(argv: list[str] | None = None, *, default_port: int = 8765) -> int:
    parser = argparse.ArgumentParser(description="Local laundry operations console; draft invoices only")
    parser.add_argument("database", type=Path, help="existing operator-owned SQLite file")
    parser.add_argument("--init", action="store_true", help="explicitly initialize a NEW file; never overwrite")
    parser.add_argument("--port", type=int, default=default_port, help="loopback port (0 chooses an available port)")
    args = parser.parse_args(argv)
    try:
        if not 0 <= args.port <= 65535:
            raise ValidationError("port must be 0..65535")
        if args.init:
            operate.execute(str(args.database), "init", None)
        with ConsoleServer(args.database, args.port) as server:
            print(f"Open http://127.0.0.1:{server.server_port}/#key={server.token}", flush=True)
            print("Private session address: do not share it. Lock clears the browser, not the server.", flush=True)
            print("Local operator records only. No customer sends, payment, or accounting writes.", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (LaundryDeskError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"laundry console: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
