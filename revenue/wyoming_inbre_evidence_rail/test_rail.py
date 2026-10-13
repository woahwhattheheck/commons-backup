from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

try:
    from .acceptance import EXPECTED_COUNTS, check_acceptance, generate_acceptance_fixture
    from .rail import RailError, reconcile, verify_receipt
except ImportError:
    from acceptance import EXPECTED_COUNTS, check_acceptance, generate_acceptance_fixture
    from rail import RailError, reconcile, verify_receipt


def event(kind: str, **overrides):
    base = {
        "allocation": {
            "event_id": "EV-ALLOC-A",
            "kind": "allocation",
            "allocation_id": "ALLOC-A",
            "campus_id": "CAMPUS-01",
            "project_id": "PROJECT-A",
            "period": "2026-Q3",
            "amount_cents": 100_000,
        },
        "allocation_amendment": {
            "event_id": "EV-AMEND-A",
            "kind": "allocation_amendment",
            "amendment_id": "AMEND-A",
            "allocation_id": "ALLOC-A",
            "delta_cents": 5_000,
        },
        "transfer": {
            "event_id": "EV-XFER-A",
            "kind": "transfer",
            "transfer_id": "XFER-A",
            "from_allocation_id": "ALLOC-A",
            "to_allocation_id": "ALLOC-B",
            "amount_cents": 10_000,
        },
        "trainee_appointment": {
            "event_id": "EV-APPT-A",
            "kind": "trainee_appointment",
            "appointment_id": "APPT-A",
            "synthetic_person_id": "SYNTH-PERSON-A",
            "allocation_id": "ALLOC-A",
            "campus_id": "CAMPUS-01",
            "project_id": "PROJECT-A",
            "period": "2026-Q3",
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
        },
        "resource_use": {
            "event_id": "EV-USE-A",
            "kind": "resource_use",
            "use_id": "USE-A",
            "allocation_id": "ALLOC-A",
            "campus_id": "CAMPUS-01",
            "project_id": "PROJECT-A",
            "period": "2026-Q3",
            "resource_id": "RESOURCE-A",
            "units_milli": 1_000,
        },
        "report_evidence": {
            "event_id": "EV-EVID-A",
            "kind": "report_evidence",
            "evidence_id": "EVID-A",
            "allocation_id": "ALLOC-A",
            "campus_id": "CAMPUS-01",
            "project_id": "PROJECT-A",
            "period": "2026-Q3",
            "evidence_kind": "SYNTHETIC-PROGRESS-POINTER",
            "source_sha256": hashlib.sha256(b"fixture").hexdigest(),
        },
    }[kind]
    return {**base, **overrides}


class RailTests(unittest.TestCase):
    def setUp(self):
        self.a = event("allocation")
        self.b = event(
            "allocation",
            event_id="EV-ALLOC-B",
            allocation_id="ALLOC-B",
            campus_id="CAMPUS-02",
            project_id="PROJECT-B",
        )

    def assertCode(self, code, callback):
        with self.assertRaises(RailError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_acceptance_500_record_contract(self):
        result = check_acceptance()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["fixture_records"], 500)
        self.assertEqual(result["manifest"]["counts"], EXPECTED_COUNTS)
        self.assertEqual(len(result["manifest"]["campuses"]), 10)

    def test_order_invariant_receipt(self):
        fixture = generate_acceptance_fixture()
        self.assertEqual(
            reconcile(fixture)["receipt_sha256"],
            reconcile(list(reversed(fixture)))["receipt_sha256"],
        )

    def test_exact_retry_collapses_without_duplicate_effect(self):
        manifest = reconcile([self.a, deepcopy(self.a)])
        self.assertEqual(manifest["unique_events"], 1)
        self.assertEqual(manifest["replay_collapsed"], 1)
        self.assertEqual(manifest["counts"]["allocations"], 1)

    def test_changed_retry_is_idempotency_conflict(self):
        changed = deepcopy(self.a)
        changed["amount_cents"] += 1
        self.assertCode("IDEMPOTENCY_CONFLICT", lambda: reconcile([self.a, changed]))

    def test_transfer_preserves_network_total(self):
        manifest = reconcile([self.a, self.b, event("transfer")])
        self.assertEqual(manifest["money"]["network_authorized_cents"], 200_000)
        self.assertEqual(manifest["money"]["network_balance_cents"], 200_000)
        self.assertEqual(manifest["money"]["transfer_volume_cents"], 10_000)

    def test_transfer_overdraw_fails_closed_independent_of_order(self):
        transfer = event("transfer", amount_cents=100_001)
        self.assertCode("TRANSFER_OVERDRAW", lambda: reconcile([transfer, self.b, self.a]))

    def test_amendment_changes_authority_explicitly(self):
        manifest = reconcile([self.a, event("allocation_amendment")])
        self.assertEqual(manifest["money"]["base_authorized_cents"], 100_000)
        self.assertEqual(manifest["money"]["amendment_delta_cents"], 5_000)
        self.assertEqual(manifest["money"]["network_authorized_cents"], 105_000)

    def test_negative_amendment_authority_rejected(self):
        amendment = event("allocation_amendment", delta_cents=-100_001)
        self.assertCode("NEGATIVE_AUTHORITY", lambda: reconcile([self.a, amendment]))

    def test_trainee_scope_mismatch_rejected(self):
        appointment = event("trainee_appointment", campus_id="CAMPUS-02")
        self.assertCode("APPOINTMENT_SCOPE_MISMATCH", lambda: reconcile([self.a, appointment]))

    def test_overlapping_synthetic_trainee_appointments_rejected(self):
        first = event("trainee_appointment")
        second = event(
            "trainee_appointment",
            event_id="EV-APPT-B",
            appointment_id="APPT-B",
            start_date="2026-07-31",
            end_date="2026-08-15",
        )
        self.assertCode("APPOINTMENT_OVERLAP", lambda: reconcile([self.a, first, second]))

    def test_unmapped_resource_is_quarantined_not_silently_counted(self):
        use = event("resource_use", allocation_id="ALLOC-MISSING")
        manifest = reconcile([self.a, use])
        self.assertEqual(manifest["counts"]["resource_use_mapped"], 0)
        self.assertEqual(manifest["quarantines"][0]["code"], "RESOURCE_UNKNOWN_ALLOCATION")

    def test_mismatched_evidence_is_quarantined(self):
        evidence = event("report_evidence", project_id="PROJECT-WRONG")
        manifest = reconcile([self.a, evidence])
        self.assertEqual(manifest["counts"]["report_evidence_mapped"], 0)
        self.assertEqual(manifest["quarantines"][0]["code"], "EVIDENCE_SCOPE_MISMATCH")

    def test_pii_shaped_field_rejected(self):
        contaminated = {**self.a, "email": "person@example.invalid"}
        self.assertCode("PII_FORBIDDEN", lambda: reconcile([contaminated]))

    def test_nested_payload_rejected(self):
        contaminated = {**self.a, "extra": {"nested": "value"}}
        self.assertCode("NESTED_DATA_FORBIDDEN", lambda: reconcile([contaminated]))

    def test_impossible_calendar_date_rejected(self):
        appointment = event("trainee_appointment", start_date="2026-02-30")
        self.assertCode("INVALID_EVENT", lambda: reconcile([self.a, appointment]))

    def test_bad_source_hash_rejected(self):
        evidence = event("report_evidence", source_sha256="abc")
        self.assertCode("INVALID_EVENT", lambda: reconcile([self.a, evidence]))

    def test_receipt_verification_and_tamper_rejection(self):
        manifest = reconcile([self.a])
        self.assertTrue(verify_receipt(manifest))
        tampered = deepcopy(manifest)
        tampered["money"]["network_balance_cents"] += 1
        self.assertFalse(verify_receipt(tampered))


if __name__ == "__main__":
    unittest.main()
