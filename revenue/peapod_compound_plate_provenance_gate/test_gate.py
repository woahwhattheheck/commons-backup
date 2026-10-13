from __future__ import annotations

import copy
import json
import unittest

from .fixture import CLEAN_COUNT, DEFECT_COUNT, TOTAL_COUNT, build_synthetic_case
from .gate import (
    DEFECT_CODES,
    DUPLICATE_ASSIGNMENT,
    HOLD,
    ORPHANED_RUN_LINK,
    READY_FOR_SCREEN,
    SOURCE_DESTINATION_MISMATCH,
    STALE_PROTOCOL,
    VOLUME_BALANCE_FAILURE,
    WRONG_POOL_MEMBERSHIP,
    build_gate_artifacts,
    verify_gate_artifacts,
)


class ProvenanceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transfers, self.context, self.expected = build_synthetic_case()

    def build(self):
        return build_gate_artifacts(self.transfers, self.context)

    def test_exact_acceptance_contract(self) -> None:
        artifacts = self.build()
        summary = artifacts.manifest["summary"]
        self.assertEqual(TOTAL_COUNT, 384)
        self.assertEqual(CLEAN_COUNT, 360)
        self.assertEqual(DEFECT_COUNT, 24)
        self.assertEqual(summary["transfer_count"], 384)
        self.assertEqual(summary["ready_count"], 360)
        self.assertEqual(summary["hold_count"], 24)
        self.assertEqual(summary["defect_counts"], {code: 4 for code in DEFECT_CODES})

    def test_exact_planted_transfer_ids_and_codes(self) -> None:
        artifacts = self.build()
        held = {
            record["transfer_id"]: record["codes"]
            for record in artifacts.manifest["records"]
            if record["decision"] == HOLD
        }
        self.assertEqual(len(held), 24)
        for code, transfer_ids in self.expected.items():
            self.assertEqual(len(transfer_ids), 4)
            for transfer_id in transfer_ids:
                self.assertEqual(held[transfer_id], [code])

    def test_zero_defective_rows_are_ready(self) -> None:
        artifacts = self.build()
        expected_defective = {
            transfer_id
            for transfer_ids in self.expected.values()
            for transfer_id in transfer_ids
        }
        for record in artifacts.manifest["records"]:
            if record["transfer_id"] in expected_defective:
                self.assertEqual(record["decision"], HOLD)
                self.assertTrue(record["codes"])
            else:
                self.assertEqual(record["decision"], READY_FOR_SCREEN)
                self.assertEqual(record["codes"], [])


    def test_manifest_records_expose_full_reconciled_provenance(self) -> None:
        artifacts = self.build()
        record = artifacts.manifest["records"][0]
        expected = self.transfers[0]
        for key in (
            "compound_master_id", "source_vial_id", "source_plate_id", "source_well",
            "source_plate_lot", "source_volume_ul_before", "transfer_volume_ul",
            "source_volume_ul_after", "source_concentration_um", "membership_type",
            "pool_id", "destination_plate_id", "destination_well", "destination_plate_lot",
            "destination_compound_master_id", "assay_protocol_id", "assay_protocol_version",
            "control_well_map_hash", "instrument_run_id",
        ):
            self.assertEqual(record[key], expected[key])

    def test_reruns_are_byte_identical(self) -> None:
        first = self.build()
        second = self.build()
        self.assertEqual(first.json_bytes, second.json_bytes)
        self.assertEqual(first.csv_bytes, second.csv_bytes)
        self.assertEqual(first.manifest_sha256, second.manifest_sha256)
        self.assertEqual(first.csv_sha256, second.csv_sha256)

    def test_input_iteration_order_does_not_change_output(self) -> None:
        forward = self.build()
        reversed_artifacts = build_gate_artifacts(reversed(self.transfers), self.context)
        self.assertEqual(forward.json_bytes, reversed_artifacts.json_bytes)
        self.assertEqual(forward.csv_bytes, reversed_artifacts.csv_bytes)

    def test_verifier_accepts_exact_artifacts(self) -> None:
        artifacts = self.build()
        self.assertTrue(
            verify_gate_artifacts(
                artifacts.json_bytes,
                artifacts.csv_bytes,
                manifest_sha256=artifacts.manifest_sha256,
                csv_sha256=artifacts.csv_sha256,
            )
        )

    def test_verifier_rejects_json_tamper(self) -> None:
        artifacts = self.build()
        tampered = bytearray(artifacts.json_bytes)
        tampered[-2] = ord(" ")
        self.assertFalse(
            verify_gate_artifacts(
                bytes(tampered),
                artifacts.csv_bytes,
                manifest_sha256=artifacts.manifest_sha256,
                csv_sha256=artifacts.csv_sha256,
            )
        )

    def test_verifier_rejects_csv_tamper(self) -> None:
        artifacts = self.build()
        tampered = artifacts.csv_bytes.replace(b"READY_FOR_SCREEN", b"HOLD", 1)
        self.assertFalse(
            verify_gate_artifacts(
                artifacts.json_bytes,
                tampered,
                manifest_sha256=artifacts.manifest_sha256,
                csv_sha256=artifacts.csv_sha256,
            )
        )

    def test_duplicate_assignment_holds_only_later_assignment(self) -> None:
        artifacts = self.build()
        first = artifacts.manifest["records"][0]
        duplicate = artifacts.manifest["records"][360]
        self.assertEqual(first["decision"], READY_FOR_SCREEN)
        self.assertEqual(duplicate["codes"], [DUPLICATE_ASSIGNMENT])
        self.assertEqual(
            (first["destination_plate_id"], first["destination_well"]),
            (duplicate["destination_plate_id"], duplicate["destination_well"]),
        )

    def test_unknown_transfer_field_fails_closed(self) -> None:
        transfers = copy.deepcopy(self.transfers)
        transfers[0]["potency"] = "invented-scientific-payload"
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            build_gate_artifacts(transfers, self.context)

    def test_nonfinite_numeric_field_fails_closed(self) -> None:
        transfers = copy.deepcopy(self.transfers)
        transfers[0]["transfer_volume_ul"] = "NaN"
        with self.assertRaisesRegex(ValueError, "non-finite"):
            build_gate_artifacts(transfers, self.context)

    def test_duplicate_sequence_fails_closed(self) -> None:
        transfers = copy.deepcopy(self.transfers)
        transfers[1]["sequence"] = transfers[0]["sequence"]
        with self.assertRaisesRegex(ValueError, "duplicate sequence"):
            build_gate_artifacts(transfers, self.context)

    def test_duplicate_transfer_id_fails_closed(self) -> None:
        transfers = copy.deepcopy(self.transfers)
        transfers[1]["transfer_id"] = transfers[0]["transfer_id"]
        with self.assertRaisesRegex(ValueError, "duplicate transfer_id"):
            build_gate_artifacts(transfers, self.context)

    def test_context_unknown_field_fails_closed(self) -> None:
        context = copy.deepcopy(self.context)
        context["buyer_secret"] = "no"
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            build_gate_artifacts(self.transfers, context)

    def test_protocol_control_map_drift_holds(self) -> None:
        transfers = copy.deepcopy(self.transfers[:1])
        transfers[0]["control_well_map_hash"] = "sha256:wrong"
        artifacts = build_gate_artifacts(transfers, self.context)
        self.assertEqual(artifacts.manifest["records"][0]["codes"], [STALE_PROTOCOL])

    def test_run_plate_drift_holds(self) -> None:
        transfers = copy.deepcopy(self.transfers[:1])
        transfers[0]["instrument_run_id"] = "RUN-DST-002"
        artifacts = build_gate_artifacts(transfers, self.context)
        self.assertEqual(artifacts.manifest["records"][0]["codes"], [ORPHANED_RUN_LINK])

    def test_source_catalog_drift_holds(self) -> None:
        transfers = copy.deepcopy(self.transfers[:1])
        transfers[0]["source_vial_id"] = "VIAL-WRONG"
        artifacts = build_gate_artifacts(transfers, self.context)
        self.assertEqual(
            artifacts.manifest["records"][0]["codes"], [SOURCE_DESTINATION_MISMATCH]
        )

    def test_volume_overspend_holds(self) -> None:
        transfers = copy.deepcopy(self.transfers[:1])
        transfers[0]["transfer_volume_ul"] = "999"
        artifacts = build_gate_artifacts(transfers, self.context)
        self.assertEqual(artifacts.manifest["records"][0]["codes"], [VOLUME_BALANCE_FAILURE])

    def test_pool_membership_holds(self) -> None:
        transfers = copy.deepcopy(self.transfers[180:181])
        transfers[0]["pool_id"] = "POOL-030"
        if transfers[0]["compound_master_id"] in self.context["pools"]["POOL-030"]:
            transfers[0]["pool_id"] = "POOL-029"
        artifacts = build_gate_artifacts(transfers, self.context)
        self.assertEqual(artifacts.manifest["records"][0]["codes"], [WRONG_POOL_MEMBERSHIP])

    def test_authority_is_evidence_only(self) -> None:
        authority = self.build().manifest["authority"]
        self.assertTrue(authority["research_metadata_only"])
        self.assertFalse(authority["scientific_release_authorized"])
        self.assertFalse(authority["hit_selection_authorized"])
        self.assertFalse(authority["potency_toxicity_efficacy_judgment_authorized"])
        self.assertFalse(authority["external_effect_authorized"])
        self.assertFalse(authority["buyer_acceptance_claimed"])
        self.assertFalse(authority["revenue_claimed"])

    def test_hash_chain_links_every_record(self) -> None:
        records = self.build().manifest["records"]
        previous = "0" * 64
        for record in records:
            self.assertEqual(record["previous_record_sha256"], previous)
            previous = record["record_sha256"]
        self.assertEqual(previous, self.build().manifest["summary"]["last_record_sha256"])

    def test_manifest_is_canonical_json(self) -> None:
        artifacts = self.build()
        decoded = json.loads(artifacts.json_bytes)
        expected = (
            json.dumps(decoded, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            + "\n"
        ).encode("utf-8")
        self.assertEqual(artifacts.json_bytes, expected)


if __name__ == "__main__":
    unittest.main()
