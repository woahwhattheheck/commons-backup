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


class QueueMixin:
    def enqueue(self, request: QueueRequest) -> QueueResult:
        operation_id = _require_text("operation_id", request.operation_id)
        mailbox = normalize_address(request.mailbox)
        envelope = self._normalize_envelope(request.envelope)
        conversation_key = normalize_key("conversation_key", request.conversation_key)
        inbound_message_id = normalize_key("inbound_message_id", request.inbound_message_id)
        if inbound_message_id is not None and conversation_key is None:
            raise ValidationError("conversation_key is required with inbound_message_id")
        inbound_received_at = None if request.inbound_received_at is None else float(request.inbound_received_at)
        if inbound_received_at is not None and inbound_received_at < 0:
            raise ValidationError("inbound_received_at must be non-negative")
        if inbound_message_id is not None and inbound_received_at is None:
            raise ValidationError("inbound_received_at is required with inbound_message_id")
        if inbound_message_id is None and inbound_received_at is not None:
            raise ValidationError("inbound_message_id is required with inbound_received_at")
        at = float(self.clock())
        message_id = request.message_id or stable_identifier("message", operation_id)
        message_id = _require_text("message_id", message_id)
        normalized_subject = normalize_subject(envelope.subject)
        input_value = {
            "message_id": message_id,
            "mailbox": mailbox,
            "sender": envelope.sender,
            "to": envelope.to,
            "cc": envelope.cc,
            "bcc": envelope.bcc,
            "subject": envelope.subject,
            "body_sha256": body_digest(envelope.body),
            "conversation_key": conversation_key,
            "inbound_message_id": inbound_message_id,
            "inbound_received_at": inbound_received_at,
        }
        request_hash = canonical_hash(input_value)
        with self._write() as connection:
            prior = self._operation_read(connection, operation_id, "enqueue", request_hash)
            if prior is not None:
                return QueueResult(
                    status=prior["status"],
                    message_id=prior["message_id"],
                    reason=prior.get("reason"),
                    conflicts=tuple(prior.get("conflicts", ())),
                )
            existing_message = connection.execute(
                "SELECT operation_id FROM messages WHERE message_id=?", (message_id,)
            ).fetchone()
            if existing_message is not None:
                raise ConflictError(
                    "message_id was already used",
                    code="MESSAGE_ID_REUSE",
                    details={"message_id": message_id},
                )

            if conversation_key is not None:
                latest = connection.execute(
                    "SELECT provider_message_id,received_at FROM inbounds WHERE mailbox=? AND conversation_key=? "
                    "ORDER BY received_at DESC,created_at DESC LIMIT 1",
                    (mailbox, conversation_key),
                ).fetchone()
                if latest is not None:
                    if inbound_message_id is None:
                        raise ConflictError(
                            "conversation has a recorded inbound; bind the candidate to it",
                            code="INBOUND_BINDING_REQUIRED",
                            details={"latest_inbound": latest["provider_message_id"]},
                        )
                    if latest["provider_message_id"] != inbound_message_id or float(latest["received_at"]) != inbound_received_at:
                        raise ConflictError(
                            "candidate is bound to a stale inbound",
                            code="STALE_INBOUND",
                            details={"latest_inbound": latest["provider_message_id"]},
                        )
                elif inbound_message_id is not None:
                    connection.execute(
                        "INSERT INTO inbounds(mailbox,conversation_key,provider_message_id,received_at,operation_id,created_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (mailbox, conversation_key, inbound_message_id, inbound_received_at, operation_id + ":implicit", at),
                    )

                if inbound_received_at is not None:
                    _, unresolved = self._invalidate_older(
                        connection,
                        mailbox=mailbox,
                        conversation_key=conversation_key,
                        received_at=inbound_received_at,
                        now=at,
                        replacement_inbound=inbound_message_id or "unknown",
                    )
                    if unresolved:
                        raise ConflictError(
                            "an earlier send attempt must be reconciled before another response is queued",
                            code="OUTCOME_RECONCILIATION_REQUIRED",
                            details={"message_ids": unresolved},
                        )

            suppressed = [
                row["address"]
                for row in connection.execute(
                    f"SELECT address FROM suppressions WHERE address IN ({','.join('?' for _ in envelope.recipients)})",
                    envelope.recipients,
                ).fetchall()
            ]

            overlaps = self._find_overlaps(
                connection,
                mailbox=mailbox,
                recipients=envelope.recipients,
                conversation_key=conversation_key,
                inbound_message_id=inbound_message_id,
                normalized_subject=normalized_subject,
            )
            if overlaps:
                result = QueueResult(
                    status="DUPLICATE",
                    message_id=overlaps[0],
                    reason="overlapping active or sent correspondence",
                    conflicts=tuple(overlaps),
                )
                self._operation_write(connection, operation_id, "enqueue", request_hash, result.as_dict(), at)
                self._event(connection, "DUPLICATE_REJECTED", now=at, data=input_value | result.as_dict())
                return result

            if self.recipient_cooldown_seconds:
                cutoff = at - self.recipient_cooldown_seconds
                placeholders = ",".join("?" for _ in envelope.recipients)
                recent = connection.execute(
                    f"SELECT DISTINCT m.message_id FROM messages m JOIN message_recipients r ON r.message_id=m.message_id "
                    f"WHERE m.mailbox=? AND r.address IN ({placeholders}) AND m.created_at>=? "
                    "AND m.state IN ('QUEUED','CLAIMED','ATTEMPTING','UNCERTAIN','SENT') ORDER BY m.created_at DESC",
                    (mailbox, *envelope.recipients, cutoff),
                ).fetchall()
                if recent:
                    conflicts = tuple(row["message_id"] for row in recent)
                    result = QueueResult(
                        status="COOLDOWN",
                        message_id=conflicts[0],
                        reason=f"recipient cooldown ({self.recipient_cooldown_seconds:g}s)",
                        conflicts=conflicts,
                    )
                    self._operation_write(connection, operation_id, "enqueue", request_hash, result.as_dict(), at)
                    self._event(connection, "RECIPIENT_COOLDOWN", now=at, data=input_value | result.as_dict())
                    return result

            state = "SUPPRESSED" if suppressed else "QUEUED"
            reason = f"suppressed recipient(s): {', '.join(suppressed)}" if suppressed else None
            connection.execute(
                "INSERT INTO messages(message_id,operation_id,mailbox,sender,subject,normalized_subject,body,body_sha256,"
                "conversation_key,inbound_message_id,inbound_received_at,state,state_reason,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    message_id,
                    operation_id,
                    mailbox,
                    envelope.sender,
                    envelope.subject,
                    normalized_subject,
                    envelope.body,
                    body_digest(envelope.body),
                    conversation_key,
                    inbound_message_id,
                    inbound_received_at,
                    state,
                    reason,
                    at,
                    at,
                ),
            )
            for kind, values in (("to", envelope.to), ("cc", envelope.cc), ("bcc", envelope.bcc)):
                connection.executemany(
                    "INSERT INTO message_recipients(message_id,address,kind,ordinal) VALUES(?,?,?,?)",
                    [(message_id, address, kind, index) for index, address in enumerate(values)],
                )
            result = QueueResult(status=state, message_id=message_id, reason=reason)
            self._operation_write(connection, operation_id, "enqueue", request_hash, result.as_dict(), at)
            self._event(connection, "MESSAGE_QUEUED" if state == "QUEUED" else "MESSAGE_SUPPRESSED", now=at, message_id=message_id, data=input_value)
            return result

    @staticmethod
    def _find_overlaps(
        connection: sqlite3.Connection,
        *,
        mailbox: str,
        recipients: Sequence[str],
        conversation_key: str | None,
        inbound_message_id: str | None,
        normalized_subject: str,
    ) -> list[str]:
        placeholders = ",".join("?" for _ in recipients)
        if inbound_message_id is not None:
            scope_sql = "m.inbound_message_id=?"
            scope_values: tuple[Any, ...] = (inbound_message_id,)
        elif conversation_key is not None:
            scope_sql = "m.conversation_key=?"
            scope_values = (conversation_key,)
        else:
            scope_sql = "m.conversation_key IS NULL AND m.inbound_message_id IS NULL AND m.normalized_subject=?"
            scope_values = (normalized_subject,)
        rows = connection.execute(
            f"SELECT DISTINCT m.message_id,m.created_at FROM messages m "
            f"JOIN message_recipients r ON r.message_id=m.message_id "
            f"WHERE m.mailbox=? AND r.address IN ({placeholders}) AND ({scope_sql}) "
            "AND m.state IN ('QUEUED','CLAIMED','ATTEMPTING','UNCERTAIN','SENT') "
            "ORDER BY m.created_at DESC",
            (mailbox, *recipients, *scope_values),
        ).fetchall()
        return [row["message_id"] for row in rows]
