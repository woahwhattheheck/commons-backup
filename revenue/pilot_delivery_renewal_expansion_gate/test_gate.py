from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from revenue.pilot_delivery_renewal_expansion_gate import engine

NOW = "2026-09-17T18:55:00Z"
FIXTURE = Path(__file__).with_name("demo") / "synthetic_ready.json"


def packet():
    return engine.load_json(FIXTURE.read_bytes())


def _text(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_packet():
    """Return the synthetic contract shifted around real process UTC for current-API tests."""
    p = packet()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    baseline = now - timedelta(days=45)
    change = now - timedelta(days=20)
    p["baseline"]["accepted_at"] = _text(baseline)
    p["baseline"]["source"]["observed_at"] = _text(baseline)
    p["change_orders"][0]["decided_at"] = _text(change)
    p["change_orders"][0]["source"]["observed_at"] = _text(change)
    for offset, row in zip((10, 8), p["milestones"]):
        delivered = now - timedelta(days=offset)
        accepted = delivered + timedelta(days=1)
        row["delivered_at"] = _text(delivered)
        row["accepted_at"] = _text(accepted)
        row["source"]["observed_at"] = _text(accepted)
    payment = now - timedelta(days=2)
    p["payment"]["observed_at"] = _text(payment)
    p["payment"]["source"]["observed_at"] = _text(payment)
    recent = now - timedelta(days=1)
    for row in p["support_findings"]:
        row["observed_at"] = _text(recent)
        row["source"]["observed_at"] = _text(recent)
    for row in p["security_data_gaps"]:
        row["source"]["observed_at"] = _text(recent)
    for row in p["expansion_hypotheses"]:
        row["source"]["observed_at"] = _text(recent)
    p["renewal_window"]["opens_at"] = _text(now - timedelta(days=1))
    p["renewal_window"]["closes_at"] = _text(now + timedelta(days=30))
    p["renewal_window"]["source"]["observed_at"] = _text(recent)
    p["route_control"]["observed_at"] = _text(now)
    p["route_control"]["source"]["observed_at"] = _text(now)
    return p


class GateTests(unittest.TestCase):
    def test_ready_owner_review_without_buyer_signal(self):
        out = engine._compile(packet(), NOW)
        self.assertEqual(out["state"], engine.READY)
        self.assertFalse(out["truth"]["buyer_signal_required_for_this_state"])
        self.assertEqual(out["truth"]["expansion_hypotheses_remain"], "PROPOSED_NOT_ACCEPTED")
        self.assertTrue(all(value is False for value in out["authority"].values()))
        self.assertEqual(out["effective_total_cents"], 15000)

    def test_baseline_must_be_accepted(self):
        p = packet(); p["baseline"]["status"] = "PROPOSED_NOT_ACCEPTED"
        self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_ACCEPTANCE)

    def test_milestone_must_be_buyer_human_accepted(self):
        for state in ("PENDING", "REJECTED", "SYSTEM_ONLY"):
            with self.subTest(state=state):
                p = packet(); p["milestones"][0]["status"] = state; p["milestones"][0]["accepted_at"] = None
                self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_ACCEPTANCE)

    def test_milestone_generation_must_match_commercial_lineage(self):
        p = packet(); p["milestones"][0]["commercial_generation"] = 1
        out = engine._compile(p, NOW)
        self.assertEqual(out["state"], engine.HOLD_ACCEPTANCE)
        self.assertIn("MILESTONE_GENERATION_MISMATCH:m1", out["reasons"])

    def test_pending_change_order_holds_evidence(self):
        p = packet(); p["change_orders"][0]["status"] = "PENDING"
        out = engine._compile(p, NOW)
        self.assertEqual(out["state"], engine.HOLD_EVIDENCE)

    def test_rejected_change_order_does_not_change_economics(self):
        p = packet()
        p["change_orders"][0]["status"] = "REJECTED"
        for m in p["milestones"]:
            m["commercial_generation"] = 1
        p["payment"]["commercial_generation"] = 1
        p["payment"]["settled_cents"] = 10000
        out = engine._compile(p, NOW)
        self.assertEqual(out["state"], engine.READY)
        self.assertEqual(out["effective_total_cents"], 10000)
        self.assertEqual(out["commercial_generation"], 1)

    def test_change_order_generation_gap_rejected(self):
        p = packet(); p["change_orders"][0]["generation"] = 3
        with self.assertRaisesRegex(engine.GateError, "generation gap"):
            engine._compile(p, NOW)

    def test_duplicate_change_order_generation_rejected(self):
        p = packet()
        extra = copy.deepcopy(p["change_orders"][0]); extra["change_order_id"] = "co-002"
        p["change_orders"].append(extra)
        with self.assertRaisesRegex(engine.GateError, "duplicate id/generation"):
            engine._compile(p, NOW)

    def test_payment_requires_settlement_evidence_not_invoice_or_link(self):
        for evidence in ("INVOICE", "PAYMENT_LINK", "ADVERTISED_AMOUNT"):
            with self.subTest(evidence=evidence):
                p = packet(); p["payment"]["evidence_class"] = evidence
                self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_PAYMENT)

    def test_payment_state_must_be_final_settled(self):
        for state in ("PARTIAL", "PENDING", "REFUNDED", "DISPUTED"):
            with self.subTest(state=state):
                p = packet(); p["payment"]["state"] = state
                self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_PAYMENT)

    def test_payment_refund_dispute_and_amount_hold(self):
        variants = [
            ("refunded_cents", 1),
            ("disputed", True),
            ("settled_cents", 14999),
            ("commercial_generation", 1),
        ]
        for key, value in variants:
            with self.subTest(key=key):
                p = packet(); p["payment"][key] = value
                self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_PAYMENT)

    def test_window_not_open_and_closed(self):
        p = packet(); p["renewal_window"]["opens_at"] = "2026-09-18T00:00:00Z"
        self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_WINDOW)
        p = packet(); p["renewal_window"]["closes_at"] = "2026-09-17T18:54:59Z"
        self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_WINDOW)

    def test_open_high_or_blocking_support_finding_holds(self):
        for severity in ("HIGH", "BLOCKING"):
            with self.subTest(severity=severity):
                p = packet(); p["support_findings"][0]["severity"] = severity
                self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_EVIDENCE)

    def test_open_low_support_finding_is_review_evidence_not_blocker(self):
        self.assertEqual(engine._compile(packet(), NOW)["state"], engine.READY)

    def test_open_blocking_security_gap_holds(self):
        p = packet(); p["security_data_gaps"][0]["status"] = "OPEN"
        out = engine._compile(p, NOW)
        self.assertEqual(out["state"], engine.HOLD_EVIDENCE)
        self.assertIn("OPEN_BLOCKING_SECURITY_DATA_GAP:gap-1", out["reasons"])

    def test_nonblocking_open_security_gap_can_be_reviewed(self):
        p = packet(); p["security_data_gaps"][0]["status"] = "OPEN"; p["security_data_gaps"][0]["blocking"] = False
        self.assertEqual(engine._compile(p, NOW)["state"], engine.READY)

    def test_hypothesis_must_remain_proposed_not_accepted(self):
        p = packet(); p["expansion_hypotheses"][0]["commercial_state"] = "ACCEPTED"
        self.assertEqual(engine._compile(p, NOW)["state"], engine.HOLD_EVIDENCE)

    def test_hypothesis_cannot_claim_buyer_interest_roi_or_approval(self):
        keys = (
            "buyer_interest_claimed", "roi_claimed", "savings_claimed",
            "usage_claimed", "urgency_claimed", "expansion_approved_claimed"
        )
        for key in keys:
            with self.subTest(key=key):
                p = packet(); p["expansion_hypotheses"][0][key] = True
                out = engine._compile(p, NOW)
                self.assertEqual(out["state"], engine.HOLD_EVIDENCE)
                self.assertIn("HYPOTHESIS_UNSUPPORTED_CLAIM:hyp-1", out["reasons"])

    def test_dnr_is_terminal(self):
        p = packet()
        p["route_control"]["state"] = "DNR"
        p["baseline"]["status"] = "PROPOSED_NOT_ACCEPTED"
        self.assertEqual(engine._compile(p, NOW)["state"], engine.DNR)

    def test_route_unassessed_does_not_mint_send_authority(self):
        out = engine._compile(packet(), NOW)
        self.assertEqual(out["route"]["state"], "UNASSESSED")
        self.assertFalse(out["authority"]["external_send_authorized"])
        self.assertFalse(out["authority"]["muse_election_authorized"])

    def test_future_source_fails_closed(self):
        p = packet(); p["payment"]["source"]["observed_at"] = "2026-09-18T00:00:00Z"
        with self.assertRaisesRegex(engine.GateError, "future timestamp"):
            engine._compile(p, NOW)

    def test_stale_payment_and_route_fail_closed(self):
        p = packet(); p["payment"]["observed_at"] = "2026-01-01T00:00:00Z"; p["payment"]["source"]["observed_at"] = "2026-01-01T00:00:00Z"
        with self.assertRaisesRegex(engine.GateError, "stale evidence"):
            engine._compile(p, NOW)
        p = packet(); p["route_control"]["observed_at"] = "2026-09-01T00:00:00Z"; p["route_control"]["source"]["observed_at"] = "2026-09-01T00:00:00Z"
        with self.assertRaisesRegex(engine.GateError, "stale evidence"):
            engine._compile(p, NOW)

    def test_bool_as_int_rejected(self):
        p = packet(); p["baseline"]["generation"] = True
        with self.assertRaisesRegex(engine.GateError, "integer required"):
            engine._compile(p, NOW)

    def test_unknown_fields_rejected(self):
        p = packet(); p["baseline"]["invented"] = "x"
        with self.assertRaisesRegex(engine.GateError, "keys mismatch"):
            engine._compile(p, NOW)

    def test_duplicate_json_keys_rejected(self):
        raw = b'{"schema":"x","schema":"y"}'
        with self.assertRaisesRegex(engine.GateError, "duplicate JSON key"):
            engine.load_json(raw)

    def test_float_nan_and_infinity_rejected(self):
        for raw in (b'{"x":1.5}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(raw=raw):
                with self.assertRaises(engine.GateError):
                    engine.load_json(raw)

    def test_source_requires_https_and_rejects_userinfo(self):
        for uri in ("http://example.invalid/x", "https://user:pass@example.invalid/x"):
            with self.subTest(uri=uri):
                p = packet(); p["baseline"]["source"]["source_uri"] = uri
                with self.assertRaisesRegex(engine.GateError, "safe HTTPS"):
                    engine._compile(p, NOW)

    def test_order_invariance_for_nonsemantic_collections(self):
        p = packet()
        p["support_findings"].reverse()
        out1 = engine._compile(packet(), NOW)
        out2 = engine._compile(p, NOW)
        self.assertEqual(out1["input_digest"], out2["input_digest"])
        self.assertEqual(out1["receipt_digest"], out2["receipt_digest"])

    def test_receipt_digest_tamper_rejected(self):
        p = packet()
        receipt = engine._compile(p, NOW)
        receipt["state"] = engine.HOLD_EVIDENCE
        with self.assertRaisesRegex(engine.GateError, "digest mismatch"):
            engine.verify_receipt(p, receipt)

    def test_resealed_semantic_receipt_tamper_rejected(self):
        p = packet()
        forged = copy.deepcopy(engine._compile(p, NOW))
        forged["authority"]["external_send_authorized"] = True
        unsigned = dict(forged)
        unsigned.pop("receipt_digest")
        forged["receipt_digest"] = engine.digest(unsigned)
        with self.assertRaisesRegex(engine.GateError, "semantic mismatch"):
            engine.verify_receipt(p, forged)

    def test_current_clock_ignores_ordinary_module_global_rebinding(self):
        p = current_packet()
        receipt = engine.compile_current(p)
        fake = datetime_like("2099-01-01T00:00:00Z")
        sentinel = object()
        names = ("datetime", "timezone", "_stdlib_datetime", "_stdlib_timezone")
        previous = {name: getattr(engine, name, sentinel) for name in names}
        try:
            for name in names:
                setattr(engine, name, fake)
            current = engine.compile_current(p)
            checked = engine.verify_receipt(p, receipt)
        finally:
            for name, value in previous.items():
                if value is sentinel:
                    delattr(engine, name)
                else:
                    setattr(engine, name, value)
        self.assertNotEqual(current["evaluated_at"], "2099-01-01T00:00:00Z")
        self.assertTrue(checked["integrity_valid"])
        self.assertTrue(checked["still_current"])


def datetime_like(value: str):
    fixed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    class FixedDateTime:
        utc = timezone.utc

        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)

        @staticmethod
        def strptime(*args, **kwargs):
            return datetime.strptime(*args, **kwargs)

    return FixedDateTime


if __name__ == "__main__":
    unittest.main()
