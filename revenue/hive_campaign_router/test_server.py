# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

from app import make_server
from campaign_router import Store

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(db_path=Path(self.temp.name) / "server.db", port=0, access_log=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        parts = urlsplit(self.server.settings.public_base_url)
        self.host, self.port = parts.hostname, parts.port

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        body = None if payload is None else json.dumps(payload).encode()
        request_headers = dict(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        result = response.status, {key.lower(): value for key, value in response.getheaders()}, raw
        connection.close()
        return result

    @staticmethod
    def json(raw):
        return json.loads(raw.decode())

    def seed(self):
        product = self.json(self.request("POST", "/api/products", {"name": "Kit", "brand": "Northstar"})[2])
        offer = self.json(self.request("POST", "/api/offers", {
            "product_id": product["id"], "name": "Main", "headline": "A measured launch",
            "body": "Keep one URL.", "cta_label": "Continue",
        })[2])
        preset = self.json(self.request("POST", "/api/presets", {
            "name": "YouTube", "utm_source": "youtube", "utm_medium": "video",
            "utm_campaign": "kit-launch", "utm_content": "description", "utm_term": "",
        })[2])
        link = self.json(self.request("POST", "/api/links", {
            "slug": "kit-youtube", "product_id": product["id"], "offer_id": offer["id"],
            "preset_id": preset["id"], "destination": "https://example.com/v1", "route_mode": "offer",
        })[2])
        return product, offer, preset, link

    def test_health_and_security_headers(self):
        status, headers, raw = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(self.json(raw)["ok"])
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])

    def test_static_customer_dashboard(self):
        status, _, raw = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"RouteFoundry", raw)
        self.assertIn(b"Create campaign link", raw)
        self.assertEqual(self.request("GET", "/static/app.js")[0], 200)

    def test_offer_click_and_conversion_are_attributed(self):
        self.seed()
        status, _, offer = self.request("GET", "/r/kit-youtube", headers={"Referer": "https://creator.example/video"})
        self.assertEqual(status, 200)
        self.assertIn(b"A measured launch", offer)
        state = self.json(self.request("GET", "/api/state")[2])
        click = state["recent_events"][0]
        self.assertEqual(click["event_type"], "click")
        self.assertEqual(click["referrer_host"], "creator.example")
        status, headers, _ = self.request("GET", f"/convert/kit-youtube?click={click['event_id']}")
        self.assertEqual(status, 302)
        self.assertIn("utm_campaign=kit-launch", headers["location"])
        report = self.json(self.request("GET", "/api/report")[2])
        self.assertEqual(report["campaigns"][0]["clicks"], 1)
        self.assertEqual(report["campaigns"][0]["conversions"], 1)

    def test_direct_redirect_has_utm(self):
        product, offer, preset, _ = self.seed()
        status, _, raw = self.request("POST", "/api/links", {
            "slug": "kit-direct", "product_id": product["id"], "offer_id": offer["id"],
            "preset_id": preset["id"], "destination": "https://example.com/buy?plan=agency", "route_mode": "redirect",
        })
        self.assertEqual(status, 201, raw)
        status, headers, _ = self.request("GET", "/r/kit-direct")
        self.assertEqual(status, 302)
        query = parse_qs(urlsplit(headers["location"]).query)
        self.assertEqual(query["plan"], ["agency"])
        self.assertEqual(query["utm_source"], ["youtube"])

    def test_destination_edit_keeps_qr_bytes(self):
        self.seed()
        before = self.request("GET", "/q/kit-youtube.svg")[2]
        status, _, raw = self.request("PATCH", "/api/links/kit-youtube", {"destination": "https://example.com/v2"})
        self.assertEqual(status, 200, raw)
        after = self.request("GET", "/q/kit-youtube.svg")[2]
        self.assertEqual(before, after)
        state = self.json(self.request("GET", "/api/state")[2])
        self.assertEqual(state["links"][0]["destination"], "https://example.com/v2")

    def test_head_does_not_log_click_or_conversion(self):
        self.seed()
        self.assertEqual(self.request("HEAD", "/r/kit-youtube")[0], 200)
        self.assertEqual(self.request("HEAD", "/convert/kit-youtube")[0], 302)
        state = self.json(self.request("GET", "/api/state")[2])
        self.assertEqual(state["recent_events"], [])

    def test_event_api_deduplicates(self):
        self.seed()
        payload = {"slug": "kit-youtube", "event_type": "conversion", "event_id": "manual_123456"}
        first = self.request("POST", "/api/events", payload)
        second = self.request("POST", "/api/events", payload)
        self.assertEqual((first[0], second[0]), (201, 200))
        self.assertTrue(self.json(first[2])["created"])
        self.assertFalse(self.json(second[2])["created"])

    def test_bad_json_and_unsafe_redirect_return_400(self):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request("POST", "/api/products", body=b"not-json", headers={"Content-Type": "application/json"})
        response = connection.getresponse(); raw = response.read(); connection.close()
        self.assertEqual(response.status, 400)
        self.assertEqual(self.json(raw)["error"], "validation_error")
        product = self.json(self.request("POST", "/api/products", {"name": "P", "brand": "B"})[2])
        status, _, raw = self.request("POST", "/api/links", {
            "slug": "unsafe-link", "product_id": product["id"], "offer_id": None, "preset_id": None,
            "destination": "http://127.0.0.1/private", "route_mode": "redirect",
        })
        self.assertEqual(status, 400)
        self.assertIn("https", self.json(raw)["message"])

    def test_paused_link_returns_not_found(self):
        self.seed()
        self.assertEqual(self.request("PATCH", "/api/links/kit-youtube", {"active": False})[0], 200)
        self.assertEqual(self.request("GET", "/r/kit-youtube")[0], 404)
        self.assertEqual(self.request("GET", "/q/kit-youtube.svg")[0], 200)

    def test_export_download_has_complete_workspace(self):
        self.seed()
        self.request("GET", "/r/kit-youtube")
        status, headers, raw = self.request("GET", "/api/export")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["content-disposition"])
        payload = self.json(raw)
        self.assertEqual(len(payload["products"]), 1)
        self.assertEqual(len(payload["events"]), 1)

    def test_done_flow_creates_three_links_for_one_product(self):
        product, offer, _, first = self.seed()
        for number, source in ((2, "newsletter"), (3, "partner")):
            preset = self.json(self.request("POST", "/api/presets", {
                "name": source.title(), "utm_source": source, "utm_medium": "referral",
                "utm_campaign": "kit-launch", "utm_content": f"placement-{number}", "utm_term": "",
            })[2])
            status, _, raw = self.request("POST", "/api/links", {
                "slug": f"kit-channel-{number}", "product_id": product["id"], "offer_id": offer["id"],
                "preset_id": preset["id"], "destination": "https://example.com/v1", "route_mode": "offer",
            })
            self.assertEqual(status, 201, raw)
        state = self.json(self.request("GET", "/api/state")[2])
        self.assertEqual(len(state["links"]), 3)
        self.assertEqual({row["product_id"] for row in state["links"]}, {product["id"]})
        self.assertEqual(first["product_id"], product["id"])


class PublicOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "public.db"
        store = Store(self.db)
        product = store.create_product({"name": "Public", "brand": "Northstar"})
        offer = store.create_offer({
            "product_id": product["id"], "name": "Offer", "headline": "Public offer",
            "body": "Safe public route.", "cta_label": "Continue",
        })
        preset = store.create_preset({
            "name": "X", "utm_source": "x", "utm_medium": "social",
            "utm_campaign": "public-launch", "utm_content": "post", "utm_term": "",
        })
        store.create_link({
            "slug": "public-link", "product_id": product["id"], "offer_id": offer["id"],
            "preset_id": preset["id"], "destination": "https://example.com/public", "route_mode": "offer",
        })
        self.server = make_server(db_path=self.db, port=0, public_only=True, access_log=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self):
        self.server.shutdown(); self.thread.join(timeout=5); self.server.server_close(); self.temp.cleanup()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        body = None if payload is None else json.dumps(payload).encode()
        connection.request(method, path, body=body, headers={"Content-Type": "application/json"} if body else {})
        response = connection.getresponse(); raw = response.read(); connection.close()
        return response.status, raw

    def test_public_routes_work_while_admin_surface_is_hidden(self):
        self.assertEqual(self.request("GET", "/health")[0], 200)
        self.assertEqual(self.request("GET", "/r/public-link")[0], 200)
        self.assertEqual(self.request("GET", "/q/public-link.svg")[0], 200)
        self.assertEqual(self.request("GET", "/static/styles.css")[0], 200)
        self.assertEqual(self.request("GET", "/")[0], 404)
        self.assertEqual(self.request("GET", "/api/state")[0], 404)
        self.assertEqual(self.request("GET", "/static/app.js")[0], 404)

    def test_public_only_rejects_admin_writes(self):
        status, _ = self.request("POST", "/api/products", {"name": "No", "brand": "No"})
        self.assertEqual(status, 404)
        status, _ = self.request("PATCH", "/api/links/public-link", {"active": False})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
