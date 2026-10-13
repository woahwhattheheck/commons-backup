from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.outbound_send_guard import route_guard


NOW = "2026-09-13T15:30:00Z"
OLD = "2026-08-01T12:00:00Z"
OLDER = "2026-07-01T12:00:00Z"
BUYER = "buyer@example.com"
SOURCE_SHA = "a" * 64


class RouteGuardTests(unittest.TestCase):
    def intent(self, *, offer: str = "offer-new") -> dict[str, object]:
        return {
            "schema_version": "outbound-send-intent/v1",
            "intent_id": "intent-route-compose-1",
            "recipient": BUYER,
            "offer_id": offer,
            "requested_at": NOW,
            "route_kind": "email",
        }

    def mail(
        self,
        message_id: str,
        observed_at: str,
        *,
        offer_id: str = "offer-old",
        direction: str = "outbound",
    ) -> dict[str, object]:
        return {
            "message_id": message_id,
            "direction": direction,
            "counterparty": BUYER,
            "observed_at": observed_at,
            "offer_id": offer_id if direction == "outbound" else None,
        }

    def slack_sent(
        self,
        event_id: str,
        observed_at: str,
        *,
        provider_message_id: str | None = None,
        offer_id: str = "offer-old",
    ) -> dict[str, object]:
        return {
            "event_id": event_id,
            "kind": "sent",
            "recipient": BUYER,
            "observed_at": observed_at,
            "offer_id": offer_id,
            "provider_message_id": provider_message_id,
        }

    def evidence(
        self,
        *,
        outbound: bool = True,
        outbound_time: str = OLD,
        outbound_offer: str = "offer-old",
        inbound_time: str | None = None,
    ) -> dict[str, object]:
        messages: list[dict[str, object]] = []
        if outbound:
            messages.append(self.mail("provider-old", outbound_time, offer_id=outbound_offer))
        if inbound_time is not None:
            messages.append(self.mail("provider-inbound", inbound_time, direction="inbound"))
        return {
            "schema_version": "outbound-send-evidence/v1",
            "generated_at": NOW,
            "mailbox": {
                "complete": True,
                "query_id": "mail-query-1",
                "messages": messages,
            },
            "slack": {
                "complete": True,
                "query_id": "slack-query-1",
                "events": [],
            },
            "policy": {
                "cross_offer_cooldown_days": 30,
                "max_evidence_age_seconds": 900,
                "max_future_skew_seconds": 300,
            },
        }

    def route(
        self,
        *,
        decision_kind: str = "unconfirmed",
        recipient: str = BUYER,
        provider_message_id: str = "provider-old",
        sent_at: str = OLD,
        as_of: str = NOW,
    ) -> dict[str, object]:
        events: list[dict[str, object]] = []
        spec = {
            "block": (550, "5.1.1"),
            "hold": (550, "5.4.1"),
            "temporary": (450, "4.2.2"),
        }
        if decision_kind in spec:
            smtp_code, enhanced_status = spec[decision_kind]
            events.append(
                {
                    "event_id": f"dsn-{decision_kind}-1",
                    "kind": "dsn",
                    "provider_message_id": provider_message_id,
                    "recipient": recipient,
                    "observed_at": "2026-08-01T12:05:00Z",
                    "source_id": f"source-{decision_kind}-1",
                    "source_sha256": SOURCE_SHA,
                    "smtp_code": smtp_code,
                    "enhanced_status": enhanced_status,
                }
            )
        elif decision_kind == "delivered":
            events.append(
                {
                    "event_id": "delivered-1",
                    "kind": "delivered",
                    "provider_message_id": provider_message_id,
                    "recipient": recipient,
                    "observed_at": "2026-08-01T12:05:00Z",
                    "source_id": "source-delivered-1",
                    "source_sha256": SOURCE_SHA,
                    "smtp_code": None,
                    "enhanced_status": None,
                }
            )
        elif decision_kind == "conflict":
            events.extend(
                [
                    {
                        "event_id": "dsn-block-1",
                        "kind": "dsn",
                        "provider_message_id": provider_message_id,
                        "recipient": recipient,
                        "observed_at": "2026-08-01T12:05:00Z",
                        "source_id": "source-block-1",
                        "source_sha256": SOURCE_SHA,
                        "smtp_code": 550,
                        "enhanced_status": "5.1.1",
                    },
                    {
                        "event_id": "delivered-1",
                        "kind": "delivered",
                        "provider_message_id": provider_message_id,
                        "recipient": recipient,
                        "observed_at": "2026-08-01T12:06:00Z",
                        "source_id": "source-delivered-1",
                        "source_sha256": "b" * 64,
                        "smtp_code": None,
                        "enhanced_status": None,
                    },
                ]
            )
        elif decision_kind != "unconfirmed":
            raise AssertionError(decision_kind)
        return {
            "schema_version": "outbound-route-lifecycle-evidence/v1",
            "capture_id": "route-capture-1",
            "recipient": recipient,
            "provider_message_id": provider_message_id,
            "sent_at": sent_at,
            "as_of": as_of,
            "complete": True,
            "next_cursor": None,
            "query_id": "route-query-1",
            "events": events,
        }

    def test_block_route_demotes_allow_new_to_do_not_resend(self) -> None:
        receipt = route_guard.evaluate(self.intent(), self.evidence(), self.route(decision_kind="block"))
        self.assertEqual(receipt["payload"]["base_guard"]["decision"], "ALLOW_NEW")
        self.assertEqual(receipt["payload"]["route_lifecycle"]["decision"], "BLOCK_ROUTE")
        self.assertEqual(receipt["payload"]["decision"], "DO_NOT_RESEND")
        self.assertFalse(receipt["payload"]["side_effects_authorized"])

    def test_hold_variants_demote_allow_new(self) -> None:
        for kind in ("hold", "temporary"):
            with self.subTest(kind=kind):
                receipt = route_guard.evaluate(self.intent(), self.evidence(), self.route(decision_kind=kind))
                self.assertEqual(receipt["payload"]["route_lifecycle"]["decision"], "HOLD_ROUTE")
                self.assertEqual(receipt["payload"]["decision"], "HOLD")

    def test_caller_supplied_nonblocking_route_cannot_satisfy_send_capable_requirement(self) -> None:
        for kind in ("delivered", "unconfirmed"):
            with self.subTest(kind=kind):
                receipt = route_guard.evaluate(self.intent(), self.evidence(), self.route(decision_kind=kind))
                self.assertEqual(receipt["payload"]["base_guard"]["decision"], "ALLOW_NEW")
                self.assertEqual(receipt["payload"]["route_lifecycle"]["decision"], kind.upper())
                self.assertEqual(receipt["payload"]["decision"], "HOLD")
                self.assertEqual(receipt["payload"]["authority"], "partial")
                self.assertTrue(
                    any("lacks independent complete-snapshot authority" in reason for reason in receipt["payload"]["reasons"])
                )

    def test_forged_empty_complete_snapshot_cannot_preserve_allow_new(self) -> None:
        forged = self.route(decision_kind="block")
        forged["events"] = []
        receipt = route_guard.evaluate(self.intent(), self.evidence(), forged)
        self.assertEqual(receipt["payload"]["route_lifecycle"]["decision"], "UNCONFIRMED")
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertEqual(receipt["payload"]["authority"], "partial")

    def test_omitting_block_from_complete_snapshot_cannot_preserve_allow_new(self) -> None:
        forged = self.route(decision_kind="conflict")
        forged["events"] = [event for event in forged["events"] if event["kind"] == "delivered"]
        receipt = route_guard.evaluate(self.intent(), self.evidence(), forged)
        self.assertEqual(receipt["payload"]["route_lifecycle"]["decision"], "DELIVERED")
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertEqual(receipt["payload"]["authority"], "partial")

    def test_stale_nonblocking_snapshot_replay_is_rejected(self) -> None:
        with self.assertRaisesRegex(route_guard.ComposeError, "as_of must equal"):
            route_guard.evaluate(
                self.intent(),
                self.evidence(),
                self.route(decision_kind="unconfirmed", as_of="2026-09-13T15:29:59Z"),
            )

    def test_missing_route_evidence_holds_send_capable_prior_route(self) -> None:
        receipt = route_guard.evaluate(self.intent(), self.evidence(), None)
        self.assertEqual(receipt["payload"]["base_guard"]["decision"], "ALLOW_NEW")
        self.assertTrue(receipt["payload"]["route_lifecycle"]["required"])
        self.assertEqual(receipt["payload"]["route_lifecycle"]["status"], "MISSING")
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertEqual(receipt["payload"]["authority"], "partial")

    def test_brand_new_recipient_needs_no_route_evidence(self) -> None:
        receipt = route_guard.evaluate(self.intent(), self.evidence(outbound=False), None)
        self.assertEqual(receipt["payload"]["decision"], "ALLOW_NEW")
        self.assertFalse(receipt["payload"]["route_lifecycle"]["required"])
        self.assertEqual(receipt["payload"]["route_lifecycle"]["status"], "NOT_APPLICABLE")

    def test_irrelevant_route_evidence_without_prior_outbound_is_rejected(self) -> None:
        with self.assertRaisesRegex(route_guard.ComposeError, "no prior outbound"):
            route_guard.evaluate(self.intent(), self.evidence(outbound=False), self.route())

    def test_route_identity_fields_are_bound(self) -> None:
        cases = [
            (self.route(provider_message_id="provider-other"), "latest provider message"),
            (self.route(recipient="other@example.com"), "recipient does not match"),
            (self.route(sent_at="2026-08-01T12:01:00Z"), "sent_at does not match"),
            (self.route(as_of="2026-09-13T15:29:59Z"), "as_of must equal"),
        ]
        for route, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(route_guard.ComposeError, message):
                    route_guard.evaluate(self.intent(), self.evidence(), route)

    def test_equivalent_timezone_sent_time_is_accepted(self) -> None:
        receipt = route_guard.evaluate(
            self.intent(),
            self.evidence(),
            self.route(sent_at="2026-08-01T08:00:00-04:00", decision_kind="delivered"),
        )
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertEqual(receipt["payload"]["authority"], "partial")

    def test_conflicting_delivery_and_block_is_unknown_hold(self) -> None:
        receipt = route_guard.evaluate(self.intent(), self.evidence(), self.route(decision_kind="conflict"))
        self.assertEqual(receipt["payload"]["route_lifecycle"]["decision"], "HOLD_ROUTE")
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertEqual(receipt["payload"]["authority"], "unknown")

    def test_reply_only_is_demoted_by_blocked_route(self) -> None:
        evidence = self.evidence(inbound_time="2026-09-13T15:00:00Z")
        receipt = route_guard.evaluate(self.intent(), evidence, self.route(decision_kind="block"))
        self.assertEqual(receipt["payload"]["base_guard"]["decision"], "REPLY_ONLY")
        self.assertEqual(receipt["payload"]["decision"], "DO_NOT_RESEND")
        self.assertIsNone(receipt["payload"]["reply_message_id"])

    def test_base_do_not_resend_is_never_promoted(self) -> None:
        receipt = route_guard.evaluate(
            self.intent(offer="offer-old"),
            self.evidence(outbound_offer="offer-old"),
            self.route(decision_kind="delivered"),
        )
        self.assertEqual(receipt["payload"]["base_guard"]["decision"], "DO_NOT_RESEND")
        self.assertEqual(receipt["payload"]["decision"], "DO_NOT_RESEND")

    def test_base_hold_does_not_require_route_evidence(self) -> None:
        receipt = route_guard.evaluate(
            self.intent(), self.evidence(outbound_time="2026-09-10T12:00:00Z"), None
        )
        self.assertEqual(receipt["payload"]["base_guard"]["decision"], "HOLD")
        self.assertFalse(receipt["payload"]["route_lifecycle"]["required"])
        self.assertEqual(receipt["payload"]["decision"], "HOLD")

    def test_slack_only_latest_send_without_provider_id_holds(self) -> None:
        evidence = self.evidence(outbound_time=OLDER)
        evidence["slack"]["events"].append(self.slack_sent("slack-newer-send", OLD))
        receipt = route_guard.evaluate(self.intent(), evidence, None)
        self.assertEqual(receipt["payload"]["base_guard"]["decision"], "ALLOW_NEW")
        self.assertEqual(receipt["payload"]["base_guard"]["latest_outbound_ref"], "slack:slack-newer-send")
        self.assertEqual(receipt["payload"]["route_lifecycle"]["status"], "PROVIDER_MESSAGE_UNAVAILABLE")
        self.assertEqual(receipt["payload"]["decision"], "HOLD")

    def test_slack_provider_id_must_resolve_to_mailbox(self) -> None:
        evidence = self.evidence(outbound_time=OLDER)
        evidence["slack"]["events"].append(
            self.slack_sent("slack-newer-send", OLD, provider_message_id="provider-missing")
        )
        receipt = route_guard.evaluate(self.intent(), evidence, None)
        self.assertEqual(receipt["payload"]["route_lifecycle"]["status"], "PROVIDER_MESSAGE_UNAVAILABLE")
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        with self.assertRaisesRegex(route_guard.ComposeError, "cannot bind"):
            route_guard.evaluate(
                self.intent(),
                evidence,
                self.route(provider_message_id="provider-missing", sent_at=OLDER),
            )

    def test_slack_latest_send_binds_its_provider_message_not_same_time_mail(self) -> None:
        evidence = self.evidence(outbound_time=OLD)
        evidence["mailbox"]["messages"].append(
            self.mail("provider-slack", OLD, offer_id="offer-slack")
        )
        evidence["slack"]["events"].append(
            self.slack_sent(
                "zz-slack-same-time",
                OLD,
                provider_message_id="provider-slack",
                offer_id="offer-slack",
            )
        )
        with self.assertRaisesRegex(route_guard.ComposeError, "latest provider message"):
            route_guard.evaluate(
                self.intent(),
                evidence,
                self.route(provider_message_id="provider-old", decision_kind="block"),
            )
        good = self.route(provider_message_id="provider-slack", decision_kind="block")
        receipt = route_guard.evaluate(self.intent(), evidence, good)
        self.assertEqual(receipt["payload"]["base_guard"]["latest_outbound_ref"], "slack:zz-slack-same-time")
        self.assertEqual(receipt["payload"]["route_lifecycle"]["target_provider_message_id"], "provider-slack")
        self.assertEqual(receipt["payload"]["decision"], "DO_NOT_RESEND")

    def test_slack_receipt_time_can_follow_provider_send_time(self) -> None:
        evidence = self.evidence(outbound_time=OLDER)
        evidence["slack"]["events"].append(
            self.slack_sent(
                "slack-posted-later",
                OLD,
                provider_message_id="provider-old",
                offer_id="offer-old",
            )
        )
        receipt = route_guard.evaluate(
            self.intent(),
            evidence,
            self.route(provider_message_id="provider-old", sent_at=OLDER, decision_kind="delivered"),
        )
        self.assertEqual(receipt["payload"]["base_guard"]["latest_outbound_at"], OLD)
        self.assertEqual(receipt["payload"]["base_guard"]["latest_outbound_source"], "slack")
        self.assertEqual(receipt["payload"]["route_lifecycle"]["target_sent_at"], OLDER)
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertEqual(receipt["payload"]["authority"], "partial")

    def test_latest_of_two_provider_outbounds_is_the_only_valid_binding(self) -> None:
        evidence = self.evidence(outbound_time=OLDER)
        evidence["mailbox"]["messages"].append(
            self.mail("provider-newer", OLD, offer_id="offer-middle")
        )
        with self.assertRaisesRegex(route_guard.ComposeError, "latest provider message"):
            route_guard.evaluate(
                self.intent(),
                evidence,
                self.route(provider_message_id="provider-old", sent_at=OLDER),
            )
        receipt = route_guard.evaluate(
            self.intent(),
            evidence,
            self.route(provider_message_id="provider-newer", decision_kind="block"),
        )
        self.assertEqual(receipt["payload"]["decision"], "DO_NOT_RESEND")
        self.assertEqual(receipt["payload"]["route_lifecycle"]["target_provider_message_id"], "provider-newer")

    def test_inputs_are_snapshotted_not_mutated(self) -> None:
        intent, evidence, route = self.intent(), self.evidence(), self.route(decision_kind="block")
        before = copy.deepcopy((intent, evidence, route))
        route_guard.evaluate(intent, evidence, route)
        self.assertEqual((intent, evidence, route), before)

    def test_receipt_is_deterministic_and_hash_bound(self) -> None:
        first = route_guard.evaluate(self.intent(), self.evidence(), self.route(decision_kind="block"))
        second = route_guard.evaluate(self.intent(), self.evidence(), self.route(decision_kind="block"))
        self.assertEqual(first, second)
        self.assertEqual(len(first["receipt_sha256"]), 64)
        self.assertEqual(len(first["payload"]["base_guard"]["receipt_sha256"]), 64)
        self.assertEqual(len(first["payload"]["route_lifecycle"]["receipt_sha256"]), 64)

    def test_cli_exit_semantics(self) -> None:
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            intent = tmp / "intent.json"
            evidence = tmp / "evidence.json"
            route = tmp / "route.json"
            out = tmp / "receipt.json"
            intent.write_text(json.dumps(self.intent()), encoding="utf-8")
            evidence.write_text(json.dumps(self.evidence()), encoding="utf-8")
            route.write_text(json.dumps(self.route(decision_kind="block")), encoding="utf-8")
            blocked = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.outbound_send_guard.route_guard",
                    "--intent",
                    str(intent),
                    "--evidence",
                    str(evidence),
                    "--route-evidence",
                    str(route),
                    "--out",
                    str(out),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 5, blocked.stderr)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["payload"]["decision"], "DO_NOT_RESEND")
            missing = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.outbound_send_guard.route_guard",
                    "--intent",
                    str(intent),
                    "--evidence",
                    str(evidence),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(missing.returncode, 4, missing.stderr)
            self.assertEqual(json.loads(missing.stdout)["payload"]["decision"], "HOLD")


if __name__ == "__main__":
    unittest.main()
