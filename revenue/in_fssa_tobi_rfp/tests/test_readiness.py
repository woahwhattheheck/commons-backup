import copy
import unittest

from revenue.in_fssa_tobi_rfp.readiness import Decision, InputError, OFFICIAL_BOARD_URL, evaluate, loads_strict


def base():
    refs = []
    for i in range(3):
        refs.append({"reference_id": f"r{i}", "client": f"c{i}", "contact_name": f"n{i}", "contact_method": f"m{i}", "permission_confirmed": True, "case_management_relevant": i != 1, "state_human_services_relevant": i == 1, "observed_at": "2026-09-12T12:00:00-04:00"})
    return {
        "rfp_id": "26-86873", "event_id": "004100000086873", "role_intent": "auto",
        "evaluated_at": "2026-09-13T05:45:00-04:00", "proposal_due_at": "2026-09-16T15:00:00-04:00",
        "official_source": {"url": OFFICIAL_BOARD_URL, "rfp_id": "26-86873", "event_id": "004100000086873", "observed_at": "2026-09-13T05:30:00-04:00"},
        "capabilities": {"cloud_case_management": True, "information_security_framework": True, "accessibility": True, "provider_management_application": True, "bidirectional_integrations": ["CMHW_PORTAL", "DARMHA", "COREMMIS"], "training_modes": ["telephone", "virtual", "onsite"], "help_desk": {"ticketing": "Jira", "response_business_hours": 48}},
        "prime_authority": {"indiana_registration": True, "bidder_database_registration": True, "financial_stability": {"two_completed_fiscal_years": True, "verifiable_records": True}, "ivosb_plan": {"target_percent": 3, "evidence_backed": True}},
        "proposal_components": {"executive": True, "business": True, "technical": True, "cost": True, "state_forms": True, "reference_forms": True},
        "references": refs,
        "subcontract": {"prime_partner_confirmed": True, "prime_partner_id": "prime-1", "scope": ["integration_mapping", "migration_validation", "qa_automation", "acceptance_evidence"], "represents_prime_qualifications": False},
    }


class T(unittest.TestCase):
    def decision(self, d, expected):
        self.assertEqual(evaluate(d).decision, expected)

    def test_ready_paths_and_receipt_authority(self):
        for role, expected in [("prime", Decision.PRIME_READY.value), ("subcontract", Decision.SUBCONTRACT_READY.value), ("auto", Decision.PRIME_READY.value)]:
            d = base(); d["role_intent"] = role; r = evaluate(d)
            self.assertEqual(r.decision, expected); self.assertFalse(r.may_submit_bid); self.assertFalse(r.may_contact_buyer); self.assertFalse(r.may_quote_price); self.assertEqual(r.revenue_status, "UNREALIZED")
        d = base(); d["prime_authority"]["indiana_registration"] = False; self.decision(d, Decision.SUBCONTRACT_READY.value)

    def test_identity_time_source_fail_closed(self):
        for mutate in [lambda d: d.update(rfp_id="x"), lambda d: d.update(proposal_due_at="2026-09-17T15:00:00-04:00"), lambda d: d.update(evaluated_at="2026-09-13T05:45:00")]:
            d = base(); mutate(d)
            with self.assertRaises(InputError): evaluate(d)
        for observed in ["2026-09-01T00:00:00-04:00", "2026-09-14T00:00:00-04:00"]:
            d = base(); d["official_source"]["observed_at"] = observed; self.decision(d, Decision.HOLD.value)
        d = base(); d["official_source"]["url"] = "https://example.com"; self.decision(d, Decision.HOLD.value)
        d = base(); d["evaluated_at"] = "2026-09-16T15:00:00-04:00"; d["official_source"]["observed_at"] = "2026-09-16T14:00:00-04:00"; self.decision(d, Decision.NO_BID.value)

    def test_technical_capability_matrix(self):
        for key in ["cloud_case_management", "information_security_framework", "accessibility", "provider_management_application"]:
            d = base(); d["capabilities"][key] = False; self.decision(d, Decision.HOLD.value)
        d = base(); d["capabilities"]["bidirectional_integrations"].remove("COREMMIS"); self.decision(d, Decision.HOLD.value)
        d = base(); d["capabilities"]["training_modes"].remove("telephone"); self.decision(d, Decision.HOLD.value)
        for ticket, hours in [("Zendesk", 48), ("Jira", 49), ("Jira", 0)]:
            d = base(); d["capabilities"]["help_desk"] = {"ticketing": ticket, "response_business_hours": hours}; self.decision(d, Decision.HOLD.value)

    def test_prime_admin_matrix(self):
        for key in ["indiana_registration", "bidder_database_registration"]:
            d = base(); d["role_intent"] = "prime"; d["prime_authority"][key] = False; self.decision(d, Decision.HOLD.value)
        d = base(); d["role_intent"] = "prime"; d["prime_authority"]["financial_stability"]["two_completed_fiscal_years"] = False; self.decision(d, Decision.HOLD.value)
        d = base(); d["role_intent"] = "prime"; d["prime_authority"]["ivosb_plan"]["target_percent"] = 2.99; self.decision(d, Decision.HOLD.value)
        d = base(); d["role_intent"] = "prime"; d["proposal_components"]["technical"] = False; self.decision(d, Decision.HOLD.value)

    def test_reference_integrity(self):
        mods = [lambda d: d.update(references=d["references"][:2]), lambda d: d["references"][2].update(reference_id="r1"), lambda d: d["references"][0].update(permission_confirmed=False), lambda d: d["references"][0].update(observed_at="2026-09-14T00:00:00-04:00"), lambda d: d["references"][0].update(contact_method="")]
        for mutate in mods:
            d = base(); d["role_intent"] = "prime"; mutate(d); self.decision(d, Decision.HOLD.value)

    def test_subcontract_boundary(self):
        d = base(); d["role_intent"] = "subcontract"; d["prime_authority"] = {}; d["references"] = []; self.decision(d, Decision.SUBCONTRACT_READY.value)
        for mutate in [lambda d: d["subcontract"].update(prime_partner_confirmed=False), lambda d: d["subcontract"].update(scope=["full_prime_delivery"]), lambda d: d["subcontract"].update(represents_prime_qualifications=True)]:
            d = base(); d["role_intent"] = "subcontract"; mutate(d); self.decision(d, Decision.HOLD.value)

    def test_parser_and_input_hardening(self):
        for text in ['{"a":1,"a":2}', '{"a":NaN}']:
            with self.assertRaises(InputError): loads_strict(text)
        d = base(); d["api_key"] = "x"
        with self.assertRaises(InputError): evaluate(d)
        d = base(); d["subcontract"]["prime_partner_id"] = "x" * 5000
        with self.assertRaises(InputError): evaluate(d)
        d = base(); d["prime_authority"]["ivosb_plan"]["target_percent"] = float("nan")
        with self.assertRaises(InputError): evaluate(d)

    def test_determinism(self):
        a = evaluate(base()); b = evaluate(copy.deepcopy(base()))
        self.assertEqual(a.input_digest, b.input_digest); self.assertEqual([x.code for x in a.findings], [x.code for x in b.findings])


if __name__ == "__main__":
    unittest.main()
