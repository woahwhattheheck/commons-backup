import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import validate_scope

BASE_TEXT = (HERE / "scope.json").read_text(encoding="utf-8")
BASE = validate_scope.load_payload_text(BASE_TEXT)


class ScopeTests(unittest.TestCase):
    def assert_error_contains(self, payload, needle, *, release=False):
        errors = validate_scope.validate(payload, release=release)
        self.assertTrue(any(needle in error for error in errors), (needle, errors))

    def test_current_package_is_valid_but_release_is_permanent_hold(self):
        self.assertEqual(validate_scope.validate(copy.deepcopy(BASE)), [])
        self.assert_error_contains(
            copy.deepcopy(BASE),
            "self-attested v1 can never authorize",
            release=True,
        )

    def test_old_local_mint_predecessor_is_rejected(self):
        p = copy.deepcopy(BASE)
        for key in p["prime_gates"]:
            p["prime_gates"][key] = True
        p["source_receipt"]["controlling_documents_read"] = True
        for i, item in enumerate(p["role_pathways"], 1):
            item["acceptance_criteria"] = [f"prime-approved criterion {i}"]
        errors = validate_scope.validate(p, release=True)
        self.assertTrue(any("cannot assert prime evidence" in e for e in errors), errors)
        self.assertTrue(any("must remain false" in e for e in errors), errors)
        self.assertTrue(any("cannot persist prime-supplied text" in e for e in errors), errors)
        self.assertTrue(any("self-attested v1 can never authorize" in e for e in errors), errors)

    def test_counterparty_state_cannot_look_agreed(self):
        p = copy.deepcopy(BASE)
        p["counterparty_state"] = "AGREEMENT_EXECUTED"
        self.assert_error_contains(p, "counterparty_state")

    def test_release_status_cannot_look_ready(self):
        p = copy.deepcopy(BASE)
        p["release"]["status"] = "READY_FOR_SUBMISSION"
        self.assert_error_contains(p, "release.status")

    def test_prime_gate_true_is_rejected_even_without_release_mode(self):
        p = copy.deepcopy(BASE)
        p["prime_gates"]["live_bid_intent_confirmed"] = True
        self.assert_error_contains(p, "cannot assert prime evidence")

    def test_controlling_documents_read_cannot_be_self_asserted(self):
        p = copy.deepcopy(BASE)
        p["source_receipt"]["controlling_documents_read"] = True
        self.assert_error_contains(p, "must remain false")

    def test_pathway_text_is_not_admitted_in_this_generation(self):
        for text in (
            "prime-approved criterion",
            "jane@example.test",
            "sk_live_deadbeef",
            "https://example.test/?X-Amz-Signature=secret",
            r"C:\Users\Jane\Private\criteria.txt",
        ):
            with self.subTest(text=text):
                p = copy.deepcopy(BASE)
                p["role_pathways"][0]["acceptance_criteria"] = [text]
                self.assert_error_contains(p, "cannot persist prime-supplied text")

    def test_receipt_note_drift_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["source_receipt"]["note"] += " Contact jane@example.test."
        self.assert_error_contains(p, "source_receipt.note")

    def test_top_level_extra_field_smuggling_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["buyer_contact"] = "jane@example.test"
        self.assert_error_contains(p, "root: exact keys required")

    def test_nested_extra_field_smuggling_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["tender"]["api_key"] = "sk_live_deadbeef"
        self.assert_error_contains(p, "tender: exact keys required")

    def test_pathway_extra_field_smuggling_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["role_pathways"][0]["contact"] = "jane@example.test"
        self.assert_error_contains(p, "exact keys required")

    def test_release_extra_field_smuggling_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["release"]["prime_signature"] = "caller-authored"
        self.assert_error_contains(p, "release: exact keys required")

    def test_deadline_drift_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["tender"]["closes_at_portal"] = "2026-09-17T12:00:00+02:00"
        self.assert_error_contains(p, "closes_at_portal: provider receipt drift")

    def test_query_deadline_drift_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["tender"]["queries_deadline_at_portal"] = "2026-09-13T12:00:00+02:00"
        self.assert_error_contains(p, "queries_deadline_at_portal: provider receipt drift")

    def test_publication_time_drift_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["tender"]["published_at_portal"] = "2026-08-25T22:00:00+02:00"
        self.assert_error_contains(p, "published_at_portal: provider receipt drift")

    def test_detail_url_drift_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["tender"]["detail_url"] = "https://example.test/tender/246"
        self.assert_error_contains(p, "detail_url: provider receipt drift")

    def test_observation_time_drift_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["source_receipt"]["observed_at"] = "2026-09-17T01:00:00-04:00"
        self.assert_error_contains(p, "observed_at: provider receipt drift")

    def test_document_set_drift_is_rejected(self):
        p = copy.deepcopy(BASE)
        p["tender"]["documents"].pop()
        self.assert_error_contains(p, "tender.documents: exact value set required")

    def test_document_duplicates_are_rejected(self):
        p = copy.deepcopy(BASE)
        p["tender"]["documents"][1] = p["tender"]["documents"][0]
        self.assert_error_contains(p, "tender.documents: duplicate values forbidden")

    def test_document_unhashable_shape_fails_without_crash(self):
        p = copy.deepcopy(BASE)
        p["tender"]["documents"][0] = {"name": "not a string"}
        self.assert_error_contains(p, "tender.documents: list of strings required")

    def test_deliverable_shape_and_order_are_frozen(self):
        p = copy.deepcopy(BASE)
        p["tjlabs_boundary"]["deliverables"][0], p["tjlabs_boundary"]["deliverables"][1] = (
            p["tjlabs_boundary"]["deliverables"][1],
            p["tjlabs_boundary"]["deliverables"][0],
        )
        self.assert_error_contains(p, "tjlabs_boundary.deliverables: exact value set required")

    def test_commercial_state_cannot_be_upgraded_locally(self):
        p = copy.deepcopy(BASE)
        p["commercial_state"] = "ACCEPTED"
        self.assert_error_contains(p, "PROPOSED_NOT_ACCEPTED")

    def test_fee_cannot_be_invented(self):
        p = copy.deepcopy(BASE)
        p["fee"] = "USD 25000"
        self.assert_error_contains(p, "TO_BE_AGREED")

    def test_outbound_and_submission_authority_cannot_be_granted(self):
        for field in ("buyer_send_allowed", "bid_submission_allowed"):
            with self.subTest(field=field):
                p = copy.deepcopy(BASE)
                p["release"][field] = True
                self.assert_error_contains(p, field)

    def test_boundary_cannot_widen_to_pii_or_certification(self):
        p = copy.deepcopy(BASE)
        p["tjlabs_boundary"]["learner_pii"] = "FULL_RECORDS"
        p["tjlabs_boundary"]["legal_or_compliance_certification"] = True
        errors = validate_scope.validate(p)
        self.assertTrue(any("learner_pii" in e for e in errors))
        self.assertTrue(any("legal_or_compliance_certification" in e for e in errors))

    def test_role_order_and_ids_are_frozen(self):
        p = copy.deepcopy(BASE)
        p["role_pathways"][0], p["role_pathways"][1] = p["role_pathways"][1], p["role_pathways"][0]
        self.assert_error_contains(p, "expected role-01")

    def test_non_object_root_is_rejected_without_exception(self):
        self.assert_error_contains([], "root: object required")

    def test_duplicate_top_level_json_key_is_rejected(self):
        raw = '{"schema":"a","schema":"b"}'
        with self.assertRaisesRegex(validate_scope.StrictJSONError, "duplicate JSON key"):
            validate_scope.load_payload_text(raw)

    def test_duplicate_nested_json_key_is_rejected(self):
        raw = '{"tender":{"issuer":"a","issuer":"b"}}'
        with self.assertRaisesRegex(validate_scope.StrictJSONError, "duplicate JSON key"):
            validate_scope.load_payload_text(raw)

    def test_nonfinite_json_constants_are_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                raw = '{"x":' + token + "}"
                with self.assertRaisesRegex(validate_scope.StrictJSONError, "non-finite JSON value"):
                    validate_scope.load_payload_text(raw)

    def test_strict_loader_accepts_canonical_scope(self):
        loaded = validate_scope.load_payload_text(BASE_TEXT)
        self.assertEqual(validate_scope.validate(loaded), [])

    def test_exact_key_contracts_exist_at_each_nested_boundary(self):
        fixtures = [
            ("source_receipt", "unexpected", "source_receipt: exact keys required"),
            ("prime_gates", "unexpected", "prime_gates: exact keys required"),
            ("tjlabs_boundary", "unexpected", "tjlabs_boundary: exact keys required"),
            ("release", "unexpected", "release: exact keys required"),
        ]
        for section, key, needle in fixtures:
            with self.subTest(section=section):
                p = copy.deepcopy(BASE)
                p[section][key] = "smuggled"
                self.assert_error_contains(p, needle)


if __name__ == "__main__":
    unittest.main()
