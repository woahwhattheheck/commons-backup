#!/usr/bin/env python3
"""Parts Sourcing Desk: source-linked options and durable, manual order handoffs.

Python 3.11+, standard library only. No supplier requests or purchases are made.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
import uuid
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from supplier_enquiries import EnquiryError, build_from_desk_request, iso_date, write_pack

MAX_BODY = 2 * 1024 * 1024
FIT = {"unreviewed", "compatible", "uncertain", "incompatible"}
STOCK = {"unknown", "in_stock", "out_of_stock"}
SCHEMA = "parts-sourcing-desk/v1"


class DeskError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def text(value, name: str, required: bool = False, limit: int = 4000) -> str:
    if not isinstance(value, str):
        raise DeskError(f"{name} must be text")
    result = value.strip()
    if len(result) > limit or "\x00" in result:
        raise DeskError(f"{name} is too long or contains a NUL character")
    if required and not result:
        raise DeskError(f"{name} is required")
    return result


def integer(value, name: str, minimum: int = 1, maximum: int = 1000000) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise DeskError(f"{name} must be a whole number")
    number = int(value)
    if not minimum <= number <= maximum:
        raise DeskError(f"{name} must be between {minimum} and {maximum}")
    return number


def cents(value, name: str) -> int | None:
    """Empty means unknown; never silently assume free shipping or a zero price."""
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise DeskError(f"{name} must be a decimal string, not a floating-point value")
    value = str(value)
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value):
        raise DeskError(f"{name} needs a nonnegative amount with at most two decimal places")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise DeskError(f"Invalid {name}") from exc
    if amount > Decimal("10000000"):
        raise DeskError(f"{name} is above the supported amount")
    return int(amount * 100)


def money(value: int | None) -> str | None:
    return None if value is None else f"{value // 100}.{value % 100:02d}"


def source_url(value) -> str:
    value = text(value, "source_url", True, 2000)
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise DeskError("source_url must be an HTTP(S) reference without embedded credentials")
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise DeskError("source_url contains whitespace or control characters")
    return value


def request_data(data: dict) -> dict:
    if not isinstance(data, dict):
        raise DeskError("Request data must be an object")
    result = {key: text(data.get(key, ""), key, key in {"job_ref", "make", "model", "description"})
              for key in ("job_ref", "make", "model", "serial", "part_number", "description", "notes")}
    result["quantity"] = integer(data.get("quantity", 1), "quantity")
    return result


def catalog_data(data: dict) -> dict:
    if not isinstance(data, dict):
        raise DeskError("Each catalog row must be an object")
    result = {key: text(data.get(key, ""), key, key in {"id", "supplier", "supplier_sku", "part_number", "description"})
              for key in ("id", "supplier", "supplier_sku", "make", "model", "part_number", "serial_scope",
                          "description", "lead_time", "source_note")}
    result["source_url"] = source_url(data.get("source_url", ""))
    checked = text(data.get("checked_on", ""), "checked_on", True)
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked):
            raise ValueError()
        date.fromisoformat(checked)
    except ValueError as exc:
        raise DeskError("checked_on must be a valid YYYY-MM-DD date") from exc
    result["checked_on"] = checked
    aliases = data.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [v.strip() for v in aliases.split(";") if v.strip()]
    if not isinstance(aliases, list) or len(aliases) > 100:
        raise DeskError("aliases must be a list or a semicolon-separated string, at most 100 entries")
    result["aliases"] = list(dict.fromkeys(text(v, "alias", True, 200) for v in aliases))
    result["unit_price"] = money(cents(data.get("unit_price", ""), "unit_price"))
    result["shipping"] = money(cents(data.get("shipping", ""), "shipping"))
    currency = text(data.get("currency", ""), "currency", True)
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise DeskError("currency must be a three-letter uppercase code; no conversion is performed")
    result["currency"] = currency
    result["stock_status"] = text(data.get("stock_status", "unknown"), "stock_status")
    if result["stock_status"] not in STOCK:
        raise DeskError("stock_status must be unknown, in_stock or out_of_stock")
    qty = data.get("stock_qty", "")
    result["stock_qty"] = None if qty is None or qty == "" else integer(qty, "stock_qty", 0)
    return result


class Desk:
    def __init__(self, database: str | Path):
        self.database = str(database)
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS requests(
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, job_key TEXT NOT NULL UNIQUE,
                    document TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS catalog(
                    id TEXT PRIMARY KEY, version INTEGER NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS options(
                    id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
                    catalog_id TEXT NOT NULL REFERENCES catalog(id), catalog_version INTEGER NOT NULL,
                    snapshot TEXT NOT NULL, review TEXT NOT NULL,
                    UNIQUE(request_id,catalog_id));
                CREATE TABLE IF NOT EXISTS orders(
                    id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
                    revision INTEGER NOT NULL, status TEXT NOT NULL,
                    document TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_order
                    ON orders(request_id) WHERE status != 'cancelled';
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL REFERENCES requests(id),
                    at TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations(
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def row(db, table: str, identity: str):
        # Table names are code-owned, never interpolated from a request parameter.
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise DeskError(f"{table.rstrip('s')} not found", 404)
        return row

    @staticmethod
    def check_revision(row, expected):
        if integer(expected, "revision") != row["revision"]:
            raise DeskError("This record changed. Reload before editing; your saved record was preserved.", 409)

    @staticmethod
    def touch(db, rid: str):
        db.execute("UPDATE requests SET revision=revision+1, updated_at=? WHERE id=?", (stamp(), rid))

    @staticmethod
    def event(db, rid: str, action: str, detail: dict):
        db.execute("INSERT INTO events(request_id,at,action,detail) VALUES(?,?,?,?)", (rid, stamp(), action, dumps(detail)))

    def mutate(self, operation: str, identity: str, body: dict) -> dict:
        if not isinstance(body, dict):
            raise DeskError("JSON body must be an object")
        op_id = text(body.get("operation_id", ""), "operation_id", True, 200)
        fingerprint = hashlib.sha256(dumps([operation, identity, body]).encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute("SELECT * FROM operations WHERE id=?", (op_id,)).fetchone()
                if old is not None:
                    if old["fingerprint"] != fingerprint:
                        raise DeskError("operation_id was already used for a different request", 409)
                    return json.loads(old["response"])
                result = self._mutate(db, operation, identity, body)
                db.execute("INSERT INTO operations VALUES(?,?,?)", (op_id, fingerprint, dumps(result)))
                db.commit()
                return result
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise DeskError("Duplicate job reference, option or active order; reload the existing record.", 409) from exc
            except Exception:
                db.rollback()
                raise

    def _mutate(self, db, operation: str, identity: str, body: dict) -> dict:
        if operation == "catalog":
            items = body.get("items")
            if body.get("format") == "csv":
                content = text(body.get("content", ""), "content", True, MAX_BODY)
                reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
                if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                    raise DeskError("CSV needs unique column names")
                items = list(reader)
            if not isinstance(items, list) or not 1 <= len(items) <= 2000:
                raise DeskError("Import needs 1–2000 catalog rows")
            items = [catalog_data(item) for item in items]
            if len({item["id"] for item in items}) != len(items):
                raise DeskError("Catalog IDs must be unique within an import")
            changed = 0
            for item in items:
                content = dumps(item)
                old = db.execute("SELECT * FROM catalog WHERE id=?", (item["id"],)).fetchone()
                if old is None:
                    db.execute("INSERT INTO catalog VALUES(?,1,?)", (item["id"], content))
                    changed += 1
                elif content != old["document"]:
                    db.execute("UPDATE catalog SET version=version+1,document=? WHERE id=?", (content, item["id"]))
                    changed += 1
            return {"rows": len(items), "changed": changed}
        if operation == "request":
            data = request_data(body.get("data", {}))
            now = stamp()
            if not identity:
                identity = uuid.uuid4().hex
                db.execute("INSERT INTO requests VALUES(?,1,?,?,?,?)",
                           (identity, data["job_ref"].casefold(), dumps(data), now, now))
            else:
                row = self.row(db, "requests", identity)
                self.check_revision(row, body.get("revision"))
                db.execute("UPDATE requests SET job_key=?,document=?,revision=revision+1,updated_at=? WHERE id=?",
                           (data["job_ref"].casefold(), dumps(data), now, identity))
            self.event(db, identity, "request_saved", data)
            return self.request(identity, db)
        if operation in ("option", "draft"):
            req = self.row(db, "requests", identity)
            self.check_revision(req, body.get("revision"))
            if operation == "option":
                cat = self.row(db, "catalog", text(body.get("catalog_id", ""), "catalog_id", True))
                oid = uuid.uuid4().hex
                db.execute("INSERT INTO options VALUES(?,?,?,?,?,?)",
                           (oid, identity, cat["id"], cat["version"], cat["document"], dumps({"fit": "unreviewed"})))
                self.touch(db, identity)
                self.event(db, identity, "option_added", {"option_id": oid, "catalog": json.loads(cat["document"])})
            else:
                option = self.row(db, "options", text(body.get("option_id", ""), "option_id", True))
                if option["request_id"] != identity:
                    raise DeskError("The option belongs to a different request")
                enriched = self.option(option, req, db)
                document = {"request": json.loads(req["document"]), "request_id": identity,
                            "request_revision": req["revision"], "option": enriched,
                            "supplier_reference": "", "placed_at": None, "cancellation": None}
                self.draft_values(document, body)
                oid = uuid.uuid4().hex
                db.execute("INSERT INTO orders VALUES(?,?,1,'draft',?,?)", (oid, identity, dumps(document), stamp()))
                self.touch(db, identity)
                self.event(db, identity, "draft_created", {"order_id": oid, "document": document})
            return self.request(identity, db)
        if operation in ("review", "refresh"):
            option = self.row(db, "options", identity)
            req = self.row(db, "requests", option["request_id"])
            self.check_revision(req, body.get("revision"))
            if operation == "refresh":
                cat = self.row(db, "catalog", option["catalog_id"])
                db.execute("UPDATE options SET snapshot=?,catalog_version=?,review=? WHERE id=?",
                           (cat["document"], cat["version"], dumps({"fit": "unreviewed"}), identity))
                detail = {"option_id": identity, "catalog": json.loads(cat["document"])}
            else:
                fit = text(body.get("fit", "unreviewed"), "fit")
                if fit not in FIT:
                    raise DeskError("Unknown fit state")
                review = {"fit": fit, "technician": text(body.get("technician", ""), "technician", fit != "unreviewed"),
                          "note": text(body.get("note", ""), "note", fit != "unreviewed"), "at": stamp(),
                          "request_hash": hashlib.sha256(req["document"].encode()).hexdigest()}
                cat = self.row(db, "catalog", option["catalog_id"])
                if cat["version"] != option["catalog_version"]:
                    raise DeskError("Catalog changed; refresh the option before recording a new fit review", 409)
                db.execute("UPDATE options SET review=? WHERE id=?", (dumps(review), identity))
                detail = {"option_id": identity, "review": review}
            self.touch(db, req["id"])
            self.event(db, req["id"], "option_" + operation, detail)
            return self.request(req["id"], db)
        if operation in ("order_edit", "placed", "cancel"):
            order = self.row(db, "orders", identity)
            self.check_revision(order, body.get("revision"))
            doc = json.loads(order["document"])
            status = order["status"]
            if operation == "order_edit":
                if status != "draft":
                    raise DeskError("Recorded orders retain their original amounts; use the cancellation record for changes", 409)
                self.draft_values(doc, body)
            elif operation == "placed":
                if status != "draft":
                    raise DeskError("Only an existing draft can be recorded as placed", 409)
                doc["supplier_reference"] = text(body.get("supplier_reference", ""), "supplier_reference", True, 500)
                doc["placed_at"] = stamp()
                status = "placed"
            else:
                if status == "cancelled":
                    raise DeskError("Order is already cancelled", 409)
                doc["cancellation"] = {"note": text(body.get("note", ""), "note", True),
                                       "supplier_confirmation": text(body.get("supplier_confirmation", ""),
                                                                      "supplier_confirmation", status == "placed"), "at": stamp()}
                status = "cancelled"
            db.execute("UPDATE orders SET revision=revision+1,status=?,document=? WHERE id=?", (status, dumps(doc), identity))
            self.touch(db, order["request_id"])
            self.event(db, order["request_id"], operation, {"order_id": identity, "document": doc})
            return self.request(order["request_id"], db)
        raise DeskError("Unknown operation", 404)

    @staticmethod
    def draft_values(doc: dict, body: dict):
        offer = doc["option"]["snapshot"]
        doc["quantity"] = integer(body.get("quantity", doc.get("quantity", doc["request"]["quantity"])), "quantity")
        price = cents(body.get("unit_price", doc.get("unit_price", offer["unit_price"])), "unit_price")
        shipping = cents(body.get("shipping", doc.get("shipping", offer["shipping"])), "shipping")
        doc.update(unit_price=money(price), shipping=money(shipping), currency=offer["currency"],
                   subtotal=money(None if price is None else price * doc["quantity"]),
                   total_before_tax=money(None if price is None or shipping is None else price * doc["quantity"] + shipping),
                   notes=text(body.get("notes", doc.get("notes", "")), "notes"))

    def option(self, row, req, db) -> dict:
        result = dict(row)
        result["snapshot"] = json.loads(row["snapshot"])
        result["review"] = json.loads(row["review"])
        cat = self.row(db, "catalog", row["catalog_id"])
        result["catalog_changed"] = cat["version"] != row["catalog_version"]
        review = result["review"]
        result["request_changed"] = review.get("request_hash") not in (None, hashlib.sha256(req["document"].encode()).hexdigest())
        result["effective_fit"] = ("stale" if result["catalog_changed"] or result["request_changed"] else review["fit"])
        return result

    def request(self, identity: str, db=None) -> dict:
        if db is None:
            with self.connect() as conn:
                return self.request(identity, conn)
        row = self.row(db, "requests", identity)
        result = dict(row)
        result.pop("job_key")
        result["data"] = json.loads(result.pop("document"))
        result["options"] = [self.option(item, row, db) for item in db.execute("SELECT * FROM options WHERE request_id=? ORDER BY rowid", (identity,))]
        result["orders"] = [self.order(item, db) for item in db.execute("SELECT * FROM orders WHERE request_id=? ORDER BY rowid DESC", (identity,))]
        result["events"] = [{**dict(item), "detail": json.loads(item["detail"])} for item in
                            db.execute("SELECT * FROM events WHERE request_id=? ORDER BY seq DESC", (identity,))]
        return result

    def order(self, row, db) -> dict:
        result = dict(row)
        doc = json.loads(result["document"])
        result["document"] = doc
        warnings = []
        req = self.row(db, "requests", row["request_id"])
        current = self.option(self.row(db, "options", doc["option"]["id"]), req, db)
        # Historical snapshot and live warnings coexist; neither silently rewrites an order.
        if current["effective_fit"] != "compatible":
            warnings.append("Current option fit: " + current["effective_fit"])
        if doc["option"]["effective_fit"] != "compatible":
            warnings.append("Fit at draft creation: " + doc["option"]["effective_fit"])
        if doc["request"] != json.loads(req["document"]):
            warnings.append("Request changed after this handoff was created")
        if doc["option"]["snapshot"] != current["snapshot"] or current["catalog_changed"]:
            warnings.append("Catalog or option changed after this handoff was created")
        offer = doc["option"]["snapshot"]
        if offer["stock_status"] != "in_stock":
            warnings.append("Stock is " + offer["stock_status"].replace("_", " "))
        if offer["stock_qty"] is not None and offer["stock_qty"] < doc["quantity"]:
            warnings.append("Recorded supplier stock is below the requested quantity")
        if doc["unit_price"] is None:
            warnings.append("Unit price is unknown")
        if doc["shipping"] is None:
            warnings.append("Shipping is unknown; total cannot be calculated")
        warnings.append("Tax, live stock, shipping date and physical fit require shop confirmation")
        result["warnings"] = warnings
        return result

    def catalog(self, query: str = "") -> list[dict]:
        query = query.strip().casefold()
        with self.connect() as db:
            rows = [{"version": row["version"], **json.loads(row["document"])} for row in db.execute("SELECT * FROM catalog ORDER BY id")]
        result = []
        for row in rows:
            fields = [row[k] for k in ("id", "supplier", "supplier_sku", "make", "model", "part_number", "description")]
            if not query or any(query in value.casefold() for value in fields + row["aliases"]):
                row["match"] = "exact part/alias" if query and query in [v.casefold() for v in [row["part_number"], *row["aliases"]]] else "text match"
                result.append(row)
        return result

    def state(self) -> dict:
        with self.connect() as db:
            requests = [{"id": row["id"], "revision": row["revision"], "updated_at": row["updated_at"],
                         **json.loads(row["document"])} for row in db.execute("SELECT * FROM requests ORDER BY updated_at DESC")]
            return {"schema": SCHEMA, "requests": requests, "catalog_count": db.execute("SELECT COUNT(*) FROM catalog").fetchone()[0]}

    def export(self) -> dict:
        with self.connect() as db:
            db.execute("BEGIN")
            return {"schema": SCHEMA, "exported_at": stamp(),
                    "tables": {table: [dict(row) for row in db.execute(f"SELECT * FROM {table}")]
                               for table in ("requests", "catalog", "options", "orders", "events", "operations")}}

    def backup(self) -> bytes:
        with self.connect() as db:
            with closing(sqlite3.connect(":memory:")) as copy:
                db.backup(copy)
                return copy.serialize()

    def handoff(self, identity: str) -> str:
        with self.connect() as db:
            order = self.order(self.row(db, "orders", identity), db)
        doc, offer = order["document"], order["document"]["option"]["snapshot"]
        req = doc["request"]
        lines = ["PARTS SOURCING — MANUAL ORDER HANDOFF", f"Order {identity} / revision {order['revision']} / {order['status']}",
                 "This application has not contacted a supplier or made a purchase.", "",
                 f"Job: {req['job_ref']}", f"Equipment: {req['make']} {req['model']}; serial: {req['serial'] or 'not supplied'}",
                 f"Requested part: {req['part_number'] or 'not supplied'}; {req['description']}",
                 f"Supplier: {offer['supplier']}; SKU: {offer['supplier_sku']}; offered part: {offer['part_number']}",
                 f"Catalog model: {offer['make']} {offer['model']}; serial scope: {offer['serial_scope'] or 'not supplied'}",
                 f"Source: {offer['source_url']}", f"Source note: {offer['source_note']}",
                 f"Observed: {offer['checked_on']}; stock: {offer['stock_status']}; lead time: {offer['lead_time'] or 'unknown'}",
                 f"Fit when drafted: {doc['option']['effective_fit']}; technician: {doc['option']['review'].get('technician', '')}",
                 f"Fit note: {doc['option']['review'].get('note', '')}",
                 f"Quantity: {doc['quantity']}; unit: {doc['currency']} {doc['unit_price'] or 'UNKNOWN'}",
                 f"Shipping: {doc['shipping'] or 'UNKNOWN'}; subtotal: {doc['subtotal'] or 'UNKNOWN'}",
                 f"Total before tax: {doc['currency']} {doc['total_before_tax'] or 'UNKNOWN'}", f"Notes: {doc['notes']}",
                 f"Supplier order reference: {doc['supplier_reference'] or 'none recorded'}", "", "CHECK BEFORE ORDERING:"]
        lines += ["- " + warning for warning in order["warnings"]]
        if doc["cancellation"]:
            lines += ["", "Cancellation record: " + dumps(doc["cancellation"])]
        return "\n".join(lines) + "\n"


def enquiry_archive(desk: Desk, identity: str, parameters: dict) -> bytes:
    """Download the existing exporter output without changing saved desk state."""
    if not isinstance(parameters, dict):
        raise DeskError("Enquiry export parameters must be an object")
    effective_date = iso_date(parameters["as_of"], "as_of") if "as_of" in parameters else None
    max_age = integer(parameters.get("max_age_days", 7), "max_age_days", 0, 36500)
    pack = build_from_desk_request(desk.request(identity), parameters.get("option_ids"),
                                   as_of=effective_date, max_age_days=max_age)
    try:
        with TemporaryDirectory(prefix="parts-enquiries-") as directory:
            destination = Path(directory) / "pack"
            write_pack(pack, destination)
            output = io.BytesIO()
            with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
                for path in sorted(destination.iterdir()):
                    archive.write(path, path.name)
            return output.getvalue()
    except OSError as exc:
        raise DeskError("Enquiry export storage is unavailable; check temporary storage and retry", 503) from exc


def make_server(desk: Desk, host: str = "127.0.0.1", port: int = 8080):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, status=200, content_type="application/json; charset=utf-8", filename=None):
            if not isinstance(data, bytes):
                data = dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                url = urlsplit(self.path)
                parts = url.path.strip("/").split("/")
                if url.path == "/":
                    return self.reply(Path(__file__).with_name("index.html").read_bytes(), content_type="text/html; charset=utf-8")
                if url.path == "/api/state":
                    return self.reply(desk.state())
                if url.path == "/api/catalog":
                    return self.reply(desk.catalog(parse_qs(url.query).get("q", [""])[0]))
                if url.path == "/api/export":
                    return self.reply(desk.export(), filename="parts-desk-export.json")
                if url.path == "/api/backup":
                    return self.reply(desk.backup(), content_type="application/vnd.sqlite3", filename="parts-desk.sqlite3")
                if len(parts) == 3 and parts[:2] == ["api", "requests"]:
                    return self.reply(desk.request(parts[2]))
                if len(parts) == 4 and parts[:2] == ["api", "requests"] and parts[3] == "enquiries.zip":
                    query = parse_qs(url.query, keep_blank_values=True)
                    parameters = {name: query[name][0] for name in ("as_of", "max_age_days") if name in query}
                    parameters["option_ids"] = query.get("option_id")
                    content = enquiry_archive(desk, parts[2], parameters)
                    return self.reply(content, content_type="application/zip", filename="parts-supplier-enquiries.zip")
                if len(parts) == 4 and parts[:2] == ["api", "orders"] and parts[3] == "handoff.txt":
                    content = desk.handoff(parts[2]).encode("utf-8")
                    return self.reply(content, content_type="text/plain; charset=utf-8", filename="parts-handoff.txt")
                raise DeskError("Route not found", 404)
            except DeskError as exc:
                self.reply({"error": str(exc)}, exc.status)
            except EnquiryError as exc:
                self.reply({"error": str(exc)}, 400)

        def do_POST(self):
            try:
                length = integer(self.headers.get("Content-Length", "0"), "Content-Length", 1, MAX_BODY)
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise DeskError("Send application/json", 415)
                body = json.loads(self.rfile.read(length).decode("utf-8"),
                                  parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                parts = urlsplit(self.path).path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "requests"] and parts[3] == "enquiries.zip":
                    content = enquiry_archive(desk, parts[2], body)
                    return self.reply(content, content_type="application/zip", filename="parts-supplier-enquiries.zip")
                operation, identity = "", ""
                if parts == ["api", "catalog", "import"]:
                    operation = "catalog"
                elif parts == ["api", "requests"]:
                    operation = "request"
                elif len(parts) == 3 and parts[:2] == ["api", "requests"]:
                    operation, identity = "request", parts[2]
                elif len(parts) == 4 and parts[:2] == ["api", "requests"]:
                    operation, identity = {"options": "option", "orders": "draft"}.get(parts[3], ""), parts[2]
                elif len(parts) == 4 and parts[:2] == ["api", "options"]:
                    operation, identity = {"review": "review", "refresh": "refresh"}.get(parts[3], ""), parts[2]
                elif len(parts) in (3, 4) and parts[:2] == ["api", "orders"]:
                    operation, identity = ("order_edit" if len(parts) == 3 else {"placed": "placed", "cancel": "cancel"}.get(parts[3], "")), parts[2]
                self.reply(desk.mutate(operation, identity, body))
            except DeskError as exc:
                self.reply({"error": str(exc)}, exc.status)
            except EnquiryError as exc:
                self.reply({"error": str(exc)}, 400)
            except (ValueError, UnicodeError, RecursionError):
                self.reply({"error": "Invalid JSON or unsupported value"}, 400)
            except sqlite3.OperationalError:
                self.reply({"error": "Storage is busy or unavailable; retry the same operation_id"}, 503)

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(Path.home() / ".parts-sourcing-desk" / "desk.sqlite3"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--import-catalog", type=Path)
    args = parser.parse_args()
    desk = Desk(args.db)
    if args.import_catalog:
        content = args.import_catalog.read_text(encoding="utf-8-sig")
        body = {"operation_id": uuid.uuid4().hex}
        if args.import_catalog.suffix.lower() == ".csv":
            body.update(format="csv", content=content)
        else:
            body["items"] = json.loads(content)
        print(dumps(desk.mutate("catalog", "", body)))
        return
    server = make_server(desk, args.host, args.port)
    print(f"Parts Sourcing Desk: http://{args.host}:{server.server_port} — no supplier actions are performed", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
