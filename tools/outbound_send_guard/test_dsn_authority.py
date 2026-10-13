from __future__ import annotations

import copy
import unittest

from tools.outbound_send_guard import dsn_authority as authority
from tools.outbound_send_guard import dsn_normalizer as dsn
from tools.outbound_send_guard.test_dsn_normalizer import binding, raw_dsn


def _refresh_attacker_hashes(receipt):
    receipt["event_sha256"] = dsn.sha256_json(receipt["event"])
    material = dict(receipt)
    material.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = dsn.sha256_json(material)


def _refresh_event_id(receipt):
    event = receipt["event"]
    identity = {
        "source_id": event["source_id"],
        "provider_message_id": event["provider_message_id"],
        "recipient": event["recipient"],
        "original_rfc822_message_id": receipt["original_rfc822_message_id"],
        "smtp_code": event["smtp_code"],
        "enhanced_status": event["enhanced_status"],
        "observed_at": event["observed_at"],
        "source_sha256": event["source_sha256"],
    }
    event["event_id"] = "dsn-" + dsn.sha256_json(identity)[:40]


class DsnAuthorityTests(unittest.TestCase):
    def test_valid_receipt_recomputes_from_independent_source_and_binding(self):
        source = raw_dsn()
        trusted_binding = binding()
        receipt = dsn.normalize(source, trusted_binding)
        self.assertTrue(authority.verify_authoritative_receipt(receipt, source, trusted_binding))
        self.assertEqual(authority.authoritative_receipt(receipt, source, trusted_binding), receipt)
        self.assertEqual(authority.authoritative_event(receipt, source, trusted_binding), receipt["event"])

    def test_refreshed_semantic_forgery_passes_integrity_but_fails_authority(self):
        source = raw_dsn()
        trusted_binding = binding()
        forged = dsn.normalize(source, trusted_binding)
        forged["event"]["smtp_code"] = 551
        _refresh_event_id(forged)
        _refresh_attacker_hashes(forged)

        # This is the exact review discriminator: every caller-computable hash
        # is fresh, so integrity alone accepts the fabricated normalized fact.
        self.assertTrue(dsn.verify_receipt(forged))
        self.assertFalse(authority.verify_authoritative_receipt(forged, source, trusted_binding))
        with self.assertRaisesRegex(dsn.DsnError, "does not match authoritative"):
            authority.authoritative_event(forged, source, trusted_binding)

    def test_fabricated_source_digest_with_fresh_hashes_fails_authority(self):
        source = raw_dsn()
        trusted_binding = binding()
        forged = dsn.normalize(source, trusted_binding)
        fake_source = "f" * 64
        forged["source_sha256"] = fake_source
        forged["event"]["source_sha256"] = fake_source
        _refresh_event_id(forged)
        _refresh_attacker_hashes(forged)

        self.assertTrue(dsn.verify_receipt(forged))
        self.assertFalse(authority.verify_authoritative_receipt(forged, source, trusted_binding))

    def test_changed_raw_source_fails_even_when_normalized_semantics_are_same(self):
        source = raw_dsn()
        trusted_binding = binding()
        receipt = dsn.normalize(source, trusted_binding)
        changed_source = source.replace(b"Delivery failed.", b"Delivery has failed.")
        self.assertFalse(
            authority.verify_authoritative_receipt(receipt, changed_source, trusted_binding)
        )

    def test_wrong_trusted_binding_fails_closed(self):
        source = raw_dsn()
        receipt = dsn.normalize(source, binding())
        wrong = binding(recipient="other@example.com")
        self.assertFalse(authority.verify_authoritative_receipt(receipt, source, wrong))

    def test_malformed_or_side_effect_escalated_receipt_fails_closed(self):
        source = raw_dsn()
        trusted_binding = binding()
        escalated = dsn.normalize(source, trusted_binding)
        escalated["side_effects_authorized"] = True
        _refresh_attacker_hashes(escalated)
        self.assertFalse(
            authority.verify_authoritative_receipt(escalated, source, trusted_binding)
        )
        self.assertFalse(authority.verify_authoritative_receipt({}, source, trusted_binding))

    def test_authoritative_event_is_detached_from_caller_receipt(self):
        source = raw_dsn()
        trusted_binding = binding()
        receipt = dsn.normalize(source, trusted_binding)
        event = authority.authoritative_event(receipt, source, trusted_binding)
        receipt["event"]["smtp_code"] = 599
        self.assertEqual(event["smtp_code"], 550)


if __name__ == "__main__":
    unittest.main()
