"""Bounded read-only provider collection for the existing command center.

Configuration belongs in the private state directory. No account, channel, or
private observation is bundled here. Connector-fed sources enter WorkstreamStore
through ingest; this module does not imitate Gmail/Airtable/native connectors.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from time import monotonic
from threading import Lock
from urllib.parse import quote, urlencode, urlsplit

from .request_budget import RequestBudget, RequestDeferred
from .slack_threads import read_channel, resolve_thread_root

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
HOUSEKEEPING = {"channel_join", "channel_leave", "channel_topic", "channel_purpose",
                "channel_name", "channel_archive", "channel_unarchive"}
UTC = timezone.utc


def now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def timestamp(value):
    if value is None or value == "":
        return None
    try:
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", str(value)):
            return datetime.fromtimestamp(float(value), UTC).isoformat().replace("+00:00", "Z")
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def latest(items):
    values = [timestamp(item.get("activity_observed_at")) for item in items]
    return max((value for value in values if value),
               key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")), default=None)


def text(value, limit=4000):
    return str(value or "")[:limit]


def link(url):
    return [{"kind": "open", "label": "Open original", "url": url}] if url else []


class SourceFailure(RuntimeError):
    def __init__(self, code, metadata=None):
        self.code = re.sub(r"[^A-Za-z0-9_.:-]", "_", str(code))[:120]
        self.metadata = metadata or {}
        super().__init__(self.code)


class LiveCollectors:
    """Read providers through existing shared equipment and ingest source batches."""

    def __init__(self, store, config=None, equipment=None, clock=now, cancel_event=None):
        self.store, self.config, self.clock = store, config or {}, clock
        if not isinstance(self.config, dict):
            raise ValueError("Collector config must be an object.")
        self.github_config = self.config.get("github", {})
        self.slack_config = self.config.get("slack", {})
        self.documents = self.config.get("documents", [])
        if not isinstance(self.github_config, dict) or not isinstance(self.slack_config, dict):
            raise ValueError("github/slack config must be objects.")
        if not isinstance(self.documents, list):
            raise ValueError("documents config must be a list.")
        self.page_size = self._bound(self.config.get("page_size", 30), 1, 100)
        self.max_pages = self._bound(self.config.get("max_pages", 2), 1, 10)
        self.max_threads = self._bound(self.slack_config.get("max_threads_per_channel", 0), 0, 8)
        self.max_thread_pages = self._bound(self.slack_config.get("max_thread_pages", 2), 1, 10)
        self.max_workers = self._bound(self.config.get("max_workers", 4), 1, 4)
        self.refresh_deadline_seconds = self._bound(self.config.get("refresh_deadline_seconds", 180), 1, 600)
        self.cancel_event, self.deadline = cancel_event, None
        self._document_heads, self._document_heads_lock = {}, Lock()
        self.request_budget = RequestBudget(getattr(store, "state_dir", None),
            fallback_seconds=self.config.get("rate_limit_fallback_seconds", 60))
        self.lookback_days = self._bound(self.github_config.get("lookback_days", 14), 1, 90)
        if equipment is None:
            from integrations.shared_equipment.provider_io import GitHubSlackEquipment
            timeout = self._bound(self.config.get("request_timeout_seconds", 25), 1, 30)
            def bounded_runner(command, **kwargs):
                kwargs["timeout"] = min(timeout, kwargs.get("timeout", timeout))
                return subprocess.run(command, **kwargs)
            equipment = GitHubSlackEquipment(gh_runner=bounded_runner)
        self.equipment = equipment

    @staticmethod
    def _bound(value, low, high):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError("Collector bound must be an integer from %s to %s." % (low, high))
        return value

    def _source(self, source_id, provider, label, scope):
        return {"id": source_id, "provider": provider, "label": label,
                "sync_mode": "direct", "scope": scope, "stale_after_seconds": 900}

    def _batch(self, source, items, complete=True, notes=None, error=None, degraded=False):
        observed = self.clock()
        source = {**source, "observed_at": observed, "activity_as_of": latest(items),
                  "status": "error" if error and not items else ("degraded" if error or degraded else "live"),
                  "error": error, "coverage": {"complete": bool(complete and not error),
                  "pagination_remaining": not complete, "notes": notes or []}}
        payload = {"source": source, "items": items}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return {"operation_id": "collect:" + digest, **payload}

    def _check_deadline(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise SourceFailure("refresh_cancelled")
        if self.deadline is not None and monotonic() >= self.deadline:
            raise SourceFailure("refresh_deadline_reached")

    def _safe(self, source, reader):
        try:
            self._check_deadline()
            return reader()
        except RequestDeferred as exc:
            # This read was deferred. Preserve the last source snapshot.
            return {"deferred": {"source_id": source["id"], "provider": source["provider"],
                    "scope": exc.scope, "reason": exc.reason,
                    "retry_not_before": exc.retry_not_before}}
        except Exception as exc:
            # Provider messages may contain private request data; retain fixed codes.
            extra = getattr(exc, "metadata", {}) if isinstance(exc, SourceFailure) else {}
            return self._batch({**source, "metadata": {"request_budget": extra}} if extra else source,
                               [], complete=False, error=getattr(exc, "code", type(exc).__name__),
                               notes=["Read failed; retain previous source items and last good activity."])

    def _github(self, endpoint):
        self._check_deadline()
        path = urlsplit(endpoint).path.lstrip("/")
        resource = "code_search" if path == "search/code" else "search" if path.startswith("search/") else "core"
        scope = "github:GET:" + resource
        # Primary quotas are independent. Secondary/unknown limits (including
        # persisted deadlines from older collectors) still pause every read.
        self.request_budget.acquire(scope, shared_scopes=("github:GET",))
        try:
            response = self.equipment.github(endpoint, method="GET")
            self.request_budget.succeeded(scope, shared_scopes=("github:GET",))
            return response
        except Exception as exc:
            if getattr(exc, "http_status", None) == 429 or getattr(exc, "code", None) == "github_rate_limited":
                reset = getattr(exc, "rate_limit_reset", None) if getattr(exc, "rate_limit_remaining", None) == 0 else None
                reported_resource = getattr(exc, "rate_limit_resource", None)
                primary = (getattr(exc, "rate_limit_kind", None) == "primary"
                           and reported_resource in (None, resource))
                limited_scope = scope if primary else "github:GET"
                # One response can report both a secondary limit and primary
                # exhaustion. Keep the resource reset out of the shared delay.
                reset_scope = (scope if not primary and reset is not None
                               and reported_resource in (None, resource) else None)
                retry = self.request_budget.rate_limited(limited_scope, getattr(exc, "retry_after", None),
                    reset_at=reset, reset_scope=reset_scope)
                raise SourceFailure("github_rate_limited", {"http_status": getattr(exc, "http_status", None),
                    "rate_limit_remaining": getattr(exc, "rate_limit_remaining", None),
                    "rate_limit_reset": reset, "rate_limit_resource": reported_resource,
                    "rate_limit_kind": getattr(exc, "rate_limit_kind", None), **retry}) from None
            raise

    def _slack_read(self, method, payload):
        self._check_deadline()
        scope = "slack:" + method
        self.request_budget.acquire(scope)
        response = self.equipment.slack(method, payload)
        if isinstance(response, dict) and response.get("ok") is True:
            self.request_budget.succeeded(scope)
        if isinstance(response, dict) and response.get("ok") is not True:
            if response.get("status") == 429 or response.get("error") == "ratelimited":
                retry = self.request_budget.rate_limited(scope, response.get("retry_after"))
                raise SourceFailure("slack_rate_limited", {"http_status": response.get("status"),
                    **retry}) from None
        return response

    def _pages(self, endpoint, key=None, *, progress=None, read_label=None):
        result, total, incomplete, seen_ids = [], None, False, set()
        for page in range(1, self.max_pages + 1):
            suffix = "&" if "?" in endpoint else "?"
            try:
                response = self._github(endpoint + suffix + urlencode({"per_page": self.page_size, "page": page}))
                rows = response.get(key) if key and isinstance(response, dict) else response
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    raise SourceFailure("github_response_shape")
                # Validate the whole envelope before appending any of this
                # page. A malformed later response must retain earlier pages
                # with incomplete coverage, just like a transport failure.
                if isinstance(response, dict):
                    if "total_count" in response:
                        total = response["total_count"]
                        if type(total) is not int or total < 0:
                            raise SourceFailure("github_pagination_shape")
                    if ("incomplete_results" in response
                            and type(response["incomplete_results"]) is not bool):
                        raise SourceFailure("github_pagination_shape")
                    incomplete = incomplete or bool(response.get("incomplete_results"))
            except Exception as exc:
                if progress is None or not progress["pages_read"]:
                    raise
                failure = {"slice": read_label, "page": page,
                           "code": getattr(exc, "code", type(exc).__name__)}
                if isinstance(exc, RequestDeferred):
                    failure.update({"scope": exc.scope, "retry_not_before": exc.retry_not_before})
                elif isinstance(exc, SourceFailure) and exc.metadata:
                    failure["request_budget"] = exc.metadata
                progress["failures"].append(failure)
                return result, False
            # GitHub page boundaries can overlap while results change between requests.
            # Stable provider ids must count once or overlap can manufacture completeness.
            for row in rows:
                row_id = row.get("id") if isinstance(row, dict) else None
                marker = ((type(row_id), row_id) if isinstance(row_id, (str, int))
                          and not isinstance(row_id, bool) else None)
                if marker is None or marker not in seen_ids:
                    result.append(row)
                    if marker is not None:
                        seen_ids.add(marker)
            if progress is not None:
                progress["pages_read"] += 1
            if not incomplete and total is not None and len(result) >= total:
                # An explicit complete count avoids probing an extra empty
                # page when the final page exactly fills the requested size.
                return result, True
            if len(rows) < self.page_size:
                # A short page cannot overrule an explicit larger result count.
                return result, not incomplete and (total is None or len(result) >= total)
        return result, not incomplete and isinstance(total, int) and len(result) >= total

    def _github_batch(self, source, items, complete, notes, progress):
        failures = progress["failures"]
        if failures:
            source = {**source, "metadata": {**source.get("metadata", {}), "github_reads": progress}}
            notes = [*notes, "Valid earlier pages retained; failed slices never authorize removal."]
        return self._batch(source, items, complete, notes,
                           error=failures[0]["code"] if failures and not progress["pages_read"] else None,
                           degraded=bool(failures))

    @staticmethod
    def _repository(value):
        if not isinstance(value, str) or not REPO.fullmatch(value):
            raise ValueError("Repository must be owner/name.")
        return value

    def _repository_batch(self, login):
        source = self._source("github:repositories", "GitHub", "Owned repositories", {"owner": login})
        progress = {"pages_read": 0, "failures": []}
        rows, complete = self._pages("user/repos?affiliation=owner&sort=pushed&direction=desc",
                                     progress=progress, read_label="owned_repositories")
        items = []
        for row in {row["full_name"]: row for row in rows}.values():
            repo = self._repository(row.get("full_name"))
            url = row.get("html_url", "https://github.com/" + repo)
            items.append({"id": "github:repo:" + repo, "kind": "repository",
                "title": repo, "status": "archived" if row.get("archived") else "active",
                "owner": row.get("owner", {}).get("login"), "project": repo,
                "updated_at": timestamp(row.get("pushed_at")),
                "activity_observed_at": timestamp(row.get("pushed_at")), "url": url,
                "summary": text(row.get("description")), "next_action": None,
                "refs": {"repository": repo, "default_branch": row.get("default_branch"),
                         "private": row.get("private"), "open_issues_count": row.get("open_issues_count")},
                "actions": link(url)})
        return self._github_batch(source, items, complete,
                           ["Repository catalog; active means not archived, not an executing job."], progress)

    def _pull_requests(self, login):
        source = self._source("github:prs", "GitHub", "Open and recently updated pull requests",
                              {"author_or_owner": login})
        since = (datetime.now(UTC) - timedelta(days=self.lookback_days)).date().isoformat()
        rows, complete = {}, True
        progress = {"pages_read": 0, "failures": []}
        for qualifier in ("author:" + login, "user:" + login):
            # Keep the windows disjoint so recently active open PRs do not
            # consume the bounded slots intended for recently closed work.
            for window in ("is:open", "is:closed updated:>=" + since):
                found, page_complete = self._pages("search/issues?" + urlencode({
                    "q": "is:pr " + qualifier + " " + window, "sort": "updated", "order": "desc"}), "items",
                    progress=progress, read_label=qualifier.partition(":")[0] + ":" + window)
                complete = complete and page_complete
                for item in found:
                    rows[str(item.get("id", item.get("html_url")))] = item
                if progress["failures"]:
                    break
            if progress["failures"]:
                break
        items = []
        for row in rows.values():
            repo = str(row.get("repository_url", "")).removeprefix("https://api.github.com/repos/")
            self._repository(repo)
            number, url = row["number"], row.get("html_url")
            status = "merged" if row.get("pull_request", {}).get("merged_at") else row.get("state", "unknown")
            items.append({"id": "github:pr:" + repo + "#" + str(number), "kind": "pull_request",
                "title": text(row.get("title"), 500), "status": status,
                "owner": row.get("user", {}).get("login"), "project": repo,
                "created_at": timestamp(row.get("created_at")),
                "updated_at": timestamp(row.get("updated_at")),
                "activity_observed_at": timestamp(row.get("updated_at")), "url": url,
                "summary": text(row.get("body")), "next_action": None,
                "refs": {"repository": repo, "number": number, "draft": row.get("draft"),
                         "merged_at": timestamp(row.get("pull_request", {}).get("merged_at")),
                         "closed_at": timestamp(row.get("closed_at")),
                         "assignees": [x.get("login") for x in row.get("assignees", [])],
                         "labels": [x.get("name") for x in row.get("labels", [])]},
                "actions": link(url)})
        return self._github_batch(source, items, complete,
                           ["Provider state is preserved; a closed PR without merged_at is not labeled merged."], progress)

    def _actions(self, repo):
        source = self._source("github:actions:" + repo, "GitHub", repo + " builds", {"repository": repo})
        rows, complete, active_complete = {}, True, True
        progress = {"pages_read": 0, "failures": []}
        queried_statuses = []
        for status in ("in_progress", "queued", None):
            endpoint = "repos/" + repo + "/actions/runs" + ("?status=" + status if status else "")
            if status is not None:
                queried_statuses.append(status)
            found, page_complete = self._pages(endpoint, "workflow_runs",
                progress=progress, read_label=status or "recent")
            complete = complete and page_complete
            if status in ("in_progress", "queued"):
                active_complete = active_complete and page_complete
            for row in found:
                rows[str(row["id"])] = row
            if progress["failures"]:
                break
        items = []
        for row in rows.values():
            url = row.get("html_url")
            requires_action = row.get("status") == "completed" and row.get("conclusion") == "action_required"
            items.append({"id": "github:run:" + repo + ":" + str(row["id"]), "kind": "build",
                "title": text(row.get("display_title") or row.get("name"), 500),
                "status": row.get("conclusion") if row.get("status") == "completed" else row.get("status", "unknown"),
                "owner": row.get("actor", {}).get("login"), "project": repo,
                "created_at": timestamp(row.get("created_at")),
                "updated_at": timestamp(row.get("updated_at")),
                "activity_observed_at": timestamp(row.get("updated_at")), "url": url,
                "summary": text(row.get("name"), 500), "needs_attention": requires_action,
                "next_action": "Inspect the workflow run for the required action or approval." if requires_action else None,
                "refs": {"run_id": row["id"], "run_attempt": row.get("run_attempt"),
                         "head_sha": row.get("head_sha"), "head_branch": row.get("head_branch"),
                         "provider_status": row.get("status"), "conclusion": row.get("conclusion")},
                "actions": link(url)})
        source = {**source, "metadata": {
            "active_queue_coverage": {
                "complete": active_complete,
                "queried_statuses": queried_statuses,
            }
        }}
        return self._github_batch(source, items, complete,
                           ["Active/queued runs plus bounded recent history; pagination caps stay visible.",
                            "metadata.active_queue_coverage distinguishes active-run completeness from capped history."], progress)

    def _slack(self, channel):
        channel_id, label = channel["id"], channel.get("label", channel["id"])
        source = self._source("slack:" + channel_id, "Slack", label, {"channel_id": channel_id})
        rows, metadata, complete = read_channel(self._slack_read, channel_id,
            page_size=self.page_size, max_pages=self.max_pages,
            max_threads=self.max_threads, max_thread_pages=self.max_thread_pages)
        items = []
        workspace = self.slack_config.get("workspace_url", "")
        for row in {str(row.get("ts")): row for row in rows if isinstance(row, dict)}.values():
            if row.get("subtype") in HOUSEKEEPING or not row.get("ts"):
                continue
            ts = str(row["ts"])
            resolution = resolve_thread_root(row, channel_id)
            body = text(row.get("text"))
            url = workspace.rstrip("/") + "/archives/" + channel_id + "/p" + ts.replace(".", "") if workspace else None
            updated = timestamp(row.get("edited", {}).get("ts") or ts)
            # A new reply is thread activity even when its parent text is unchanged.
            activity = latest({"activity_observed_at": value}
                              for value in (updated, row.get("latest_reply")))
            items.append({"id": "slack:" + channel_id + ":" + ts, "kind": "slack_thread",
                "title": body.splitlines()[0][:500] if body else "Slack message",
                "status": "posted", "owner": row.get("user") or row.get("bot_id"),
                "project": channel.get("project") or label, "updated_at": updated,
                "activity_observed_at": activity, "url": url, "summary": body,
                "next_action": None, "refs": {"channel_id": channel_id, "message_ts": ts,
                    "thread_ts": resolution["thread_ts"], "root_resolution": resolution["state"],
                    "root_reason": resolution["reason"], "reply_count": row.get("reply_count"),
                    "latest_reply": row.get("latest_reply")}, "actions": link(url)})
        batch = self._batch({**source, "metadata": metadata}, items, complete,
            ["Membership housekeeping omitted from work view; original Slack history remains unchanged.",
             "Reply coverage applies only to threads discovered in this bounded channel history.",
             "Partial valid pages are ingested; missing pages and threads never authorize removal."])
        if (metadata["history"]["error"] or metadata["unresolved_thread_roots_count"]
                or any(row["error"] for row in metadata["thread_coverage"])):
            # source.error would make WorkstreamStore discard even valid rows.
            # Preserve per-slice failures in metadata, with incomplete coverage.
            batch["source"]["status"] = "degraded"
        payload = {key: value for key, value in batch.items() if key != "operation_id"}
        batch["operation_id"] = "collect:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return batch

    def _document_head(self, repo, ref):
        """Resolve a repository/ref once per refresh, including parallel readers."""
        self._check_deadline()
        key = (repo, ref)
        with self._document_heads_lock:
            pending = self._document_heads.get(key)
            leader = pending is None
            if leader:
                pending = self._document_heads[key] = Future()
        if leader:
            try:
                head = self._github("repos/" + repo + "/commits/" + quote(ref, safe=""))
                sha = head.get("sha") if isinstance(head, dict) else None
                if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                    raise SourceFailure("github_commit_shape")
                pending.set_result(sha)
            except BaseException as exc:
                # Wake every waiter on failure as well; do not multiply a
                # failed provider read by the number of configured documents.
                pending.set_exception(exc)
                raise
        return pending.result()

    def _document(self, spec):
        repo, path = self._repository(spec["repository"]), spec["path"]
        if not isinstance(path, str) or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Document path must stay inside its repository.")
        source = self._source("github:document:" + repo + ":" + path, "GitHub",
                              spec.get("label", path), {"repository": repo, "path": path})
        ref = spec.get("ref", "main")
        sha = self._document_head(repo, ref)
        document = self._github("repos/" + repo + "/contents/" + quote(path, safe="/") + "?ref=" + sha)
        if document.get("encoding") != "base64" or not isinstance(document.get("content"), str):
            raise SourceFailure("github_document_encoding")
        data = json.loads(base64.b64decode(document["content"]).decode("utf-8-sig"))
        items = []
        for collection in spec.get("collections", ["features"]):
            if collection not in data:
                raise SourceFailure("document_collection_missing")
            rows = data[collection]
            if not isinstance(rows, list):
                raise SourceFailure("document_collection_shape")
            for row in rows:
                if not isinstance(row, dict):
                    raise SourceFailure("document_item_shape")
                detail = row.get("data") if isinstance(row.get("data"), dict) else row
                key = row.get("id") or row.get("subject_id") or row.get("record_id")
                if not key:
                    raise SourceFailure("document_item_shape")
                origin = row.get("source", {})
                origin = origin if isinstance(origin, dict) else {}
                provider = row.get("provider", {})
                provider = provider if isinstance(provider, dict) else {}
                url = "https://github.com/" + repo + "/blob/" + sha + "/" + quote(path, safe="/")
                observed = timestamp(row.get("observed_at"))
                updated = timestamp(row.get("updated_at") or row.get("last_change") or provider.get("event_at"))
                items.append({"id": "document:" + repo + ":" + path + ":" + collection + ":" + str(key),
                    "kind": {"features": "feature", "operations": "task", "artifacts": "artifact",
                             "sessions": "session", "sources": "work"}.get(collection, collection.rstrip("s")),
                    "title": text(row.get("name") or row.get("label") or detail.get("description") or key, 500),
                    "status": next((value for value in (row.get("status"), row.get("rollup"),
                        provider.get("status"), detail.get("reported_status"), detail.get("reported_state"))
                        if isinstance(value, str) and value), "unknown"),
                    "owner": row.get("owner") or row.get("owner_subsystem") or detail.get("owner"),
                    "project": row.get("project") or spec.get("project") or repo,
                    "updated_at": updated, "activity_observed_at": updated,
                    "url": row.get("url") or detail.get("url") or origin.get("ref") if str(row.get("url") or detail.get("url") or origin.get("ref") or "").startswith("https://") else url,
                    "summary": text(row.get("capability") or row.get("objective") or detail.get("description") or row.get("notes")),
                    "next_action": row.get("next_action") or row.get("next_gap") or detail.get("next_action"),
                    "refs": {"canonical_url": url, "collection": collection, "source_id": key,
                             "source_sha": sha, "source_status": row.get("source_status"),
                             "test_status": row.get("test_status"), "live_status": row.get("live_status"),
                             "source_ref": origin.get("ref"), "provider_status": provider.get("status"),
                             "resource_observed_at": observed},
                    "actions": link(url)})
        return self._batch(source, items, True,
                           ["Canonical source assertions retained; fetching a document does not re-measure its work activity."])

    def _github_discovery(self):
        """Discover Actions work without delaying independent provider readers."""
        results, tasks, deferred = [], [], []
        if self.github_config.get("enabled", True):
            identity_source = self._source("github:identity", "GitHub", "Existing GitHub account", {})
            try:
                identity = self._github("user")
                login = identity["login"]
                if not re.fullmatch(r"[A-Za-z0-9-]+", login):
                    raise SourceFailure("github_identity_shape")
                results.append(self._batch(identity_source, [], True,
                    ["Authenticated identity observed; this is not a business activity timestamp."]))
                repos = self._safe(self._source("github:repositories", "GitHub", "Owned repositories", {"owner": login}),
                                   lambda: self._repository_batch(login))
                prs = self._safe(self._source("github:prs", "GitHub", "Pull requests", {"author_or_owner": login}),
                                 lambda: self._pull_requests(login))
                for batch in (repos, prs):
                    if "deferred" in batch:
                        deferred.append(batch["deferred"])
                    else:
                        results.append(batch)
                candidates = {}
                cutoff = (datetime.now(UTC) - timedelta(days=self.lookback_days)).isoformat().replace("+00:00", "Z")
                for item in repos.get("items", []) + prs.get("items", []):
                    if item.get("updated_at") and item["updated_at"] >= cutoff:
                        candidates[item["project"]] = max(candidates.get(item["project"], ""), item["updated_at"])
                explicit = [self._repository(repo) for repo in self.github_config.get("working_repositories", [])]
                selected = list(dict.fromkeys(explicit + sorted(candidates, key=candidates.get, reverse=True)))
                cap = self._bound(self.github_config.get("max_action_repositories", 8), 1, 40)
                for repo in selected[:cap]:
                    source = self._source("github:actions:" + repo, "GitHub", repo + " builds", {"repository": repo})
                    tasks.append((source, lambda repo=repo: self._actions(repo)))
                if "source" in repos:
                    repos["source"].setdefault("metadata", {}).update({
                        "action_repositories_selected": selected[:cap],
                        "action_repositories_pending": selected[cap:cap + 100],
                        "action_repositories_pending_count": max(0, len(selected) - cap)})
                    if selected[cap:]:
                        repos["source"]["coverage"]["notes"].append(
                            str(len(selected[cap:])) + " additional working repositories exceed the Actions collection cap.")
            except RequestDeferred as exc:
                deferred.append({"source_id": identity_source["id"], "provider": "GitHub",
                    "scope": exc.scope, "reason": exc.reason,
                    "retry_not_before": exc.retry_not_before})
            except Exception as exc:
                extra = getattr(exc, "metadata", {}) if isinstance(exc, SourceFailure) else {}
                results.append(self._batch({**identity_source, "metadata": {"request_budget": extra}}
                    if extra else identity_source, [], False, error=getattr(exc, "code", type(exc).__name__)))
        return results, tasks, deferred

    def collect(self):
        # Cooperative deadline: in-flight provider reads finish under their own
        # timeout, and the executor is joined before the caller releases its lock.
        self.deadline = monotonic() + self.refresh_deadline_seconds
        # A collector may be reused. Never carry a branch pin into a later
        # refresh after the upstream ref may have advanced.
        with self._document_heads_lock:
            self._document_heads.clear()
        results, tasks, deferred, receipts = [], [], [], []

        def ingest(batch):
            # Commit completed sources on this thread while other readers run.
            # Provider workers never share a Store transaction, and each
            # receipt stays in the same order as its finalized source batch.
            payload = {key: value for key, value in batch.items() if key != "operation_id"}
            batch["operation_id"] = "collect:" + hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
            receipt = self.store.ingest(batch)
            results.append(batch)
            receipts.append(receipt)

        for channel in self.slack_config.get("channels", []):
            if not isinstance(channel, dict) or not re.fullmatch(r"[CDG][A-Z0-9]+", str(channel.get("id", ""))):
                raise ValueError("Slack channels need an existing provider id.")
            source = self._source("slack:" + channel["id"], "Slack", channel.get("label", channel["id"]), {"channel_id": channel["id"]})
            tasks.append((source, lambda channel=channel: self._slack(channel)))
        for spec in self.documents:
            source = self._source("github:document:" + spec["repository"] + ":" + spec["path"], "GitHub",
                                  spec.get("label", spec["path"]), {"repository": spec["repository"], "path": spec["path"]})
            tasks.append((source, lambda spec=spec: self._document(spec)))
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = set()
            discovery = None
            if self.github_config.get("enabled", True):
                discovery = executor.submit(self._github_discovery)
                futures.add(discovery)

            def submit(readers):
                for source, reader in readers:
                    try:
                        self._check_deadline()
                    except SourceFailure as exc:
                        ingest(self._batch(source, [], False, error=exc.code,
                            notes=["Collection stopped before dispatch; previous items remain available."]))
                        continue
                    futures.add(executor.submit(self._safe, source, reader))

            submit(tasks)
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    futures.remove(future)
                    if future is discovery:
                        batches, discovered, held = future.result()
                        for batch in batches:
                            ingest(batch)
                        deferred.extend(held)
                        # Discovered work uses the same worker cap, deadline,
                        # and request budget as already-dispatched readers.
                        submit(discovered)
                    else:
                        batch = future.result()
                        if "deferred" in batch:
                            deferred.append(batch["deferred"])
                        else:
                            ingest(batch)
        return {"observed_at": self.clock(), "sources": [batch["source"] for batch in results],
                "items_observed": sum(len(batch["items"]) for batch in results), "receipts": receipts,
                "deferred_sources": sorted(deferred, key=lambda row: row["source_id"]),
                "request_budget": self.request_budget.metrics()}
