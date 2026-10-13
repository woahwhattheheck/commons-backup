import unittest

import validate_pack


class BoundaryMeshCarrierTests(unittest.TestCase):
    def test_carrier_validates(self):
        self.assertTrue(validate_pack.validate()["ok"], validate_pack.validate()["errors"])

    def test_budget_math_and_overhead_ceiling(self):
        budget = validate_pack.load_json("budget.json")
        direct = sum(row["amount"] for row in budget["direct_costs"])
        self.assertEqual(direct, 90000)
        self.assertEqual(budget["overhead"]["amount"], 9000)
        self.assertLessEqual(budget["overhead"]["amount"], direct * 0.10)
        self.assertEqual(budget["total_requested"], 99000)

    def test_no_submission_or_award_claim(self):
        opp = validate_pack.load_json("opportunity.json")
        self.assertEqual(opp["submission_status"], "NOT_SUBMITTED")
        self.assertEqual(opp["award_status"], "UNKNOWN")

    def test_deadline_exact(self):
        opp = validate_pack.load_json("opportunity.json")
        self.assertEqual(opp["deadline"], "2026-10-31T23:59:00-07:00")

    def test_all_deliverables_open_source(self):
        spec = validate_pack.load_json("project_spec.json")
        self.assertGreaterEqual(len(spec["deliverables"]), 5)
        self.assertTrue(all(row["open_source"] for row in spec["deliverables"]))

    def test_protocol_enum_bound_to_spec(self):
        spec = validate_pack.load_json("project_spec.json")
        schema = validate_pack.load_json("protocol_v0.schema.json")
        self.assertEqual(schema["properties"]["event_type"]["enum"], spec["event_types"])

    def test_seed_has_hostile_and_clean_cases(self):
        seed = validate_pack.load_json("benchmark_seed.json")
        expected = {row["expected"] for row in seed["scenarios"]}
        self.assertIn("ALLOW", expected)
        self.assertTrue(any(value.startswith("HOLD_") for value in expected))
        self.assertIn("REJECT_EVENT_ID_CONFLICT", expected)
        self.assertIn("IDEMPOTENT_REPLAY", expected)

    def test_scenario_ids_unique(self):
        seed = validate_pack.load_json("benchmark_seed.json")
        ids = [row["id"] for row in seed["scenarios"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_background_ip_boundary_is_explicit(self):
        spec = validate_pack.load_json("project_spec.json")
        boundary = spec["background_ip_boundary"]
        self.assertIn("not charged to the grant", boundary)
        self.assertIn("open-sourced", boundary)

    def test_application_map_admits_form_schema_gap(self):
        text = (validate_pack.ROOT / "application_fields.md").read_text(encoding="utf-8")
        self.assertIn("FORM_SCHEMA_PARTIAL", text)
        self.assertIn("does **not** invent exact form questions", text)

    def test_empirical_claim_is_target_not_result(self):
        text = (validate_pack.ROOT / "proposal.md").read_text(encoding="utf-8")
        self.assertIn("Those are targets, not pre-claimed results", text)

    def test_sources_include_live_form_and_official_rfp(self):
        opp = validate_pack.load_json("opportunity.json")
        joined = "\n".join(opp["sources"])
        self.assertIn("foresight.org/grants/ai-science-safety-nodes-rfp-coordination-and-accountability", joined)
        self.assertIn("airtable.com/appyVXc5SMPAvIKpP/pagp7takV26cG6JY1/form", joined)


if __name__ == "__main__":
    unittest.main()
