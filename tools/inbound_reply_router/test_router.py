from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

try:
    from .router import (
        DuplicateKeyError,
        Policy,
        RouterError,
        load_json,
        route_reply,
        write_receipt_atomic,
    )
except ImportError:
    from router import (
        DuplicateKeyError,
        Policy,
        RouterError,
        load_json,
        route_reply,
        write_receipt_atomic,
    )


NOW = "2026-09-13T08:30:00Z"
CAPTURED = "2026-09-13T08:29:30Z"
SENT = "2026-09-13T08:20:00Z"


def context():
    return {
        "schema": "inbound-reply-context/v1",
        "offer_id": "offer-123",
        "counterparty": "buyer@example.com",
        "thread_id": "thread-abc",
        "owner_id": "ZFY-9130415X7Q",
        "prior_outbound_message_id": "outbound-1",
        "prior_outbound_observed_at": SENT,
    }


def evidence(*events):
    return {
        "schema": "inbound-reply-evidence/v1",
        "captured_at": CAPTURED,
        "provider_query_complete": True,
        "ownership_query_complete": True,
        "events": list(events),
        "owner_bindings": [
            {
                "owner_id": "ZFY-9130415X7Q",
                "offer_id": "offer-123",
                "thread_id": "thread-abc",
                "status": "ACTIVE",
                "observed_at": "2026-09-13T08:29:00Z",
            }
        ],
    }


def event(
    classification,
    *,
    message_id="inbound-1",
    observed_at="2026-09-13T08:25:00Z",
    offer_id="offer-123",
    thread_id="thread-abc",
    counterparty="buyer@example.com",
    new_route=None,
):
    human = classification.startswith("HUMAN_")
    row = {
        "message_id": message_id,
        "thread_id": thread_id,
        "counterparty": counterparty,
        "observed_at": observed_at,
        "offer_id": offer_id,
        "classification": classification,
        "classified_by": "human_operator" if human else "provider",
        "classifier_id": "operator-7" if human else None,
        "new_route": new_route,
    }
    return row


class RouterTests(unittest.TestCase):
    def route(self, ev=None, ctx=None):
        return route_reply(
            ctx or context(),
            ev if ev is not None else evidence(),
            evaluated_at=NOW,
        )

    def test_no_new_inbound_waits(self):
        receipt = self.route()
        self.assertEqual(receipt["action"], "WAIT_NO_ACTION")
        self.assertEqual(receipt["basis"], ["no_new_inbound_evidence"])
        self.assertFalse(receipt["authority"]["reply_send_authorized"])

    def test_interest_requires_owner_reply_but_authorizes_no_send(self):
        receipt = self.route(evidence(event("HUMAN_INTERESTED")))
        self.assertEqual(receipt["action"], "OWNER_REPLY_REQUIRED")
        self.assertIn("human_interest", receipt["basis"][0])
        self.assertFalse(receipt["authority"]["side_effects_authorized"])
        self.assertFalse(receipt["authority"]["payment_authorized"])
        self.assertFalse(receipt["authority"]["contract_authorized"])
        self.assertFalse(receipt["authority"]["revenue_recognized"])
        self.assertFalse(receipt["authority"]["buyer_acceptance_inferred"])

    def test_question_requires_owner_reply(self):
        receipt = self.route(evidence(event("HUMAN_QUESTION")))
        self.assertEqual(receipt["action"], "OWNER_REPLY_REQUIRED")

    def test_route_change_requires_owner_verification(self):
        receipt = self.route(
            evidence(
                event(
                    "HUMAN_ROUTE_CHANGE",
                    new_route="new.owner@Example.org",
                )
            )
        )
        self.assertEqual(receipt["action"], "OWNER_REPLY_REQUIRED")
        self.assertEqual(receipt["candidate_new_route"], "new.owner@example.org")
        self.assertFalse(receipt["authority"]["reply_send_authorized"])

    def test_route_change_without_new_route_is_invalid(self):
        with self.assertRaises(RouterError):
            self.route(evidence(event("HUMAN_ROUTE_CHANGE")))

    def test_route_change_to_current_route_holds(self):
        receipt = self.route(
            evidence(
                event(
                    "HUMAN_ROUTE_CHANGE",
                    new_route="buyer@example.com",
                )
            )
        )
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("route_change_reuses_current_route", receipt["basis"])

    def test_decline_closes_offer_without_hard_unsubscribe(self):
        receipt = self.route(evidence(event("HUMAN_DECLINED")))
        self.assertEqual(receipt["action"], "CLOSE_DO_NOT_CONTACT")
        self.assertTrue(receipt["do_not_resend"])
        self.assertFalse(receipt["hard_do_not_contact"])

    def test_unsubscribe_is_hard_terminal(self):
        receipt = self.route(evidence(event("HUMAN_UNSUBSCRIBE")))
        self.assertEqual(receipt["action"], "CLOSE_DO_NOT_CONTACT")
        self.assertTrue(receipt["do_not_resend"])
        self.assertTrue(receipt["hard_do_not_contact"])

    def test_post_unsubscribe_interest_holds_for_manual_override(self):
        receipt = self.route(
            evidence(
                event(
                    "HUMAN_UNSUBSCRIBE",
                    message_id="u1",
                    observed_at="2026-09-13T08:23:00Z",
                ),
                event(
                    "HUMAN_INTERESTED",
                    message_id="i1",
                    observed_at="2026-09-13T08:26:00Z",
                ),
            )
        )
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn(
            "post_unsubscribe_human_requires_manual_override",
            receipt["basis"],
        )

    def test_routing_ack_is_not_interest(self):
        receipt = self.route(evidence(event("HUMAN_ROUTING_ACK")))
        self.assertEqual(receipt["action"], "WAIT_NO_ACTION")
        self.assertIn("not_buyer_interest", receipt["basis"][0])

    def test_human_other_requires_review_not_reply_authority(self):
        receipt = self.route(evidence(event("HUMAN_OTHER")))
        self.assertEqual(receipt["action"], "OWNER_REVIEW_REQUIRED")
        self.assertFalse(receipt["authority"]["reply_send_authorized"])

    def test_auto_ack_is_not_interest(self):
        receipt = self.route(evidence(event("AUTO_ACK")))
        self.assertEqual(receipt["action"], "WAIT_NO_ACTION")
        self.assertIn("automated_acknowledgement", receipt["basis"][0])

    def test_out_of_office_is_not_interest(self):
        receipt = self.route(evidence(event("OUT_OF_OFFICE")))
        self.assertEqual(receipt["action"], "WAIT_NO_ACTION")
        self.assertIn("out_of_office", receipt["basis"][0])

    def test_delivery_failure_requires_route_repair_and_no_resend(self):
        receipt = self.route(evidence(event("DELIVERY_FAILURE")))
        self.assertEqual(receipt["action"], "ROUTE_REPAIR_REQUIRED")
        self.assertTrue(receipt["do_not_resend"])
        self.assertFalse(receipt["authority"]["resend_authorized"])

    def test_delivery_delay_waits(self):
        receipt = self.route(evidence(event("DELIVERY_DELAY")))
        self.assertEqual(receipt["action"], "WAIT_NO_ACTION")

    def test_unknown_holds(self):
        receipt = self.route(evidence(event("UNKNOWN")))
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("unclassified_inbound_evidence", receipt["basis"])

    def test_human_and_delivery_failure_conflict_holds(self):
        receipt = self.route(
            evidence(
                event("HUMAN_QUESTION", message_id="h1"),
                event("DELIVERY_FAILURE", message_id="d1"),
            )
        )
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn(
            "human_reply_conflicts_with_delivery_failure",
            receipt["basis"],
        )

    def test_newer_auto_ack_does_not_erase_human_reply(self):
        receipt = self.route(
            evidence(
                event(
                    "HUMAN_INTERESTED",
                    message_id="h1",
                    observed_at="2026-09-13T08:24:00Z",
                ),
                event(
                    "AUTO_ACK",
                    message_id="a1",
                    observed_at="2026-09-13T08:27:00Z",
                ),
            )
        )
        self.assertEqual(receipt["action"], "OWNER_REPLY_REQUIRED")

    def test_latest_human_disposition_wins_interest_then_decline(self):
        receipt = self.route(
            evidence(
                event(
                    "HUMAN_INTERESTED",
                    message_id="h1",
                    observed_at="2026-09-13T08:24:00Z",
                ),
                event(
                    "HUMAN_DECLINED",
                    message_id="h2",
                    observed_at="2026-09-13T08:27:00Z",
                ),
            )
        )
        self.assertEqual(receipt["action"], "CLOSE_DO_NOT_CONTACT")

    def test_latest_human_disposition_wins_decline_then_interest(self):
        receipt = self.route(
            evidence(
                event(
                    "HUMAN_DECLINED",
                    message_id="h1",
                    observed_at="2026-09-13T08:24:00Z",
                ),
                event(
                    "HUMAN_INTERESTED",
                    message_id="h2",
                    observed_at="2026-09-13T08:27:00Z",
                ),
            )
        )
        self.assertEqual(receipt["action"], "OWNER_REPLY_REQUIRED")

    def test_prior_reply_before_outbound_is_ignored(self):
        receipt = self.route(
            evidence(
                event(
                    "HUMAN_QUESTION",
                    observed_at="2026-09-13T08:19:59Z",
                )
            )
        )
        self.assertEqual(receipt["action"], "WAIT_NO_ACTION")
        self.assertEqual(
            receipt["evidence_counts"]["ignored_pre_outbound_events"], 1
        )

    def test_prior_unsubscribe_before_outbound_holds(self):
        receipt = self.route(
            evidence(
                event(
                    "HUMAN_UNSUBSCRIBE",
                    observed_at="2026-09-13T08:19:59Z",
                )
            )
        )
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("outbound_after_prior_unsubscribe", receipt["basis"])

    def test_identical_duplicate_message_id_is_deduped(self):
        row = event("HUMAN_INTERESTED")
        receipt = self.route(evidence(row, deepcopy(row)))
        self.assertEqual(receipt["action"], "OWNER_REPLY_REQUIRED")
        self.assertEqual(receipt["evidence_counts"]["raw_events"], 2)
        self.assertEqual(receipt["evidence_counts"]["deduped_events"], 1)

    def test_conflicting_duplicate_message_id_holds(self):
        first = event("HUMAN_INTERESTED")
        second = event("HUMAN_QUESTION")
        receipt = self.route(evidence(first, second))
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("conflicting_duplicate_message_id", receipt["basis"])

    def test_incomplete_provider_query_holds(self):
        ev = evidence()
        ev["provider_query_complete"] = False
        receipt = self.route(ev)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("provider_query_incomplete", receipt["basis"])

    def test_incomplete_ownership_query_holds(self):
        ev = evidence()
        ev["ownership_query_complete"] = False
        receipt = self.route(ev)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("ownership_query_incomplete", receipt["basis"])

    def test_stale_evidence_holds(self):
        ev = evidence()
        ev["captured_at"] = "2026-09-13T08:00:00Z"
        receipt = self.route(ev)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("evidence_snapshot_stale", receipt["basis"])

    def test_future_evidence_holds(self):
        ev = evidence()
        ev["captured_at"] = "2026-09-13T08:40:00Z"
        receipt = self.route(ev)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("evidence_snapshot_from_future", receipt["basis"])

    def test_no_active_owner_holds(self):
        ev = evidence()
        ev["owner_bindings"][0]["status"] = "RELEASED"
        receipt = self.route(ev)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("no_active_owner", receipt["basis"])

    def test_active_owner_mismatch_holds(self):
        ev = evidence()
        ev["owner_bindings"][0]["owner_id"] = "other-owner"
        receipt = self.route(ev)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("active_owner_mismatch", receipt["basis"])

    def test_multiple_active_owners_hold(self):
        ev = evidence()
        ev["owner_bindings"].append(
            {
                "owner_id": "other-owner",
                "offer_id": "offer-123",
                "thread_id": "thread-abc",
                "status": "ACTIVE",
                "observed_at": "2026-09-13T08:29:00Z",
            }
        )
        receipt = self.route(ev)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("multiple_active_owners", receipt["basis"])

    def test_duplicate_owner_row_holds(self):
        ev = evidence()
        ev["owner_bindings"].append(deepcopy(ev["owner_bindings"][0]))
        receipt = self.route(ev)
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("duplicate_owner_binding", receipt["basis"])

    def test_provider_scope_mismatch_holds(self):
        receipt = self.route(
            evidence(event("AUTO_ACK", thread_id="wrong-thread"))
        )
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("provider_evidence_scope_mismatch", receipt["basis"])

    def test_counterparty_scope_mismatch_holds(self):
        receipt = self.route(
            evidence(event("AUTO_ACK", counterparty="other@example.com"))
        )
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("provider_evidence_scope_mismatch", receipt["basis"])

    def test_offer_scope_mismatch_holds(self):
        receipt = self.route(
            evidence(event("AUTO_ACK", offer_id="other-offer"))
        )
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("provider_evidence_scope_mismatch", receipt["basis"])

    def test_event_after_snapshot_holds(self):
        receipt = self.route(
            evidence(
                event(
                    "AUTO_ACK",
                    observed_at="2026-09-13T08:36:00Z",
                )
            )
        )
        self.assertEqual(receipt["action"], "HOLD")
        self.assertIn("event_after_snapshot", receipt["basis"])

    def test_human_classification_requires_human_operator(self):
        row = event("HUMAN_INTERESTED")
        row["classified_by"] = "provider"
        row["classifier_id"] = None
        with self.assertRaises(RouterError):
            self.route(evidence(row))

    def test_provider_classification_rejects_human_classifier(self):
        row = event("AUTO_ACK")
        row["classified_by"] = "human_operator"
        row["classifier_id"] = "operator-7"
        with self.assertRaises(RouterError):
            self.route(evidence(row))

    def test_unknown_field_rejected(self):
        ctx = context()
        ctx["surprise"] = True
        with self.assertRaises(RouterError):
            self.route(evidence(), ctx=ctx)

    def test_naive_timestamp_rejected(self):
        ev = evidence(event("AUTO_ACK"))
        ev["captured_at"] = "2026-09-13T08:29:30"
        with self.assertRaises(RouterError):
            self.route(ev)

    def test_policy_bounds_rejected(self):
        with self.assertRaises(RouterError):
            route_reply(
                context(),
                evidence(),
                evaluated_at=NOW,
                policy=Policy(max_evidence_age_seconds=-1),
            )

    def test_receipt_is_deterministic(self):
        ev = evidence(event("HUMAN_QUESTION"))
        first = self.route(deepcopy(ev))
        second = self.route(deepcopy(ev))
        self.assertEqual(first, second)
        self.assertEqual(len(first["receipt_sha256"]), 64)

    def test_message_id_digest_is_order_stable(self):
        e1 = event(
            "AUTO_ACK",
            message_id="b",
            observed_at="2026-09-13T08:22:00Z",
        )
        e2 = event(
            "OUT_OF_OFFICE",
            message_id="a",
            observed_at="2026-09-13T08:23:00Z",
        )
        one = self.route(evidence(e1, e2))
        two = self.route(evidence(e2, e1))
        self.assertEqual(
            one["relevant_message_ids_sha256"],
            two["relevant_message_ids_sha256"],
        )

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dup.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(DuplicateKeyError):
                load_json(path)

    def test_atomic_write_round_trip(self):
        receipt = self.route(evidence(event("HUMAN_QUESTION")))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "receipt.json"
            write_receipt_atomic(receipt, target)
            loaded = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(loaded, receipt)
            leftovers = list(Path(tmp).glob(".receipt.json.*.tmp"))
            self.assertEqual(leftovers, [])

    def test_cli_writes_same_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            context_path = tmp_path / "context.json"
            evidence_path = tmp_path / "evidence.json"
            output_path = tmp_path / "receipt.json"
            context_path.write_text(json.dumps(context()), encoding="utf-8")
            evidence_path.write_text(
                json.dumps(evidence(event("HUMAN_INTERESTED"))),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("router.py")),
                    "--context",
                    str(context_path),
                    "--evidence",
                    str(evidence_path),
                    "--evaluated-at",
                    NOW,
                    "--output",
                    str(output_path),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            cli_receipt = json.loads(output_path.read_text(encoding="utf-8"))
            direct = self.route(evidence(event("HUMAN_INTERESTED")))
            self.assertEqual(cli_receipt, direct)


if __name__ == "__main__":
    unittest.main()
