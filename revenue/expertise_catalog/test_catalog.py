from __future__ import annotations

import copy
import json
import unittest

from revenue.expertise_catalog.catalog import CatalogError, compile_catalog, verify_catalog

COMMIT = "1" * 40
DIGEST = "a" * 64


def _canonical_digest(value):
    import hashlib
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def offer(offer_id: str = "agent-architecture-review", *, price_cents: int = 125_00):
    return {
        "offer_id": offer_id,
        "version": "1.0.0",
        "title": "Agent architecture review",
        "summary": "Evidence-bound architecture assessment with a written findings packet and bounded recommendations.",
        "deliverable_type": "DESIGN_REVIEW",
        "currency": "USD",
        "price_cents": price_cents,
        "valid_from": "2026-09-01T00:00:00Z",
        "valid_until": "2026-10-01T00:00:00Z",
        "delivery_window_days": 3,
        "source": {
            "repository": "woahwhattheheck/commons",
            "commit": COMMIT,
            "path": "revenue/OFFERING_FAMILIES.md",
            "sha256": DIGEST,
        },
        "evidence": [
            {
                "evidence_id": "architecture-demo",
                "kind": "CAPABILITY_DEMO",
                "repository": "woahwhattheheck/commons",
                "commit": COMMIT,
                "path": "revenue/agent_ops/README.md",
                "sha256": "b" * 64,
            },
            {
                "evidence_id": "receipt-sample",
                "kind": "DELIVERY_RECEIPT",
                "repository": "woahwhattheheck/commons",
                "commit": COMMIT,
                "path": "revenue/scope_to_delivery/README.md",
                "sha256": "c" * 64,
            },
        ],
        "scope": {
            "included": ["Architecture findings packet", "One prioritized recommendation matrix"],
            "excluded": ["Production deployment", "Contract signature", "Provider spend"],
        },
    }


class CatalogTests(unittest.TestCase):
    def compile(self, offers):
        return compile_catalog(offers, as_of="2026-09-13T10:00:00Z")

    def test_ready_offer_and_authority_ceiling(self):
        result = self.compile([offer()])
        self.assertTrue(verify_catalog(result.manifest, result.markdown))
        self.assertEqual(result.manifest["counts"], {"total": 1, "review_packet_ready": 1, "hold": 0})
        item = result.manifest["offers"][0]
        self.assertEqual(item["status"], "CATALOG_REVIEW_PACKET_READY")
        self.assertFalse(item["publication_authorized"])
        self.assertFalse(item["checkout_or_payment_authorized"])
        self.assertFalse(item["revenue_recognized"])

    def test_order_is_deterministic(self):
        a = offer("zeta-review")
        b = offer("alpha-review")
        first = self.compile([a, b])
        second = self.compile([b, a])
        self.assertEqual(first.manifest["offers"], second.manifest["offers"])
        self.assertEqual(first.markdown, second.markdown)
        self.assertEqual(first.manifest["input_digest"], second.manifest["input_digest"])

    def test_exact_duplicate_collapses(self):
        item = offer()
        result = self.compile([item, copy.deepcopy(item)])
        self.assertEqual(result.manifest["counts"]["total"], 1)

    def test_conflicting_duplicate_fails_closed(self):
        a = offer()
        b = offer()
        b["price_cents"] += 1
        with self.assertRaisesRegex(CatalogError, "conflicting duplicate"):
            self.compile([a, b])

    def test_unknown_field_rejected(self):
        item = offer()
        item["autopublish"] = True
        with self.assertRaisesRegex(CatalogError, "unknown fields"):
            self.compile([item])

    def test_noncanonical_timestamp_rejected(self):
        item = offer()
        item["valid_until"] = "2026-10-01T00:00:00+00:00"
        with self.assertRaisesRegex(CatalogError, "canonical UTC"):
            self.compile([item])

    def test_expired_offer_is_hold(self):
        item = offer()
        item["valid_until"] = "2026-09-13T09:59:59Z"
        result = self.compile([item])
        self.assertEqual(result.manifest["offers"][0]["status"], "HOLD")
        self.assertEqual(result.manifest["offers"][0]["hold_reasons"], ["EXPIRED"])

    def test_not_yet_active_offer_is_hold(self):
        item = offer()
        item["valid_from"] = "2026-09-14T00:00:00Z"
        item["valid_until"] = "2026-10-14T00:00:00Z"
        result = self.compile([item])
        self.assertEqual(result.manifest["offers"][0]["hold_reasons"], ["NOT_YET_ACTIVE"])

    def test_secret_shaped_text_rejected(self):
        item = offer()
        item["summary"] = "Use sk-proj-abcdefghijklmnop for the demo"
        with self.assertRaisesRegex(CatalogError, "secret-shaped"):
            self.compile([item])

    def test_email_pii_rejected(self):
        item = offer()
        item["scope"]["included"].append("Contact buyer@example.com after review")
        with self.assertRaisesRegex(CatalogError, "PII-shaped"):
            self.compile([item])

    def test_path_traversal_rejected(self):
        item = offer()
        item["source"]["path"] = "revenue/../secret.txt"
        with self.assertRaisesRegex(CatalogError, "traversal"):
            self.compile([item])

    def test_commit_must_be_full_pin(self):
        item = offer()
        item["source"]["commit"] = "deadbeef"
        with self.assertRaisesRegex(CatalogError, "40-hex"):
            self.compile([item])

    def test_money_must_be_json_safe_integer(self):
        item = offer(price_cents=9_007_199_254_740_992)
        with self.assertRaisesRegex(CatalogError, "JSON-safe integer"):
            self.compile([item])
        item = offer()
        item["price_cents"] = 125.00
        with self.assertRaisesRegex(CatalogError, "JSON-safe integer"):
            self.compile([item])

    def test_conflicting_evidence_id_rejected(self):
        item = offer()
        duplicate = copy.deepcopy(item["evidence"][0])
        duplicate["path"] = "revenue/other/README.md"
        item["evidence"].append(duplicate)
        with self.assertRaisesRegex(CatalogError, "conflicting duplicate evidence_id"):
            self.compile([item])

    def test_scope_overlap_rejected(self):
        item = offer()
        item["scope"]["excluded"].append("Architecture findings packet")
        with self.assertRaisesRegex(CatalogError, "overlap"):
            self.compile([item])

    def test_manifest_tamper_rejected(self):
        result = self.compile([offer()])
        tampered = copy.deepcopy(result.manifest)
        tampered["offers"][0]["price_cents"] += 1
        self.assertFalse(verify_catalog(tampered, result.markdown))

    def test_recomputed_derived_field_tamper_rejected(self):
        result = self.compile([offer()])
        tampered = copy.deepcopy(result.manifest)
        tampered["counts"]["hold"] = 1
        tampered["catalog_digest"] = _canonical_digest(
            {key: value for key, value in tampered.items() if key != "catalog_digest"}
        )
        self.assertFalse(verify_catalog(tampered))

    def test_expected_digest_binds_coherent_catalog_rewrite(self):
        original = self.compile([offer(price_cents=12500)])
        rewritten = self.compile([offer(price_cents=12600)])
        self.assertTrue(verify_catalog(rewritten.manifest, rewritten.markdown))
        self.assertFalse(
            verify_catalog(
                rewritten.manifest,
                rewritten.markdown,
                expected_catalog_digest=original.manifest["catalog_digest"],
            )
        )
        self.assertTrue(
            verify_catalog(
                original.manifest,
                original.markdown,
                expected_catalog_digest=original.manifest["catalog_digest"],
            )
        )

    def test_markdown_tamper_rejected(self):
        result = self.compile([offer()])
        self.assertFalse(verify_catalog(result.manifest, result.markdown + "tamper\n"))

    def test_large_exact_money_rendering_has_no_float_drift(self):
        cents = 9_007_199_254_740_991
        result = self.compile([offer(price_cents=cents)])
        self.assertIn("$90,071,992,547,409.91 USD", result.markdown)
        self.assertNotIn(".92 USD", result.markdown)

    def test_receipt_is_json_serializable_without_nan(self):
        result = self.compile([offer()])
        encoded = json.dumps(result.manifest, allow_nan=False, sort_keys=True)
        self.assertIn('"schema": "commons.expertise-catalog/v1"', encoded)


if __name__ == "__main__":
    unittest.main()
