"""Consortium authority hostiles."""

from unittest.mock import patch

from .test_support import *  # noqa: F401,F403

class ConsortiumTests(unittest.TestCase):
    def test_funded_partner_minimum(self):
        value = base_valid()
        value["consortium"]["members"] = value["consortium"]["members"][:2]
        self.assertIn("CONSORTIUM_FUNDED_PARTNER_MINIMUM", reason_codes(compile_valid(value)))

    def test_funded_country_minimum(self):
        value = base_valid()
        value["consortium"]["members"][1]["country_code"] = "DE"
        self.assertIn("CONSORTIUM_FUNDED_COUNTRY_MINIMUM", reason_codes(compile_valid(value)))

    def test_eu_associated_minimum(self):
        value = base_valid()
        value["consortium"]["members"][1]["eu_or_associated"] = False
        value["consortium"]["members"][2]["eu_or_associated"] = False
        self.assertIn("CONSORTIUM_EU_ASSOCIATED_MINIMUM", reason_codes(compile_valid(value)))

    def test_exactly_one_coordinator(self):
        value = base_valid()
        value["consortium"]["members"][1]["coordinator"] = True
        self.assertIn("CONSORTIUM_COORDINATOR_COUNT", reason_codes(compile_valid(value)))

    def test_coordinator_must_be_eligible(self):
        value = base_valid()
        value["consortium"]["members"][0]["fpo_eligibility_verified"] = False
        self.assertIn("CONSORTIUM_COORDINATOR_INELIGIBLE", reason_codes(compile_valid(value)))

    def test_unverified_legal_entity_holds(self):
        value = base_valid()
        value["consortium"]["members"][1]["legal_entity_verified"] = False
        self.assertIn("CONSORTIUM_LEGAL_ENTITY_UNVERIFIED", reason_codes(compile_valid(value)))

    def test_unverified_pic_holds(self):
        value = base_valid()
        value["consortium"]["members"][1]["pic_verified"] = False
        self.assertIn("CONSORTIUM_PIC_UNVERIFIED", reason_codes(compile_valid(value)))

    def test_nonparticipating_funded_country_holds(self):
        value = base_valid()
        value["consortium"]["members"][1]["participating_fpo_country"] = False
        self.assertIn("CONSORTIUM_FUNDED_COUNTRY_NOT_PARTICIPATING", reason_codes(compile_valid(value)))

    def test_unverified_fpo_eligibility_holds(self):
        value = base_valid()
        value["consortium"]["members"][1]["fpo_eligibility_verified"] = False
        self.assertIn("CONSORTIUM_FPO_ELIGIBILITY_UNVERIFIED", reason_codes(compile_valid(value)))

    def test_us_cannot_be_funded_even_if_flags_are_asserted(self):
        value = base_valid()
        value["consortium"]["members"][0]["country_code"] = "US"
        value["consortium"]["members"][0]["eu_or_associated"] = False
        value["applicant"]["country_code"] = "US"
        self.assertIn("CONSORTIUM_KNOWN_NONPARTICIPATING_FUNDED_COUNTRY", reason_codes(compile_valid(value)))

    def test_one_verified_us_self_funded_partner_is_structurally_allowed(self):
        value = base_valid()
        value["consortium"]["members"].append(
            {
                "partner_id": "us-self",
                "organization_label": "US self-funded entity",
                "country_code": "US",
                "role": "SELF_FUNDED_PARTNER",
                "eu_or_associated": False,
                "participating_fpo_country": False,
                "fpo_eligibility_verified": False,
                "undersubscribed_fpo": False,
                "legal_entity_verified": True,
                "pic_verified": True,
                "self_funding_commitment_verified": True,
                "coordinator": False,
                "person_months_milli": 9000,
                "synthetic_placeholder": False,
            }
        )
        value["applicant"].update(
            {
                "applicant_id": "us-self",
                "organization_label": "US self-funded entity",
                "country_code": "US",
                "intended_role": "SELF_FUNDED_PARTNER",
                "legal_entity_verified": True,
                "pic_verified": True,
            }
        )
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_valid(value, mode="CURRENT")
        self.assertEqual(bundle["packet"]["decision"]["status"], "READY_FOR_OWNER_REVIEW")

    def test_two_self_funded_partners_hold(self):
        value = base_valid()
        for idx, country in enumerate(("US", "CA"), 1):
            value["consortium"]["members"].append(
                {
                    "partner_id": "self%d" % idx,
                    "organization_label": "self%d" % idx,
                    "country_code": country,
                    "role": "SELF_FUNDED_PARTNER",
                    "eu_or_associated": False,
                    "participating_fpo_country": False,
                    "fpo_eligibility_verified": False,
                    "undersubscribed_fpo": False,
                    "legal_entity_verified": True,
                    "pic_verified": True,
                    "self_funding_commitment_verified": True,
                    "coordinator": False,
                    "person_months_milli": 5000,
                    "synthetic_placeholder": False,
                }
            )
        self.assertIn("CONSORTIUM_SELF_FUNDED_MAXIMUM", reason_codes(compile_valid(value)))

    def test_self_funded_cannot_coordinate(self):
        value = base_valid()
        member = value["consortium"]["members"][0]
        member["role"] = "SELF_FUNDED_PARTNER"
        member["self_funding_commitment_verified"] = True
        self.assertIn("SELF_FUNDED_COORDINATOR_FORBIDDEN", reason_codes(compile_valid(value)))

    def test_self_funding_commitment_required(self):
        value = base_valid()
        member = value["consortium"]["members"][2]
        member["role"] = "SELF_FUNDED_PARTNER"
        member["participating_fpo_country"] = False
        member["fpo_eligibility_verified"] = False
        self.assertIn("SELF_FUNDING_COMMITMENT_UNVERIFIED", reason_codes(compile_valid(value)))

    def test_seven_partner_default_limit_allowed(self):
        value = base_valid()
        countries = ["DE", "ES", "NL", "FR", "IT", "SE", "NO"]
        template = value["consortium"]["members"][0]
        value["consortium"]["members"] = []
        for index, country in enumerate(countries):
            member = copy.deepcopy(template)
            member.update({"partner_id": "p%d" % (index + 1), "organization_label": "p%d" % (index + 1), "country_code": country, "coordinator": index == 0, "person_months_milli": 1000})
            value["consortium"]["members"].append(member)
        value["applicant"].update({"applicant_id": "p1", "organization_label": "p1", "country_code": "DE"})
        self.assertNotIn("CONSORTIUM_PARTNER_MAXIMUM", reason_codes(compile_valid(value)))

    def test_eight_requires_undersubscribed_fpo(self):
        value = base_valid()
        countries = ["DE", "ES", "NL", "FR", "IT", "SE", "NO", "FI"]
        template = value["consortium"]["members"][0]
        value["consortium"]["members"] = []
        for index, country in enumerate(countries):
            member = copy.deepcopy(template)
            member.update({"partner_id": "p%d" % (index + 1), "organization_label": "p%d" % (index + 1), "country_code": country, "coordinator": index == 0, "person_months_milli": 1000})
            value["consortium"]["members"].append(member)
        value["applicant"].update({"applicant_id": "p1", "organization_label": "p1", "country_code": "DE"})
        self.assertIn("CONSORTIUM_PARTNER_MAXIMUM", reason_codes(compile_valid(value)))
        value["consortium"]["members"][7]["undersubscribed_fpo"] = True
        self.assertNotIn("CONSORTIUM_PARTNER_MAXIMUM", reason_codes(compile_valid(value)))

    def test_nine_exceeds_even_extended_limit(self):
        value = base_valid()
        countries = ["DE", "ES", "NL", "FR", "IT", "SE", "NO", "FI", "DK"]
        template = value["consortium"]["members"][0]
        value["consortium"]["members"] = []
        for index, country in enumerate(countries):
            member = copy.deepcopy(template)
            member.update({"partner_id": "p%d" % (index + 1), "organization_label": "p%d" % (index + 1), "country_code": country, "coordinator": index == 0, "person_months_milli": 1000, "undersubscribed_fpo": index == 8})
            value["consortium"]["members"].append(member)
        value["applicant"].update({"applicant_id": "p1", "organization_label": "p1", "country_code": "DE"})
        self.assertIn("CONSORTIUM_PARTNER_MAXIMUM", reason_codes(compile_valid(value)))

    def test_partner_over_half_workload_holds(self):
        value = base_valid()
        p1, p2, p3 = value["consortium"]["members"]
        p1["person_months_milli"] = 21000
        p2["person_months_milli"] = 10000
        p3["person_months_milli"] = 10000
        self.assertIn("PARTNER_WORKLOAD_OVER_HALF", reason_codes(compile_valid(value)))

    def test_exactly_half_workload_allowed(self):
        value = base_valid()
        p1, p2, p3 = value["consortium"]["members"]
        p1["person_months_milli"] = 20000
        p2["person_months_milli"] = 10000
        p3["person_months_milli"] = 10000
        self.assertNotIn("PARTNER_WORKLOAD_OVER_HALF", reason_codes(compile_valid(value)))

    def test_country_over_half_workload_holds(self):
        value = base_valid()
        p1, p2, p3 = value["consortium"]["members"]
        p1["country_code"] = "DE"
        p2["country_code"] = "DE"
        p1["person_months_milli"] = 12000
        p2["person_months_milli"] = 10000
        p3["person_months_milli"] = 10000
        self.assertIn("COUNTRY_WORKLOAD_OVER_HALF", reason_codes(compile_valid(value)))
