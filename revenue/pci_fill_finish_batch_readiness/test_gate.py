from __future__ import annotations

import copy
import hashlib
import unittest

from revenue.pci_fill_finish_batch_readiness.gate import (
    DEFAULT_MAX_DECISION_AGE_SECONDS,
    ReadinessError,
    canonical_json,
    evaluate,
    normalize_packet,
    verify_decision,
)

AS_OF = "2026-09-13T11:00:00Z"
VERIFY_AT = "2026-09-13T11:01:00Z"


def h(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def packet() -> dict:
    approved_digest = h("recipe-approved-v7")
    return {
        "schema_version": "pci.fill-finish-batch-readiness/v2",
        "packet_id": "packet-001",
        "batch_id": "batch-001",
        "planned_slot_at": "2026-09-13T12:00:00Z",
        "recipe": {
            "recipe_id": "recipe-sterile-A",
            "version": "v7",
            "approved": True,
            "approved_digest": approved_digest,
            "observed_at": "2026-09-13T10:54:00Z",
            "scheduled_recipe_id": "recipe-sterile-A",
            "scheduled_version": "v7",
            "required_material_components": ["drug-A", "excipient-B"],
            "required_equipment_ids": ["filler-1", "isolator-1"],
        },
        "materials": [
            {
                "lot_id": "lot-drug-1",
                "component": "drug-A",
                "released": True,
                "release_digest": h("lot-drug-1-release"),
                "observed_at": "2026-09-13T10:55:00Z",
            },
            {
                "lot_id": "lot-excipient-1",
                "component": "excipient-B",
                "released": True,
                "release_digest": h("lot-excipient-1-release"),
                "observed_at": "2026-09-13T10:55:00Z",
            },
        ],
        "equipment": [
            {
                "equipment_id": "filler-1",
                "calibration_valid_until": "2026-09-14T00:00:00Z",
                "calibration_digest": h("filler-1-cal"),
                "observed_at": "2026-09-13T10:56:00Z",
            },
            {
                "equipment_id": "isolator-1",
                "calibration_valid_until": "2026-09-14T00:00:00Z",
                "calibration_digest": h("isolator-1-cal"),
                "observed_at": "2026-09-13T10:56:00Z",
            },
        ],
        "environment": {
            "isolator_state": "READY",
            "em_state": "PASS",
            "captured_at": "2026-09-13T10:57:00Z",
            "valid_until": "2026-09-13T12:30:00Z",
            "evidence_digest": h("environment-ready"),
        },
        "fill_inspection": {
            "fill_weight_batch_id": "batch-001",
            "inspection_batch_id": "batch-001",
            "recipe_digest": approved_digest,
            "fill_weight_digest": h("fill-weight"),
            "inspection_digest": h("inspection"),
            "observed_at": "2026-09-13T10:58:00Z",
        },
        "bom": {
            "required": [
                {"component_id": "label-A", "version": "v2"},
                {"component_id": "device-A", "version": "v5"},
            ],
            "staged": [
                {"component_id": "device-A", "version": "v5"},
                {"component_id": "label-A", "version": "v2"},
            ],
            "evidence_digest": h("bom"),
            "observed_at": "2026-09-13T10:59:00Z",
        },
    }


def trusted_definition() -> dict:
    return {
        "recipe_id": "recipe-sterile-A",
        "version": "v7",
        "approved_digest": h("recipe-approved-v7"),
        "required_material_components": ["drug-A", "excipient-B"],
        "required_equipment_ids": ["filler-1", "isolator-1"],
        "required_bom": [
            {"component_id": "label-A", "version": "v2"},
            {"component_id": "device-A", "version": "v5"},
        ],
    }


def evaluate_packet(raw, *, trusted_as_of=AS_OF, definition=None):
    return evaluate(
        raw,
        trusted_as_of=trusted_as_of,
        trusted_definition=trusted_definition() if definition is None else definition,
    )


def verify_packet(raw, decision, *, definition=None, **kwargs):
    return verify_decision(
        raw,
        decision,
        trusted_definition=trusted_definition() if definition is None else definition,
        **kwargs,
    )


class ReadinessV2Tests(unittest.TestCase):
    def test_complete_packet_is_ready(self):
        decision = evaluate_packet(packet(), trusted_as_of=AS_OF)
        self.assertEqual(decision["status"], "READY")
        self.assertEqual(decision["hold_reasons"], [])
        self.assertEqual(decision["evaluated_at"], AS_OF)

    def test_packet_cannot_choose_its_own_as_of(self):
        raw = packet()
        raw["as_of"] = "2020-01-01T00:00:00Z"
        with self.assertRaisesRegex(ReadinessError, "PACKET_FIELDS"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_missing_required_material_holds(self):
        raw = packet()
        raw["materials"] = raw["materials"][:1]
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        self.assertEqual(decision["hold_reasons"], ["MATERIAL_COVERAGE_MISMATCH"])

    def test_extra_material_holds(self):
        raw = packet()
        raw["materials"].append(
            {
                "lot_id": "lot-extra-1",
                "component": "unapproved-C",
                "released": True,
                "release_digest": h("extra-release"),
                "observed_at": "2026-09-13T10:55:00Z",
            }
        )
        self.assertIn("MATERIAL_COVERAGE_MISMATCH", evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"])

    def test_missing_required_equipment_holds(self):
        raw = packet()
        raw["equipment"] = raw["equipment"][:1]
        self.assertEqual(evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"], ["EQUIPMENT_COVERAGE_MISMATCH"])

    def test_extra_equipment_holds(self):
        raw = packet()
        raw["equipment"].append(
            {
                "equipment_id": "pump-9",
                "calibration_valid_until": "2026-09-14T00:00:00Z",
                "calibration_digest": h("pump-9-cal"),
                "observed_at": "2026-09-13T10:56:00Z",
            }
        )
        self.assertIn("EQUIPMENT_COVERAGE_MISMATCH", evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"])

    def test_duplicate_recipe_requirements_fail_closed(self):
        raw = packet()
        raw["recipe"]["required_material_components"].append("drug-A")
        with self.assertRaisesRegex(ReadinessError, "DUPLICATE_RECIPE_REQUIREMENT"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_unreleased_material_holds(self):
        raw = packet()
        raw["materials"][0]["released"] = False
        self.assertEqual(evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"], ["MATERIAL_UNRELEASED"])

    def test_expired_calibration_holds(self):
        raw = packet()
        raw["equipment"][0]["calibration_valid_until"] = "2026-09-13T11:59:59Z"
        self.assertEqual(evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"], ["CALIBRATION_EXPIRED"])

    def test_environment_state_holds(self):
        raw = packet()
        raw["environment"]["em_state"] = "HOLD"
        self.assertEqual(evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"], ["ENVIRONMENT_HOLD"])

    def test_environment_must_be_valid_through_slot(self):
        raw = packet()
        raw["environment"]["valid_until"] = "2026-09-13T11:59:59Z"
        self.assertEqual(evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"], ["ENVIRONMENT_STALE_FOR_SLOT"])

    def test_environment_validity_cannot_precede_capture(self):
        raw = packet()
        raw["environment"]["valid_until"] = "2026-09-13T10:56:59Z"
        with self.assertRaisesRegex(ReadinessError, "ENVIRONMENT_VALIDITY_BEFORE_CAPTURE"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_recipe_mismatch_holds(self):
        raw = packet()
        raw["recipe"]["scheduled_version"] = "v8"
        self.assertEqual(evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"], ["RECIPE_MISMATCH"])

    def test_inspection_lineage_mismatch_holds(self):
        raw = packet()
        raw["fill_inspection"]["inspection_batch_id"] = "batch-999"
        self.assertEqual(evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"], ["INSPECTION_LINEAGE_MISMATCH"])

    def test_bom_mismatch_holds(self):
        raw = packet()
        raw["bom"]["staged"][0]["version"] = "v6"
        self.assertEqual(evaluate_packet(raw, trusted_as_of=AS_OF)["hold_reasons"], ["BOM_MISMATCH"])

    def test_all_evidence_observation_times_are_fenced_by_trusted_as_of(self):
        mutations = [
            lambda x: x["recipe"].__setitem__("observed_at", "2026-09-13T11:00:01Z"),
            lambda x: x["materials"][0].__setitem__("observed_at", "2026-09-13T11:00:01Z"),
            lambda x: x["equipment"][0].__setitem__("observed_at", "2026-09-13T11:00:01Z"),
            lambda x: x["environment"].__setitem__("captured_at", "2026-09-13T11:00:01Z"),
            lambda x: x["fill_inspection"].__setitem__("observed_at", "2026-09-13T11:00:01Z"),
            lambda x: x["bom"].__setitem__("observed_at", "2026-09-13T11:00:01Z"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                raw = packet()
                mutate(raw)
                with self.assertRaisesRegex(ReadinessError, "EVIDENCE_AFTER_TRUSTED_AS_OF"):
                    evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_trusted_as_of_cannot_be_after_planned_slot(self):
        with self.assertRaisesRegex(ReadinessError, "TRUSTED_AS_OF_AFTER_PLANNED_SLOT"):
            evaluate_packet(packet(), trusted_as_of="2026-09-13T12:00:01Z")

    def test_input_order_is_canonical(self):
        a = packet()
        b = copy.deepcopy(a)
        b["materials"] = list(reversed(b["materials"]))
        b["equipment"] = list(reversed(b["equipment"]))
        b["recipe"]["required_material_components"] = list(reversed(b["recipe"]["required_material_components"]))
        b["recipe"]["required_equipment_ids"] = list(reversed(b["recipe"]["required_equipment_ids"]))
        b["bom"]["required"] = list(reversed(b["bom"]["required"]))
        self.assertEqual(evaluate_packet(a, trusted_as_of=AS_OF), evaluate_packet(b, trusted_as_of=AS_OF))

    def test_duplicate_material_lot_rejected(self):
        raw = packet()
        raw["materials"].append(copy.deepcopy(raw["materials"][0]))
        with self.assertRaisesRegex(ReadinessError, "DUPLICATE_MATERIAL_LOT"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_duplicate_equipment_rejected(self):
        raw = packet()
        raw["equipment"].append(copy.deepcopy(raw["equipment"][0]))
        with self.assertRaisesRegex(ReadinessError, "DUPLICATE_EQUIPMENT"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_duplicate_bom_pair_rejected(self):
        raw = packet()
        raw["bom"]["required"].append(copy.deepcopy(raw["bom"]["required"][0]))
        with self.assertRaisesRegex(ReadinessError, "DUPLICATE_BOM_COMPONENT"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_unknown_packet_key_rejected(self):
        raw = packet()
        raw["approval_override"] = True
        with self.assertRaisesRegex(ReadinessError, "PACKET_FIELDS"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_integer_cannot_alias_boolean(self):
        raw = packet()
        raw["recipe"]["approved"] = 1
        with self.assertRaisesRegex(ReadinessError, "BOOLEAN_REQUIRED"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_invalid_digest_rejected(self):
        raw = packet()
        raw["materials"][0]["release_digest"] = "0" * 63
        with self.assertRaisesRegex(ReadinessError, "INVALID_DIGEST"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_noncanonical_timestamp_rejected(self):
        raw = packet()
        raw["planned_slot_at"] = "2026-09-13T12:00:00+00:00"
        with self.assertRaisesRegex(ReadinessError, "NONCANONICAL_TIMESTAMP"):
            evaluate_packet(raw, trusted_as_of=AS_OF)

    def test_verify_decision_success(self):
        raw = packet()
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        verified = verify_packet(
            raw,
            decision,
            expected_evaluated_at=AS_OF,
            trusted_verify_at=VERIFY_AT,
        )
        self.assertTrue(verified["valid"])
        self.assertEqual(verified["age_seconds"], 60)

    def test_verifier_requires_out_of_band_evaluation_time(self):
        raw = packet()
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        with self.assertRaisesRegex(ReadinessError, "DECISION_MISMATCH"):
            verify_packet(
                raw,
                decision,
                expected_evaluated_at="2026-09-13T11:00:01Z",
                trusted_verify_at=VERIFY_AT,
            )

    def test_verify_before_evaluation_rejected(self):
        raw = packet()
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        with self.assertRaisesRegex(ReadinessError, "VERIFY_BEFORE_EVALUATION"):
            verify_packet(
                raw,
                decision,
                expected_evaluated_at=AS_OF,
                trusted_verify_at="2026-09-13T10:59:59Z",
            )

    def test_staleness_uses_exact_seconds_not_floor_minutes(self):
        raw = packet()
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        with self.assertRaisesRegex(ReadinessError, "DECISION_STALE"):
            verify_packet(
                raw,
                decision,
                expected_evaluated_at=AS_OF,
                trusted_verify_at="2026-09-14T11:00:01Z",
                max_age_seconds=DEFAULT_MAX_DECISION_AGE_SECONDS,
            )

    def test_exact_max_age_is_fresh(self):
        raw = packet()
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        verified = verify_packet(
            raw,
            decision,
            expected_evaluated_at=AS_OF,
            trusted_verify_at="2026-09-14T11:00:00Z",
            max_age_seconds=DEFAULT_MAX_DECISION_AGE_SECONDS,
        )
        self.assertEqual(verified["age_seconds"], DEFAULT_MAX_DECISION_AGE_SECONDS)

    def test_boolean_max_age_rejected(self):
        raw = packet()
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        with self.assertRaisesRegex(ReadinessError, "INVALID_MAX_AGE"):
            verify_packet(
                raw,
                decision,
                expected_evaluated_at=AS_OF,
                trusted_verify_at=VERIFY_AT,
                max_age_seconds=True,
            )

    def test_source_tamper_rejected(self):
        raw = packet()
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        changed = copy.deepcopy(raw)
        changed["materials"][0]["released"] = False
        with self.assertRaisesRegex(ReadinessError, "DECISION_MISMATCH"):
            verify_packet(
                changed,
                decision,
                expected_evaluated_at=AS_OF,
                trusted_verify_at=VERIFY_AT,
            )

    def test_decision_tamper_rejected(self):
        raw = packet()
        decision = evaluate_packet(raw, trusted_as_of=AS_OF)
        decision["authority"]["batch_release"] = True
        with self.assertRaisesRegex(ReadinessError, "DECISION_MISMATCH"):
            verify_packet(
                raw,
                decision,
                expected_evaluated_at=AS_OF,
                trusted_verify_at=VERIFY_AT,
            )

    def test_authority_ceiling_all_false(self):
        authority = evaluate_packet(packet(), trusted_as_of=AS_OF)["authority"]
        self.assertTrue(authority)
        self.assertTrue(all(value is False for value in authority.values()))

    def test_trusted_definition_digest_is_out_of_band_and_stable(self):
        first = evaluate_packet(packet())["trusted_definition_digest"]
        changed = packet()
        changed["recipe"]["required_material_components"] = ["drug-A"]
        changed["materials"] = changed["materials"][:1]
        decision = evaluate_packet(changed)
        self.assertEqual(first, decision["trusted_definition_digest"])
        self.assertEqual(decision["status"], "HOLD")
        self.assertIn("TRUSTED_DEFINITION_MISMATCH", decision["hold_reasons"])
        self.assertIn("MATERIAL_COVERAGE_MISMATCH", decision["hold_reasons"])

    def test_coordinated_material_shrink_cannot_replace_trust_root(self):
        raw = packet()
        raw["recipe"]["required_material_components"] = ["drug-A"]
        raw["materials"] = raw["materials"][:1]
        decision = evaluate_packet(raw)
        self.assertEqual(decision["status"], "HOLD")
        self.assertIn("TRUSTED_DEFINITION_MISMATCH", decision["hold_reasons"])
        self.assertIn("MATERIAL_COVERAGE_MISMATCH", decision["hold_reasons"])

    def test_coordinated_equipment_shrink_cannot_replace_trust_root(self):
        raw = packet()
        raw["recipe"]["required_equipment_ids"] = ["filler-1"]
        raw["equipment"] = raw["equipment"][:1]
        decision = evaluate_packet(raw)
        self.assertEqual(decision["status"], "HOLD")
        self.assertIn("TRUSTED_DEFINITION_MISMATCH", decision["hold_reasons"])
        self.assertIn("EQUIPMENT_COVERAGE_MISMATCH", decision["hold_reasons"])

    def test_coordinated_bom_shrink_cannot_replace_trust_root(self):
        raw = packet()
        raw["bom"]["required"] = raw["bom"]["required"][:1]
        raw["bom"]["staged"] = [copy.deepcopy(raw["bom"]["required"][0])]
        decision = evaluate_packet(raw)
        self.assertEqual(decision["status"], "HOLD")
        self.assertIn("TRUSTED_DEFINITION_MISMATCH", decision["hold_reasons"])
        self.assertIn("BOM_MISMATCH", decision["hold_reasons"])

    def test_trusted_definition_shape_is_strict(self):
        definition = trusted_definition()
        definition["packet_can_override"] = True
        with self.assertRaisesRegex(ReadinessError, "TRUSTED_DEFINITION_FIELDS"):
            evaluate_packet(packet(), definition=definition)

    def test_verifier_uses_same_out_of_band_definition(self):
        raw = packet()
        decision = evaluate_packet(raw)
        changed_definition = trusted_definition()
        changed_definition["required_material_components"] = ["drug-A"]
        with self.assertRaisesRegex(ReadinessError, "DECISION_MISMATCH"):
            verify_packet(
                raw,
                decision,
                definition=changed_definition,
                expected_evaluated_at=AS_OF,
                trusted_verify_at=VERIFY_AT,
            )

    def test_normalized_packet_has_no_caller_authored_clock(self):
        normalized = normalize_packet(packet(), trusted_as_of=AS_OF)
        self.assertNotIn("as_of", normalized)
        self.assertEqual(normalized["schema_version"], "pci.fill-finish-batch-readiness/v2")

    def test_canonical_json_is_byte_stable_for_equivalent_packets(self):
        a = evaluate_packet(packet(), trusted_as_of=AS_OF)
        b = copy.deepcopy(a)
        self.assertEqual(canonical_json(a), canonical_json(b))


if __name__ == "__main__":
    unittest.main()
