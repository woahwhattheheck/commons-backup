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


class AttemptMixin:
    def begin_attempt(
        self,
        *,
        operation_id: str,
        claim_id: str,
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        operation_id = _require_text("operation_id", operation_id)
        claim_id = _require_text("claim_id", claim_id)
        attempt_id = _require_text("attempt_id", attempt_id or stable_identifier("attempt", operation_id))
        at = float(self.clock())
        request = {"claim_id": claim_id, "attempt_id": attempt_id}
        request_hash = canonical_hash(request)
        with self._write() as connection:
            prior = self._operation_read(connection, operation_id, "begin_attempt", request_hash)
            if prior is not None:
                return prior
            existing_attempt = connection.execute(
                "SELECT message_id FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if existing_attempt is not None:
                raise ConflictError(
                    "attempt_id was already used",
                    code="ATTEMPT_ID_REUSE",
                    details={"attempt_id": attempt_id, "message_id": existing_attempt["message_id"]},
                )
            claim = connection.execute("SELECT * FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
            if claim is None:
                raise NotFoundError("claim not found", details={"claim_id": claim_id})
            message = connection.execute("SELECT * FROM messages WHERE message_id=?", (claim["message_id"],)).fetchone()
            if claim["state"] != "CLAIMED" or message["state"] != "CLAIMED":
                raise ConflictError("claim cannot begin an attempt", code="CLAIM_NOT_ACTIVE")
            if float(claim["lease_until"]) <= at:
                raise ConflictError("claim lease expired before provider attempt", code="CLAIM_EXPIRED")
            connection.execute(
                "INSERT INTO attempts(attempt_id,message_id,claim_id,state,started_at,updated_at) VALUES(?,?,?,?,?,?)",
                (attempt_id, claim["message_id"], claim_id, "STARTED", at, at),
            )
            connection.execute(
                "UPDATE claims SET state='ATTEMPTING',attempt_id=? WHERE claim_id=?", (attempt_id, claim_id)
            )
            connection.execute(
                "UPDATE messages SET state='ATTEMPTING',updated_at=? WHERE message_id=?",
                (at, claim["message_id"]),
            )
            result = {"status": "ATTEMPTING", "message_id": claim["message_id"], "claim_id": claim_id, "attempt_id": attempt_id}
            self._operation_write(connection, operation_id, "begin_attempt", request_hash, result, at)
            self._event(connection, "PROVIDER_ATTEMPT_STARTED", now=at, message_id=claim["message_id"], data=result)
            return result

    def record_provider_receipt(
        self,
        *,
        operation_id: str,
        attempt_id: str,
        provider_message_id: str,
        accepted_at: float,
    ) -> dict[str, Any]:
        operation_id = _require_text("operation_id", operation_id)
        attempt_id = _require_text("attempt_id", attempt_id)
        provider_message_id = _require_text("provider_message_id", provider_message_id, max_length=1024)
        accepted_at = float(accepted_at)
        if accepted_at < 0:
            raise ValidationError("accepted_at must be non-negative")
        at = float(self.clock())
        request = {"attempt_id": attempt_id, "provider_message_id": provider_message_id, "accepted_at": accepted_at}
        request_hash = canonical_hash(request)
        with self._write() as connection:
            prior = self._operation_read(connection, operation_id, "record_provider_receipt", request_hash)
            if prior is not None:
                return prior
            attempt = connection.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise NotFoundError("attempt not found", details={"attempt_id": attempt_id})
            receipt_owner = connection.execute(
                "SELECT attempt_id FROM attempts WHERE provider_message_id=? AND attempt_id<>?",
                (provider_message_id, attempt_id),
            ).fetchone()
            if receipt_owner is not None:
                raise ConflictError(
                    "provider_message_id is already bound to another attempt",
                    code="PROVIDER_RECEIPT_REUSE",
                    details={"attempt_id": receipt_owner["attempt_id"]},
                )
            if attempt["state"] == "SENT":
                if attempt["provider_message_id"] != provider_message_id or float(attempt["provider_accepted_at"]) != accepted_at:
                    raise ConflictError("attempt already has a different provider receipt", code="RECEIPT_CONFLICT")
            elif attempt["state"] not in ("STARTED", "UNCERTAIN"):
                raise ConflictError("attempt cannot accept a provider receipt", code="ATTEMPT_FINALIZED")
            connection.execute(
                "UPDATE attempts SET state='SENT',updated_at=?,provider_message_id=?,provider_accepted_at=? WHERE attempt_id=?",
                (at, provider_message_id, accepted_at, attempt_id),
            )
            connection.execute(
                "UPDATE claims SET state='COMPLETED',released_at=? WHERE claim_id=?",
                (at, attempt["claim_id"]),
            )
            connection.execute(
                "UPDATE messages SET state='SENT',state_reason=NULL,provider_message_id=?,provider_accepted_at=?,updated_at=? WHERE message_id=?",
                (provider_message_id, accepted_at, at, attempt["message_id"]),
            )
            result = {
                "status": "SENT",
                "message_id": attempt["message_id"],
                "attempt_id": attempt_id,
                "provider_message_id": provider_message_id,
                "provider_accepted_at": accepted_at,
            }
            self._operation_write(connection, operation_id, "record_provider_receipt", request_hash, result, at)
            self._event(connection, "PROVIDER_RECEIPT_RECORDED", now=at, message_id=attempt["message_id"], data=result)
            return result

    def mark_uncertain(
        self,
        *,
        operation_id: str,
        attempt_id: str,
        detail: str,
    ) -> dict[str, Any]:
        operation_id = _require_text("operation_id", operation_id)
        attempt_id = _require_text("attempt_id", attempt_id)
        detail = _require_text("detail", detail, max_length=4096)
        at = float(self.clock())
        request = {"attempt_id": attempt_id, "detail": detail}
        request_hash = canonical_hash(request)
        with self._write() as connection:
            prior = self._operation_read(connection, operation_id, "mark_uncertain", request_hash)
            if prior is not None:
                return prior
            attempt = connection.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise NotFoundError("attempt not found", details={"attempt_id": attempt_id})
            if attempt["state"] not in ("STARTED", "UNCERTAIN"):
                raise ConflictError("attempt cannot be marked uncertain", code="ATTEMPT_FINALIZED")
            connection.execute(
                "UPDATE attempts SET state='UNCERTAIN',updated_at=?,detail=? WHERE attempt_id=?",
                (at, detail, attempt_id),
            )
            connection.execute(
                "UPDATE messages SET state='UNCERTAIN',state_reason=?,updated_at=? WHERE message_id=?",
                (detail, at, attempt["message_id"]),
            )
            result = {"status": "UNCERTAIN", "message_id": attempt["message_id"], "attempt_id": attempt_id, "detail": detail}
            self._operation_write(connection, operation_id, "mark_uncertain", request_hash, result, at)
            self._event(connection, "PROVIDER_OUTCOME_UNCERTAIN", now=at, message_id=attempt["message_id"], data=result)
            return result
