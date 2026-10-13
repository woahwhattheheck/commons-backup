#!/usr/bin/env python3
"""Cross-product acceptance for Brand Launch Ops -> Shop Operations Desk.

This is deliberately test/evidence only. It imports the landed sibling runtimes,
uses synthetic fixtures, and never sends inventory, orders, refunds, or messages
to an external provider.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launch = load_module("brand_launch_ops_runtime", HERE / "launch_ops.py")
shop = load_module("shop_operations_runtime", HERE.parent / "shop-operations" / "shop_ops.py")


class BrandLaunchShopOpsIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.product = {
            "sku": "SYN-TOTE-001",
            "name": "Synthetic Field Tote",
            "description": "Synthetic zip-top canvas tote used only for local acceptance.",
            "price_cents": 3200,
            "currency": "USD",
            "stock": 12,
            "reorder_at": 3,
            "shipping_terms": "Synthetic acceptance fixture; no shipment is created.",
            "return_days": 30,
            "support_contact": "support@example.invalid",
            "attributes": {
                "material": "12 oz cotton canvas",
                "color": "natural",
                "closure": "zip top",
            },
            "benefits": [
                "Zip-top closure keeps everyday items contained.",
                "Interior pocket separates small essentials.",
            ],
            "creative_constraints": [
                "Do not claim waterproofing, load rating, scarcity, or endorsement."
            ],
            "channels": ["web", "creator_shop", "marketplace"],
        }
        self.launch_dir = self.root / "launch"
        self.manifest = launch.build(self.product, self.launch_dir)
        self.store = shop.Store(self.root / "shop.sqlite3")
        evidence = self.manifest["source_sha256"]
        self.shop_product = {
            "sku": self.product["sku"],
            "version": 0,
            "title": self.product["name"],
            "description": self.product["description"],
            "source_url": f"https://maker.example.invalid/source/{evidence}",
            "uncertainties": "",
            "price_minor": self.product["price_cents"],
            "currency": self.product["currency"],
            "listing_state": "ready",
        }
        self.exec_op("product-v1", "product", self.shop_product)
        self.exec_op(
            "receive-v1",
            "receive",
            {
                "sku": self.product["sku"],
                "quantity": self.product["stock"],
                "reference": f"launch:{evidence}",
            },
        )

    def tearDown(self):
        self.temp.cleanup()

    def exec_op(self, key, action, data):
        return self.store.execute({"key": key, "action": action, "data": data})

    def product_row(self):
        rows = self.store.snapshot()["products"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def reorder_projection(self):
        row = self.product_row()
        return launch.inventory(
            {
                "sku": row["sku"],
                "available": row["available"],
                "reorder_at": self.product["reorder_at"],
            }
        )

    def test_source_truth_and_publication_boundary_survive_handoff(self):
        source_bytes = (self.launch_dir / "product_source.json").read_bytes()
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), self.manifest["source_sha256"])

        listings = json.loads((self.launch_dir / "listings.json").read_text())
        for channel in self.product["channels"]:
            listing = listings["listings"][channel]
            self.assertEqual(listing["sku"], self.product["sku"])
            self.assertEqual(listing["attributes"], self.product["attributes"])
            self.assertEqual(listing["benefits"], self.product["benefits"])
            self.assertEqual(listing["source"], "operator_supplied")

        handoff = json.loads((self.launch_dir / "inventory_handoff.json").read_text())
        self.assertEqual(handoff["source_available"], self.product["stock"])
        self.assertTrue(all(v["publication"] == "NOT_SENT" for v in handoff["channels"].values()))

        row = self.product_row()
        self.assertEqual(row["sku"], self.product["sku"])
        self.assertEqual(row["title"], self.product["name"])
        self.assertEqual(row["description"], self.product["description"])
        self.assertEqual(row["price_minor"], self.product["price_cents"])
        self.assertEqual(row["currency"], self.product["currency"])
        self.assertTrue(row["source_url"].endswith(self.manifest["source_sha256"]))

    def test_order_fulfill_return_drives_reorder_from_shop_inventory(self):
        order = {
            "id": "order-001",
            "kind": "sale",
            "recipient_ref": "synthetic-recipient",
            "lines": [{"sku": self.product["sku"], "quantity": 10}],
        }
        first = self.exec_op("order-op-001", "order", order)
        replay = self.exec_op("order-op-001", "order", order)
        self.assertEqual(first, replay)
        self.assertEqual(self.product_row()["available"], 2)
        self.assertTrue(self.reorder_projection()["reorder_needed"])

        fulfill = {"id": "order-001", "shipment_ref": "synthetic-shipment"}
        first_fulfill = self.exec_op("fulfill-op-001", "fulfill", fulfill)
        self.assertEqual(first_fulfill, self.exec_op("fulfill-op-001", "fulfill", fulfill))
        self.assertEqual(self.product_row()["on_hand"], 2)
        self.assertEqual(self.product_row()["reserved"], 0)
        self.assertTrue(self.reorder_projection()["reorder_needed"])

        returned = {
            "id": "return-001",
            "order_id": "order-001",
            "sku": self.product["sku"],
            "quantity": 2,
            "restock": True,
            "note": "synthetic inspection accepted",
        }
        first_return = self.exec_op("return-op-001", "return", returned)
        self.assertEqual(first_return, self.exec_op("return-op-001", "return", returned))
        self.assertEqual(self.product_row()["on_hand"], 4)
        self.assertFalse(self.reorder_projection()["reorder_needed"])

        reasons = [m["reason"] for m in self.store.snapshot()["movements"]]
        self.assertEqual(reasons.count("receipt"), 1)
        self.assertEqual(reasons.count("reserve"), 1)
        self.assertEqual(reasons.count("fulfill"), 1)
        self.assertEqual(reasons.count("return"), 1)

    def test_conflicting_retry_cannot_mutate_inventory(self):
        original = {
            "id": "order-conflict",
            "kind": "sale",
            "recipient_ref": "synthetic-recipient",
            "lines": [{"sku": self.product["sku"], "quantity": 2}],
        }
        self.exec_op("order-op-conflict", "order", original)
        before = self.store.snapshot()
        changed = dict(original)
        changed["lines"] = [{"sku": self.product["sku"], "quantity": 3}]
        with self.assertRaises(shop.DomainError) as caught:
            self.exec_op("order-op-conflict", "order", changed)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.store.snapshot(), before)

    def test_launch_rehearsal_state_is_not_used_as_second_live_inventory(self):
        launch_state = json.loads((self.launch_dir / "state.json").read_text())
        self.assertEqual(launch_state["available"], 12)
        self.exec_op(
            "shop-order-only",
            "order",
            {
                "id": "shop-order-only",
                "kind": "sale",
                "recipient_ref": "synthetic-recipient",
                "lines": [{"sku": self.product["sku"], "quantity": 1}],
            },
        )
        self.assertEqual(self.product_row()["available"], 11)
        self.assertEqual(json.loads((self.launch_dir / "state.json").read_text()), launch_state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
