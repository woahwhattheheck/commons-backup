"""Applicant, evidence, parser, verifier, and CLI hostiles."""

from .test_support import *  # noqa: F401,F403

class ApplicantAndEvidenceTests(unittest.TestCase):
    def test_formal_applicant_must_be_in_consortium(self):
        value = base_valid()
        value["applicant"]["applicant_id"] = "absent"
        self.assertIn("APPLICANT_NOT_IN_CONSORTIUM", reason_codes(compile_valid(value)))

    def test_formal_applicant_role_must_match(self):
        value = base_valid()
        value["applicant"]["intended_role"] = "SELF_FUNDED_PARTNER"
        self.assertIn("APPLICANT_CONSORTIUM_ROLE_MISMATCH", reason_codes(compile_valid(value)))

    def test_subcontract_candidate_always_requires_owner_review(self):
        value = base_valid()
        value["applicant"].update(
            {
                "applicant_id": "vendor",
                "organization_label": "Vendor",
                "country_code": "US",
                "intended_role": "PAID_TECHNICAL_SUBCONTRACT_CANDIDATE",
                "legal_entity_verified": True,
                "pic_verified": True,
                "paid_role_authority_verified": True,
                "subcontract_rule_verified": True,
            }
        )
        bundle = compile_valid(value)
        self.assertIn("SUBCONTRACT_CANDIDATE_OWNER_REVIEW_REQUIRED", reason_codes(bundle))
        self.assertEqual(bundle["packet"]["decision"]["status"], "HOLD_APPLICANT_ROLE")

    def test_subcontract_candidate_cannot_be_counted_as_formal_partner(self):
        value = base_valid()
        value["applicant"].update(
            {
                "applicant_id": "p2",
                "organization_label": "p2",
                "country_code": "ES",
                "intended_role": "PAID_TECHNICAL_SUBCONTRACT_CANDIDATE",
                "legal_entity_verified": True,
                "pic_verified": True,
                "paid_role_authority_verified": True,
                "subcontract_rule_verified": True,
            }
        )
        self.assertIn("SUBCONTRACT_CANDIDATE_COUNTED_AS_PARTNER", reason_codes(compile_valid(value)))

    def test_invalid_commit_sha_rejected(self):
        value = base_valid()
        value["technical_evidence"][0]["commit_sha"] = "not-a-commit"
        with self.assertRaisesRegex(ReadinessError, "digest syntax"):
            compile_valid(value)

    def test_invalid_content_digest_rejected(self):
        value = base_valid()
        value["technical_evidence"][0]["content_sha256"] = "0" * 63
        with self.assertRaisesRegex(ReadinessError, "digest syntax"):
            compile_valid(value)

    def test_unverified_evidence_holds(self):
        value = base_valid()
        value["technical_evidence"][0]["verified"] = False
        self.assertIn("TECHNICAL_EVIDENCE_UNVERIFIED", reason_codes(compile_valid(value)))

    def test_missing_capability_holds(self):
        value = base_valid()
        value["technical_evidence"][0]["capability_tags"].remove("uncertainty_quantification")
        self.assertIn("TECHNICAL_TOPIC_TAG_GAPS", reason_codes(compile_valid(value)))

    def test_stale_evidence_holds_current_only(self):
        value = base_valid()
        value["technical_evidence"][0]["observed_at"] = "2026-06-01T00:00:00Z"
        current = compile_current(value, value)
        historical = compile_at(value, T0, "HISTORICAL")
        self.assertIn("TECHNICAL_EVIDENCE_STALE", reason_codes(current))
        self.assertNotIn("TECHNICAL_EVIDENCE_STALE", reason_codes(historical))

    def test_future_evidence_holds(self):
        value = base_valid()
        value["technical_evidence"][0]["observed_at"] = "2026-09-14T05:00:00Z"
        self.assertIn("TECHNICAL_EVIDENCE_FUTURE", reason_codes(compile_valid(value)))

    def test_unsupported_topic_model_holds(self):
        value = base_valid()
        value["concept"]["topic_ids"] = [2]
        value["technical_evidence"][0]["capability_tags"] = []
        self.assertIn("TOPIC_TAG_MODEL_UNSUPPORTED", reason_codes(compile_valid(value)))

    def test_empty_partner_shortlist_holds(self):
        value = base_valid()
        value["partner_shortlist"] = []
        self.assertIn("PARTNER_SHORTLIST_EMPTY", reason_codes(compile_valid(value)))

    def test_partner_shortlist_forbids_contact_fields(self):
        value = base_valid()
        value["partner_shortlist"][0]["email"] = "person@example.invalid"
        with self.assertRaisesRegex(ReadinessError, "forbidden contact"):
            compile_valid(value)

    def test_partner_shortlist_requires_official_host(self):
        value = base_valid()
        value["partner_shortlist"][0]["public_profile_url"] = "https://example.com/profile"
        with self.assertRaisesRegex(ReadinessError, "proposals.etag.ee"):
            compile_valid(value)

    def test_partner_shortlist_must_remain_research_only(self):
        value = base_valid()
        value["partner_shortlist"][0]["status"] = "CONTACT_NOW"
        self.assertIn("PARTNER_SHORTLIST_STATUS_INVALID", reason_codes(compile_valid(value)))

    def test_proposed_commercial_path_holds(self):
        value = base_valid()
        value["commercial"]["status"] = "PROPOSED_NOT_ACCEPTED"
        value["commercial"]["owner_approved_internal"] = False
        self.assertIn("COMMERCIAL_PATH_NOT_OWNER_APPROVED", reason_codes(compile_valid(value)))

    def test_false_external_acceptance_claim_holds(self):
        value = base_valid()
        value["commercial"]["status"] = "ACCEPTED_EXTERNAL"
        value["commercial"]["accepted_external"] = False
        self.assertIn("COMMERCIAL_ACCEPTANCE_CONTRADICTION", reason_codes(compile_valid(value)))


class ParsingAndCliTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ReadinessError, "duplicate JSON key"):
            strict_json_loads('{"a":1,"a":2}')

    def test_nan_rejected(self):
        with self.assertRaisesRegex(ReadinessError, "non-finite"):
            strict_json_loads('{"a":NaN}')

    def test_float_anywhere_rejected(self):
        value = base_valid()
        value["ignored_float"] = 1.25
        with self.assertRaisesRegex(ReadinessError, "floating-point"):
            compile_valid(value)

    def test_cli_historical_compile_and_verify(self):
        value = base_valid()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.json"
            bundle_path = root / "bundle.json"
            result_path = root / "result.json"
            input_path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(cli.main(["compile-historical", str(input_path), "2026-09-14T04:00:00Z", str(bundle_path)]), 0)
            self.assertEqual(cli.main(["verify", str(input_path), str(bundle_path), "--result-output", str(result_path)]), 0)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(result["valid"])

    def test_cli_refuses_output_overwrite(self):
        value = base_valid()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.json"
            output_path = root / "exists.json"
            input_path.write_text(json.dumps(value), encoding="utf-8")
            output_path.write_text("existing", encoding="utf-8")
            self.assertEqual(cli.main(["compile-historical", str(input_path), "2026-09-14T04:00:00Z", str(output_path)]), 2)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "existing")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_cli_refuses_symlink_input(self):
        value = base_valid()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.json"
            link = root / "link.json"
            output = root / "out.json"
            target.write_text(json.dumps(value), encoding="utf-8")
            os.symlink(str(target), str(link))
            self.assertEqual(cli.main(["compile-historical", str(link), "2026-09-14T04:00:00Z", str(output)]), 2)
            self.assertFalse(output.exists())

    def test_public_shortlist_file_contains_no_contact_keys(self):
        shortlist = load_json("partner_shortlist.json")
        encoded = json.dumps(shortlist, sort_keys=True).lower()
        self.assertNotIn('"email"', encoded)
        self.assertNotIn('"phone"', encoded)
        self.assertNotIn('"message"', encoded)

    def test_example_remains_fail_closed(self):
        example = load_json("example_input.json")
        bundle = compile_current(example, example)
        self.assertEqual(bundle["packet"]["decision"]["status"], "HOLD_DEADLINE_SOURCE_CONFLICT")
        authority = bundle["packet"]["authority"]
        self.assertFalse(authority["external_contact_authorized"])
        self.assertFalse(authority["submission_authorized"])
        self.assertFalse(authority["revenue_recognized"])

    def test_source_commitment_changes_when_fact_changes(self):
        source = load_json("official_sources.json")[0]
        original = source["fact_commitment"]
        source["version"] = source["version"] + "-changed"
        self.assertNotEqual(original, seal_source(source)["fact_commitment"])

    def test_canonical_digest_is_stable(self):
        one = {"b": 2, "a": [3, 1]}
        two = {"a": [3, 1], "b": 2}
        self.assertEqual(sha256_hex(one), sha256_hex(two))
