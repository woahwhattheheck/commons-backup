from __future__ import annotations

import json
import random
import sys
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from contract_fixture import (  # noqa: E402
    DEFECTS,
    SyntheticFixtureSigner,
    build_acceptance_fixture,
    run_acceptance,
)
from contract_gate import (  # noqa: E402
    DetachedSigner,
    EvidenceInputError,
    attach_signature,
    canonical_manifest_bytes,
    prepare_manifest,
    sign_manifest,
    validate_prepared_manifest,
)


def signer() -> DetachedSigner:
    return DetachedSigner(
        SyntheticFixtureSigner.signer_id,
        SyntheticFixtureSigner.algorithm,
        SyntheticFixtureSigner.sign_digest,
    )


def valid_one():
    shipments, _ = build_acceptance_fixture()
    return deepcopy(shipments[100])


class GateTests(unittest.TestCase):
    def test_frozen_acceptance_exact_counts_and_codes(self):
        manifest = run_acceptance()
        self.assertEqual(manifest["summary"]["shipment_count"], 240)
        self.assertEqual(manifest["summary"]["complete_shipments"], 192)
        self.assertEqual(manifest["summary"]["held_shipments"], 48)
        self.assertEqual(manifest["summary"]["leg_count"], 720)
        self.assertEqual(manifest["summary"]["held_legs"], 48)
        self.assertEqual(manifest["summary"]["hold_code_counts"], {code: 8 for code in sorted(DEFECTS)})

    def test_three_full_signed_reruns_are_byte_identical(self):
        a = canonical_manifest_bytes(run_acceptance())
        b = canonical_manifest_bytes(run_acceptance())
        c = canonical_manifest_bytes(run_acceptance())
        self.assertEqual(a, b)
        self.assertEqual(b, c)

    def test_input_shipment_order_does_not_change_manifest(self):
        shipments, _ = build_acceptance_fixture()
        a = sign_manifest(deepcopy(shipments), signer())
        shuffled = deepcopy(shipments)
        random.Random(913433).shuffle(shuffled)
        b = sign_manifest(shuffled, signer())
        self.assertEqual(canonical_manifest_bytes(a), canonical_manifest_bytes(b))

    def test_valid_shipment_is_complete_and_non_authoritative(self):
        manifest = sign_manifest([valid_one()], signer())
        self.assertEqual(manifest["shipments"][0]["status"], "EVIDENCE_COMPLETE")
        self.assertFalse(manifest["dispatch_authorized"])
        self.assertFalse(manifest["release_authorized"])
        self.assertFalse(manifest["clinical_decision_inferred"])
        self.assertFalse(manifest["temperature_disposition_inferred"])
        self.assertFalse(manifest["customs_judgment_inferred"])

    def test_custody_chain_mismatch_holds(self):
        item = valid_one()
        item["legs"][2]["custodian_from"] = "OTHER-CUSTODIAN"
        manifest = prepare_manifest([item])
        self.assertIn("CUSTODY_GAP", manifest["shipments"][0]["codes"])

    def test_temperature_excursion_requires_acknowledgement_but_does_not_decide_disposition(self):
        item = valid_one()
        leg = item["legs"][2]
        leg["sensor"]["observed_max_c"] = "12.5"
        held = prepare_manifest([item])
        self.assertIn("EXCURSION_UNACKNOWLEDGED", held["shipments"][0]["codes"])
        leg["incidents"] = [{"incident_id": "INC-1", "code": "TEMP_EXCURSION", "acknowledged_by": "QUALITY-7"}]
        complete = prepare_manifest([item])
        self.assertEqual(complete["shipments"][0]["status"], "EVIDENCE_COMPLETE")
        self.assertFalse(complete["temperature_disposition_inferred"])

    def test_time_window_breach_acknowledgement_is_evidence_not_release(self):
        item = valid_one()
        leg = item["legs"][2]
        handoff = datetime.fromisoformat(leg["handoff_at"].replace("Z", "+00:00"))
        leg["window_end"] = (handoff - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        self.assertIn("WINDOW_BREACH_UNACKNOWLEDGED", prepare_manifest([item])["shipments"][0]["codes"])
        leg["incidents"] = [{"incident_id": "INC-W", "code": "WINDOW_BREACH", "acknowledged_by": "OPS-4"}]
        manifest = prepare_manifest([item])
        self.assertEqual(manifest["shipments"][0]["status"], "EVIDENCE_COMPLETE")
        self.assertFalse(manifest["release_authorized"])

    def test_packout_sensor_lineage_mismatch_holds(self):
        item = valid_one()
        item["legs"][1]["sensor"]["packout_id"] = "PACK-WRONG"
        self.assertIn("PACKOUT_TEMPERATURE_MISMATCH", prepare_manifest([item])["shipments"][0]["codes"])

    def test_expired_document_holds(self):
        item = valid_one()
        item["legs"][1]["documents"][0]["valid_until"] = item["legs"][1]["pickup_at"]
        pickup = datetime.fromisoformat(item["legs"][1]["pickup_at"].replace("Z", "+00:00"))
        item["legs"][1]["documents"][0]["valid_until"] = (pickup - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        self.assertIn("DOCUMENT_INVALID", prepare_manifest([item])["shipments"][0]["codes"])

    def test_duplicate_leg_ids_hold_fail_closed(self):
        item = valid_one()
        item["legs"][2]["leg_id"] = item["legs"][1]["leg_id"]
        manifest = prepare_manifest([item])
        self.assertIn("LEG_GRAPH_INVALID", manifest["shipments"][0]["codes"])

    def test_orphan_predecessor_holds(self):
        item = valid_one()
        item["legs"][2]["predecessor_leg_id"] = "NO-SUCH-LEG"
        self.assertIn("LEG_GRAPH_INVALID", prepare_manifest([item])["shipments"][0]["codes"])

    def test_incomplete_pod_holds(self):
        item = valid_one()
        item["legs"][2]["pod"]["signed_by"] = ""
        self.assertIn("RECIPIENT_POD_INCOMPLETE", prepare_manifest([item])["shipments"][0]["codes"])

    def test_duplicate_shipment_ids_are_refused(self):
        item = valid_one()
        with self.assertRaisesRegex(EvidenceInputError, "duplicate shipment id"):
            prepare_manifest([item, deepcopy(item)])

    def test_secret_and_patient_identifiers_are_refused_recursively(self):
        for key in ("api_token", "private_key", "patient_name", "mrn"):
            item = valid_one()
            item["legs"][0][key] = "forbidden"
            with self.assertRaises(EvidenceInputError) as ctx:
                prepare_manifest([item])
            self.assertEqual(ctx.exception.code, "SECRET_OR_PII_FIELD")
            message = str(ctx.exception).lower()
            self.assertNotIn("not permitted", message)
            self.assertIn("outside the shipment evidence schema", message)

    def test_authority_shaped_fields_are_refused(self):
        item = valid_one()
        item["release_decision"] = "approve"
        with self.assertRaises(EvidenceInputError) as ctx:
            prepare_manifest([item])
        self.assertEqual(ctx.exception.code, "FORBIDDEN_AUTHORITY_FIELD")

    def test_timestamp_must_be_utc_rfc3339(self):
        item = valid_one()
        item["legs"][0]["pickup_at"] = "2026-09-01T08:00:00-04:00"
        with self.assertRaises(EvidenceInputError):
            prepare_manifest([item])

    def test_prepared_manifest_detects_tampering_before_signature_attach(self):
        prepared = prepare_manifest([valid_one()])
        prepared["summary"]["complete_shipments"] = 999
        with self.assertRaises(EvidenceInputError) as ctx:
            attach_signature(prepared, signer_id="KMS-1", algorithm="Ed25519", signature="A" * 88)
        self.assertEqual(ctx.exception.code, "MANIFEST_DIGEST_MISMATCH")

    def test_external_signature_envelope_covers_exact_manifest_digest(self):
        prepared = prepare_manifest([valid_one()])
        validated = validate_prepared_manifest(deepcopy(prepared))
        attached = attach_signature(validated, signer_id="KMS-1", algorithm="Ed25519", signature="A" * 88)
        self.assertEqual(attached["signature"]["covers"], "manifest_digest_sha256")
        self.assertEqual(attached["manifest_digest"], prepared["manifest_digest"])

    def test_signer_failure_fails_closed(self):
        def boom(_: bytes) -> str:
            raise RuntimeError("kms unavailable")

        with self.assertRaises(EvidenceInputError) as ctx:
            sign_manifest([valid_one()], DetachedSigner("KMS-1", "Ed25519", boom))
        self.assertEqual(ctx.exception.code, "SIGNER_FAILURE")

    def test_manifest_is_plain_json_and_signature_contains_no_key_material(self):
        manifest = sign_manifest([valid_one()], signer())
        encoded = json.dumps(manifest, sort_keys=True)
        self.assertIn("manifest_digest", encoded)
        self.assertNotIn("public-test-fixture-key-not-for-production", encoded)
        self.assertNotIn("private_key", encoded)


if __name__ == "__main__":
    unittest.main()
