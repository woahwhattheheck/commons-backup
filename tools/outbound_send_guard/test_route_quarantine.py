from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.outbound_send_guard import route_quarantine as rq

NOW = "2026-09-13T15:00:00Z"
OLD = "2026-08-01T15:00:00Z"
RECIPIENT = "buyer@example.com"


def intent(*, offer_id: str = "offer-new") -> dict:
    return {
        "schema_version": "outbound-send-intent/v1",
        "intent_id": "intent-1",
        "recipient": RECIPIENT,
        "offer_id": offer_id,
        "requested_at": NOW,
        "route_kind": "email",
    }


def send_evidence(messages: list[dict] | None = None, *, slack_events: list[dict] | None = None) -> dict:
    return {
        "schema_version": "outbound-send-evidence/v1",
        "generated_at": NOW,
        "mailbox": {
            "complete": True,
            "query_id": "mail-q-1",
            "messages": messages or [],
        },
        "slack": {
            "complete": True,
            "query_id": "slack-q-1",
            "events": slack_events or [],
        },
        "policy": {
            "cross_offer_cooldown_days": 30,
            "max_evidence_age_seconds": 900,
            "max_future_skew_seconds": 300,
        },
    }


def outbound(message_id: str = "sent-old", *, observed_at: str = OLD, offer_id: str = "offer-old") -> dict:
    return {
        "message_id": message_id,
        "direction": "outbound",
        "counterparty": RECIPIENT,
        "observed_at": observed_at,
        "offer_id": offer_id,
    }


def route_check(
    message_id: str = "sent-old",
    *,
    sent_at: str = OLD,
    events: list[dict] | None = None,
    as_of: str = NOW,
) -> dict:
    return {
        "schema_version": "outbound-route-lifecycle-evidence/v1",
        "capture_id": f"capture-{message_id}",
        "recipient": RECIPIENT,
        "provider_message_id": message_id,
        "sent_at": sent_at,
        "as_of": as_of,
        "complete": True,
        "next_cursor": None,
        "query_id": f"route-q-{message_id}",
        "events": events or [],
    }


def dsn(message_id: str, *, status: str, smtp: int, event_id: str = "dsn-1") -> dict:
    return {
        "event_id": event_id,
        "kind": "dsn",
        "provider_message_id": message_id,
        "recipient": RECIPIENT,
        "observed_at": NOW,
        "source_id": f"source-{event_id}",
        "source_sha256": "a" * 64,
        "smtp_code": smtp,
        "enhanced_status": status,
    }


def delivered(message_id: str, *, event_id: str = "delivered-1") -> dict:
    return {
        "event_id": event_id,
        "kind": "delivered",
        "provider_message_id": message_id,
        "recipient": RECIPIENT,
        "observed_at": NOW,
        "source_id": f"source-{event_id}",
        "source_sha256": "b" * 64,
    }


def bundle(checks: list[dict], *, recipient: str = RECIPIENT, as_of: str = NOW) -> dict:
    return {
        "schema_version": rq.BUNDLE_SCHEMA,
        "recipient": recipient,
        "as_of": as_of,
        "route_checks": checks,
    }


class RouteQuarantineTests(unittest.TestCase):
    def test_no_history_preserves_allow_new(self) -> None:
        receipt = rq.evaluate(intent(), send_evidence(), bundle([]))
        self.assertEqual(receipt["payload"]["decision"], "ALLOW_NEW")
        self.assertEqual(receipt["payload"]["route_state"], "CLEAR")
        self.assertFalse(receipt["payload"]["side_effects_authorized"])
        self.assertFalse(receipt["payload"]["same_route_send_authorized"])
        self.assertFalse(receipt["payload"]["alternate_route_research_required"])
        self.assertIsNone(receipt["payload"]["research_obligation"])

    def test_different_offer_after_cooldown_is_still_blocked_by_dead_mailbox(self) -> None:
        evidence = send_evidence([outbound()])
        check = route_check(events=[dsn("sent-old", status="5.1.1", smtp=550)])
        receipt = rq.evaluate(intent(offer_id="offer-new"), evidence, bundle([check]))
        self.assertEqual(receipt["payload"]["send_guard_decision"], "ALLOW_NEW")
        self.assertEqual(receipt["payload"]["route_state"], "BLOCKED")
        self.assertEqual(receipt["payload"]["decision"], "DO_NOT_USE_ROUTE")
        self.assertFalse(receipt["payload"]["alternate_route_research_required"])
        self.assertIsNone(receipt["payload"]["research_obligation"])
        self.assertTrue(receipt["payload"]["alternate_route_send_requires_fresh_preflight"])
        self.assertFalse(receipt["payload"]["side_effects_authorized"])

    def test_blocked_route_cannot_be_rehashed_into_alias_hunt_instruction(self) -> None:
        evidence = send_evidence([outbound()])
        check_bundle = bundle([route_check(events=[dsn("sent-old", status="5.1.1", smtp=550)])])
        receipt = rq.evaluate(intent(), evidence, check_bundle)
        tampered = copy.deepcopy(receipt)
        tampered["payload"]["alternate_route_research_required"] = True
        tampered["payload"]["research_obligation"] = {
            "kind": "FIND_INDEPENDENT_PUBLIC_BUSINESS_ROUTE",
            "automatic_replacement_forbidden": True,
        }
        tampered["receipt_sha256"] = rq.digest_object(tampered["payload"])
        self.assertFalse(rq.verify(tampered, intent(), evidence, check_bundle))

    def test_policy_rejection_holds_route(self) -> None:
        evidence = send_evidence([outbound()])
        check = route_check(events=[dsn("sent-old", status="5.4.1", smtp=550)])
        receipt = rq.evaluate(intent(), evidence, bundle([check]))
        self.assertEqual(receipt["payload"]["route_state"], "HOLD")
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertTrue(receipt["payload"]["route_review_required"])
        self.assertFalse(receipt["payload"]["alternate_route_research_required"])
        self.assertIsNone(receipt["payload"]["research_obligation"])

    def test_mailbox_full_holds_route(self) -> None:
        evidence = send_evidence([outbound()])
        check = route_check(events=[dsn("sent-old", status="5.2.2", smtp=550)])
        receipt = rq.evaluate(intent(), evidence, bundle([check]))
        self.assertEqual(receipt["payload"]["decision"], "HOLD")

    def test_transient_failure_holds_route(self) -> None:
        evidence = send_evidence([outbound()])
        check = route_check(events=[dsn("sent-old", status="4.2.2", smtp=450)])
        receipt = rq.evaluate(intent(), evidence, bundle([check]))
        self.assertEqual(receipt["payload"]["decision"], "HOLD")

    def test_delivered_prior_send_does_not_upgrade_same_offer_dnr(self) -> None:
        evidence = send_evidence([outbound(offer_id="offer-same")])
        check = route_check(events=[delivered("sent-old")])
        receipt = rq.evaluate(intent(offer_id="offer-same"), evidence, bundle([check]))
        self.assertEqual(receipt["payload"]["route_state"], "CLEAR")
        self.assertEqual(receipt["payload"]["send_guard_decision"], "DO_NOT_RESEND")
        self.assertEqual(receipt["payload"]["decision"], "DO_NOT_RESEND")

    def test_unconfirmed_prior_send_preserves_send_guard_only(self) -> None:
        evidence = send_evidence([outbound()])
        receipt = rq.evaluate(intent(), evidence, bundle([route_check()]))
        self.assertEqual(receipt["payload"]["route_state"], "CLEAR")
        self.assertEqual(receipt["payload"]["decision"], "ALLOW_NEW")

    def test_missing_route_coverage_fails_closed(self) -> None:
        with self.assertRaisesRegex(rq.QuarantineError, "coverage is incomplete"):
            rq.evaluate(intent(), send_evidence([outbound()]), bundle([]))

    def test_extra_route_check_fails_closed(self) -> None:
        with self.assertRaisesRegex(rq.QuarantineError, "absent from send evidence"):
            rq.evaluate(intent(), send_evidence(), bundle([route_check()]))

    def test_duplicate_route_check_fails_closed(self) -> None:
        evidence = send_evidence([outbound()])
        check = route_check()
        with self.assertRaisesRegex(rq.QuarantineError, "duplicate route check"):
            rq.evaluate(intent(), evidence, bundle([check, copy.deepcopy(check)]))

    def test_sent_at_must_match_provider_send_generation(self) -> None:
        evidence = send_evidence([outbound()])
        check = route_check(sent_at="2026-08-02T15:00:00Z")
        with self.assertRaisesRegex(rq.QuarantineError, "sent_at disagrees"):
            rq.evaluate(intent(), evidence, bundle([check]))

    def test_route_boundary_must_equal_send_snapshot_boundary(self) -> None:
        evidence = send_evidence([outbound()])
        check = route_check(as_of="2026-09-13T14:59:59Z")
        with self.assertRaisesRegex(rq.QuarantineError, "does not share the bundle as_of"):
            rq.evaluate(intent(), evidence, bundle([check]))

    def test_bundle_boundary_must_equal_send_snapshot_boundary(self) -> None:
        with self.assertRaisesRegex(rq.QuarantineError, "must equal send_evidence.generated_at"):
            rq.evaluate(intent(), send_evidence(), bundle([], as_of="2026-09-13T14:59:59Z"))

    def test_conflicting_delivered_and_failure_holds(self) -> None:
        evidence = send_evidence([outbound()])
        check = route_check(
            events=[
                delivered("sent-old"),
                dsn("sent-old", status="5.1.1", smtp=550, event_id="dsn-block"),
            ]
        )
        receipt = rq.evaluate(intent(), evidence, bundle([check]))
        self.assertEqual(receipt["payload"]["route_state"], "HOLD")
        self.assertEqual(receipt["payload"]["decision"], "HOLD")

    def test_slack_sent_without_provider_id_cannot_escape_route_coverage(self) -> None:
        slack = [{
            "event_id": "slack-sent-1",
            "kind": "sent",
            "recipient": RECIPIENT,
            "observed_at": OLD,
            "offer_id": "offer-old",
            "provider_message_id": None,
        }]
        with self.assertRaisesRegex(rq.QuarantineError, "without provider_message_id"):
            rq.evaluate(intent(), send_evidence([], slack_events=slack), bundle([]))

    def test_slack_provider_id_requires_matching_mailbox_send(self) -> None:
        slack = [{
            "event_id": "slack-sent-1",
            "kind": "sent",
            "recipient": RECIPIENT,
            "observed_at": OLD,
            "offer_id": "offer-old",
            "provider_message_id": "sent-old",
        }]
        with self.assertRaisesRegex(rq.QuarantineError, "no matching provider outbound"):
            rq.evaluate(intent(), send_evidence([], slack_events=slack), bundle([]))

    def test_verifier_recomputes_from_all_sources(self) -> None:
        evidence = send_evidence([outbound()])
        check_bundle = bundle([route_check(events=[delivered("sent-old")])])
        receipt = rq.evaluate(intent(), evidence, check_bundle)
        self.assertTrue(rq.verify(receipt, intent(), evidence, check_bundle))
        tampered = copy.deepcopy(receipt)
        tampered["payload"]["decision"] = "DO_NOT_USE_ROUTE"
        tampered["receipt_sha256"] = rq.digest_object(tampered["payload"])
        self.assertFalse(rq.verify(tampered, intent(), evidence, check_bundle))

    def test_duplicate_json_keys_rejected(self) -> None:
        with self.assertRaises(rq.DuplicateKeyError):
            rq.parse_json_bytes(b'{"a":1,"a":2}', "fixture")

    def test_cli_reader_rejects_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(rq.QuarantineError, "regular file"):
                rq._read_bounded_regular(Path(directory), "fixture")


if __name__ == "__main__":
    unittest.main()
