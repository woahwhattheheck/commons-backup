# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest

from campaign_router import Store, ValidationError, short_url

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "workspace.db")

    def tearDown(self):
        self.temp.cleanup()

    def seed(self):
        product = self.store.create_product({"name": "Creator Kit", "brand": "Northstar"})
        offer = self.store.create_offer({
            "product_id": product["id"], "name": "Launch", "headline": "Ship it",
            "body": "A complete offer.", "cta_label": "Buy",
        })
        preset = self.store.create_preset({
            "name": "YouTube", "utm_source": "youtube", "utm_medium": "video",
            "utm_campaign": "creator-launch", "utm_content": "description", "utm_term": "",
        })
        link = self.store.create_link({
            "slug": "creator-youtube", "product_id": product["id"], "offer_id": offer["id"],
            "preset_id": preset["id"], "destination": "https://example.com/v1", "route_mode": "offer",
        })
        return product, offer, preset, link

    def test_complete_data_model(self):
        product, offer, preset, link = self.seed()
        joined = self.store.get_link("creator-youtube")
        self.assertEqual(joined["product_name"], product["name"])
        self.assertEqual(joined["headline"], offer["headline"])
        self.assertEqual(joined["utm_campaign"], preset["utm_campaign"])
        self.assertEqual(link["slug"], "creator-youtube")

    def test_offer_must_belong_to_product(self):
        p1, offer, preset, _ = self.seed()
        p2 = self.store.create_product({"name": "Other", "brand": "Other"})
        with self.assertRaises(ValidationError):
            self.store.create_link({
                "slug": "other-link", "product_id": p2["id"], "offer_id": offer["id"],
                "preset_id": preset["id"], "destination": "https://example.com", "route_mode": "offer",
            })
        self.assertNotEqual(p1["id"], p2["id"])

    def test_offer_route_requires_offer(self):
        product = self.store.create_product({"name": "P", "brand": "B"})
        with self.assertRaises(ValidationError):
            self.store.create_link({
                "slug": "missing-offer", "product_id": product["id"], "offer_id": None,
                "preset_id": None, "destination": "https://example.com", "route_mode": "offer",
            })

    def test_destination_edit_keeps_slug_and_short_url(self):
        _, _, _, link = self.seed()
        before = short_url("https://go.example.com", link["slug"])
        updated = self.store.update_link(link["slug"], {"destination": "https://example.com/v2?plan=pro"})
        after = short_url("https://go.example.com", updated["slug"])
        self.assertEqual(before, after)
        self.assertEqual(updated["destination"], "https://example.com/v2?plan=pro")

    def test_duplicate_slug_and_preset_rejected(self):
        product, offer, preset, _ = self.seed()
        with self.assertRaises(ValidationError):
            self.store.create_preset({
                "name": preset["name"], "utm_source": "x", "utm_medium": "social",
                "utm_campaign": "other",
            })
        with self.assertRaises(ValidationError):
            self.store.create_link({
                "slug": "creator-youtube", "product_id": product["id"], "offer_id": offer["id"],
                "preset_id": preset["id"], "destination": "https://example.com", "route_mode": "offer",
            })

    def test_event_id_is_idempotent(self):
        self.seed()
        first = self.store.record_event("creator-youtube", "conversion", requested_event_id="conversion_0001")
        second = self.store.record_event("creator-youtube", "conversion", requested_event_id="conversion_0001")
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        report = self.store.report()
        self.assertEqual(report["campaigns"][0]["conversions"], 1)

    def test_concurrent_event_deduplication(self):
        self.seed()
        outcomes = []
        lock = threading.Lock()
        def record():
            result = self.store.record_event("creator-youtube", "click", requested_event_id="concurrent_0001")
            with lock:
                outcomes.append(result.created)
        threads = [threading.Thread(target=record) for _ in range(12)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 11)

    def test_report_uses_preset_and_referrer_hostname_only(self):
        self.seed()
        self.store.record_event("creator-youtube", "click", requested_event_id="referrer_0001",
                                referrer="https://creator.example/path?q=secret")
        state = self.store.list_state("https://go.example.com")
        self.assertEqual(state["recent_events"][0]["referrer_host"], "creator.example")
        self.assertEqual(state["recent_events"][0]["utm_source"], "youtube")
        self.assertNotIn("secret", json.dumps(state))

    def test_inactive_link_rejects_event_but_remains_editable(self):
        self.seed()
        self.store.update_link("creator-youtube", {"active": False})
        with self.assertRaises(KeyError):
            self.store.record_event("creator-youtube", "click")
        self.assertFalse(bool(self.store.get_link("creator-youtube")["active"]))

    def test_export_contains_workspace_without_ip_fields(self):
        self.seed()
        self.store.record_event("creator-youtube", "click", requested_event_id="exported_0001")
        payload = json.loads(self.store.export_json())
        self.assertEqual(payload["schema"], "routefoundry.export.v1")
        self.assertEqual(len(payload["links"]), 1)
        keys = set()
        def collect(value):
            if isinstance(value, dict):
                keys.update(value)
                for item in value.values(): collect(item)
            elif isinstance(value, list):
                for item in value: collect(item)
        collect(payload)
        self.assertTrue({"ip", "ip_address", "remote_addr"}.isdisjoint(keys))

    def test_update_rejects_unknown_fields(self):
        self.seed()
        with self.assertRaises(ValidationError):
            self.store.update_link("creator-youtube", {"slug": "replacement"})

    def test_parent_click_and_event_id_binding(self):
        product, offer, preset, _ = self.seed()
        self.store.create_link({
            "slug": "creator-second", "product_id": product["id"], "offer_id": offer["id"],
            "preset_id": preset["id"], "destination": "https://example.com/v2", "route_mode": "offer",
        })
        click = self.store.record_event("creator-youtube", "click", requested_event_id="parent_click_0001")
        conversion = self.store.record_event(
            "creator-youtube", "conversion", requested_event_id="conversion_parent_0001",
            parent_event_id=click.event_id,
        )
        self.assertTrue(conversion.created)
        with self.assertRaises(ValidationError):
            self.store.record_event(
                "creator-second", "conversion", requested_event_id="wrong_parent_0001",
                parent_event_id=click.event_id,
            )
        with self.assertRaises(ValidationError):
            self.store.record_event("creator-youtube", "click", requested_event_id="conversion_parent_0001")




if __name__ == "__main__":
    unittest.main(verbosity=2)
