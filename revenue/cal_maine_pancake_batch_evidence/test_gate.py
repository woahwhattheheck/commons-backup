from __future__ import annotations

import copy
import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

from revenue.cal_maine_pancake_batch_evidence import gate

NOW = dt.datetime(2026, 9, 13, 14, 0, 0, tzinfo=dt.timezone.utc)


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = gate.acceptance_policy()
        self.packet = gate._base_packet("TEST-BATCH")

    def test_acceptance_contract(self) -> None:
        result = gate.run_acceptance()
        self.assertTrue(result["passed"])
        self.assertEqual(result["packet_count"], 256)
        self.assertEqual(result["clean_complete"], 128)
        self.assertEqual(result["seeded_defects"], 96)
        self.assertEqual(result["seeded_recalled"], 96)
        self.assertEqual(result["false_complete"], 0)
        self.assertTrue(result["three_manifests_byte_identical"])
        self.assertEqual(set(result["family_counts"].values()), {16})

    def test_clean_is_complete_and_verifies(self) -> None:
        compiled = gate.compile_packet(self.packet, self.policy, NOW)
        self.assertEqual(compiled["manifest"]["state"], "COMPLETE_FOR_OWNER_REVIEW")
        self.assertTrue(gate.verify_compiled(compiled))

    def test_every_defect_family_binds_field_and_source_hash(self) -> None:
        mutations = {
            "FORMULA_OR_ALLERGEN": ("egg_allergen_declaration", "MISSING"),
            "LABEL_OR_FILM": ("film_revision", "FILM-OLD"),
            "LINE_OR_CALIBRATION": ("line_id", "WRONG-LINE"),
            "COOK_PROCESS": ("finished_weight_g", 60),
            "METAL_DETECTOR": ("metal_detector_check", "MISSING"),
            "LOT_LINEAGE": ("finished_lot_lineage", ["EGGLOT-1"]),
        }
        for family, (field, value) in mutations.items():
            with self.subTest(family=family):
                packet = copy.deepcopy(self.packet)
                gate._set_value(packet, field, value)
                compiled = gate.compile_packet(packet, self.policy, NOW)
                defect = next(d for d in compiled["manifest"]["defects"] if d["family"] == family)
                self.assertEqual(defect["field"], f"evidence.{field}")
                self.assertRegex(defect["source_sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(compiled["manifest"]["state"], "HOLD_FOR_OWNER_REVIEW")

    def test_strict_json_rejects_duplicate_and_nonfinite(self) -> None:
        with self.assertRaises(gate.GateError):
            gate.strict_loads('{"a":1,"a":2}')
        with self.assertRaises(gate.GateError):
            gate.strict_loads('{"a":NaN}')

    def test_unknown_fields_rejected(self) -> None:
        packet = copy.deepcopy(self.packet)
        packet["extra"] = 1
        with self.assertRaises(gate.GateError):
            gate.compile_packet(packet, self.policy, NOW)

    def test_digest_drift_rejected(self) -> None:
        packet = copy.deepcopy(self.packet)
        packet["evidence"]["label_revision"]["value"] = "LABEL-TAMPER"
        with self.assertRaises(gate.GateError):
            gate.compile_packet(packet, self.policy, NOW)

    def test_generation_policy_and_export_fences(self) -> None:
        for mutate in ("generation", "revision", "export"):
            packet = copy.deepcopy(self.packet)
            if mutate == "generation":
                packet["source_generation"] = "OTHER-GEN"
            elif mutate == "revision":
                packet["policy_revision"] = 8
            else:
                packet["export_complete"] = False
            with self.subTest(mutate=mutate), self.assertRaises(gate.GateError):
                gate.compile_packet(packet, self.policy, NOW)

    def test_time_fences_stale_future_alias(self) -> None:
        packet = copy.deepcopy(self.packet)
        packet["capture_utc"] = "2026-09-13T11:59:59Z"
        with self.assertRaises(gate.GateError):
            gate.compile_packet(packet, self.policy, NOW)
        packet["capture_utc"] = "2026-09-13T14:00:01Z"
        with self.assertRaises(gate.GateError):
            gate.compile_packet(packet, self.policy, NOW)
        packet["capture_utc"] = "2026-09-13T13:00:00+00:00"
        with self.assertRaises(gate.GateError):
            gate.compile_packet(packet, self.policy, NOW)

    def test_bool_and_float_integer_traps(self) -> None:
        packet = copy.deepcopy(self.packet)
        packet["policy_revision"] = True
        with self.assertRaises(gate.GateError):
            gate.compile_packet(packet, self.policy, NOW)
        packet = copy.deepcopy(self.packet)
        packet["evidence"]["cook_temp_f"] = {"value": 350.0, "sha256": "0" * 64}
        with self.assertRaises(gate.GateError):
            gate.compile_packet(packet, self.policy, NOW)

    def test_order_invariance(self) -> None:
        packet = copy.deepcopy(self.packet)
        packet["evidence"] = dict(reversed(list(packet["evidence"].items())))
        a = gate.compile_packet(self.packet, self.policy, NOW)
        b = gate.compile_packet(packet, dict(reversed(list(self.policy.items()))), NOW)
        self.assertEqual(gate.canonical_bytes(a), gate.canonical_bytes(b))

    def test_manifest_and_receipt_tamper_rejected(self) -> None:
        compiled = gate.compile_packet(self.packet, self.policy, NOW)
        tampered = copy.deepcopy(compiled)
        tampered["manifest"]["state"] = "HOLD_FOR_OWNER_REVIEW"
        with self.assertRaises(gate.GateError):
            gate.verify_compiled(tampered)
        resealed = copy.deepcopy(tampered)
        resealed["receipt_sha256"] = gate.sha256_value(resealed["manifest"])
        with self.assertRaises(gate.GateError):
            gate.verify_compiled(resealed)

    def test_exact_replay_collapses_changed_replay_blocks(self) -> None:
        exact = [self.packet, copy.deepcopy(self.packet)]
        corpus = gate.compile_corpus(exact, self.policy, NOW)
        self.assertEqual(corpus["summary"]["unique_batch_count"], 1)
        self.assertEqual(corpus["summary"]["exact_replay_count"], 1)
        changed = copy.deepcopy(self.packet)
        gate._set_value(changed, "label_revision", "LABEL-18")
        with self.assertRaises(gate.GateError):
            gate.compile_corpus([self.packet, changed], self.policy, NOW)

    def test_policy_schema_and_range_validation(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["expected"]["cook_temp_f"] = [355, 345]
        with self.assertRaises(gate.GateError):
            gate.compile_packet(self.packet, policy, NOW)
        policy = copy.deepcopy(self.policy)
        policy["extra"] = True
        with self.assertRaises(gate.GateError):
            gate.compile_packet(self.packet, policy, NOW)

    def test_markdown_does_not_claim_release(self) -> None:
        compiled = gate.compile_packet(self.packet, self.policy, NOW)
        md = gate.markdown_projection(compiled)
        self.assertIn("owner review only", md)
        self.assertIn("not a food-safety conclusion", md)
        self.assertNotIn("APPROVED FOR RELEASE", md)

    def test_write_exclusive_refuses_overwrite_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "out.json"
            gate.write_exclusive(output, b"one")
            with self.assertRaises(gate.GateError):
                gate.write_exclusive(output, b"two")
            target = root / "target"
            target.write_bytes(b"x")
            link = root / "link"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink not supported")
            with self.assertRaises(gate.GateError):
                gate.write_exclusive(link, b"two")

    def test_read_bounded_regular_refuses_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "in.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "link.json"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink not supported")
            with self.assertRaises(gate.GateError):
                gate._read_bounded_regular(link)

    def test_cli_acceptance(self) -> None:
        self.assertEqual(gate.main(["acceptance"]), 0)


if __name__ == "__main__":
    unittest.main()
