from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from revenue.trusted_evidence_authority.acceptance import packet_value, registry_value
from revenue.trusted_evidence_authority.authority import (
    AuthorityError,
    load_trusted_registry,
    make_packet,
    registry_from_value_for_tests,
    sha256_bytes,
    verify_current,
    verify_historical,
    verify_receipt,
)
from revenue.trusted_evidence_authority.strict_json import StrictJsonError, canonical_json, loads_strict

UTC = timezone.utc
NOW = datetime(2026, 9, 13, 11, 0, tzinfo=UTC)


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(StrictJsonError):
            loads_strict('{"x":1,"x":2}')

    def test_reserved_proto_keys_rejected(self):
        for key in ("__proto__", "prototype", "constructor"):
            with self.subTest(key=key), self.assertRaises(StrictJsonError):
                loads_strict(json.dumps({key: {"x": 1}}))

    def test_non_finite_and_float_rejected(self):
        with self.assertRaises(StrictJsonError):
            loads_strict('{"x":NaN}')
        with self.assertRaises(StrictJsonError):
            canonical_json({"x": 0.1})

    def test_unsafe_integer_rejected(self):
        with self.assertRaises(StrictJsonError):
            canonical_json({"x": (1 << 53)})


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.registry_raw = registry_value()
        self.registry = registry_from_value_for_tests(self.registry_raw)
        self.packet = packet_value(self.registry_raw)

    def test_exact_current_source_authority_passes(self):
        receipt = verify_current(self.packet, self.registry, now=NOW)
        self.assertEqual(receipt["evidence_level"], "CURRENT_SOURCE_AUTHORITY")
        self.assertTrue(receipt["current_source_authority"])
        self.assertTrue(verify_receipt(receipt))

    def test_content_forgery_holds(self):
        packet = deepcopy(self.packet)
        packet["sources"][0]["content_sha256"] = "f" * 64
        receipt = verify_current(packet, self.registry, now=NOW)
        self.assertFalse(receipt["current_source_authority"])
        self.assertIn("SOURCE_MISMATCH:provider-status:content_sha256", receipt["reasons"])

    def test_omission_holds(self):
        packet = deepcopy(self.packet)
        packet["sources"].pop()
        receipt = verify_current(packet, self.registry, now=NOW)
        self.assertFalse(receipt["current_source_authority"])
        self.assertTrue(any(r.startswith("MISSING_SOURCE:") for r in receipt["reasons"]))

    def test_unknown_extra_source_holds(self):
        packet = deepcopy(self.packet)
        extra = deepcopy(packet["sources"][0])
        extra["source_id"] = "extra"
        extra["scope"] = "other/scope"
        packet["sources"].append(extra)
        receipt = verify_current(packet, self.registry, now=NOW)
        self.assertIn("UNKNOWN_SOURCE:extra", receipt["reasons"])

    def test_provider_scope_resource_aliases_hold(self):
        for field, changed in (
            ("provider", "provider-b"),
            ("scope", "account/other"),
            ("resource", "acct-42/status-alt"),
        ):
            packet = deepcopy(self.packet)
            packet["sources"][0][field] = changed
            with self.subTest(field=field):
                self.assertFalse(verify_current(packet, self.registry, now=NOW)["current_source_authority"])

    def test_superseded_generation_holds(self):
        packet = deepcopy(self.packet)
        packet["sources"][0]["generation"] -= 1
        receipt = verify_current(packet, self.registry, now=NOW)
        self.assertIn("SOURCE_MISMATCH:provider-status:generation", receipt["reasons"])

    def test_stale_source_holds_at_current_time(self):
        receipt = verify_current(self.packet, self.registry, now=NOW + timedelta(hours=2))
        self.assertFalse(receipt["current_source_authority"])
        self.assertTrue(any(r.startswith("STALE_SOURCE:") for r in receipt["reasons"]))

    def test_future_source_holds(self):
        receipt = verify_current(self.packet, self.registry, now=NOW - timedelta(hours=1))
        self.assertTrue(any(r.startswith("SOURCE_FROM_FUTURE:") for r in receipt["reasons"]))

    def test_historical_replay_never_upgrades_to_current(self):
        receipt = verify_historical(self.packet, self.registry, as_of=NOW)
        self.assertEqual(receipt["evidence_level"], "HISTORICAL_INTEGRITY")
        self.assertFalse(receipt["current_source_authority"])
        self.assertTrue(verify_receipt(receipt))

    def test_payload_hash_is_exact(self):
        packet = deepcopy(self.packet)
        packet["payload"]["amount_cents"] = 1
        with self.assertRaises(AuthorityError):
            verify_current(packet, self.registry, now=NOW)

    def test_decision_and_subject_bind_packet_identity(self):
        original = verify_current(self.packet, self.registry, now=NOW)
        for field in ("decision_id", "subject_id"):
            packet = deepcopy(self.packet)
            packet[field] += "-other"
            changed = verify_current(packet, self.registry, now=NOW)
            with self.subTest(field=field):
                self.assertNotEqual(original["packet_sha256"], changed["packet_sha256"])

    def test_registry_rejects_ambiguous_scope(self):
        raw = deepcopy(self.registry_raw)
        extra = deepcopy(raw["sources"][0])
        extra["source_id"] = "other"
        raw["sources"].append(extra)
        with self.assertRaises(AuthorityError):
            registry_from_value_for_tests(raw)

    def test_registry_file_requires_independent_pin(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            data = (canonical_json(self.registry_raw) + "\n").encode()
            path.write_bytes(data)
            good_pin = sha256_bytes(data)
            self.assertEqual(load_trusted_registry(path, expected_file_sha256=good_pin).registry_id, "demo-registry-v7")
            with self.assertRaises(AuthorityError):
                load_trusted_registry(path, expected_file_sha256="0" * 64)

    def test_coordinated_forged_registry_cannot_reuse_external_pin(self):
        with tempfile.TemporaryDirectory() as td:
            legitimate = Path(td) / "legit.json"
            legit_bytes = (canonical_json(self.registry_raw) + "\n").encode()
            legitimate.write_bytes(legit_bytes)
            pin = sha256_bytes(legit_bytes)
            fake_raw = deepcopy(self.registry_raw)
            fake_raw["sources"][0]["content_sha256"] = "f" * 64
            forged = Path(td) / "forged.json"
            forged.write_text(canonical_json(fake_raw) + "\n", encoding="utf-8")
            with self.assertRaises(AuthorityError):
                load_trusted_registry(forged, expected_file_sha256=pin)

    def test_receipt_tamper_rejected(self):
        receipt = verify_current(self.packet, self.registry, now=NOW)
        receipt["subject_id"] = "other"
        self.assertFalse(verify_receipt(receipt))

    def test_receipt_authority_ceiling_explicit(self):
        receipt = verify_current(self.packet, self.registry, now=NOW)
        self.assertIn("no decision correctness", receipt["authority_ceiling"])
        self.assertNotIn("payment_authorized", receipt)

    def test_make_packet_rejects_float_payload(self):
        with self.assertRaises(StrictJsonError):
            make_packet(registry_id="r", subject_id="s", decision_id="d", payload={"x": 1.2}, sources=[])


if __name__ == "__main__":
    unittest.main()
