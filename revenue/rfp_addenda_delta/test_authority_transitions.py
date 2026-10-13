from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

try:
    from . import engine as engine_module
    from .engine import compile_current, compile_historical, verify_report
    from .schema import normalize_decisions, normalize_generation
    from .test_helpers import decision_for, generation
except ImportError:
    import engine as engine_module
    from engine import compile_current, compile_historical, verify_report
    from schema import normalize_decisions, normalize_generation
    from test_helpers import decision_for, generation


class SourceAuthorityTransitionTests(unittest.TestCase):
    NOW = "2026-09-13T18:00:00Z"

    def report(self, old, new, decisions=None):
        with patch.object(engine_module, "_process_now", return_value=self.NOW):
            return compile_current(old, new, decisions or [])

    def test_incomplete_old_generation_cannot_carry_review_into_complete_new_generation(self):
        old = generation(complete=False)
        new = generation("g2", "2026-09-13T13:00:00Z", complete=True)
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertEqual(out["source_set_delta"], {"old_complete": False, "new_complete": True})
        self.assertEqual(out["carried_review_decisions"], [])
        self.assertEqual(out["review_required"], ["R-001"])

    def test_stale_prior_review_cannot_carry_into_fresh_generation(self):
        old = generation(captured="2026-09-01T12:00:00Z")
        new = generation("g2", "2026-09-13T17:00:00Z")
        decision = decision_for(old)
        decision["decided_at"] = "2026-09-01T12:30:00Z"
        out = self.report(old, new, [decision])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertEqual(out["carried_review_decisions"], [])
        self.assertEqual(
            out["stale_review_decisions"],
            [{"requirement_id": "R-001", "decision_id": "d-R-001"}],
        )
        self.assertEqual(out["review_required"], ["R-001"])

    def test_public_historical_clock_can_never_mint_green(self):
        old = generation(captured="2026-09-01T12:00:00Z")
        new = generation("g2", "2026-09-01T13:00:00Z")
        decision = decision_for(old)
        decision["decided_at"] = "2026-09-01T12:30:00Z"
        out = compile_historical(old, new, [decision], trusted_as_of="2026-09-01T14:00:00Z")
        self.assertEqual(out["clock_authority"], "CALLER_SUPPLIED_HISTORICAL")
        self.assertEqual(out["state"], "HOLD")

    def test_current_verifier_rejects_old_process_clock_receipt(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        report = self.report(old, new, [decision_for(old)])
        with patch.object(engine_module, "_process_now", return_value="2026-09-13T18:06:00Z"):
            ok, reason = verify_report(old, new, [decision_for(old)], report)
        self.assertFalse(ok)
        self.assertEqual(reason, "report_stale")

    def test_direct_submodule_has_no_caller_time_current_authority_minter(self):
        # The stale-head defect existed because production functions accepted both
        # caller time and PROCESS_UTC. Those functions must not exist anymore.
        self.assertFalse(hasattr(engine_module, "_compile_at"))
        self.assertFalse(hasattr(engine_module, "_verify_report_at"))
        for name, obj in vars(engine_module).items():
            if not inspect.isfunction(obj) or obj.__module__ != engine_module.__name__:
                continue
            params = inspect.signature(obj).parameters
            if name != "compile_historical":
                self.assertNotIn("trusted_as_of", params, name)
            self.assertNotIn("verifier_now", params, name)
            self.assertNotIn("clock_authority", params, name)

        # The only explicit-time semantic primitive is a non-authoritative
        # projection. It cannot be fed to verify_report as a current receipt.
        old = generation(captured="2026-09-01T12:00:00Z")
        new = generation("g2", "2026-09-01T13:00:00Z")
        decision = decision_for(old)
        decision["decided_at"] = "2026-09-01T12:30:00Z"
        projection = engine_module._semantic_projection(
            normalize_generation(old), normalize_generation(new), normalize_decisions([decision]),
            "2026-09-01T14:00:00Z",
        )
        for authority_key in ("schema", "evaluated_at", "clock_authority", "semantic_sha256"):
            self.assertNotIn(authority_key, projection)
        self.assertEqual(projection["state"], "NO_MATERIAL_CHANGE")
        with patch.object(engine_module, "_process_now", return_value="2026-09-13T18:00:00Z"):
            self.assertEqual(
                verify_report(old, new, [decision], projection),
                (False, "report_shape"),
            )


if __name__ == "__main__":
    unittest.main()
