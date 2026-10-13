from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.commercial_reply_guard import guard


ZERO = "0" * 64
BODY = hashlib.sha256(b"draft-body-v1").hexdigest()


def make_router(
    *,
    action="OWNER_REPLY_REQUIRED",
    ids=None,
    owner="Z-OWNER",
    offer="offer-1",
    counterparty="buyer@example.com",
    thread="thread-1",
    evaluated="2026-09-13T10:00:00Z",
    dnr=False,
    hard_dnc=False,
):
    ids = ["in-1"] if ids is None else list(ids)
    body = {
        "schema": guard.ROUTER_RECEIPT_SCHEMA,
        "evaluated_at": evaluated,
        "offer_id": offer,
        "counterparty": counterparty,
        "thread_id": thread,
        "owner_id": owner,
        "prior_outbound_message_id": "out-1",
        "prior_outbound_observed_at": "2026-09-13T09:30:00Z",
        "evidence_captured_at": "2026-09-13T09:59:30Z",
        "action": action,
        "basis": ["fixture"],
        "candidate_new_route": None,
        "do_not_resend": dnr,
        "hard_do_not_contact": hard_dnc,
        "relevant_message_ids": ids,
        "relevant_message_ids_sha256": hashlib.sha256(
            "\n".join(sorted(ids)).encode("utf-8")
        ).hexdigest(),
        "evidence_counts": {
            "raw_events": len(ids),
            "deduped_events": len(ids),
            "ignored_pre_outbound_events": 0,
            "owner_bindings": 1,
        },
        "authority": {
            "owner_queue_custody_only": True,
            "side_effects_authorized": False,
            "reply_send_authorized": False,
            "resend_authorized": False,
            "payment_authorized": False,
            "contract_authorized": False,
            "revenue_recognized": False,
            "buyer_acceptance_inferred": False,
        },
    }
    body["receipt_sha256"] = guard._digest(body)
    return body


def make_policy(**changes):
    body = {
        "schema": guard.POLICY_SCHEMA,
        "policy_id": "policy-1",
        "offer_id": "offer-1",
        "counterparty": "buyer@example.com",
        "thread_id": "thread-1",
        "owner_id": "Z-OWNER",
        "issued_at": "2026-09-13T09:50:00Z",
        "expires_at": "2026-09-13T11:00:00Z",
        "allowed_draft_modes": [
            "ROUTING_CONTEXT",
            "FIT_ANSWER",
            "CLARIFYING_QUESTION",
            "SCHEDULING_COORDINATION",
        ],
    }
    body.update(changes)
    return body


def make_proposal(**changes):
    body = {
        "schema": guard.PROPOSAL_SCHEMA,
        "proposal_id": "proposal-1",
        "offer_id": "offer-1",
        "counterparty": "buyer@example.com",
        "thread_id": "thread-1",
        "owner_id": "Z-OWNER",
        "inbound_message_id": "in-1",
        "mode": "FIT_ANSWER",
        "body_sha256": BODY,
        "requested_at": "2026-09-13T10:01:00Z",
        "history_complete": True,
        "handled_inbound_message_ids": [],
    }
    body.update(changes)
    return body


class CommercialReplyGuardTests(unittest.TestCase):
    def evaluate(self, router=None, policy=None, proposal=None):
        return guard.evaluate(
            make_router() if router is None else router,
            make_policy() if policy is None else policy,
            make_proposal() if proposal is None else proposal,
        )

    def test_four_factual_modes_can_be_drafted(self):
        for mode in sorted(guard.DRAFTABLE_MODES):
            with self.subTest(mode=mode):
                result = self.evaluate(proposal=make_proposal(mode=mode))
                self.assertEqual(result["decision"], "DRAFT_ALLOWED")
                self.assertTrue(result["authority"]["draft_creation_authorized"])
                self.assertFalse(result["authority"]["provider_send_authorized"])

    def test_sensitive_modes_require_owner_review(self):
        for mode in sorted(guard.SENSITIVE_MODES):
            with self.subTest(mode=mode):
                result = self.evaluate(proposal=make_proposal(mode=mode))
                self.assertEqual(result["decision"], "OWNER_REVIEW_REQUIRED")
                self.assertIn(f"sensitive_mode:{mode}", result["reasons"])
                self.assertFalse(result["authority"]["draft_creation_authorized"])
                self.assertFalse(result["authority"]["provider_send_authorized"])
                self.assertFalse(result["authority"]["pricing_authorized"])
                self.assertFalse(result["authority"]["contract_authorized"])

    def test_policy_cannot_preapprove_sensitive_mode(self):
        policy = make_policy(allowed_draft_modes=["FIT_ANSWER", "PRICING"])
        with self.assertRaises(guard.GuardError):
            self.evaluate(policy=policy)

    def test_non_preapproved_factual_mode_requires_owner_review(self):
        result = self.evaluate(
            policy=make_policy(allowed_draft_modes=["FIT_ANSWER"]),
            proposal=make_proposal(mode="ROUTING_CONTEXT"),
        )
        self.assertEqual(result["decision"], "OWNER_REVIEW_REQUIRED")
        self.assertIn("draft_mode_not_preapproved", result["reasons"])

    def test_owner_review_router_cannot_be_downgraded(self):
        result = self.evaluate(router=make_router(action="OWNER_REVIEW_REQUIRED"))
        self.assertEqual(result["decision"], "OWNER_REVIEW_REQUIRED")
        self.assertFalse(result["authority"]["draft_creation_authorized"])

    def test_router_hold_stays_hold(self):
        result = self.evaluate(router=make_router(action="HOLD"))
        self.assertEqual(result["decision"], "HOLD")

    def test_unsubscribe_or_decline_suppresses(self):
        result = self.evaluate(
            router=make_router(
                action="CLOSE_DO_NOT_CONTACT", dnr=True, hard_dnc=True
            )
        )
        self.assertEqual(result["decision"], "SUPPRESS")
        self.assertFalse(result["authority"]["provider_send_authorized"])

    def test_hard_do_not_contact_suppresses_even_if_action_reply(self):
        result = self.evaluate(router=make_router(hard_dnc=True))
        self.assertEqual(result["decision"], "SUPPRESS")

    def test_wait_no_action_stays_no_action(self):
        result = self.evaluate(router=make_router(action="WAIT_NO_ACTION"))
        self.assertEqual(result["decision"], "NO_ACTION")

    def test_delivery_failure_routes_repair_without_send_authority(self):
        result = self.evaluate(
            router=make_router(action="ROUTE_REPAIR_REQUIRED", dnr=True)
        )
        self.assertEqual(result["decision"], "SUPPRESS")
        self.assertFalse(result["authority"]["provider_send_authorized"])

    def test_route_repair_when_not_dnr(self):
        result = self.evaluate(router=make_router(action="ROUTE_REPAIR_REQUIRED"))
        self.assertEqual(result["decision"], "ROUTE_REPAIR")

    def test_scope_mismatch_holds(self):
        for field, value in {
            "offer_id": "other-offer",
            "counterparty": "other@example.com",
            "thread_id": "other-thread",
            "owner_id": "OTHER-OWNER",
        }.items():
            with self.subTest(field=field):
                proposal = make_proposal(**{field: value})
                result = self.evaluate(proposal=proposal)
                self.assertEqual(result["decision"], "HOLD")
                self.assertIn(f"{field}_mismatch", result["reasons"])

    def test_policy_scope_mismatch_holds(self):
        result = self.evaluate(policy=make_policy(owner_id="OTHER-OWNER"))
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("owner_id_mismatch", result["reasons"])

    def test_stale_router_receipt_holds(self):
        proposal = make_proposal(requested_at="2026-09-13T10:15:01Z")
        result = self.evaluate(proposal=proposal)
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("router_receipt_stale", result["reasons"])

    def test_exact_router_age_boundary_is_allowed(self):
        proposal = make_proposal(requested_at="2026-09-13T10:15:00Z")
        result = self.evaluate(proposal=proposal)
        self.assertEqual(result["decision"], "DRAFT_ALLOWED")

    def test_future_router_beyond_skew_holds(self):
        router = make_router(evaluated="2026-09-13T10:06:01Z")
        result = self.evaluate(router=router)
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("router_receipt_from_future", result["reasons"])

    def test_policy_expired_holds(self):
        result = self.evaluate(
            proposal=make_proposal(requested_at="2026-09-13T11:00:01Z")
        )
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("policy_expired", result["reasons"])

    def test_policy_exact_expiry_boundary_is_allowed(self):
        policy = make_policy(expires_at="2026-09-13T10:15:00Z")
        result = self.evaluate(
            policy=policy,
            proposal=make_proposal(requested_at="2026-09-13T10:15:00Z"),
        )
        self.assertEqual(result["decision"], "DRAFT_ALLOWED")

    def test_proposal_predates_policy_holds(self):
        policy = make_policy(issued_at="2026-09-13T10:00:30Z")
        result = self.evaluate(
            policy=policy,
            proposal=make_proposal(requested_at="2026-09-13T10:00:00Z"),
        )
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("proposal_predates_policy", result["reasons"])

    def test_policy_ttl_hard_max(self):
        policy = make_policy(
            issued_at="2026-09-01T00:00:00Z",
            expires_at="2026-09-09T00:00:01Z",
        )
        with self.assertRaises(guard.GuardError):
            self.evaluate(policy=policy)

    def test_incomplete_history_holds(self):
        result = self.evaluate(proposal=make_proposal(history_complete=False))
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("reply_history_incomplete", result["reasons"])

    def test_already_handled_event_is_idempotent_no_action(self):
        result = self.evaluate(
            proposal=make_proposal(handled_inbound_message_ids=["in-1"])
        )
        self.assertEqual(result["decision"], "NO_ACTION")
        self.assertIn("inbound_event_already_handled", result["reasons"])

    def test_unbound_message_holds(self):
        result = self.evaluate(proposal=make_proposal(inbound_message_id="in-2"))
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("inbound_message_not_bound_by_router", result["reasons"])

    def test_multiple_relevant_events_require_owner_review(self):
        router = make_router(ids=["in-1", "in-2"])
        result = self.evaluate(router=router)
        self.assertEqual(result["decision"], "OWNER_REVIEW_REQUIRED")
        self.assertIn("multiple_relevant_inbound_events", result["reasons"])

    def test_tampered_router_receipt_rejected(self):
        router = make_router()
        router["owner_id"] = "ATTACKER"
        with self.assertRaisesRegex(guard.GuardError, "receipt_sha256 mismatch"):
            self.evaluate(router=router)

    def test_router_authority_escalation_rejected(self):
        router = make_router()
        router["authority"]["reply_send_authorized"] = True
        router["receipt_sha256"] = guard._digest(
            {k: v for k, v in router.items() if k != "receipt_sha256"}
        )
        with self.assertRaisesRegex(
            guard.GuardError, "reply_send_authorized must remain false"
        ):
            self.evaluate(router=router)

    def test_router_message_digest_mismatch_rejected(self):
        router = make_router()
        router["relevant_message_ids_sha256"] = ZERO
        router["receipt_sha256"] = guard._digest(
            {k: v for k, v in router.items() if k != "receipt_sha256"}
        )
        with self.assertRaisesRegex(
            guard.GuardError, "relevant_message_ids digest mismatch"
        ):
            self.evaluate(router=router)

    def test_router_duplicate_message_ids_rejected(self):
        router = make_router(ids=["in-1", "in-1"])
        with self.assertRaisesRegex(guard.GuardError, "contains duplicates"):
            self.evaluate(router=router)

    def test_duplicate_history_ids_rejected(self):
        with self.assertRaisesRegex(guard.GuardError, "contains duplicates"):
            self.evaluate(
                proposal=make_proposal(handled_inbound_message_ids=["old", "old"])
            )

    def test_unknown_fields_fail_closed(self):
        proposal = make_proposal()
        proposal["please_send"] = True
        with self.assertRaisesRegex(guard.GuardError, "unknown fields"):
            self.evaluate(proposal=proposal)

    def test_non_lowercase_sha_rejected(self):
        with self.assertRaisesRegex(guard.GuardError, "lowercase SHA-256"):
            self.evaluate(proposal=make_proposal(body_sha256="A" * 64))

    def test_receipt_is_deterministic_and_content_bound(self):
        one = self.evaluate()
        two = self.evaluate()
        self.assertEqual(one, two)
        changed = self.evaluate(
            proposal=make_proposal(body_sha256=hashlib.sha256(b"other").hexdigest())
        )
        self.assertNotEqual(one["receipt_sha256"], changed["receipt_sha256"])
        self.assertNotEqual(one["proposal_sha256"], changed["proposal_sha256"])

    def test_receipt_never_grants_sensitive_authorities(self):
        for proposal in [make_proposal(), make_proposal(mode="PRICING")]:
            result = self.evaluate(proposal=proposal)
            authority = result["authority"]
            for key in (
                "provider_send_authorized",
                "new_thread_authorized",
                "pricing_authorized",
                "discount_authorized",
                "scope_expansion_authorized",
                "contract_authorized",
                "payment_authorized",
                "buyer_acceptance_inferred",
                "revenue_recognized",
            ):
                self.assertFalse(authority[key], key)

    def test_cli_writes_receipt_atomically(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            router_p = base / "router.json"
            policy_p = base / "policy.json"
            proposal_p = base / "proposal.json"
            out_p = base / "receipt.json"
            router_p.write_text(json.dumps(make_router()), encoding="utf-8")
            policy_p.write_text(json.dumps(make_policy()), encoding="utf-8")
            proposal_p.write_text(json.dumps(make_proposal()), encoding="utf-8")
            rc = guard.main(
                [
                    "--router-receipt",
                    str(router_p),
                    "--policy",
                    str(policy_p),
                    "--proposal",
                    str(proposal_p),
                    "--output",
                    str(out_p),
                ]
            )
            self.assertEqual(rc, 0)
            saved = json.loads(out_p.read_text(encoding="utf-8"))
            self.assertEqual(saved["decision"], "DRAFT_ALLOWED")
            self.assertEqual(saved, self.evaluate())

    def test_cli_rejects_output_alias(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            router_p = base / "router.json"
            policy_p = base / "policy.json"
            proposal_p = base / "proposal.json"
            router_p.write_text(json.dumps(make_router()), encoding="utf-8")
            policy_p.write_text(json.dumps(make_policy()), encoding="utf-8")
            proposal_p.write_text(json.dumps(make_proposal()), encoding="utf-8")
            with self.assertRaisesRegex(guard.GuardError, "output must not alias"):
                guard.main(
                    [
                        "--router-receipt",
                        str(router_p),
                        "--policy",
                        str(policy_p),
                        "--proposal",
                        str(proposal_p),
                        "--output",
                        str(policy_p),
                    ]
                )

    def test_strict_json_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "dup.json"
            path.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with self.assertRaises(guard.DuplicateKeyError):
                guard.load_json(path)


if __name__ == "__main__":
    unittest.main()
