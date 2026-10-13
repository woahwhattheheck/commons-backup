from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

from .models import (
    ACTIVE_STATES, Claim, ConflictError, CoordinationError, Envelope,
    NotFoundError, QueueRequest, QueueResult, ValidationError, body_digest,
    canonical_hash, normalize_address, normalize_key, normalize_subject,
    stable_identifier, utc_now, _require_text,
)


class ClaimMixin:
    def claim(
        self,
        *,
        operation_id: str,
        message_id: str,
        worker_id: str,
        lease_seconds: float = 120.0,
        claim_id: str | None = None,
    ) -> Claim:
        operation_id = _require_text("operation_id", operation_id)
        message_id = _require_text("message_id", message_id)
        worker_id = _require_text("worker_id", worker_id)
        lease_seconds = float(lease_seconds)
        if lease_seconds <= 0 or lease_seconds > 3600:
            raise ValidationError("lease_seconds must be in (0, 3600]")
        at = float(self.clock())
        claim_id = claim_id or stable_identifier("claim", operation_id)
        claim_id = _require_text("claim_id", claim_id)
        request = {"message_id": message_id, "worker_id": worker_id, "lease_seconds": lease_seconds, "claim_id": claim_id}
        request_hash = canonical_hash(request)
        with self._write() as connection:
            prior = self._operation_read(connection, operation_id, "claim", request_hash)
            if prior is not None:
                return self._claim_from_result(prior)
            existing_claim = connection.execute("SELECT message_id FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
            if existing_claim is not None:
                raise ConflictError(
                    "claim_id was already used",
                    code="CLAIM_ID_REUSE",
                    details={"claim_id": claim_id, "message_id": existing_claim["message_id"]},
                )
            message = connection.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone()
            if message is None:
                raise NotFoundError("message not found", details={"message_id": message_id})

            current_claim = None
            if message["current_claim_id"]:
                current_claim = connection.execute(
                    "SELECT * FROM claims WHERE claim_id=?", (message["current_claim_id"],)
                ).fetchone()
            if current_claim is not None and current_claim["state"] == "CLAIMED":
                if float(current_claim["lease_until"]) > at:
                    raise ConflictError(
                        "message is already claimed",
                        code="ALREADY_CLAIMED",
                        details={"claim_id": current_claim["claim_id"], "lease_until": current_claim["lease_until"]},
                    )
                connection.execute(
                    "UPDATE claims SET state='EXPIRED',released_at=? WHERE claim_id=?",
                    (at, current_claim["claim_id"]),
                )
                connection.execute(
                    "UPDATE messages SET state='QUEUED',current_claim_id=NULL,updated_at=? WHERE message_id=? AND state='CLAIMED'",
                    (at, message_id),
                )
                message = connection.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone()
                self._event(connection, "CLAIM_EXPIRED", now=at, message_id=message_id, data={"claim_id": current_claim["claim_id"]})

            if message["state"] != "QUEUED":
                raise ConflictError(
                    f"message is not claimable in state {message['state']}",
                    code="NOT_CLAIMABLE",
                    details={"state": message["state"]},
                )
            suppressed = connection.execute(
                "SELECT s.address FROM suppressions s JOIN message_recipients r ON r.address=s.address WHERE r.message_id=? LIMIT 1",
                (message_id,),
            ).fetchone()
            if suppressed is not None:
                connection.execute(
                    "UPDATE messages SET state='SUPPRESSED',state_reason=?,updated_at=? WHERE message_id=?",
                    (f"suppressed recipient: {suppressed['address']}", at, message_id),
                )
                raise ConflictError("recipient is suppressed", code="SUPPRESSED", details={"address": suppressed["address"]})

            lease_until = at + lease_seconds
            connection.execute(
                "INSERT INTO claims(claim_id,message_id,worker_id,state,claimed_at,lease_until) VALUES(?,?,?,?,?,?)",
                (claim_id, message_id, worker_id, "CLAIMED", at, lease_until),
            )
            connection.execute(
                "UPDATE messages SET state='CLAIMED',current_claim_id=?,updated_at=? WHERE message_id=?",
                (claim_id, at, message_id),
            )
            result = self._claim_result(connection, message_id, claim_id, worker_id, lease_until)
            self._operation_write(connection, operation_id, "claim", request_hash, result, at)
            self._event(connection, "MESSAGE_CLAIMED", now=at, message_id=message_id, data={"claim_id": claim_id, "worker_id": worker_id, "lease_until": lease_until})
            return self._claim_from_result(result)

    @staticmethod
    def _claim_result(
        connection: sqlite3.Connection,
        message_id: str,
        claim_id: str,
        worker_id: str,
        lease_until: float,
    ) -> dict[str, Any]:
        message = connection.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone()
        recipients = connection.execute(
            "SELECT address,kind,ordinal FROM message_recipients WHERE message_id=? ORDER BY kind,ordinal",
            (message_id,),
        ).fetchall()
        grouped: dict[str, list[str]] = {"to": [], "cc": [], "bcc": []}
        for recipient in recipients:
            grouped[recipient["kind"]].append(recipient["address"])
        return {
            "claim_id": claim_id,
            "message_id": message_id,
            "worker_id": worker_id,
            "lease_until": lease_until,
            "body_sha256": message["body_sha256"],
            "envelope": {
                "sender": message["sender"],
                "to": grouped["to"],
                "cc": grouped["cc"],
                "bcc": grouped["bcc"],
                "subject": message["subject"],
                "body": message["body"],
            },
        }

    @staticmethod
    def _claim_from_result(result: dict[str, Any]) -> Claim:
        envelope = result["envelope"]
        return Claim(
            claim_id=result["claim_id"],
            message_id=result["message_id"],
            worker_id=result["worker_id"],
            lease_until=float(result["lease_until"]),
            body_sha256=result["body_sha256"],
            envelope=Envelope(
                sender=envelope["sender"],
                to=tuple(envelope["to"]),
                cc=tuple(envelope["cc"]),
                bcc=tuple(envelope["bcc"]),
                subject=envelope["subject"],
                body=envelope["body"],
            ),
        )
