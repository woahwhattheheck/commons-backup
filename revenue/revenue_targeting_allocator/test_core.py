from .test_support import *


class CoreTests(AllocatorBase):
    def test_fixture_compiles(self):
        raw = json.loads(FIXTURE.read_text())
        out, md, receipt = compile_portfolio(raw)
        self.assertEqual(out["counts"], {"total": 4, "expected_value": 2, "evidence_strength": 1, "hold": 1})
        self.assertIn("RELATIONSHIP_DNR", md)
        self.assertFalse(receipt["payment_or_revenue_inferred"])

    def test_input_order_does_not_change_output(self):
        a = candidate(opportunity_id="opp-a", probability_bps=2500, evidence_bundle_sha256=digest("a"))
        b = candidate(opportunity_id="opp-b", probability_bps=5000, evidence_bundle_sha256=digest("b"))
        out1, md1, _ = compile_portfolio(document(a, b))
        out2, md2, _ = compile_portfolio(document(b, a))
        self.assertEqual(out1, out2)
        self.assertEqual(md1, md2)

    def test_expected_value_integer_ranking(self):
        a = candidate(opportunity_id="opp-a", commercial_value_minor=1001, probability_bps=5000, evidence_bundle_sha256=digest("a"))
        b = candidate(opportunity_id="opp-b", commercial_value_minor=800, probability_bps=7000, evidence_bundle_sha256=digest("b"))
        out, _, _ = compile_portfolio(document(a, b))
        rows = [r for r in out["rows"] if r["queue"] == "EXPECTED_VALUE"]
        self.assertEqual([r["opportunity_id"] for r in rows], ["opp-b", "opp-a"])
        self.assertEqual([r["expected_value_minor"] for r in rows], [560, 500])

    def test_missing_probability_never_invented(self):
        out, _, _ = compile_portfolio(document(candidate()))
        row = out["rows"][0]
        self.assertEqual(row["queue"], "EVIDENCE_STRENGTH")
        self.assertIsNone(row["probability_bps"])
        self.assertIsNone(row["expected_value_minor"])

    def test_mixed_currency_never_fx_compared(self):
        usd = candidate(opportunity_id="usd", currency="USD", probability_bps=5000, evidence_bundle_sha256=digest("usd"))
        eur = candidate(opportunity_id="eur", currency="EUR", probability_bps=5000, evidence_bundle_sha256=digest("eur"))
        out, md, _ = compile_portfolio(document(usd, eur))
        self.assertEqual({r["currency"] for r in out["rows"]}, {"USD", "EUR"})
        self.assertTrue(all(r["rank"] == 1 for r in out["rows"]))
        self.assertIn("never converted", md)

    def test_dnr_holds(self):
        self.assertIn("RELATIONSHIP_DNR", self.assertHold(relationship_state="DNR")["hold_reasons"])

    def test_optout_holds(self):
        self.assertIn("RELATIONSHIP_OPTOUT", self.assertHold(relationship_state="OPTOUT")["hold_reasons"])

    def test_unknown_route_holds(self):
        self.assertIn("ROUTE_UNKNOWN", self.assertHold(route_state="UNKNOWN")["hold_reasons"])

    def test_foreign_collision_holds(self):
        self.assertIn("COLLISION_OWNED_OTHER", self.assertHold(collision_state="OWNED_OTHER")["hold_reasons"])

    def test_stale_evidence_holds(self):
        self.assertIn("EVIDENCE_STALE", self.assertHold(freshness_state="STALE")["hold_reasons"])

    def test_buyer_stage_conflict_holds(self):
        self.assertIn("BUYER_STAGE_CONFLICT", self.assertHold(buyer_stage_state="CONFLICT")["hold_reasons"])

    def test_unknown_fit_holds(self):
        self.assertIn("FIT_UNKNOWN", self.assertHold(fit_state="UNKNOWN")["hold_reasons"])

    def test_delivery_hold_holds(self):
        self.assertIn("DELIVERY_HOLD", self.assertHold(delivery_state="HOLD")["hold_reasons"])

    def test_nonpositive_value_holds(self):
        self.assertIn("NON_POSITIVE_COMMERCIAL_VALUE", self.assertHold(commercial_value_minor=0)["hold_reasons"])

