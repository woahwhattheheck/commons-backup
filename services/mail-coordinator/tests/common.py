from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mail_coordinator import Envelope, MailCoordinator, QueueRequest


class Clock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class CoordinatorTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "coordination.sqlite3"
        self.clock = Clock()
        self.coordinator = MailCoordinator(self.database, clock=self.clock)
        self.coordinator.initialize()

    def inbound(self, suffix: str, received_at: float) -> str:
        provider_id = f"incoming-{suffix}"
        self.coordinator.record_inbound(
            operation_id=f"record-{suffix}",
            mailbox="sales@example.com",
            conversation_key="lead-42",
            provider_message_id=provider_id,
            received_at=received_at,
        )
        return provider_id

    def request(
        self,
        operation: str,
        *,
        body: str = "Hello",
        message_id: str | None = None,
        recipient: str = "lead@example.com",
        subject: str = "Re: Pilot",
        inbound: str | None = None,
        received_at: float | None = None,
        conversation: str | None = "lead-42",
    ) -> QueueRequest:
        return QueueRequest(
            operation_id=operation,
            message_id=message_id,
            mailbox="sales@example.com",
            envelope=Envelope(
                sender="sales@example.com",
                to=(recipient,),
                subject=subject,
                body=body,
            ),
            conversation_key=conversation,
            inbound_message_id=inbound,
            inbound_received_at=received_at,
        )
