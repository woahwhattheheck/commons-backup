from __future__ import annotations

import concurrent.futures

from mail_coordinator import ConflictError
from common import CoordinatorTestBase


class ReconciliationTest(CoordinatorTestBase):
    def test_generated_identifiers_are_retry_stable(self) -> None:
        inbound = self.inbound("stable", 900)
        request = self.request("stable-enqueue", inbound=inbound, received_at=900)
        first = self.coordinator.enqueue(request)
        second = self.coordinator.enqueue(request)
        self.assertEqual(first.message_id, second.message_id)
        first_claim = self.coordinator.claim(
            operation_id="stable-claim", message_id=first.message_id, worker_id="worker"
        )
        second_claim = self.coordinator.claim(
            operation_id="stable-claim", message_id=first.message_id, worker_id="worker"
        )
        self.assertEqual(first_claim.claim_id, second_claim.claim_id)
        first_attempt = self.coordinator.begin_attempt(
            operation_id="stable-attempt", claim_id=first_claim.claim_id
        )
        second_attempt = self.coordinator.begin_attempt(
            operation_id="stable-attempt", claim_id=first_claim.claim_id
        )
        self.assertEqual(first_attempt["attempt_id"], second_attempt["attempt_id"])

    def test_reconcile_not_sent_respects_newer_inbound(self) -> None:
        inbound = self.inbound("old", 900)
        self.coordinator.enqueue(self.request("enqueue-old", message_id="old", inbound=inbound, received_at=900))
        claim = self.coordinator.claim(operation_id="claim-old", message_id="old", worker_id="worker")
        self.coordinator.begin_attempt(operation_id="attempt-old", claim_id=claim.claim_id, attempt_id="attempt-old")
        self.coordinator.mark_uncertain(operation_id="uncertain-old", attempt_id="attempt-old", detail="timeout")
        self.coordinator.record_inbound(
            operation_id="new-inbound",
            mailbox="sales@example.com",
            conversation_key="lead-42",
            provider_message_id="incoming-new",
            received_at=950,
        )
        result = self.coordinator.reconcile_not_sent(
            operation_id="reconcile-old", attempt_id="attempt-old", evidence_ref="sent-folder empty"
        )
        self.assertEqual(result["status"], "INVALIDATED")
        self.assertEqual(self.coordinator.status("old")["state"], "INVALIDATED")

    def test_reconcile_not_sent_respects_suppression(self) -> None:
        inbound = self.inbound("suppress", 900)
        self.coordinator.enqueue(self.request("enqueue-suppress", message_id="suppressed-attempt", inbound=inbound, received_at=900))
        claim = self.coordinator.claim(operation_id="claim-suppress", message_id="suppressed-attempt", worker_id="worker")
        self.coordinator.begin_attempt(operation_id="attempt-suppress", claim_id=claim.claim_id, attempt_id="attempt-suppress")
        self.coordinator.mark_uncertain(operation_id="uncertain-suppress", attempt_id="attempt-suppress", detail="timeout")
        suppression = self.coordinator.suppress(
            operation_id="suppress-contact",
            address="lead@example.com",
            reason="declined",
            evidence_ref="incoming:suppress",
        )
        self.assertEqual(suppression["unresolved"], ["suppressed-attempt"])
        result = self.coordinator.reconcile_not_sent(
            operation_id="reconcile-suppress", attempt_id="attempt-suppress", evidence_ref="sent-folder empty"
        )
        self.assertEqual(result["status"], "SUPPRESSED")

    def test_provider_receipt_cannot_be_reused_across_messages(self) -> None:
        first_inbound = self.inbound("receipt-a", 900)
        self.coordinator.enqueue(self.request("queue-receipt-a", message_id="receipt-a", inbound=first_inbound, received_at=900))
        first_claim = self.coordinator.claim(operation_id="claim-receipt-a", message_id="receipt-a", worker_id="worker")
        self.coordinator.begin_attempt(operation_id="attempt-receipt-a", claim_id=first_claim.claim_id, attempt_id="attempt-receipt-a")
        self.coordinator.record_provider_receipt(
            operation_id="provider-receipt-a",
            attempt_id="attempt-receipt-a",
            provider_message_id="provider-shared",
            accepted_at=1_010,
        )

        self.clock.advance(200)
        second = self.coordinator.enqueue(
            self.request(
                "queue-receipt-b",
                message_id="receipt-b",
                recipient="other@example.com",
                conversation=None,
                inbound=None,
                received_at=None,
                subject="Another lead",
            )
        )
        second_claim = self.coordinator.claim(operation_id="claim-receipt-b", message_id=second.message_id, worker_id="worker")
        self.coordinator.begin_attempt(operation_id="attempt-receipt-b", claim_id=second_claim.claim_id, attempt_id="attempt-receipt-b")
        with self.assertRaisesRegex(ConflictError, "another attempt"):
            self.coordinator.record_provider_receipt(
                operation_id="record-receipt-b",
                attempt_id="attempt-receipt-b",
                provider_message_id="provider-shared",
                accepted_at=1_210,
            )
