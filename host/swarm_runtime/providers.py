"""Bounded GitHub reconciliation through the command center's existing IO.

Sync and dispatch freshness checks call ``enrich``; ordinary seat status reads
the projection. All refreshers share proactive client pacing, provider retry
budgets, caches, and nonblocking singleflight in the state directory.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlsplit

from integrations.command_center.collectors import LiveCollectors
from integrations.command_center.request_budget import RequestBudget, RequestDeferred
from integrations.shared_equipment.provider_io import redacted
from .locks import held
from .projector import normalize_equivalent

TTL = 60
TASK = re.compile(r"^github:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):(issue|pr):([1-9][0-9]*)$", re.I)
PR_URL = re.compile(r"^/repos/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pulls/([1-9][0-9]*)$")
SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
FULL_SHA = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
PINNED_COMPARE = re.compile(
    r"^repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/compare/"
    r"([0-9a-fA-F]{40}|[0-9a-fA-F]{64})\.\.\."
    r"([0-9a-fA-F]{40}|[0-9a-fA-F]{64})\?per_page=1&page=1$")


def _epoch(value):
    if value is None:
        return time.time()
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    return float(value)


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _jitter(key):
    return 1 + int(hashlib.sha256(key.encode()).hexdigest()[:4], 16) % 10


def _decode(value, default=None):
    try:
        return json.loads(value) if value else default
    except (ValueError, TypeError):
        return default


def _client_policy():
    """Local fleet policy, deliberately not an assertion about GitHub quota."""
    try:
        interval = float(os.environ.get("COMMONS_SWARM_GITHUB_INTERVAL_S", "3"))
        burst = int(os.environ.get("COMMONS_SWARM_GITHUB_BURST", "4"))
    except ValueError as exc:
        raise ValueError("swarm GitHub interval/burst configuration must be numeric") from exc
    if not math.isfinite(interval) or not 1 <= interval <= 3600 or not 1 <= burst <= 20:
        raise ValueError("swarm GitHub interval must be 1..3600 seconds and burst must be 1..20")
    return {"kind": "client_policy", "interval_seconds": interval, "burst": burst}


def _error(exc):
    code, status = getattr(exc, "code", type(exc).__name__), getattr(exc, "http_status", None)
    metadata = dict(getattr(exc, "metadata", {}) or {})
    status = metadata.get("http_status", status)
    message = str(redacted(str(exc)))[:600]
    if isinstance(exc, RequestDeferred) or code == "github_rate_limited":
        state = "rate_limited"
    elif status == 401:
        state = "connector_unauthenticated"
    elif status == 403 and any(term in message.lower() for term in ("policy", "saml", "ip allow", "organization has blocked")):
        state = "repository_policy_refusal"
    elif status == 403:
        state = "account_lacks_permission"
    elif status == 404:
        state = "resource_missing_or_inaccessible"
    elif code == "github_transport_failed" and shutil.which("gh") is None:
        state = "tool_not_discovered"
    else:
        state = "provider_failure"
    return {"code": code, "error_state": state, "http_status": status,
            "message": message, **redacted(metadata)}


class _Deferred(Exception):
    def __init__(self, reason, retry_at=None, error=None):
        self.reason, self.retry_at, self.error = reason, retry_at, error


def _pr_endpoint(url):
    parsed = urlsplit(str(url or ""))
    if parsed.netloc != "api.github.com":
        return None
    match = PR_URL.fullmatch(parsed.path)
    return parsed.path.lstrip("/") if match else None


def _artifact_spec(task):
    """Only an explicitly complete commit artifact can close a non-PR task."""
    if not isinstance(task, dict):
        return None
    artifact, repo = task.get("artifact"), task.get("repo")
    if (not isinstance(artifact, dict) or artifact.get("kind") != "commit"
            or artifact.get("complete") is not True or not isinstance(repo, str)
            or not REPO.fullmatch(repo)):
        return None
    sha, branch = artifact.get("sha"), artifact.get("target_branch")
    if (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha)
            or not isinstance(branch, str) or not branch.strip()):
        return None
    return {"repo": repo, "sha": sha.lower(), "target_branch": branch}


def _compact(endpoint, data):
    """Cache provider evidence, not discussion bodies or account metadata."""
    if "/git/ref/heads/" in endpoint:
        obj = data.get("object") if isinstance(data, dict) else None
        if not isinstance(obj, dict) or not SHA.fullmatch(str(obj.get("sha", ""))):
            raise ValueError("github_branch_response_invalid")
        return {"sha": obj["sha"], "ref": data.get("ref")}
    if "/compare/" in endpoint:
        if not isinstance(data, dict) or data.get("status") not in {"ahead", "behind", "identical", "diverged"}:
            raise ValueError("github_compare_response_invalid")
        return {"status": data["status"], "ahead_by": data.get("ahead_by"),
                "behind_by": data.get("behind_by"), "html_url": data.get("html_url"),
                "base_sha": (data.get("base_commit") or {}).get("sha"),
                "merge_base_sha": (data.get("merge_base_commit") or {}).get("sha")}
    if "/timeline?" in endpoint:
        if not isinstance(data, list):
            raise ValueError("github_timeline_response_invalid")
        result = []
        for event in data:
            source = event.get("source") or {}
            issue = source.get("issue") or {}
            pull = issue.get("pull_request") or {}
            result.append({"id": event.get("id"), "event": event.get("event"),
                           "created_at": event.get("created_at"), "commit_id": event.get("commit_id"),
                           "pull_url": pull.get("url")})
        return result
    if "/commits/" in endpoint and "/pulls?" in endpoint:
        if not isinstance(data, list):
            raise ValueError("github_commit_pulls_response_invalid")
        return [{"url": row.get("url")} for row in data]
    if not isinstance(data, dict) or not isinstance(data.get("number"), int):
        raise ValueError("github_item_response_invalid")
    result = {name: data.get(name) for name in ("number", "state", "state_reason", "updated_at", "closed_at", "html_url")}
    if "/pulls/" in endpoint:
        result.update({name: data.get(name) for name in ("merged", "merged_at", "merge_commit_sha")})
        for name in ("head", "base"):
            ref = data.get(name) or {}
            result[name] = {"sha": ref.get("sha"), "ref": ref.get("ref")}
        result["default_branch"] = (data.get("base", {}).get("repo") or {}).get("default_branch")
    return result


def _immutable_compare(endpoint, data):
    """Only complete ancestry evidence between full commit IDs is permanent."""
    match = PINNED_COMPARE.fullmatch(endpoint)
    return bool(match and isinstance(data, dict)
                and data.get("status") in {"ahead", "behind", "identical", "diverged"}
                and str(data.get("base_sha", "")).lower() == match[1].lower()
                and FULL_SHA.fullmatch(str(data.get("merge_base_sha", "")))
                and all(type(data.get(field)) is int and data[field] >= 0
                        for field in ("ahead_by", "behind_by")))


class _Refresh:
    def __init__(self, db, state_dir, equipment, max_calls, stamp):
        self.db, self.stamp, self.max_calls = db, stamp, max_calls
        self.calls = self.hits = 0
        self.client_policy = _client_policy()
        self.pacing_deferred = False
        self.pacing_retry_at = None
        self.collector = LiveCollectors(SimpleNamespace(state_dir=state_dir), equipment=equipment,
                                        config={"request_timeout_seconds": 15})
        # Same durable ledger and transport as ordinary command-center refresh.
        self.collector.request_budget = RequestBudget(state_dir, clock=lambda: self.stamp)

    def _bucket(self):
        row = self.db.execute("SELECT value FROM progress WHERE name='github_client_bucket'").fetchone()
        bucket = _decode(row["value"], {}) if row else {}
        previous = float(bucket.get("updated_at", self.stamp))
        interval, burst = self.client_policy["interval_seconds"], self.client_policy["burst"]
        remaining = min(burst, float(bucket.get("remaining", burst)) + max(0, self.stamp - previous) / interval)
        return {"remaining": max(0, remaining), "updated_at": max(self.stamp, previous)}

    def _save_bucket(self, bucket):
        self.db.execute("INSERT OR REPLACE INTO progress(name,value) VALUES('github_client_bucket',?)",
                        (json.dumps(bucket, sort_keys=True),))
        self.db.commit()

    def pace(self, endpoint):
        # The refresh flock serializes this read/update across all callers.
        # Charge cache misses only; persisting the balance survives restarts.
        if self.pacing_deferred:
            # This refresh has one fixed clock and holds the shared lock. Its
            # exhausted bucket cannot refill while later cache hits are read.
            raise _Deferred("shared_request_budget", self.pacing_retry_at + _jitter(endpoint))
        bucket = self._bucket()
        if bucket["remaining"] < 1:
            self.pacing_retry_at = (bucket["updated_at"] + (1 - bucket["remaining"])
                                    * self.client_policy["interval_seconds"])
            self._save_bucket(bucket)
            self.pacing_deferred = True
            raise _Deferred("shared_request_budget", self.pacing_retry_at + _jitter(endpoint))
        bucket["remaining"] -= 1
        self._save_bucket(bucket)

    def refund_pacing(self):
        bucket = self._bucket()
        bucket["remaining"] = min(self.client_policy["burst"], bucket["remaining"] + 1)
        self._save_bucket(bucket)

    def pacing_status(self):
        bucket = self._bucket()
        retry_at = (bucket["updated_at"] + (1 - bucket["remaining"])
                    * self.client_policy["interval_seconds"] if bucket["remaining"] < 1 else None)
        return {**self.client_policy, "remaining": round(bucket["remaining"], 3),
                "retry_not_before": _iso(retry_at) if retry_at else None}

    def get(self, endpoint):
        row = self.db.execute("SELECT * FROM responses WHERE endpoint=?", (endpoint,)).fetchone()
        if row and row["retry_at"] > self.stamp:
            raise _Deferred("provider_retry", row["retry_at"], _decode(row["error"]))
        if row and row["value"]:
            value = _decode(row["value"])
            if row["immutable"] or _immutable_compare(endpoint, value) or row["expires_at"] > self.stamp:
                self.hits += 1
                return value, row["observed_at"]
        if self.calls >= self.max_calls:
            raise _Deferred("call_budget")
        self.pace(endpoint)
        self.calls += 1
        try:
            data = _compact(endpoint, self.collector._github(endpoint))
        except Exception as exc:
            if isinstance(exc, RequestDeferred):
                self.calls -= 1  # No provider request happened.
                self.refund_pacing()
            error = _error(exc)
            retry_value = getattr(exc, "retry_not_before", None) or error.get("retry_not_before")
            retry_at = max(self.stamp + TTL, _epoch(retry_value)) if retry_value else self.stamp + TTL
            retry_at += _jitter(endpoint)
            self.db.execute("""INSERT INTO responses(endpoint,retry_at,error) VALUES(?,?,?)
                ON CONFLICT(endpoint) DO UPDATE SET retry_at=excluded.retry_at,error=excluded.error""",
                (endpoint, retry_at, json.dumps(error, sort_keys=True)))
            self.db.commit()
            raise _Deferred(error["error_state"], retry_at, error) from None
        immutable = ((isinstance(data, dict) and data.get("merged") is True
                      and bool(data.get("merge_commit_sha"))) or _immutable_compare(endpoint, data))
        self.db.execute("""INSERT INTO responses(endpoint,value,observed_at,expires_at,immutable,retry_at,error)
            VALUES(?,?,?,?,?,0,NULL) ON CONFLICT(endpoint) DO UPDATE SET value=excluded.value,
            observed_at=excluded.observed_at,expires_at=excluded.expires_at,immutable=excluded.immutable,
            retry_at=0,error=NULL""", (endpoint, json.dumps(data, sort_keys=True), self.stamp,
                                      self.stamp + TTL, int(immutable)))
        self.db.commit()
        return data, self.stamp

    def pr(self, repo, number, resolve_equivalent=True):
        data, observed = self.get(f"repos/{repo}/pulls/{number}")
        merged = data.get("merged")
        fact = {"provider": "github", "repo": repo, "pr": number,
                "source": f"repos/{repo}/pulls/{number}",
                "state": data.get("state"), "merged": merged, "merged_at": data.get("merged_at"),
                "merge_sha": data.get("merge_commit_sha") if merged is True else None,
                "head_sha": data["head"].get("sha"), "branch": data["head"].get("ref"),
                "base_sha": data["base"].get("sha"), "base_ref": data["base"].get("ref"),
                "updated_at": data.get("updated_at"), "url": data.get("html_url"),
                "observed_at": _iso(observed), "freshness": "immutable" if merged else "fresh"}
        if resolve_equivalent and data.get("state") == "closed" and merged is False:
            branch = data.get("default_branch") or ("main" if fact["base_ref"] == "main" else None)
            if not branch or not SHA.fullmatch(str(fact.get("head_sha", ""))):
                fact["reconciliation_pending"] = "target_branch_or_head_unknown"
                return fact
            try:
                equivalent = self.contains(repo, fact["head_sha"], branch)
            except _Deferred as exc:
                fact["reconciliation_pending"] = exc.reason
                if exc.error:
                    fact["reconciliation_error"] = exc.error
                if exc.retry_at:
                    fact["retry_not_before"] = _iso(exc.retry_at)
            else:
                fact["current_base_sha"] = equivalent["current_sha"]
                fact["ancestry"] = equivalent["evidence"]
                if equivalent["contains"]:
                    fact["equivalent"] = {"provider": "github", "integrated": True,
                        "artifact_landed": True, "artifact_sha": fact["head_sha"],
                        "landed_sha": equivalent["current_sha"], "repo": repo,
                        "branch": branch, "url": f"https://github.com/{repo}/commit/{equivalent['current_sha']}",
                        "source": equivalent["evidence"]["endpoint"],
                        "evidence": equivalent["evidence"], "observed_at": equivalent["observed_at"]}
        return fact

    def contains(self, repo, head, branch):
        # Resolve the branch now; a PR's base.sha can be its historical base.
        # Pin both sides of the comparison so a moving branch cannot change
        # which commit this evidence proves was already integrated.
        branch_endpoint = f"repos/{repo}/git/ref/heads/{quote(branch, safe='')}"
        current, observed = self.get(branch_endpoint)
        current_sha = current["sha"]
        if (isinstance(head, str) and FULL_SHA.fullmatch(head)
                and isinstance(current_sha, str) and head.lower() == current_sha.lower()):
            # The branch observation already proves this exact commit is its
            # head. Record that derivation without inventing a compare read.
            evidence = {"kind": "exact_head_ancestry", "proof_method": "target_head_identity",
                        "head_sha": head, "target_sha": current_sha, "target_branch": branch,
                        "status": "identical", "behind_by": 0, "merge_base_sha": head,
                        "endpoint": branch_endpoint}
            return {"contains": True, "current_sha": current_sha, "evidence": evidence,
                    "observed_at": _iso(observed)}
        endpoint = f"repos/{repo}/compare/{head}...{current_sha}?per_page=1&page=1"
        comparison, compared_at = self.get(endpoint)
        contains = (comparison["status"] in {"ahead", "identical"}
                    and comparison.get("behind_by") == 0
                    and comparison.get("base_sha") == head
                    and comparison.get("merge_base_sha") == head)
        evidence = {"kind": "exact_head_ancestry", "head_sha": head,
                    "target_sha": current_sha, "target_branch": branch,
                    "status": comparison["status"], "behind_by": comparison.get("behind_by"),
                    "merge_base_sha": comparison.get("merge_base_sha"), "endpoint": endpoint}
        return {"contains": contains, "current_sha": current_sha, "evidence": evidence,
                "observed_at": _iso(min(observed, compared_at))}

    def artifact(self, spec):
        proof = self.contains(spec["repo"], spec["sha"], spec["target_branch"])
        return {"provider": "github", "repo": spec["repo"],
                "artifact": {"kind": "commit", "sha": spec["sha"],
                             "target_branch": spec["target_branch"], "complete": True},
                "artifact_landed": proof["contains"], "artifact_sha": spec["sha"],
                "landed_sha": proof["current_sha"] if proof["contains"] else None,
                "current_base_sha": proof["current_sha"], "ancestry": proof["evidence"],
                "source": proof["evidence"]["endpoint"], "observed_at": proof["observed_at"],
                "freshness": "fresh"}

    def issue(self, key, repo, number):
        data, observed = self.get(f"repos/{repo}/issues/{number}")
        fact = {"provider": "github", "repo": repo, "issue": number, "state": data.get("state"),
                "source": f"repos/{repo}/issues/{number}",
                "state_reason": data.get("state_reason"), "merged": None, "merge_sha": None,
                "updated_at": data.get("updated_at"), "observed_at": _iso(observed),
                "url": data.get("html_url"), "freshness": "fresh"}
        # An open issue or a manually closed issue is not evidence of shipment.
        if data.get("state") != "closed":
            return fact
        signature = [data.get("updated_at"), data.get("state"), data.get("closed_at")]
        row = self.db.execute("SELECT value FROM timelines WHERE task_key=?", (key,)).fetchone()
        progress = _decode(row["value"], {}) if row else {}
        if progress.get("signature") != signature:
            progress = {"signature": signature, "page": 1, "complete": False, "candidates": [],
                        "candidate_cursor": 0, "closed": None}

        def save():
            self.db.execute("INSERT OR REPLACE INTO timelines(task_key,value) VALUES(?,?)",
                            (key, json.dumps(progress, sort_keys=True)))
            self.db.commit()

        if not progress["complete"]:
            page = progress["page"]
            events, _ = self.get(f"repos/{repo}/issues/{number}/timeline?per_page=100&page={page}")
            for event in events:
                if event.get("event") == "closed":
                    progress["closed"] = event
                elif event.get("event") == "reopened":
                    progress["closed"] = None
                endpoint = _pr_endpoint(event.get("pull_url"))
                if endpoint and endpoint not in progress["candidates"]:
                    progress["candidates"].append(endpoint)
            progress["complete"] = len(events) < 100
            progress["page"] = page + 1
            save()
        fact["timeline"] = {"next_page": progress["page"], "complete": progress["complete"]}
        if not progress["complete"]:
            fact["reconciliation_pending"] = "timeline_pagination"
            return fact
        closed = progress.get("closed") or {}
        commit = closed.get("commit_id")
        if not isinstance(commit, str) or not SHA.fullmatch(commit):
            fact["reconciliation_pending"] = "closed_without_linked_merge"
            return fact
        if not progress.get("commit_pulls_complete"):
            page = progress.get("commit_pulls_page", 1)
            pulls, _ = self.get(f"repos/{repo}/commits/{commit}/pulls?per_page=100&page={page}")
            related = [endpoint for pull in pulls if (endpoint := _pr_endpoint(pull.get("url")))]
            # Prefer the closing commit's exact associated PRs. References alone
            # may point to unrelated discussion PRs and cannot close the issue.
            progress["candidates"] = list(dict.fromkeys(related + progress["candidates"]))
            progress["commit_pulls_complete"] = len(pulls) < 100
            progress["commit_pulls_page"] = page + 1
            progress["candidate_cursor"] = 0
            save()
        candidates = progress["candidates"]
        start = progress["candidate_cursor"] % len(candidates) if candidates else 0
        for offset in range(len(candidates)):
            index = (start + offset) % len(candidates)
            endpoint = candidates[index]
            match = PR_URL.fullmatch("/" + endpoint)
            try:
                pr = self.pr(match[1], int(match[2]), resolve_equivalent=False)
            except _Deferred:
                progress["candidate_cursor"] = index
                save()
                raise
            progress["candidate_cursor"] = (index + 1) % len(candidates)
            save()
            # REST closed.commit_id is the closes/fixes commit. A mere timeline
            # cross-reference is not enough: bind it to the actual merged PR.
            if pr.get("merged") is True and pr.get("merge_sha") == commit:
                fact.update({"merged": True, "merge_sha": commit, "merged_at": pr.get("merged_at"),
                             "pr": pr["pr"], "pr_repo": pr["repo"], "pr_url": pr.get("url"),
                             "head_sha": pr.get("head_sha"), "branch": pr.get("branch"),
                             "base_sha": pr.get("base_sha"), "base_ref": pr.get("base_ref"),
                             "closure_evidence": {"event_id": closed.get("id"), "commit_id": commit,
                                                  "pr": pr["pr"], "repo": pr["repo"]}})
                return fact
        fact["reconciliation_pending"] = "closing_commit_has_no_verified_merged_pr"
        return fact


def _cached(path, keys, stamp):
    if not keys or not path.exists():
        return {}
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0)
        try:
            result = {}
            wanted = sorted(keys)
            for offset in range(0, len(wanted), 500):
                batch = wanted[offset:offset + 500]
                placeholders = ",".join("?" for _ in batch)
                for key, encoded, expiry in db.execute(
                        "SELECT task_key,value,expires_at FROM facts WHERE task_key IN (" +
                        placeholders + ")", batch):
                    fact = _decode(encoded, {})
                    for field in ("equivalent", "superseded_by"):
                        if field in fact:
                            fact[field] = normalize_equivalent(fact[field])
                    if fact.get("freshness") != "immutable" and expiry <= stamp:
                        fact["freshness"] = "stale"
                    result[key] = fact
            return result
        finally:
            db.close()
    except sqlite3.OperationalError:
        return {}


def enrich(tasks: dict, state_dir: Path, equipment=None, max_calls=4, now=None):
    """Return current/cached facts and explicit coverage using <= max_calls reads.

    ``tasks`` is keyed by canonical task_key. A task with an explicit ``repo``
    and ``artifact={kind: 'commit', sha: <40 hex>, target_branch: 'main',
    complete: True}`` can reconcile a complete direct-publication artifact
    without a PR. Generic head_sha/branch activity never implies completion.
    Mutable provider responses have a
    fixed 60-second TTL; there is intentionally no force-refresh bypass. A busy
    refresher returns its cache immediately, without sleeping or provider IO.
    Cache misses also share a durable token bucket (burst 4, one read every
    3 seconds by default). This is client policy, not provider quota. The
    bounded COMMONS_SWARM_GITHUB_INTERVAL_S / COMMONS_SWARM_GITHUB_BURST
    environment settings tune it. Existing provider Retry-After/reset budgets
    still apply independently and are never shortened. No caller sleeps.
    Timeline page and task rotation persist across calls/processes. Null facts
    stay unknown. Provider failures do not erase prior successful observations.
    """
    if not isinstance(tasks, dict):
        raise ValueError("tasks must be keyed by canonical task_key")
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or not 0 <= max_calls <= 100:
        raise ValueError("max_calls must be an integer from 0 to 100")
    stamp, state_dir = _epoch(now), Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "swarm-provider-refresh.sqlite3"
    artifacts = {key: spec for key, task in tasks.items() if (spec := _artifact_spec(task))}
    keys = sorted(key for key in tasks if isinstance(key, str) and (TASK.fullmatch(key) or key in artifacts))
    facts = _cached(path, set(keys), stamp)
    result = {"provider_facts": facts, "deferred": [], "calls": 0,
              "coverage": {"tasks": len(keys), "complete": False, "cached": len(facts),
                           "fresh": 0, "pending": len(keys), "source": "live_github_and_shared_cache",
                           "shared_request_policy": {**_client_policy(), "remaining": None,
                                                     "retry_not_before": None}}}
    with held(state_dir / "swarm-provider-refresh.lock") as lock_state:
        if lock_state != "acquired":
            reason = "refresh_in_progress" if lock_state == "busy" else "refresh_lock_unavailable"
            result["deferred"] = [{"reason": reason, "retry_not_before": _iso(stamp + TTL)}]
            return result
        db = sqlite3.connect(path, timeout=0)
        db.row_factory = sqlite3.Row
        try:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS responses(endpoint TEXT PRIMARY KEY,value TEXT,
                    observed_at REAL NOT NULL DEFAULT 0,expires_at REAL NOT NULL DEFAULT 0,
                    immutable INTEGER NOT NULL DEFAULT 0,retry_at REAL NOT NULL DEFAULT 0,error TEXT);
                CREATE TABLE IF NOT EXISTS facts(task_key TEXT PRIMARY KEY,value TEXT,expires_at REAL);
                CREATE TABLE IF NOT EXISTS timelines(task_key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE IF NOT EXISTS progress(name TEXT PRIMARY KEY,value TEXT);
            """)
            refresh = _Refresh(db, state_dir, equipment, max_calls, stamp)
            previous = db.execute("SELECT value FROM progress WHERE name='last_task' ").fetchone()
            request_cursor = previous["value"] if previous else ""
            previous_cache = db.execute("SELECT value FROM progress WHERE name='last_cache_task'").fetchone()
            cache_cursor = previous_cache["value"] if previous_cache else request_cursor
            cursor = request_cursor if max_calls else cache_cursor
            ordered = [key for key in keys if key > cursor] + [key for key in keys if key <= cursor]
            visited = []
            advance_requests = max_calls > 0
            for key in ordered[:200]:
                # get() checks reusable responses before enforcing the network
                # budget or shared pacing, so retained responses can reconcile
                # throughout this bounded window after either is exhausted.
                match = TASK.fullmatch(key)
                calls_before = refresh.calls
                budget_deferred = False
                try:
                    if key in artifacts and (match is None or match[2].lower() != "pr"):
                        fact = refresh.artifact(artifacts[key])
                    else:
                        repo, kind, number = match[1], match[2].lower(), int(match[3])
                        fact = refresh.pr(repo, number) if kind == "pr" else refresh.issue(key, repo, number)
                    fact["task_key"] = key
                    facts[key] = fact
                    db.execute("INSERT OR REPLACE INTO facts(task_key,value,expires_at) VALUES(?,?,?)",
                               (key, json.dumps(fact, sort_keys=True), stamp + TTL))
                    result["coverage"]["fresh"] += 1
                except _Deferred as exc:
                    budget_deferred = exc.reason in {"call_budget", "shared_request_budget"}
                    deferred = {"task_key": key, "reason": exc.reason}
                    if exc.retry_at:
                        deferred["retry_not_before"] = _iso(exc.retry_at)
                    if exc.error:
                        deferred["error"] = exc.error
                    result["deferred"].append(deferred)
                visited.append(key)
                if advance_requests:
                    # A partially served task rotates fairly; its endpoint/page
                    # progress is retained. An unserved budget miss resumes next.
                    if not budget_deferred or refresh.calls > calls_before:
                        request_cursor = key
                        db.execute("INSERT OR REPLACE INTO progress(name,value) VALUES('last_task',?)", (key,))
                    if budget_deferred:
                        advance_requests = False
                if not max_calls:
                    # Positive refreshes must not reset an independent cache
                    # sweep when shared pacing stops their first request.
                    cache_cursor = key
                    db.execute("INSERT OR REPLACE INTO progress(name,value) VALUES('last_cache_task',?)", (key,))
                db.commit()
            unvisited = len(keys) - len(visited)
            if unvisited:
                result["deferred"].append({"reason": "call_budget_or_task_window", "tasks": unvisited})
            pending = sum(key not in facts or facts[key].get("freshness") == "stale"
                          or bool(facts[key].get("reconciliation_pending")) for key in keys)
            result["calls"] = refresh.calls
            if max_calls and previous_cache is None:
                cache_cursor = request_cursor
            result["coverage"].update({"complete": pending == 0 and not result["deferred"],
                                       "pending": pending, "visited": len(visited),
                                       "cache_hits": refresh.hits,
                                       "shared_request_policy": refresh.pacing_status(),
                                       "next_after_task_key": request_cursor,
                                       "cache_next_after_task_key": cache_cursor})
            return result
        finally:
            db.close()
