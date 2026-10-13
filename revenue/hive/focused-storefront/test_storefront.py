from __future__ import annotations
import concurrent.futures
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import storefront


class StorefrontTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = storefront.HERE / "examples" / "synthetic-supplier.json"
        self.db = self.root / "store.sqlite3"
        self.store = storefront.Store(self.db, self.fixture)

    def test_fixture_hash_media_hash_and_open_gates(self):
        state = self.store.snapshot()
        self.assertEqual("synthetic", state["fixture"]["fixture_kind"])
        self.assertEqual(64, len(state["fixture"]["fixture_sha256"]))
        self.assertEqual(64, len(state["fixture"]["media"][0]["sha256"]))
        self.assertTrue(all(v is False for v in state["gates"].values()))

    def test_unit_economics_math(self):
        e = self.store.snapshot()["unit_economics"]
        self.assertEqual(1499, e["gross_revenue_cents"])
        self.assertEqual(75, e["channel_fee_cents"])
        self.assertEqual(754, e["contribution_cents"])

    def test_order_fulfill_return_restock_conserves_stock(self):
        start = self.store.snapshot()["inventory"][0]["on_hand"]
        order = self.store.place_order("place-1", 2)
        self.assertEqual(2, self.store.snapshot()["inventory"][0]["reserved"])
        self.store.fulfill(order["id"])
        self.assertEqual(start - 2, self.store.snapshot()["inventory"][0]["on_hand"])
        ret = self.store.request_return("return-1", order["id"], "synthetic return")
        self.store.complete_return(ret["id"], restock=True)
        state = self.store.snapshot()
        self.assertEqual(start, state["inventory"][0]["on_hand"])
        self.assertEqual(0, state["inventory"][0]["reserved"])
        self.assertEqual("returned", state["orders"][0]["state"])

    def test_order_idempotency_reserves_once(self):
        first = self.store.place_order("same", 3)
        second = self.store.place_order("same", 3)
        self.assertEqual(first, second)
        state = self.store.snapshot()
        self.assertEqual(1, len(state["orders"]))
        self.assertEqual(3, state["inventory"][0]["reserved"])

    def test_concurrent_order_claims_never_oversell(self):
        def attempt(i):
            try:
                return self.store.place_order(f"order-{i}", 2)["id"]
            except ValueError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(12)))
        winners = [r for r in results if r]
        state = self.store.snapshot()
        self.assertEqual(6, len(winners))
        self.assertEqual(12, state["inventory"][0]["reserved"])
        self.assertEqual(0, state["inventory"][0]["on_hand"] - state["inventory"][0]["reserved"])

    def test_return_idempotency_and_decision_immutability(self):
        order = self.store.place_order("place", 1)
        self.store.fulfill(order["id"])
        a = self.store.request_return("return", order["id"], "reason")
        b = self.store.request_return("return", order["id"], "reason")
        self.assertEqual(a, b)
        done = self.store.complete_return(a["id"], restock=False)
        self.assertEqual(done, self.store.complete_return(a["id"], restock=False))
        with self.assertRaises(ValueError):
            self.store.complete_return(a["id"], restock=True)

    def test_existing_db_refuses_fixture_drift(self):
        altered = self.root / "altered.json"
        doc = json.loads(self.fixture.read_text())
        doc["shipping_terms"] += " changed"
        altered.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "fixture hash"):
            storefront.Store(self.db, altered)

    def test_export_reopens_with_same_state(self):
        order = self.store.place_order("place", 1)
        self.store.fulfill(order["id"])
        expected = json.loads(self.store.export_json())
        reopened = storefront.Store(self.db, self.fixture)
        actual = json.loads(reopened.export_json())
        self.assertEqual(expected, actual)
        csv_bytes = reopened.export_handoff_csv()
        self.assertIn(order["id"].encode(), csv_bytes)
        self.assertIn(b"fulfilled", csv_bytes)

    def test_reject_return_before_fulfillment(self):
        order = self.store.place_order("place", 1)
        with self.assertRaisesRegex(ValueError, "fulfilled"):
            self.store.request_return("ret", order["id"], "too soon")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = storefront.Store(root / "http.sqlite3", storefront.HERE / "examples" / "synthetic-supplier.json")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), storefront.handler_for(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def request(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as response:
            return response.code, response.read(), response.headers

    def test_http_real_process_order_return_and_exports(self):
        status, body, _ = self.request("/api/state")
        self.assertEqual(200, status)
        self.assertFalse(json.loads(body)["gates"]["ready_for_real_sales"])
        status, body, _ = self.request("/api/orders", {"idempotency_key": "web-order", "quantity": 1})
        self.assertEqual(201, status); order = json.loads(body)
        self.assertEqual(200, self.request("/api/fulfill", {"order_id": order["id"]})[0])
        status, body, _ = self.request("/api/returns", {"idempotency_key": "web-ret", "order_id": order["id"], "reason": "synthetic"})
        self.assertEqual(201, status); ret = json.loads(body)
        self.assertEqual(200, self.request("/api/returns/complete", {"return_id": ret["id"], "restock": True})[0])
        self.assertIn(order["id"].encode(), self.request("/api/handoff.csv")[1])
        self.assertIn(b"fixture_sha256", self.request("/api/export.json")[1])

    def test_http_duplicate_order_and_stock_conflict(self):
        first = json.loads(self.request("/api/orders", {"idempotency_key": "same", "quantity": 12})[1])
        second = json.loads(self.request("/api/orders", {"idempotency_key": "same", "quantity": 12})[1])
        self.assertEqual(first["id"], second["id"])
        status, body, _ = self.request("/api/orders", {"idempotency_key": "other", "quantity": 1})
        self.assertEqual(409, status)
        self.assertIn(b"insufficient stock", body)

    def test_http_serves_original_media_and_page(self):
        status, page, _ = self.request("/")
        self.assertEqual(200, status)
        self.assertIn(b"Supplier/sample gate is open", page)
        status, media, _ = self.request("/media/synthetic-cable-clip.svg")
        self.assertEqual(200, status)
        self.assertEqual(storefront.sha256_bytes(media), self.store.fixture["media"][0]["sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
