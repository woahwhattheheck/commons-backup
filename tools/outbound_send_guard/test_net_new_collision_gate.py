from __future__ import annotations

import unittest

from . import net_new_collision_gate as gate

CAP = "11" * 32
BRANCH = "a" * 40
PARENT = "b" * 40
META = '{"lease":"exact"}\n'


def buyer_receipt(*, decision="ALLOW_NEW", authority="complete", scope="buyer-123", offer="pilot-001"):
    core = {
        "schema_version": "outbound-send-guard-receipt/v1",
        "intent": {"intent_id": "i-1", "recipient": "buyer@example.com", "offer_id": offer, "requested_at": "2026-09-14T23:00:00Z", "route_kind": "email"},
        "evidence": {}, "policy": {}, "decision": decision, "authority": authority,
        "reasons": [], "latest_outbound_at": None, "latest_inbound_at": None,
        "reply_message_id": None, "side_effects_authorized": False,
    }
    payload = {
        "schema_version": gate.BUYER_RECEIPT_SCHEMA,
        "buyer_scope": {"scope_id": scope, "members": [{
            "email": "buyer@example.com",
            "mailbox_complete": True, "mailbox_query_id": "gmail-sweep",
            "slack_complete": True, "slack_query_id": "slack-sweep",
        }]},
        "source": {},
        "core_receipt_sha256": gate._digest(core),
        "core": core,
        "decision": decision,
        "authority": authority,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": gate._digest(payload)}


def lease_receipt(preflight: str, *, recipient="buyer@example.com", offer="pilot-001", held=True, lease_scope=None, lease_offer=None):
    lease_scope = lease_scope or gate._lease_scope_token("email", recipient)
    lease_offer = lease_offer or gate._lease_scope_token("offer", offer)
    raw = {
        "schema": gate.LEASE_RECEIPT_SCHEMA,
        "repo": "woahwhattheheck/commons", "buyer_scope": lease_scope, "offer_scope": lease_offer,
        "seam_sha256": "2" * 64, "lease_ref": "refs/heads/outbound-lease-v3/x",
        "branch_name": "outbound-lease-v3/x", "metadata_path": ".tjlabs/x.json",
        "claimant": "Z-Worker", "claim_id": "claim-1", "claim_started_at": "2026-09-14T23:00:01Z",
        "anchor_sha": PARENT, "preflight_sha256": preflight,
        "claim_capability_sha256": "3" * 64, "metadata_sha256": "4" * 64,
        "plan_sha256": "5" * 64, "intent_sha256": "6" * 64,
        "lease_commit_sha": BRANCH, "observed_branch_sha": BRANCH if held else "c" * 40,
        "observed_parent_sha": PARENT, "lease_held_by_claimant": held,
        "decision": "LEASE_HELD" if held else "HOLD", "reason": "test",
        "external_send_authorized": False,
    }
    raw["receipt_sha256"] = gate._digest(raw)
    return raw


def public_ok(_):
    return True


def possession_ok(_, *, claim_capability, live_branch_sha, live_parent_sha, live_metadata_json):
    return claim_capability == CAP and live_branch_sha == BRANCH and live_parent_sha == PARENT and live_metadata_json == META


class GateTests(unittest.TestCase):
    def evaluate(self, buyer=None, lease=None, cap=CAP, **kw):
        buyer = buyer or buyer_receipt()
        lease = lease or lease_receipt(buyer["receipt_sha256"])
        return gate.evaluate(
            buyer, lease, claim_capability=cap,
            live_branch_sha=kw.get("branch", BRANCH), live_parent_sha=kw.get("parent", PARENT),
            live_metadata_json=kw.get("metadata", META), receipt_verifier=public_ok,
            possession_verifier=possession_ok,
        )

    def test_exact_bound_holder_is_collision_clear_but_not_send_authority(self):
        result = self.evaluate()
        self.assertEqual(result["payload"]["decision"], "COLLISION_CLEAR")
        self.assertTrue(result["payload"]["collision_gate_passed"])
        self.assertTrue(result["payload"]["live_possession_proven"])
        self.assertIs(result["payload"]["external_send_authorized"], False)
        self.assertNotIn(CAP, str(result))
        self.assertEqual(result["receipt_sha256"], gate._digest(result["payload"]))

    def test_same_recipient_cannot_escape_collision_by_renaming_buyer_scope(self):
        buyer = buyer_receipt(scope="arbitrary-local-name")
        lease = lease_receipt(
            buyer["receipt_sha256"],
            lease_scope=gate._lease_scope_token("email", "other@example.com"),
        )
        result = self.evaluate(buyer, lease)
        self.assertEqual(result["payload"]["decision"], "HOLD")
        self.assertIn("RECIPIENT_LEASE_SCOPE_BINDING_MISMATCH", result["payload"]["reasons"])

    def test_green_artifacts_from_different_offer_are_not_composable(self):
        buyer = buyer_receipt(offer="offer-A")
        lease = lease_receipt(
            buyer["receipt_sha256"],
            offer="offer-A",
            lease_offer=gate._lease_scope_token("offer", "offer-B"),
        )
        result = self.evaluate(buyer, lease)
        self.assertIn("OFFER_LEASE_SCOPE_BINDING_MISMATCH", result["payload"]["reasons"])

    def test_lease_tokens_are_canonical_machine_tokens_not_caller_names(self):
        buyer = buyer_receipt(scope="Buyer Name With Spaces", offer="Pilot / 001")
        lease = lease_receipt(buyer["receipt_sha256"], offer="Pilot / 001")
        result = self.evaluate(buyer, lease)
        self.assertEqual(result["payload"]["decision"], "COLLISION_CLEAR")
        self.assertRegex(result["payload"]["lease_buyer_scope"], r"^email-[0-9a-f]{64}$")
        self.assertRegex(result["payload"]["lease_offer_scope"], r"^offer-[0-9a-f]{64}$")

    def test_lease_must_bind_exact_preflight_receipt_generation(self):
        buyer = buyer_receipt()
        lease = lease_receipt("9" * 64)
        result = self.evaluate(buyer, lease)
        self.assertIn("PREFLIGHT_DIGEST_BINDING_MISMATCH", result["payload"]["reasons"])

    def test_non_allow_new_preflight_holds_before_possession(self):
        buyer = buyer_receipt(decision="DO_NOT_RESEND")
        lease = lease_receipt(buyer["receipt_sha256"])
        called = []
        def should_not_run(*args, **kwargs):
            called.append(1)
            return True
        result = gate.evaluate(
            buyer, lease, claim_capability=CAP, live_branch_sha=BRANCH,
            live_parent_sha=PARENT, live_metadata_json=META,
            receipt_verifier=public_ok, possession_verifier=should_not_run,
        )
        self.assertIn("BUYER_PREFLIGHT_NOT_ALLOW_NEW", result["payload"]["reasons"])
        self.assertEqual(called, [])

    def test_partial_authority_holds(self):
        buyer = buyer_receipt(decision="HOLD", authority="partial")
        lease = lease_receipt(buyer["receipt_sha256"])
        result = self.evaluate(buyer, lease)
        self.assertIn("BUYER_PREFLIGHT_AUTHORITY_NOT_COMPLETE", result["payload"]["reasons"])

    def test_public_lease_without_held_state_holds(self):
        buyer = buyer_receipt()
        lease = lease_receipt(buyer["receipt_sha256"], held=False)
        result = self.evaluate(buyer, lease)
        self.assertIn("LEASE_NOT_HELD", result["payload"]["reasons"])

    def test_copied_public_winner_with_wrong_private_capability_holds(self):
        result = self.evaluate(cap="22" * 32)
        self.assertEqual(result["payload"]["decision"], "HOLD")
        self.assertIn("LIVE_LEASE_POSSESSION_NOT_PROVEN", result["payload"]["reasons"])

    def test_fresh_provider_readback_is_required(self):
        result = self.evaluate(branch="c" * 40)
        self.assertIn("LIVE_LEASE_POSSESSION_NOT_PROVEN", result["payload"]["reasons"])

    def test_tampered_buyer_receipt_digest_is_invalid_not_hold(self):
        buyer = buyer_receipt()
        buyer["payload"]["authority"] = "partial"
        lease = lease_receipt(buyer["receipt_sha256"])
        with self.assertRaisesRegex(gate.CollisionGateError, "digest mismatch"):
            self.evaluate(buyer, lease)

    def test_tampered_embedded_core_is_invalid(self):
        buyer = buyer_receipt()
        buyer["payload"]["core"]["intent"]["offer_id"] = "other"
        buyer["receipt_sha256"] = gate._digest(buyer["payload"])
        lease = lease_receipt(buyer["receipt_sha256"])
        with self.assertRaisesRegex(gate.CollisionGateError, "embedded core digest mismatch"):
            self.evaluate(buyer, lease)

    def test_unknown_outer_buyer_field_is_invalid(self):
        buyer = buyer_receipt()
        buyer["extra"] = 1
        lease = lease_receipt(buyer["receipt_sha256"])
        with self.assertRaisesRegex(gate.CollisionGateError, "exact fields"):
            self.evaluate(buyer, lease)

    def test_lease_public_verifier_failure_is_invalid(self):
        buyer = buyer_receipt()
        lease = lease_receipt(buyer["receipt_sha256"])
        with self.assertRaisesRegex(gate.CollisionGateError, "verifier rejected"):
            gate.evaluate(
                buyer, lease, claim_capability=CAP, live_branch_sha=BRANCH,
                live_parent_sha=PARENT, live_metadata_json=META,
                receipt_verifier=lambda _: False, possession_verifier=possession_ok,
            )

    def test_core_recipient_must_be_declared_buyer_member(self):
        buyer = buyer_receipt()
        buyer["payload"]["buyer_scope"]["members"][0]["email"] = "other@example.com"
        buyer["receipt_sha256"] = gate._digest(buyer["payload"])
        lease = lease_receipt(buyer["receipt_sha256"])
        with self.assertRaisesRegex(gate.CollisionGateError, "not a declared buyer-scope member"):
            self.evaluate(buyer, lease)

    def test_default_verifiers_accept_real_v3_receipt_and_possession(self):
        try:
            from . import connector_capability_lease as v3
        except ImportError:
            self.skipTest("real v3 module unavailable in isolated local fixture")
        buyer = buyer_receipt(scope="arbitrary-local-name", offer="Pilot / 001")
        retained = []
        claim = {
            "repo": "woahwhattheheck/commons",
            "buyer_scope": gate._lease_scope_token("email", "buyer@example.com"),
            "offer_scope": gate._lease_scope_token("offer", "Pilot / 001"),
            "claimant": "Z-Worker", "claim_id": "claim-001",
            "claim_started_at": "2026-09-14T23:00:01Z",
            "anchor_sha": PARENT, "preflight_sha256": buyer["receipt_sha256"],
        }
        plan = v3.prepare_acquisition(claim, retain_capability=retained.append)
        intent = v3.bind_lease_commit(plan, BRANCH)
        receipt = v3.receipt_from_readback(
            intent, observed_branch_sha=BRANCH, observed_parent_sha=PARENT,
            observed_metadata_json=plan["metadata_json"],
        )
        result = gate.evaluate(
            buyer, receipt, claim_capability=retained[0],
            live_branch_sha=BRANCH, live_parent_sha=PARENT,
            live_metadata_json=plan["metadata_json"],
        )
        self.assertEqual(result["payload"]["decision"], "COLLISION_CLEAR")
        self.assertTrue(result["payload"]["live_possession_proven"])
        self.assertNotIn(retained[0], str(result))

    def test_output_is_deterministic_for_same_bound_evidence(self):
        self.assertEqual(self.evaluate(), self.evaluate())

    def test_strict_parser_rejects_duplicate_and_nonfinite_json(self):
        with self.assertRaises(gate.CollisionGateError):
            gate.parse_json_bytes(b'{"a":1,"a":2}', "x")
        with self.assertRaises(gate.CollisionGateError):
            gate.parse_json_bytes(b'{"a":NaN}', "x")


if __name__ == "__main__":
    unittest.main()
