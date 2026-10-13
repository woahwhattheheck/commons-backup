"""Shared command-center state and exact-operation journal; Python stdlib only.

Tool arguments/results are never written to disk. A repeated tool operation returns
its durable status, not its original result. Unknown transport outcomes are never
automatically replayed. Every peer and the human use the same methods.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

from .schema import (
    CoreError, _SECRET_KEYS, _SECRET_TEXT, _json, _metadata, _no_secret_fields, _text,
)


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _age(timestamp):
    if not timestamp:
        return float("inf")
    try:
        return time.time() - datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return float("inf")


def _identifier(value, label="id"):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,180}", value):
        raise CoreError(400, label + " must be a nonempty stable identifier.")
    return value


def _url(value, gateway=False):
    value = _text(value, 4000).strip()
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise CoreError(400, "URLs must be HTTP(S) without embedded credentials.")
    if gateway and (parsed.query or parsed.fragment):
        raise CoreError(400, "A runtime gateway URL cannot contain a query or fragment.")
    for key, _ in urllib.parse.parse_qsl(parsed.query):
        if _SECRET_KEYS.fullmatch(key):
            raise CoreError(400, "Credential-bearing URLs cannot be stored as metadata.")
    if "[redacted]" in value:
        raise CoreError(400, "Credential-bearing URLs cannot be stored as metadata.")
    return value.rstrip("/") if gateway else value


def _public_tool(tool, runtime_id):
    """Preserve callable schema, omit provider examples/default values."""
    def clean(value):
        if isinstance(value, dict):
            return {str(k): clean(v) for k, v in value.items()
                    if k not in ("default", "example", "examples")}
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, str):
            return _text(value, 30000)
        return value

    if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
        return None
    return {
        "name": _text(tool["name"], 300),
        "description": _text(tool.get("description", ""), 30000),
        "inputSchema": clean(tool.get("inputSchema", tool.get("input_schema", {}))),
        "annotations": clean(tool.get("annotations", {})),
        "runtime_id": runtime_id,
    }


class CommandCenter:
    SOURCE_TTL = 300
    RUNTIME_TTL = 60
    # A read of connected work older than this starts one bounded refresh in
    # the background, whoever reads it: the browser, an HTTP caller, or a peer
    # through the command_center_work_state tool. There is still no scheduler;
    # a refresh only ever follows a read, and the cross-process lock keeps it to
    # one at a time. The browser's own visible-tab cadence uses the same bound.
    WORK_REFRESH_TTL = 300
    # A "running" record older than this is re-offered to the lock, which is
    # held by the OS for as long as a collector really is running; a process
    # that died mid-read no longer blocks every later read from refreshing.
    WORK_RUNNING_GRACE = 900
    # The observability bakes (pulse.json, feed/head.json, seats.json,
    # feed/github.json) are read from main at the pinned commit, re-read when
    # main moves or after this long, whichever is first.
    BAKE_TTL = 300
    SOURCE_PATHS = (
        ("resource-ledger", "ground/RESOURCE_LEDGER.json", False),
        ("connected-capabilities", "inventory/resources/connected_capabilities.json", False),
        ("titan", "revenue/kaggriculture/command-center-adapter/adapter.json", True),
    )

    def __init__(self, state_dir: Path, gateway_url="http://127.0.0.1:8878",
                 repo="woahwhattheheck/commons", fetcher=None, *, initialize=True):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise CoreError(400, "Expected an owner/repository reference.")
        self.state_dir = Path(state_dir)
        self.database = self.state_dir / "command-center.sqlite3"
        self._initialize = initialize
        if initialize:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        elif not self.database.is_file():
            raise FileNotFoundError("Existing command-center.sqlite3 is required.")
        self._summary_lock = threading.Lock()
        self._summary_cache = None
        self._mail_cache = None
        self._work_snapshot_cache = None
        self._context_index_cache = None
        self._work_store = None
        self._work_store_lock = threading.Lock()
        self._work_refresh_thread = None
        # Process-local and deliberately not the sources table: the bakes move
        # every few minutes, and a persisted observation per move would flood
        # the derived feed with source events.
        self._bakes = {}
        self._bakes_lock = threading.Lock()
        self.repo = repo
        self.gateway_url = _url(gateway_url, gateway=True)
        self.fetcher = fetcher or self._fetch_http
        if not initialize:
            # Local provider exit observers attach to existing custody only.
            # They must not create a center, schema, or default runtime route.
            return
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, path TEXT, sha TEXT, observed_at TEXT,
                    attempted_at TEXT, status TEXT, error TEXT, data TEXT
                );
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(kind,id)
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, kind TEXT NOT NULL,
                    name TEXT NOT NULL, runtime TEXT, status TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT, summary TEXT, error TEXT
                );
                CREATE INDEX IF NOT EXISTS operations_started
                    ON operations(started_at DESC);
                CREATE TABLE IF NOT EXISTS work_refresh (
                    id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS moderation (
                    event_id TEXT PRIMARY KEY, hidden INTEGER NOT NULL,
                    reason TEXT NOT NULL, peer TEXT NOT NULL, observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_events (
                    id TEXT PRIMARY KEY, observed_at TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS source_events_observed
                    ON source_events(observed_at DESC);
            """)
            initial = {"id": "shared-equipment", "label": "Shared equipment",
                       "gateway_url": self.gateway_url, "observed_at": _now()}
            db.execute("INSERT OR IGNORE INTO records(kind,id,data) VALUES(?,?,?)",
                       ("runtimes", initial["id"], _json(initial)))

    @contextmanager
    def _db(self):
        if self._initialize:
            db = sqlite3.connect(str(self.database), timeout=30)
        else:
            db = sqlite3.connect(self.database.resolve().as_uri() + "?mode=rw",
                                 timeout=30, uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _fetch_http(method, url, payload=None):
        data = None if payload is None else _json(payload).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, method=method,
            headers={"Accept": "application/json", "User-Agent": "Commons-Command-Center/1",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise CoreError(502, "Provider response exceeded the size limit.")
            return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _failure(exc):
        # Never persist str(exc), provider response bodies, request URLs, or headers.
        if isinstance(exc, urllib.error.HTTPError):
            return "HTTP " + str(exc.code)
        if isinstance(exc, CoreError):
            return "Provider request failed (" + str(exc.status) + ")"
        return "Provider request failed (" + type(exc).__name__ + ")"

    def _get_records(self, kind):
        with self._db() as db:
            return [json.loads(row["data"]) for row in db.execute(
                "SELECT data FROM records WHERE kind=? ORDER BY id", (kind,))]

    def _source(self, source_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["data"] = json.loads(result["data"]) if result["data"] else None
        return result

    @staticmethod
    def _source_event_content(source):
        """Compare operational changes without collector clock/liveness noise."""
        content = {key: source.get(key) for key in
                   ("id", "path", "sha", "status", "error", "data")}
        if source["id"].startswith("runtime:") and isinstance(content["data"], dict):
            data = {key: value for key, value in content["data"].items()
                    if key not in ("tools_observed_at", "health_observed_at")}
            if isinstance(data.get("health"), dict):
                data["health"] = {key: value for key, value in data["health"].items()
                                  if key != "uptime_seconds"}
            content["data"] = data
        return _json(content)

    def _save_source(self, source_id, path, sha, data=None, error=None, missing=False,
                     partial=False):
        previous = self._source(source_id)
        attempted_at = _now()
        if error:
            result = {
                "id": source_id, "path": path, "sha": previous["sha"] if previous else sha,
                "observed_at": attempted_at if partial else (previous["observed_at"] if previous else None),
                "attempted_at": attempted_at,
                "status": "degraded" if partial else (
                    "stale" if previous and previous["data"] is not None else
                    ("unavailable" if missing else "error")),
                "error": error, "data": data if data is not None else (previous["data"] if previous else None),
            }
        else:
            result = {"id": source_id, "path": path, "sha": sha,
                      "observed_at": attempted_at, "attempted_at": attempted_at,
                      "status": "live", "error": None, "data": data}
        with self._db() as db:
            db.execute("""INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET path=excluded.path,sha=excluded.sha,
                observed_at=excluded.observed_at,attempted_at=excluded.attempted_at,
                status=excluded.status,error=excluded.error,data=excluded.data""",
                (result["id"], result["path"], result["sha"], result["observed_at"],
                 result["attempted_at"], result["status"], result["error"],
                 _json(result["data"]) if result["data"] is not None else None))
        if previous is None or self._source_event_content(previous) != self._source_event_content(result):
            self._append_source_event(result)
        return result

    def _append_source_event(self, source):
        """Retain immutable observation metadata and an exact source reference.

        Canonical document history stays at its pinned GitHub SHA; full documents
        are not copied into an ever-growing event mirror. Runtime observations
        retain only safe names/health metadata, never tool arguments or results.
        """
        source_id = source["id"]
        data = source.get("data")
        if source_id.startswith("runtime:"):
            source_url = source["path"]
            runtime_data = data if isinstance(data, dict) else {}
            snapshot = {
                "tool_names": [t["name"] for t in runtime_data.get("tools", [])],
                "health": runtime_data.get("health"),
                "tools_observed_at": runtime_data.get("tools_observed_at"),
                "health_observed_at": runtime_data.get("health_observed_at"),
                "tools_error": runtime_data.get("tools_error"),
                "health_error": runtime_data.get("health_error"),
            }
        elif source_id == "github-main":
            source_url = ("https://github.com/" + self.repo + "/commit/" + source["sha"]
                          if source.get("sha") else source["path"])
            snapshot = {"sha": source.get("sha"), "repo": self.repo}
        else:
            source_url = ("https://github.com/" + self.repo + "/blob/" +
                          source["sha"] + "/" + source["path"]) if source.get("sha") else ""
            snapshot = {"sha": source.get("sha"), "path": source["path"], "url": source_url}
        if data is not None:
            snapshot["content_sha256"] = hashlib.sha256(_json(data).encode("utf-8")).hexdigest()
        event = {
            "kind": "source", "source_id": source_id,
            "title": source_id + " — " + source["status"],
            "body": source["error"] or "Source observation refreshed.",
            "source_url": source_url, "observed_at": source["attempted_at"],
            "source_observed_at": source["observed_at"], "snapshot": snapshot,
            "source_status": source["status"],
        }
        event["id"] = "source-event:" + hashlib.sha256(_json(event).encode("utf-8")).hexdigest()[:32]
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO source_events VALUES(?,?,?)",
                       (event["id"], event["observed_at"], _json(event)))

    def _refresh_sources(self, force=False):
        head = self._source("github-main")
        if not force and head and _age(head["attempted_at"]) < self.SOURCE_TTL:
            return
        head_url = "https://api.github.com/repos/" + self.repo + "/commits/main"
        try:
            response = self.fetcher("GET", head_url)
            sha = response.get("sha") if isinstance(response, dict) else None
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
                raise CoreError(502, "GitHub did not return a valid commit SHA.")
            self._save_source("github-main", head_url, sha, {"sha": sha, "repo": self.repo})
        except Exception as exc:
            error = self._failure(exc)
            self._save_source("github-main", head_url, None, error=error)
            for source_id, path, _ in self.SOURCE_PATHS:
                self._save_source(source_id, path, None,
                                  error="Pinned main unavailable: " + error)
            return
        for source_id, path, optional in self.SOURCE_PATHS:
            url = "https://raw.githubusercontent.com/" + self.repo + "/" + sha + "/" + path
            try:
                data = self.fetcher("GET", url)
                if not isinstance(data, (dict, list)):
                    raise CoreError(502, "Canonical source must be a JSON object or array.")
                self._save_source(source_id, path, sha, data)
            except Exception as exc:
                missing = optional and isinstance(exc, urllib.error.HTTPError) and exc.code == 404
                self._save_source(source_id, path, sha, error=self._failure(exc), missing=missing)

    def _runtimes(self, force=False, runtime_id=None):
        results = []
        for runtime in self._get_records("runtimes"):
            if runtime_id is not None and runtime["id"] != runtime_id:
                continue
            source_id = "runtime:" + runtime["id"]
            snapshot = self._source(source_id)
            if force or not snapshot or _age(snapshot["attempted_at"]) >= self.RUNTIME_TTL:
                old = snapshot.get("data") if snapshot else None
                data = dict(old or {"tools": [], "health": None})
                errors, successes = [], 0
                for endpoint in ("tools", "health"):
                    url = runtime["gateway_url"] + ("/v1/tools" if endpoint == "tools" else "/health")
                    try:
                        response = self.fetcher("GET", url)
                        if endpoint == "tools":
                            raw_tools = response.get("tools") if isinstance(response, dict) else response
                            if not isinstance(raw_tools, list):
                                raise CoreError(502, "Runtime tool catalog must be a list.")
                            data["tools"] = [
                                t for t in (_public_tool(v, runtime["id"]) for v in raw_tools) if t]
                        else:
                            if not isinstance(response, dict):
                                raise CoreError(502, "Runtime health response must be an object.")
                            data["health"] = {key: _metadata(response[key]) for key in
                                ("ok", "status", "service", "version", "tool_count", "uptime_seconds")
                                if key in response}
                        data[endpoint + "_observed_at"] = _now()
                        data[endpoint + "_error"] = None
                        successes += 1
                    except Exception as exc:
                        error = self._failure(exc)
                        data[endpoint + "_error"] = error
                        errors.append(endpoint + ": " + error)
                # Each successful component is durable even if its sibling failed.
                snapshot = self._save_source(
                    source_id, runtime["gateway_url"], None, data=data,
                    error="; ".join(errors) if errors else None, partial=bool(successes))
            data = snapshot.get("data") or {}
            catalog_live = bool(data.get("tools_observed_at")) and not data.get("tools_error")
            results.append(dict(
                runtime, status=snapshot["status"], observed_at=snapshot["observed_at"],
                attempted_at=snapshot["attempted_at"], tools=data.get("tools", []),
                health=data.get("health"), catalog_live=catalog_live,
                tools_observed_at=data.get("tools_observed_at"),
                health_observed_at=data.get("health_observed_at"),
                tools_error=data.get("tools_error"), health_error=data.get("health_error"),
                error=snapshot["error"]))
        return results

    def tools(self):
        runtimes = self._runtimes(force=True)
        return {"tools": [tool for runtime in runtimes for tool in runtime["tools"]],
                "runtimes": runtimes}

    @staticmethod
    def _operation(row):
        item = dict(row)
        item.pop("payload_hash", None)
        item["operation_id"] = item["id"]
        item["runtime_id"] = item["runtime"]
        item["summary"] = json.loads(item["summary"]) if item.get("summary") else None
        return item

    def _reserve(self, operation_id, payload_hash, kind, name, runtime=None):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row:
                if row["payload_hash"] != payload_hash:
                    raise CoreError(409, "Operation ID already exists with different content.")
                return self._operation(row)
            db.execute("""INSERT INTO operations
                (id,payload_hash,kind,name,runtime,status,started_at)
                VALUES(?,?,?,?,?,'dispatching',?)""",
                (operation_id, payload_hash, kind, name, runtime, _now()))
        return None

    def _finish(self, operation_id, status, summary, error=None):
        with self._db() as db:
            db.execute("""UPDATE operations SET status=?,finished_at=?,summary=?,error=?
                WHERE id=?""", (status, _now(), _json(summary), error, operation_id))
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        return self._operation(row)

    def call_tool(self, payload):
        if not isinstance(payload, dict):
            raise CoreError(400, "Tool request must be an object.")
        operation_id = _identifier(payload.get("operation_id"), "operation_id")
        name = _identifier(payload.get("name"), "name")
        runtime_id = _identifier(payload.get("runtime_id", "shared-equipment"), "runtime_id")
        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            raise CoreError(400, "Tool arguments must be an object.")
        # The hash is the only persisted representation of arguments.
        semantic = {"runtime_id": runtime_id, "name": name, "arguments": arguments}
        swarm = None
        if "swarm" in payload:
            from .swarm_dispatch import normalize
            swarm = normalize(name, arguments, payload["swarm"])
            semantic["swarm"] = swarm
        payload_hash = hashlib.sha256(_json(semantic).encode("utf-8")).hexdigest()
        with self._db() as db:
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if row:
            if row["payload_hash"] != payload_hash:
                raise CoreError(409, "Operation ID already exists with different content.")
            operation = self._operation(row)
            return {"operation_id": operation_id, "status": row["status"], "replayed": True,
                    "result_available": False, "result": None, "retry_blocked": True,
                    "operation": operation,
                    **({"swarm": (operation.get("summary") or {}).get("swarm")} if swarm is not None else {})}
        runtime = next(iter(self._runtimes(force=True, runtime_id=runtime_id)), None)
        if runtime is None:
            raise CoreError(404, "Runtime is not registered.")
        if not runtime["catalog_live"]:
            raise CoreError(503, "Runtime discovery is unavailable; no tool call was sent.")
        if name not in {tool["name"] for tool in runtime["tools"]}:
            raise CoreError(404, "Tool is not in the current runtime catalog.")
        existing = self._reserve(operation_id, payload_hash, "tool", name, runtime_id)
        if existing:
            return {"operation_id": operation_id, "status": existing["status"], "replayed": True,
                    "result_available": False, "result": None, "retry_blocked": True,
                    "operation": existing,
                    **({"swarm": (existing.get("summary") or {}).get("swarm")} if swarm is not None else {})}
        # Calling this center through its advertised equipment tools shares this
        # same journal. Namespace only a colliding inner metadata-operation ID;
        # preserve the original semantic hash, parent call_id and all service IDs.
        dispatch_arguments = arguments
        child_operation_id = None
        center_metadata_tools = {
            "command_center_focus", "command_center_session", "command_center_budget",
            "command_center_runtime", "command_center_janny", "command_center_note",
            "command_center_moderate",
        }
        if name in center_metadata_tools and arguments.get("operation_id") == operation_id:
            child_operation_id = "nested-" + hashlib.sha256(
                _json({"parent": operation_id, "name": name}).encode("utf-8")).hexdigest()[:40]
            dispatch_arguments = dict(arguments, operation_id=child_operation_id)
        child_summary = {"child_operation_id": child_operation_id} if child_operation_id else {}
        binding = {}
        if swarm is not None:
            from .swarm_dispatch import prepare, reserve_binding
            try:
                prepared = prepare(self, name, arguments, swarm, operation_id)
            except Exception as exc:
                prepared = {"ready": False, "swarm": {
                    "status": "error", "requested_task_key": swarm.get("task_key"),
                    "worker": swarm["worker"], "rerouted": False,
                    "reason": getattr(exc, "kind", type(exc).__name__)}}
                if getattr(exc, "retry_after", None) is not None:
                    prepared["swarm"]["retry_after"] = exc.retry_after
            if prepared["ready"]:
                prior_dispatch = reserve_binding(self, operation_id,
                                                 {**child_summary, "swarm": prepared["swarm"]})
                if prior_dispatch is not None:
                    prepared = {"ready": False, "swarm": prior_dispatch}
            binding = {"swarm": prepared["swarm"]}
            child_summary.update(binding)
            if not prepared["ready"]:
                operation = self._finish(operation_id, "failed",
                    {"provider_dispatched": False, "automatic_retry": False, **child_summary},
                    prepared["swarm"].get("reason"))
                return {"operation_id": operation_id, "status": "failed", "replayed": False,
                        "provider_dispatched": False, "result_available": False,
                        "result": None, "retry_blocked": True, "operation": operation, **binding}
            dispatch_arguments = prepared["arguments"]
        envelope = {"request_id": "command-center", "call_id": operation_id,
                    "name": name, "arguments": dispatch_arguments}
        try:
            result = self.fetcher("POST", runtime["gateway_url"] + "/v1/tools/call", envelope)
        except Exception as exc:
            operation = self._finish(operation_id, "uncertain",
                {"receipt_received": False, "automatic_retry": False, **child_summary},
                self._failure(exc))
            return {"operation_id": operation_id, "status": "uncertain", "replayed": False,
                    "result_available": False, "result": None, "retry_blocked": True,
                    "operation": operation, **binding}
        status = self._receipt_status(result, operation_id)
        failed = status == "failed"
        provider_refs = self._provider_refs(result)
        # Never journal provider text, arbitrary result keys, excerpts or arguments.
        operation = self._finish(operation_id, status,
                                 {"receipt_received": True, "provider_reported_error": failed,
                                  "execution_complete": status in ("succeeded", "failed", "cancelled"),
                                  "provider_refs": provider_refs, **child_summary})
        lifecycle = None
        if swarm is not None or name in {"gemini_get_request", "gemini_events",
                                         "grokbot_inspect", "grokbot_events"}:
            # Receipt handles must be durable before a terminal observation can
            # identify its canonical dispatch. No additional provider read occurs.
            try:
                from .swarm_lifecycle import observe_result, consume_operation
                lifecycle = {"observed": observe_result(self, name, result, runtime_id=runtime_id)}
                if swarm is not None:
                    lifecycle["consumed"] = consume_operation(self, operation_id)
            except Exception as exc:
                # The provider receipt remains valid if reconciliation defers.
                lifecycle = {"status": "deferred", "reason": getattr(exc, "kind", type(exc).__name__)}
                if getattr(exc, "retry_after", None) is not None:
                    lifecycle["retry_after"] = exc.retry_after
            with self._db() as db:
                current = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            operation = self._operation(current)
            status = operation["status"]
        return {"operation_id": operation_id, "status": status, "replayed": False,
                "result_available": True, "result": result, "retry_blocked": True,
                "operation": operation, **binding,
                **({"swarm_lifecycle": lifecycle} if lifecycle is not None else {})}

    @staticmethod
    def _provider_refs(result):
        """Retain only bounded reconciliation handles, never arbitrary results."""
        keys = {"request_id", "provider_request_id", "run_id", "job_id", "session_id",
                "thread_id", "task_id", "operation_id", "artifact_id", "html_url", "url"}
        refs, seen = [], set()

        def keep(key, value, path):
            if len(refs) >= 40 or isinstance(value, bool) or value is None:
                return
            if key in ("url", "html_url"):
                if not isinstance(value, str):
                    return
                try:
                    value = _url(value)
                    parsed = urllib.parse.urlsplit(value)
                    # Never retain signed/callback/auth URLs or opaque query values.
                    safe_query_keys = {"page", "per_page", "tab", "line", "thread_ts", "cid"}
                    if not value or any(k not in safe_query_keys for k, _ in
                                        urllib.parse.parse_qsl(parsed.query)):
                        return
                    if parsed.fragment and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", parsed.fragment):
                        return
                except CoreError:
                    return
            else:
                if isinstance(value, int):
                    value = str(value)
                if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,240}", value):
                    return
                if _SECRET_TEXT.search(value):
                    return
            identity = (path, key, value)
            if identity not in seen:
                refs.append({"path": path + "." + key, "key": key, "value": value})
                seen.add(identity)

        def inspect(value, path="gateway", depth=0):
            if depth > 6 or len(refs) >= 40:
                return
            if isinstance(value, list):
                for index, item in enumerate(value[:10]):
                    inspect(item, path + "[" + str(index) + "]", depth + 1)
                return
            if not isinstance(value, dict):
                return
            for key in keys:
                if key in value:
                    keep(key, value[key], path)
            for key in ("result", "structuredContent", "data"):
                inspect(value.get(key), path + "." + key, depth + 1)
            content = value.get("content")
            for index, item in enumerate(content[:10] if isinstance(content, list) else []):
                if isinstance(item, dict) and item.get("type") == "text":
                    raw = item.get("text")
                    if isinstance(raw, str) and len(raw) < 1000000:
                        try:
                            inspect(json.loads(raw), path + ".content[" + str(index) + "].json", depth + 1)
                        except (ValueError, TypeError):
                            pass

        inspect(result)
        return refs

    @staticmethod
    def _receipt_status(result, operation_id=None):
        """Classify explicit receipts; transport acceptance is not completion."""
        flags = {"uncertain": False, "failed": False, "cancelled": False,
                 "pending": False, "explicit": False}
        pending = {"accepted", "pending", "queued", "running", "dispatching", "received",
                   "in_progress", "in-progress", "submitted", "started", "processing",
                   "scheduled", "received_pending_projection", "paused", "awaiting_input",
                   "needs_attention"}
        failed = {"failed", "failure", "error", "rejected", "denied"}
        cancelled = {"cancelled", "canceled", "aborted"}
        uncertain = {"uncertain", "unknown_outcome", "unknown", "interrupted",
                     "timeout", "timed_out", "lost_response"}
        completed = {"succeeded", "success", "completed", "complete", "done"}

        def inspect(value, depth=0):
            if depth > 6 or not isinstance(value, dict):
                return
            if isinstance(value.get("ok"), bool) or isinstance(value.get("isError"), bool):
                flags["explicit"] = True
            flags["uncertain"] |= value.get("uncertain") is True
            flags["failed"] |= value.get("isError") is True or value.get("ok") is False
            for key in ("state", "status"):
                label = value.get(key)
                if isinstance(label, str):
                    normalized = label.lower().strip()
                    flags["pending"] |= normalized in pending
                    flags["failed"] |= normalized in failed
                    flags["cancelled"] |= normalized in cancelled
                    flags["uncertain"] |= normalized in uncertain
                    flags["explicit"] |= normalized in (pending | failed | cancelled | uncertain | completed)
            for key in ("result", "structuredContent", "data"):
                inspect(value.get(key), depth + 1)
            for item in value.get("content", []) if isinstance(value.get("content"), list) else []:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str) and len(text) < 1000000:
                        try:
                            inspect(json.loads(text), depth + 1)
                        except (ValueError, TypeError):
                            pass

        inspect(result)
        if isinstance(result, dict):
            if result.get("request_id") not in (None, "command-center"):
                flags["uncertain"] = True
            if operation_id is not None and result.get("call_id") not in (None, operation_id):
                flags["uncertain"] = True
        if flags["uncertain"] or not flags["explicit"]:
            return "uncertain"
        if flags["cancelled"]:
            return "cancelled"
        if flags["failed"]:
            return "failed"
        if flags["pending"]:
            return "pending"
        return "succeeded"

    def mutate(self, kind, payload):
        aliases = {"session": "sessions", "budget": "budgets", "runtime": "runtimes",
                   "feed/moderate": "moderate"}
        kind = aliases.get(kind, kind)
        if kind not in ("focus", "sessions", "budgets", "runtimes", "janny", "feed", "moderate"):
            raise CoreError(404, "Unknown metadata operation.")
        if not isinstance(payload, dict):
            raise CoreError(400, "Metadata request must be an object.")
        operation_id = _identifier(payload.get("operation_id"), "operation_id")
        _no_secret_fields(payload)
        body = {k: v for k, v in payload.items() if k != "operation_id"}
        # Validate all fields before opening the transaction.
        record_id, record, moderation = "current", None, None
        if kind == "focus":
            record = {key: _text(body.get(key, "")) for key in
                      ("objective", "next_action", "status", "notes")}
        elif kind == "sessions":
            item = body.get("session", body)
            if not isinstance(item, dict):
                raise CoreError(400, "session must be an object.")
            record_id = _identifier(item.get("id"), "session.id")
            keys = ("id", "label", "url", "provider", "model", "cpu", "ram_gib", "gpu",
                    "disk_gib", "disk_free_gib", "workspace", "observed_at", "status",
                    "objective", "resource_id", "origin", "capabilities", "tools", "egress",
                    "artifact_transport", "expires_at", "lifetime", "notes", "cost_source")
            record = {key: _metadata(item[key]) for key in keys if key in item}
            if "url" in record:
                record["url"] = _url(record["url"])
        elif kind == "budgets":
            item = body.get("budget", body)
            if not isinstance(item, dict):
                raise CoreError(400, "budget must be an object.")
            record_id = _identifier(item.get("id"), "budget.id")
            keys = ("id", "label", "limit", "used", "balance", "remaining", "committed",
                    "unit", "period", "observed_at",
                    "source_url", "provider", "kind", "currency", "notes")
            record = {key: _metadata(item[key]) for key in keys if key in item}
            for key in ("limit", "used", "balance", "remaining", "committed"):
                if key in record and record[key] is not None and (
                        isinstance(record[key], bool) or not isinstance(record[key], (int, float))
                        or record[key] < 0):
                    raise CoreError(400, key + " must be a nonnegative number or null.")
            if "source_url" in record:
                record["source_url"] = _url(record["source_url"])
            record.setdefault("kind", "manual_observation")
        elif kind == "runtimes":
            item = body.get("runtime", body)
            if not isinstance(item, dict):
                raise CoreError(400, "runtime must be an object.")
            record_id = _identifier(item.get("id"), "runtime.id")
            gateway_url = _url(item.get("gateway_url", ""), gateway=True)
            if not gateway_url:
                raise CoreError(400, "Runtime registration requires gateway_url.")
            record = {"id": record_id, "label": _text(item.get("label", record_id), 300),
                      "gateway_url": gateway_url}
        elif kind == "janny":
            record = {"peer": _text(body.get("peer", body.get("peer_id", "")), 300),
                      "status": _text(body.get("status", "active"), 100),
                      "responsibility": "Reversible moderation of the derived feed; no access grants."}
        elif kind == "feed":
            record_id = "note:" + operation_id
            source_url = _url(body.get("source_url", ""))
            record = {"id": record_id, "kind": "note",
                      "title": _text(body.get("title", "Operation note"), 300),
                      "body": _text(body.get("body", body.get("text", "")), 4000),
                      "source_url": source_url,
                      "source_ref": _text(body.get("source_ref", ""), 1000)}
        else:
            event_id = _identifier(body.get("event_id", body.get("item_id")), "event_id")
            hidden = body.get("hidden")
            if "hidden" not in body:
                legacy = body.get("action")
                if legacy == "hide":
                    hidden = True
                elif legacy == "restore":
                    hidden = False
            if not isinstance(hidden, bool):
                raise CoreError(400, "Moderation hidden must be a boolean.")
            reason = _text(body.get("reason", ""), 1000).strip()
            if not reason:
                raise CoreError(400, "Moderation needs a reason.")
            self.event(event_id)  # Originals remain addressable outside the latest feed view.
            moderation = {"event_id": event_id, "hidden": hidden,
                          "reason": reason, "peer": _text(body.get("peer", ""), 300)}
        payload_hash = hashlib.sha256(
            _json({"kind": kind, "content": body}).encode("utf-8")).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if previous:
                if previous["payload_hash"] != payload_hash:
                    raise CoreError(409, "Operation ID already exists with different content.")
                return {"ok": True, "operation_id": operation_id, "replayed": True,
                        "operation": self._operation(previous)}
            timestamp = _now()
            if record is not None:
                record.setdefault("observed_at", None if kind == "sessions" else timestamp)
                record["updated_at"] = timestamp
                db.execute("""INSERT INTO records VALUES(?,?,?)
                    ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data""",
                    (kind, record_id, _json(record)))
                if kind == "runtimes":
                    db.execute("DELETE FROM sources WHERE id=?", ("runtime:" + record_id,))
            else:
                moderation["observed_at"] = timestamp
                db.execute("""INSERT INTO moderation VALUES(?,?,?,?,?)
                    ON CONFLICT(event_id) DO UPDATE SET hidden=excluded.hidden,
                    reason=excluded.reason,peer=excluded.peer,observed_at=excluded.observed_at""",
                    (moderation["event_id"], int(moderation["hidden"]), moderation["reason"],
                     moderation["peer"], timestamp))
            summary = {"record_id": record_id} if record is not None else {
                "event_id": moderation["event_id"], "hidden": moderation["hidden"]}
            db.execute("""INSERT INTO operations
                (id,payload_hash,kind,name,runtime,status,started_at,finished_at,summary)
                VALUES(?,?,?,? ,NULL,'succeeded',?,?,?)""",
                (operation_id, payload_hash, kind, kind, timestamp, timestamp, _json(summary)))
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        return {"ok": True, "operation_id": operation_id, "replayed": False,
                "record": record if record is not None else moderation,
                "operation": self._operation(row)}

    @staticmethod
    def _operation_event(row):
        event = CommandCenter._operation(row)
        return {"id": "operation:" + event["id"], "kind": "operation",
                "title": event["name"] + " — " + event["status"],
                "body": "Runtime: " + (event["runtime"] or "command center") +
                        ". Status: " + event["status"] + ".",
                "source_url": "", "observed_at": event["finished_at"] or event["started_at"],
                "operation_id": event["id"], "summary": event["summary"],
                "provider_refs": (event["summary"] or {}).get("provider_refs", [])}

    def event(self, event_id):
        """Read any retained event, including originals outside the 300-item view."""
        event_id = _identifier(event_id, "event_id")
        with self._db() as db:
            if event_id.startswith("operation:"):
                row = db.execute("SELECT * FROM operations WHERE id=?",
                                 (event_id[len("operation:"):],)).fetchone()
                event = self._operation_event(row) if row else None
            else:
                row = db.execute("SELECT data FROM source_events WHERE id=?", (event_id,)).fetchone()
                if not row:
                    row = db.execute("SELECT data FROM records WHERE kind='feed' AND id=?",
                                     (event_id,)).fetchone()
                event = json.loads(row["data"]) if row else None
            if event is None:
                raise CoreError(404, "Feed event does not exist.")
            mod = db.execute("SELECT * FROM moderation WHERE event_id=?", (event_id,)).fetchone()
        event["hidden"] = bool(mod["hidden"]) if mod else False
        event["moderation"] = dict(mod) if mod else None
        return event

    def _feed(self, operations=None):
        """Build the feed, reusing this response's operation rows when supplied."""
        with self._db() as db:
            if operations is None:
                operations = db.execute(
                    "SELECT * FROM operations ORDER BY started_at DESC LIMIT 300").fetchall()
            source_events = db.execute(
                "SELECT data FROM source_events ORDER BY observed_at DESC LIMIT 300").fetchall()
        feed = self._get_records("feed")
        feed.extend(self._operation_event(row) for row in operations)
        feed.extend(json.loads(row["data"]) for row in source_events)
        feed = sorted(feed, key=lambda item: item.get("observed_at") or "", reverse=True)[:300]
        if not feed:
            return feed
        # The retained moderation history can outgrow this bounded view. Its
        # primary key already supports exact lookups for the events we return.
        with self._db() as db:
            placeholders = ",".join("?" for _ in feed)
            moderation = {row["event_id"]: dict(row) for row in db.execute(
                "SELECT * FROM moderation WHERE event_id IN (" + placeholders + ")",
                [event["id"] for event in feed])}
        for event in feed:
            mod = moderation.get(event["id"])
            event["hidden"] = bool(mod["hidden"]) if mod else False
            event["moderation"] = mod
        return feed



    def _merged_sessions(self, sources):
        """Merge actual observations by their own timestamps, never fetch time."""
        def observed_time(item):
            value = item.get("observed_at")
            if not isinstance(value, str) or not value:
                return None
            try:
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return stamp.timestamp() if stamp.tzinfo is not None else None
            except (ValueError, OverflowError):
                return None

        by_id = {}
        titan = next((source for source in sources if source["id"] == "titan"), None)
        adapter = titan.get("data") if titan else None
        raw_sessions = adapter.get("sessions", []) if isinstance(adapter, dict) else []
        allowed = ("id", "label", "url", "provider", "model", "cpu", "ram_gib", "gpu",
                   "disk_gib", "disk_free_gib", "workspace", "observed_at", "status",
                   "objective", "resource_id", "origin", "capabilities", "tools", "egress",
                   "artifact_transport", "expires_at", "lifetime", "notes", "cost_source")
        if isinstance(raw_sessions, list):
            for item in raw_sessions:
                if not isinstance(item, dict):
                    continue
                try:
                    _identifier(item.get("id"), "session.id")
                    _no_secret_fields(item)
                    session = {key: _metadata(item[key]) for key in allowed if key in item}
                    if "url" in session:
                        session["url"] = _url(session["url"])
                    session.update(source_id="titan", source_status=titan["status"],
                                   source_observed_at=titan["observed_at"])
                    by_id[session["id"]] = session
                except CoreError:
                    continue
        measurement_fields = ("cpu", "ram_gib", "gpu", "disk_gib", "disk_free_gib",
                              "workspace", "observed_at", "status", "objective",
                              "capabilities", "tools", "egress")
        binding_fields = ("url", "provider", "model", "resource_id", "origin",
                          "artifact_transport", "expires_at", "lifetime", "cost_source")
        for local in self._get_records("sessions"):
            adapter_session = by_id.get(local["id"])
            if adapter_session is None:
                by_id[local["id"]] = local
                continue
            local_time, adapter_time = observed_time(local), observed_time(adapter_session)
            adapter_wins = adapter_time is not None and (local_time is None or adapter_time > local_time)
            winner = adapter_session if adapter_wins else local
            merged = {**adapter_session, **local}
            # Do not stamp an old hardware measurement with a newer observation date.
            for key in measurement_fields:
                merged.pop(key, None)
                if key in winner:
                    merged[key] = winner[key]
            for key in binding_fields:
                if key in winner:
                    merged[key] = winner[key]
            merged["telemetry_source"] = "titan" if adapter_wins else "local-session"
            merged["telemetry_observed_at"] = winner.get("observed_at")
            merged["adapter_source"] = {
                "source_id": "titan", "source_status": adapter_session.get("source_status"),
                "fetched_at": adapter_session.get("source_observed_at"),
                "observed_at": adapter_session.get("observed_at")}
            merged["local_metadata"] = {key: local[key] for key in
                                       ("label", "notes", "updated_at") if key in local}
            by_id[local["id"]] = merged
        return list(by_id.values())


    def _work_store_instance(self):
        # Lazy import avoids a core -> workstreams -> CoreError module cycle.
        with self._work_store_lock:
            if self._work_store is None:
                from .workstreams import WorkstreamStore
                self._work_store = WorkstreamStore(self.state_dir)
            return self._work_store

    def _work_refresh_status(self):
        with self._db() as db:
            row = db.execute("SELECT data FROM work_refresh WHERE id=1").fetchone()
        return json.loads(row["data"]) if row else {
            "status": "idle", "started_at": None, "finished_at": None,
            "note": ("Refresh runs when requested or when a read finds the last "
                     "one older than the TTL; no scheduled producer.")}

    def _save_work_refresh(self, status):
        with self._db() as db:
            db.execute("INSERT INTO work_refresh(id,data) VALUES(1,?) "
                       "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                       (_json(status),))

    def _take_work_refresh_lock(self):
        # Held by the OS until the worker exits, including in-flight provider
        # reads. Process exit releases it; no stale-file deletion or TTL race.
        try:
            handle = (self.state_dir / "workstreams-refresh.lock").open("a+b")
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                handle.close()
                if exc.errno in (11, 13, 35, 36) or getattr(exc, "winerror", None) in (33, 36):
                    return None
                raise
            return handle
        except OSError:
            raise CoreError(503, "Work refresh lock unavailable.") from None

    @staticmethod
    def _release_work_refresh_lock(handle):
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def _shared_work_snapshot_locked(self):
        """Reuse one normalized local observation across compact read views.

        Caller holds _summary_lock. Ingestion invalidates this by database/WAL
        signature; reading a snapshot never advances provider freshness.
        """
        store = self._work_store_instance()
        signature = []
        for path in (store.db_path, Path(str(store.db_path) + "-wal")):
            try:
                stat = path.stat()
                signature.append((stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                signature.append(None)
        signature = tuple(signature)
        now = time.monotonic()
        cached = self._work_snapshot_cache
        if cached and cached["signature"] == signature and now - cached["at"] < 5:
            return cached["state"], {"hit": True, "ttl_seconds": 5,
                                     "age_seconds": round(now - cached["at"], 3)}
        snapshot = store.state()
        self._work_snapshot_cache = {"signature": signature, "at": now, "state": snapshot}
        return snapshot, {"hit": False, "ttl_seconds": 5, "age_seconds": 0}

    def work_context(self, limit=20, offset=0, query="", owner="", provider="",
                     source="", kind="", status="", if_revision=None,
                     order="priority", seat=""):
        """Read a selective shared context page, with unchanged-page reuse."""
        from .context_view import build_index, select
        started = time.monotonic()
        with self._summary_lock:
            work, cache = self._shared_work_snapshot_locked()
            cached = self._context_index_cache
            # Raw snapshots expire even without writes, so freshness threshold
            # crossings are evaluated without a query-specific cache explosion.
            if cached is None or cached["work"] is not work:
                cached = {"work": work, "index": build_index(work)}
                self._context_index_cache = cached
            try:
                result = select(cached["index"], limit=limit, offset=offset,
                                query=query, owner=owner, provider=provider,
                                source=source, kind=kind, status=status,
                                if_revision=if_revision, order=order, seat=seat)
            except ValueError as exc:
                raise CoreError(400, str(exc)) from None
            result["cache"] = cache
            result["telemetry"] = {
                "projection_ms": round((time.monotonic() - started) * 1000, 2),
                "records_examined": len(work.get("items", [])),
            }
            return result

    def work_context_item(self, source_id, item_id):
        """Read one exact normalized observation, not the entire work feed."""
        if any(not isinstance(value, str) or not value or len(value) > 2000
               for value in (source_id, item_id)):
            raise CoreError(400, "A source_id and item_id are required.")
        with self._summary_lock:
            work, cache = self._shared_work_snapshot_locked()
            item = next((value for value in work.get("items", [])
                         if value.get("source_id") == source_id and value.get("id") == item_id), None)
            if item is None:
                raise CoreError(404, "The selected observation is not in the loaded source coverage.")
            source = next((value for value in work.get("sources", [])
                           if value.get("id") == source_id), {})
            # The exact-item handoff needs the same freshness/error/coverage
            # evidence as the list. WorkstreamStore already normalizes this
            # metadata and excludes raw provider bodies and credential values.
            source_detail = {key: source.get(key) for key in
                             ("id", "provider", "label", "status", "last_success_at",
                              "last_good_observed_at", "coverage", "scope", "sync_mode")}
            source_detail.update(source)
            result = {"item": item, "source": source_detail,
                      "cache": cache, "provider_requests": 0,
                      "scope": "One stored normalized observation; provider-original content stays at its original source."}
            return json.loads(json.dumps(result))

    def work_summary(self):
        """Compact shared observation; never triggers provider reads or refresh."""
        from .summary import build_summary
        started = time.monotonic()
        store = self._work_store_instance()
        paths = [store.db_path, Path(str(store.db_path) + "-wal"),
                 self.database, Path(str(self.database) + "-wal")]
        def signature():
            result = []
            for path in paths:
                try:
                    stat = path.stat()
                    result.append((stat.st_mtime_ns, stat.st_size))
                except FileNotFoundError:
                    result.append(None)
            return tuple(result)
        with self._summary_lock:
            before = signature()
            cached = self._summary_cache
            if cached and cached["signature"] == before and started - cached["at"] < 5:
                # Return independent objects; callers cannot corrupt shared cache.
                result = json.loads(cached["json"])
                result["cache"] = {"hit": True, "ttl_seconds": 5,
                                   "age_seconds": round(started - cached["at"], 3)}
                return result
            work = dict(self._shared_work_snapshot_locked()[0])
            work["refresh"] = self._work_refresh_status()
            result = build_summary(work)
            result["telemetry"] = {"projection_ms": round((time.monotonic() - started) * 1000, 2),
                                   "records_examined": len(work["items"])}
            self._summary_cache = {"signature": before, "at": started,
                                   "json": json.dumps(result)}
            result["cache"] = {"hit": False, "ttl_seconds": 5, "age_seconds": 0}
            return result

    def work_mail(self, limit=100, offset=0, query="", mode="all"):
        """Read paginated mail threads from shared observations, without inference or provider calls."""
        from .mail_tracking import project
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise CoreError(400, "Mail pagination requires limit 1..200 and nonnegative offset.")
        if not isinstance(query, str) or len(query) > 240 or not isinstance(mode, str) or mode not in {"all", "waiting_on_us", "waiting_on_them", "unknown", "unread", "overdue"}:
            raise CoreError(400, "Invalid mail filter.")
        started = time.monotonic()
        store = self._work_store_instance()
        paths = [store.db_path, Path(str(store.db_path) + "-wal")]
        def signature():
            result = []
            for path in paths:
                try:
                    stat = path.stat()
                    result.append((stat.st_mtime_ns, stat.st_size))
                except FileNotFoundError:
                    result.append(None)
            return tuple(result)
        with self._summary_lock:
            before = signature()
            cached = self._mail_cache
            hit = bool(cached and cached["signature"] == before and started - cached["at"] < 5)
            if not hit:
                work, _ = self._shared_work_snapshot_locked()
                result = project(work)
                result["telemetry"] = {"projection_ms": round((time.monotonic() - started) * 1000, 2),
                                       "records_examined": len(work["items"])}
                cached = {"signature": before, "at": started, "json": json.dumps(result)}
                self._mail_cache = cached
            result = json.loads(cached["json"])
        query = query.strip().casefold()
        rows = [row for row in result["threads"]
                if (not query or query in " ".join(str(row.get(key) or "") for key in
                    ("title", "account", "owner", "assigned_owner", "next_action")).casefold())
                and (mode == "all" or row.get("waiting_on") == mode
                     or mode == "unread" and row.get("unread") is True
                     or mode == "overdue" and row.get("overdue") is True)]
        result["threads"] = rows[offset:offset + limit]
        result["pagination"] = {"limit": limit, "offset": offset, "matching_threads": len(rows),
                                "next_offset": offset + limit if offset + limit < len(rows) else None}
        result["cache"] = {"hit": hit, "ttl_seconds": 5, "age_seconds": round(started - cached["at"], 3)}
        result["provider_requests"] = 0
        return result

    def work_state(self, refresh=False):
        if refresh:
            started = self.refresh_work()
            trigger = "requested"
        else:
            started, trigger = self._refresh_work_if_due()
        state = self._work_store_instance().state()
        state["refresh"] = self._work_refresh_status()
        state["freshness"] = self._work_freshness(state, started, trigger)
        try:
            from .queue_pressure import queue_pressure
            state["queue_pressure"] = queue_pressure(state)
        except Exception:
            # Queue pressure is an advisory read. Never take down the work view
            # because this reducer failed, and never turn a reducer failure into
            # permission to describe CI as green.
            state["queue_pressure"] = {
                "schema": "commons-actions-queue-pressure/v1",
                "state": "UNKNOWN",
                "warning": True,
                "reason": "queue_pressure_reducer_failed",
                "ci_green_claim_allowed": False,
                "read_only": True,
            }
        return state

    def swarm_state(self, refresh=False):
        """Read the existing coordination branch, with explicit freshness.

        This is an observation, never merge authority. The merger rechecks live
        PR/review/tree state. Reads are also usage receipts in the existing DB.
        """
        cache_key = "\0swarm-state"
        with self._bakes_lock:
            cached = self._bakes.get(cache_key)
        if cached and not refresh and time.time() - cached["fetched"] < 60:
            payload = dict(cached["read"])
        else:
            url = "https://raw.githubusercontent.com/" + self.repo + "/state/coordination/coordination.json"
            try:
                source = self.fetcher("GET", url)
                if not isinstance(source, dict):
                    raise CoreError(502, "Coordination state must be an object.")
                payload = {"schema": "commons-swarm-view/v1", "source_url": url,
                           "observed_at": source.get("observed_at"), "main": source.get("main"),
                           "swarm": source.get("swarm"), "degraded": source.get("degraded", []),
                           "prs": [{k: r.get(k) for k in ("number", "title", "head", "swarm")}
                                   for r in source.get("prs", [])], "read_error": None}
                with self._bakes_lock:
                    self._bakes[cache_key] = {"fetched": time.time(), "read": dict(payload)}
            except Exception as exc:
                payload = dict(cached["read"]) if cached else {
                    "schema": "commons-swarm-view/v1", "source_url": url,
                    "observed_at": None, "swarm": None, "prs": []}
                payload["read_error"] = self._failure(exc)
        # Connector-equipped peers can feed the same observed PRs through the
        # existing ingest API when this runtime has no direct GitHub road.
        # Prefer a newer, explicitly scoped observation; never infer full fleet
        # coverage or copy a work item's edit time into provider observed_at.
        work = self._work_store_instance().state()
        sources = [s for s in work["sources"] if s.get("id") == "commons-swarm:" + self.repo
                   and s.get("last_good_observed_at") and not s.get("retained_last_good")]
        if sources:
            source = sources[0]
            stamp = source["last_good_observed_at"]
            if _age(stamp) < _age(payload.get("observed_at")) or payload.get("swarm") is None:
                items = [i for i in work["items"] if i["source_id"] == source["id"]]
                prs = []
                for item in items:
                    meta = item.get("metadata") or {}
                    if isinstance(meta.get("swarm"), dict):
                        prs.append({"number": meta.get("number"), "title": item.get("title"),
                                    "head": meta.get("head"), "swarm": meta["swarm"]})
                counts = {}
                for pr in prs:
                    state = (pr["swarm"].get("review") or {}).get("state", "UNKNOWN")
                    counts[state] = counts.get(state, 0) + 1
                payload = {"schema": "commons-swarm-view/v1", "source_url": source.get("url"),
                           "source_road": "connector-ingest", "observed_at": stamp,
                           "coverage": source.get("last_good_coverage"), "scope": source.get("scope"),
                           "main_read_error": payload.get("read_error"), "read_error": None,
                           "prs": prs, "swarm": {"counts": counts, "batches": [], "capacity": None},
                           "degraded": [] if (source.get("last_good_coverage") or {}).get("complete") else ["partial-view"]}
        age = _age(payload.get("observed_at"))
        payload["age_seconds"] = None if age == float("inf") else int(age)
        payload["stale"] = (age < -300 or age >= 600 or payload.get("read_error") is not None
                            or payload.get("swarm") is None)
        with self._db() as db:
            row = db.execute("SELECT data FROM records WHERE kind='usage' AND id='swarm-state'").fetchone()
            previous = json.loads(row["data"]) if row else {}
            usage = {"reads": previous.get("reads", 0) + 1, "last_read_at": _now(),
                     "source_observed_at": payload.get("observed_at"), "stale": payload["stale"]}
            db.execute("INSERT OR REPLACE INTO records(kind,id,data) VALUES('usage','swarm-state',?)",
                       (_json(usage),))
        payload["usage"] = usage
        return payload

    def _work_refresh_due(self, status):
        """(due, why) from the last refresh record, without taking the lock."""
        current = status.get("status")
        if current == "running":
            age = _age(status.get("started_at"))
            if age < self.WORK_RUNNING_GRACE:
                return False, "running"
            return True, "running_record_expired"
        last = status.get("finished_at") or status.get("started_at")
        if not last:
            return True, "never_refreshed"
        if _age(last) >= self.WORK_REFRESH_TTL:
            return True, "older_than_ttl"
        return False, "fresh"

    def _refresh_work_if_due(self):
        due, why = self._work_refresh_due(self._work_refresh_status())
        if not due:
            return None, why
        try:
            return self.refresh_work(), why
        except CoreError:
            # A read must never fail because a background refresh could not
            # start; the freshness block says what happened.
            return {"ok": False, "started": False, "already_running": False,
                    "error": "work_refresh_unavailable"}, why

    def _work_freshness(self, state, started, trigger):
        """What a reader needs to judge this read, in one place.

        `age_seconds` is measured from the last refresh that actually
        collected (completed or completed_with_errors). `stale` is true when
        that is older than the TTL or nothing has been collected yet; per-source
        ages stay on each source. `auto_refresh` says whether this read started
        one, so a caller knows a re-read in a few seconds may be newer.
        """
        status = self._work_refresh_status()
        # Freshness counts only a refresh that actually collected. An attempt
        # that failed or found no collector configured does not make the data
        # any newer, so it does not reset the clock.
        completed = status.get("last_completed_at")
        age = _age(completed)
        age_seconds = None if age == float("inf") else max(0, int(age))
        if started is None:
            outcome = "not_due" if trigger == "fresh" else trigger
        elif started.get("started"):
            outcome = "started"
        elif started.get("already_running"):
            outcome = "already_running"
        else:
            outcome = started.get("error") or "not_started"
        stale_sources = sorted(
            source.get("id") for source in state.get("sources", [])
            if source.get("stale") or source.get("data_stale"))
        return {
            "ttl_seconds": self.WORK_REFRESH_TTL,
            "last_refresh_status": status.get("status"),
            "last_refresh_finished_at": status.get("finished_at"),
            "last_completed_at": completed,
            "age_seconds": age_seconds,
            "stale": age_seconds is None or age_seconds >= self.WORK_REFRESH_TTL,
            "collector_configured": status.get("status") != "not_configured",
            "trigger": trigger,
            "auto_refresh": outcome,
            "stale_sources": stale_sources,
            "note": ("Any read starts one bounded refresh when the last one is "
                     "older than ttl_seconds and returns at once; read again "
                     "after the refresh finishes for newer observations. "
                     "Connector-fed sources refresh only when their peers ingest."),
        }

    def ingest_work(self, payload):
        result = self._work_store_instance().ingest(payload)
        from .swarm_tasks import after_ingest
        after_ingest(self)
        return result

    def update_work(self, payload):
        return self._work_store_instance().update_work(payload)

    def refresh_work(self):
        # The lock spans instances/processes that share this state directory.
        handle = self._take_work_refresh_lock()
        if handle is None:
            return {"ok": True, "started": False, "already_running": True,
                    "refresh": self._work_refresh_status()}
        prior = self._work_refresh_status()
        started = {"id": "work-refresh-" + uuid.uuid4().hex, "status": "running",
                   "started_at": _now(), "finished_at": None, "owner_pid": os.getpid(),
                   "config_path": str(self.state_dir / "workstreams.config.json"),
                   "read_only": True, "scheduled_producer": False,
                   # Carried forward so a failed attempt does not erase when the
                   # data last came from a real collection.
                   "last_completed_at": prior.get("last_completed_at")}
        try:
            self._save_work_refresh(started)
            worker = threading.Thread(target=self._run_work_refresh,
                                      args=(handle, started), daemon=True,
                                      name="command-center-work-refresh")
            self._work_refresh_thread = worker
            worker.start()
        except Exception:
            failed = {**started, "status": "failed", "finished_at": _now(),
                      "error": "work_refresh_start_failed"}
            self._save_work_refresh(failed)
            self._release_work_refresh_lock(handle)
            raise CoreError(503, "Work refresh could not start.") from None
        return {"ok": True, "started": True, "already_running": False,
                "refresh": started}

    def _run_work_refresh(self, handle, started):
        final = {**started}
        try:
            path = self.state_dir / "workstreams.config.json"
            if not path.is_file():
                final.update(status="not_configured", error="workstreams_config_missing")
                return
            if path.stat().st_size > 131072:
                final.update(status="failed", error="workstreams_config_too_large")
                return
            try:
                config = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                final.update(status="failed", error="workstreams_config_unreadable")
                return
            if not isinstance(config, dict):
                final.update(status="failed", error="workstreams_config_not_object")
                return
            _no_secret_fields(config)
            # Collector checks this deadline before scheduling/source/provider
            # reads. Already in-flight bounded reads may finish afterwards.
            config = {**config, "refresh_deadline_seconds":
                      config.get("refresh_deadline_seconds", 180)}
            collectors = __import__("integrations.command_center.collectors", fromlist=["LiveCollectors"])
            result = collectors.LiveCollectors(self._work_store_instance(), config).collect()
            sources = result.get("sources", [])
            errors = sum(bool(source.get("error")) for source in sources)
            budget = result.get("request_budget") or {}
            deferred = result.get("deferred_sources") or []
            final.update(request_budget=budget, deferred_sources=deferred)
            wholly_deferred = budget.get("observed_attempts") == 0 and bool(deferred)
            final.update(status="deferred" if wholly_deferred else "completed_with_errors" if errors else "completed",
                         source_count=len(sources), sources_with_errors=errors,
                         items_observed=result.get("items_observed", 0),
                         error=None, last_collected_at=result.get("observed_at"))
        except Exception as exc:
            # Do not persist exception messages, config values or provider results.
            final.update(status="failed", error="work_refresh_" + type(exc).__name__)
        finally:
            final["finished_at"] = _now()
            if final.get("status") in ("completed", "completed_with_errors"):
                final["last_completed_at"] = final["finished_at"]
                from .swarm_tasks import after_ingest
                after_ingest(self, refresh_providers=True)
            try:
                self._save_work_refresh(final)
            finally:
                self._release_work_refresh_lock(handle)

    def observability(self, limit=20, repo_root=None, refresh=False):
        """The observability snapshot, composed from main at the current commit.

        A checkout on the owner's host is only as current as its last pull, so
        the panel reads the bakes the board workflow commits, at the commit the
        rest of this app already pins. If main cannot be read, each bake falls
        back to the checkout and says so (road=checkout, plus the main error);
        a bake neither road can read is named as degraded, never drawn empty.
        """
        from . import observability as obs
        self._refresh_sources(force=refresh)
        head = self._source("github-main")
        sha = head.get("sha") if head and head.get("status") == "live" else None
        reads = {}
        for name, rel in obs.SOURCES:
            main = self._bake(rel, sha, force=refresh) if sha else None
            if main and main.get("ok"):
                reads[name] = main
                continue
            local = obs._read(repo_root, rel) if repo_root else {
                "path": rel, "ok": False, "error": "no_checkout", "value": None}
            local["road"] = "checkout"
            local["main_error"] = (main or {}).get("error") or (
                "main unavailable: " + (head.get("error") or "not read")
                if head else "main not read")
            reads[name] = local
        payload = obs.compose(reads, limit)
        payload["main"] = {"sha": sha, "status": head.get("status") if head else None,
                           "observed_at": head.get("observed_at") if head else None,
                           "bake_ttl_seconds": self.BAKE_TTL}
        coordination = self._coordination_head(force=refresh)
        payload["coordination"] = coordination["value"] if coordination.get("ok") else None
        payload["coordination_source"] = {k: v for k, v in coordination.items() if k != "value"}
        return payload

    COORDINATION_HEAD_URL = ("https://raw.githubusercontent.com/{repo}/"
                             "state/coordination/coordination-head.json")

    def _coordination_head(self, force=False):
        """The coordination head from the state/coordination branch, not main.

        host/coordination_state.py publishes it there so a refresh never moves
        main. It is optional: a missing branch reads as absent with its error,
        and never enters `sources` or `degraded`. Cached for BAKE_TTL.
        """
        with self._bakes_lock:
            cached = self._bakes.get("\0coordination-head")
            if (cached and not force
                    and time.time() - cached["fetched"] < self.BAKE_TTL):
                return dict(cached["read"])
        url = self.COORDINATION_HEAD_URL.format(repo=self.repo)
        base = {"path": "coordination-head.json", "road": "state-branch",
                "branch": "state/coordination"}
        try:
            value = self.fetcher("GET", url)
            if not isinstance(value, dict):
                raise CoreError(502, "Coordination head must be a JSON object.")
            read = dict(base, ok=True, value=value, observed_at=_now())
        except Exception as exc:
            read = dict(base, ok=False, value=None, error=self._failure(exc))
        with self._bakes_lock:
            self._bakes["\0coordination-head"] = {"fetched": time.time(), "read": read}
        return dict(read)

    def _bake(self, rel, sha, force=False):
        """One bake from main at `sha`, cached until main moves or BAKE_TTL."""
        with self._bakes_lock:
            cached = self._bakes.get(rel)
            if (cached and not force and cached["sha"] == sha
                    and time.time() - cached["fetched"] < self.BAKE_TTL):
                return dict(cached["read"])
        url = ("https://raw.githubusercontent.com/" + self.repo + "/" + sha +
               "/" + rel)
        try:
            value = self.fetcher("GET", url)
            if not isinstance(value, (dict, list)):
                raise CoreError(502, "Bake must be a JSON object or array.")
            read = {"path": rel, "ok": True, "value": value, "road": "main",
                    "sha": sha, "observed_at": _now()}
        except Exception as exc:
            read = {"path": rel, "ok": False, "value": None, "road": "main",
                    "sha": sha, "error": self._failure(exc)}
        with self._bakes_lock:
            self._bakes[rel] = {"sha": sha, "fetched": time.time(), "read": read}
        return dict(read)

    def state(self, refresh=False):
        self._refresh_sources(force=refresh)
        runtimes = self._runtimes(force=refresh)
        with self._db() as db:
            source_ids = [row["id"] for row in db.execute(
                "SELECT id FROM sources WHERE id NOT LIKE 'runtime:%' ORDER BY id")]
            operation_rows = db.execute(
                "SELECT * FROM operations ORDER BY started_at DESC LIMIT 300").fetchall()
        operations = [self._operation(row) for row in operation_rows]
        sources = [self._source(source_id) for source_id in source_ids]
        ledger = next((s for s in sources if s["id"] == "resource-ledger"), None)
        catalog = next((s for s in sources if s["id"] == "connected-capabilities"), None)
        ledger_data = ledger["data"] if ledger and isinstance(ledger["data"], dict) else {}
        catalog_data = catalog["data"] if catalog and isinstance(catalog["data"], dict) else {}
        resources = [dict(item, id=item.get("id", item.get("name", "")),
                          source_id="resource-ledger", source_observed_at=ledger["observed_at"],
                          source_status=ledger["status"])
                     for item in ledger_data.get("surfaces", []) if isinstance(item, dict)]
        connections = [dict(item, source_id="connected-capabilities",
                            source_observed_at=catalog["observed_at"],
                            source_status=catalog["status"])
                       for item in catalog_data.get("providers", []) if isinstance(item, dict)]
        sessions = self._merged_sessions(sources)
        focus = self._get_records("focus")
        janny = self._get_records("janny")
        return {"observed_at": _now(), "sources": sources, "resources": resources,
                "connections": connections, "runtimes": runtimes,
                "sessions": sessions, "budgets": self._get_records("budgets"),
                "operations": operations,
                "focus": focus[0] if focus else {"objective": "", "next_action": ""},
                "feed": self._feed(operation_rows),
                "janny": janny[0] if janny else {"peer": "", "status": "unassigned",
                    "responsibility": "Reversible derived-feed moderation; no access grants."}}
