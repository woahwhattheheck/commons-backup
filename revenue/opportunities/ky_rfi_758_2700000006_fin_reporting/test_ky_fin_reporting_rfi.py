from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import ky_fin_reporting_rfi as subject

from ky_fin_reporting_rfi import (
    AUTHORITY_FALSE,
    CASE_SCHEMA,
    ContractError,
    compile_bundle,
    evaluate_case,
    evaluate_matrix,
    strict_loads,
    validate_manifest,
    verify_bundle,
)

ROOT = Path(__file__).resolve().parent
FIXTURES = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))
AS_OF = "2026-09-18T02:20:00Z"


def manifest():
    return copy.deepcopy(FIXTURES["manifest"])


def matrix():
    return copy.deepcopy(FIXTURES["matrix"])


def base_case(**updates):
    row = {
        "schema": CASE_SCHEMA,
        "case_id": "case-base-001",
        "report_id": "synthetic-report-001",
        "semantic_parity_evidenced": True,
        "source_lineage_complete": True,
        "access_model_mapped": True,
        "gcc_compatibility_evidenced": True,
        "accessibility_evidenced": True,
        "performance_target_met": True,
        "distribution_contract_evidenced": True,
        "migration_reconciled": True,
        "operability_dr_evidenced": True,
        "sensitive_production_data_present": False,
        "observed_at_utc": "2026-09-18T01:30:00Z",
    }
    row.update(updates)
    return row


class StrictBoundaryTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ContractError):
            strict_loads('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ContractError):
            strict_loads('{"a":NaN}')

    def test_unknown_case_key_rejected(self):
        row = base_case()
        row["surprise"] = True
        with self.assertRaises(ContractError):
            evaluate_case(row, AS_OF)

    def test_bool_alias_must_be_real_bool(self):
        with self.assertRaises(ContractError):
            evaluate_case(
                base_case(performance_target_met=1),
                AS_OF,
            )

    def test_future_evidence_rejected(self):
        with self.assertRaises(ContractError):
            evaluate_case(
                base_case(observed_at_utc="2026-09-18T02:21:00Z"),
                AS_OF,
            )

    def test_stale_evidence_rejected(self):
        with self.assertRaises(ContractError):
            evaluate_case(
                base_case(observed_at_utc="2026-09-01T02:20:00Z"),
                AS_OF,
            )


class ManifestTests(unittest.TestCase):
    def test_absent_buyer_packet_holds_response_content(self):
        state = validate_manifest(manifest(), AS_OF)
        self.assertEqual(
            state["source_authority_state"],
            "HOLD_BUYER_PACKET_REQUIRED",
        )
        self.assertEqual(state["response_window_state"], "OPEN_INTERNAL_BUILD")
        self.assertEqual(
            state["submission_state"],
            "HOLD_OWNER_AND_PORTAL_AUTHORITY",
        )
        self.assertEqual(
            state["commercial_follow_on_state"],
            "INTERNAL_HYPOTHESIS_NOT_SUBMITTED",
        )
        self.assertEqual(
            state["commercial_follow_on_price_usd_cents"],
            2_500_000,
        )
        for field in AUTHORITY_FALSE:
            self.assertFalse(state[field])

    def test_packet_cannot_self_attest_without_digest(self):
        doc = manifest()
        doc["buyer_packet"]["retained"] = True
        doc["buyer_packet"]["source_generation"] = "version-2"
        doc["buyer_packet"]["authority"] = "BUYER_PACKET"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_packet_cannot_self_attest_with_arbitrary_digest(self):
        doc = manifest()
        doc["buyer_packet"]["retained"] = True
        doc["buyer_packet"]["sha256"] = "a" * 64
        doc["buyer_packet"]["source_generation"] = "version-2"
        doc["buyer_packet"]["authority"] = "BUYER_PACKET"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_absent_packet_cannot_carry_fake_digest(self):
        doc = manifest()
        doc["buyer_packet"]["sha256"] = "0" * 64
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_research_lead_cannot_self_promote(self):
        doc = manifest()
        doc["research_leads"][0]["status"] = "BUYER_VERIFIED"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_secondary_source_cannot_be_future_dated(self):
        doc = manifest()
        doc["source_evidence"][0]["captured_at_utc"] = (
            "2026-09-18T02:21:00Z"
        )
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_stale_secondary_source_holds_internal_readiness(self):
        doc = manifest()
        doc["source_evidence"][0]["captured_at_utc"] = (
            "2026-09-15T02:10:00Z"
        )
        state = validate_manifest(doc, AS_OF)
        self.assertEqual(
            state["response_window_state"],
            "HOLD_SOURCE_REFRESH_REQUIRED",
        )

    def test_response_cannot_authorize_send(self):
        doc = manifest()
        doc["response_posture"]["external_send_authorized"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_commercial_hypothesis_cannot_leak_into_rfi(self):
        doc = manifest()
        doc["commercial_follow_on"]["included_in_rfi_response"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_commercial_hypothesis_cannot_self_accept(self):
        doc = manifest()
        doc["commercial_follow_on"]["state"] = "ACCEPTED"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_commercial_reference_price_drift_rejected(self):
        doc = manifest()
        doc["commercial_follow_on"]["price_usd_cents"] = 2_500_001
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_submission_authority_cannot_promote(self):
        doc = manifest()
        doc["authority"]["submission_authorized"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_vendor_registration_authority_cannot_promote(self):
        doc = manifest()
        doc["authority"]["vendor_registration_authorized"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_production_data_authority_cannot_promote(self):
        doc = manifest()
        doc["authority"]["production_data_authorized"] = True
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_close_deadline_drift_rejected(self):
        doc = manifest()
        doc["solicitation"]["close_utc"] = "2026-10-02T20:30:00Z"
        with self.assertRaises(ContractError):
            validate_manifest(doc, AS_OF)

    def test_closed_window_is_not_internal_ready(self):
        state = validate_manifest(
            manifest(),
            "2026-10-02T19:30:00Z",
        )
        self.assertEqual(state["response_window_state"], "HOLD_CLOSED_WINDOW")
        self.assertFalse(state["submission_authorized"])


class DiscoveryCaseTests(unittest.TestCase):
    def test_complete_synthetic_case_is_evidence_ready(self):
        result = evaluate_case(base_case(), AS_OF)
        self.assertEqual(result["decision"], "DISCOVERY_EVIDENCE_READY")
        for field in AUTHORITY_FALSE:
            self.assertFalse(result[field])

    def test_sensitive_production_data_dominates(self):
        result = evaluate_case(
            base_case(
                sensitive_production_data_present=True,
                semantic_parity_evidenced=False,
            ),
            AS_OF,
        )
        self.assertEqual(result["decision"], "REJECT_SENSITIVE_PRODUCTION_DATA")

    def test_semantic_gap_holds_before_later_gaps(self):
        result = evaluate_case(
            base_case(
                semantic_parity_evidenced=False,
                source_lineage_complete=False,
            ),
            AS_OF,
        )
        self.assertEqual(result["decision"], "HOLD_REPORT_SEMANTICS")

    def test_gcc_gap_holds(self):
        result = evaluate_case(
            base_case(gcc_compatibility_evidenced=False),
            AS_OF,
        )
        self.assertEqual(result["decision"], "HOLD_GCC_COMPATIBILITY")

    def test_migration_reconciliation_gap_holds(self):
        result = evaluate_case(
            base_case(migration_reconciled=False),
            AS_OF,
        )
        self.assertEqual(
            result["decision"],
            "HOLD_MIGRATION_RECONCILIATION",
        )


class MatrixAndBundleTests(unittest.TestCase):
    def test_fixture_matrix_covers_every_terminal_once(self):
        result = evaluate_matrix(matrix(), AS_OF)
        self.assertEqual(result["case_count"], 11)
        self.assertTrue(
            all(value == 1 for value in result["decision_counts"].values())
        )
        for field in AUTHORITY_FALSE:
            self.assertFalse(result[field])

    def test_duplicate_case_id_rejected(self):
        doc = matrix()
        doc["cases"][1]["case"]["case_id"] = (
            doc["cases"][0]["case"]["case_id"]
        )
        with self.assertRaises(ContractError):
            evaluate_matrix(doc, AS_OF)

    def test_expected_decision_mismatch_rejected(self):
        doc = matrix()
        doc["cases"][0]["expected_decision"] = "HOLD_REPORT_SEMANTICS"
        with self.assertRaises(ContractError):
            evaluate_matrix(doc, AS_OF)

    def test_missing_terminal_rejected(self):
        doc = matrix()
        doc["cases"] = [
            row
            for row in doc["cases"]
            if row["expected_decision"] != "HOLD_OPERABILITY_DR"
        ]
        with self.assertRaises(ContractError):
            evaluate_matrix(doc, AS_OF)

    def test_bundle_holds_content_and_submission(self):
        bundle = compile_bundle(manifest(), matrix(), AS_OF)
        self.assertEqual(
            bundle["response_content_state"],
            "HOLD_BUYER_PACKET_REQUIRED",
        )
        self.assertEqual(
            bundle["submission_state"],
            "HOLD_OWNER_AND_PORTAL_AUTHORITY",
        )
        for field in AUTHORITY_FALSE:
            self.assertFalse(bundle[field])
        self.assertTrue(
            verify_bundle(
                bundle,
                manifest(),
                matrix(),
                AS_OF,
            )
        )

    def test_bundle_tamper_detected(self):
        bundle = compile_bundle(manifest(), matrix(), AS_OF)
        forged = copy.deepcopy(bundle)
        forged["submission_state"] = "READY"
        self.assertFalse(
            verify_bundle(
                forged,
                manifest(),
                matrix(),
                AS_OF,
            )
        )

    def test_deterministic_recompile(self):
        one = compile_bundle(manifest(), matrix(), AS_OF)
        two = compile_bundle(manifest(), matrix(), AS_OF)
        self.assertEqual(one, two)

    def test_exported_authority_map_cannot_widen_compiled_or_verified_outputs(self):
        authority_fields = tuple(AUTHORITY_FALSE)
        original = subject.AUTHORITY_FALSE
        try:
            original["submission_authorized"] = True
            mutated = subject.compile_bundle(manifest(), matrix(), AS_OF)
            surfaces = [
                mutated,
                mutated["pursuit"],
                mutated["discovery_matrix"],
                *mutated["discovery_matrix"]["results"],
            ]
            for surface in surfaces:
                for field in authority_fields:
                    self.assertIs(surface[field], False)

            subject.AUTHORITY_FALSE = {"submission_authorized": True}
            rebound = subject.compile_bundle(manifest(), matrix(), AS_OF)
            surfaces = [
                rebound,
                rebound["pursuit"],
                rebound["discovery_matrix"],
                *rebound["discovery_matrix"]["results"],
            ]
            for surface in surfaces:
                for field in authority_fields:
                    self.assertIs(surface[field], False)

            forged = copy.deepcopy(rebound)
            forged["submission_authorized"] = True
            forged = subject.receipt(forged)
            self.assertFalse(
                subject.verify_bundle(
                    forged,
                    manifest(),
                    matrix(),
                    AS_OF,
                )
            )
        finally:
            original.clear()
            original.update({field: False for field in authority_fields})
            subject.AUTHORITY_FALSE = original


if __name__ == "__main__":
    unittest.main()
