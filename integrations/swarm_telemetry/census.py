"""Read existing cross-harness runtime roads without starting any peer.

Native runtime snapshots and narrowly recognized live agent CLI processes form
the observed census. Protocol seats, old command-center rows and open browser
tabs remain separately labelled declarations/discovery. Returned originals and
event cursors can be committed to private telemetry custody. No read starts or
resumes work, changes provider state, or exposes command lines or message bodies.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .notifications import redact

_PROCESS_CACHE: dict[str, Any] = {}
_NONTERMINAL = {"queued", "running", "working", "waiting", "active", "pending"}
_TERMINAL = {"complete", "completed", "completed_observed", "completed_reported", "cancelled", "canceled", "failed", "closed", "archived", "terminated", "stopped", "done", "succeeded"}
_PROVIDER_TERMINAL = _TERMINAL | {"error", "interrupted"}


class CensusStoragePending(RuntimeError):
    """No additional source read was started below the collection reserve."""


class CensusCustodyPending(RuntimeError):
    """A returned original is retained while its durable write is retried."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: Any) -> str | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value / 1000 if value > 10**11 else value, timezone.utc).isoformat().replace("+00:00", "Z")
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _age(value: Any, at: str) -> float | None:
    stamp = _timestamp(value)
    if not stamp:
        return None
    return (datetime.fromisoformat(at.replace("Z", "+00:00")) - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds()


def _unwrap(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("isError"):
        raise ValueError("source_tool_error")
    if isinstance(value, Mapping) and (value.get("ok") is False or value.get("status") == "error"):
        raise ValueError("source_read_error")
    if isinstance(value, Mapping) and value.get("structuredContent"):
        return _unwrap(value["structuredContent"])
    if isinstance(value, Mapping) and isinstance(value.get("content"), list):
        for block in value["content"]:
            if block.get("type") == "text":
                return _unwrap(json.loads(block["text"]))
    if isinstance(value, Mapping) and "result" in value and isinstance(value["result"], (dict, list)):
        return _unwrap(value["result"])
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _json_read(url: str, timeout: float, payload: Mapping | None = None, source_sink=None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(32 * 1024 * 1024 + 1)
        status = response.status
    read_at = _now()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("source_response_exceeds_32MiB")
    text = raw.decode("utf-8")
    if source_sink:
        source_sink(text, read_at, status)
    if status >= 400:
        raise RuntimeError("source_http_error:" + str(status))
    return _unwrap(json.loads(text))


def _tool(base: str, name: str, arguments: Mapping, timeout: float, source_sink=None) -> Any:
    # These exact tools are reads. No arbitrary tool name is accepted here.
    allowed = {"command_center_state", "read_observatory", "gemini_events", "gemini_get_request", "grokbot_events", "grokbot_inspect"}
    if name not in allowed:
        raise ValueError("census_read_tool_required")
    # A new read ID avoids the gateway replaying a prior census response.
    digest = hashlib.sha256(json.dumps([name, arguments, time.time_ns()], sort_keys=True).encode()).hexdigest()[:24]
    return _json_read(base.rstrip("/") + "/v1/tools/call", timeout,
                      {"name": name, "arguments": dict(arguments), "request_id": "census-read-" + digest, "call_id": "census-read-" + digest},
                      source_sink=(lambda raw, read_at, status: source_sink(name, arguments, raw, read_at, "census-read-" + digest, status)) if source_sink else None)


def _rows(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [dict(v) for v in value if isinstance(v, Mapping)]
    if not isinstance(value, Mapping):
        return []
    rows = []
    for key in ("pinnedThreads", "threads", "sessions", "peers", "agents", "requests", "runs"):
        item = value.get(key)
        if isinstance(item, list):
            rows.extend(dict(v) for v in item if isinstance(v, Mapping))
        elif isinstance(item, Mapping):
            rows.extend(dict(v, id=v.get("id") or k) for k, v in item.items() if isinstance(v, Mapping))
    for key in ("session", "thread", "request", "run", "event"):
        if isinstance(value.get(key), Mapping):
            rows.append(dict(value[key]))
    return rows


def _status(row: Mapping) -> str:
    origin = row.get("origin") if isinstance(row.get("origin"), Mapping) else {}
    value = row.get("status") or row.get("state") or origin.get("native_execution_status") or "unknown"
    if isinstance(value, Mapping):
        value = value.get("type") or value.get("status") or value.get("state") or "unknown"
    return str(value).lower().replace("-", "_")


def _peer(row: Mapping, source: str, read_at: str, *, fresh_read: bool, ttl: float, declared: bool = False) -> dict | None:
    if str(row.get("kind") or "").lower() in {"machine", "runtime", "service", "resource"}:
        return None
    origin = row.get("origin") if isinstance(row.get("origin"), Mapping) else {}
    sid = row.get("session_id") or row.get("threadId") or row.get("thread_id") or origin.get("canonical_session_id") or origin.get("native_thread_id") or row.get("request_id") or row.get("run_id") or row.get("id")
    if not sid:
        return None
    state = _status(row)
    if state in _TERMINAL | {"notloaded", "not_loaded", "unloaded"}:
        return None
    observed = read_at if fresh_read else _timestamp(row.get("runtime_observed_at") or origin.get("metadata_observed_at") or row.get("telemetry_observed_at") or row.get("observed_at"))
    age = _age(observed, read_at)
    fresh = age is not None and -300 <= age <= ttl and not declared
    reported = state.endswith("_reported") or state in {"live", "quiet", "awake", "existing"}
    status = "unknown"
    if fresh and not reported:
        if state in {"running", "executing", "active", "inprogress", "in_progress", "working", "busy", "streaming", "thinking", "tool_running", "adapter_revision_running"}:
            status = "executing"
        elif state in {"waiting", "queued", "pending", "needs_attention", "needs_input", "interrupted", "waiting_for_input", "waiting_for_approval"}:
            status = "waiting"
    known_idle = state == "idle"
    if known_idle:
        status = "idle_session"
    provider = row.get("provider") or ("openai" if row.get("backingKind") == "codex" or row.get("source") == "codex" or row.get("harness") == "codex" else None)
    harness = row.get("harness") or row.get("backingKind") or row.get("source") or provider or "unknown"
    parent = row.get("parent_agent_id") or row.get("parentAgentId") or row.get("parent_id")
    return {
        "peer_id": str(row.get("peer_id") or row.get("peer") or sid), "session_id": str(sid),
        "agent_id": row.get("agent_id") or row.get("agentId"), "parent_agent_id": parent,
        "parent_session_id": row.get("parent_session_id") or row.get("parentThreadId"),
        "provider": provider, "model": row.get("model"), "harness": harness,
        "title": redact(row.get("title") or row.get("task_title") or row.get("name")),
        "task_title": redact(row.get("task_title") or row.get("title")),
        "work_id": row.get("work_id") or row.get("task_id"),
        "source_record_ref": row.get("source_record_ref"),
        "status": status, "source_status": state,
        "last_activity_at": _timestamp(row.get("last_activity_at") or row.get("lastActivityAt") or row.get("updatedAt") or row.get("updated_at") or row.get("last_active") or observed),
        "observed_at": observed, "fresh": fresh,
        "basis": "known_session" if known_idle else "declared" if declared or reported or not fresh else "runtime_observation",
        "source_refs": [source], "metadata": {"source_observation_age_seconds": age},
    }


def _processes(timeout: float) -> list[dict]:
    if os.name != "nt":
        return []
    # CommandLine never leaves PowerShell. Only exact agent executable/package
    # signatures qualify. UI processes, app servers, generic Python/Node and
    # every browser process are excluded. Process alive does not mean inference.
    script = r'''
$ErrorActionPreference = 'Stop'
$censusRows = @(Get-CimInstance Win32_Process | ForEach-Object {
  $censusName = [string]$_.Name
  $censusCommand = [string]$_.CommandLine
  $censusHarness = $null
  $censusLauncher = $false
  if ($censusName -match '^(codex|claude|gemini|opencode|aider|goose)(\.exe)?$') {
    $censusHarness = [IO.Path]::GetFileNameWithoutExtension($censusName).ToLowerInvariant()
  } elseif ($censusName -match '^(node|python|python3|pythonw)(\.exe)?$') {
    if ($censusCommand -match '[/\\]@anthropic-ai[/\\]claude-code[/\\].*(cli\.js|claude)') { $censusHarness = 'claude-code' }
    elseif ($censusCommand -match '[/\\]@google[/\\]gemini-cli[/\\].*(index\.js|cli\.js)') { $censusHarness = 'gemini-cli' }
    elseif ($censusCommand -match '[/\\]@openai[/\\]codex[/\\].*codex') { $censusHarness = 'codex-cli' }
    elseif ($censusCommand -match '(?:^|\s)-m\s+aider(?:\s|$)|[/\\]aider[/\\]__main__\.py') { $censusHarness = 'aider' }
    if ($censusName -match '^node') { $censusLauncher = $true }
  }
  if ($censusHarness -and $censusCommand -notmatch '(?:^|\s)(app-server|mcp-server|mcp\s+serve|--version|--help)(?:\s|$)') {
    $censusSession = $null
    if ($censusCommand -match '(?:--session-id|--resume|\sresume)\s+([A-Za-z0-9_-]{16,})') { $censusSession = $Matches[1] }
    [pscustomobject]@{ pid = [int]$_.ProcessId; parent_pid = [int]$_.ParentProcessId; harness = $censusHarness; launcher = $censusLauncher; session_id = $censusSession; created_at = $_.CreationDate.ToUniversalTime().ToString('o') }
  }
})
ConvertTo-Json -InputObject $censusRows -Depth 5 -Compress
'''
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError("windows_process_inventory_failed")
    return _rows(json.loads(result.stdout or "[]"))


def collect_census(config: Mapping | None = None, *, state: Mapping | None = None) -> dict:
    """Return live census plus separately preserved declared peer discovery.

    Config: gateway_url; timeout_seconds; stale_after_seconds; processes;
    native_sessions (fresh native API rows or envelope); runtime_snapshots
    ({source,payload,observed_at,fresh_read,complete}); browser_endpoints (known
    existing CDP JSON base URLs); provider_events; max_event_pages/max_inspects.
    provider_event_state and persist_provider_state retain committed cursors
    and nonterminal request projections between reads. source_read_allowed
    guards collection only; source_recorder commits complete returned originals
    before an event cursor can advance.
    source_snapshots maps read tool names to already fetched source envelopes;
    tool_reader(name, arguments) can bind the existing service connector road.
    Native snapshots with fresh_read=True must be returned by a read in this
    collection run. Provider rows and bakes never inherit a fresh fetch time.
    """
    config = dict(config or {})
    at = _now()
    native_observed_at = at
    native_file_error = None
    if config.get("native_runtime_path"):
        try:
            native_path = Path(config["native_runtime_path"])
            native = _unwrap(json.loads(native_path.read_text(encoding="utf-8")))
            config["native_sessions"] = native.get("native_sessions", native) if isinstance(native, Mapping) else native
            config["native_sessions_complete"] = bool(native.get("complete", native.get("native_sessions_complete", False))) if isinstance(native, Mapping) else False
            native_observed_at = (_timestamp(native.get("observed_at") or native.get("read_at")) if isinstance(native, Mapping) else None) or _timestamp(native_path.stat().st_mtime)
        except Exception as error:
            native_file_error = type(error).__name__
    timeout = max(0.2, min(float(config.get("timeout_seconds", 12)), 30))
    ttl = max(1, float(config.get("stale_after_seconds", 900)))
    base = str(config.get("gateway_url") or "http://127.0.0.1:8878")
    coverage, live, declared = [], [], []
    source_reads = {}
    provider_event_state = {}
    legacy_events = (state or {}).get("provider_events", {})
    retained_events = config.get("provider_event_state") or legacy_events

    def add_rows(rows: list[dict], source: str, *, fresh_read=False, declaration=False, observed_at=None):
        for row in rows:
            if fresh_read and observed_at:
                row = dict(row, runtime_observed_at=observed_at)
                fresh_read_for_row = False
            else:
                fresh_read_for_row = fresh_read
            peer = _peer(row, source, at, fresh_read=fresh_read_for_row, ttl=ttl, declared=declaration)
            if peer:
                (live if peer["basis"] == "runtime_observation" else declared).append(peer)

    def read_tool(name, args):
        snapshots = config.get("source_snapshots") or {}
        if name in snapshots:
            source_reads[name] = {"fresh_read": False}
            return _unwrap(snapshots[name])
        failures = []
        for attempt in range(2):
            try:
                allowed = config.get("source_read_allowed")
                if callable(allowed) and not allowed():
                    raise CensusStoragePending("collection_storage_reserve")
                def retain(tool, arguments, raw, read_at, read_id, status):
                    recorder = config.get("source_recorder")
                    ref = recorder(tool, arguments, raw, read_at, read_id, status) if callable(recorder) else None
                    source_reads[tool] = {"observed_at": read_at, "source_record_ref": ref, "fresh_read": True}
                if callable(config.get("tool_reader")):
                    result = config["tool_reader"](name, args)
                    read_at = _now()
                    retain(name, args, json.dumps(result, ensure_ascii=False), read_at, "census-bound-read-" + hashlib.sha256((name + read_at).encode()).hexdigest()[:24], None)
                    return _unwrap(result)
                return _tool(base, name, args, timeout, source_sink=retain)
            except (CensusStoragePending, CensusCustodyPending):
                raise
            except Exception as error:
                failures.append(type(error).__name__)
        raise RuntimeError(";".join(failures))

    try:
        state = read_tool("command_center_state", {"refresh": False})
        add_rows(_rows(state), "command_center_state")
        coverage.append({"source": "command_center_state", "status": "observed", "records_read": len(_rows(state)), "observed_at": at, "complete": True, "scope": "existing shared cross-harness session records; record timestamps preserved"})
    except Exception as error:
        coverage.append({"source": "command_center_state", "status": "pending_storage" if isinstance(error, CensusStoragePending) else "pending_source_custody" if isinstance(error, CensusCustodyPending) else "unavailable", "error": type(error).__name__, "attempts": 2, "complete": False, "unread_regions": ["session records"]})
    try:
        bake = read_tool("read_observatory", {"view": "census", "limit": 0})
        add_rows(_rows(bake), "read_observatory", declaration=True)
        source_gaps = [str(row.get("source")) for row in bake.get("source_coverage", []) if row.get("state") not in {"OBSERVED", "observed"}]
        cursors = [p.get("next_cursor") for p in bake.get("pagination", []) if p.get("next_cursor")]
        coverage.append({"source": "read_observatory", "status": "partial" if source_gaps or cursors else "observed", "records_read": len(_rows(bake)), "observed_at": at,
                         "complete": not source_gaps and not cursors, "scope": "protocol census declarations", "source_coverage": bake.get("source_coverage", []), "freshness": bake.get("freshness"),
                         "unread_regions": source_gaps + ["census after cursor " + str(cursor) for cursor in cursors]})
    except Exception as error:
        coverage.append({"source": "read_observatory", "status": "pending_storage" if isinstance(error, CensusStoragePending) else "pending_source_custody" if isinstance(error, CensusCustodyPending) else "unavailable", "error": type(error).__name__, "attempts": 2, "complete": False, "unread_regions": ["protocol census"]})

    if "native_sessions" in config:
        rows = _rows(_unwrap(config["native_sessions"]))
        add_rows(rows, "native_app_sessions", fresh_read=True, observed_at=native_observed_at)
        native_age = _age(native_observed_at, at)
        native_fresh = native_age is not None and -300 <= native_age <= ttl
        unread = [] if config.get("native_sessions_complete", True) else ["native list pagination/cap beyond supplied snapshot"]
        if not native_fresh:
            unread.append("native lifecycle changes after the retained source read; an available native host caller must refresh the snapshot")
        coverage.append({"source": "native_app_sessions", "status": "observed" if native_fresh else "pending_host_refresh", "records_read": len(rows), "observed_at": native_observed_at, "snapshot_age_seconds": native_age, "fresh": native_fresh, "stale_after_seconds": ttl, "complete": native_fresh and bool(config.get("native_sessions_complete", True)), "scope": "native session status at actual source read", "unread_regions": unread, "refresh_mode": "host_supplied_snapshot" if config.get("native_runtime_path") else "caller_supplied_native_rows"})
    else:
        coverage.append({"source": "native_app_sessions", "status": "unavailable" if native_file_error else "not_connected", "error": native_file_error, "complete": False, "unread_regions": ["native desktop/cloud session lifecycle"]})
    if config.get("native_runtime_path"):
        producer = config.get("native_refresh_producer")
        producer = producer if isinstance(producer, Mapping) else {}
        configured = producer.get("configured") is True and producer.get("status") == "ACTIVE"
        descriptor = {key: producer.get(key) for key in ("id", "kind", "status", "interval_seconds", "registered_at", "last_verified_scheduled_read_at") if producer.get(key) is not None}
        coverage.append({"source_id": "native_app_sessions:refresh-producer", "source": "native_app_sessions", "status": "external_host_configured" if configured else "host_caller_required", "observed_at": at, "complete": False, "continuous_refresh_producer": False, "automatic_refresh_configured": configured, "refresh_producer": descriptor, "scope": "native application lifecycle refresh producer", "unread_regions": ["external host refresh execution must be established by its actual native source receipts" if configured else "no automatic native application API producer is configured in the telemetry runtime"], "snapshot_source_observed_at": native_observed_at, "refresh_requirement": "an available host caller performs the actual native API read, retains its complete response in encrypted custody, and updates native_runtime_path with the original read timestamp"})
    for snapshot in config.get("runtime_snapshots", []):
        source = str(snapshot.get("source") or "runtime_snapshot")
        try:
            payload = _unwrap(snapshot.get("payload") or {})
            rows = _rows(payload)
            add_rows(rows, source, fresh_read=bool(snapshot.get("fresh_read")))
            coverage.append({"source": source, "status": "observed", "records_read": len(rows), "complete": bool(snapshot.get("complete", False)), "observed_at": snapshot.get("observed_at") or at})
        except Exception as error:
            coverage.append({"source": source, "status": "unavailable", "complete": False, "error": type(error).__name__})

    if config.get("processes", True):
        try:
            refresh = max(1, float(config.get("process_refresh_seconds", 120)))
            cached = bool(_PROCESS_CACHE) and time.monotonic() - _PROCESS_CACHE["at_monotonic"] < refresh
            if cached:
                processes = _PROCESS_CACHE["rows"]
                process_observed_at = _PROCESS_CACHE["observed_at"]
            else:
                processes = _processes(max(30, min(timeout * 3, 45)))
                process_observed_at = _now()
                _PROCESS_CACHE.update(rows=processes, observed_at=process_observed_at, at_monotonic=time.monotonic())
            by_pid = {row["pid"]: row for row in processes}
            process_sessions = {row["pid"]: row.get("session_id") or "process:" + str(row["pid"]) + ":" + str(row.get("created_at")) for row in processes}
            for row in processes:
                # Package launcher plus its matching executable child is one
                # instance; parent links are retained for distinct children.
                if row.get("launcher") and any(child.get("parent_pid") == row["pid"] and child["harness"].split("-")[0] == row["harness"].split("-")[0] for child in processes):
                    continue
                harness = row["harness"]
                pid = row["pid"]
                provider = "openai" if "codex" in harness else "anthropic" if "claude" in harness else "google" if "gemini" in harness else None
                live.append({"peer_id": "process:" + str(pid), "session_id": process_sessions[pid], "agent_id": None,
                             "parent_agent_id": None, "parent_session_id": process_sessions.get(row.get("parent_pid")),
                             "provider": provider, "model": None, "harness": harness, "status": "unknown", "source_status": "process_alive",
                             "last_activity_at": None, "observed_at": process_observed_at, "fresh": True, "basis": "runtime_observation", "source_refs": ["windows_process_metadata"],
                             "metadata": {"pid": pid, "parent_pid": row.get("parent_pid"), "created_at": row.get("created_at"), "execution_state": "unmeasured"}})
            coverage.append({"source": "windows_process_metadata", "status": "observed" if os.name == "nt" else "not_applicable", "records_read": len(processes), "complete": True, "observed_at": process_observed_at, "cached": cached, "process_refresh_seconds": refresh, "scope": "identified local agent CLI processes only; browser/app-server processes excluded"})
        except Exception as error:
            coverage.append({"source": "windows_process_metadata", "status": "unavailable", "error": type(error).__name__, "complete": False, "unread_regions": ["local identified CLI process metadata"]})

    if not config.get("browser_endpoints"):
        coverage.append({"source": "browser_runtime", "status": "not_connected", "complete": False, "unread_regions": ["browser/cloud provider lifecycle outside connected roads"]})
    for endpoint in config.get("browser_endpoints", []):
        source = "browser_cdp:" + urlsplit(str(endpoint)).netloc
        try:
            tabs = _json_read(str(endpoint).rstrip("/") + "/json/list", timeout)
            read = 0
            for tab in tabs:
                if tab.get("type") != "page":
                    continue
                url = urlsplit(str(tab.get("url") or ""))
                provider = {"chatgpt.com": "openai", "claude.ai": "anthropic", "grok.com": "xai", "kimi.com": "moonshot", "gemini.google.com": "google"}.get(url.hostname)
                if not provider:
                    continue
                sid = url.path.strip("/").split("/")[-1] or str(tab.get("id"))
                declared.append({"peer_id": source + ":" + str(tab.get("id")), "session_id": sid, "agent_id": None, "parent_agent_id": None, "parent_session_id": None,
                                 "provider": provider, "model": None, "harness": "browser", "status": "unknown", "source_status": "open_tab", "last_activity_at": None,
                                 "observed_at": at, "fresh": True, "basis": "declared", "source_refs": [source], "metadata": {"execution_state": "unmeasured"}})
                read += 1
            coverage.append({"source": source, "status": "observed", "records_read": read, "complete": True, "scope": "open provider tabs, separate from runtime execution"})
        except Exception as error:
            coverage.append({"source": source, "status": "unavailable", "error": type(error).__name__, "complete": False})

    if config.get("provider_events", True):
        for tool, inspector, identifier in (("gemini_events", "gemini_get_request", "request_id"), ("grokbot_events", "grokbot_inspect", "run_id")):
            previous = retained_events.get(tool) or legacy_events.get(tool, {})
            if "nonterminal" not in previous and "pending" in previous:
                previous = {**previous, "nonterminal": previous["pending"]}
            committed = json.loads(json.dumps(previous)) if isinstance(previous, Mapping) else {}
            cursor = committed.get("cursor", 0)
            pages, read, inspected = 0, 0, 0
            latest = committed.get("nonterminal", {})
            latest = dict(latest) if isinstance(latest, Mapping) else {}
            done = False
            selected = []
            inspected_keys = set()
            inspection_errors = {}
            source_error = None

            def checkpoint():
                nonlocal committed
                value = {**committed, "version": 1, "cursor": cursor, "nonterminal": latest,
                         "checkpoint_acknowledged": True}
                persist = config.get("persist_provider_state")
                if callable(persist):
                    persist(tool, value)
                # Keep only the state whose write was acknowledged. A failed
                # checkpoint never becomes the next read cursor.
                committed = json.loads(json.dumps(value))

            try:
                if isinstance(cursor, bool) or not str(cursor).isdigit():
                    raise ValueError("invalid_retained_event_cursor")
                cursor = int(cursor)
                for _ in range(max(1, min(int(config.get("max_event_pages", 20)), 100))):
                    args = {"after": cursor, "limit": 200}
                    if tool == "grokbot_events":
                        args["wait_ms"] = 0
                    result = read_tool(tool, args)
                    if not isinstance(result, Mapping) or "events" not in result:
                        raise ValueError("event_page_unavailable")
                    page = result["events"]
                    if not isinstance(page, list):
                        raise ValueError("invalid_event_page")
                    pages += 1
                    read += len(page)
                    for event in page:
                        if not isinstance(event, Mapping):
                            continue
                        ident = event.get(identifier)
                        if ident:
                            key = str(ident)
                            state = _status(event)
                            if state in _PROVIDER_TERMINAL:
                                latest.pop(key, None)
                            elif state in _NONTERMINAL or key in latest:
                                # This is a runtime projection. The complete
                                # response is retained separately by the sink.
                                projection = {k: event[k] for k in (identifier, "peer", "status", "state", "ts", "observed_at", "seq") if k in event}
                                latest[key] = {**latest.get(key, {}), **projection,
                                               "event_source_ref": source_reads.get(tool, {}).get("source_record_ref")}
                    next_cursor = result.get("next_cursor")
                    if next_cursor is not None:
                        if isinstance(next_cursor, bool) or not str(next_cursor).isdigit() or int(next_cursor) < cursor:
                            raise ValueError("nonmonotonic_event_cursor")
                        advanced = int(next_cursor) > cursor
                        cursor = int(next_cursor)
                    else:
                        advanced = False
                    done = not page
                    if page and not advanced:
                        # A nonempty page without a continuation is not a
                        # completed history and cannot supply a guessed cursor.
                        raise ValueError("event_continuation_missing")
                    committed["last_event_read_at"] = source_reads.get(tool, {}).get("observed_at")
                    committed["last_source_record_ref"] = source_reads.get(tool, {}).get("source_record_ref")
                    committed["historical_complete"] = bool(committed.get("historical_complete")) or done
                    checkpoint()
                    if done:
                        break
                limit = max(0, min(int(config.get("max_inspects", 12)), 100))
                keys = sorted(latest)
                prior_inspect = str(committed.get("last_inspection_attempt") or committed.get("last_inspected_request") or "")
                split = next((i for i, key in enumerate(keys) if key > prior_inspect), 0)
                selected = (keys[split:] + keys[:split])[:limit]
                for key in selected:
                    event = latest[key]
                    args = {identifier: event[identifier], "wait_ms": 0}
                    try:
                        current = read_tool(inspector, args)
                    except (CensusStoragePending, CensusCustodyPending):
                        raise
                    except Exception as error:
                        inspection_errors[key] = type(error).__name__
                        latest[key] = {**event, "last_inspection_error": type(error).__name__, "last_inspection_attempt_at": _now()}
                        committed["last_inspection_attempt"] = key
                        checkpoint()
                        continue
                    rows = _rows(current) or [dict(current)]
                    retained_peers = []
                    info = source_reads.get(inspector, {})
                    inspected_at = info.get("observed_at")
                    for row in rows:
                        row.setdefault(identifier, event[identifier])
                        row.setdefault("provider", "google" if tool == "gemini_events" else "xai")
                        row.setdefault("harness", "shared-equipment")
                        row.setdefault("peer_id", event.get("peer"))
                        if _status(row) in _PROVIDER_TERMINAL:
                            continue
                        if inspected_at:
                            row["runtime_observed_at"] = inspected_at
                        peer = _peer(row, inspector, at, fresh_read=False, ttl=ttl)
                        if peer:
                            retained_peers.append({**peer, "status": peer["source_status"],
                                                   "runtime_observed_at": peer["observed_at"],
                                                   "source_record_ref": info.get("source_record_ref")})
                    if retained_peers:
                        latest[key] = {**event, "peers": retained_peers}
                    elif rows and all(_status(row) in _PROVIDER_TERMINAL for row in rows):
                        latest.pop(key, None)
                    committed["last_inspected_request"] = key
                    committed["last_inspection_attempt"] = key
                    checkpoint()
                    inspected += 1
                    inspected_keys.add(key)
            except Exception as error:
                source_error = error
            provider_event_state[tool] = committed
            retained = committed.get("nonterminal", {})
            for event in retained.values():
                add_rows(event.get("peers", []), inspector)
            remaining = len(set(retained) - inspected_keys)
            status = "pending_storage" if isinstance(source_error, CensusStoragePending) else "pending_source_custody" if isinstance(source_error, CensusCustodyPending) else "partial" if source_error or not done or remaining else "observed"
            row = {"source": tool, "status": status, "pages_read": pages, "records_read": read,
                   "next_cursor": committed.get("cursor", 0), "inspected_requests": inspected,
                   "nonterminal_requests_retained": len(retained), "remaining_nonterminal_readbacks": remaining,
                   "pending_requests": len(retained),
                   "inspection_errors": inspection_errors,
                   "observed_at": committed.get("last_event_read_at"), "status_observed_at": at,
                   "source_record_ref": committed.get("last_source_record_ref"),
                   "historical_complete": bool(committed.get("historical_complete")),
                   "cursor_persisted": callable(config.get("persist_provider_state")) and bool(committed.get("checkpoint_acknowledged")),
                   "complete": source_error is None and done and not remaining,
                   "unread_regions": ([] if done else ["events after cursor " + str(committed.get("cursor", 0))]) + ([] if not remaining else ["remaining nonterminal provider request readbacks"])}
            if source_error:
                row["error"] = type(source_error).__name__
            coverage.append(row)
    else:
        recovery = config.get("census_provider_events_recovery") or {}
        for tool in ("gemini_events", "grokbot_events"):
            previous = retained_events.get(tool) or legacy_events.get(tool, {})
            if "nonterminal" not in previous and "pending" in previous:
                previous = {**previous, "nonterminal": previous["pending"]}
            provider_event_state[tool] = previous
            inspector = "gemini_get_request" if tool == "gemini_events" else "grokbot_inspect"
            for event in previous.get("nonterminal", {}).values():
                add_rows(event.get("peers", []), inspector)
            coverage.append({"source": tool, "status": recovery.get("status", "not_enabled"), "complete": False,
                             "next_cursor": previous.get("cursor", 0), "observed_at": previous.get("last_event_read_at"),
                             "status_observed_at": at, "unread_regions": ["provider-event collection awaiting the recorded recovery condition"],
                             "recovery": recovery})

    def dedupe(rows):
        merged = {}
        for row in rows:
            key = (row.get("session_id"), row.get("agent_id"))
            old = merged.get(key)
            if old:
                refs = sorted(set(old["source_refs"] + row["source_refs"]))
                metadata = {**old.get("metadata", {}), **row.get("metadata", {})}
                if row["status"] != "unknown" or not old.get("fresh"):
                    merged[key] = row
                merged[key]["source_refs"] = refs
                merged[key]["metadata"] = metadata
            else:
                merged[key] = row
        return sorted(merged.values(), key=lambda row: (str(row.get("harness")), str(row.get("session_id")), str(row.get("agent_id"))))
    peers = dedupe(live)
    runtime_keys = {(peer["session_id"], peer["agent_id"]) for peer in peers}
    declarations = dedupe([peer for peer in declared if (peer["session_id"], peer["agent_id"]) not in runtime_keys])
    counts = {"observed_instances": len(peers), "executing": sum(peer["status"] == "executing" for peer in peers),
              "waiting": sum(peer["status"] == "waiting" for peer in peers), "unknown": sum(peer["status"] == "unknown" for peer in peers), "declared_instances": len(declarations),
              "loaded_idle_sessions": sum(peer["status"] == "idle_session" for peer in declarations)}
    return {"peers": peers, "declared_peers": declarations, "counts": counts, "coverage": coverage, "observed_at": at,
            "provider_event_state": provider_event_state,
            "state": {"provider_events": {tool: {**value, "pending": value.get("nonterminal", {})} for tool, value in provider_event_state.items()}},
            "complete": bool(coverage) and all(row.get("complete") for row in coverage),
            "scope": "observed instances across connected runtime roads; protocol declarations and provider tabs reported separately"}
