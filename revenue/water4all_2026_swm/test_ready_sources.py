"""Ready-path and official-source hostiles."""

from unittest.mock import patch

from .test_support import *  # noqa: F401,F403


class ReadyPathTests(unittest.TestCase):
    def test_valid_packet_reaches_owner_review(self):
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_valid(mode="CURRENT")
        self.assertEqual(bundle["packet"]["decision"]["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(bundle["packet"]["decision"]["reason_count"], 0)

    def test_ready_never_authorizes_external_action(self):
        authority = compile_valid()["packet"]["authority"]
        self.assertTrue(all(value is False for value in authority.values()))

    def test_repeat_compile_is_byte_deterministic(self):
        value = base_valid()
        one = compile_valid(value)
        two = compile_valid(copy.deepcopy(value))
        self.assertEqual(canonical_bytes(one), canonical_bytes(two))

    def test_historical_verify_is_integrity_only(self):
        value = base_valid()
        bundle = compile_valid(value)
        result = verify_bundle(value, bundle, T0 + dt.timedelta(days=300))
        self.assertTrue(result["valid"])
        self.assertTrue(result["historical_integrity_only"])
        self.assertFalse(result["current_semantics"])

    def test_current_uses_process_time_not_caller_backdate(self):
        value = base_valid()
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        self.assertEqual(bundle["packet"]["generated_at"], "2026-09-14T04:00:00Z")

    def test_current_verify_recompiles_live_semantics(self):
        value = base_valid()
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0 + dt.timedelta(seconds=60)):
            result = verify_bundle(value, bundle, T0 - dt.timedelta(days=100))
        self.assertTrue(result["current_semantics"])

    def test_current_verify_rejects_stale_packet_even_with_backdated_argument(self):
        value = base_valid()
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0 + dt.timedelta(seconds=301)):
            with self.assertRaisesRegex(ReadinessError, "freshness"):
                verify_bundle(value, bundle, T0)

    def test_receipt_tamper_is_rejected(self):
        value = base_valid()
        bundle = compile_valid(value)
        bundle["packet"]["decision"]["status"] = "READY_FOR_SUBMISSION"
        with self.assertRaisesRegex(ReadinessError, "receipt mismatch"):
            verify_bundle(value, bundle, T0)

    def test_input_generation_drift_is_rejected(self):
        value = base_valid()
        bundle = compile_valid(value)
        value["concept"]["concept_title"] = "changed"
        with self.assertRaisesRegex(ReadinessError, "exactly replay"):
            verify_bundle(value, bundle, T0)

    def test_markdown_is_explicitly_non_authoritative(self):
        text = render_owner_markdown(compile_valid())
        self.assertIn("External contact authorized: `false`", text)
        self.assertIn("Submission authorized: `false`", text)
        self.assertIn("not signatures", text)


class SourceAuthorityTests(unittest.TestCase):
    def test_live_official_deadline_conflict_holds(self):
        value = load_json("example_input.json")
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        self.assertEqual(bundle["packet"]["decision"]["status"], "HOLD_DEADLINE_SOURCE_CONFLICT")
        self.assertIn("DEADLINE_SOURCE_CONFLICT", reason_codes(bundle))
        self.assertIsNone(bundle["packet"]["deadline_authority"]["controlling_preproposal_deadline_at"])
        self.assertEqual(bundle["packet"]["deadline_authority"]["planning_only_earliest_deadline_at"], "2026-11-10T14:00:00Z")

    def test_reversing_sources_cannot_select_later_deadline(self):
        value = load_json("example_input.json")
        value["official_sources"].reverse()
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        self.assertIsNone(bundle["packet"]["deadline_authority"]["controlling_preproposal_deadline_at"])
        self.assertEqual(bundle["packet"]["deadline_authority"]["planning_only_earliest_deadline_at"], "2026-11-10T14:00:00Z")

    def test_required_source_missing_holds(self):
        value = base_valid()
        value["official_sources"] = [s for s in value["official_sources"] if s["authority_class"] != "OFFICIAL_NATIONAL_REGULATIONS"]
        self.assertIn("REQUIRED_SOURCE_MISSING", reason_codes(compile_valid(value)))

    def test_source_fact_commitment_tamper_holds(self):
        value = base_valid()
        value["official_sources"][0]["budget_eur_cents"] += 1
        bundle = compile_valid(value)
        self.assertIn("SOURCE_FACT_COMMITMENT_MISMATCH", reason_codes(bundle))
        self.assertIn("SOURCE_GENERATION_REGISTRY_MISMATCH", reason_codes(bundle))

    def test_source_stale_in_current_mode(self):
        value = base_valid()
        for source in value["official_sources"]:
            source["observed_at"] = "2026-08-01T00:00:00Z"
            reseal(source)
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        self.assertIn("SOURCE_OBSERVATION_STALE", reason_codes(bundle))
        self.assertIn("SOURCE_GENERATION_REGISTRY_MISMATCH", reason_codes(bundle))

    def test_resealed_historical_generation_cannot_mint_authority(self):
        value = base_valid()
        for source in value["official_sources"]:
            source["observed_at"] = "2026-08-01T00:00:00Z"
            reseal(source)
        bundle = compile_at(value, T0, "HISTORICAL")
        self.assertNotIn("SOURCE_OBSERVATION_STALE", reason_codes(bundle))
        self.assertIn("SOURCE_GENERATION_REGISTRY_MISMATCH", reason_codes(bundle))
        self.assertEqual(bundle["packet"]["decision"]["status"], "HOLD_SOURCE_AUTHORITY")

    def test_future_source_holds(self):
        value = base_valid()
        value["official_sources"][0]["observed_at"] = "2026-09-14T05:00:00Z"
        reseal(value["official_sources"][0])
        self.assertIn("SOURCE_OBSERVED_IN_FUTURE", reason_codes(compile_valid(value)))

    def test_incomplete_source_holds(self):
        value = base_valid()
        value["official_sources"][0]["complete"] = False
        reseal(value["official_sources"][0])
        self.assertIn("SOURCE_INCOMPLETE", reason_codes(compile_valid(value)))

    def test_not_current_source_holds(self):
        value = base_valid()
        value["official_sources"][0]["declared_current"] = False
        reseal(value["official_sources"][0])
        self.assertIn("SOURCE_NOT_DECLARED_CURRENT", reason_codes(compile_valid(value)))

    def test_duplicate_source_id_rejected(self):
        value = base_valid()
        value["official_sources"].append(copy.deepcopy(value["official_sources"][0]))
        with self.assertRaisesRegex(ReadinessError, "duplicate source_id"):
            compile_valid(value)

    def test_duplicate_source_class_holds(self):
        value = base_valid()
        duplicate = copy.deepcopy(value["official_sources"][0])
        duplicate["source_id"] = "second-call-page"
        reseal(duplicate)
        value["official_sources"].append(duplicate)
        self.assertIn("DUPLICATE_SOURCE_CLASS", reason_codes(compile_valid(value)))

    def test_budget_conflict_holds(self):
        value = base_valid()
        value["official_sources"][0]["budget_eur_cents"] += 100
        reseal(value["official_sources"][0])
        self.assertIn("CALL_BUDGET_SOURCE_CONFLICT", reason_codes(compile_valid(value)))

    def test_full_proposal_deadline_conflict_holds(self):
        value = base_valid()
        value["official_sources"][0]["full_proposal_deadline_at"] = "2027-04-07T13:00:00Z"
        reseal(value["official_sources"][0])
        self.assertIn("FULL_PROPOSAL_DEADLINE_CONFLICT", reason_codes(compile_valid(value)))
