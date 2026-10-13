"""Durable provider cooldowns and cooperating process admission.

The existing refresh OS lock remains the refresh singleflight. This small SQLite
ledger lets later collector instances honor a provider's Retry-After without
sleeping through the collection deadline or blocking unrelated providers.
Repeated limits without a provider deadline use persisted, bounded backoff.
Expiring capacity leases share this ledger with the command-center read budget.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


def _iso(value):
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def retry_seconds(value, now, fallback):
    """Parse a provider delay/date; malformed values use an explicit local policy."""
    if not isinstance(value, bool) and value is not None:
        try:
            seconds = float(value)
            if math.isfinite(seconds) and 0 <= seconds <= 3153600000:
                return seconds, "provider"
        except (ValueError, TypeError, OverflowError):
            pass
        if isinstance(value, str):
            try:
                stamp = parsedate_to_datetime(value)
                if stamp.tzinfo is not None:
                    seconds = stamp.timestamp() - now
                    if math.isfinite(seconds) and seconds <= 3153600000:
                        return max(0, seconds), "provider"
            except (ValueError, TypeError, OverflowError):
                pass
    return fallback, "configured_fallback"


class RequestDeferred(RuntimeError):
    def __init__(self, scope, retry_at, reason):
        super().__init__("collector_read_deferred")
        self.code = "collector_read_deferred"
        self.scope = scope
        self.retry_not_before = _iso(retry_at)
        self.reason = reason


class RequestBudget:
    def __init__(self, state_dir=None, *, clock=time.time, fallback_seconds=60):
        if (isinstance(fallback_seconds, bool) or not isinstance(fallback_seconds, (int, float))
                or not math.isfinite(fallback_seconds) or not 1 <= fallback_seconds <= 3600):
            raise ValueError("rate_limit_fallback_seconds must be from 1 to 3600.")
        self.clock, self.fallback_seconds = clock, fallback_seconds
        self.path = Path(state_dir) / "request-budget.sqlite3" if state_dir is not None else None
        self._lock = threading.RLock()
        self._memory = sqlite3.connect(":memory:", check_same_thread=False) if self.path is None else None
        self._attempts = self._deferred = self._limited = 0
        with self._transaction(write=False) as db:
            tables = {row["name"] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            schema_ready = {
                "read_budget", "provider_capacity", "provider_leases",
                "provider_limit_observations",
            } <= tables
            if schema_ready:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(read_budget)")}
                schema_ready = "fallback_streak" in columns
        if schema_ready:
            return
        with self._transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS read_budget(
                scope TEXT PRIMARY KEY, retry_until REAL NOT NULL DEFAULT 0, last_attempt REAL,
                last_limited REAL, attempts INTEGER NOT NULL DEFAULT 0,
                deferred INTEGER NOT NULL DEFAULT 0, limited INTEGER NOT NULL DEFAULT 0,
                retry_basis TEXT, fallback_streak INTEGER NOT NULL DEFAULT 0)""")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(read_budget)")}
            if "fallback_streak" not in columns:
                db.execute("ALTER TABLE read_budget ADD COLUMN fallback_streak INTEGER NOT NULL DEFAULT 0")
            db.execute("""CREATE TABLE IF NOT EXISTS provider_capacity(
                scope TEXT PRIMARY KEY, capacity INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS provider_leases(
                scope TEXT NOT NULL, holder TEXT NOT NULL, lease_id TEXT NOT NULL,
                expires_at REAL NOT NULL, PRIMARY KEY(scope, holder), UNIQUE(lease_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS provider_limit_observations(
                observation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL)""")

    @contextmanager
    def _transaction(self, *, write=True):
        with self._lock:
            db = self._memory or sqlite3.connect(str(self.path), timeout=10)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA busy_timeout=10000")
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                if self._memory is None:
                    db.close()

    @staticmethod
    def _row(db, scope):
        db.execute("INSERT OR IGNORE INTO read_budget(scope) VALUES(?)", (scope,))
        return db.execute("SELECT * FROM read_budget WHERE scope=?", (scope,)).fetchone()

    def acquire(self, scope, *, shared_scopes=()):
        """Count one request after checking its resource and shared cooldowns.

        Shared scopes carry provider-wide limits without charging the same
        request twice. Existing provider-wide deadlines remain effective when
        callers start using finer-grained resource scopes.
        """
        deferred = None
        with self._transaction() as db:
            now = self.clock()
            row = self._row(db, scope)
            for shared in set(shared_scopes) - {scope}:
                candidate = db.execute("SELECT * FROM read_budget WHERE scope=?", (shared,)).fetchone()
                if candidate is not None and candidate["retry_until"] > row["retry_until"]:
                    row = candidate
            until = row["retry_until"]
            if now < until:
                db.execute("UPDATE read_budget SET deferred=deferred+1 WHERE scope=?", (row["scope"],))
                self._deferred += 1
                deferred = RequestDeferred(row["scope"], until, "rate_limited")
            else:
                db.execute("""UPDATE read_budget SET attempts=attempts+1,
                    last_attempt=? WHERE scope=?""", (now, scope))
                self._attempts += 1
        if deferred is not None:
            raise deferred

    def rate_limited(self, scope, retry_after=None, reset_at=None, *, observation_id=None,
                     reset_scope=None):
        """Record one provider observation; exact named retries never count twice.

        The caller keeps one ID per actual provider response. The fingerprint
        binds it to the original scope/evidence without retaining header text.
        Replays return the currently governing deadline, including newer limits.
        A separate reset_scope keeps a resource reset out of a shared secondary
        cooldown. Both facts commit atomically and count as one response.
        """
        if reset_scope is not None:
            self._lease_name(reset_scope)
        separate_reset = reset_scope is not None and reset_scope != scope

        def reset_receipt(db, now):
            row = db.execute("SELECT * FROM read_budget WHERE scope=?", (reset_scope,)).fetchone()
            if row is None:
                return {}
            return {"reset_cooldown": {"scope": reset_scope,
                    "retry_not_before": _iso(row["retry_until"]),
                    "retry_after_seconds": max(0, row["retry_until"] - now),
                    "retry_basis": row["retry_basis"]}}

        fingerprint = None
        if observation_id is not None:
            if (not isinstance(observation_id, str) or not 1 <= len(observation_id) <= 200
                    or any(ord(char) < 32 for char in observation_id)):
                raise ValueError("observation_id must be nonempty text up to 200 characters.")
            evidence = [scope, retry_after, reset_at]
            if reset_scope is not None:
                evidence.append(reset_scope)
            fingerprint = hashlib.sha256(json.dumps(evidence,
                sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        with self._transaction() as db:
            now = self.clock()
            row = self._row(db, scope)
            if observation_id is not None:
                previous = db.execute("SELECT fingerprint FROM provider_limit_observations "
                                      "WHERE observation_id=?", (observation_id,)).fetchone()
                if previous is not None:
                    if previous["fingerprint"] != fingerprint:
                        raise ValueError("observation_id was already used with different rate-limit evidence.")
                    return {"scope": scope, "retry_not_before": _iso(row["retry_until"]),
                            "retry_after_seconds": max(0, row["retry_until"] - now),
                            "retry_basis": row["retry_basis"], "observation_id": observation_id,
                            "replayed": True, **(reset_receipt(db, now) if separate_reset else {})}
            seconds, basis = retry_seconds(retry_after, now, self.fallback_seconds)
            valid_reset = (not isinstance(reset_at, bool) and isinstance(reset_at, (int, float))
                           and math.isfinite(reset_at) and now <= reset_at <= now + 3153600000)
            if valid_reset and not separate_reset:
                seconds = max(reset_at - now, seconds if basis == "provider" else 0)
                basis = "provider_retry_and_reset" if basis == "provider" else "provider_reset"
            streak = 0
            if basis == "configured_fallback":
                # The streak survives refresh/restart. Even a configured one
                # second fallback reaches the one-hour cap within 13 failures.
                streak = min(row["fallback_streak"] + 1, 13)
                seconds = min(3600, self.fallback_seconds * 2 ** (streak - 1))
                if streak > 1:
                    basis = "configured_exponential_backoff"
            if seconds < 1:
                seconds, basis = 1, basis + "_minimum_delay"
            until = now + seconds
            if row["retry_until"] >= until:
                # Keep the reason for the deadline that still governs this read.
                until, basis = row["retry_until"], row["retry_basis"] or basis
            db.execute("""UPDATE read_budget SET retry_until=?,last_limited=?,
                limited=limited+1,retry_basis=?,fallback_streak=? WHERE scope=?""",
                (until, now, basis, streak, scope))
            if separate_reset and valid_reset:
                reset_row = self._row(db, reset_scope)
                reset_until = max(reset_at, now + 1)
                reset_basis = "provider_reset" + ("_minimum_delay" if reset_at < now + 1 else "")
                if reset_row["retry_until"] >= reset_until:
                    reset_until = reset_row["retry_until"]
                    reset_basis = reset_row["retry_basis"] or reset_basis
                db.execute("""UPDATE read_budget SET retry_until=?,last_limited=?,
                    limited=limited+1,retry_basis=?,fallback_streak=0 WHERE scope=?""",
                    (reset_until, now, reset_basis, reset_scope))
            reset_evidence = reset_receipt(db, now) if separate_reset else {}
            if observation_id is not None:
                db.execute("INSERT INTO provider_limit_observations(observation_id,fingerprint) VALUES(?,?)",
                           (observation_id, fingerprint))
            self._limited += 1
        return {"scope": scope, "retry_not_before": _iso(until),
                "retry_after_seconds": max(0, until - now), "retry_basis": basis,
                **reset_evidence,
                **({"observation_id": observation_id, "replayed": False} if observation_id is not None else {})}

    def succeeded(self, scope, *, shared_scopes=()):
        """Reset fallback backoff after recovery without clearing a live limit.

        Another in-flight request may have just recorded a new cooldown; that
        deadline and its streak must survive an older request's success.
        """
        scopes = tuple({scope, *shared_scopes})
        placeholders = ",".join("?" for _ in scopes)
        predicate = ("scope IN (" + placeholders +
                     ") AND retry_until<=? AND fallback_streak<>0")
        # Most successful reads have no fallback streak to reset. Do not take
        # the writer slot for that no-op while another process records work.
        with self._transaction(write=False) as db:
            if db.execute("SELECT 1 FROM read_budget WHERE " + predicate + " LIMIT 1",
                          (*scopes, self.clock())).fetchone() is None:
                return
        # End the read transaction before acquiring the writer slot; recheck
        # current state so a newer live cooldown keeps its deadline and streak.
        with self._transaction() as db:
            db.execute("UPDATE read_budget SET fallback_streak=0 WHERE " + predicate,
                       (*scopes, self.clock()))

    @staticmethod
    def _lease_name(value):
        if (not isinstance(value, str) or not 1 <= len(value) <= 200
                or any(ord(char) < 32 for char in value)):
            raise ValueError("Lease scope and holder must be nonempty text up to 200 characters.")
        return value

    def set_capacity(self, scope, capacity):
        self._lease_name(scope)
        if type(capacity) is not int or not 1 <= capacity <= 64:
            raise ValueError("Provider capacity must be an integer from 1 to 64.")
        with self._transaction() as db:
            db.execute("INSERT INTO provider_capacity(scope,capacity) VALUES(?,?) "
                       "ON CONFLICT(scope) DO UPDATE SET capacity=excluded.capacity", (scope, capacity))
        return {"scope": scope, "capacity": capacity}

    @staticmethod
    def _lease_ttl(ttl_seconds):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise ValueError("Lease lifetime must be an integer from 1 to 3600 seconds.")

    def _lease_cooldown(self, db, scope, shared_scopes, now):
        scopes = tuple({self._lease_name(name) for name in (scope, *shared_scopes)})
        placeholders = ",".join("?" for _ in scopes)
        return db.execute("SELECT scope,retry_until FROM read_budget WHERE scope IN (" +
                          placeholders + ") AND retry_until>? ORDER BY retry_until DESC LIMIT 1",
                          (*scopes, now)).fetchone()

    @staticmethod
    def _lease_receipt(row, capacity):
        return {"scope": row["scope"], "holder": row["holder"], "lease_id": row["lease_id"],
                "expires_at": _iso(row["expires_at"]), "capacity": capacity}

    def acquire_lease(self, scope, holder, *, ttl_seconds=300, shared_scopes=()):
        """Atomically admit one cooperating holder; repeated acquisition is idempotent.

        Leases apply only to callers sharing this database. They cannot cancel
        an in-flight remote request; renew immediately before every new effect.
        """
        self._lease_name(scope)
        self._lease_name(holder)
        self._lease_ttl(ttl_seconds)
        with self._transaction() as db:
            now = self.clock()
            policy = db.execute("SELECT capacity FROM provider_capacity WHERE scope=?", (scope,)).fetchone()
            if policy is None:
                raise ValueError("Provider capacity is not configured for this scope.")
            cooldown = self._lease_cooldown(db, scope, shared_scopes, now)
            if cooldown is not None:
                raise RequestDeferred(cooldown["scope"], cooldown["retry_until"], "rate_limited")
            db.execute("DELETE FROM provider_leases WHERE scope=? AND expires_at<=?", (scope, now))
            row = db.execute("SELECT * FROM provider_leases WHERE scope=? AND holder=?", (scope, holder)).fetchone()
            if row is None:
                active = db.execute("SELECT expires_at FROM provider_leases WHERE scope=? "
                                    "ORDER BY expires_at", (scope,)).fetchall()
                if len(active) >= policy["capacity"]:
                    # A capacity reduction can require several leases to expire.
                    until = active[len(active) - policy["capacity"]]["expires_at"]
                    raise RequestDeferred(scope, until, "capacity_exhausted")
                db.execute("INSERT INTO provider_leases(scope,holder,lease_id,expires_at) VALUES(?,?,?,?)",
                           (scope, holder, uuid.uuid4().hex, now + ttl_seconds))
                row = db.execute("SELECT * FROM provider_leases WHERE scope=? AND holder=?", (scope, holder)).fetchone()
            return self._lease_receipt(row, policy["capacity"])

    def renew_lease(self, scope, holder, lease_id, *, ttl_seconds=300, shared_scopes=()):
        self._lease_name(scope)
        self._lease_name(holder)
        self._lease_ttl(ttl_seconds)
        with self._transaction() as db:
            now = self.clock()
            row = db.execute("SELECT * FROM provider_leases WHERE scope=? AND holder=? AND lease_id=? "
                             "AND expires_at>?", (scope, holder, lease_id, now)).fetchone()
            if row is None:
                raise ValueError("Provider lease expired or no longer belongs to this holder.")
            cooldown = self._lease_cooldown(db, scope, shared_scopes, now)
            if cooldown is not None:
                raise RequestDeferred(cooldown["scope"], cooldown["retry_until"], "rate_limited")
            until = max(row["expires_at"], now + ttl_seconds)
            db.execute("UPDATE provider_leases SET expires_at=? WHERE lease_id=?", (until, lease_id))
            policy = db.execute("SELECT capacity FROM provider_capacity WHERE scope=?", (scope,)).fetchone()
            return self._lease_receipt({**dict(row), "expires_at": until}, policy["capacity"])

    def release_lease(self, scope, holder, lease_id):
        self._lease_name(scope)
        self._lease_name(holder)
        with self._transaction() as db:
            changed = db.execute("DELETE FROM provider_leases WHERE scope=? AND holder=? AND lease_id=?",
                                 (scope, holder, lease_id)).rowcount
        return {"scope": scope, "holder": holder, "released": bool(changed)}

    def lease_status(self, scope, *, shared_scopes=()):
        self._lease_name(scope)
        with self._transaction(write=False) as db:
            now = self.clock()
            policy = db.execute("SELECT capacity FROM provider_capacity WHERE scope=?", (scope,)).fetchone()
            active = db.execute("SELECT holder,expires_at FROM provider_leases WHERE scope=? AND expires_at>? "
                                "ORDER BY expires_at,holder", (scope, now)).fetchall()
            cooldown = self._lease_cooldown(db, scope, shared_scopes, now)
            reason, until = None, None
            if cooldown is not None:
                reason, until = "rate_limited", cooldown["retry_until"]
            elif policy is None:
                reason = "capacity_unconfigured"
            elif len(active) >= policy["capacity"]:
                reason = "capacity_exhausted"
                until = active[len(active) - policy["capacity"]]["expires_at"]
            return {"scope": scope, "capacity": policy["capacity"] if policy else None,
                    "active": len(active), "admission_available": reason is None,
                    "reason": reason, "retry_not_before": _iso(until),
                    "leases": [{"holder": row["holder"], "expires_at": _iso(row["expires_at"])} for row in active]}

    def metrics(self):
        with self._transaction(write=False) as db:
            now = self.clock()
            scopes = []
            for row in db.execute("""SELECT * FROM read_budget
                    ORDER BY CASE WHEN retry_until>? THEN 0 ELSE 1 END,
                    CASE WHEN retry_until>? THEN retry_until
                         ELSE MAX(COALESCE(last_attempt,0),COALESCE(last_limited,0)) END DESC,
                    scope LIMIT 100""", (now, now)):
                until = row["retry_until"]
                scopes.append({"scope": row["scope"],
                    "state": "rate_limited" if now < until else "ready",
                    "retry_not_before": _iso(until) if until else None,
                    "retry_remaining_seconds": max(0, until - now),
                    "last_attempt_at": _iso(row["last_attempt"]),
                    "last_rate_limit_at": _iso(row["last_limited"]),
                    "retry_basis": row["retry_basis"],
                    "fallback_streak": row["fallback_streak"],
                    "total_observed_attempts": row["attempts"],
                    "total_deferred_reads": row["deferred"],
                    "total_rate_limit_responses": row["limited"]})
            scope_count = db.execute("SELECT COUNT(*) FROM read_budget").fetchone()[0]
            return {"observed_attempts": self._attempts, "deferred_reads": self._deferred,
                    "scope_count": scope_count, "scopes_truncated": scope_count > len(scopes),
                    "rate_limit_responses": self._limited, "scopes": scopes,
                    "persistence": "state_directory" if self.path is not None else "instance_only"}
