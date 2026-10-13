"""Provider-result recording and external readback reconciliation."""

from __future__ import annotations
from typing import Any, Dict, Optional
from .codec import digest, iso, parse_time
from .constants import (
    COMMITTED, COOLDOWN, DISPATCHING, OPERATOR_COMMITTED, OPERATOR_REJECTED,
    QUEUED, RECONCILE_REQUIRED, REJECTED,
)
from .errors import PacemakerError, StoreInvariantError


class StoreResultsMixin:
    def record_result(self, key: str, *, attempt: int, classification: str,
                      reason: str, provider_status: Optional[int] = None,
                      provider_receipt_sha256: Optional[str] = None,
                      retry_at: Optional[str] = None) -> Dict[str, Any]:
        allowed = {"committed", "rejected", "rate_limited", "ambiguous"}
        if classification not in allowed:
            raise PacemakerError("unsupported provider classification")
        if provider_receipt_sha256 and (
                len(provider_receipt_sha256) != 64 or
                any(c not in "0123456789abcdef" for c in provider_receipt_sha256)):
            raise PacemakerError("provider receipt digest must be lowercase SHA-256")
        moment = iso(self.clock())
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM mutations WHERE mutation_key=?", (key,)).fetchone()
            if not row:
                raise PacemakerError("unknown mutation key")
            if row["state"] != DISPATCHING or row["attempts"] != attempt:
                raise StoreInvariantError("result does not match active claim")
            state = {"committed": COMMITTED, "rejected": REJECTED,
                     "rate_limited": COOLDOWN,
                     "ambiguous": RECONCILE_REQUIRED}[classification]
            if classification == "rate_limited":
                if not retry_at:
                    raise PacemakerError("rate limit requires retry_at")
                parse_time(retry_at, "retry_at")
                # A known rejection stays known even if its deadline elapsed
                # before recording. claim_next applies the retained deadline.
                db.execute("UPDATE meta SET cooldown_until=?,cooldown_reason=? WHERE singleton=1",
                           (retry_at, reason))
            else:
                retry_at = None
            db.execute("""UPDATE mutations SET state=?,updated_at=?,retry_at=?,provider_status=?,
              provider_receipt_sha256=?,reason=? WHERE mutation_key=?""",
              (state,moment,retry_at,provider_status,provider_receipt_sha256,reason,key))
            row = db.execute("SELECT * FROM mutations WHERE mutation_key=?", (key,)).fetchone()
            db.execute("COMMIT")
            return self._receipt(row)
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def reconcile(self, key: str, *, outcome: str, observation_ref: str,
                  observation_sha256: str) -> Dict[str, Any]:
        if (outcome not in {"committed", "rejected", "retry"} or
                len(observation_sha256) != 64 or
                any(c not in "0123456789abcdef" for c in observation_sha256)):
            raise PacemakerError("invalid reconciliation")
        state = {"committed": OPERATOR_COMMITTED,
                 "rejected": OPERATOR_REJECTED, "retry": QUEUED}[outcome]
        moment = iso(self.clock())
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM mutations WHERE mutation_key=?", (key,)).fetchone()
            if not row or row["state"] not in {DISPATCHING, RECONCILE_REQUIRED}:
                raise StoreInvariantError("mutation is not awaiting reconciliation")
            db.execute("""UPDATE mutations SET state=?,updated_at=?,claimed_at=NULL,retry_at=NULL,
              observation_ref_sha256=?,observation_sha256=?,reason=? WHERE mutation_key=?""",
              (state,moment,digest(observation_ref.encode()),observation_sha256,
               "external readback recorded: %s" % outcome,key))
            row = db.execute("SELECT * FROM mutations WHERE mutation_key=?", (key,)).fetchone()
            db.execute("COMMIT")
            return self._receipt(row)
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
