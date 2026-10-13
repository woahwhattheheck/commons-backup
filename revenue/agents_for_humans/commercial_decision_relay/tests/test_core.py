from copy import deepcopy
import json
from pathlib import Path
import unittest

from decision_relay.core import AuthorityBoundaryError, DecisionRelayError, RelayEngine, canonical_digest, normalize_batch, receipt_self_digest_matches, reconcile, verify_receipt

FIXTURE = Path(__file__).parents[1] / "fixtures" / "demo-batch.json"

def batch():
    return json.loads(FIXTURE.read_text())


def response_event(**overrides):
    event = {
        "event_id": "r1", "kind": "response", "series_id": "s", "offer_version": 1,
        "counterparty_id": "cp", "thread_id": "thread", "currency": "USD", "amount_minor": 100,
        "terms_digest": "a" * 64, "response_class": "exact_acceptance",
        "received_at": "2026-09-13T10:00:00Z", "reviewed_at": "2026-09-13T10:01:00Z",
        "source_digest": "b" * 64, "reviewer_attestation_digest": "c" * 64,
    }
    event.update(overrides)
    return event


def offer_event(**overrides):
    event = {
        "event_id": "o1", "kind": "offer", "series_id": "s", "offer_version": 1,
        "counterparty_id": "cp", "thread_id": "thread", "currency": "USD", "amount_minor": 100,
        "terms_digest": "a" * 64, "issued_at": "2026-09-13T09:00:00Z", "expires_at": "2026-09-20T09:00:00Z",
    }
    event.update(overrides)
    return event


def simple_batch(events, snapshot="2026-09-13T12:00:00Z"):
    return {"schema_version": 1, "snapshot_at": snapshot, "events": events}


class RelayTests(unittest.TestCase):
    def test_demo_surfaces_two_decisions_and_suppresses_routine(self):
        receipt = reconcile(batch())
        self.assertEqual(receipt["summary"], {"series_count": 4, "decision_count": 2, "routine_count": 2, "quarantine_count": 0})
        self.assertEqual([x["series_id"] for x in receipt["decision_queue"]], ["alpha-renewal", "beta-pilot"])

    def test_exact_acceptance_is_only_closing_ready(self):
        receipt = reconcile(simple_batch([offer_event(), response_event()]))
        self.assertEqual(receipt["series"][0]["status"], "HUMAN_CLOSING_READY")

    def test_exact_acceptance_amount_mismatch_is_conflict(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(amount_minor=99)]))
        self.assertEqual(receipt["series"][0]["status"], "EVIDENCE_CONFLICT")

    def test_exact_acceptance_terms_mismatch_is_conflict(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(terms_digest="d" * 64)]))
        self.assertEqual(receipt["series"][0]["status"], "EVIDENCE_CONFLICT")

    def test_thread_mismatch_is_conflict(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(thread_id="other")]))
        self.assertEqual(receipt["series"][0]["status"], "EVIDENCE_CONFLICT")

    def test_counterparty_mismatch_is_conflict(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(counterparty_id="other")]))
        self.assertEqual(receipt["series"][0]["status"], "EVIDENCE_CONFLICT")

    def test_counteroffer_surfaces_human(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(response_class="counteroffer", amount_minor=90)]))
        self.assertEqual(receipt["series"][0]["status"], "COUNTEROFFER_REVIEW")
        self.assertEqual(len(receipt["decision_queue"]), 1)

    def test_clarification_surfaces_human(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(response_class="clarification")]))
        self.assertEqual(receipt["series"][0]["status"], "CLARIFICATION_REQUIRED")

    def test_decline_is_routine(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(response_class="decline")]))
        self.assertEqual(receipt["series"][0]["status"], "DECLINED")
        self.assertEqual(receipt["decision_queue"], [])

    def test_no_response_before_expiry_is_routine(self):
        receipt = reconcile(simple_batch([offer_event()]))
        self.assertEqual(receipt["series"][0]["status"], "AWAITING_RESPONSE")

    def test_no_response_after_expiry_requires_reissue(self):
        receipt = reconcile(simple_batch([offer_event()]), evaluated_at="2026-09-21T00:00:00Z")
        self.assertEqual(receipt["series"][0]["status"], "REISSUE_REQUIRED")

    def test_late_response_is_not_acceptance(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(received_at="2026-09-21T10:00:00Z", reviewed_at="2026-09-21T10:01:00Z")]), evaluated_at="2026-09-21T11:00:00Z")
        self.assertEqual(receipt["series"][0]["status"], "LATE_RESPONSE_REVIEW")

    def test_response_predating_offer_is_conflict(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(received_at="2026-09-13T08:00:00Z", reviewed_at="2026-09-13T08:01:00Z")]))
        self.assertEqual(receipt["series"][0]["status"], "EVIDENCE_CONFLICT")

    def test_future_review_is_quarantined(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(reviewed_at="2026-09-14T10:01:00Z", received_at="2026-09-14T10:00:00Z")]))
        self.assertEqual(receipt["series"][0]["status"], "AWAITING_RESPONSE")
        self.assertEqual(receipt["quarantined"][0]["reason"], "future_evidence")

    def test_orphan_response_is_quarantined(self):
        receipt = reconcile(simple_batch([offer_event(), response_event(series_id="other")]))
        self.assertEqual(receipt["summary"]["quarantine_count"], 1)
        self.assertEqual(receipt["quarantined"][0]["reason"], "response_without_matching_offer")

    def test_latest_offer_version_controls(self):
        events = [offer_event(), offer_event(event_id="o2", offer_version=2, amount_minor=200)]
        receipt = reconcile(simple_batch(events))
        self.assertEqual(receipt["series"][0]["offer_version"], 2)
        self.assertEqual(receipt["series"][0]["status"], "AWAITING_RESPONSE")

    def test_duplicate_equivalent_reviewed_response_uses_latest_evidence(self):
        events = [offer_event(), response_event(), response_event(event_id="r2", reviewed_at="2026-09-13T10:03:00Z", received_at="2026-09-13T10:02:00Z")]
        receipt = reconcile(simple_batch(events))
        self.assertEqual(receipt["series"][0]["status"], "HUMAN_CLOSING_READY")
        self.assertEqual(receipt["series"][0]["response_event_id"], "r2")

    def test_conflicting_reviewed_responses_never_reduce_to_latest_wins(self):
        events = [offer_event(), response_event(), response_event(event_id="r2", response_class="decline", reviewed_at="2026-09-13T10:03:00Z", received_at="2026-09-13T10:02:00Z")]
        receipt = reconcile(simple_batch(events))
        self.assertEqual(receipt["series"][0]["status"], "EVIDENCE_CONFLICT")
        self.assertEqual(receipt["series"][0]["reason"], "conflicting_reviewed_responses_for_current_offer")

    def test_late_response_to_superseded_offer_surfaces_conflict(self):
        events = [
            offer_event(),
            offer_event(event_id="o2", offer_version=2, amount_minor=200, issued_at="2026-09-13T10:00:00Z"),
            response_event(received_at="2026-09-13T10:04:00Z", reviewed_at="2026-09-13T10:05:00Z"),
        ]
        receipt = reconcile(simple_batch(events))
        self.assertEqual(receipt["series"][0]["status"], "EVIDENCE_CONFLICT")
        self.assertEqual(receipt["series"][0]["reason"], "response_to_superseded_offer_arrived_after_new_offer")

    def test_response_to_old_offer_reviewed_before_new_offer_does_not_block_new_offer(self):
        events = [
            offer_event(),
            response_event(received_at="2026-09-13T09:30:00Z", reviewed_at="2026-09-13T09:31:00Z"),
            offer_event(event_id="o2", offer_version=2, amount_minor=200, issued_at="2026-09-13T10:00:00Z"),
        ]
        receipt = reconcile(simple_batch(events))
        self.assertEqual(receipt["series"][0]["status"], "AWAITING_RESPONSE")

    def test_exact_event_replay_collapses(self):
        raw = simple_batch([offer_event(), offer_event()])
        self.assertEqual(len(normalize_batch(raw)["events"]), 1)

    def test_event_id_conflict_rejected(self):
        with self.assertRaisesRegex(DecisionRelayError, "reused"):
            normalize_batch(simple_batch([offer_event(), offer_event(series_id="other", amount_minor=200)]))

    def test_offer_version_conflict_rejected(self):
        with self.assertRaises(DecisionRelayError) as ctx:
            normalize_batch(simple_batch([offer_event(), offer_event(event_id="o2", amount_minor=200)]))
        self.assertEqual(ctx.exception.code, "offer_version_conflict")

    def test_review_before_receipt_rejected(self):
        with self.assertRaises(DecisionRelayError) as ctx:
            normalize_batch(simple_batch([offer_event(), response_event(reviewed_at="2026-09-13T09:59:59Z")]))
        self.assertEqual(ctx.exception.code, "review_before_receipt")

    def test_evaluation_before_snapshot_rejected(self):
        with self.assertRaises(DecisionRelayError) as ctx:
            reconcile(batch(), evaluated_at="2026-09-13T11:59:59Z")
        self.assertEqual(ctx.exception.code, "evaluation_before_snapshot")

    def test_receipt_deterministic_under_event_reordering(self):
        a = batch(); b = batch(); b["events"] = list(reversed(b["events"]))
        ra, rb = reconcile(a), reconcile(b)
        self.assertEqual(ra["series"], rb["series"])
        self.assertEqual(ra["decision_queue"], rb["decision_queue"])

    def test_self_digest_matches(self):
        receipt = reconcile(batch())
        self.assertTrue(receipt_self_digest_matches(receipt))

    def test_tampered_receipt_fails_self_digest(self):
        receipt = reconcile(batch()); receipt["series"][0]["amount_minor"] += 1
        self.assertFalse(receipt_self_digest_matches(receipt))

    def test_verify_requires_independent_expected_digest(self):
        receipt = reconcile(batch())
        self.assertTrue(verify_receipt(receipt, receipt["receipt_sha256"], batch()))
        self.assertFalse(verify_receipt(receipt, "0" * 64, batch()))

    def test_changed_source_fails_verification(self):
        receipt = reconcile(batch()); changed = batch(); changed["events"][0]["amount_minor"] += 1
        self.assertFalse(verify_receipt(receipt, receipt["receipt_sha256"], changed))

    def test_recomputed_forged_authority_fails(self):
        receipt = reconcile(batch())
        receipt["authority"]["payment_or_charge"] = True
        body = deepcopy(receipt); body.pop("receipt_sha256"); receipt["receipt_sha256"] = canonical_digest(body)
        self.assertFalse(verify_receipt(receipt, receipt["receipt_sha256"], batch()))

    def test_forged_receipt_shape_fails_closed(self):
        receipt = reconcile(batch())
        receipt["series"] = {"not": "an array"}
        body = deepcopy(receipt); body.pop("receipt_sha256"); receipt["receipt_sha256"] = canonical_digest(body)
        self.assertFalse(verify_receipt(receipt, receipt["receipt_sha256"], batch()))

    def test_forged_decision_queue_fails_closed(self):
        receipt = reconcile(batch())
        receipt["decision_queue"] = []
        receipt["summary"]["decision_count"] = 0
        body = deepcopy(receipt); body.pop("receipt_sha256"); receipt["receipt_sha256"] = canonical_digest(body)
        self.assertFalse(verify_receipt(receipt, receipt["receipt_sha256"], batch()))

    def test_all_authorities_are_false(self):
        self.assertTrue(all(value is False for value in reconcile(batch())["authority"].values()))

    def test_engine_forbids_authority_mutation(self):
        with self.assertRaises(AuthorityBoundaryError):
            RelayEngine().mutate_commercial_authority()

    def test_engine_requires_ingest_before_reconcile(self):
        with self.assertRaises(DecisionRelayError) as ctx:
            RelayEngine().reconcile()
        self.assertEqual(ctx.exception.code, "no_batch")

    def test_engine_roundtrip(self):
        engine = RelayEngine(); info = engine.ingest(batch()); receipt = engine.reconcile()
        self.assertEqual(info["event_count"], 7)
        self.assertEqual(len(engine.decisions()), 2)
        self.assertTrue(engine.verify(receipt["receipt_sha256"], evaluated_at=receipt["evaluated_at"]))


if __name__ == "__main__":
    unittest.main()
