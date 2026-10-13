from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from revenue.offer_outcome_learning.engine import LearningError, compile_historical, loads_strict, render_markdown, verify_package

AT = "2026-09-13T23:40:00Z"


def h(seed: str) -> str:
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


def campaign(i: int, *, offer="audit", proof="proof-a", band="mid", org=None, amount=300000):
    org = org or f"org-{i}"
    return {
        "campaign_id": f"c-{i}", "org_id": org, "offer_id": offer, "proof_id": proof,
        "price_band_id": band, "proposed_minor": amount, "currency": "USD",
        "created_at": "2026-09-13T20:00:00Z", "source_ref": f"campaign-src-{i}", "source_sha256": h(f"campaign-{i}"),
    }


def event(i: int, stage: str, minute: int, *, amount=None, eid=None):
    row = {
        "event_id": eid or f"e-{i}-{stage.lower()}", "campaign_id": f"c-{i}", "stage": stage,
        "occurred_at": f"2026-09-13T20:{minute:02d}:00Z", "source_ref": f"event-src-{i}-{stage.lower()}",
        "source_sha256": h(f"event-{i}-{stage}"),
    }
    if amount is not None:
        row["amount_minor"] = amount
    if stage == "PAYMENT_CONFIRMED":
        row["settlement_ref"] = f"settlement-{i}"
        row["settlement_sha256"] = h(f"settlement-{i}")
    return row


def progression(i: int, *, paid=False, reported=False, accepted=True):
    rows = [event(i, "SENT", 1), event(i, "HUMAN_REPLY", 2), event(i, "QUALIFIED", 3)]
    if accepted:
        rows.append(event(i, "PILOT_ACCEPTED", 4, amount=250000))
    if reported:
        rows.append(event(i, "PAYMENT_REPORTED", 5, amount=250000))
    if paid:
        rows.append(event(i, "PAYMENT_CONFIRMED", 6, amount=250000))
    return rows


def base_input(n=6, paid=(1, 2)):
    campaigns = [campaign(i) for i in range(1, n + 1)]
    events = []
    for i in range(1, n + 1):
        events.extend(progression(i, paid=i in paid, accepted=i <= 4))
    return {"schema": "commons.offer-outcome-learning/input-v1", "currency": "USD", "campaigns": campaigns, "events": events}


class LearningTests(unittest.TestCase):
    def test_observed_signal_requires_diverse_evidence(self):
        package = compile_historical(base_input(), AT)
        c = package["payload"]["cohorts"][0]
        self.assertEqual(c["campaigns"], 6)
        self.assertEqual(c["payment_confirmed_count"], 2)
        self.assertEqual(c["paid_orgs"], 2)
        self.assertEqual(c["dominant_paid_org_share_bps"], 5000)
        self.assertIn(c["evidence_state"], {"OWNER_REVIEW_OBSERVED_SIGNAL", "OBSERVED_SIGNAL_WEAK"})
        self.assertFalse(package["payload"]["authority"]["external_send_authorized"])

    def test_one_whale_is_concentrated(self):
        raw = base_input(n=6, paid=(1, 2, 3))
        for idx in (0, 1, 2):
            raw["campaigns"][idx]["org_id"] = "org-whale"
        c = compile_historical(raw, AT)["payload"]["cohorts"][0]
        self.assertEqual(c["evidence_state"], "OBSERVED_SIGNAL_CONCENTRATED")
        self.assertEqual(c["paid_orgs"], 1)
        self.assertEqual(c["leave_one_org_out_confirmed_count_floor"], 0)

    def test_payment_report_does_not_count_as_cash(self):
        raw = base_input(n=5, paid=())
        raw["events"].append(event(1, "PAYMENT_REPORTED", 5, amount=250000))
        c = compile_historical(raw, AT)["payload"]["cohorts"][0]
        self.assertEqual(c["payment_report_count"], 1)
        self.assertEqual(c["payment_confirmed_count"], 0)
        self.assertEqual(c["confirmed_payment_minor"], 0)

    def test_confirmed_requires_settlement_evidence(self):
        raw = base_input()
        row = next(r for r in raw["events"] if r["stage"] == "PAYMENT_CONFIRMED")
        del row["settlement_ref"]
        with self.assertRaisesRegex(LearningError, "INVALID_ID"):
            compile_historical(raw, AT)

    def test_duplicate_event_exact_replay_collapses(self):
        raw = base_input()
        raw["events"].append(copy.deepcopy(raw["events"][0]))
        p = compile_historical(raw, AT)
        self.assertEqual(p["payload"]["event_count"], len(raw["events"]) - 1)

    def test_duplicate_event_changed_rejected(self):
        raw = base_input()
        dup = copy.deepcopy(raw["events"][0]); dup["occurred_at"] = "2026-09-13T20:09:00Z"
        raw["events"].append(dup)
        with self.assertRaisesRegex(LearningError, "EVENT_ID_CONFLICT"):
            compile_historical(raw, AT)

    def test_source_digest_alias_rejected(self):
        raw = base_input()
        raw["events"][1]["source_sha256"] = raw["events"][0]["source_sha256"]
        with self.assertRaisesRegex(LearningError, "SOURCE_DIGEST_ALIAS"):
            compile_historical(raw, AT)

    def test_event_before_campaign_rejected(self):
        raw = base_input(); raw["events"][0]["occurred_at"] = "2026-09-13T19:59:00Z"
        with self.assertRaisesRegex(LearningError, "EVENT_BEFORE_CAMPAIGN"):
            compile_historical(raw, AT)

    def test_future_event_rejected(self):
        raw = base_input(); raw["events"][0]["occurred_at"] = "2026-09-13T23:41:00Z"
        with self.assertRaisesRegex(LearningError, "EVENT_FROM_FUTURE"):
            compile_historical(raw, AT)

    def test_missing_sent_rejected(self):
        raw = base_input(); raw["events"] = [e for e in raw["events"] if not (e["campaign_id"] == "c-1" and e["stage"] == "SENT")]
        with self.assertRaisesRegex(LearningError, "MISSING_SENT"):
            compile_historical(raw, AT)

    def test_qualified_without_reply_rejected(self):
        raw = base_input(); raw["events"] = [e for e in raw["events"] if not (e["campaign_id"] == "c-1" and e["stage"] == "HUMAN_REPLY")]
        with self.assertRaisesRegex(LearningError, "STAGE_PREDECESSOR_MISSING"):
            compile_historical(raw, AT)

    def test_confirmed_more_than_accepted_rejected(self):
        raw = base_input(); row = next(e for e in raw["events"] if e["campaign_id"] == "c-1" and e["stage"] == "PAYMENT_CONFIRMED"); row["amount_minor"] = 300000
        with self.assertRaisesRegex(LearningError, "CONFIRMED_PAYMENT_EXCEEDS_ACCEPTED"):
            compile_historical(raw, AT)

    def test_report_confirm_mismatch_rejected(self):
        raw = base_input(); raw["events"].append(event(1, "PAYMENT_REPORTED", 5, amount=200000))
        with self.assertRaisesRegex(LearningError, "PAYMENT_REPORT_CONFIRM_MISMATCH"):
            compile_historical(raw, AT)

    def test_terminal_blocks_later_event(self):
        raw = base_input(); raw["events"].append(event(1, "DNR", 5, eid="dnr-1"))
        with self.assertRaisesRegex(LearningError, "EVENT_AFTER_TERMINAL"):
            compile_historical(raw, AT)

    def test_order_independent_package(self):
        raw = base_input(); a = compile_historical(raw, AT)
        raw2 = copy.deepcopy(raw); raw2["campaigns"].reverse(); raw2["events"].reverse()
        b = compile_historical(raw2, AT)
        self.assertEqual(a, b)

    def test_package_tamper_rejected(self):
        raw = base_input(); p = compile_historical(raw, AT); p["payload"]["campaign_count"] = 999
        with self.assertRaisesRegex(LearningError, "PACKAGE_RECEIPT_MISMATCH"):
            verify_package(raw, p)

    def test_semantic_reseal_tamper_rejected(self):
        from revenue.offer_outcome_learning.engine import sha256_json
        raw = base_input(); p = compile_historical(raw, AT); p["payload"]["campaign_count"] = 999; p["receipt_sha256"] = sha256_json(p["payload"])
        with self.assertRaisesRegex(LearningError, "PACKAGE_SEMANTIC_MISMATCH"):
            verify_package(raw, p)

    def test_input_transplant_rejected(self):
        raw = base_input(); p = compile_historical(raw, AT); raw2 = copy.deepcopy(raw); raw2["campaigns"][0]["proof_id"] = "proof-b"
        with self.assertRaisesRegex(LearningError, "PACKAGE_INPUT_MISMATCH"):
            verify_package(raw2, p)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(LearningError, "DUPLICATE_JSON_KEY"):
            loads_strict('{"schema":"a","schema":"b"}')

    def test_bool_not_integer(self):
        raw = base_input(); raw["campaigns"][0]["proposed_minor"] = True
        with self.assertRaisesRegex(LearningError, "INVALID_INTEGER"):
            compile_historical(raw, AT)

    def test_unsafe_integer_rejected(self):
        raw = base_input(); raw["campaigns"][0]["proposed_minor"] = 9007199254740992
        with self.assertRaisesRegex(LearningError, "INVALID_INTEGER"):
            compile_historical(raw, AT)

    def test_markdown_contains_no_contact_or_send_authority(self):
        p = compile_historical(base_input(), AT); md = render_markdown(p)
        self.assertIn("does not authorize outreach", md)
        self.assertNotIn("@", md)
        self.assertIn("Receipt:", md)

    def test_current_package_staleness_rejected(self):
        raw = base_input(); p = compile_historical(raw, AT)
        p["payload"]["mode"] = "CURRENT"
        from revenue.offer_outcome_learning.engine import sha256_json
        p["receipt_sha256"] = sha256_json(p["payload"])
        with self.assertRaisesRegex(LearningError, "CURRENT_PACKAGE_STALE"):
            verify_package(raw, p, now="2026-09-14T00:10:01Z")

    def test_multiple_cohorts_deterministically_rank(self):
        raw = base_input(n=6, paid=(1,2))
        for i in range(7, 12):
            raw["campaigns"].append(campaign(i, offer="other", proof="proof-b", band="high"))
            raw["events"].extend(progression(i, paid=False, accepted=False))
        p = compile_historical(raw, AT)
        self.assertEqual([c["offer_id"] for c in p["payload"]["cohorts"]], ["audit", "other"])
        self.assertEqual(len(p["payload"]["strategy_queue"]), 2)


if __name__ == "__main__":
    unittest.main()
