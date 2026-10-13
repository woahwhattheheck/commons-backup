from __future__ import annotations

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from tools.outbound_send_guard import buyer_scope


class BuyerScopeCustodyEscapeTests(unittest.TestCase):
    @staticmethod
    def encoded(value):
        return json.dumps(value, sort_keys=True).encode("utf-8") + b"\n"

    @staticmethod
    def intent(*, offer_id="offer-a"):
        return {
            "schema_version": "outbound-send-intent/v1",
            "intent_id": "intent-1",
            "recipient": "ceo@buyer.test",
            "offer_id": offer_id,
            "requested_at": "2026-09-13T10:10:00Z",
            "route_kind": "email",
        }

    @staticmethod
    def evidence():
        return {
            "schema_version": "outbound-send-evidence/v1",
            "generated_at": "2026-09-13T10:09:00Z",
            "mailbox": {"complete": True, "query_id": "mail-parent", "messages": []},
            "slack": {"complete": True, "query_id": "slack-parent", "events": []},
        }

    @staticmethod
    def scope():
        return {
            "schema_version": "outbound-send-buyer-scope/v1",
            "scope_id": "buyer-1",
            "members": [
                {
                    "email": "ceo@buyer.test",
                    "mailbox_complete": True,
                    "mailbox_query_id": "mail-ceo",
                    "slack_complete": True,
                    "slack_query_id": "slack-ceo",
                }
            ],
        }

    def assert_custody_mismatch(self, intent, evidence, scope, raw_scope=None, raw_evidence=None):
        with self.assertRaisesRegex(
            buyer_scope.ScopeError,
            "raw-byte custody does not match evaluated source objects",
        ):
            buyer_scope._evaluate(
                intent,
                evidence,
                scope,
                raw_bytes=(
                    self.encoded(intent),
                    self.encoded(raw_evidence if raw_evidence is not None else evidence),
                    self.encoded(raw_scope if raw_scope is not None else scope),
                ),
            )

    def test_parsed_object_api_detaches_all_caller_graphs_before_semantics_and_hashing(self):
        intent = self.intent()
        evidence = self.evidence()
        scope = self.scope()
        original_intent = deepcopy(intent)
        original_evidence = deepcopy(evidence)
        original_scope = deepcopy(scope)
        original_rebind = buyer_scope._rebind_evidence

        def rebind_then_mutate(intent_snapshot, evidence_snapshot, members):
            scoped = original_rebind(intent_snapshot, evidence_snapshot, members)
            intent["intent_id"] = "intent-mutated-after-snapshot"
            evidence["mailbox"]["messages"].append(
                {
                    "message_id": "late-caller-mutation",
                    "direction": "outbound",
                    "counterparty": "ceo@buyer.test",
                    "observed_at": "2026-09-13T10:08:00Z",
                    "offer_id": "offer-a",
                }
            )
            scope["members"][0]["mailbox_query_id"] = "mail-mutated-after-snapshot"
            return scoped

        with patch.object(buyer_scope, "_rebind_evidence", side_effect=rebind_then_mutate):
            payload = buyer_scope.evaluate(intent, evidence, scope)["payload"]

        self.assertEqual(payload["decision"], "ALLOW_NEW")
        self.assertEqual(payload["core"]["intent"]["intent_id"], original_intent["intent_id"])
        self.assertEqual(
            payload["buyer_scope"]["members"][0]["mailbox_query_id"],
            original_scope["members"][0]["mailbox_query_id"],
        )
        self.assertEqual(
            payload["source"]["intent_object_sha256"],
            buyer_scope.guard.digest_object(original_intent),
        )
        self.assertEqual(
            payload["source"]["evidence_object_sha256"],
            buyer_scope.guard.digest_object(original_evidence),
        )
        self.assertEqual(
            payload["source"]["scope_object_sha256"],
            buyer_scope.guard.digest_object(original_scope),
        )
        self.assertNotEqual(
            payload["source"]["intent_object_sha256"],
            buyer_scope.guard.digest_object(intent),
        )
        self.assertNotEqual(
            payload["source"]["evidence_object_sha256"],
            buyer_scope.guard.digest_object(evidence),
        )
        self.assertNotEqual(
            payload["source"]["scope_object_sha256"],
            buyer_scope.guard.digest_object(scope),
        )

    def test_internal_custody_path_reparses_and_rejects_mismatched_bytes(self):
        intent = self.intent()
        evidence = self.evidence()
        scope = self.scope()
        with self.assertRaisesRegex(
            buyer_scope.ScopeError,
            "raw-byte custody does not match evaluated source objects",
        ):
            buyer_scope._evaluate(
                intent,
                evidence,
                scope,
                raw_bytes=(
                    self.encoded(self.intent(offer_id="different-offer")),
                    self.encoded(evidence),
                    self.encoded(scope),
                ),
            )

    def test_internal_custody_path_rejects_true_vs_one_alias(self):
        intent = self.intent()
        evidence = self.evidence()
        scope = self.scope()
        forged_scope = self.scope()
        forged_scope["members"][0]["mailbox_complete"] = 1
        self.assert_custody_mismatch(intent, evidence, scope, raw_scope=forged_scope)

    def test_internal_custody_path_rejects_false_vs_zero_alias(self):
        intent = self.intent()
        evidence = self.evidence()
        scope = self.scope()
        scope["members"][0]["slack_complete"] = False
        forged_scope = self.scope()
        forged_scope["members"][0]["slack_complete"] = 0
        self.assert_custody_mismatch(intent, evidence, scope, raw_scope=forged_scope)

    def test_internal_custody_path_rejects_integer_vs_float_alias(self):
        intent = self.intent()
        evidence = self.evidence()
        evidence["policy"] = {"cross_offer_cooldown_days": 1}
        scope = self.scope()
        forged_evidence = self.evidence()
        forged_evidence["policy"] = {"cross_offer_cooldown_days": 1.0}
        self.assert_custody_mismatch(
            intent,
            evidence,
            scope,
            raw_evidence=forged_evidence,
        )

    def test_internal_custody_path_rejects_digest_like_strings(self):
        with self.assertRaisesRegex(
            buyer_scope.ScopeError,
            "exactly three byte strings",
        ):
            buyer_scope._evaluate(
                self.intent(),
                self.evidence(),
                self.scope(),
                raw_bytes=("0" * 64, b"{}", b"{}"),
            )


if __name__ == "__main__":
    unittest.main()