"""FIFO enqueue and one-at-a-time connector claim operations."""

from __future__ import annotations
import datetime as dt
from typing import Any, Dict, Tuple
from .codec import iso, parse_json, parse_time
from .constants import COOLDOWN, DISPATCHING, QUEUED, RECONCILE_REQUIRED
from .errors import AmbiguousOutcome, IntentConflict, NoDispatchableMutation, PacemakerError
from .intent import Claim, normalize_intent


class StoreQueueMixin:
    def enqueue(self, value: Any) -> Tuple[Dict[str, Any], bool]:
        intent = normalize_intent(value)
        moment = iso(self.clock())
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM mutations WHERE mutation_key=? OR semantic_sha256=?",
                (intent.mutation_key, intent.semantic_sha256),
            ).fetchone()
            if row:
                if (row["mutation_key"] == intent.mutation_key and
                        row["semantic_sha256"] != intent.semantic_sha256):
                    raise IntentConflict("mutation key already binds different semantics")
                db.execute("COMMIT")
                return self._receipt(row), True
            db.execute("""INSERT INTO mutations(
              mutation_key,semantic_sha256,intent_sha256,method,api_path,description,
              body_json,body_sha256,state,enqueued_at,updated_at,reason)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
              (intent.mutation_key,intent.semantic_sha256,intent.intent_sha256,
               intent.method,intent.api_path,intent.description,intent.body_bytes,
               intent.body_sha256,QUEUED,moment,moment,"waiting for connector dispatch"))
            row = db.execute("SELECT * FROM mutations WHERE mutation_key=?",
                             (intent.mutation_key,)).fetchone()
            db.execute("COMMIT")
            return self._receipt(row), False
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def claim_next(self, minimum_interval_seconds: int = 1) -> Claim:
        if type(minimum_interval_seconds) is not int or minimum_interval_seconds < 0:
            raise PacemakerError("minimum interval must be a non-negative integer")
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            now = self.clock().astimezone(dt.timezone.utc).replace(microsecond=0)
            moment = iso(now)
            uncertain = db.execute(
                "SELECT mutation_key FROM mutations WHERE state IN (?,?) LIMIT 1",
                (DISPATCHING, RECONCILE_REQUIRED),
            ).fetchone()
            if uncertain:
                raise AmbiguousOutcome(
                    "mutation %s requires readback" % uncertain["mutation_key"])
            meta = db.execute("SELECT * FROM meta WHERE singleton=1").fetchone()
            cooldown_until = (parse_time(meta["cooldown_until"], "cooldown")
                              if meta["cooldown_until"] else now)
            interval_until = now
            if meta["last_claim_at"]:
                interval_until = parse_time(meta["last_claim_at"], "last claim") + dt.timedelta(
                    seconds=minimum_interval_seconds)
            retry_until = max(cooldown_until, interval_until)
            if retry_until > now:
                reason = ("provider cooldown is active" if cooldown_until > now
                          else "minimum claim interval is active")
                raise NoDispatchableMutation(
                    reason, retry_at=iso(retry_until),
                    retry_after_seconds=int((retry_until - now).total_seconds()))
            row = db.execute("""SELECT * FROM mutations WHERE state IN (?,?)
              AND (retry_at IS NULL OR retry_at<=?) ORDER BY seq LIMIT 1""",
              (QUEUED, COOLDOWN, moment)).fetchone()
            if not row:
                raise NoDispatchableMutation("no eligible mutation")
            attempt = row["attempts"] + 1
            db.execute("""UPDATE mutations SET state=?,attempts=?,claimed_at=?,updated_at=?,reason=?
              WHERE mutation_key=?""", (DISPATCHING,attempt,moment,moment,
              "connector claim issued; provider outcome pending",row["mutation_key"]))
            db.execute("""UPDATE meta SET last_claim_at=?,cooldown_until=NULL,
              cooldown_reason=NULL WHERE singleton=1""", (moment,))
            db.execute("COMMIT")
            return Claim(row["mutation_key"], row["method"], row["api_path"],
                         parse_json(bytes(row["body_json"])), attempt, moment,
                         row["semantic_sha256"])
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
