from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone

from tools.outbound_send_guard import current, guard
from tools.outbound_send_guard.test_current import evidence, intent


class CurrentClockBoundaryTests(unittest.TestCase):
    def test_embedded_current_surface_exposes_no_clock_core_or_sync_authority_seam(self):
        self.assertNotIn("_utc_now", current.__dict__)
        self.assertNotIn("_core", current.__dict__)
        self.assertNotIn("_sync_impl", current.__dict__)
        self.assertNotIn("_compile_current_owned_clock", current.__dict__)
        self.assertNotIn("_verify_current_owned_clock", current.__dict__)
        self.assertFalse(hasattr(current.guard, "evaluate"))

    def test_supported_embedded_emitters_accept_no_clock_or_mode_parameter(self):
        forbidden = {"now", "verified_at", "historical_at", "mode", "verifier_time"}
        for name in ("compile_current", "compile_current_bytes", "verify_current", "verify_current_bytes"):
            params = set(inspect.signature(getattr(current, name)).parameters)
            self.assertFalse(params & forbidden, f"{name} exposes {params & forbidden}")

    def test_predecessor_wrapper_state_and_default_container_names_are_inert(self):
        current._utc_now = lambda: datetime(2099, 1, 1, tzinfo=timezone.utc)  # type: ignore[attr-defined]
        current._core = lambda *a, **k: None  # type: ignore[attr-defined]
        current._sync_impl = lambda *a, **k: None  # type: ignore[attr-defined]
        current._sync_impl.__defaults__ = (  # type: ignore[attr-defined]
            lambda: datetime(2099, 1, 1, tzinfo=timezone.utc),
            lambda *a, **k: {"payload": {"decision": "ALLOW_NEW"}},
        )
        try:
            result = current.compile_current(intent(), evidence())
            self.assertEqual(result["payload"]["decision"], "HOLD")
            self.assertEqual(result["payload"]["mode"], current.MODE_EMBEDDED)
            self.assertFalse(result["payload"]["current_preflight_clear"])
        finally:
            for name in ("_utc_now", "_core", "_sync_impl"):
                current.__dict__.pop(name, None)

    def test_compatibility_facade_does_not_replay_historical_positive(self):
        result = guard.evaluate(intent(), evidence())
        self.assertEqual(result["payload"]["historical_decision"], "ALLOW_NEW")
        self.assertEqual(result["payload"]["decision"], "HOLD")
        self.assertFalse(result["payload"]["current_preflight_clear"])


if __name__ == "__main__":
    unittest.main()
