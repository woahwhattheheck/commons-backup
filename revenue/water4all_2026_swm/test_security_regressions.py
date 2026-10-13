"""Predecessor-killer tests for the accepted Water4All STOP-MERGE findings."""

from unittest.mock import patch

from .test_support import *  # noqa: F401,F403


class AuthorityBoundaryRegressionTests(unittest.TestCase):
    def test_resealed_source_payload_cannot_mint_retained_authority(self):
        value = base_valid()
        value["official_sources"][0]["budget_eur_cents"] += 1
        reseal(value["official_sources"][0])
        codes = reason_codes(compile_valid(value))
        self.assertIn("SOURCE_GENERATION_REGISTRY_MISMATCH", codes)

    def test_unknown_source_generation_cannot_mint_authority(self):
        value = base_valid()
        source = value["official_sources"][0]
        source["source_id"] = "attacker-resealed-source"
        reseal(source)
        self.assertIn("SOURCE_GENERATION_NOT_RETAINED", reason_codes(compile_valid(value)))

    def test_verified_true_does_not_promote_unretained_evidence(self):
        value = base_valid()
        value["technical_evidence"][0]["evidence_id"] = "caller-minted-evidence"
        value["technical_evidence"][0]["verified"] = True
        codes = reason_codes(compile_valid(value))
        self.assertIn("TECHNICAL_EVIDENCE_NOT_RETAINED", codes)
        self.assertIn("TECHNICAL_TOPIC_TAG_GAPS", codes)

    def test_retained_evidence_descriptor_mismatch_holds(self):
        value = base_valid()
        value["technical_evidence"][0]["content_sha256"] = "c" * 64
        codes = reason_codes(compile_valid(value))
        self.assertIn("TECHNICAL_EVIDENCE_REGISTRY_MISMATCH", codes)
        self.assertIn("TECHNICAL_TOPIC_TAG_GAPS", codes)

    def test_current_compile_ignores_backdated_caller_clock(self):
        value = base_valid()
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        self.assertEqual(bundle["packet"]["generated_at"], "2026-09-14T04:00:00Z")

    def test_current_verify_ignores_backdated_trusted_now(self):
        value = base_valid()
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0 + dt.timedelta(seconds=301)):
            with self.assertRaisesRegex(ReadinessError, "freshness"):
                verify_bundle(value, bundle, T0 - dt.timedelta(days=365))


class ConsortiumAndPartnerRegressionTests(unittest.TestCase):
    def test_three_partnership_beneficiaries_exceed_small_consortium_cap(self):
        value = base_valid()
        for member in value["consortium"]["members"]:
            member["water4all_partnership_beneficiary"] = True
        self.assertIn("PARTNERSHIP_BENEFICIARY_ENTITY_CAP_EXCEEDED", reason_codes(compile_valid(value)))

    def test_missing_coordinator_pi_cross_proposal_evidence_holds(self):
        value = base_valid()
        del value["consortium"]["coordinator_pi_cross_proposal_evidence"]
        self.assertIn("COORDINATOR_PI_CROSS_PROPOSAL_EVIDENCE_MISSING", reason_codes(compile_valid(value)))

    def test_coordinator_pi_other_proposal_conflict_holds(self):
        value = base_valid()
        value["consortium"]["coordinator_pi_cross_proposal_evidence"]["participates_in_other_jtc_or_ecr_proposal"] = True
        self.assertIn("COORDINATOR_PI_CROSS_PROPOSAL_CONFLICT", reason_codes(compile_valid(value)))

    def test_partner_shortlist_rejects_secret_field(self):
        value = base_valid()
        value["partner_shortlist"][0]["api_token"] = "secret"
        with self.assertRaisesRegex(ReadinessError, "contact/outreach/secret"):
            compile_valid(value)

    def test_partner_shortlist_rejects_query_fragment_and_encoded_path(self):
        attacks = [
            "https://proposals.etag.ee/water4all/2026/partner-search-entry/858?message=hi",
            "https://proposals.etag.ee/water4all/2026/partner-search-entry/858#contact",
            "https://proposals.etag.ee/water4all/2026/partner-search-entry/%38%35%38",
            "https://user@proposals.etag.ee/water4all/2026/partner-search-entry/858",
            "https://proposals.etag.ee:443/water4all/2026/partner-search-entry/858",
            "https://proposals.etag.ee/water4all/2026/partner-search-entry/0858",
        ]
        for attack in attacks:
            value = base_valid()
            value["partner_shortlist"][0]["public_profile_url"] = attack
            with self.subTest(url=attack):
                with self.assertRaises(ReadinessError):
                    compile_valid(value)

    def test_partner_shortlist_rejects_embedded_email_route(self):
        value = base_valid()
        value["partner_shortlist"][0]["public_fit_summary"] = "Write person@example.invalid for access"
        with self.assertRaisesRegex(ReadinessError, "contact-route semantics"):
            compile_valid(value)

    def test_partner_shortlist_rejects_mailto_in_organization_label(self):
        value = base_valid()
        value["partner_shortlist"][0]["organization_label"] = "mailto:owner@example.invalid Lab"
        with self.assertRaisesRegex(ReadinessError, "contact-route semantics"):
            compile_valid(value)


if __name__ == "__main__":
    unittest.main()
