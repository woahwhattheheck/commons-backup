"""Read-only coordination. Share one local SQLite database across cooperating processes."""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MAX_REQUEST = 32768
MAX_RESPONSE = 524288
MAX_AGE = 300
METHODS = {
    "conversations.history": {"channel", "cursor", "oldest", "latest", "inclusive", "include_all_metadata", "limit"},
    "conversations.replies": {"channel", "ts", "cursor", "oldest", "latest", "inclusive", "limit"},
    "conversations.info": {"channel", "include_locale", "include_num_members"},
    "conversations.list": {"cursor", "exclude_archived", "types", "limit"},
    "search.messages": {"query", "count", "page", "highlight", "sort", "sort_dir"},
}
BOOLS = {"inclusive", "include_all_metadata", "include_locale", "include_num_members", "exclude_archived", "highlight"}
AUTH_ERRORS = {"invalid_auth", "token_revoked", "account_inactive", "not_authed", "token_expired"}
SAFE_ERRORS = AUTH_ERRORS | {"missing_scope", "channel_not_found", "not_in_channel", "invalid_cursor", "invalid_arguments", "ratelimited"}


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def loads(raw: str | bytes) -> Any:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out

    def constant(_):
        raise ValueError("nonfinite JSON value")

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def normalize(method: str, params: dict, page_limit: int = 15) -> dict:
    if not isinstance(method, str) or method not in METHODS:
        raise ValueError("read method is not allowed")
    if not isinstance(params, dict) or set(params) - METHODS[method]:
        raise ValueError("unsupported parameters")
    required = {"channel"} if method in {"conversations.history", "conversations.replies", "conversations.info"} else set()
    if method == "conversations.replies":
        required.add("ts")
    if method == "search.messages":
        required.add("query")
    if not required <= params.keys():
        raise ValueError("missing required parameters")
    out = dict(params)
    for key, value in out.items():
        if key in BOOLS:
            if type(value) is not bool:
                raise ValueError("boolean required")
        elif key in {"limit", "count", "page"}:
            ceiling = 100 if key == "page" else page_limit
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("invalid page bound")
        elif not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("invalid string parameter")
    if "channel" in out and not re.fullmatch(r"[CDG][A-Z0-9]{2,30}", out["channel"]):
        raise ValueError("invalid channel id")
    for key in ("oldest", "latest", "ts"):
        if key in out and not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,9})?", out[key]):
            raise ValueError("timestamp must remain a decimal string")
    if method in {"conversations.history", "conversations.replies"}:
        # Slack ignores inclusive without time bounds; false is its default.
        if not {"oldest", "latest"} & out.keys() or out.get("inclusive") is False:
            out.pop("inclusive", None)
    # Slack documents these booleans as false when omitted. Canonicalize
    # explicit false only after type validation so equivalent reads share
    # the same cache and in-flight request; true remains a distinct view.
    default_false = {
        "conversations.history": ("include_all_metadata",),
        "conversations.info": ("include_locale", "include_num_members"),
        "search.messages": ("highlight",),
    }
    for flag in default_false.get(method, ()):
        if out.get(flag) is False:
            out.pop(flag)
    if "sort" in out and out["sort"] not in {"score", "timestamp"}:
        raise ValueError("invalid sort")
    if "sort_dir" in out and out["sort_dir"] not in {"asc", "desc"}:
        raise ValueError("invalid sort direction")
    if "types" in out:
        types = out["types"].split(",")
        if not set(types) <= {"public_channel", "private_channel", "im", "mpim"}:
            raise ValueError("invalid conversation types")
        out["types"] = ",".join(sorted(set(types)))
    if method == "conversations.list":
        # Omitted filters have these exact Slack defaults. Keep other views distinct.
        if out.get("exclude_archived") is False:
            out.pop("exclude_archived")
        if out.get("types") == "public_channel":
            out.pop("types")
    if "limit" in METHODS[method]:
        out.setdefault("limit", page_limit)
    if method == "search.messages":
        out.setdefault("count", page_limit)
        out.setdefault("page", 1)
        out.setdefault("sort", "score")
        out.setdefault("sort_dir", "desc")
    if len(dumps(out).encode()) > MAX_REQUEST:
        raise ValueError("request too large")
    return out


def retry_seconds(value: Any) -> int:
    text = str(value).strip()
    # Never shorten a valid provider interval. Slack specifies integer seconds.
    return max(1, int(text)) if re.fullmatch(r"[0-9]{1,10}", text) else 60


@dataclass(frozen=True)
class Lease:
    key: str
    nonce: str
    method: str
    params: dict
    expires_at: float


@dataclass(frozen=True)
class Upstream:
    status: int
    payload: Any = None
    retry_after: Any = None


class Broker:
    def __init__(self, path: str | Path, workspace: str, app: str, principal: str,
                 *, clock: Callable[[], float] = time.time, internal_app: bool = False,
                 lease_seconds: float = 45, max_entries: int = 256):
        if not re.fullmatch(r"T[A-Z0-9]{2,30}", workspace) or not re.fullmatch(r"A[A-Z0-9]{2,30}", app):
            raise ValueError("explicit workspace and app ids required")
        if not re.fullmatch(r"[a-f0-9]{64}", principal):
            raise ValueError("credential fingerprint required, never a raw token")
        if type(internal_app) is not bool or type(max_entries) is not int or not 1 <= max_entries <= 4096:
            raise ValueError("invalid configuration")
        if type(lease_seconds) not in (int, float) or not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("invalid lease duration")
        self.path, self.clock = str(path), clock
        self.rate_scope = workspace + ":" + app
        self.namespace = self.rate_scope + ":" + principal
        self.page_limit = 100 if internal_app else 15
        self.intervals = {method: 3.0 for method in METHODS}
        for method in ("conversations.history", "conversations.replies"):
            self.intervals[method] = 1.25 if internal_app else 60.0
        self.lease_seconds, self.max_entries = float(lease_seconds), max_entries
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported database version")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cache (
                  namespace TEXT, key TEXT, fetched REAL, payload TEXT,
                  PRIMARY KEY(namespace,key));
                CREATE TABLE IF NOT EXISTS flight (
                  namespace TEXT, key TEXT, nonce TEXT, expires REAL,
                  PRIMARY KEY(namespace,key));
                CREATE TABLE IF NOT EXISTS rate (
                  scope TEXT, method TEXT, next_at REAL,
                  PRIMARY KEY(scope,method));
                CREATE TABLE IF NOT EXISTS blocked (
                  namespace TEXT PRIMARY KEY, reason TEXT);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def now(self):
        value = self.clock()
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid clock")
        return float(value)

    @staticmethod
    def envelope(state, **fields):
        return {"state": state, "outbound_clearance": False, **fields}

    def acquire(self, method: str, params: dict, max_age_seconds: int = 30):
        params = normalize(method, params, self.page_limit)
        if type(max_age_seconds) is not int or not 0 <= max_age_seconds <= MAX_AGE:
            raise ValueError("invalid cache age")
        key = hashlib.sha256(dumps([method, params]).encode()).hexdigest()
        with self.connect() as db:
            if max_age_seconds > 0:
                # A completed cache read does not need the single writer slot.
                # Read the block state and payload from one snapshot, then end
                # it before decoding or entering the lease-acquisition path.
                db.execute("BEGIN")
                blocked = db.execute("SELECT reason FROM blocked WHERE namespace=?", (self.namespace,)).fetchone()
                if blocked:
                    return self.envelope("AUTH_BLOCKED", error=blocked[0])
                row = db.execute("SELECT fetched,payload FROM cache WHERE namespace=? AND key=?", (self.namespace, key)).fetchone()
                now = self.now()
                db.commit()
                if row and 0 <= now - row[0] <= max_age_seconds:
                    return self.envelope("CACHED", fetched_at=row[0], age_seconds=now-row[0], data=loads(row[1]))
                # A miss must recheck state after obtaining the write lock;
                # another process may have completed or invalidated this key.
            db.execute("BEGIN IMMEDIATE")
            now = self.now()
            blocked = db.execute("SELECT reason FROM blocked WHERE namespace=?", (self.namespace,)).fetchone()
            if blocked:
                return self.envelope("AUTH_BLOCKED", error=blocked[0])
            db.execute("DELETE FROM cache WHERE fetched<?", (now - MAX_AGE,))
            db.execute("DELETE FROM flight WHERE expires<=?", (now,))
            row = db.execute("SELECT fetched,payload FROM cache WHERE namespace=? AND key=?", (self.namespace, key)).fetchone()
            if row and max_age_seconds > 0 and 0 <= now - row[0] <= max_age_seconds:
                # The snapshot is detached; decoding must not hold the writer.
                db.commit()
                return self.envelope("CACHED", fetched_at=row[0], age_seconds=now-row[0], data=loads(row[1]))
            flight = db.execute("SELECT expires FROM flight WHERE namespace=? AND key=?", (self.namespace, key)).fetchone()
            if flight:
                # The writer may finish before lease expiry; recheck its cache soon.
                # acquire still fences dispatch with the live lease and method budget.
                return self.envelope("BUSY", retry_after_seconds=1)
            rate = db.execute("SELECT next_at FROM rate WHERE scope=? AND method=?", (self.rate_scope, method)).fetchone()
            if rate and rate[0] > now:
                return self.envelope("COOLDOWN", retry_after_seconds=math.ceil(rate[0] - now))
            if db.execute("SELECT count(*) FROM flight").fetchone()[0] >= self.max_entries:
                return self.envelope("BUSY", retry_after_seconds=1)
            nonce = secrets.token_hex(24)
            expires = now + self.lease_seconds
            db.execute("INSERT INTO flight VALUES (?,?,?,?)", (self.namespace, key, nonce, expires))
            db.execute("INSERT INTO rate VALUES (?,?,?) ON CONFLICT(scope,method) DO UPDATE SET next_at=excluded.next_at", (self.rate_scope, method, now + self.intervals[method]))
            return Lease(key, nonce, method, params, expires)

    def finish(self, lease: Lease, result: Upstream):
        payload = result.payload
        limited = result.status == 429 or (isinstance(payload, dict) and payload.get("error") == "ratelimited")
        interval = retry_seconds(result.retry_after)
        error = "invalid_auth" if result.status == 401 else (payload.get("error") if isinstance(payload, dict) else None)
        error = error if isinstance(error, str) and error in SAFE_ERRORS else "upstream_error"
        text = None
        if result.status == 200 and isinstance(payload, dict) and payload.get("ok") is True and not limited:
            try:
                encoded = dumps(payload)
                if len(encoded.encode()) <= MAX_RESPONSE:
                    text = encoded
            except (ValueError, TypeError, RecursionError):
                pass
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self.now()
            # A late genuine 429 still applies to the whole method, even after lease expiry.
            if limited:
                db.execute("INSERT INTO rate VALUES (?,?,?) ON CONFLICT(scope,method) DO UPDATE SET next_at=max(rate.next_at,excluded.next_at)", (self.rate_scope, lease.method, now + interval))
            if error in AUTH_ERRORS:
                db.execute("INSERT OR REPLACE INTO blocked VALUES (?,?)", (self.namespace, error))
                db.execute("DELETE FROM cache WHERE namespace=?", (self.namespace,))
            row = db.execute("SELECT nonce,expires FROM flight WHERE namespace=? AND key=?", (self.namespace, lease.key)).fetchone()
            if not row or row[0] != lease.nonce or row[1] <= now:
                return self.envelope("DISCARDED", retry_after_seconds=1)
            db.execute("DELETE FROM flight WHERE namespace=? AND key=? AND nonce=?", (self.namespace, lease.key, lease.nonce))
            blocked = db.execute("SELECT reason FROM blocked WHERE namespace=?", (self.namespace,)).fetchone()
            if blocked:
                return self.envelope("AUTH_BLOCKED", error=blocked[0])
            if limited:
                db.execute("DELETE FROM cache WHERE namespace=? AND key=?", (self.namespace, lease.key))
                next_at = db.execute("SELECT next_at FROM rate WHERE scope=? AND method=?", (self.rate_scope, lease.method)).fetchone()[0]
                return self.envelope("COOLDOWN", retry_after_seconds=max(1, math.ceil(next_at - now)))
            if text is None:
                db.execute("DELETE FROM cache WHERE namespace=? AND key=?", (self.namespace, lease.key))
                return self.envelope("UPSTREAM_ERROR", error=error)
            db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (self.namespace, lease.key, now, text))
            db.execute("DELETE FROM cache WHERE rowid IN (SELECT rowid FROM cache ORDER BY fetched DESC,namespace,key LIMIT -1 OFFSET ?)", (self.max_entries,))
        return self.envelope("FETCHED", fetched_at=now, age_seconds=0, data=loads(text))

    def read(self, method: str, params: dict, provider: Callable, max_age_seconds: int = 30):
        decision = self.acquire(method, params, max_age_seconds)
        if not isinstance(decision, Lease):
            return decision
        try:
            result = provider(decision.method, decision.params)
            if not isinstance(result, Upstream):
                result = Upstream(502)
        except Exception:
            # Provider exceptions may include credentials or sensitive query text.
            result = Upstream(502)
        return self.finish(decision, result)
