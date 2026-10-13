#!/usr/bin/env python3
"""Local-first focused storefront control plane. Standard library only."""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import mimetypes
import sqlite3
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SCHEMA_VERSION = 1
ORDER_STATES = {"placed", "fulfilled", "return_requested", "returned", "cancelled"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_text(value, name: str, maximum: int = 4000, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f"{name} must be {'text' if empty else 'non-empty text'} up to {maximum} characters")
    return value.strip()


def cents(value, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer number of cents")
    return value


def quantity(value, name: str = "quantity") -> int:
    if type(value) is not int or value <= 0 or value > 10000:
        raise ValueError(f"{name} must be an integer from 1 to 10000")
    return value


def load_fixture(path: Path) -> dict:
    raw = path.read_bytes()
    doc = json.loads(raw)
    required = {
        "fixture_kind", "supplier", "product", "economics", "shipping_terms",
        "support_terms", "inventory_units", "media"
    }
    if not isinstance(doc, dict) or set(doc) != required:
        raise ValueError("supplier fixture has an unexpected shape")
    if doc["fixture_kind"] not in {"synthetic", "authorized"}:
        raise ValueError("fixture_kind must be synthetic or authorized")
    supplier = doc["supplier"]
    product = doc["product"]
    economics = doc["economics"]
    media = doc["media"]
    if not isinstance(supplier, dict) or set(supplier) != {"name", "source_reference", "verified"}:
        raise ValueError("supplier requires name/source_reference/verified")
    if not isinstance(product, dict) or set(product) != {"sku", "name", "description", "sample_verified"}:
        raise ValueError("product requires sku/name/description/sample_verified")
    for key in ("name", "source_reference"):
        require_text(supplier[key], f"supplier.{key}", 500)
    require_text(product["sku"], "product.sku", 80)
    require_text(product["name"], "product.name", 160)
    require_text(product["description"], "product.description", 2000)
    if type(supplier["verified"]) is not bool or type(product["sample_verified"]) is not bool:
        raise ValueError("verified flags must be booleans")
    if not isinstance(economics, dict) or set(economics) != {
        "price_cents", "landed_cost_cents", "channel_fee_bps", "return_reserve_cents", "support_allowance_cents"
    }:
        raise ValueError("economics has an unexpected shape")
    cents(economics["price_cents"], "price_cents")
    cents(economics["landed_cost_cents"], "landed_cost_cents")
    cents(economics["return_reserve_cents"], "return_reserve_cents")
    cents(economics["support_allowance_cents"], "support_allowance_cents")
    if type(economics["channel_fee_bps"]) is not int or not 0 <= economics["channel_fee_bps"] <= 10000:
        raise ValueError("channel_fee_bps must be an integer from 0 to 10000")
    quantity(doc["inventory_units"], "inventory_units")
    require_text(doc["shipping_terms"], "shipping_terms", 2000)
    require_text(doc["support_terms"], "support_terms", 2000)
    if not isinstance(media, list) or not media:
        raise ValueError("media must contain at least one item")
    cleaned_media = []
    for item in media:
        if not isinstance(item, dict) or set(item) != {"path", "label", "origin"}:
            raise ValueError("media item requires path/label/origin")
        rel = Path(require_text(item["path"], "media.path", 300))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("media path must stay inside package")
        data = (HERE / rel).read_bytes()
        cleaned_media.append({**item, "sha256": sha256_bytes(data), "bytes": len(data)})
    return {**doc, "fixture_sha256": sha256_bytes(raw), "media": cleaned_media}


def economics(doc: dict, units: int = 1) -> dict:
    quantity(units, "units")
    e = doc["economics"]
    gross = e["price_cents"] * units
    landed = e["landed_cost_cents"] * units
    fees = (gross * e["channel_fee_bps"] + 9999) // 10000
    reserve = e["return_reserve_cents"] * units
    support = e["support_allowance_cents"] * units
    contribution = gross - landed - fees - reserve - support
    return {
        "units": units,
        "gross_revenue_cents": gross,
        "landed_cost_cents": landed,
        "channel_fee_cents": fees,
        "return_reserve_cents": reserve,
        "support_allowance_cents": support,
        "contribution_cents": contribution,
    }


class Store:
    def __init__(self, db_path: Path | str, fixture_path: Path | str):
        self.db_path = str(db_path)
        self.fixture_path = Path(fixture_path)
        self.fixture = load_fixture(self.fixture_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection(write=True) as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS inventory (
                sku TEXT PRIMARY KEY, on_hand INTEGER NOT NULL CHECK(on_hand >= 0),
                reserved INTEGER NOT NULL CHECK(reserved >= 0 AND reserved <= on_hand), version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, idem_key TEXT NOT NULL UNIQUE, sku TEXT NOT NULL,
                quantity INTEGER NOT NULL, state TEXT NOT NULL, price_cents INTEGER NOT NULL,
                economics_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS returns (
                id TEXT PRIMARY KEY, idem_key TEXT NOT NULL UNIQUE, order_id TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL, state TEXT NOT NULL, restock INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT NOT NULL, kind TEXT NOT NULL,
                delta_on_hand INTEGER NOT NULL, delta_reserved INTEGER NOT NULL,
                ref TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """)
            fixture_sha = self.fixture["fixture_sha256"]
            existing = db.execute("SELECT value FROM metadata WHERE key='fixture_sha256'").fetchone()
            if existing is None:
                db.executemany("INSERT INTO metadata(key,value) VALUES(?,?)", [
                    ("schema_version", str(SCHEMA_VERSION)),
                    ("fixture_sha256", fixture_sha),
                    ("fixture_path", str(self.fixture_path)),
                ])
                sku = self.fixture["product"]["sku"]
                units = self.fixture["inventory_units"]
                db.execute("INSERT INTO inventory VALUES(?,?,?,?)", (sku, units, 0, 1))
                db.execute(
                    "INSERT INTO ledger(sku,kind,delta_on_hand,delta_reserved,ref,created_at) VALUES(?,?,?,?,?,?)",
                    (sku, "initial_fixture", units, 0, fixture_sha, now()),
                )
            elif existing[0] != fixture_sha:
                raise ValueError("database fixture hash does not match supplied fixture; migrate explicitly")

    @contextlib.contextmanager
    def connection(self, write: bool = False):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _inventory(db, sku: str):
        row = db.execute("SELECT * FROM inventory WHERE sku=?", (sku,)).fetchone()
        if row is None:
            raise ValueError("unknown SKU")
        return dict(row)

    def gates(self) -> dict:
        return {
            "supplier_verified": bool(self.fixture["supplier"]["verified"]),
            "sample_verified": bool(self.fixture["product"]["sample_verified"]),
            "real_test_order_completed": False,
            "real_test_return_completed": False,
            "external_checkout_enabled": False,
            "ready_for_real_sales": bool(
                self.fixture["supplier"]["verified"] and self.fixture["product"]["sample_verified"]
            ) and False,
        }

    def snapshot(self) -> dict:
        with self.connection() as db:
            inventory = [dict(r) for r in db.execute("SELECT * FROM inventory ORDER BY sku")]
            orders = [dict(r) for r in db.execute("SELECT * FROM orders ORDER BY created_at,id")]
            returns = [dict(r) for r in db.execute("SELECT * FROM returns ORDER BY created_at,id")]
            ledger = [dict(r) for r in db.execute("SELECT * FROM ledger ORDER BY id")]
        return {
            "schema_version": SCHEMA_VERSION,
            "fixture": self.fixture,
            "gates": self.gates(),
            "unit_economics": economics(self.fixture),
            "inventory": inventory,
            "orders": orders,
            "returns": returns,
            "ledger": ledger,
        }

    def place_order(self, idem_key: str, units: int = 1) -> dict:
        idem_key = require_text(idem_key, "idempotency key", 120)
        units = quantity(units)
        sku = self.fixture["product"]["sku"]
        with self.connection(write=True) as db:
            existing = db.execute("SELECT * FROM orders WHERE idem_key=?", (idem_key,)).fetchone()
            if existing:
                return dict(existing)
            inv = self._inventory(db, sku)
            available = inv["on_hand"] - inv["reserved"]
            if units > available:
                raise ValueError(f"insufficient stock: requested {units}, available {available}")
            oid = "O-" + hashlib.sha256((idem_key + sku).encode()).hexdigest()[:12]
            ts = now()
            econ = economics(self.fixture, units)
            db.execute(
                "INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?)",
                (oid, idem_key, sku, units, "placed", self.fixture["economics"]["price_cents"], canonical(econ), ts, ts),
            )
            db.execute("UPDATE inventory SET reserved=reserved+?,version=version+1 WHERE sku=?", (units, sku))
            db.execute(
                "INSERT INTO ledger(sku,kind,delta_on_hand,delta_reserved,ref,created_at) VALUES(?,?,?,?,?,?)",
                (sku, "order_reserved", 0, units, oid, ts),
            )
            return dict(db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone())

    def fulfill(self, order_id: str) -> dict:
        order_id = require_text(order_id, "order_id", 80)
        with self.connection(write=True) as db:
            row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if row is None:
                raise ValueError("unknown order")
            order = dict(row)
            if order["state"] == "fulfilled":
                return order
            if order["state"] != "placed":
                raise ValueError(f"order cannot be fulfilled from state {order['state']}")
            inv = self._inventory(db, order["sku"])
            if inv["reserved"] < order["quantity"] or inv["on_hand"] < order["quantity"]:
                raise ValueError("inventory reservation is inconsistent")
            ts = now()
            db.execute("UPDATE inventory SET on_hand=on_hand-?,reserved=reserved-?,version=version+1 WHERE sku=?",
                       (order["quantity"], order["quantity"], order["sku"]))
            db.execute("UPDATE orders SET state='fulfilled',updated_at=? WHERE id=?", (ts, order_id))
            db.execute(
                "INSERT INTO ledger(sku,kind,delta_on_hand,delta_reserved,ref,created_at) VALUES(?,?,?,?,?,?)",
                (order["sku"], "fulfilled", -order["quantity"], -order["quantity"], order_id, ts),
            )
            return dict(db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())

    def request_return(self, idem_key: str, order_id: str, reason: str) -> dict:
        idem_key = require_text(idem_key, "idempotency key", 120)
        order_id = require_text(order_id, "order_id", 80)
        reason = require_text(reason, "reason", 800)
        with self.connection(write=True) as db:
            by_key = db.execute("SELECT * FROM returns WHERE idem_key=?", (idem_key,)).fetchone()
            if by_key:
                return dict(by_key)
            old = db.execute("SELECT * FROM returns WHERE order_id=?", (order_id,)).fetchone()
            if old:
                return dict(old)
            order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if order is None:
                raise ValueError("unknown order")
            if order["state"] != "fulfilled":
                raise ValueError("only fulfilled orders can request a return")
            rid = "R-" + hashlib.sha256((idem_key + order_id).encode()).hexdigest()[:12]
            ts = now()
            db.execute("INSERT INTO returns VALUES(?,?,?,?,?,?,?,?)",
                       (rid, idem_key, order_id, reason, "requested", 0, ts, ts))
            db.execute("UPDATE orders SET state='return_requested',updated_at=? WHERE id=?", (ts, order_id))
            return dict(db.execute("SELECT * FROM returns WHERE id=?", (rid,)).fetchone())

    def complete_return(self, return_id: str, *, restock: bool) -> dict:
        return_id = require_text(return_id, "return_id", 80)
        if type(restock) is not bool:
            raise ValueError("restock must be boolean")
        with self.connection(write=True) as db:
            row = db.execute("SELECT * FROM returns WHERE id=?", (return_id,)).fetchone()
            if row is None:
                raise ValueError("unknown return")
            ret = dict(row)
            if ret["state"] == "completed":
                if bool(ret["restock"]) != restock:
                    raise ValueError("completed return cannot change restock decision")
                return ret
            order = db.execute("SELECT * FROM orders WHERE id=?", (ret["order_id"],)).fetchone()
            if order is None or order["state"] != "return_requested":
                raise ValueError("return/order state is inconsistent")
            ts = now()
            if restock:
                db.execute("UPDATE inventory SET on_hand=on_hand+?,version=version+1 WHERE sku=?",
                           (order["quantity"], order["sku"]))
                db.execute(
                    "INSERT INTO ledger(sku,kind,delta_on_hand,delta_reserved,ref,created_at) VALUES(?,?,?,?,?,?)",
                    (order["sku"], "return_restock", order["quantity"], 0, return_id, ts),
                )
            db.execute("UPDATE returns SET state='completed',restock=?,updated_at=? WHERE id=?",
                       (int(restock), ts, return_id))
            db.execute("UPDATE orders SET state='returned',updated_at=? WHERE id=?", (ts, order["id"]))
            return dict(db.execute("SELECT * FROM returns WHERE id=?", (return_id,)).fetchone())

    def export_json(self) -> bytes:
        return (json.dumps(self.snapshot(), indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()

    def export_handoff_csv(self) -> bytes:
        state = self.snapshot()
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(["order_id", "sku", "quantity", "state", "unit_price_cents", "contribution_cents"])
        for order in state["orders"]:
            econ = json.loads(order["economics_json"])
            writer.writerow([order["id"], order["sku"], order["quantity"], order["state"], order["price_cents"], econ["contribution_cents"]])
        return out.getvalue().encode()


def handler_for(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _send(self, status: int, data: bytes, mime: str):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: int, value):
            self._send(status, canonical(value).encode(), "application/json; charset=utf-8")

        def _body(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                raise ValueError("request too large")
            raw = self.rfile.read(length)
            value = json.loads(raw or b"{}")
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            return value

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == "/api/state":
                    self._json(200, store.snapshot()); return
                if path == "/api/export.json":
                    self._send(200, store.export_json(), "application/json; charset=utf-8"); return
                if path == "/api/handoff.csv":
                    self._send(200, store.export_handoff_csv(), "text/csv; charset=utf-8"); return
                if path == "/":
                    self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8"); return
                if path.startswith("/media/"):
                    rel = Path(path.lstrip("/"))
                    if rel.is_absolute() or ".." in rel.parts:
                        raise ValueError("invalid media path")
                    data = (HERE / rel).read_bytes()
                    self._send(200, data, mimetypes.guess_type(str(rel))[0] or "application/octet-stream"); return
                self._json(404, {"error": "not found"})
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})

        def do_POST(self):
            path = urlsplit(self.path).path
            try:
                body = self._body()
                if path == "/api/orders":
                    self._json(201, store.place_order(body.get("idempotency_key"), body.get("quantity", 1))); return
                if path == "/api/fulfill":
                    self._json(200, store.fulfill(body.get("order_id"))); return
                if path == "/api/returns":
                    self._json(201, store.request_return(body.get("idempotency_key"), body.get("order_id"), body.get("reason"))); return
                if path == "/api/returns/complete":
                    self._json(200, store.complete_return(body.get("return_id"), restock=body.get("restock"))); return
                self._json(404, {"error": "not found"})
            except (ValueError, OSError, json.JSONDecodeError, sqlite3.Error) as exc:
                self._json(409 if isinstance(exc, ValueError) else 500, {"error": str(exc)})

    return Handler


def serve(db: Path, fixture: Path, host: str, port: int):
    store = Store(db, fixture)
    server = ThreadingHTTPServer((host, port), handler_for(store))
    print(f"Focused storefront: http://{host}:{server.server_port}", flush=True)
    server.serve_forever()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("storefront.sqlite3"))
    parser.add_argument("--fixture", type=Path, default=HERE / "examples" / "synthetic-supplier.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    exp = sub.add_parser("export")
    exp.add_argument("destination", type=Path)
    srv = sub.add_parser("serve")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8097)
    args = parser.parse_args(argv)
    store = Store(args.db, args.fixture)
    if args.command == "init":
        print(canonical(store.snapshot()))
        return 0
    if args.command == "export":
        if args.destination.exists():
            raise SystemExit("refusing to overwrite existing export")
        args.destination.write_bytes(store.export_json())
        print(args.destination)
        return 0
    if args.command == "serve":
        serve(args.db, args.fixture, args.host, args.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
