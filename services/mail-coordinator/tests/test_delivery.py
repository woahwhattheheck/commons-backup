from __future__ import annotations

import concurrent.futures

from mail_coordinator import ConflictError
from common import CoordinatorTestBase


class DeliveryStateTest(CoordinatorTestBase):
    def test_only_provider_receipt_marks_sent(self) -> None:
        inbound = self.inbound("a", 900)
        self.coordinator.enqueue(self.request("enqueue-a", message_id="message-a", inbound=inbound, received_at=900))
        claim = self.coordinator.claim(operation_id="claim-a", message_id="message-a", worker_id="worker-a")
        self.coordinator.begin_attempt(operation_id="attempt-a", claim_id=claim.claim_id, attempt_id="attempt-a")
        self.coordinator.mark_uncertain(operation_id="uncertain-a", attempt_id="attempt-a", detail="provider timeout")
        self.assertEqual(self.coordinator.status("message-a")["state"], "UNCERTAIN")
        receipt = self.coordinator.record_provider_receipt(
            operation_id="receipt-a",
            attempt_id="attempt-a",
            provider_message_id="provider-123",
            accepted_at=1_010,
        )
        self.assertEqual(receipt["status"], "SENT")
        status = self.coordinator.status("message-a")
        self.assertEqual(status["state"], "SENT")
        self.assertEqual(status["provider_message_id"], "provider-123")

    def test_uncertain_not_sent_reconciliation_requeues_same_message(self) -> None:
        inbound = self.inbound("a", 900)
        self.coordinator.enqueue(self.request("enqueue-a", message_id="message-a", inbound=inbound, received_at=900))
        claim = self.coordinator.claim(operation_id="claim-a", message_id="message-a", worker_id="worker-a")
        self.coordinator.begin_attempt(operation_id="attempt-a", claim_id=claim.claim_id, attempt_id="attempt-a")
        self.coordinator.mark_uncertain(operation_id="uncertain-a", attempt_id="attempt-a", detail="network reset")
        result = self.coordinator.reconcile_not_sent(
            operation_id="reconcile-a",
            attempt_id="attempt-a",
            evidence_ref="provider sent-folder check 2026-09-14T02:30Z",
        )
        self.assertEqual(result["status"], "QUEUED")
        next_claim = self.coordinator.claim(operation_id="claim-b", message_id="message-a", worker_id="worker-b")
        self.assertNotEqual(next_claim.claim_id, claim.claim_id)

    def test_expired_claim_can_be_recovered_before_attempt(self) -> None:
        inbound = self.inbound("a", 900)
        self.coordinator.enqueue(self.request("enqueue-a", message_id="message-a", inbound=inbound, received_at=900))
        first = self.coordinator.claim(operation_id="claim-a", message_id="message-a", worker_id="worker-a", lease_seconds=10)
        self.clock.advance(11)
        second = self.coordinator.claim(operation_id="claim-b", message_id="message-a", worker_id="worker-b")
        self.assertNotEqual(first.claim_id, second.claim_id)
        self.assertEqual(self.coordinator.status("message-a")["claims"][0]["state"], "EXPIRED")

    def test_suppression_invalidates_waiting_messages_but_flags_attempts(self) -> None:
        inbound = self.inbound("a", 900)
        self.coordinator.enqueue(self.request("enqueue-a", message_id="message-a", inbound=inbound, received_at=900))
        result = self.coordinator.suppress(
            operation_id="suppress-a",
            address="lead@example.com",
            reason="recipient declined",
            evidence_ref="gmail:incoming-a",
        )
        self.assertEqual(result["suppressed"], ["message-a"])
        self.assertEqual(self.coordinator.status("message-a")["state"], "SUPPRESSED")
        blocked = self.coordinator.enqueue(
            self.request(
                "enqueue-b",
                message_id="message-b",
                conversation=None,
                inbound=None,
                received_at=None,
                subject="New topic",
            )
        )
        self.assertEqual(blocked.status, "SUPPRESSED")

    def test_status_redacts_body_by_default(self) -> None:
        inbound = self.inbound("a", 900)
        self.coordinator.enqueue(self.request("enqueue-a", body="private body", message_id="message-a", inbound=inbound, received_at=900))
        self.assertNotIn("body", self.coordinator.status("message-a"))
        self.assertEqual(self.coordinator.status("message-a", include_body=True)["body"], "private body")
