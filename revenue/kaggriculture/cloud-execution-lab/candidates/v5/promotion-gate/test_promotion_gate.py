# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
import unittest

import promotion_gate as gate


def _rehash_manifest(manifest):
    body = {key: value for key, value in manifest.items() if key != "candidate_id"}
    manifest["candidate_id"] = "v5c:" + hashlib.sha256(
        json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    return manifest


def _manifest():
    body = {
        "schema": gate.IDENTITY_SCHEMA,
        "base_id": "titan-v5-main",
        "engine_id": "engine:abc",
        "opponent_pack_id": "frontier:1",
        "config_sha256": "a" * 64,
        "components": [
            {
                "name": "candidate",
                "source": "candidate.py",
                "source_sha256": "b" * 64,
                "activation": {
                    "mode": "config",
                    "equals": {
                        "t": "dict",
                        "v": [["feature", {"t": "bool", "v": True}]],
                    },
                },
            }
        ],
    }
    return _rehash_manifest({**body, "candidate_id": ""})


def _engagement(candidate_id):
    return {
        "classification": "ENGAGED",
        "observations": 8,
        "noop_threshold": 8,
        "divergence_count": 2,
        "engagement_rate": 0.25,
        "first_divergence": {
            "observation": 2,
            "key": {"seed": 7, "seat": 0, "step": 12, "phase": "market"},
            "control_fingerprint": "c" * 64,
            "candidate_fingerprint": "d" * 64,
        },
        "control_sequence_fingerprint": "e" * 64,
        "candidate_sequence_fingerprint": "f" * 64,
        "key_fields": ["seed", "seat", "step", "phase"],
        "control_id": "v5c:" + "1" * 64,
        "candidate_id": candidate_id,
    }


def _timing(count, *, wall, cpu):
    return {
        "count": count,
        "wall_seconds": dict(zip(("p50", "p95", "p99", "max"), wall)),
        "cpu_seconds": dict(zip(("p50", "p95", "p99", "max"), cpu)),
    }


def _runtime(candidate_id):
    overall = _timing(
        8,
        wall=(0.03, 0.06, 0.06, 0.06),
        cpu=(0.02, 0.05, 0.05, 0.05),
    )
    candidate = json.loads(json.dumps(overall))
    candidate["deadline_fallback_count"] = 0
    return {
        "classification": "PASS",
        "promotion_ready": True,
        "receipt_count": 8,
        "candidate_count": 1,
        "budget_seconds": 0.1,
        "reserve_seconds": 0.02,
        "usable_budget_seconds": 0.08,
        "p99_headroom_seconds": 0.02,
        "max_fallback_rate": 0.0,
        "deadline_fallback_count": 0,
        "deadline_fallback_rate": 0.0,
        "fallback_stage_counts": {},
        "expected_design_declared": True,
        "expected_callback_count": 8,
        "expected_complete": True,
        "missing_expected": [],
        "unexpected_extra": [],
        "overall": overall,
        "by_phase": {
            "early": _timing(
                2,
                wall=(0.01, 0.02, 0.02, 0.02),
                cpu=(0.01, 0.015, 0.015, 0.015),
            ),
            "mid": _timing(
                3,
                wall=(0.03, 0.04, 0.04, 0.04),
                cpu=(0.02, 0.03, 0.03, 0.03),
            ),
            "late": _timing(
                3,
                wall=(0.05, 0.06, 0.06, 0.06),
                cpu=(0.04, 0.05, 0.05, 0.05),
            ),
        },
        "by_candidate": {candidate_id: candidate},
        "phase_contract": {
            "total_steps": 720,
            "early": [0, 240],
            "mid": [240, 480],
            "late": [480, 720],
        },
    }


class PromotionGateTest(unittest.TestCase):
    def test_valid_cross_evidence_receipt(self):
        manifest = _manifest()
        engagement = _engagement(manifest["candidate_id"])
        runtime = _runtime(manifest["candidate_id"])
        receipt = gate.build_receipt(manifest, engagement, runtime)
        self.assertEqual("PASS", receipt["classification"])
        self.assertTrue(receipt["promotion_ready"])
        self.assertEqual(manifest["candidate_id"], receipt["candidate_id"])
        self.assertEqual(engagement["control_id"], receipt["control_id"])
        self.assertEqual(8, receipt["runtime"]["receipt_count"])
        self.assertEqual(
            {"candidate_manifest", "engagement_report", "runtime_report"},
            set(receipt["evidence_sha256"]),
        )

    def test_cross_build_engagement_is_rejected(self):
        manifest = _manifest()
        engagement = _engagement("v5c:" + "2" * 64)
        with self.assertRaisesRegex(gate.PromotionError, "does not match candidate manifest"):
            gate.build_receipt(manifest, engagement, _runtime(manifest["candidate_id"]))

    def test_noop_engagement_is_not_promotable(self):
        manifest = _manifest()
        engagement = _engagement(manifest["candidate_id"])
        engagement["classification"] = "NO_OP_OBSERVED"
        engagement["divergence_count"] = 0
        engagement["first_divergence"] = None
        with self.assertRaisesRegex(gate.PromotionError, "must be ENGAGED"):
            gate.build_receipt(manifest, engagement, _runtime(manifest["candidate_id"]))

    def test_impossible_engagement_summary_is_rejected(self):
        manifest = _manifest()
        candidate_id = manifest["candidate_id"]
        runtime = _runtime(candidate_id)
        cases = [
            (
                "rate",
                lambda report: report.__setitem__("engagement_rate", 0.5),
                "rate disagrees",
            ),
            (
                "threshold-type",
                lambda report: report.__setitem__("noop_threshold", True),
                "noop_threshold must be a plain int",
            ),
            (
                "impossible-first-index",
                lambda report: report["first_divergence"].__setitem__("observation", 8),
                "inconsistent with divergence count",
            ),
            (
                "duplicate-key-fields",
                lambda report: report.__setitem__("key_fields", ["seed", "seed"]),
                "key_fields must be unique",
            ),
            (
                "first-key-shape",
                lambda report: report["first_divergence"].__setitem__(
                    "key", {"seed": 7, "seat": 0, "step": 12}
                ),
                "key must match key_fields exactly",
            ),
            (
                "bad-decision-fingerprint",
                lambda report: report["first_divergence"].__setitem__(
                    "control_fingerprint", "not-a-sha"
                ),
                "64 lowercase hex",
            ),
            (
                "non-divergent-fingerprints",
                lambda report: report["first_divergence"].__setitem__(
                    "candidate_fingerprint",
                    report["first_divergence"]["control_fingerprint"],
                ),
                "fingerprints must differ",
            ),
            (
                "bad-sequence-fingerprint",
                lambda report: report.__setitem__(
                    "candidate_sequence_fingerprint", "0" * 63
                ),
                "64 lowercase hex",
            ),
            (
                "missing-first-divergence",
                lambda report: report.__setitem__("first_divergence", None),
                "requires first_divergence object",
            ),
        ]
        for label, mutate, message in cases:
            with self.subTest(label=label):
                engagement = json.loads(json.dumps(_engagement(candidate_id)))
                mutate(engagement)
                with self.assertRaisesRegex(gate.PromotionError, message):
                    gate.build_receipt(manifest, engagement, runtime)

    def test_stale_runtime_pass_with_extra_callback_is_rejected(self):
        manifest = _manifest()
        runtime = _runtime(manifest["candidate_id"])
        runtime["unexpected_extra"] = [
            {"candidate": manifest["candidate_id"], "seed": 9, "seat": 0, "step": 1}
        ]
        with self.assertRaisesRegex(gate.PromotionError, "unexpected callbacks"):
            gate.build_receipt(
                manifest, _engagement(manifest["candidate_id"]), runtime
            )

    def test_runtime_must_be_candidate_pure(self):
        manifest = _manifest()
        runtime = _runtime(manifest["candidate_id"])
        runtime["candidate_count"] = 2
        runtime["by_candidate"]["v5c:" + "3" * 64] = {
            **json.loads(json.dumps(runtime["overall"])),
            "deadline_fallback_count": 0,
        }
        with self.assertRaisesRegex(gate.PromotionError, "exactly one candidate"):
            gate.build_receipt(
                manifest, _engagement(manifest["candidate_id"]), runtime
            )

    def test_manifest_id_tamper_is_rejected(self):
        manifest = _manifest()
        manifest["base_id"] = "other-base"
        with self.assertRaisesRegex(gate.PromotionError, "does not match manifest body"):
            gate.build_receipt(
                manifest,
                _engagement(manifest["candidate_id"]),
                _runtime(manifest["candidate_id"]),
            )

    def test_self_hashed_noncanonical_component_is_rejected(self):
        manifest = _manifest()
        manifest["components"][0]["invented"] = True
        _rehash_manifest(manifest)
        with self.assertRaisesRegex(gate.PromotionError, "exact canonical component keys"):
            gate.build_receipt(
                manifest,
                _engagement(manifest["candidate_id"]),
                _runtime(manifest["candidate_id"]),
            )

    def test_self_hashed_component_order_and_uniqueness_are_rejected(self):
        manifest = _manifest()
        first = manifest["components"][0]
        second = {
            "name": "aaa",
            "source": "aaa.py",
            "source_sha256": "c" * 64,
            "activation": {"mode": "unconditional"},
        }
        manifest["components"] = [first, second]
        _rehash_manifest(manifest)
        with self.assertRaisesRegex(gate.PromotionError, "must be sorted by name"):
            gate.build_receipt(
                manifest,
                _engagement(manifest["candidate_id"]),
                _runtime(manifest["candidate_id"]),
            )

        manifest = _manifest()
        duplicate = json.loads(json.dumps(manifest["components"][0]))
        duplicate["source"] = "other.py"
        duplicate["source_sha256"] = "c" * 64
        manifest["components"].append(duplicate)
        _rehash_manifest(manifest)
        with self.assertRaisesRegex(gate.PromotionError, "names must be unique"):
            gate.build_receipt(
                manifest,
                _engagement(manifest["candidate_id"]),
                _runtime(manifest["candidate_id"]),
            )

    def test_self_hashed_noncanonical_typed_activation_is_rejected(self):
        manifest = _manifest()
        manifest["components"][0]["activation"]["equals"] = {
            "t": "dict",
            "v": [
                ["z", {"t": "int", "v": "01"}],
                ["a", {"t": "bool", "v": True}],
            ],
        }
        _rehash_manifest(manifest)
        with self.assertRaises(gate.PromotionError):
            gate.build_receipt(
                manifest,
                _engagement(manifest["candidate_id"]),
                _runtime(manifest["candidate_id"]),
            )

    def test_self_hashed_empty_or_reserved_config_activation_is_rejected(self):
        manifest = _manifest()
        manifest["components"][0]["activation"]["equals"] = {
            "t": "dict",
            "v": [],
        }
        _rehash_manifest(manifest)
        with self.assertRaisesRegex(gate.PromotionError, "must be non-empty"):
            gate.build_receipt(
                manifest,
                _engagement(manifest["candidate_id"]),
                _runtime(manifest["candidate_id"]),
            )

        manifest = _manifest()
        manifest["components"][0]["activation"]["equals"] = {
            "t": "dict",
            "v": [["_meta", {"t": "bool", "v": True}]],
        }
        _rehash_manifest(manifest)
        with self.assertRaisesRegex(gate.PromotionError, "reserved metadata keys"):
            gate.build_receipt(
                manifest,
                _engagement(manifest["candidate_id"]),
                _runtime(manifest["candidate_id"]),
            )

    def test_engagement_shape_is_exact_after_semantic_validation(self):
        manifest = _manifest()
        candidate_id = manifest["candidate_id"]
        engagement = _engagement(candidate_id)
        engagement["invented"] = True
        with self.assertRaisesRegex(gate.PromotionError, "engagement report keys mismatch"):
            gate.build_receipt(manifest, engagement, _runtime(candidate_id))

        engagement = _engagement(candidate_id)
        engagement["first_divergence"]["invented"] = True
        with self.assertRaisesRegex(gate.PromotionError, "first_divergence keys mismatch"):
            gate.build_receipt(manifest, engagement, _runtime(candidate_id))

    def test_runtime_headroom_is_recomputed(self):
        manifest = _manifest()
        runtime = _runtime(manifest["candidate_id"])
        for summary in (
            runtime["overall"],
            runtime["by_candidate"][manifest["candidate_id"]],
            runtime["by_phase"]["late"],
        ):
            summary["wall_seconds"]["p95"] = 0.09
            summary["wall_seconds"]["p99"] = 0.09
            summary["wall_seconds"]["max"] = 0.09
        with self.assertRaisesRegex(gate.PromotionError, "p99 headroom disagrees"):
            gate.build_receipt(
                manifest, _engagement(manifest["candidate_id"]), runtime
            )

    def test_runtime_summary_inconsistency_is_rejected(self):
        manifest = _manifest()
        runtime = _runtime(manifest["candidate_id"])
        runtime["deadline_fallback_count"] = 1
        with self.assertRaisesRegex(gate.PromotionError, "fallback count disagrees"):
            gate.build_receipt(
                manifest, _engagement(manifest["candidate_id"]), runtime
            )

    def test_runtime_report_shape_is_exact(self):
        manifest = _manifest()
        candidate_id = manifest["candidate_id"]
        for label, mutate in (
            ("missing", lambda report: report.pop("fallback_stage_counts")),
            ("extra", lambda report: report.__setitem__("invented", True)),
        ):
            with self.subTest(label=label):
                runtime = _runtime(candidate_id)
                mutate(runtime)
                with self.assertRaisesRegex(gate.PromotionError, "runtime report keys mismatch"):
                    gate.build_receipt(manifest, _engagement(candidate_id), runtime)

    def test_runtime_timing_summaries_are_producer_shaped(self):
        manifest = _manifest()
        candidate_id = manifest["candidate_id"]
        cases = [
            (
                "missing-cpu",
                lambda report: report["overall"].pop("cpu_seconds"),
                "exact timing-summary keys",
            ),
            (
                "nonmonotonic",
                lambda report: report["overall"]["wall_seconds"].__setitem__("p50", 0.07),
                "percentiles must be monotonic",
            ),
            (
                "candidate-drift",
                lambda report: report["by_candidate"][candidate_id]["wall_seconds"].__setitem__(
                    "p50", 0.031
                ),
                "candidate timing summary must equal overall",
            ),
        ]
        for label, mutate, message in cases:
            with self.subTest(label=label):
                runtime = _runtime(candidate_id)
                mutate(runtime)
                with self.assertRaisesRegex(gate.PromotionError, message):
                    gate.build_receipt(manifest, _engagement(candidate_id), runtime)

    def test_runtime_nearest_rank_identity_is_exact(self):
        manifest = _manifest()
        candidate_id = manifest["candidate_id"]

        runtime = _runtime(candidate_id)
        runtime["by_phase"]["early"]["wall_seconds"] = {
            "p50": 0.01,
            "p95": 0.015,
            "p99": 0.018,
            "max": 0.02,
        }
        with self.assertRaisesRegex(gate.PromotionError, "nearest-rank identity"):
            gate.build_receipt(manifest, _engagement(candidate_id), runtime)

        runtime = _runtime(candidate_id)
        runtime["overall"]["wall_seconds"] = {
            "p50": 0.03,
            "p95": 0.055,
            "p99": 0.058,
            "max": 0.06,
        }
        runtime["by_candidate"][candidate_id]["wall_seconds"] = dict(
            runtime["overall"]["wall_seconds"]
        )
        with self.assertRaisesRegex(gate.PromotionError, "nearest-rank identity"):
            gate.build_receipt(manifest, _engagement(candidate_id), runtime)

        for count, values in (
            (1, (0.01, 0.02, 0.03, 0.04)),
            (2, (0.01, 0.02, 0.03, 0.04)),
            (3, (0.01, 0.02, 0.03, 0.04)),
            (8, (0.01, 0.02, 0.03, 0.04)),
        ):
            with self.subTest(count=count):
                stats = dict(zip(("p50", "p95", "p99", "max"), values))
                with self.assertRaisesRegex(gate.PromotionError, "nearest-rank identity"):
                    gate._validate_stats(stats, "runtime timing", count=count)

    def test_runtime_phase_partition_and_contract_are_exact(self):
        manifest = _manifest()
        candidate_id = manifest["candidate_id"]

        runtime = _runtime(candidate_id)
        runtime["by_phase"]["early"]["count"] = 1
        for metric in ("wall_seconds", "cpu_seconds"):
            maximum = runtime["by_phase"]["early"][metric]["max"]
            runtime["by_phase"]["early"][metric] = {
                key: maximum for key in ("p50", "p95", "p99", "max")
            }
        with self.assertRaisesRegex(gate.PromotionError, "counts must sum"):
            gate.build_receipt(manifest, _engagement(candidate_id), runtime)

        runtime = _runtime(candidate_id)
        runtime["phase_contract"]["mid"] = [241, 480]
        with self.assertRaisesRegex(gate.PromotionError, "boundary is noncanonical"):
            gate.build_receipt(manifest, _engagement(candidate_id), runtime)

        runtime = _runtime(candidate_id)
        runtime["by_phase"]["late"]["wall_seconds"] = {
            "p50": 0.05,
            "p95": 0.05,
            "p99": 0.05,
            "max": 0.05,
        }
        with self.assertRaisesRegex(gate.PromotionError, "max disagrees with overall"):
            gate.build_receipt(manifest, _engagement(candidate_id), runtime)

    def test_runtime_fallback_stage_counts_close_fallback_evidence(self):
        manifest = _manifest()
        candidate_id = manifest["candidate_id"]
        runtime = _runtime(candidate_id)
        runtime["deadline_fallback_count"] = 1
        runtime["deadline_fallback_rate"] = 0.125
        runtime["max_fallback_rate"] = 0.2
        runtime["by_candidate"][candidate_id]["deadline_fallback_count"] = 1
        with self.assertRaisesRegex(gate.PromotionError, "must sum to fallback count"):
            gate.build_receipt(manifest, _engagement(candidate_id), runtime)

        runtime["fallback_stage_counts"] = {"selected_transform": 1}
        receipt = gate.build_receipt(manifest, _engagement(candidate_id), runtime)
        self.assertTrue(receipt["promotion_ready"])

    def test_runtime_empty_phase_requires_null_stats(self):
        manifest = _manifest()
        candidate_id = manifest["candidate_id"]
        runtime = _runtime(candidate_id)
        runtime["by_phase"]["early"] = {
            "count": 0,
            "wall_seconds": {"p50": None, "p95": None, "p99": None, "max": None},
            "cpu_seconds": {"p50": None, "p95": None, "p99": None, "max": None},
        }
        runtime["by_phase"]["mid"]["count"] = 5
        receipt = gate.build_receipt(manifest, _engagement(candidate_id), runtime)
        self.assertTrue(receipt["promotion_ready"])

        runtime = _runtime(candidate_id)
        runtime["by_phase"]["early"] = {
            "count": 0,
            "wall_seconds": {"p50": 0.0, "p95": None, "p99": None, "max": None},
            "cpu_seconds": {"p50": None, "p95": None, "p99": None, "max": None},
        }
        runtime["by_phase"]["mid"]["count"] = 5
        with self.assertRaisesRegex(gate.PromotionError, "only null stats"):
            gate.build_receipt(manifest, _engagement(candidate_id), runtime)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_constants(self):
        with self.assertRaisesRegex(gate.PromotionError, "duplicate JSON object key"):
            gate._loads_strict('{"candidate_id":"a","candidate_id":"b"}')
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(gate.PromotionError, "non-finite"):
                    gate._loads_strict('{"x":' + token + "}")


if __name__ == "__main__":
    unittest.main()
