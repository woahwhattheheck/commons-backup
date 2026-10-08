"""Cross-process coordination for bounded, read-only GitHub API calls."""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

MAX_REQUEST = 32768
MAX_RESPONSE = 1048576
MAX_AGE = 300
MAX_COOLDOWN = 86400
MAX_SECONDARY_FALLBACK = 3600
BURST_INTERVAL = 0.5

ROUTES = {
    "repo.get": {"owner", "repo"},
    "contents.get": {"owner", "repo", "path", "ref"},
    "pull.get": {"owner", "repo", "number"},
    "pull.files": {"owner", "repo", "number", "page", "per_page"},
    "pull.reviews": {"owner", "repo", "number", "page", "per_page"},
    "pull.comments": {"owner", "repo", "number", "page", "per_page"},
    "pull.commits": {"owner", "repo", "number", "page", "per_page"},
    "pulls.list": {"owner", "repo", "head", "base", "state", "page", "per_page"},
    "commit.get": {"owner", "repo", "ref"},
    "issues.list": {"owner", "repo", "state", "labels", "sort", "direction", "page", "per_page"},
    "actions.runs": {"owner", "repo", "branch", "event", "status", "head_sha", "page", "per_page"},
    "search.issues": {"q", "page", "per_page", "sort", "order"},
    "search.code": {"q", "page", "per_page", "sort", "order"},
}
SEARCH_ROUTES = {"search.issues", "search.code"}
OWNER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
REPO_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}")
HEX64_RE = re.compile(r"[a-f0-9]{64}")


def usable_etag(value: Any) -> str | None:
    # HTTP entity-tags are opaque quoted values, optionally weak. Ignore an
    # unusable validator without discarding an otherwise valid JSON response.
    if isinstance(value, str) and len(value) <= 1024 and re.fullmatch(r'(?:W/)?"[\x21\x23-\x7e\x80-\xff]*"', value):
        return value
    return None


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


def _safe_text(value: Any, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError("invalid string parameter")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("control character in string parameter")
    return value


def _safe_path(value: Any) -> str:
    value = _safe_text(value, maximum=4096)
    if value.startswith("/") or value.endswith("/") or "\\" in value:
        raise ValueError("path must be repository-relative")
    pieces = value.split("/")
    if any(piece in {"", ".", ".."} for piece in pieces):
        raise ValueError("path traversal is not allowed")
    return value


def route_bucket(route: str) -> str:
    if route in SEARCH_ROUTES:
        return "code_search" if route == "search.code" else "issue_search"
    return "core"


def normalize(route: str, params: dict) -> dict:
    if not isinstance(route, str) or route not in ROUTES:
        raise ValueError("read route is not allowed")
    if not isinstance(params, dict) or set(params) - ROUTES[route]:
        raise ValueError("unsupported parameters")
    out = dict(params)

    if route.startswith(("repo.", "contents.", "pull.", "pulls.", "commit.", "issues.", "actions.")):
        if not {"owner", "repo"} <= out.keys():
            raise ValueError("owner and repo are required")
    if "owner" in out:
        if not isinstance(out["owner"], str) or OWNER_RE.fullmatch(out["owner"]) is None:
            raise ValueError("invalid owner")
        out["owner"] = out["owner"].lower()
    if "repo" in out:
        if not isinstance(out["repo"], str) or REPO_RE.fullmatch(out["repo"]) is None:
            raise ValueError("invalid repo")
        out["repo"] = out["repo"].lower()
    if route == "contents.get":
        if "path" not in out:
            raise ValueError("path is required")
        out["path"] = _safe_path(out["path"])
    if route.startswith("pull.") and "number" not in out:
        raise ValueError("pull number is required")
    if route == "pulls.list":
        for key in ("head", "base"):
            if key not in out:
                continue
            value = _safe_text(out[key], maximum=255)
            branch = value
            if key == "head" and ":" in value:
                owner, branch = value.split(":", 1)
                if OWNER_RE.fullmatch(owner) is None:
                    raise ValueError("invalid pull head owner")
                # GitHub login names are case-insensitive. Keep the branch
                # component untouched: Git ref names remain case-sensitive.
                value = f"{owner.lower()}:{branch}"
            if not re.fullmatch(r"[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*", branch):
                raise ValueError("invalid pull branch")
            if any(part in {".", ".."} or part.endswith((".lock", ".")) for part in branch.split("/")) or ".." in branch:
                raise ValueError("invalid pull branch")
            out[key] = value
    if route == "commit.get" and "ref" not in out:
        raise ValueError("ref is required")
    if route.startswith("search.") and "q" not in out:
        raise ValueError("search query is required")

    for key in ("number", "page", "per_page"):
        if key not in out:
            continue
        value = out[key]
        if type(value) is not int:
            raise ValueError("integer parameter required")
        if key == "number" and not 1 <= value <= 2_147_483_647:
            raise ValueError("invalid pull number")
        if key == "page" and not 1 <= value <= 1000:
            raise ValueError("invalid page")
        if key == "per_page" and not 1 <= value <= 100:
            raise ValueError("invalid page size")

    for key in ("ref", "branch", "event", "status", "head_sha", "labels", "q", "sort", "order", "state", "direction"):
        if key in out:
            out[key] = _safe_text(out[key], maximum=1024 if key == "q" else 255)

    if "state" in out and out["state"] not in {"open", "closed", "all"}:
        raise ValueError("invalid state")
    if "direction" in out and out["direction"] not in {"asc", "desc"}:
        raise ValueError("invalid direction")
    if "order" in out and out["order"] not in {"asc", "desc"}:
        raise ValueError("invalid order")
    if "sort" in out:
        allowed = {"created", "updated", "comments"} if route == "search.issues" else {"indexed"} if route == "search.code" else {"created", "updated", "comments"}
        if out["sort"] not in allowed:
            raise ValueError("invalid sort")

    if route in {"pull.files", "pull.reviews", "pull.comments", "pull.commits", "pulls.list", "issues.list", "actions.runs", "search.issues", "search.code"}:
        out.setdefault("per_page", 30)
        out.setdefault("page", 1)
    if route == "pulls.list":
        # GitHub defaults to open PRs. Keep omitted and explicit defaults on
        # one request key, cached response, and in-flight provider lease.
        out.setdefault("state", "open")
    if route == "issues.list":
        out.setdefault("state", "open")
        out.setdefault("sort", "created")
        out.setdefault("direction", "desc")
    if len(dumps(out).encode()) > MAX_REQUEST:
        raise ValueError("request too large")
    return out


def retry_after_seconds(value: Any, now: float | None = None) -> int | None:
    text = str(value).strip()
    if re.fullmatch(r"[0-9]{1,10}", text):
        return max(1, int(text))
    try:
        deadline = parsedate_to_datetime(text)
        # The obsolete asctime HTTP-date form has no explicit zone; HTTP
        # dates are UTC. Do not let the machine's local zone change the wait.
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        observed = time.time() if now is None else now
        if type(observed) not in (int, float) or not math.isfinite(observed):
            return None
        return max(1, math.ceil(deadline.timestamp() - observed))
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def reset_delay(reset_value: Any, now: float) -> int | None:
    text = str(reset_value).strip()
    if not re.fullmatch(r"[0-9]{1,12}", text):
        return None
    target = int(text)
    if target <= now:
        return 1
    return min(MAX_COOLDOWN, max(1, math.ceil(target - now)))


@dataclass(frozen=True)
class Lease:
    key: str
    nonce: str
    route: str
    params: dict
    bucket: str
    expires_at: float
    acquired_at: float | None = None
    # Exact validated representation retained privately for this request only.
    validator: tuple[str, str] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Upstream:
    status: int
    payload: Any = None
    retry_after: Any = None
    rate_remaining: Any = None
    rate_reset: Any = None
    secondary_limited: bool = False
    etag: str | None = None
    validated_etag: str | None = None


class Broker:
    def __init__(self, path: str | Path, principal: str, *, clock: Callable[[], float] = time.time,
                 lease_seconds: float = 45, max_entries: int = 256, burst_interval: float = BURST_INTERVAL):
        if not isinstance(principal, str) or HEX64_RE.fullmatch(principal) is None:
            raise ValueError("credential fingerprint required, never a raw token")
        if type(max_entries) is not int or not 1 <= max_entries <= 4096:
            raise ValueError("invalid max entries")
        for name, value in (("lease_seconds", lease_seconds), ("burst_interval", burst_interval)):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"invalid {name}")
        self.path = str(path)
        self.clock = clock
        self.namespace = "api.github.com:" + principal
        self.scope = self.namespace
        self.lease_seconds = float(lease_seconds)
        self.max_entries = max_entries
        self.burst_interval = float(burst_interval)
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
                  scope TEXT, bucket TEXT, next_at REAL,
                  PRIMARY KEY(scope,bucket));
                CREATE TABLE IF NOT EXISTS blocked (
                  namespace TEXT PRIMARY KEY, reason TEXT);
                CREATE TABLE IF NOT EXISTS secondary_backoff (
                  scope TEXT PRIMARY KEY, failures INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS validators (
                  namespace TEXT, key TEXT, fetched REAL, etag TEXT, digest TEXT,
                  PRIMARY KEY(namespace,key));
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

    def now(self) -> float:
        value = self.clock()
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid clock")
        return float(value)

    @staticmethod
    def envelope(state: str, **fields):
        return {"state": state, "provider_write_authority": False, **fields}

    def _cooldown(self, db, bucket: str, now: float) -> int | None:
        # Older workers recorded both search resources in one bucket. Honor
        # that shared floor until it expires, including late legacy completions.
        legacy = "search" if bucket in {"issue_search", "code_search"} else bucket
        rows = db.execute(
            "SELECT bucket,next_at FROM rate WHERE scope=? AND bucket IN (?,?,?,?)",
            (self.scope, "secondary", "burst", bucket, legacy),
        ).fetchall()
        future = [row["next_at"] for row in rows if row["next_at"] > now]
        return max(1, math.ceil(max(future) - now)) if future else None

    def acquire(self, route: str, params: dict, max_age_seconds: int = 30):
        params = normalize(route, params)
        if type(max_age_seconds) is not int or not 0 <= max_age_seconds <= MAX_AGE:
            raise ValueError("invalid cache age")
        key = hashlib.sha256(dumps([route, params]).encode()).hexdigest()
        bucket = route_bucket(route)
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
                if row and 0 <= now - row["fetched"] <= max_age_seconds:
                    return self.envelope("CACHED", fetched_at=row["fetched"], age_seconds=now-row["fetched"], data=loads(row["payload"]))
                # A miss must recheck state after obtaining the write lock;
                # another process may have completed or invalidated this key.
            db.execute("BEGIN IMMEDIATE")
            now = self.now()
            blocked = db.execute("SELECT reason FROM blocked WHERE namespace=?", (self.namespace,)).fetchone()
            if blocked:
                return self.envelope("AUTH_BLOCKED", error=blocked[0])
            db.execute("DELETE FROM cache WHERE fetched<?", (now - MAX_AGE,))
            self._prune_validators(db)
            db.execute("DELETE FROM flight WHERE expires<=?", (now,))
            row = db.execute("SELECT fetched,payload FROM cache WHERE namespace=? AND key=?", (self.namespace, key)).fetchone()
            if row and max_age_seconds > 0 and 0 <= now - row["fetched"] <= max_age_seconds:
                # The selected bytes belong to this completed read. Release the
                # write transaction before decoding so independent cache readers
                # do not serialize on JSON parsing.
                db.commit()
                return self.envelope("CACHED", fetched_at=row["fetched"], age_seconds=now-row["fetched"], data=loads(row["payload"]))
            flight = db.execute("SELECT expires FROM flight WHERE namespace=? AND key=?", (self.namespace, key)).fetchone()
            if flight:
                # Recheck the local cache promptly: lease expiry is the owner's
                # crash-recovery deadline, not the expected response-ready time.
                # Keeping the flight intact prevents duplicate provider calls.
                return self.envelope("BUSY", retry_after_seconds=1)
            cooldown = self._cooldown(db, bucket, now)
            if cooldown is not None:
                return self.envelope("COOLDOWN", retry_after_seconds=cooldown)
            if db.execute("SELECT count(*) FROM flight WHERE namespace=?", (self.namespace,)).fetchone()[0] >= self.max_entries:
                return self.envelope("BUSY", retry_after_seconds=1)
            nonce = secrets.token_hex(24)
            expires = now + self.lease_seconds
            db.execute("INSERT INTO flight VALUES (?,?,?,?)", (self.namespace, key, nonce, expires))
            db.execute(
                "INSERT INTO rate VALUES (?,?,?) ON CONFLICT(scope,bucket) DO UPDATE SET next_at=max(rate.next_at,excluded.next_at)",
                (self.scope, "burst", now + self.burst_interval),
            )
            saved = db.execute(
                "SELECT etag,digest FROM validators WHERE namespace=? AND key=? AND fetched=?",
                (self.namespace, key, row["fetched"]),
            ).fetchone() if row and 0 <= now - row["fetched"] <= MAX_AGE else None
            # Hashing a retained body must not occupy the shared writer slot.
            db.commit()
            validator = None
            if saved and usable_etag(saved["etag"]) and hashlib.sha256(row["payload"].encode()).hexdigest() == saved["digest"]:
                validator = (saved["etag"], row["payload"])
            return Lease(key, nonce, route, params, bucket, expires, now, validator)

    @staticmethod
    def _prune_validators(db):
        # A side table keeps the original four-column cache compatible with
        # older processes. Remove metadata when they evict or replace a row.
        db.execute(
            "DELETE FROM validators WHERE NOT EXISTS (SELECT 1 FROM cache "
            "WHERE cache.namespace=validators.namespace AND cache.key=validators.key "
            "AND cache.fetched=validators.fetched)"
        )

    def _extend(self, db, bucket: str, next_at: float):
        db.execute(
            "INSERT INTO rate VALUES (?,?,?) ON CONFLICT(scope,bucket) DO UPDATE SET next_at=max(rate.next_at,excluded.next_at)",
            (self.scope, bucket, next_at),
        )

    def finish(self, lease: Lease, result: Upstream):
        now = self.now()
        if not isinstance(result, Upstream):
            result = Upstream(502)
        secondary = type(result.secondary_limited) is bool and result.secondary_limited
        retry = retry_after_seconds(result.retry_after, now)
        remaining_zero = str(result.rate_remaining).strip() == "0"
        primary_limited = result.status in {403, 429} and remaining_zero
        generic_429 = result.status == 429 and not secondary
        limited = secondary or primary_limited or generic_429
        if secondary:
            delay = retry or 60
            limit_bucket = "secondary"
        elif primary_limited:
            delay = retry or reset_delay(result.rate_reset, now) or 60
            limit_bucket = lease.bucket
        elif generic_429:
            # GitHub may signal secondary throttling with a bare 429 and no
            # parseable body/header distinction. Fail conservatively across
            # all routes for this credential instead of stampeding another bucket.
            delay = retry or 60
            limit_bucket = "secondary"
        else:
            delay = None
            limit_bucket = None

        revalidated = (result.status == 304 and lease.validator is not None
                       and result.validated_etag == lease.validator[0])
        payload_text = lease.validator[1] if revalidated else None
        etag = usable_etag(result.etag) or (lease.validator[0] if revalidated else None)
        if result.status == 200:
            try:
                encoded = dumps(result.payload)
                if len(encoded.encode()) <= MAX_RESPONSE:
                    payload_text = encoded
            except (ValueError, TypeError, RecursionError):
                pass
        digest = hashlib.sha256(payload_text.encode()).hexdigest() if payload_text is not None and etag else None

        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Lock waits must not extend a lease. Keep the response observation
            # time above for payload freshness and provider cooldown deadlines.
            transaction_now = self.now()
            row = db.execute("SELECT nonce,expires FROM flight WHERE namespace=? AND key=?", (self.namespace, lease.key)).fetchone()
            if limited:
                if limit_bucket == "secondary" and retry is None:
                    previous = db.execute(
                        "SELECT failures FROM secondary_backoff WHERE scope=?", (self.scope,),
                    ).fetchone()
                    floor = db.execute(
                        "SELECT next_at FROM rate WHERE scope=? AND bucket='secondary'", (self.scope,),
                    ).fetchone()
                    # Several responses can already be in flight when a limit
                    # arrives. Only a request admitted after the previous pause
                    # is a failed retry; older responses keep the same streak.
                    after_pause = lease.acquired_at is not None and (
                        floor is None or lease.acquired_at >= floor["next_at"])
                    failures = previous["failures"] if previous else 0
                    if row and row["nonce"] == lease.nonce and (after_pause or floor is None):
                        failures = min(7, failures + 1)
                    if failures:
                        delay = min(MAX_SECONDARY_FALLBACK, 60 * 2 ** (failures - 1))
                        if previous is None or failures != previous["failures"]:
                            db.execute(
                                "INSERT INTO secondary_backoff VALUES (?,?) "
                                "ON CONFLICT(scope) DO UPDATE SET failures=excluded.failures",
                                (self.scope, failures),
                            )
                self._extend(db, limit_bucket, now + delay)
            # Primary exhaustion can coincide with a secondary limit. Keep its
            # reset floor independently so a shorter Retry-After cannot reopen
            # that quota bucket early. Successful final requests keep their
            # payload, and expired leases still carry quota observations.
            if remaining_zero and result.status in {200, 304, 403, 429}:
                primary_delay = max(retry or 0, reset_delay(result.rate_reset, now) or 0) or 60
                self._extend(db, lease.bucket, now + primary_delay)
            if result.status == 401:
                db.execute("INSERT OR REPLACE INTO blocked VALUES (?,?)", (self.namespace, "bad_credentials"))
                db.execute("DELETE FROM cache WHERE namespace=?", (self.namespace,))
                db.execute("DELETE FROM validators WHERE namespace=?", (self.namespace,))
            if not row or row["nonce"] != lease.nonce or row["expires"] <= transaction_now:
                return self.envelope("DISCARDED", retry_after_seconds=1)
            db.execute("DELETE FROM flight WHERE namespace=? AND key=? AND nonce=?", (self.namespace, lease.key, lease.nonce))
            blocked = db.execute("SELECT reason FROM blocked WHERE namespace=?", (self.namespace,)).fetchone()
            if blocked:
                return self.envelope("AUTH_BLOCKED", error=blocked[0])
            if limited:
                db.execute("DELETE FROM cache WHERE namespace=? AND key=?", (self.namespace, lease.key))
                db.execute("DELETE FROM validators WHERE namespace=? AND key=?", (self.namespace, lease.key))
                wait = self._cooldown(db, lease.bucket, transaction_now) or 1
                return self.envelope("COOLDOWN", retry_after_seconds=wait)
            if payload_text is None:
                db.execute("DELETE FROM cache WHERE namespace=? AND key=?", (self.namespace, lease.key))
                db.execute("DELETE FROM validators WHERE namespace=? AND key=?", (self.namespace, lease.key))
                safe = "not_found" if result.status == 404 else "forbidden" if result.status == 403 else "upstream_error"
                return self.envelope("UPSTREAM_ERROR", error=safe)
            # An old in-flight success is not a successful retry. It must not
            # erase the fallback streak merely because completion was delayed.
            floor = db.execute(
                "SELECT next_at FROM rate WHERE scope=? AND bucket='secondary'", (self.scope,),
            ).fetchone()
            if floor is None or (
                    lease.acquired_at is not None and lease.acquired_at >= floor["next_at"]):
                db.execute("DELETE FROM secondary_backoff WHERE scope=?", (self.scope,))
            db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (self.namespace, lease.key, now, payload_text))
            if etag:
                db.execute("INSERT OR REPLACE INTO validators VALUES (?,?,?,?,?)",
                           (self.namespace, lease.key, now, etag, digest))
            else:
                db.execute("DELETE FROM validators WHERE namespace=? AND key=?", (self.namespace, lease.key))
            # Each credential namespace owns its cache budget. A busy token
            # must not evict another token's successful reads from a shared DB.
            db.execute(
                "DELETE FROM cache WHERE rowid IN (SELECT rowid FROM cache "
                "WHERE namespace=? ORDER BY fetched DESC,key LIMIT -1 OFFSET ?)",
                (self.namespace, self.max_entries),
            )
            self._prune_validators(db)
            # Persist the completed response before decoding its return value,
            # so JSON parsing does not hold the shared write transaction.
            db.commit()
            return self.envelope("FETCHED", fetched_at=now, age_seconds=0, data=loads(payload_text),
                                 **({"revalidated": True} if revalidated else {}))

    def read(self, route: str, params: dict, provider: Callable, max_age_seconds: int = 30):
        decision = self.acquire(route, params, max_age_seconds)
        if not isinstance(decision, Lease):
            return decision
        try:
            revalidate = getattr(provider, "revalidate", None)
            if decision.validator is not None and callable(revalidate):
                result = revalidate(decision.route, decision.params, decision.validator[0])
            else:
                result = provider(decision.route, decision.params)
            if not isinstance(result, Upstream):
                result = Upstream(502)
        except Exception:
            result = Upstream(502)
        return self.finish(decision, result)

