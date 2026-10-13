from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

try:
    from .ledger import (
        FunnelError,
        HOLD,
        INPUT_SCHEMA,
        READY,
        STAGES,
        canonical_json,
        compile_funnel,
        strict_loads,
        verify_compilation,
    )
except ImportError:
    from ledger import (
        FunnelError,
        HOLD,
        INPUT_SCHEMA,
        READY,
        STAGES,
        canonical_json,
        compile_funnel,
        strict_loads,
        verify_compilation,
    )

AS_OF = "2026-09-13T10:10:00Z"
COMMIT = "a" * 40


def src(name: str, digest_char: str = "b") -> dict:
    return {
        "repository": "woahwhattheheck/commons",
        "commit": COMMIT,
        "path": f"evidence/{name}.json",
        "sha256": digest_char * 64,
    }


def event(stage: str, idx: int, *, at: str | None = None, proves=None, evidence=None, money=None, noncash=None, reversal_of=None) -> dict:
    out = {
        "id": f"evt-{stage.lower()}-{idx}",
        "stage": stage,
        "observed_at": at or f"2026-09-{min(12, 1 + idx):02d}T10:00:00Z",
        "evidence": evidence or src(f"event-{stage.lower()}-{idx}", "bcdef0123456789a"[idx % 16]),
    }
    if proves is not None:
        out["proves"] = proves
    if money is not None:
        out["money"] = money
    if noncash is not None:
        out["noncash"] = noncash
    if reversal_of is not None:
        out["reversal_of"] = reversal_of
    return out


def opportunity(opp_id="opp-1", family="SERVICE", through="TRAFFIC") -> dict:
    depth = STAGES.index(through) + 1 if through else 0
    events = []
    for i, stage in enumerate(STAGES[:depth]):
        money = {"currency": "USD", "minor_units": 10000} if stage == "CASH" else None
        events.append(event(stage, i, money=money, evidence=src(f"{opp_id}-{stage.lower()}", "bcdef0"[i])))
    return {
        "id": opp_id,
        "family": family,
        "offer": {"id": f"offer-{opp_id}", "version": "v1", "source": src(f"offer-{opp_id}", "f")},
        "events": events,
    }


def payload(*opps: dict) -> dict:
    return {"schema": INPUT_SCHEMA, "opportunities": list(opps)}


class FunnelTests(unittest.TestCase):
    def compile(self, *opps):
        return compile_funnel(payload(*opps), as_of=AS_OF)

    def test_full_cash_ready(self):
        out = self.compile(opportunity(through="CASH"))
        self.assertEqual(out["packet"]["state"], READY)
        self.assertEqual(out["packet"]["metrics"]["net_cash_by_currency"], {"USD": 10000})
        self.assertEqual(out["packet"]["opportunities"][0]["strongest_evidenced_stage"], "CASH")

    def test_delivery_does_not_become_cash(self):
        out = self.compile(opportunity(through="DELIVERY"))
        self.assertEqual(out["packet"]["metrics"]["net_cash_by_currency"], {})
        self.assertEqual(out["packet"]["opportunities"][0]["next_evidence_needed"], "TRANSFER")

    def test_noncash_award_stays_separate(self):
        opp = opportunity(through="ACCEPTANCE")
        opp["events"].append(event("NONCASH_AWARD", 9, noncash={"asset": "RTC", "quantity": 25}, evidence=src("award", "9")))
        out = self.compile(opp)
        metrics = out["packet"]["metrics"]
        self.assertEqual(metrics["net_cash_by_currency"], {})
        self.assertEqual(metrics["noncash_awards"], {"RTC": 25})

    def test_cash_reversal_reduces_net(self):
        opp = opportunity(through="CASH")
        cash_id = opp["events"][-1]["id"]
        opp["events"].append(event("CASH_REVERSAL", 10, at="2026-09-12T11:00:00Z", money={"currency": "USD", "minor_units": 2500}, reversal_of=cash_id, evidence=src("refund", "8")))
        out = self.compile(opp)
        self.assertEqual(out["packet"]["metrics"]["gross_cash_by_currency"], {"USD": 10000})
        self.assertEqual(out["packet"]["metrics"]["cash_reversals_by_currency"], {"USD": 2500})
        self.assertEqual(out["packet"]["metrics"]["net_cash_by_currency"], {"USD": 7500})

    def test_reversal_exceeds_cash_holds(self):
        opp = opportunity(through="CASH")
        cash_id = opp["events"][-1]["id"]
        opp["events"].append(event("CASH_REVERSAL", 10, at="2026-09-12T11:00:00Z", money={"currency": "USD", "minor_units": 10001}, reversal_of=cash_id, evidence=src("refund2", "8")))
        out = self.compile(opp)
        self.assertEqual(out["packet"]["state"], HOLD)
        self.assertIn("REVERSAL_EXCEEDS_CASH", out["packet"]["opportunities"][0]["hold_reasons"])
        self.assertEqual(out["packet"]["metrics"]["net_cash_by_currency"], {})

    def test_reversal_requires_prior_cash_identity(self):
        opp = opportunity(through="ACCEPTANCE")
        opp["events"].append(event("CASH_REVERSAL", 10, money={"currency": "USD", "minor_units": 1}, reversal_of="missing-cash", evidence=src("orphan-refund", "7")))
        out = self.compile(opp)
        self.assertIn("REVERSAL_TARGET_NOT_PRIOR_CASH", out["packet"]["opportunities"][0]["hold_reasons"])

    def test_reversal_currency_mismatch_holds(self):
        opp = opportunity(through="CASH")
        cash_id = opp["events"][-1]["id"]
        opp["events"].append(event("CASH_REVERSAL", 10, at="2026-09-12T11:00:00Z", money={"currency": "EUR", "minor_units": 1}, reversal_of=cash_id, evidence=src("refund-eur", "7")))
        out = self.compile(opp)
        self.assertIn("REVERSAL_CURRENCY_MISMATCH", out["packet"]["opportunities"][0]["hold_reasons"])

    def test_future_evidence_holds(self):
        opp = opportunity(through="TRAFFIC")
        opp["events"][0]["observed_at"] = "2026-09-14T10:00:00Z"
        out = self.compile(opp)
        self.assertIn("EVIDENCE_FROM_FUTURE", out["packet"]["opportunities"][0]["hold_reasons"])

    def test_stale_evidence_holds(self):
        opp = opportunity(through="TRAFFIC")
        opp["events"][0]["observed_at"] = "2024-09-01T10:00:00Z"
        out = self.compile(opp)
        self.assertIn("EVIDENCE_STALE", out["packet"]["opportunities"][0]["hold_reasons"])

    def test_stage_gap_holds(self):
        opp = opportunity(through="TRAFFIC")
        opp["events"] = [event("ACCEPTANCE", 2, evidence=src("accept-only", "5"))]
        out = self.compile(opp)
        self.assertIn("STAGE_GAP_ACCEPTANCE", out["packet"]["opportunities"][0]["hold_reasons"])

    def test_immutable_stronger_evidence_can_prove_prior_stages(self):
        opp = opportunity(through="TRAFFIC")
        opp["events"] = [event("ACCEPTANCE", 2, proves=["TRAFFIC", "REPLY"], evidence=src("signed-acceptance", "5"))]
        out = self.compile(opp)
        self.assertEqual(out["packet"]["state"], READY)
        self.assertEqual(out["packet"]["metrics"]["stage_counts"]["ACCEPTANCE"], 1)

    def test_illegal_proves_future_stage_rejected(self):
        opp = opportunity(through="TRAFFIC")
        opp["events"] = [event("REPLY", 1, proves=["ACCEPTANCE"], evidence=src("bad-proves", "5"))]
        with self.assertRaises(FunnelError):
            self.compile(opp)

    def test_stage_time_order_holds(self):
        opp = opportunity(through="REPLY")
        opp["events"][0]["observed_at"] = "2026-09-10T10:00:00Z"
        opp["events"][1]["observed_at"] = "2026-09-09T10:00:00Z"
        out = self.compile(opp)
        self.assertIn("STAGE_TIME_ORDER_INVALID", out["packet"]["opportunities"][0]["hold_reasons"])

    def test_identical_event_replay_is_idempotent(self):
        opp = opportunity(through="REPLY")
        opp["events"].append(copy.deepcopy(opp["events"][0]))
        out = self.compile(opp)
        self.assertEqual(out["packet"]["state"], READY)
        self.assertEqual(len(out["packet"]["opportunities"][0]["events"]), 2)

    def test_same_event_id_different_payload_holds(self):
        opp = opportunity(through="REPLY")
        conflict = copy.deepcopy(opp["events"][0])
        conflict["evidence"] = src("conflict", "6")
        opp["events"].append(conflict)
        out = self.compile(opp)
        self.assertIn("EVENT_ID_CONFLICT", out["packet"]["opportunities"][0]["hold_reasons"])

    def test_cross_opportunity_evidence_reuse_holds_both(self):
        a = opportunity("opp-a", through="TRAFFIC")
        b = opportunity("opp-b", through="TRAFFIC")
        b["events"][0]["evidence"] = copy.deepcopy(a["events"][0]["evidence"])
        out = self.compile(a, b)
        self.assertEqual(out["packet"]["metrics"]["held_opportunity_count"], 2)
        for opp in out["packet"]["opportunities"]:
            self.assertIn("EVIDENCE_REUSED_ACROSS_OPPORTUNITIES", opp["hold_reasons"])

    def test_duplicate_opportunity_id_rejected(self):
        with self.assertRaises(FunnelError):
            self.compile(opportunity("dup"), opportunity("dup"))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(FunnelError):
            strict_loads('{"schema":"a","schema":"b"}')

    def test_float_rejected(self):
        p = payload(opportunity())
        p["opportunities"][0]["extra"] = 1.5
        with self.assertRaises(FunnelError):
            compile_funnel(p, as_of=AS_OF)

    def test_secret_shaped_value_rejected(self):
        p = payload(opportunity())
        p["opportunities"][0]["offer"]["id"] = "Bearer abcdefghijklmnop"
        with self.assertRaises(FunnelError):
            compile_funnel(p, as_of=AS_OF)

    def test_email_shaped_value_rejected(self):
        p = payload(opportunity())
        p["opportunities"][0]["offer"]["id"] = "person@example.com"
        with self.assertRaises(FunnelError):
            compile_funnel(p, as_of=AS_OF)

    def test_mutable_or_short_commit_rejected(self):
        p = payload(opportunity())
        p["opportunities"][0]["events"][0]["evidence"]["commit"] = "main"
        with self.assertRaises(FunnelError):
            compile_funnel(p, as_of=AS_OF)

    def test_path_traversal_rejected(self):
        p = payload(opportunity())
        p["opportunities"][0]["events"][0]["evidence"]["path"] = "../secret"
        with self.assertRaises(FunnelError):
            compile_funnel(p, as_of=AS_OF)

    def test_boolean_money_rejected(self):
        opp = opportunity(through="CASH")
        opp["events"][-1]["money"]["minor_units"] = True
        with self.assertRaises(FunnelError):
            self.compile(opp)

    def test_money_on_acceptance_rejected(self):
        opp = opportunity(through="ACCEPTANCE")
        opp["events"][-1]["money"] = {"currency": "USD", "minor_units": 1}
        with self.assertRaises(FunnelError):
            self.compile(opp)

    def test_multiple_currencies_never_fx_convert(self):
        a = opportunity("usd", through="CASH")
        b = opportunity("eur", through="CASH")
        b["events"][-1]["money"] = {"currency": "EUR", "minor_units": 7000}
        out = self.compile(a, b)
        self.assertEqual(out["packet"]["metrics"]["net_cash_by_currency"], {"EUR": 7000, "USD": 10000})

    def test_authority_ceiling_all_false(self):
        out = self.compile(opportunity(through="CASH"))
        self.assertTrue(out["packet"]["authority"])
        self.assertTrue(all(value is False for value in out["packet"]["authority"].values()))

    def test_verifier_detects_packet_tamper(self):
        p = payload(opportunity(through="CASH"))
        out = compile_funnel(p, as_of=AS_OF)
        self.assertTrue(verify_compilation(p, as_of=AS_OF, packet=out["packet"], receipt=out["receipt"]))
        bad = copy.deepcopy(out["packet"])
        bad["metrics"]["stage_counts"]["CASH"] = 999
        self.assertFalse(verify_compilation(p, as_of=AS_OF, packet=bad, receipt=out["receipt"]))

    def test_order_independent_bytes(self):
        a = opportunity("a", through="CASH")
        b = opportunity("b", through="DELIVERY")
        p1 = payload(a, b)
        p2 = payload(copy.deepcopy(b), copy.deepcopy(a))
        p2["opportunities"][0]["events"].reverse()
        p2["opportunities"][1]["events"].reverse()
        o1 = compile_funnel(p1, as_of=AS_OF)
        o2 = compile_funnel(p2, as_of=AS_OF)
        self.assertEqual(canonical_json(o1["packet"]), canonical_json(o2["packet"]))
        self.assertEqual(canonical_json(o1["receipt"]), canonical_json(o2["receipt"]))
        self.assertEqual(o1["csv"], o2["csv"])
        self.assertEqual(o1["markdown"], o2["markdown"])

    def test_all_family_metrics(self):
        opps = [opportunity(f"opp-{family.lower()}", family, through="REPLY") for family in ("PRODUCT", "SERVICE", "EXPERTISE", "DATA")]
        out = self.compile(*opps)
        self.assertEqual(out["packet"]["metrics"]["family_eligible_counts"], {"PRODUCT": 1, "SERVICE": 1, "EXPERTISE": 1, "DATA": 1})

    def test_empty_events_is_valid_and_needs_traffic(self):
        opp = opportunity(through="TRAFFIC")
        opp["events"] = []
        out = self.compile(opp)
        row = out["packet"]["opportunities"][0]
        self.assertEqual(row["state"], READY)
        self.assertIsNone(row["strongest_evidenced_stage"])
        self.assertEqual(row["next_evidence_needed"], "TRAFFIC")

    def test_strict_timestamp_requires_z_and_seconds(self):
        opp = opportunity(through="TRAFFIC")
        opp["events"][0]["observed_at"] = "2026-09-01T10:00:00+00:00"
        with self.assertRaises(FunnelError):
            self.compile(opp)

    def test_unknown_keys_fail_closed(self):
        p = payload(opportunity())
        p["opportunities"][0]["unknown"] = "x"
        with self.assertRaises(FunnelError):
            compile_funnel(p, as_of=AS_OF)

    def test_acceptance_corpus_128_opportunities(self):
        opps = []
        families = ("PRODUCT", "SERVICE", "EXPERTISE", "DATA")
        for i in range(128):
            stage = STAGES[i % len(STAGES)]
            opp = opportunity(f"corpus-{i:03d}", families[i % 4], through=stage)
            if stage == "CASH":
                opp["events"][-1]["money"]["minor_units"] = 100 + i
            opps.append(opp)
        out = self.compile(*opps)
        self.assertEqual(out["packet"]["metrics"]["opportunity_count"], 128)
        self.assertEqual(out["packet"]["metrics"]["held_opportunity_count"], 0)
        self.assertEqual(out["packet"]["state"], READY)
        cash_count = sum(1 for i in range(128) if STAGES[i % 6] == "CASH")
        self.assertEqual(out["packet"]["metrics"]["stage_counts"]["CASH"], cash_count)


if __name__ == "__main__":
    unittest.main()
