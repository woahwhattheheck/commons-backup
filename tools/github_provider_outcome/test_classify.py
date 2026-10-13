"""Focused regression cases for contradictory provider-reach observations."""
import unittest

from classify import classify


class ProviderReachContradictionTests(unittest.TestCase):
    def test_preprovider_without_http_is_definitely_not_sent(self):
        result = classify({
            "operation_kind": "write",
            "provider_reached": False,
            "message": "This tool call was blocked by OpenAI's safety checks.",
        })
        self.assertEqual(result["classification"], "pre_provider_block")
        self.assertEqual(result["effect_state"], "not_sent")
        self.assertFalse(result["requires_provider_readback"])

    def test_explicit_preprovider_with_reported_success_is_not_trusted(self):
        result = classify({
            "operation_kind": "write",
            "provider_reached": False,
            "http_status": 201,
        })
        self.assertEqual(result["classification"], "indeterminate")
        self.assertEqual(result["effect_state"], "uncertain")
        self.assertTrue(result["requires_provider_readback"])
        self.assertFalse(result["automatic_retry"])

    def test_preprovider_conflicting_with_http_permission_error_is_uncertain(self):
        result = classify({
            "operation_kind": "write",
            "provider_reached": False,
            "http_status": 403,
            "message": "Resource not accessible by integration",
        })
        self.assertEqual(result["classification"], "indeterminate")
        self.assertEqual(result["next_action"], "reconcile_write_before_retry")

    def test_safety_marker_with_explicit_provider_reach_is_uncertain(self):
        result = classify({
            "operation_kind": "write",
            "provider_reached": True,
            "message": "This tool call was blocked by OpenAI's safety checks.",
        })
        self.assertEqual(result["classification"], "indeterminate")
        self.assertTrue(result["requires_provider_readback"])

    def test_unambiguous_provider_permission_denial_stays_permission_denial(self):
        result = classify({
            "operation_kind": "write",
            "provider_reached": True,
            "http_status": 403,
            "message": "Resource not accessible by integration",
        })
        self.assertEqual(result["classification"], "app_permission_denied")
        self.assertFalse(result["requires_provider_readback"])


if __name__ == "__main__":
    unittest.main()
