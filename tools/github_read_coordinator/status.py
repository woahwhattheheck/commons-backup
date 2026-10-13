"""Offline, read-only GitHub broker status. No provider calls or credentials."""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

BUCKETS = {"core", "issue_search", "code_search", "search", "secondary", "burst"}


def uncached_route_decisions(cooldowns, auth_blocked):
    """Summarize recorded wait floors by read family, not provider readiness."""
    families = {
        "core": ("core", "secondary", "burst"),
        "issue_search": ("issue_search", "search", "secondary", "burst"),
        "code_search": ("code_search", "search", "secondary", "burst"),
    }
    results = {}
    for family, inherited in families.items():
        active = {bucket: cooldowns[bucket] for bucket in inherited if bucket in cooldowns}
        deadline = max((entry["until"] for entry in active.values()), default=None)
        remaining = max((entry["remaining_seconds"] for entry in active.values()), default=None)
        state = "AUTH_BLOCKED" if auth_blocked else "COOLDOWN" if active else "NO_RECORDED_COOLDOWN"
        results[family] = {
            "state": state,
            "blocking_buckets": sorted(active),
            "until": deadline,
            "remaining_seconds": remaining,
        }
    return results


def snapshot(path, alias, principal, *, now=None):
    """Observe one explicitly selected namespace without opening a write handle."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", alias):
        raise ValueError("invalid rail alias")
    if not isinstance(principal, str) or not re.fullmatch(r"[a-f0-9]{64}", principal):
        raise ValueError("credential fingerprint required, never a raw token")
    observed = time.time() if now is None else now
    if type(observed) not in (int, float) or not math.isfinite(observed) or observed < 0:
        raise ValueError("invalid observation time")
    scope = "api.github.com:" + principal
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("unsupported broker database")
        rows = db.execute("SELECT bucket,next_at FROM rate WHERE scope=?", (scope,)).fetchall()
        blocked = bool(db.execute("SELECT 1 FROM blocked WHERE namespace=?", (scope,)).fetchone())
        flights = db.execute("SELECT count(*) FROM flight WHERE namespace=? AND expires>?", (scope, observed)).fetchone()[0]
        cached = db.execute("SELECT count(*) FROM cache WHERE namespace=? AND fetched BETWEEN ? AND ?", (scope, observed - 300, observed)).fetchone()[0]
        db.commit()
    cooldowns = {}
    for bucket, deadline in rows:
        if bucket in BUCKETS and type(deadline) in (int, float) and math.isfinite(deadline) and deadline > observed:
            cooldowns[bucket] = {"until": deadline, "remaining_seconds": math.ceil(deadline - observed)}
    return {"rail": alias, "observed_at": observed, "coverage": "selected_local_broker_namespace_only",
            "provider_write_authority": False, "auth_blocked": blocked,
            "cooldowns": dict(sorted(cooldowns.items())),
            "uncached_read_routes": uncached_route_decisions(cooldowns, blocked),
            "active_leases": flights,
            "recent_cache_entries": cached, "cache_age_window_seconds": 300,
            "request_budget": None, "last_error": None,
            "unavailable_reason": "broker_does_not_persist_quota_or_last_error",
            "provider_health": "unknown"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--rail", required=True)
    parser.add_argument("--fingerprint", required=True, help="existing SHA-256 fingerprint; never a token")
    args = parser.parse_args()
    try:
        result = snapshot(args.db, args.rail, args.fingerprint)
    except (ValueError, sqlite3.Error, OSError):
        parser.exit(2, "Status unavailable: database or selection invalid.\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
