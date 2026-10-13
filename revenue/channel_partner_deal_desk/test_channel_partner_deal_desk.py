import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from channel_partner_deal_desk import ConflictError, DealDesk, DeskError, apply_mutation, canonical_bytes, run_demo, strict_json_loads


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class DeskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "desk.sqlite")
        self.desk = DealDesk(self.db)
        self.desk.add_partner(operation_key="op.partner", partner_id="partner.a", display_name="Partner A",
                              created_at="2026-09-16T10:00:00Z", source_ref="fixture:partner", source_sha256=h("p"))
        self.desk.add_terms(operation_key="op.terms", terms_id="terms.a.1", partner_id="partner.a", revision=1,
                            commission_bps=1500, protection_days=30, effective_at="2026-09-16T10:00:00Z",
                            source_ref="fixture:terms", source_sha256=h("t"))

    def tearDown(self):
        self.desk.close()
        self.tmp.cleanup()

    def register(self, **overrides):
        data = dict(operation_key="op.deal", deal_id="deal.a", partner_id="partner.a", terms_id="terms.a.1",
                    buyer_key="buyer.1", opportunity_key="opp.1", registered_at="2026-09-16T11:00:00Z",
                    scope_sha256=h("scope"), currency="USD", proposed_value_minor=100_000,
                    source_ref="fixture:deal", source_sha256=h("d"))
        data.update(overrides)
        return self.desk.register_deal(**data)

    def accept(self, when="2026-09-17T00:00:00Z"):
        return self.desk.add_event(operation_key="op.accept", event_id="event.accept", deal_id="deal.a",
                                   kind="BUYER_ACCEPTED", occurred_at=when, source_ref="fixture:accept",
                                   source_sha256=h("a"))

    def test_happy_path_due_then_paid_evidence(self):
        self.register(); self.accept()
        self.desk.add_event(operation_key="op.settle", event_id="event.settle", deal_id="deal.a", kind="PAYMENT_SETTLED",
                            occurred_at="2026-09-18T00:00:00Z", amount_minor=100_000, currency="USD",
                            source_ref="fixture:settle", source_sha256=h("s"))
        row = self.desk.compile_deal("deal.a")
        self.assertEqual(row["state"], "COMMISSION_DUE_FOR_OWNER_REVIEW")
        self.assertEqual(row["computed_commission_minor"], 15_000)
        self.desk.add_event(operation_key="op.paid", event_id="event.paid", deal_id="deal.a",
                            kind="PARTNER_PAYMENT_RECORDED", occurred_at="2026-09-19T00:00:00Z",
                            amount_minor=15_000, currency="USD", source_ref="fixture:payout", source_sha256=h("pay"))
        row = self.desk.compile_deal("deal.a")
        self.assertEqual(row["state"], "PAID_EVIDENCE")
        self.assertEqual(row["commission_outstanding_minor"], 0)

    def test_operation_replay_and_changed_payload_conflict(self):
        first = self.register(); second = self.register()
        self.assertEqual(first, second)
        with self.assertRaises(ConflictError):
            self.register(proposed_value_minor=100_001)

    def test_registration_collision_is_durable_hold(self):
        self.register()
        result = self.desk.register_deal(operation_key="op.deal2", deal_id="deal.b", partner_id="partner.a",
                                         terms_id="terms.a.1", buyer_key="buyer.1", opportunity_key="opp.1",
                                         registered_at="2026-09-16T12:00:00Z", scope_sha256=h("scope2"), currency="USD",
                                         proposed_value_minor=120_000, source_ref="fixture:deal2", source_sha256=h("d2"))
        self.assertEqual(result["status"], "HOLD_REGISTRATION_CONFLICT")
        self.assertEqual(result["existing_deal_id"], "deal.a")
        snap = self.desk.snapshot()
        self.assertEqual(len(snap["registration_conflicts"]), 1)

    def test_terms_generation_is_bound_to_deal(self):
        self.register(); self.accept()
        self.desk.add_terms(operation_key="op.terms2", terms_id="terms.a.2", partner_id="partner.a", revision=2,
                            commission_bps=3000, protection_days=60, effective_at="2026-09-17T10:00:00Z",
                            source_ref="fixture:terms2", source_sha256=h("t2"))
        self.desk.add_event(operation_key="op.settle", event_id="event.settle", deal_id="deal.a", kind="PAYMENT_SETTLED",
                            occurred_at="2026-09-18T00:00:00Z", amount_minor=100_000, currency="USD",
                            source_ref="fixture:settle", source_sha256=h("s"))
        self.assertEqual(self.desk.compile_deal("deal.a")["computed_commission_minor"], 15_000)

    def test_acceptance_after_protection_holds(self):
        self.register()
        self.accept("2026-10-20T00:00:00Z")
        self.assertEqual(self.desk.compile_deal("deal.a")["state"], "HOLD_PROTECTION_EXPIRED")

    def test_financial_event_requires_acceptance_and_matching_currency(self):
        self.register()
        with self.assertRaises(DeskError):
            self.desk.add_event(operation_key="x", event_id="event.x", deal_id="deal.a", kind="PAYMENT_SETTLED",
                                occurred_at="2026-09-18T00:00:00Z", amount_minor=1, currency="USD",
                                source_ref="fixture:x", source_sha256=h("x"))
        self.accept()
        with self.assertRaises(DeskError):
            self.desk.add_event(operation_key="y", event_id="event.y", deal_id="deal.a", kind="PAYMENT_SETTLED",
                                occurred_at="2026-09-18T00:00:00Z", amount_minor=1, currency="EUR",
                                source_ref="fixture:y", source_sha256=h("y"))

    def test_financial_event_cannot_predate_acceptance(self):
        self.register(); self.accept("2026-09-18T00:00:00Z")
        with self.assertRaises(DeskError):
            self.desk.add_event(operation_key="early", event_id="event.early", deal_id="deal.a", kind="PAYMENT_SETTLED",
                                occurred_at="2026-09-17T23:59:59Z", amount_minor=10_000, currency="USD",
                                source_ref="fixture:early", source_sha256=h("early"))

    def test_apply_mutation_strict_surface(self):
        result = apply_mutation(self.desk, {
            "action": "REGISTER_DEAL", "operation_key": "apply.deal", "deal_id": "deal.apply",
            "partner_id": "partner.a", "terms_id": "terms.a.1", "buyer_key": "buyer.apply",
            "opportunity_key": "opp.apply", "registered_at": "2026-09-16T11:00:00Z",
            "scope_sha256": h("apply-scope"), "currency": "USD", "proposed_value_minor": 42_000,
            "source_ref": "fixture:apply", "source_sha256": h("apply")
        })
        self.assertEqual(result["status"], "DEAL_REGISTERED")
        with self.assertRaises(DeskError):
            apply_mutation(self.desk, {"action": "REGISTER_DEAL", "surprise": True})
        with self.assertRaises(DeskError):
            apply_mutation(self.desk, {"action": "PURGE_LEDGER", "operation_key": "apply.purge"})

    def test_reversal_recomputes_due_and_cannot_cross_paid(self):
        self.register(); self.accept()
        self.desk.add_event(operation_key="s", event_id="event.s", deal_id="deal.a", kind="PAYMENT_SETTLED",
                            occurred_at="2026-09-18T00:00:00Z", amount_minor=100_000, currency="USD",
                            source_ref="fixture:s", source_sha256=h("s"))
        self.desk.add_event(operation_key="r", event_id="event.r", deal_id="deal.a", kind="PAYMENT_REVERSED",
                            occurred_at="2026-09-19T00:00:00Z", amount_minor=20_000, currency="USD",
                            source_ref="fixture:r", source_sha256=h("r"))
        self.assertEqual(self.desk.compile_deal("deal.a")["computed_commission_minor"], 12_000)
        with self.assertRaises(DeskError):
            self.desk.add_event(operation_key="r2", event_id="event.r2", deal_id="deal.a", kind="PAYMENT_REVERSED",
                                occurred_at="2026-09-19T01:00:00Z", amount_minor=90_000, currency="USD",
                                source_ref="fixture:r2", source_sha256=h("r2"))

    def test_partner_payment_cannot_exceed_due(self):
        self.register(); self.accept()
        self.desk.add_event(operation_key="s", event_id="event.s", deal_id="deal.a", kind="PAYMENT_SETTLED",
                            occurred_at="2026-09-18T00:00:00Z", amount_minor=10_000, currency="USD",
                            source_ref="fixture:s", source_sha256=h("s"))
        with self.assertRaises(DeskError):
            self.desk.add_event(operation_key="p", event_id="event.p", deal_id="deal.a", kind="PARTNER_PAYMENT_RECORDED",
                                occurred_at="2026-09-19T00:00:00Z", amount_minor=1_501, currency="USD",
                                source_ref="fixture:p", source_sha256=h("p2"))

    def test_export_verify_restart_and_tamper(self):
        self.register(); self.accept()
        out = Path(self.tmp.name) / "out"
        self.desk.export(out)
        self.assertTrue(self.desk.verify_export(out))
        self.desk.close()
        self.desk = DealDesk(self.db)
        self.assertTrue(self.desk.verify_export(out))
        path = out / "channel_partner_review.md"
        path.write_text(path.read_text() + "tamper", encoding="utf-8")
        with self.assertRaises(DeskError):
            self.desk.verify_export(out)

    def test_export_refuses_overwrite(self):
        self.register()
        out = Path(self.tmp.name) / "out"
        self.desk.export(out)
        with self.assertRaises(FileExistsError):
            self.desk.export(out)

    def test_snapshot_is_order_stable(self):
        self.register(); self.accept()
        a = canonical_bytes(self.desk.snapshot())
        b = canonical_bytes(self.desk.snapshot())
        self.assertEqual(a, b)

    def test_bool_is_not_integer(self):
        with self.assertRaises(DeskError):
            self.desk.add_terms(operation_key="bad", terms_id="terms.bad", partner_id="partner.a", revision=2,
                                commission_bps=True, protection_days=1, effective_at="2026-09-17T00:00:00Z",
                                source_ref="fixture:bad", source_sha256=h("bad"))

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        with self.assertRaises(DeskError): strict_json_loads('{"a":1,"a":2}')
        with self.assertRaises(DeskError): strict_json_loads('{"a":NaN}')

    def test_event_cannot_predate_registration(self):
        self.register()
        with self.assertRaises(DeskError):
            self.accept("2026-09-16T10:59:59Z")

    def test_backdated_financial_timeline_is_rejected(self):
        self.register(); self.accept()
        self.desk.add_event(operation_key="late.settle", event_id="event.zsettle", deal_id="deal.a", kind="PAYMENT_SETTLED",
                            occurred_at="2026-09-20T00:00:00Z", amount_minor=100_000, currency="USD",
                            source_ref="fixture:late-settle", source_sha256=h("late-settle"))
        with self.assertRaises(DeskError):
            self.desk.add_event(operation_key="early.reverse", event_id="event.areverse", deal_id="deal.a", kind="PAYMENT_REVERSED",
                                occurred_at="2026-09-19T00:00:00Z", amount_minor=1, currency="USD",
                                source_ref="fixture:early-reverse", source_sha256=h("early-reverse"))

    def test_demo_is_real_restart_safe_flow(self):
        self.desk.close()
        demo_db = str(Path(self.tmp.name) / "demo.sqlite")
        out = str(Path(self.tmp.name) / "demo-out")
        result = run_demo(demo_db, out)
        self.assertEqual(result["deal"]["state"], "COMMISSION_DUE_FOR_OWNER_REVIEW")
        self.assertTrue(Path(out, "channel_partner_snapshot.json").exists())
        self.desk = DealDesk(self.db)


if __name__ == "__main__":
    unittest.main()
