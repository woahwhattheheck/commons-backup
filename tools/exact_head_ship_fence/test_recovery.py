"""Bounded-input and optional-review regression coverage for the retained compiler."""
from __future__ import annotations

from copy import deepcopy
import unittest

from . import fence
from .demo import snapshot


class ReviewInputBounds(unittest.TestCase):
    def test_review_count_is_checked_before_rows(self):
        packet = snapshot()
        packet["reviews"] *= 65
        with self.assertRaisesRegex(fence.EvidenceError, "reviews: too many items"):
            fence.compile_current(packet)

    def test_non_string_head_is_rejected_without_comparison(self):
        class NotAString:
            def __eq__(self, other):
                raise RuntimeError("non-JSON comparison was invoked")
        packet = snapshot()
        packet["reviews"][0]["head_sha"] = NotAString()
        with self.assertRaises(fence.EvidenceError):
            fence.compile_current(packet)

    def test_long_reviewer_is_rejected(self):
        packet = snapshot()
        packet["reviews"][0]["reviewer"] = "r" * 129
        with self.assertRaisesRegex(fence.EvidenceError, "invalid string"):
            fence.compile_current(packet)

    def test_malformed_head_still_rejected(self):
        packet = snapshot()
        packet["reviews"][0]["head_sha"] = "1" * 41
        with self.assertRaises(fence.EvidenceError):
            fence.compile_current(packet)

    def test_maximum_distinct_review_rows_are_accepted(self):
        packet = snapshot()
        template = packet["reviews"][0]
        packet["reviews"] = [dict(template, review_id=f"review-{i}", reviewer=f"seat-{i}") for i in range(64)]
        report = fence.compile_current(packet)
        self.assertEqual(report["summary"]["current_review_pass_count"], 64)
        self.assertTrue(fence.verify_current(report, packet))

    def test_invalid_input_does_not_modify_packet(self):
        packet = snapshot()
        packet["reviews"] *= 65
        before = deepcopy(packet)
        with self.assertRaises(fence.EvidenceError):
            fence.compile_current(packet)
        self.assertEqual(packet, before)


class RetainedSuccessorCoverage(unittest.TestCase):
    def test_optional_positive_review_policy_does_not_erase_stop(self):
        packet = snapshot()
        packet["review_policy"] = {"required": False, "min_passes": 0}
        packet["reviews"][0]["verdict"] = "STOP"
        report = fence.compile_current(packet)
        self.assertEqual(report["verdict"], "HOLD_REVIEW_STALE")
        self.assertEqual(report["reason_codes"], ["EXACT_HEAD_REVIEW_STOP"])
        self.assertTrue(fence.verify_current(report, packet))
        self.assertTrue(all(value is False for value in report["authority"].values()))

    def test_optional_review_stop_and_queued_ci_remains_hold(self):
        packet = snapshot()
        packet["review_policy"] = {"required": False, "min_passes": 0}
        packet["reviews"][0]["verdict"] = "STOP"
        packet["checks"][0].update(status="QUEUED", conclusion="NONE")
        self.assertEqual(fence.compile_current(packet)["reason_codes"], ["EXACT_HEAD_REVIEW_STOP"])

    def test_schema_array_caps(self):
        for key in ("checks", "check_policy"):
            with self.subTest(key=key):
                packet = snapshot()
                packet[key] *= 129
                with self.assertRaisesRegex(fence.EvidenceError, "too many items"):
                    fence.compile_current(packet)

    def test_path_array_caps(self):
        for key in ("candidate_paths", "base_delta_paths"):
            with self.subTest(key=key):
                packet = snapshot()
                packet["topology"][key] = [{"path": "x", "blob_sha": None}] * 1025
                with self.assertRaisesRegex(fence.EvidenceError, "too many items"):
                    fence.compile_current(packet)

    def test_direct_node_budget(self):
        with self.assertRaisesRegex(fence.EvidenceError, "node budget"):
            fence.canonical_json_bytes([None] * 65536)

    def test_direct_text_byte_budget(self):
        for value in ("a" * 1048577, "\u20ac" * 400000):
            with self.subTest(length=len(value)):
                with self.assertRaisesRegex(fence.EvidenceError, "byte budget"):
                    fence.canonical_json_bytes(value)

    def test_direct_cycles_are_domain_errors(self):
        value = []
        value.append(value)
        with self.assertRaisesRegex(fence.EvidenceError, "nesting too deep"):
            fence.canonical_json_bytes(value)


if __name__ == "__main__":
    unittest.main()
