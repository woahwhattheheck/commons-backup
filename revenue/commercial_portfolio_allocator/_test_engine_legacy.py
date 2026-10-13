from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from .acceptance import NOW, acceptance_summary, base_packet, opportunity
from .engine import ContractError, compile_plan, derive_collision_key, render_markdown, verify_plan


class CommercialPortfolioAllocatorTests(unittest.TestCase):
    def test_single_active_opportunity_selected(self):
        p = base_packet("single")
        p["opportunities"] = [opportunity("x")]
        plan = compile_plan(p, now=NOW)
        self.assertEqual(plan["stage"], "ALLOCATED")
        self.assertEqual([x["opportunity_id"] for x in plan["selected"]], ["x"])

    def test_dnr_huge_value_never_selected(self):
        p = base_packet("dnr")
        p["opportunities"] = [opportunity("good"), opportunity("dnr", gross=10_000_000, conversion=1_000_000, state="DNR")]
        plan = compile_plan(p, now=NOW)
        self.assertEqual([x["opportunity_id"] for x in plan["selected"]], ["good"])
        self.assertIn("DNR", next(x for x in plan["suppressed"] if x["opportunity_id"] == "dnr")["reasons"])

    def test_closed_and_blocked_suppressed(self):
        p = base_packet("states")
        p["opportunities"] = [opportunity("closed", state="CLOSED"), opportunity("blocked", state="BLOCKED")]
        plan = compile_plan(p, now=NOW)
        reasons = {x["opportunity_id"]: x["reasons"] for x in plan["suppressed"]}
        self.assertIn("CLOSED", reasons["closed"])
        self.assertIn("BLOCKED", reasons["blocked"])

    def test_missing_dependency_suppressed(self):
        p = base_packet("dep")
        p["opportunities"] = [opportunity("x", requires=["missing"])]
        self.assertIn("DEPENDENCY_UNSATISFIED", compile_plan(p, now=NOW)["suppressed"][0]["reasons"])

    def test_prerequisites_not_ready_suppressed(self):
        p = base_packet("pre")
        p["opportunities"] = [opportunity("x", prereq=False)]
        self.assertIn("PREREQUISITES_NOT_READY", compile_plan(p, now=NOW)["suppressed"][0]["reasons"])

    def test_owner_review_not_ready_suppressed(self):
        p = base_packet("owner")
        p["opportunities"] = [opportunity("x", owner_ready=False)]
        self.assertIn("OWNER_REVIEW_NOT_READY", compile_plan(p, now=NOW)["suppressed"][0]["reasons"])

    def test_deadline_passed_suppressed(self):
        p = base_packet("deadline")
        p["opportunities"] = [opportunity("x", deadline="2026-09-13T16:00:00Z")]
        self.assertIn("DEADLINE_PASSED", compile_plan(p, now=NOW)["suppressed"][0]["reasons"])

    def test_outside_horizon_suppressed(self):
        p = base_packet("horizon")
        p["opportunities"] = [opportunity("x", deadline="2026-09-21T16:00:00Z")]
        self.assertIn("OUTSIDE_HORIZON", compile_plan(p, now=NOW)["suppressed"][0]["reasons"])

    def test_stale_evidence_suppressed(self):
        p = base_packet("stale")
        p["evidence_max_age_seconds"] = 60
        p["opportunities"] = [opportunity("x", observed="2026-09-13T15:58:00Z")]
        self.assertIn("STALE_EVIDENCE", compile_plan(p, now=NOW)["suppressed"][0]["reasons"])

    def test_future_evidence_holds_portfolio(self):
        p = base_packet("future")
        p["opportunities"] = [opportunity("x", observed="2026-09-13T16:00:01Z")]
        plan = compile_plan(p, now=NOW)
        self.assertEqual(plan["stage"], "HOLD")
        self.assertIn("FUTURE_EVIDENCE", plan["portfolio_reasons"])
        self.assertEqual(plan["selected"], [])

    def test_collision_key_conflict_holds_portfolio(self):
        p = base_packet("collision")
        p["opportunities"] = [opportunity("a", buyer_id="buyer-shared", opportunity_key="shared-rfp"), opportunity("b", buyer_id="buyer-shared", opportunity_key="shared-rfp")]
        plan = compile_plan(p, now=NOW)
        self.assertEqual(plan["stage"], "HOLD")
        self.assertIn("COLLISION_KEY_CONFLICT", plan["portfolio_reasons"])


    def test_hard_hold_does_not_mislabel_capacity_selection(self):
        p = base_packet("hold-reason")
        p["opportunities"] = [opportunity("a", buyer_id="buyer-shared", opportunity_key="shared-rfp"), opportunity("b", buyer_id="buyer-shared", opportunity_key="shared-rfp")]
        plan = compile_plan(p, now=NOW)
        self.assertEqual(plan["stage"], "HOLD")
        self.assertTrue(plan["suppressed"])
        self.assertTrue(all(x["reasons"] == ["PORTFOLIO_HOLD"] for x in plan["suppressed"]))

    def test_forged_collision_key_rejected(self):
        p = base_packet("forged-collision")
        x = opportunity("x")
        x["collision_key"] = "0" * 64
        p["opportunities"] = [x]
        with self.assertRaises(ContractError):
            compile_plan(p, now=NOW)

    def test_collision_key_derivation_is_stable(self):
        self.assertEqual(derive_collision_key("buyer-acme", "rfp-123"), derive_collision_key("buyer-acme", "rfp-123"))
        self.assertNotEqual(derive_collision_key("buyer-acme", "rfp-123"), derive_collision_key("buyer-acme", "rfp-124"))

    def test_changed_same_opportunity_id_holds(self):
        p = base_packet("conflict")
        a = opportunity("x")
        b = copy.deepcopy(a)
        b["gross_value_minor"] += 1
        p["opportunities"] = [a, b]
        plan = compile_plan(p, now=NOW)
        self.assertIn("OPPORTUNITY_ID_CONFLICT", plan["portfolio_reasons"])
        self.assertEqual(plan["stage"], "HOLD")

    def test_exact_replay_collapses(self):
        p = base_packet("replay")
        a = opportunity("x")
        p["opportunities"] = [a, copy.deepcopy(a)]
        plan = compile_plan(p, now=NOW)
        self.assertEqual(plan["replay_collapses"], 1)
        self.assertEqual(plan["stage"], "ALLOCATED")
        self.assertEqual(len(plan["selected"]), 1)

    def test_global_knapsack_beats_greedy_big_item(self):
        p = base_packet("knapsack")
        p["opportunities"] = [
            opportunity("big", gross=100000, conversion=1_000_000, risk=0, effort=6),
            opportunity("small-a", gross=60000, conversion=1_000_000, risk=0, effort=3),
            opportunity("small-b", gross=60000, conversion=1_000_000, risk=0, effort=3),
        ]
        plan = compile_plan(p, now=NOW)
        self.assertEqual([x["opportunity_id"] for x in plan["selected"]], ["small-a", "small-b"])
        self.assertEqual(plan["used_capacity_units"], 6)

    def test_tie_break_is_lexicographic(self):
        p = base_packet("tie")
        p["capacity_units"] = 1
        p["opportunities"] = [opportunity("b", effort=1), opportunity("a", effort=1)]
        plan = compile_plan(p, now=NOW)
        self.assertEqual([x["opportunity_id"] for x in plan["selected"]], ["a"])

    def test_same_stage_can_have_different_declared_conversion(self):
        p = base_packet("conv")
        p["capacity_units"] = 4
        p["opportunities"] = [opportunity("lo", conversion=200000), opportunity("hi", conversion=800000)]
        plan = compile_plan(p, now=NOW)
        metrics = {x["opportunity_id"]: x["metrics"] for x in plan["selected"]}
        self.assertGreater(metrics["hi"]["expected_cash_pipeline_minor"], metrics["lo"]["expected_cash_pipeline_minor"])

    def test_zero_conversion_suppressed(self):
        p = base_packet("zero")
        p["opportunities"] = [opportunity("x", conversion=0)]
        plan = compile_plan(p, now=NOW)
        self.assertEqual(plan["stage"], "NO_ELIGIBLE")
        self.assertIn("ZERO_ALLOCATABLE_VALUE", plan["suppressed"][0]["reasons"])

    def test_effort_above_capacity_suppressed(self):
        p = base_packet("effort")
        p["capacity_units"] = 2
        p["opportunities"] = [opportunity("x", effort=3)]
        self.assertIn("EFFORT_EXCEEDS_CAPACITY", compile_plan(p, now=NOW)["suppressed"][0]["reasons"])

    def test_risk_reduces_objective(self):
        p = base_packet("risk")
        p["capacity_units"] = 4
        p["opportunities"] = [opportunity("low", risk=0), opportunity("high", risk=900000)]
        plan = compile_plan(p, now=NOW)
        m = {x["opportunity_id"]: x["metrics"] for x in plan["selected"]}
        self.assertGreater(m["low"]["objective_points"], m["high"]["objective_points"])

    def test_strategic_weight_is_declared_input(self):
        p = base_packet("weight")
        p["capacity_units"] = 4
        p["opportunities"] = [opportunity("one", weight=500000), opportunity("two", weight=1500000)]
        plan = compile_plan(p, now=NOW)
        m = {x["opportunity_id"]: x["metrics"] for x in plan["selected"]}
        self.assertGreater(m["two"]["objective_points"], m["one"]["objective_points"])

    def test_nearer_deadline_has_higher_urgency(self):
        p = base_packet("urgency")
        p["capacity_units"] = 4
        p["opportunities"] = [
            opportunity("near", deadline="2026-09-14T16:00:00Z"),
            opportunity("far", deadline="2026-09-20T16:00:00Z"),
        ]
        plan = compile_plan(p, now=NOW)
        m = {x["opportunity_id"]: x["metrics"] for x in plan["selected"]}
        self.assertGreater(m["near"]["urgency_ppm"], m["far"]["urgency_ppm"])

    def test_order_invariant_receipt(self):
        p = base_packet("order")
        p["opportunities"] = [opportunity("c"), opportunity("a"), opportunity("b")]
        first = compile_plan(p, now=NOW)
        p["opportunities"] = list(reversed(p["opportunities"]))
        second = compile_plan(p, now=NOW)
        self.assertEqual(first, second)

    def test_pipeline_never_becomes_booked_revenue(self):
        p = base_packet("truth")
        p["opportunities"] = [opportunity("x", gross=900000, conversion=1_000_000, risk=0)]
        plan = compile_plan(p, now=NOW)
        self.assertGreater(plan["selected_expected_cash_pipeline_minor"], 0)
        self.assertEqual(plan["booked_revenue_minor"], 0)
        self.assertEqual(plan["recognized_revenue_minor"], 0)

    def test_authority_ceiling_all_false(self):
        p = base_packet("ceiling")
        p["opportunities"] = [opportunity("x")]
        self.assertTrue(all(value is False for value in compile_plan(p, now=NOW)["authority_ceiling"].values()))

    def test_horizon_elapsed_yields_no_eligible(self):
        p = base_packet("elapsed")
        p["horizon_end"] = "2026-09-13T15:59:59Z"
        p["opportunities"] = [opportunity("x", deadline="2026-09-14T16:00:00Z")]
        plan = compile_plan(p, now=NOW)
        self.assertEqual(plan["stage"], "NO_ELIGIBLE")
        self.assertIn("HORIZON_ELAPSED", plan["suppressed"][0]["reasons"])

    def test_currency_mismatch_rejected(self):
        p = base_packet("currency")
        x = opportunity("x")
        x["currency"] = "EUR"
        p["opportunities"] = [x]
        with self.assertRaises(ContractError):
            compile_plan(p, now=NOW)

    def test_unknown_keys_rejected(self):
        p = base_packet("keys")
        p["unexpected"] = True
        with self.assertRaises(ContractError):
            compile_plan(p, now=NOW)

    def test_verifier_detects_tamper(self):
        p = base_packet("verify")
        p["opportunities"] = [opportunity("x")]
        plan = compile_plan(p, now=NOW)
        self.assertTrue(verify_plan(p, plan, now=NOW)["historical_valid"])
        tampered = copy.deepcopy(plan)
        tampered["booked_revenue_minor"] = 100
        self.assertFalse(verify_plan(p, tampered, now=NOW)["historical_valid"])

    def test_verifier_recompiles_current_state(self):
        p = base_packet("current")
        p["opportunities"] = [opportunity("x", deadline="2026-09-14T16:00:00Z")]
        plan = compile_plan(p, now=NOW)
        later = datetime(2026, 9, 15, 16, 0, tzinfo=timezone.utc)
        result = verify_plan(p, plan, now=later)
        self.assertTrue(result["historical_valid"])
        self.assertEqual(result["current_stage"], "NO_ELIGIBLE")

    def test_markdown_repeats_truth_boundary(self):
        p = base_packet("markdown")
        p["opportunities"] = [opportunity("x")]
        text = render_markdown(compile_plan(p, now=NOW))
        self.assertIn("Booked revenue by allocator: `0`", text)
        self.assertIn("does not authorize contact", text)

    def test_acceptance_fixture(self):
        summary = acceptance_summary()
        self.assertEqual(summary["count"], 10)
        self.assertEqual(summary["stages"]["HOLD"], 2)
        self.assertGreaterEqual(summary["stages"]["NO_ELIGIBLE"], 1)


if __name__ == "__main__":
    unittest.main()
