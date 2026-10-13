#!/usr/bin/env python3
from __future__ import annotations

import unittest

from status_claims import claims_activation


class StatusClaimsTests(unittest.TestCase):
    def test_negative_lifecycle_statuses_are_not_activation(self) -> None:
        values = (
            "default_off",
            "default_off_complete_day_quote_telemetry_hardened_engine_checked",
            "inactive_native_admission_experiment_component_tested_not_runtime_promoted",
            "exact_donor_and_current_component_tested_not_runtime_promoted",
            "source_repair_component_tested_not_runtime_promoted",
            "not_active",
            "not_enabled",
            "not_activated",
            "not_production_promoted",
            "not_runtime_promoted",
            "source_only",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(claims_activation(value))

    def test_positive_lifecycle_tokens_are_activation(self) -> None:
        values = (
            "active",
            "promoted",
            "enabled",
            "activated",
            "production_promoted",
            "runtime_active",
            "source_active_guard_enabled",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(claims_activation(value))

    def test_substrings_do_not_count_as_tokens(self) -> None:
        for value in ("inactive", "reactivatedness", "promotedness", "enabledness"):
            with self.subTest(value=value):
                self.assertFalse(claims_activation(value))

    def test_non_strings_are_not_activation(self) -> None:
        for value in (None, False, True, 0, 1, [], {}):
            with self.subTest(value=value):
                self.assertFalse(claims_activation(value))


if __name__ == "__main__":
    unittest.main()
