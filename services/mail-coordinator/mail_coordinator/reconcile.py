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


class ReconcileMixin:
    def reconcile_not_sent(
        self,
        *,
        operation_id: str,
        attempt_id: str,
        evidence_ref: str,
    ) -> dict[str, Any]:
        operation_id = _require_text("operation_id", operation_id)
        attempt_id = _require_text("attempt_id", attempt_id)
        evidence_ref = _require_text("evidence_ref", evidence_ref, max_length=2048)
        at = float(self.clock())
        request = {"attempt_id": attempt_id, "evidence_ref": evidence_ref}
        request_hash = canonical_hash(request)
        with self._write() as connection:
            prior = self._operation_read(connection, operation_id, "reconcile_not_sent", request_hash)
            if prior is not None:
                return prior
            attempt = connection.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise NotFoundError("attempt not found", details={"attempt_id": attempt_id})
            if attempt["state"] != "UNCERTAIN":
                raise ConflictError("only an uncertain attempt can be reconciled as not sent", code="NOT_UNCERTAIN")
            message = connection.execute(
                "SELECT * FROM messages WHERE message_id=?", (attempt["message_id"],)
            ).fetchone()
            target_state = "QUEUED"
            reason = f"reconciled not sent: {evidence_ref}"
            suppressed = connection.execute(
                "SELECT s.address FROM suppressions s JOIN message_recipients r ON r.address=s.address "
                "WHERE r.message_id=? LIMIT 1",
                (attempt["message_id"],),
            ).fetchone()
            if suppressed is not None:
                target_state = "SUPPRESSED"
                reason = f"reconciled not sent; suppressed recipient: {suppressed['address']}"
            elif message["conversation_key"] is not None:
                latest = connection.execute(
                    "SELECT provider_message_id,received_at FROM inbounds WHERE mailbox=? AND conversation_key=? "
                    "ORDER BY received_at DESC,created_at DESC LIMIT 1",
                    (message["mailbox"], message["conversation_key"]),
                ).fetchone()
                if latest is not None and (
                    latest["provider_message_id"] != message["inbound_message_id"]
                    or float(latest["received_at"]) != float(message["inbound_received_at"])
                ):
                    target_state = "INVALIDATED"
                    reason = f"reconciled not sent; newer inbound {latest['provider_message_id']} exists"
            connection.execute(
                "UPDATE attempts SET state='NOT_SENT',updated_at=?,detail=? WHERE attempt_id=?",
                (at, f"not sent: {evidence_ref}", attempt_id),
            )
            connection.execute(
                "UPDATE claims SET state='RELEASED',released_at=? WHERE claim_id=?",
                (at, attempt["claim_id"]),
            )
            connection.execute(
                "UPDATE messages SET state=?,state_reason=?,current_claim_id=NULL,updated_at=? WHERE message_id=?",
                (target_state, reason, at, attempt["message_id"]),
            )
            result = {"status": target_state, "message_id": attempt["message_id"], "attempt_id": attempt_id, "evidence_ref": evidence_ref}
            self._operation_write(connection, operation_id, "reconcile_not_sent", request_hash, result, at)
            self._event(connection, "ATTEMPT_RECONCILED_NOT_SENT", now=at, message_id=attempt["message_id"], data=result)
            return result

    def suppress(
        self,
        *,
        operation_id: str,
        address: str,
        reason: str,
        evidence_ref: str,
    ) -> dict[str, Any]:
        operation_id = _require_text("operation_id", operation_id)
        address = normalize_address(address)
        reason = _require_text("reason", reason, max_length=1024)
        evidence_ref = _require_text("evidence_ref", evidence_ref, max_length=2048)
        at = float(self.clock())
        request = {"address": address, "reason": reason, "evidence_ref": evidence_ref}
        request_hash = canonical_hash(request)
        with self._write() as connection:
            prior = self._operation_read(connection, operation_id, "suppress", request_hash)
            if prior is not None:
                return prior
            existing = connection.execute("SELECT reason,evidence_ref FROM suppressions WHERE address=?", (address,)).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO suppressions(address,reason,evidence_ref,created_at) VALUES(?,?,?,?)",
                    (address, reason, evidence_ref, at),
                )
            elif existing["reason"] != reason or existing["evidence_ref"] != evidence_ref:
                raise ConflictError("suppression already exists with different evidence", code="SUPPRESSION_CONFLICT")
            rows = connection.execute(
                "SELECT DISTINCT m.message_id,m.state FROM messages m JOIN message_recipients r ON r.message_id=m.message_id "
                "WHERE r.address=? AND m.state IN ('QUEUED','CLAIMED','ATTEMPTING','UNCERTAIN')",
                (address,),
            ).fetchall()
            suppressed: list[str] = []
            unresolved: list[str] = []
            for row in rows:
                if row["state"] in ("ATTEMPTING", "UNCERTAIN"):
                    unresolved.append(row["message_id"])
                    continue
                connection.execute(
                    "UPDATE messages SET state='SUPPRESSED',state_reason=?,current_claim_id=NULL,updated_at=? WHERE message_id=?",
                    (f"suppressed {address}: {reason}", at, row["message_id"]),
                )
                connection.execute(
                    "UPDATE claims SET state='RELEASED',released_at=? WHERE message_id=? AND state='CLAIMED'",
                    (at, row["message_id"]),
                )
                suppressed.append(row["message_id"])
                self._event(connection, "MESSAGE_SUPPRESSED", now=at, message_id=row["message_id"], data=request)
            result = {"status": "SUPPRESSED", "address": address, "suppressed": suppressed, "unresolved": unresolved}
            self._operation_write(connection, operation_id, "suppress", request_hash, result, at)
            self._event(connection, "CONTACT_SUPPRESSED", now=at, data=request | result)
            return result
