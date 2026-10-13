from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from . import authority as a
from .test_authority import HostAuthority, NOW, packet


BEFORE = datetime(2026, 9, 13, 22, 44, 59, tzinfo=timezone.utc)
EQUAL = datetime(2026, 9, 13, 22, 45, 0, tzinfo=timezone.utc)
AFTER = datetime(2026, 9, 13, 22, 45, 1, tzinfo=timezone.utc)


class QuoteExpiryVerificationTests(unittest.TestCase):
    def _current_fixture(self):
        p = copy.deepcopy(packet())
        p["policy"]["quote_validity_hours"] = 1
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        host = HostAuthority(Path(td.name))
        host.sign(p, generation=11)
        ctx = patch.object(a, "_host_paths", return_value=host.paths)
        return p, host, ctx

    def test_quote_is_current_one_second_before_expiry(self):
        p, _, ctx = self._current_fixture()
        with ctx:
            report = a._compile_current_at(p, NOW)
            self.assertEqual(report["calculation"]["quote_valid_until"], "2026-09-13T22:45:00Z")
            result = a._verify_current_at(p, report, BEFORE)
        self.assertEqual(result["state"], "CURRENT_VERIFIED")

    def test_quote_is_current_at_exact_expiry_boundary(self):
        p, _, ctx = self._current_fixture()
        with ctx:
            report = a._compile_current_at(p, NOW)
            result = a._verify_current_at(p, report, EQUAL)
        self.assertEqual(result["state"], "CURRENT_VERIFIED")

    def test_quote_is_stale_one_second_after_expiry_while_other_authority_is_fresh(self):
        p, _, ctx = self._current_fixture()
        with ctx:
            report = a._compile_current_at(p, NOW)
            self.assertTrue(report["input_authority"]["authenticated"])
            result = a._verify_current_at(p, report, AFTER)
        self.assertTrue(result["historical_receipt_valid"])
        self.assertEqual(result["state"], "STALE_OR_DRIFTED")

    def test_future_receipt_cannot_verify_current(self):
        p, _, ctx = self._current_fixture()
        earlier = datetime(2026, 9, 13, 21, 44, 59, tzinfo=timezone.utc)
        with ctx:
            report = a._compile_current_at(p, NOW)
            result = a._verify_current_at(p, report, earlier)
        self.assertTrue(result["historical_receipt_valid"])
        self.assertEqual(result["state"], "FUTURE_RECEIPT")
        self.assertIsNone(result["current_report_receipt_sha256"])

    def test_quote_expiry_field_tamper_is_not_historical_truth(self):
        p, _, ctx = self._current_fixture()
        with ctx:
            report = a._compile_current_at(p, NOW)
            report["calculation"]["quote_valid_until"] = "not-a-time"
            result = a._verify_current_at(p, report, NOW)
        self.assertFalse(result["historical_receipt_valid"])
        self.assertEqual(result["state"], "INVALID_HISTORICAL_RECEIPT")


if __name__ == "__main__":
    unittest.main()
