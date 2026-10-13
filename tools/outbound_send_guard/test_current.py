from __future__ import annotations

import inspect
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import tools.outbound_send_guard as outbound_package
from tools.outbound_send_guard import current, current_impl, current_worker, guard

NOW = datetime(2026, 9, 14, 4, 55, 0, tzinfo=timezone.utc)


def intent(requested_at: str = "2026-09-14T04:54:30Z") -> dict:
    return {
        "schema_version": "outbound-send-intent/v1",
        "intent_id": "intent-current-boundary-1",
        "recipient": "buyer@example.com",
        "offer_id": "fixed-proof-001",
        "requested_at": requested_at,
        "route_kind": "email",
    }


def evidence(generated_at: str = "2026-09-14T04:54:20Z") -> dict:
    return {
        "schema_version": "outbound-send-evidence/v1",
        "generated_at": generated_at,
        "mailbox": {"complete": True, "query_id": "mail-complete", "messages": []},
        "slack": {"complete": True, "query_id": "slack-complete", "events": []},
        "policy": {
            "cross_offer_cooldown_days": 30,
            "max_evidence_age_seconds": 604800,
            "max_future_skew_seconds": 86400,
        },
    }


def encoded(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class CurrentBoundaryTests(unittest.TestCase):
    def test_package_evaluate_is_fail_closed_embedded_surface(self):
        self.assertIs(outbound_package.evaluate, current.compile_current)
        result = outbound_package.evaluate(intent(), evidence())
        payload = result["payload"]
        self.assertEqual(payload["mode"], current.MODE_EMBEDDED)
        self.assertEqual(payload["historical_decision"], "ALLOW_NEW")
        self.assertEqual(payload["decision"], "HOLD")
        self.assertFalse(payload["current_preflight_clear"])
        self.assertFalse(payload["side_effects_authorized"])

    def test_wrapper_state_mutation_cannot_reenable_embedded_positive(self):
        # These names were authority seams on the superseded head. Assigning
        # arbitrary replacements must now be inert because production CURRENT
        # no longer exists in the imported wrapper.
        current._utc_now = lambda: NOW  # type: ignore[attr-defined]
        current._core = lambda *a, **k: {  # type: ignore[attr-defined]
            "payload": {"decision": "ALLOW_NEW", "side_effects_authorized": False},
            "receipt_sha256": "0" * 64,
        }
        try:
            result = current.compile_current(intent(), evidence())
            self.assertEqual(result["payload"]["decision"], "HOLD")
            self.assertFalse(result["payload"]["current_preflight_clear"])
        finally:
            current.__dict__.pop("_utc_now", None)
            current.__dict__.pop("_core", None)

    def test_compatibility_guard_caller_digests_cannot_forge_provenance(self):
        it = intent()
        ev = evidence()
        receipt = guard.evaluate(
            it,
            ev,
            intent_sha256="a" * 64,
            evidence_sha256="b" * 64,
        )
        payload = receipt["payload"]
        self.assertEqual(payload["intent"]["recipient"], "buyer@example.com")
        self.assertEqual(payload["authority"], "complete")
        self.assertEqual(payload["evidence"]["intent_sha256"], guard.digest_object(it))
        self.assertEqual(payload["evidence"]["evidence_sha256"], guard.digest_object(ev))
        self.assertNotEqual(payload["evidence"]["intent_sha256"], "a" * 64)
        self.assertNotEqual(payload["evidence"]["evidence_sha256"], "b" * 64)
        custody = payload["source_custody"]
        self.assertEqual(custody["mode"], "CANONICAL_OBJECT_SNAPSHOT")
        self.assertEqual(custody["intent"]["canonical_object_sha256"], guard.digest_object(it))
        self.assertIsNone(custody["intent"]["exact_bytes_sha256"])
        self.assertEqual(custody["evidence"]["canonical_object_sha256"], guard.digest_object(ev))
        self.assertIsNone(custody["evidence"]["exact_bytes_sha256"])
        self.assertEqual(payload["historical_decision"], "ALLOW_NEW")
        self.assertEqual(payload["decision"], "HOLD")
        self.assertFalse(payload["current_preflight_clear"])

    def test_compatibility_guard_byte_api_binds_only_exact_consumed_bytes(self):
        it = intent()
        ev = evidence()
        ib = json.dumps(it, sort_keys=True, indent=2).encode("utf-8")
        eb = json.dumps(ev, sort_keys=True, indent=2).encode("utf-8")
        receipt = guard.evaluate_bytes(ib, eb)
        payload = receipt["payload"]
        custody = payload["source_custody"]
        self.assertEqual(custody["mode"], "EXACT_CONSUMED_BYTES")
        self.assertEqual(payload["evidence"]["intent_sha256"], guard.digest_bytes(ib))
        self.assertEqual(payload["evidence"]["evidence_sha256"], guard.digest_bytes(eb))
        self.assertEqual(custody["intent"]["exact_bytes_sha256"], guard.digest_bytes(ib))
        self.assertEqual(custody["evidence"]["exact_bytes_sha256"], guard.digest_bytes(eb))
        self.assertEqual(custody["intent"]["canonical_object_sha256"], guard.digest_object(it))
        self.assertEqual(custody["evidence"]["canonical_object_sha256"], guard.digest_object(ev))
        self.assertNotEqual(guard.digest_bytes(ib), guard.digest_object(it))
        self.assertNotEqual(guard.digest_bytes(eb), guard.digest_object(ev))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertFalse(payload["side_effects_authorized"])

    def test_compatibility_guard_byte_api_rejects_non_bytes(self):
        with self.assertRaises(guard.GuardError):
            guard.evaluate_bytes(intent(), encoded(evidence()))  # type: ignore[arg-type]
        with self.assertRaises(guard.GuardError):
            guard.evaluate_bytes(encoded(intent()), evidence())  # type: ignore[arg-type]

    def test_exact_byte_embedded_surface_binds_consumed_bytes_and_holds(self):
        ib = encoded(intent())
        eb = encoded(evidence())
        result = current.compile_current_bytes(ib, eb)
        payload = result["payload"]
        self.assertEqual(payload["decision"], "HOLD")
        self.assertEqual(
            payload["source"]["byte_custody"]["intent_sha256"],
            current.guard.digest_bytes(ib),
        )
        self.assertEqual(
            payload["source"]["byte_custody"]["evidence_sha256"],
            current.guard.digest_bytes(eb),
        )

    def test_embedded_verify_is_always_non_authorizing(self):
        result = current.verify_current(intent(), evidence(), {"forged": "current"})
        payload = result["payload"]
        self.assertFalse(payload["historical_valid"])
        self.assertFalse(payload["current_semantics_match"])
        self.assertFalse(payload["current_preflight_valid"])
        self.assertEqual(payload["current_decision"], "HOLD")

    def test_explicit_historical_replay_is_hold_only(self):
        result = current.compile_historical_at(intent(), evidence(), historical_at=NOW)
        payload = result["payload"]
        self.assertEqual(payload["mode"], current.MODE_HISTORICAL)
        self.assertEqual(payload["historical_decision"], "ALLOW_NEW")
        self.assertEqual(payload["decision"], "HOLD")
        self.assertFalse(payload["current_preflight_clear"])

    def test_internal_worker_still_computes_current_semantics_for_direct_cli(self):
        # This is an internal runtime primitive test, not a claim that importing
        # current_worker establishes production authority.
        with patch.object(current_impl, "_utc_now", return_value=NOW):
            result = current_worker.compile_current(intent(), evidence())
        payload = result["payload"]
        self.assertEqual(payload["mode"], current.MODE_CURRENT)
        self.assertEqual(payload["decision"], "ALLOW_NEW")
        self.assertTrue(payload["current_preflight_clear"])
        self.assertFalse(payload["side_effects_authorized"])

    def test_worker_bind_keeps_four_arg_core_adapter(self):
        """Regress run 35113530437: do not smash current_impl._core with 2-arg evaluate."""
        current_worker._bind_internal_engine()
        self.assertIs(current_impl.guard, current_worker._core)
        params = list(inspect.signature(current_impl._core).parameters)
        self.assertEqual(params, ["intent", "evidence", "ib", "eb"])
        self.assertIsNot(current_impl._core, current_worker._core.evaluate)


if __name__ == "__main__":
    unittest.main()
