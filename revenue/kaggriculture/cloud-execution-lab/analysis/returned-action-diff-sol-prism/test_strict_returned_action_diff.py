#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

import returned_action_diff as parent
import strict_returned_action_diff as strict


def _sample(action):
    raw = {"statusCode": 200, "body": {"action": action}}
    unwrapped, path = parent.unwrap_action(raw)
    assert unwrapped == action
    return {
        "captured_at": "2026-09-10T00:00:00+00:00",
        "http": {
            "status": 200,
            "content_type": "application/json",
            "elapsed_ms": 1.0,
            "body_sha256": strict.sha256_json(raw),
        },
        "raw_response": raw,
        "unwrap_path": list(path),
        "action": action,
        "action_sha256": strict.sha256_json(action),
    }


def capture(
    action,
    *,
    state=None,
    samples=None,
    name="arm",
    endpoint="https://example.invalid/arm",
):
    state = {"step": 95, "board": [1, 2, 3]} if state is None else state
    samples = [_sample(action)] if samples is None else samples
    hashes = [item["action_sha256"] for item in samples]
    first_unstable = next(
        (i for i, value in enumerate(hashes[1:], 1) if value != hashes[0]), None
    )
    first_internal = None
    if first_unstable is not None:
        diffs = parent.semantic_diff(
            samples[0]["action"], samples[first_unstable]["action"]
        )
        first_internal = asdict(diffs[0]) if diffs else None
    state_bytes = strict.canonical_json_bytes(state)
    baseline = samples[0]
    return {
        "format": parent.CAPTURE_FORMAT,
        "name": name,
        "endpoint": endpoint,
        "captured_at": "2026-09-10T00:00:00+00:00",
        "state_sha256": strict.sha256_bytes(state_bytes),
        "request_sha256": strict.sha256_bytes(state_bytes),
        "request_bytes_length": len(state_bytes),
        "state": state,
        "sample_count": len(samples),
        "unique_action_count": len(set(hashes)),
        "deterministic": len(set(hashes)) == 1,
        "first_unstable_sample": first_unstable,
        "first_internal_difference": first_internal,
        "samples": samples,
        "raw_response": baseline["raw_response"],
        "unwrap_path": baseline["unwrap_path"],
        "action": baseline["action"],
        "action_sha256": baseline["action_sha256"],
    }


class StrictDiffTests(unittest.TestCase):
    def test_positional_market_swap_is_difference_by_default(self):
        left = {"market": [{"id": "A", "qty": 1}, {"id": "B", "qty": 2}]}
        right = {"market": [{"id": "B", "qty": 2}, {"id": "A", "qty": 1}]}
        diffs = strict.strict_semantic_diff(left, right)
        self.assertTrue(diffs)
        self.assertTrue(any(item.path.startswith("$.market[0]") for item in diffs))

    def test_explicit_unordered_path_can_ignore_pure_reorder(self):
        left = {"market": [{"id": "A", "qty": 1}, {"id": "B", "qty": 2}]}
        right = {"market": [{"id": "B", "qty": 2}, {"id": "A", "qty": 1}]}
        self.assertEqual(
            strict.strict_semantic_diff(
                left, right, unordered_paths=frozenset({"$.market"})
            ),
            [],
        )

    def test_unordered_path_requires_unique_identity(self):
        left = {"market": [{"id": "A"}, {"id": "A"}]}
        right = {"market": [{"id": "A"}, {"id": "A"}]}
        with self.assertRaises(strict.EvidenceError):
            strict.strict_semantic_diff(
                left, right, unordered_paths=frozenset({"$.market"})
            )

    def test_large_integer_does_not_binary64_alias(self):
        n = 2**53
        diffs = strict.strict_semantic_diff({"cash": n + 1}, {"cash": n})
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].absolute_delta, 1)

    def test_large_integer_vs_float_does_not_alias(self):
        n = 2**53
        diffs = strict.strict_semantic_diff({"cash": n + 1}, {"cash": float(n)})
        self.assertEqual(len(diffs), 1)

    def test_bool_and_int_are_type_distinct(self):
        diffs = strict.strict_semantic_diff({"x": True}, {"x": 1})
        self.assertEqual(diffs[0].kind, "type")

    def test_nonfinite_direct_value_rejected(self):
        with self.assertRaises(strict.EvidenceError):
            strict.strict_semantic_diff({"x": float("nan")}, {"x": 1})

    def test_negative_or_nonfinite_tolerance_rejected(self):
        with self.assertRaises(strict.EvidenceError):
            strict.strict_semantic_diff(1, 1, abs_tol=-1)
        with self.assertRaises(strict.EvidenceError):
            strict.strict_semantic_diff(1, 1, rel_tol=float("inf"))


class CaptureValidationTests(unittest.TestCase):
    def test_valid_capture_is_recomputed(self):
        bundle = capture({"market": [["SELL", "MILK", 1]]})
        got = strict.validate_capture_bundle(bundle)
        self.assertTrue(got.deterministic)
        self.assertEqual(got.action_sha256, strict.sha256_json(bundle["action"]))
        self.assertEqual(got.endpoint, bundle["endpoint"])

    def test_forged_state_hash_rejected(self):
        bundle = capture({"x": 1})
        bundle["state_sha256"] = "0" * 64
        with self.assertRaises(strict.EvidenceError):
            strict.validate_capture_bundle(bundle)

    def test_forged_request_hash_rejected(self):
        bundle = capture({"x": 1})
        bundle["request_sha256"] = "1" * 64
        with self.assertRaises(strict.EvidenceError):
            strict.validate_capture_bundle(bundle)

    def test_missing_state_rejected(self):
        bundle = capture({"x": 1})
        del bundle["state"]
        with self.assertRaises(strict.EvidenceError):
            strict.validate_capture_bundle(bundle)

    def test_missing_endpoint_rejected(self):
        bundle = capture({"x": 1})
        del bundle["endpoint"]
        with self.assertRaises(strict.EvidenceError):
            strict.validate_capture_bundle(bundle)

    def test_forged_action_hash_rejected(self):
        bundle = capture({"x": 1})
        bundle["samples"][0]["action_sha256"] = "2" * 64
        with self.assertRaises(strict.EvidenceError):
            strict.validate_capture_bundle(bundle)

    def test_raw_response_projection_mismatch_rejected(self):
        bundle = capture({"x": 1})
        bundle["samples"][0]["action"] = {"x": 2}
        bundle["samples"][0]["action_sha256"] = strict.sha256_json({"x": 2})
        bundle["action"] = {"x": 2}
        bundle["action_sha256"] = strict.sha256_json({"x": 2})
        with self.assertRaises(strict.EvidenceError):
            strict.validate_capture_bundle(bundle)

    def test_unwrap_path_mismatch_rejected(self):
        bundle = capture({"x": 1})
        bundle["samples"][0]["unwrap_path"] = []
        with self.assertRaises(strict.EvidenceError):
            strict.validate_capture_bundle(bundle)

    def test_sample_count_mismatch_rejected(self):
        bundle = capture({"x": 1})
        bundle["sample_count"] = 2
        with self.assertRaises(strict.EvidenceError):
            strict.validate_capture_bundle(bundle)

    def test_unstable_capture_holds_instead_of_comparing_sample_zero(self):
        left = capture(
            {"x": 1}, samples=[_sample({"x": 1}), _sample({"x": 2})], name="left"
        )
        right = capture({"x": 1}, name="right")
        report = strict.compare_validated_captures(left, right)
        self.assertEqual(report["verdict"], "HOLD_UNSTABLE")
        self.assertIsNone(report["summary"]["equal"])

    def test_parent_unordered_diagnostic_does_not_override_instability(self):
        a = [{"id": "A"}, {"id": "B"}]
        b = [{"id": "B"}, {"id": "A"}]
        left = capture(a, samples=[_sample(a), _sample(b)], name="left")
        self.assertIsNone(left["first_internal_difference"])
        report = strict.compare_validated_captures(left, capture(a, name="right"))
        self.assertEqual(report["verdict"], "HOLD_UNSTABLE")

    def test_different_states_fail_closed(self):
        with self.assertRaises(strict.EvidenceError):
            strict.compare_validated_captures(
                capture({"x": 1}, state={"step": 1}),
                capture({"x": 1}, state={"step": 2}),
            )

    def test_pair_report_explicitly_disclaims_trajectory_and_causality(self):
        report = strict.compare_validated_captures(
            capture({"x": 1}, name="left", endpoint="https://left.invalid"),
            capture({"x": 2}, name="right", endpoint="https://right.invalid"),
        )
        self.assertEqual(report["scope"], "single_pair_only")
        self.assertIs(report["trajectory_claim"], False)
        self.assertIs(report["causality_claim"], False)
        self.assertEqual(report["verdict"], "DIFFERENT")
        self.assertNotIn("first_temporal_divergence", report)
        self.assertFalse(hasattr(strict, "validate_temporal_ledger"))
        self.assertFalse(hasattr(strict, "STRICT_LEDGER_FORMAT"))


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_object_key_rejected_at_any_depth(self):
        with self.assertRaises(strict.EvidenceError):
            strict.strict_loads('{"x":{"a":1,"a":2}}')

    def test_nan_constant_rejected(self):
        with self.assertRaises(strict.EvidenceError):
            strict.strict_loads('{"x":NaN}')

    def test_infinity_constant_rejected(self):
        with self.assertRaises(strict.EvidenceError):
            strict.strict_loads('{"x":Infinity}')

    def test_overflowing_float_rejected(self):
        with self.assertRaises(strict.EvidenceError):
            strict.strict_loads('{"x":1e9999}')


class PathCustodyTests(unittest.TestCase):
    def test_symlink_input_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.json"
            real.write_text("{}", encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(real)
            with self.assertRaises(strict.EvidenceError):
                strict.validate_path_separation([link], [])

    def test_hardlink_input_alias_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = root / "a.json"
            second = root / "b.json"
            first.write_text("{}", encoding="utf-8")
            os.link(first, second)
            with self.assertRaises(strict.EvidenceError):
                strict.validate_path_separation([first, second], [])

    def test_output_alias_to_input_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "same.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(strict.EvidenceError):
                strict.validate_path_separation([path], [path])

    def test_output_symlink_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "in.json"
            target = root / "target.json"
            out = root / "out.json"
            inp.write_text("{}", encoding="utf-8")
            target.write_text("{}", encoding="utf-8")
            out.symlink_to(target)
            with self.assertRaises(strict.EvidenceError):
                strict.validate_path_separation([inp], [out])

    def test_atomic_write_roundtrip_and_self_seal(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "report.json"
            report = strict.compare_validated_captures(
                capture({"x": 1}, name="left"), capture({"x": 1}, name="right")
            )
            self.assertEqual(report["report_sha256"], strict._seal(report))
            strict.atomic_write_json(out, report)
            self.assertEqual(strict.strict_load_file(out), report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
