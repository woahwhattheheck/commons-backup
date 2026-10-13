import copy
import json
import unittest

from revenue.commercial_offer_contract.offer_contract import (
    ContractError,
    approve_offer,
    authorize_send,
    capture_buyer_acceptance,
    compile_offer,
    contract_receipt_sha256,
    load_json_strict,
    verify_owner_approval,
    verify_send_authority,
)

SECRET = b"s" * 32
OTHER_SECRET = b"x" * 32
H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
H4 = "4" * 64


def valid_spec():
    return {
        "schema_version": 1,
        "offer_id": "offer-2026-001",
        "opportunity_id": "lead-42",
        "buyer_ref": "buyer-acme-opaque",
        "created_at": "2026-09-13T09:00:00Z",
        "valid_until": "2026-09-20T09:00:00Z",
        "currency": "USD",
        "total_amount_minor": 150000,
        "deliverables": [
            {
                "id": "D1",
                "title": "Implementation",
                "acceptance_criteria": "All synthetic acceptance cases pass.",
                "evidence_sha256": H1,
            },
            {
                "id": "D2",
                "title": "Handoff",
                "acceptance_criteria": "Runbook and source manifest delivered.",
                "evidence_sha256": H2,
            },
        ],
        "milestones": [
            {
                "id": "M1",
                "deliverable_ids": ["D1"],
                "amount_minor": 100000,
                "acceptance_window_hours": 72,
                "payment_due_days": 7,
            },
            {
                "id": "M2",
                "deliverable_ids": ["D2"],
                "amount_minor": 50000,
                "acceptance_window_hours": 48,
                "payment_due_days": 7,
            },
        ],
        "assumptions": ["Buyer supplies test fixtures."],
        "exclusions": ["No production deployment."],
    }


def approved_contract():
    return approve_offer(
        compile_offer(valid_spec()),
        SECRET,
        key_id="owner-key-1",
        approved_at="2026-09-13T10:00:00Z",
    )


def send_ready_contract():
    return authorize_send(
        approved_contract(),
        SECRET,
        destination_sha256=H3,
        channel="email",
        authorized_at="2026-09-13T10:05:00Z",
    )


class OfferContractTests(unittest.TestCase):
    def test_compile_is_deterministic_and_non_authorizing(self):
        a = compile_offer(valid_spec())
        b = compile_offer(copy.deepcopy(valid_spec()))
        self.assertEqual(a, b)
        self.assertEqual(a["state"], "READY_FOR_OWNER_APPROVAL")
        self.assertFalse(any(a["authority"].values()))
        self.assertEqual(contract_receipt_sha256(a), contract_receipt_sha256(b))

    def test_exact_integer_money_rejects_bool_float_and_string(self):
        for bad in (True, 150000.0, "150000"):
            spec = valid_spec()
            spec["total_amount_minor"] = bad
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                compile_offer(spec)

    def test_negative_money_rejected(self):
        spec = valid_spec()
        spec["milestones"][0]["amount_minor"] = -1
        with self.assertRaises(ContractError):
            compile_offer(spec)

    def test_amount_sum_must_match(self):
        spec = valid_spec()
        spec["milestones"][1]["amount_minor"] = 49999
        with self.assertRaisesRegex(ContractError, "do not equal"):
            compile_offer(spec)

    def test_deliverable_must_be_assigned_exactly_once(self):
        spec = valid_spec()
        spec["milestones"][1]["deliverable_ids"] = ["D1"]
        with self.assertRaises(ContractError):
            compile_offer(spec)

    def test_unknown_deliverable_rejected(self):
        spec = valid_spec()
        spec["milestones"][1]["deliverable_ids"] = ["D9"]
        with self.assertRaisesRegex(ContractError, "unknown deliverable"):
            compile_offer(spec)

    def test_duplicate_deliverable_id_rejected(self):
        spec = valid_spec()
        spec["deliverables"][1]["id"] = "D1"
        with self.assertRaisesRegex(ContractError, "duplicate deliverable"):
            compile_offer(spec)

    def test_unknown_fields_rejected(self):
        spec = valid_spec()
        spec["send_now"] = True
        with self.assertRaisesRegex(ContractError, "keys mismatch"):
            compile_offer(spec)

    def test_currency_is_strict(self):
        for bad in ("usd", "USDT", 123):
            spec = valid_spec()
            spec["currency"] = bad
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                compile_offer(spec)

    def test_canonical_timestamp_required(self):
        for bad in ("2026-09-13T09:00:00+00:00", "2026-09-13T09:00:00.000Z", "nope"):
            spec = valid_spec()
            spec["created_at"] = bad
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                compile_offer(spec)

    def test_valid_until_after_created(self):
        spec = valid_spec()
        spec["valid_until"] = spec["created_at"]
        with self.assertRaises(ContractError):
            compile_offer(spec)

    def test_strict_json_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
            load_json_strict('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ContractError):
            load_json_strict('{"x":NaN}')

    def test_owner_approval_requires_strong_secret(self):
        with self.assertRaises(ContractError):
            approve_offer(compile_offer(valid_spec()), b"short", key_id="k1", approved_at="2026-09-13T10:00:00Z")

    def test_owner_approval_verifies(self):
        c = approved_contract()
        verify_owner_approval(c, SECRET, trusted_now="2026-09-13T11:00:00Z")
        self.assertEqual(c["state"], "OWNER_APPROVED")
        self.assertFalse(c["authority"]["external_send_authorized"])

    def test_wrong_secret_rejected(self):
        with self.assertRaisesRegex(ContractError, "HMAC invalid"):
            verify_owner_approval(approved_contract(), OTHER_SECRET)

    def test_offer_tamper_breaks_approval(self):
        c = approved_contract()
        c["offer"]["total_amount_minor"] = 1
        with self.assertRaises(ContractError):
            verify_owner_approval(c, SECRET)

    def test_approval_tamper_breaks_hmac(self):
        c = approved_contract()
        c["owner_approval"]["approved_at"] = "2026-09-13T10:01:00Z"
        with self.assertRaisesRegex(ContractError, "HMAC invalid"):
            verify_owner_approval(c, SECRET)

    def test_expired_offer_fails_trusted_time(self):
        with self.assertRaisesRegex(ContractError, "expired"):
            verify_owner_approval(approved_contract(), SECRET, trusted_now="2026-09-21T00:00:00Z")

    def test_send_authorization_before_owner_approval_rejected(self):
        with self.assertRaisesRegex(ContractError, "predate owner approval"):
            authorize_send(
                approved_contract(),
                SECRET,
                destination_sha256=H3,
                channel="email",
                authorized_at="2026-09-13T09:59:59Z",
            )

    def test_send_authority_binds_destination_and_channel(self):
        c = send_ready_contract()
        verify_send_authority(c, SECRET, trusted_now="2026-09-13T11:00:00Z")
        self.assertTrue(c["authority"]["external_send_authorized"])
        self.assertEqual(c["send_authority"]["destination_sha256"], H3)
        self.assertEqual(c["send_authority"]["channel"], "email")

    def test_send_destination_tamper_rejected(self):
        c = send_ready_contract()
        c["send_authority"]["destination_sha256"] = H4
        with self.assertRaisesRegex(ContractError, "HMAC invalid"):
            verify_send_authority(c, SECRET)

    def test_unsupported_send_channel_rejected(self):
        with self.assertRaises(ContractError):
            authorize_send(
                approved_contract(), SECRET, destination_sha256=H3, channel="slack-dm", authorized_at="2026-09-13T10:05:00Z"
            )

    def test_send_authority_cannot_preexist_before_approval(self):
        c = compile_offer(valid_spec())
        c["send_authority"] = {}
        with self.assertRaises(ContractError):
            approve_offer(c, SECRET, key_id="k1", approved_at="2026-09-13T10:00:00Z")

    def test_acceptance_requires_matching_offer_and_buyer(self):
        c = send_ready_contract()
        acceptance = {
            "offer_sha256": c["offer_sha256"],
            "buyer_ref": c["offer"]["buyer_ref"],
            "accepted_at": "2026-09-13T11:00:00Z",
            "evidence_sha256": H4,
            "identity_verification_sha256": H2,
        }
        out = capture_buyer_acceptance(c, SECRET, acceptance=acceptance, trusted_now="2026-09-13T11:01:00Z")
        self.assertEqual(out["state"], "BUYER_ACCEPTANCE_EVIDENCE_CAPTURED")
        self.assertFalse(out["authority"]["buyer_acceptance_verified"])
        self.assertFalse(out["authority"]["fulfillment_authorized"])
        self.assertFalse(out["authority"]["payment_collected"])
        self.assertFalse(out["authority"]["revenue_recognized"])

    def test_acceptance_before_send_authorization_rejected(self):
        c = send_ready_contract()
        acceptance = {
            "offer_sha256": c["offer_sha256"],
            "buyer_ref": c["offer"]["buyer_ref"],
            "accepted_at": "2026-09-13T10:04:59Z",
            "evidence_sha256": H4,
            "identity_verification_sha256": H2,
        }
        with self.assertRaisesRegex(ContractError, "predate send authorization"):
            capture_buyer_acceptance(c, SECRET, acceptance=acceptance, trusted_now="2026-09-13T11:01:00Z")

    def test_acceptance_wrong_buyer_rejected(self):
        c = send_ready_contract()
        acceptance = {
            "offer_sha256": c["offer_sha256"],
            "buyer_ref": "somebody-else",
            "accepted_at": "2026-09-13T11:00:00Z",
            "evidence_sha256": H4,
            "identity_verification_sha256": H2,
        }
        with self.assertRaisesRegex(ContractError, "identity"):
            capture_buyer_acceptance(c, SECRET, acceptance=acceptance, trusted_now="2026-09-13T11:01:00Z")

    def test_acceptance_wrong_offer_rejected(self):
        c = send_ready_contract()
        acceptance = {
            "offer_sha256": H4,
            "buyer_ref": c["offer"]["buyer_ref"],
            "accepted_at": "2026-09-13T11:00:00Z",
            "evidence_sha256": H4,
            "identity_verification_sha256": H2,
        }
        with self.assertRaisesRegex(ContractError, "different offer"):
            capture_buyer_acceptance(c, SECRET, acceptance=acceptance, trusted_now="2026-09-13T11:01:00Z")

    def test_future_acceptance_rejected(self):
        c = send_ready_contract()
        acceptance = {
            "offer_sha256": c["offer_sha256"],
            "buyer_ref": c["offer"]["buyer_ref"],
            "accepted_at": "2026-09-13T12:00:00Z",
            "evidence_sha256": H4,
            "identity_verification_sha256": H2,
        }
        with self.assertRaisesRegex(ContractError, "future"):
            capture_buyer_acceptance(c, SECRET, acceptance=acceptance, trusted_now="2026-09-13T11:00:00Z")

    def test_contract_cannot_self_assert_payment_or_revenue(self):
        c = approved_contract()
        c["authority"]["revenue_recognized"] = True
        with self.assertRaisesRegex(ContractError, "never self-assert"):
            verify_owner_approval(c, SECRET)

    def test_receipt_changes_when_authority_changes(self):
        a = approved_contract()
        b = send_ready_contract()
        self.assertNotEqual(contract_receipt_sha256(a), contract_receipt_sha256(b))

    def test_json_round_trip_is_stable(self):
        c = send_ready_contract()
        again = json.loads(json.dumps(c, sort_keys=True))
        self.assertEqual(contract_receipt_sha256(c), contract_receipt_sha256(again))


if __name__ == "__main__":
    unittest.main()
