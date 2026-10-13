from __future__ import annotations

import copy
import hashlib
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from tools.outbound_send_guard import turn_generation_lease as m


A40 = "a" * 40
C40 = "c" * 40
F40 = "f" * 40
Z64 = "0" * 64
ONE64 = "1" * 64
TWO64 = "2" * 64
THREE64 = "3" * 64


def claim(**updates):
    raw = {
        "repo": "woahwhattheheck/commons",
        "provider": "gmail",
        "account_scope": "brycembusiness2@gmail.com",
        "provider_thread_id": "1a09b4740e7731e7",
        "latest_inbound_message_id": "1a09b5b0fe3deeca",
        "send_intent_sha256": ONE64,
        "body_sha256": TWO64,
        "claimant": "ZCFJ-Q8L4 / GPT-5.6 Sol",
        "claim_id": "zcfjq8l4-20260914-a",
        "claim_started_at": "2026-09-14T23:30:00Z",
        "anchor_sha": A40,
        "preflight_sha256": THREE64,
    }
    raw.update(updates)
    return raw


def plan_for(raw=None):
    kept = []
    plan = m.prepare_acquisition(raw or claim(), retain_capability=kept.append)
    return plan, kept[0]


def receipt_for(raw=None):
    plan, cap = plan_for(raw)
    intent = m.bind_lease_commit(plan, C40)
    receipt = m.receipt_from_readback(
        intent,
        observed_branch_sha=C40,
        observed_parent_sha=A40,
        observed_metadata_json=plan["metadata_json"],
    )
    return plan, cap, intent, receipt


def complete_history(receipt, *, latest=None, sent=False, status="COMPLETE", **updates):
    kwargs = {
        "provider": receipt["provider"],
        "account_scope": receipt["account_scope"],
        "provider_thread_id": receipt["provider_thread_id"],
        "status": status,
        "latest_inbound_message_id": (
            receipt["latest_inbound_message_id"] if latest is None and status == "COMPLETE" else latest
        ),
        "provider_sent_after_bound_inbound": sent if status == "COMPLETE" else None,
        "observed_at": "2026-09-14T23:31:00Z",
    }
    kwargs.update(updates)
    return m.make_provider_history(**kwargs)


class TurnGenerationLeaseTests(unittest.TestCase):
    def test_same_generation_different_body_has_same_atomic_seam(self):
        a = claim(body_sha256=ONE64, send_intent_sha256=TWO64)
        b = claim(body_sha256=TWO64, send_intent_sha256=THREE64, claimant="Another Worker")
        self.assertEqual(m.seam_sha256(a), m.seam_sha256(b))
        self.assertEqual(m.branch_name(a), m.branch_name(b))

    def test_new_inbound_generation_gets_new_seam(self):
        a = claim(latest_inbound_message_id="msgA")
        b = claim(latest_inbound_message_id="msgB")
        self.assertNotEqual(m.seam_sha256(a), m.seam_sha256(b))
        self.assertNotEqual(m.branch_name(a), m.branch_name(b))

    def test_route_alias_cannot_be_added_to_claim(self):
        raw = claim()
        raw["recipient_route"] = "alternate@example.com"
        with self.assertRaises(m.TurnLeaseError):
            m.TurnClaim.parse(raw)

    def test_private_capability_retained_before_public_plan(self):
        plan, cap = plan_for()
        self.assertTrue(m.verify_plan(plan))
        self.assertTrue(m.public_capability_absent(plan, cap))
        self.assertEqual(m.capability_commitment(cap), plan["turn_capability_sha256"])
        self.assertFalse(plan["external_send_authorized"])

    def test_retention_failure_stops_before_plan(self):
        def fail(_):
            raise RuntimeError("vault down")
        with self.assertRaises(m.TurnLeaseError):
            m.prepare_acquisition(claim(), retain_capability=fail)

    def test_plan_tamper_rejected(self):
        plan, _ = plan_for()
        bad = copy.deepcopy(plan)
        bad["body_sha256"] = ONE64
        with self.assertRaises(m.TurnLeaseError):
            m.verify_plan(bad)

    def test_exact_readback_mints_held_receipt_not_send_authority(self):
        plan, cap, intent, receipt = receipt_for()
        self.assertTrue(m.verify_receipt(receipt))
        self.assertEqual(receipt["decision"], "LEASE_HELD")
        self.assertFalse(receipt["external_send_authorized"])
        self.assertTrue(
            m.verify_possession(
                receipt,
                turn_capability=cap,
                live_branch_sha=C40,
                live_parent_sha=A40,
                live_metadata_json=plan["metadata_json"],
            )
        )

    def test_wrong_secret_cannot_prove_possession(self):
        plan, _, _, receipt = receipt_for()
        self.assertFalse(
            m.verify_possession(
                receipt,
                turn_capability="f" * 64,
                live_branch_sha=C40,
                live_parent_sha=A40,
                live_metadata_json=plan["metadata_json"],
            )
        )

    def test_ref_drift_holds(self):
        plan, _, intent, _ = receipt_for()
        rec = m.receipt_from_readback(
            intent,
            observed_branch_sha=F40,
            observed_parent_sha=A40,
            observed_metadata_json=plan["metadata_json"],
        )
        self.assertEqual(rec["decision"], "HOLD")
        self.assertEqual(rec["reason"], "HELD_BY_OTHER_OR_REF_DRIFT")

    def test_metadata_tamper_holds(self):
        plan, _, intent, _ = receipt_for()
        rec = m.receipt_from_readback(
            intent,
            observed_branch_sha=C40,
            observed_parent_sha=A40,
            observed_metadata_json=plan["metadata_json"].replace("gmail", "other"),
        )
        self.assertEqual(rec["reason"], "METADATA_MISMATCH")

    def test_complete_unsent_same_generation_ready_for_policy_only(self):
        plan, cap, _, receipt = receipt_for()
        history = complete_history(receipt)
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=history,
        )
        self.assertTrue(m.verify_finalization(final))
        self.assertEqual(final["decision"], "TURN_READY_FOR_POLICY")
        self.assertFalse(final["external_send_authorized"])

    def test_unknown_provider_history_holds(self):
        plan, cap, _, receipt = receipt_for()
        history = complete_history(receipt, status="UNKNOWN", latest=None)
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=history,
        )
        self.assertEqual(final["decision"], "HOLD")
        self.assertEqual(final["reason"], "PROVIDER_HISTORY_UNKNOWN")

    def test_throttled_provider_history_holds(self):
        plan, cap, _, receipt = receipt_for()
        history = complete_history(receipt, status="THROTTLED", latest=None)
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=history,
        )
        self.assertEqual(final["reason"], "PROVIDER_HISTORY_THROTTLED")

    def test_generation_advance_holds(self):
        plan, cap, _, receipt = receipt_for()
        history = complete_history(receipt, latest="newInbound")
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=history,
        )
        self.assertEqual(final["reason"], "INBOUND_GENERATION_ADVANCED")

    def test_provider_send_after_bound_inbound_holds(self):
        plan, cap, _, receipt = receipt_for()
        history = complete_history(receipt, sent=True)
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=history,
        )
        self.assertEqual(final["reason"], "PROVIDER_SEND_ALREADY_EXISTS_AFTER_BOUND_INBOUND")

    def test_provider_scope_mismatch_holds(self):
        plan, cap, _, receipt = receipt_for()
        history = complete_history(receipt, provider_thread_id="otherThread")
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=history,
        )
        self.assertEqual(final["reason"], "PROVIDER_SCOPE_MISMATCH")

    def test_copied_public_winner_evidence_without_secret_holds(self):
        plan, _, _, receipt = receipt_for()
        history = complete_history(receipt)
        final = m.finalize_turn(
            receipt,
            turn_capability="e" * 64,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=history,
        )
        self.assertEqual(final["reason"], "CURRENT_WORKER_POSSESSION_UNPROVEN")

    def test_history_digest_tamper_rejected(self):
        _, _, _, receipt = receipt_for()
        history = complete_history(receipt)
        history["provider_sent_after_bound_inbound"] = True
        with self.assertRaises(m.TurnLeaseError):
            m.ProviderHistory.parse(history)

    def test_incomplete_history_cannot_assert_facts(self):
        with self.assertRaises(m.TurnLeaseError):
            m.make_provider_history(
                provider="gmail",
                account_scope="brycembusiness2@gmail.com",
                provider_thread_id="thread1",
                status="UNKNOWN",
                latest_inbound_message_id="msg1",
                provider_sent_after_bound_inbound=False,
                observed_at="2026-09-14T23:31:00Z",
            )

    def test_finalization_tamper_rejected(self):
        plan, cap, _, receipt = receipt_for()
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=complete_history(receipt),
        )
        final["external_send_authorized"] = True
        with self.assertRaises(m.TurnLeaseError):
            m.verify_finalization(final)

    def test_provider_result_binds_ready_finalization_without_granting_authority(self):
        plan, cap, _, receipt = receipt_for()
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=complete_history(receipt),
        )
        result = m.record_provider_result(
            final,
            status="SENT",
            provider_message_id="1a0a1234abcd",
            observed_at="2026-09-14T23:32:00Z",
        )
        self.assertTrue(m.verify_provider_result(result))
        self.assertFalse(result["external_send_authorized"])

    def test_cannot_attach_provider_result_to_hold(self):
        plan, cap, _, receipt = receipt_for()
        final = m.finalize_turn(
            receipt,
            turn_capability=cap,
            live_branch_sha=C40,
            live_parent_sha=A40,
            live_metadata_json=plan["metadata_json"],
            provider_history=complete_history(receipt, sent=True),
        )
        with self.assertRaises(m.TurnLeaseError):
            m.record_provider_result(
                final,
                status="SENT",
                provider_message_id="msg2",
                observed_at="2026-09-14T23:32:00Z",
            )

    def test_same_generation_64_worker_race_has_one_ref_winner(self):
        # The Git provider operation used by the connector is create-exclusive.
        # This memory model exercises the deterministic-ref property under race:
        # all 64 contenders target exactly one ref; only first create succeeds.
        lock = threading.Lock()
        refs = set()
        won = []

        def worker(i):
            raw = claim(
                claimant=f"Worker {i:02d}",
                claim_id=f"worker-{i:02d}",
                body_sha256=hashlib.sha256(f"body-{i}".encode()).hexdigest(),
                send_intent_sha256=hashlib.sha256(f"intent-{i}".encode()).hexdigest(),
            )
            ref = m.lease_ref(raw)
            with lock:
                if ref in refs:
                    won.append(False)
                else:
                    refs.add(ref)
                    won.append(True)

        with ThreadPoolExecutor(max_workers=32) as pool:
            list(pool.map(worker, range(64)))
        self.assertEqual(sum(won), 1)
        self.assertEqual(len(refs), 1)

    def test_different_generations_can_each_have_one_winner(self):
        refs = {m.lease_ref(claim(latest_inbound_message_id=f"msg{i}")) for i in range(4)}
        self.assertEqual(len(refs), 4)

    def test_claim_rejects_noncanonical_account_scope(self):
        with self.assertRaises(m.TurnLeaseError):
            m.TurnClaim.parse(claim(account_scope="Bryce@Example.COM"))

    def test_canonicalizes_history_timestamp(self):
        _, _, _, receipt = receipt_for()
        h = m.make_provider_history(
            provider=receipt["provider"],
            account_scope=receipt["account_scope"],
            provider_thread_id=receipt["provider_thread_id"],
            status="COMPLETE",
            latest_inbound_message_id=receipt["latest_inbound_message_id"],
            provider_sent_after_bound_inbound=False,
            observed_at="2026-09-14T19:31:00-04:00",
        )
        self.assertEqual(h["observed_at"], "2026-09-14T23:31:00Z")
        self.assertTrue(m.ProviderHistory.parse(h))


if __name__ == "__main__":
    unittest.main()
