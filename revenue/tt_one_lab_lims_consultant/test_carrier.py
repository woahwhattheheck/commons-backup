from __future__ import annotations

from copy import deepcopy
from datetime import datetime as real_datetime
import json
from pathlib import Path
import unittest

import revenue.tt_one_lab_lims_consultant.carrier as carrier_module
from revenue.tt_one_lab_lims_consultant.carrier import (
    CarrierError,
    compile_packet,
    example_owner_input,
    loads_strict,
    source_manifest_digest,
    verify_packet,
)

DIGESTS = [f"{i:064x}"[-64:] for i in range(1, 10)]
SOURCE = json.loads(
    Path(__file__).with_name("source_manifest.json").read_text(encoding="utf-8")
)
_MISSING = object()


class ModulePatch:
    def __init__(self, **updates):
        self.updates = updates
        self.originals = {}

    def __enter__(self):
        for name, value in self.updates.items():
            self.originals[name] = getattr(carrier_module, name, _MISSING)
            setattr(carrier_module, name, value)
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self.originals.items():
            if value is _MISSING:
                delattr(carrier_module, name)
            else:
                setattr(carrier_module, name, value)
        return False


def complete_input():
    payload = example_owner_input()
    payload["candidate"].update(
        {
            "degree_evidence_digest": DIGESTS[0],
            "experience_years": 7,
            "experience_evidence_digest": DIGESTS[1],
            "reference_evidence_digests": DIGESTS[2:5],
            "nine_month_availability": True,
            "in_country_availability": True,
            "availability_evidence_digest": DIGESTS[5],
            "lims_health_system_evidence_digest": DIGESTS[6],
            "cross_sector_integration_evidence_digest": DIGESTS[7],
            "training_evidence_digest": DIGESTS[8],
            "conflict_disclosure": "NO_KNOWN_CONFLICT",
        }
    )
    payload["commercial"]["currency"] = "TTD"
    payload["commercial"]["all_inclusive_owner_confirmed"] = True
    for index, key in enumerate(payload["commercial"]["price_rows_minor"], start=1):
        payload["commercial"]["price_rows_minor"][key] = index * 100_000
    return payload


class CarrierTest(unittest.TestCase):
    def test_source_contract_keeps_price_rows_distinct_from_six_milestones(self):
        buyer = SOURCE["buyer_facts"]
        self.assertEqual(len(buyer["price_rows"]), 7)
        self.assertEqual(len(buyer["deliverables"]), 6)
        self.assertEqual(sum(buyer["evaluation_weights"].values()), 100)
        combined = buyer["deliverables"][2]
        self.assertEqual(combined["due"], "month 4")
        self.assertIn("Cross-Sector SOPs", combined["name"])
        self.assertIn("Recommendation for Adapting Existing LIMS", combined["name"])
        self.assertEqual(buyer["deliverables"][3]["due"], "month 7")
        self.assertEqual(buyer["deliverables"][4]["due"], "month 8")
        self.assertEqual(buyer["deliverables"][5]["due"], "month 9")

    def test_empty_owner_profile_holds_without_inventing(self):
        owner = example_owner_input()
        packet = compile_packet(owner)
        self.assertEqual(packet["posture"], "HOLD_OWNER_EVIDENCE")
        self.assertIn("OWNER_CREDENTIAL_EVIDENCE_INCOMPLETE", packet["blockers"])
        self.assertIn("OWNER_PRICING_INCOMPLETE", packet["blockers"])
        self.assertIn("CONFLICT_DISCLOSURE_UNRESOLVED", packet["blockers"])
        self.assertTrue(all(value is False for value in packet["authority"].values()))
        self.assertTrue(verify_packet(packet, owner))

    def test_replay_time_is_explicitly_not_current(self):
        owner = complete_input()
        packet = compile_packet(owner)
        self.assertEqual(
            packet["evaluation_time_authority"],
            "CALLER_SUPPLIED_REPLAY_ONLY_NOT_CURRENT",
        )
        self.assertFalse(packet["current_deadline_readiness_claimed"])
        self.assertTrue(verify_packet(packet, owner))

    def test_complete_internal_packet_never_becomes_submission_authority(self):
        owner = complete_input()
        packet = compile_packet(owner)
        self.assertEqual(
            packet["posture"], "OWNER_REVIEW_PACKET_COMPLETE_NOT_SUBMISSION_AUTHORITY"
        )
        self.assertEqual(packet["blockers"], [])
        self.assertFalse(packet["authority"]["submission_authorized"])
        self.assertFalse(packet["authority"]["pricing_commitment_authorized"])
        self.assertFalse(packet["authority"]["buyer_contact_authorized"])

    def test_three_distinct_reference_evidence_receipts_required(self):
        owner = complete_input()
        owner["candidate"]["reference_evidence_digests"] = DIGESTS[2:4]
        packet = compile_packet(owner)
        self.assertFalse(
            packet["readiness"]["essential_owner_evidence_present"]["three_references"]
        )
        owner = complete_input()
        owner["candidate"]["reference_evidence_digests"] = [DIGESTS[2]] * 3
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_experience_bool_alias_rejected(self):
        owner = complete_input()
        owner["candidate"]["experience_years"] = True
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_price_bool_alias_rejected(self):
        owner = complete_input()
        first = next(iter(owner["commercial"]["price_rows_minor"]))
        owner["commercial"]["price_rows_minor"][first] = True
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_all_seven_price_rows_are_mandatory(self):
        owner = complete_input()
        owner["commercial"]["price_rows_minor"].pop(
            "End-User Training and Training Report"
        )
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_currency_and_extra_rows_fail_closed(self):
        owner = complete_input()
        owner["commercial"]["currency"] = "ttd"
        with self.assertRaises(CarrierError):
            compile_packet(owner)
        owner = complete_input()
        owner["commercial"]["price_rows_minor"]["Travel"] = 1
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_submission_route_typo_is_not_normalized(self):
        owner = complete_input()
        owner["submission"]["email"] = "procurement@heath.gov.tt"
        packet = compile_packet(owner)
        self.assertEqual(packet["posture"], "HOLD_OWNER_EVIDENCE")
        self.assertIn("SUBMISSION_METADATA_MISMATCH", packet["blockers"])
        self.assertEqual(
            packet["buyer"]["clarification_email_as_printed_in_pdf"],
            "procurement@heath.gov.tt",
        )
        self.assertTrue(packet["buyer"]["clarification_route_conflict"])

    def test_submission_subject_drift_holds(self):
        owner = complete_input()
        owner["submission"]["subject"] = "LIMS Consultant Proposal"
        packet = compile_packet(owner)
        self.assertIn("SUBMISSION_METADATA_MISMATCH", packet["blockers"])

    def test_ninety_day_validity_is_floor(self):
        owner = complete_input()
        owner["submission"]["validity_days"] = 89
        packet = compile_packet(owner)
        self.assertIn("SUBMISSION_METADATA_MISMATCH", packet["blockers"])

    def test_deadline_passed_is_terminal_internal_posture(self):
        owner = complete_input()
        owner["evaluated_at"] = "2026-10-01T10:00:01-04:00"
        packet = compile_packet(owner)
        self.assertEqual(packet["posture"], "NO_BID_DEADLINE_PASSED")
        self.assertIn("PROPOSAL_DEADLINE_PASSED", packet["blockers"])
        self.assertFalse(packet["authority"]["submission_authorized"])
        self.assertEqual(
            packet["evaluation_time_authority"],
            "CALLER_SUPPLIED_REPLAY_ONLY_NOT_CURRENT",
        )

    def test_offset_conversion_is_real_not_string_compare(self):
        owner = complete_input()
        owner["evaluated_at"] = "2026-10-01T13:59:59+00:00"
        packet = compile_packet(owner)
        self.assertNotIn("PROPOSAL_DEADLINE_PASSED", packet["blockers"])
        owner["evaluated_at"] = "2026-10-01T14:00:01+00:00"
        packet = compile_packet(owner)
        self.assertIn("PROPOSAL_DEADLINE_PASSED", packet["blockers"])

    def test_source_manifest_digest_is_required(self):
        owner = complete_input()
        owner["source_manifest_digest"] = "0" * 64
        with self.assertRaises(CarrierError):
            compile_packet(owner)
        self.assertEqual(len(source_manifest_digest()), 64)

    def test_transplanted_packet_does_not_verify(self):
        first = complete_input()
        packet = compile_packet(first)
        second = complete_input()
        second["candidate"]["experience_years"] = 8
        self.assertFalse(verify_packet(packet, second))

    def test_packet_tamper_does_not_verify(self):
        owner = complete_input()
        packet = compile_packet(owner)
        packet["posture"] = "SUBMISSION_READY"
        self.assertFalse(verify_packet(packet, owner))

    def test_duplicate_json_keys_fail_closed(self):
        with self.assertRaises(CarrierError):
            loads_strict('{"candidate": {}, "candidate": {}}')

    def test_nonfinite_json_fails_closed(self):
        with self.assertRaises(CarrierError):
            loads_strict('{"x": NaN}')

    def test_exact_key_contract_rejects_extra_authority_claim(self):
        owner = complete_input()
        owner["submission"]["send_authorized"] = True
        with self.assertRaises(CarrierError):
            compile_packet(owner)

    def test_availability_requires_evidence_receipt_not_boolean_only(self):
        owner = complete_input()
        owner["candidate"]["availability_evidence_digest"] = None
        packet = compile_packet(owner)
        essential = packet["readiness"]["essential_owner_evidence_present"]
        self.assertFalse(essential["nine_month_availability"])
        self.assertFalse(essential["in_country_availability"])

    def test_candidate_receipts_do_not_embed_reference_contacts(self):
        owner = complete_input()
        packet = compile_packet(owner)
        candidate = json.dumps(packet["candidate_evidence"], sort_keys=True)
        self.assertNotIn("@", candidate)
        self.assertNotIn("http", candidate)

    def test_legacy_global_poison_cannot_widen_authority_or_remint_buyer(self):
        owner = complete_input()
        baseline = compile_packet(owner)
        with ModulePatch(
            _SOURCE_DIGEST="0" * 64,
            _BUYER={
                "submission_email": "attacker@example.test",
                "submission_subject": "forged",
            },
            _AUTHORITY_FALSE={"submission_authorized": True, "revenue_claimed": True},
            _DEADLINE=real_datetime.fromisoformat("2099-12-31T23:59:59-04:00"),
            _PRICE_ROWS=("Forged Price",),
        ):
            poisoned = compile_packet(owner)
            self.assertEqual(poisoned, baseline)
            self.assertTrue(verify_packet(baseline, owner))
            self.assertEqual(
                poisoned["buyer"]["submission_email"], "procurement@health.gov.tt"
            )
            self.assertTrue(all(value is False for value in poisoned["authority"].values()))

    def test_helper_and_stdlib_rebinding_cannot_change_generation(self):
        owner = complete_input()
        baseline = compile_packet(owner)
        with ModulePatch(
            _strict_int=lambda *args, **kwargs: 999999,
            _validate_submission=lambda value: {
                "email": "attacker@example.test",
                "subject": "forged",
                "validity_days": 9999,
            },
            _canonical=lambda value: b"forged",
            _digest=lambda value: "f" * 64,
            datetime=object(),
            deepcopy=lambda value: {"forged": True},
            hashlib=None,
            json=None,
            re=None,
        ):
            poisoned = compile_packet(owner)
            self.assertEqual(poisoned, baseline)
            self.assertTrue(verify_packet(baseline, owner))

    def test_verifier_does_not_follow_rebound_public_compiler(self):
        owner = complete_input()
        baseline = compile_packet(owner)
        forged = deepcopy(baseline)
        forged["authority"]["submission_authorized"] = True
        original_compile = carrier_module.compile_packet
        try:
            carrier_module.compile_packet = lambda ignored: forged
            self.assertTrue(verify_packet(baseline, owner))
            self.assertFalse(verify_packet(forged, owner))
        finally:
            carrier_module.compile_packet = original_compile

    def test_source_digest_remint_global_cannot_change_manifest_binding(self):
        owner = complete_input()
        expected = source_manifest_digest()
        with ModulePatch(_SOURCE_DIGEST="0" * 64):
            self.assertEqual(source_manifest_digest(), expected)
            bad = complete_input()
            bad["source_manifest_digest"] = "0" * 64
            with self.assertRaises(CarrierError):
                compile_packet(bad)
            self.assertTrue(verify_packet(compile_packet(owner), owner))

    def test_deadline_extension_global_cannot_reopen_replay(self):
        owner = complete_input()
        owner["evaluated_at"] = "2026-10-02T10:00:00-04:00"
        baseline = compile_packet(owner)
        self.assertEqual(baseline["posture"], "NO_BID_DEADLINE_PASSED")
        with ModulePatch(_DEADLINE=real_datetime.fromisoformat("2099-01-01T00:00:00-04:00")):
            poisoned = compile_packet(owner)
            self.assertEqual(poisoned, baseline)
            self.assertIn("PROPOSAL_DEADLINE_PASSED", poisoned["blockers"])

    def test_price_row_global_mutation_cannot_expand_commercial_contract(self):
        owner = complete_input()
        owner["commercial"]["price_rows_minor"]["Travel"] = 1
        with ModulePatch(_PRICE_ROWS=tuple(owner["commercial"]["price_rows_minor"])):
            with self.assertRaises(CarrierError):
                compile_packet(owner)

    def test_buyer_route_global_mutation_cannot_authorize_reminted_submission(self):
        owner = complete_input()
        owner["submission"]["email"] = "attacker@example.test"
        with ModulePatch(
            _BUYER={
                "submission_email": "attacker@example.test",
                "submission_subject": owner["submission"]["subject"],
                "proposal_validity_days": 1,
            }
        ):
            packet = compile_packet(owner)
            self.assertIn("SUBMISSION_METADATA_MISMATCH", packet["blockers"])
            self.assertFalse(packet["authority"]["submission_authorized"])

    def test_error_class_rebinding_does_not_change_captured_fail_closed_type(self):
        owner = complete_input()
        owner["candidate"]["experience_years"] = True
        with ModulePatch(CarrierError=RuntimeError):
            with self.assertRaises(CarrierError):
                compile_packet(owner)


if __name__ == "__main__":
    unittest.main()
