from __future__ import annotations

import concurrent.futures

from mail_coordinator import ConflictError, MailCoordinator
from common import CoordinatorTestBase


class QueueAndInboundTest(CoordinatorTestBase):
    def test_operation_id_is_idempotent_and_content_bound(self) -> None:
        inbound = self.inbound("a", 900)
        request = self.request("enqueue-a", message_id="message-a", inbound=inbound, received_at=900)
        first = self.coordinator.enqueue(request)
        second = self.coordinator.enqueue(request)
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ConflictError, "different input"):
            self.coordinator.enqueue(self.request("enqueue-a", body="changed", message_id="message-a", inbound=inbound, received_at=900))

    def test_concurrent_workers_cannot_queue_duplicate_response(self) -> None:
        inbound = self.inbound("race", 900)
        barrier = __import__("threading").Barrier(2)

        def enqueue(index: int):
            coordinator = MailCoordinator(self.database, clock=self.clock)
            barrier.wait()
            return coordinator.enqueue(
                self.request(
                    f"race-{index}",
                    body=f"candidate {index}",
                    message_id=f"race-message-{index}",
                    inbound=inbound,
                    received_at=900,
                )
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(enqueue, (1, 2)))
        self.assertEqual(sorted(result.status for result in results), ["DUPLICATE", "QUEUED"])
        queued = {result.message_id for result in results if result.status == "QUEUED"}
        duplicate = next(result for result in results if result.status == "DUPLICATE")
        self.assertEqual(set(duplicate.conflicts), queued)

    def test_newer_inbound_invalidates_unsent_claim(self) -> None:
        inbound = self.inbound("old", 900)
        queued = self.coordinator.enqueue(self.request("enqueue-old", message_id="old", inbound=inbound, received_at=900))
        claim = self.coordinator.claim(operation_id="claim-old", message_id=queued.message_id, worker_id="worker-a")
        result = self.coordinator.record_inbound(
            operation_id="record-new",
            mailbox="sales@example.com",
            conversation_key="lead-42",
            provider_message_id="incoming-new",
            received_at=950,
        )
        self.assertEqual(result["invalidated"], ["old"])
        self.assertEqual(result["unresolved"], [])
        status = self.coordinator.status("old")
        self.assertEqual(status["state"], "INVALIDATED")
        self.assertEqual(status["claims"][0]["state"], "RELEASED")
        self.assertEqual(status["claims"][0]["claim_id"], claim.claim_id)

    def test_newer_inbound_never_hides_in_flight_uncertainty(self) -> None:
        inbound = self.inbound("old", 900)
        self.coordinator.enqueue(self.request("enqueue-old", message_id="old", inbound=inbound, received_at=900))
        claim = self.coordinator.claim(operation_id="claim-old", message_id="old", worker_id="worker-a")
        attempt = self.coordinator.begin_attempt(operation_id="attempt-old", claim_id=claim.claim_id, attempt_id="attempt-1")
        result = self.coordinator.record_inbound(
            operation_id="record-new",
            mailbox="sales@example.com",
            conversation_key="lead-42",
            provider_message_id="incoming-new",
            received_at=950,
        )
        self.assertEqual(result["invalidated"], [])
        self.assertEqual(result["unresolved"], ["old"])
        with self.assertRaisesRegex(ConflictError, "reconciled"):
            self.coordinator.enqueue(self.request("enqueue-new", message_id="new", inbound="incoming-new", received_at=950))
        self.assertEqual(attempt["status"], "ATTEMPTING")

    def test_cold_subject_normalization_catches_parallel_outreach(self) -> None:
        first = self.coordinator.enqueue(
            self.request("cold-a", message_id="cold-a", conversation=None, inbound=None, received_at=None, subject="Pilot proposal")
        )
        second = self.coordinator.enqueue(
            self.request("cold-b", message_id="cold-b", conversation=None, inbound=None, received_at=None, subject="Re:  Pilot   proposal")
        )
        self.assertEqual(first.status, "QUEUED")
        self.assertEqual(second.status, "DUPLICATE")
