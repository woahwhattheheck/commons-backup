"""Incremental discovery of every available account/service source road.

Only existing metadata, secure credential facilities and provider read APIs are
used. Discovery never switches logins, launches peers, subscribes to services or
writes source state. Listing coverage is distinct from full-content backfill.
"""
from __future__ import annotations

import hashlib
import base64
import ctypes
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping

from .notifications import redact


GITHUB_SCOPES = {
    "issues": "repos/{repo}/issues?state=all&per_page=100",
    "issue_comments": "repos/{repo}/issues/comments?per_page=100",
    "pull_requests": "repos/{repo}/pulls?state=all&per_page=100",
    "reviews": "repos/{repo}/pulls/{number}/reviews?per_page=100",
    "review_comments": "repos/{repo}/pulls/comments?per_page=100",
    "commits": "repos/{repo}/commits?per_page=100",
    "commit_comments": "repos/{repo}/comments?per_page=100",
    "refs": "repos/{repo}/git/matching-refs/",
    "branches": "repos/{repo}/branches?per_page=100",
    "tags": "repos/{repo}/tags?per_page=100",
    "trees": "repos/{repo}/git/trees/{tree_sha}?recursive=1",
    "blobs": "repos/{repo}/git/blobs/{sha}",
    "contents": "repos/{repo}/contents/{path}",
    "actions_runs": "repos/{repo}/actions/runs?per_page=100",
    "actions_jobs": "repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
    "actions_logs": "repos/{repo}/actions/jobs/{job_id}/logs",
    "actions_artifacts": "repos/{repo}/actions/artifacts?per_page=100",
    "releases": "repos/{repo}/releases?per_page=100",
    "deployments": "repos/{repo}/deployments?per_page=100",
    "deployment_statuses": "repos/{repo}/deployments/{deployment_id}/statuses?per_page=100",
    "events": "repos/{repo}/events?per_page=100",
    "discussions": "graphql:repository.discussions(cursor)",
    "checks": "repos/{repo}/commits/{ref}/check-runs?per_page=100",
    "statuses": "repos/{repo}/commits/{ref}/statuses?per_page=100",
    "security_alerts": "repos/{repo}/dependabot/alerts?per_page=100",
    "notifications": "notifications?all=true&per_page=100",
}
SLACK_SCOPES = {
    "history": "conversations.history", "replies": "conversations.replies",
    "files": "files.list/files.info/private_file_download", "edits": "message.changed/source event metadata",
    "deletions": "message.deleted/source event metadata", "retention": "provider-retained history and available retention metadata",
    "reactions": "reactions.get", "pins": "pins.list", "bookmarks": "bookmarks.list",
    "canvases": "canvases.info", "audit_logs": "audit.logs.read when exposed by the connected account",
}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:/@+ -]{1,300}$")


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _id(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _name(value):
    if isinstance(value, (str, int)) and _SAFE_NAME.fullmatch(str(value)):
        return str(value)
    return None


def _reference(value):
    # Retrieval references may be URI-encoded or Unicode. They are supplied by
    # the secure reference facility, never derived from a credential value.
    if isinstance(value, str) and 0 < len(value) <= 8192 and not any(ord(character) < 32 for character in value):
        return value
    return None


def _service(value, reference=None):
    raw = str(value or reference or "unknown").lower()
    parts = raw.strip("/").split("/")
    if parts[0] == "vault":
        parts = parts[1:]
    if not parts:
        return "shared-vault"
    if parts[0] in {"commons", "shared"}:
        return "shared-vault"
    if parts[0].startswith(("owner-", "swe2-")) or parts[0] in {"transfer", "windows", "deposits"}:
        return "shared-vault"
    if parts[0] == "file":
        text = "/".join(parts[1:])
        for harness in ("claude", "codex", "gemini", "ssh"):
            if "." + harness in text:
                return harness
        return "shared-vault"
    if parts[0] in {"cloud", "environment"}:
        text = "/".join(parts)
        for target in ("slack", "discord", "vercel", "github", "webmcp"):
            if target in text:
                return target
        return "github-actions" if parts[0] == "cloud" else "shared-vault"
    if parts[0] == "codex" and "mcp" in parts:
        position = parts.index("mcp") + 1
        return parts[position] if position < len(parts) else "codex"
    return _name(parts[0]) or "unknown"


def _safe_output(value):
    # Secure references are metadata, not credential values. Preserve their
    # exact retrieval labels while still scrubbing secret-like string formats.
    if isinstance(value, Mapping):
        result = {}
        for key, child in value.items():
            if key in {"credential_ref", "credential_refs", "vault_ref", "keyring_ref", "account_ref", "credential_facility"}:
                result[str(key)] = _safe_output(child)
            elif redact({str(key): None}).get(str(key)) == "[REDACTED]":
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _safe_output(child)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_output(child) for child in value]
    return redact(value)


def _dpapi(data, decrypt=False):
    if os.name != "nt":
        raise DiscoveryError("native_snapshot_custody_requires_existing_windows_profile")
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming = Blob(len(data), buffer)
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(Blob)]
    function.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise DiscoveryError("native_snapshot_custody_failed")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


def save_native_snapshot(path, *, payload, service, account_ref, workspace_id=None, observed_at=None, complete=False):
    """Preserve the full original native result under existing Windows custody."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    descriptor = {"service": service, "account_ref": account_ref, "workspace_id": workspace_id,
                  "observed_at": observed_at or _now(), "complete": complete,
                  "custody": "windows_dpapi_current_profile", "source_envelope_sha256": hashlib.sha256(raw).hexdigest(),
                  "source_envelope_bytes": len(raw), "source_envelope_encrypted": base64.b64encode(_dpapi(raw)).decode("ascii"),
                  "reader": {"road": "native_installed_service_connector", "mode": "read_only", "scope": "all account/provider-visible retained source contents"}}
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
    return {key: value for key, value in descriptor.items() if key != "source_envelope_encrypted"}


def load_native_snapshot(path):
    """Open the retained exact source in caller memory without printing it."""
    descriptor = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if descriptor.get("custody") == "windows_dpapi_current_profile":
        raw = _dpapi(base64.b64decode(descriptor["source_envelope_encrypted"], validate=True), decrypt=True)
        if hashlib.sha256(raw).hexdigest() != descriptor["source_envelope_sha256"]:
            raise DiscoveryError("native_snapshot_custody_integrity_failed")
        descriptor["payload"] = json.loads(raw.decode("utf-8"))
    return descriptor


def _unwrap(value):
    for _ in range(12):
        if isinstance(value, Mapping) and (value.get("isError") or value.get("ok") is False or value.get("error")):
            raise DiscoveryError(str(value.get("error") or "source_read_error"))
        if isinstance(value, Mapping) and isinstance(value.get("result"), (dict, list)):
            value = value["result"]
        elif isinstance(value, Mapping) and isinstance(value.get("structuredContent"), (dict, list)):
            value = value["structuredContent"]
        elif isinstance(value, Mapping) and isinstance(value.get("content"), list):
            texts = [row["text"] for row in value["content"] if row.get("type") == "text"]
            if not texts:
                break
            value = json.loads(texts[0])
        else:
            break
    return value


class DiscoveryError(RuntimeError):
    def __init__(self, code, *, retry_after=None, reset_at=None):
        super().__init__(code)
        self.code = _name(code) or "source_read_failed"
        self.retry_after = retry_after
        self.reset_at = reset_at


def _run(command, timeout=30):
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DiscoveryError(type(error).__name__) from None
    if result.returncode:
        # Never return stderr/stdout; auth tools may contain credential material.
        raise DiscoveryError("native_cli_read_failed")
    return result.stdout


def _native_gh_accounts():
    candidates = []
    if os.environ.get("GH_CONFIG_DIR"):
        candidates.append(Path(os.environ["GH_CONFIG_DIR"]) / "hosts.yml")
    if os.environ.get("APPDATA"):
        candidates.append(Path(os.environ["APPDATA"]) / "GitHub CLI" / "hosts.yml")
    candidates.append(Path.home() / ".config" / "gh" / "hosts.yml")
    accounts = {}
    files = []
    for path in dict.fromkeys(candidates):
        if not path.is_file():
            continue
        files.append(str(path))
        host, active, in_users, users_indent, member_indent = None, None, False, 0, None
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            top = re.fullmatch(r"([A-Za-z0-9.-]+):\s*", line)
            if top:
                host, active, in_users, member_indent = top.group(1), None, False, None
                continue
            user = re.fullmatch(r"\s+user:\s*[\"']?([A-Za-z0-9][A-Za-z0-9-]{0,38})[\"']?\s*", line)
            if user and host:
                active = user.group(1)
                accounts[(host, active)] = {"account_ref": "github:" + host + ":" + active, "host": host, "login": active, "active": True, "native_keyring": True}
            if re.fullmatch(r"\s+users:\s*", line):
                in_users = True
                users_indent = len(line) - len(line.lstrip())
                member_indent = None
                continue
            indentation = len(line) - len(line.lstrip())
            if line.strip() and indentation <= users_indent:
                in_users = False
            member = re.fullmatch(r"\s+([A-Za-z0-9][A-Za-z0-9-]{0,38}):\s*", line)
            if in_users and member and host and indentation > users_indent and (member_indent is None or member_indent == indentation):
                member_indent = indentation
                login = member.group(1)
                accounts[(host, login)] = {"account_ref": "github:" + host + ":" + login, "host": host, "login": login, "active": login == active, "native_keyring": True}
    return list(accounts.values()), files


def _existing_credential(config, reference):
    root = config.get("existing_commons_runtime") or "C:/Users/lucys/Documents/Codex/2026-08-25/yo/work/commons-spark-link"
    if str(root) not in sys.path:
        sys.path.append(str(root))
    import integrations
    existing_path = str(Path(root) / "integrations")
    if existing_path not in integrations.__path__:
        integrations.__path__.append(existing_path)
    from integrations.shared_equipment.credential_client import retrieve_local
    return retrieve_local(reference)


def _http_json(url, timeout, *, bearer=None):
    headers = {"Accept": "application/json", "User-Agent": "Commons-Swarm-Telemetry"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        retry_after = error.headers.get("Retry-After")
        reset_at = error.headers.get("X-RateLimit-Reset")
        code = "rate_limited" if error.code in (403, 429) and (retry_after or reset_at) else "http_" + str(error.code)
        raise DiscoveryError(code, retry_after=retry_after, reset_at=reset_at) from None
    except Exception as error:
        raise DiscoveryError(type(error).__name__) from None
    if len(raw) > 16 * 1024 * 1024:
        raise DiscoveryError("response_size_limit")
    return json.loads(raw.decode("utf-8"))


def _default_slack_reader(config):
    root = config.get("existing_commons_runtime") or "C:/Users/lucys/Documents/Codex/2026-08-25/yo/work/commons-spark-link"
    if str(root) not in sys.path:
        sys.path.append(str(root))
    import integrations
    existing_path = str(Path(root) / "integrations")
    if existing_path not in integrations.__path__:
        integrations.__path__.append(existing_path)
    # Existing installed secure facility: no new vault, key cache or model data.
    from integrations.grok_slack.handoff import default_vault_path, read_vault
    timeout = float(config.get("timeout_seconds", 25))

    def read(method, arguments):
        if method not in {"auth.test", "conversations.list", "team.info", "users.conversations"}:
            raise DiscoveryError("discovery_read_method_required")
        token = read_vault(default_vault_path())["bot_token"]
        value = _http_json("https://slack.com/api/" + method + "?" + urllib.parse.urlencode(arguments), timeout, bearer=token)
        token = None
        if value.get("ok") is False:
            raise DiscoveryError(str(value.get("error") or "slack_read_failed"))
        return value
    return read


def _sqlite_channels(path):
    file = Path(path)
    if not file.is_file():
        raise DiscoveryError("native_slack_cache_missing")
    channels = set()
    spans = {}
    with closing(sqlite3.connect(file.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in sorted(tables):
            quoted = '"' + name.replace('"', '""') + '"'
            columns = {row[1] for row in db.execute("PRAGMA table_info(" + quoted + ")")}
            field = "channel" if "channel" in columns else "channel_id" if "channel_id" in columns else None
            if field:
                for row in db.execute("SELECT DISTINCT " + field + " FROM " + quoted + " WHERE " + field + " IS NOT NULL"):
                    if re.fullmatch(r"[CGD][A-Z0-9]{7,}", str(row[0])):
                        channels.add(str(row[0]))
                if "message_ts" in columns:
                    row = db.execute("SELECT MIN(message_ts),MAX(message_ts),COUNT(*) FROM " + quoted).fetchone()
                    spans[name] = {"oldest": row[0], "newest": row[1], "records": row[2]}
    return sorted(channels), spans


def _metadata_rows(value):
    rows = []
    if isinstance(value, list):
        for row in value:
            rows.extend(_metadata_rows(row))
    elif isinstance(value, Mapping):
        if any(key in value for key in ("service", "provider", "credential_ref", "account_ref", "connector", "source_id", "label", "platform", "family")):
            rows.append(value)
        for key in ("references", "sources", "accounts", "services", "providers", "surfaces", "deposits", "resources", "entries"):
            child = value.get(key)
            if isinstance(child, Mapping):
                for label, row in child.items():
                    if isinstance(row, Mapping):
                        rows.extend(_metadata_rows({"label": label, **row}))
            elif isinstance(child, list):
                rows.extend(_metadata_rows(child))
    return rows


def _connector_channels(value):
    value = _unwrap(value)
    if isinstance(value, Mapping) and isinstance(value.get("channels"), list):
        return value["channels"], value.get("response_metadata", {}).get("next_cursor") or "", None
    text = value.get("result") if isinstance(value, Mapping) else value
    if not isinstance(text, str):
        return [], None, None
    rows = []
    for block in re.finditer(r"(?ms)^### (.*?)\n(.*?)(?=^### |\Z)", text):
        heading, body = block.groups()
        fields = {match.group(1): match.group(2) for match in re.finditer(r"(?m)^- \*\*([^:*]+):\*\* (.*)$", body)}
        channel = fields.get("ID")
        if not channel or not re.fullmatch(r"[CGD][A-Z0-9]+", channel):
            continue
        kind = fields.get("Type")
        rows.append({"id": channel, "name": heading[1:] if heading.startswith("#") else None,
                     "display_name": heading, "type": kind, "is_private": kind in {"Private Channel", "Direct Message", "Group DM"},
                     "is_im": kind == "Direct Message", "is_mpim": kind == "Group DM", "is_archived": fields.get("Archived") == "Yes" if "Archived" in fields else None,
                     "user_id": fields.get("User ID"), "members_text": fields.get("Members"), "purpose": fields.get("Purpose"), "source_fields": fields})
    next_page = re.search(r'(?m)^Pagination:\s*More results available\.\s*Use cursor:\s*"([^"\r\n]+)"\s*$', text)
    if next_page:
        # Native cursors are opaque, including their padding. Retain the exact
        # value so a host can continue this incomplete conversation listing.
        return rows, next_page.group(1), False
    totals = re.search(r"showing\s+(\d+)\s+of\s+(\d+)\s+total", text)
    complete = bool(totals) and int(totals.group(1)) == int(totals.group(2)) == len(rows)
    return rows, "" if complete else None, complete


def discover_sources(config: Mapping | None = None, state: Mapping | None = None) -> dict:
    """List all discoverable scope with provider-sized resumable pagination.

    Config accepts source_catalog/path, tool_reader, credential_references,
    resource_ledger/url, inventory_paths, slack_cache_paths, slack_readers
    [{account_ref,reader(method,args),workspace_id}], github_readers
    [{account_ref,host,reader(endpoint)}], github_accounts, gh, and page_budget.
    Returned state is caller-persisted, never written into provider sources.
    page_budget defaults to all pages; an explicit bounded budget preserves
    continuation and discovered rows. Completed listings refresh on interval.
    connector_slack_snapshots / connector_github_snapshots ingest actual native
    connector results already read by the host, with account_ref, workspace_id/
    host, payload, complete and observed_at. This keeps all connector accounts
    in scope alongside native CLI/vault roads without changing auth state.
    """
    config = dict(config or {})
    state = dict(state or {})
    at = _now()
    timeout = float(config.get("timeout_seconds", 25))
    refresh = float(config.get("discovery_refresh_seconds", 900))
    page_budget = config.get("page_budget")
    remaining = None if page_budget is None else max(0, int(page_budget))
    sources, accounts, coverage = {}, {}, []
    verified_account_refs = {"slack": set(), "github": set()}
    channels = set(config.get("slack_channels") or []) | set(state.get("slack_channels") or [])
    repositories = set(config.get("github_repositories") or []) | set(state.get("github_repositories") or [])
    continuation = dict(state.get("continuation") or {})
    repo_metadata = dict(state.get("repo_metadata") or {})
    channel_metadata = dict(state.get("channel_metadata") or {})
    org_metadata = dict(state.get("org_metadata") or {})
    for path in config.get("connector_snapshot_paths", []):
        try:
            snapshot = load_native_snapshot(path)
            service = snapshot.get("service")
            key = "connector_slack_snapshots" if service == "slack" else "connector_github_snapshots" if service == "github" else None
            if key:
                config[key] = list(config.get(key) or []) + [snapshot]
            else:
                metadata_sources_from_snapshot = snapshot.get("payload")
                config["source_catalog"] = list(_metadata_rows(config.get("source_catalog") or {})) + list(_metadata_rows(metadata_sources_from_snapshot))
        except Exception as error:
            coverage.append({"source": "native_connector_snapshot", "source_locator": str(path), "status": "pending_recovery", "complete": False, "error": type(error).__name__})

    def account(service, reference, **metadata):
        ref = _name(reference) or service + ":unresolved-account"
        key = service + ":" + ref
        identity_state = metadata.get("identity_state")
        initial_status = "provider_observed" if identity_state == "provider_observed" else "pending_recovery" if identity_state is not None else "discovered"
        current = accounts.setdefault(key, {"account_ref": ref, "service": service, "status": initial_status, "credential_refs": [], "metadata": {}})
        current["metadata"].update({k: v for k, v in metadata.items() if isinstance(v, (str, int, bool)) or v is None})
        if initial_status == "provider_observed":
            current["status"] = "provider_observed"
        elif initial_status == "pending_recovery" and current.get("status") != "provider_observed":
            current["status"] = "pending_recovery"
        return current

    def source(service, reference, scope, locator=None, **values):
        sid = service + ":" + _id(reference, scope, locator)
        row = {"source_id": sid, "service": service, "source": service, "account_ref": reference,
               "scope": scope, "status": "pending_backfill", "complete": False, "source_locator": locator,
               "observed_at": at, **values}
        sources[sid] = row
        return row

    def read_error(name, error, **fields):
        coverage.append({"source": name, "status": "pending_recovery", "complete": False,
                         "error": getattr(error, "code", type(error).__name__), "retry_after": getattr(error, "retry_after", None),
                         "reset_at": getattr(error, "reset_at", None), "observed_at": at, **fields})

    def fresh_done(key):
        item = continuation.get(key, {})
        return item.get("complete") and time.time() - float(item.get("completed_epoch", 0)) < refresh

    def spend_page():
        nonlocal remaining
        if remaining is None:
            return True
        if remaining <= 0:
            return False
        remaining -= 1
        return True

    catalog = config.get("source_catalog")
    catalog_path = config.get("source_catalog_path") or "work/telemetry-runtime/service-catalog.json"
    if catalog is None:
        try:
            catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8-sig"))
        except Exception as error:
            read_error("installed_service_catalog", error)
    catalog_evidence_rows = 0
    catalog_unbound_accounts = 0
    for row in _metadata_rows(catalog or {}):
        catalog_evidence_rows += 1
        service = _name(row.get("service") or row.get("source") or row.get("provider")) or "unknown"
        account_identity = _name(row.get("account_ref") or row.get("account_id") or row.get("account"))
        if account_identity is None:
            catalog_unbound_accounts += 1
        ref = account_identity or service + ":connector-account-unresolved"
        tools = sorted({_name(name) for name in row.get("tools", []) if _name(name)})
        account(service, ref, identity_state="unresolved" if account_identity is None else "observed")
        source(service, ref, "all accounts and all provider-retained available content/activity", row.get("source_id"),
               status="pending_recovery" if account_identity is None else "reader_binding_pending", tools=tools,
               reader={"road": "installed_service_connector", "tool_names": tools},
               identity_state="unresolved" if account_identity is None else "observed",
               unread_regions=["provider account identity is not attached to this catalog entry" if account_identity is None else "all service content and activity not yet ingested"])
    if catalog is not None:
        coverage.append({"source": "installed_service_catalog", "status": "observed", "complete": False,
                         "listing_complete": True, "services": len(sources), "observed_at": at,
                         "scope": "known installed-service catalog entries only",
                         "unread_regions": ["services and accounts not represented in this catalog", "provider account identities and service capabilities not enumerated by the catalog"]})

    metadata_sources = []
    try:
        refs = config.get("credential_references")
        if refs is None:
            reader = config.get("tool_reader")
            if callable(reader):
                refs = reader("credential_references", {})
            else:
                from .runner import Gateway
                refs = Gateway(config.get("gateway") or config.get("gateway_url") or "http://127.0.0.1:8878", timeout).call("credential_references", {})
        refs = _unwrap(refs)
        metadata_sources.append(("shared_credential_metadata", refs))
        coverage.append({"source": "shared_credential_metadata", "status": "observed", "complete": True, "references": len(refs.get("references", [])), "observed_at": at})
    except Exception as error:
        read_error("shared_credential_metadata", error)
    try:
        ledger = config.get("resource_ledger")
        if ledger is None:
            ledger = _http_json(config.get("resource_ledger_url") or "https://raw.githubusercontent.com/woahwhattheheck/commons/main/ground/RESOURCE_LEDGER.json", timeout)
        metadata_sources.append(("public_resource_ledger", ledger))
        coverage.append({"source": "public_resource_ledger", "status": "observed", "complete": True, "observed_at": at, "scope": "declared account/service discovery; no capacity inferred"})
    except Exception as error:
        read_error("public_resource_ledger", error)
    for path in config.get("inventory_paths", ["C:/Users/lucys/.commons/credential_sources.json"]):
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            metadata_sources.append(("configured_reference_metadata", value))
            coverage.append({"source": "configured_reference_metadata", "source_locator": str(path), "status": "observed", "complete": True, "observed_at": at})
        except Exception as error:
            read_error("configured_reference_metadata", error, source_locator=str(path))
    metadata_evidence_rows = 0
    unresolved_bindings = {}
    observed_service_names = set()
    for origin, value in metadata_sources:
        for row in _metadata_rows(value):
            metadata_evidence_rows += 1
            credential_ref = _reference(row.get("credential_ref") or row.get("vault_ref") or row.get("keyring_ref"))
            reference_evidence = _reference(credential_ref or row.get("target") or row.get("pointer") or row.get("label"))
            service = _name(row.get("service") or row.get("provider") or row.get("connector"))
            if not service and reference_evidence:
                service = reference_evidence.split("/", 1)[0].split(":", 1)[0]
            service = _service(service or _name(row.get("label") or row.get("id")), reference_evidence)
            explicit_reference = _name(row.get("account_ref") or row.get("account_id") or row.get("account") or row.get("owner"))
            candidate_reference = explicit_reference
            identity_state = "source_asserted_unverified" if explicit_reference else "unresolved"
            if reference_evidence and service == "github":
                parts = reference_evidence.strip("/").split("/")
                if "github" in parts and parts.index("github") + 1 < len(parts):
                    login = parts[parts.index("github") + 1]
                    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login) and login not in {"token", "api-key", "access", "refresh", "oauth", "app", "bot"}:
                        candidate_reference = candidate_reference or "github:github.com:" + login
                        if not explicit_reference:
                            identity_state = "reference_alias_unverified"
            if reference_evidence and "/slack/accounts/" in reference_evidence:
                label = reference_evidence.split("/slack/accounts/", 1)[1].split("/", 1)[0]
                candidate_reference = candidate_reference or "slack:" + label
                if not explicit_reference:
                    identity_state = "reference_alias_unverified"
            if row.get("identity_state") in {"provider_observed", "authenticated"} or row.get("provider_identity_verified") is True:
                identity_state = "provider_observed"
            identity_verified = identity_state == "provider_observed"
            if identity_verified and not candidate_reference:
                identity_state = "unresolved"
                identity_verified = False
            if identity_verified and candidate_reference:
                reference = candidate_reference
            else:
                evidence_id = _id(service, reference_evidence or (origin, row.get("source_id") or row.get("id") or candidate_reference))
                reference = service + ":unresolved-evidence:" + evidence_id
            observed_service_names.add(service)
            entry = account(service, reference, identity_state=identity_state,
                            candidate_account_ref=candidate_reference if not identity_verified else None)
            if credential_ref:
                entry["credential_refs"] = sorted(set(entry["credential_refs"] + [credential_ref]))
            if not identity_verified:
                group = unresolved_bindings.setdefault(service, {"evidence": {}, "origins": set()})
                evidence_id = _id(service, reference_evidence or row.get("source_id") or row.get("id") or row.get("label") or origin)
                group["evidence"][evidence_id] = reference
                group["origins"].add(origin)
            source(service, reference, "all available account/service activity and retained content", credential_ref or _name(row.get("source_id") or row.get("id") or row.get("target") or row.get("pointer")),
                   status="reader_binding_pending" if identity_verified else "pending_recovery",
                   reader={"road": origin, "credential_ref": credential_ref},
                   unread_regions=["provider reader binding and full-content listing pending"],
                   identity_state=identity_state, candidate_account_ref=candidate_reference if not identity_verified else None)

    universe_recovery = {
        "source": "service_account_universe", "status": "pending_recovery", "complete": False,
        "observed_at": at, "metadata_evidence_rows": metadata_evidence_rows,
        "catalog_evidence_rows": catalog_evidence_rows, "catalog_unbound_accounts": catalog_unbound_accounts,
        "observed_services": sorted(observed_service_names),
        "unresolved_account_scopes": len(unresolved_bindings),
        "scope": "all accounts and all services across existing credential, configuration, connector and observability evidence",
        "unread_regions": [
            "accounts and services without evidence in the supplied secure-reference facility, resource ledger, connector catalog, configuration roots or observability sources",
            "provider account universes not enumerable through a supplied connected reader",
            "service-specific capabilities, quotas and retained activity not exposed by current readers",
        ],
        "recovery": "continue discovery from additional existing source metadata and bind read-only provider readers for each observed account/service",
    }
    source("service_account_universe", "universe:unresolved", universe_recovery["scope"], "cross-source-inventory-closure",
           status="pending_recovery", reader={"road": "existing metadata, credentials, connectors and observability"},
           unread_regions=universe_recovery["unread_regions"])
    coverage.append(universe_recovery)

    cache_paths = config.get("slack_cache_paths") or ["C:/Users/lucys/.commons/grok_slack.sqlite3"]
    for path in cache_paths:
        try:
            found, spans = _sqlite_channels(path)
            channels.update(found)
            coverage.append({"source": "native_slack_cache_metadata", "source_locator": str(path), "status": "observed", "complete": True,
                             "channels": len(found), "retained_spans": spans, "observed_at": at, "scope": "cache metadata only; workspace/account mapping and source completeness separate"})
            for channel in found:
                source("slack", "slack:cache-account-unresolved", "all retained channel/thread/file/edit/deletion activity", channel,
                       reader={"road": "existing_slack_service", "methods": SLACK_SCOPES}, status="account_mapping_pending")
        except Exception as error:
            read_error("native_slack_cache_metadata", error, source_locator=str(path))

    slack_readers = list(config.get("slack_readers") or [])
    if not any(str(row.get("account_ref")) == "slack:existing-grok-vault" for row in slack_readers):
        try:
            slack_readers.append({"account_ref": "slack:existing-grok-vault", "reader": _default_slack_reader(config)})
        except Exception as error:
            read_error("slack:existing-grok-vault", error)
            account("slack", "slack:existing-grok-vault", identity_state="pending_recovery")
    for road in slack_readers:
        ref = str(road.get("account_ref") or "slack:connector-account-unresolved")
        reader = road.get("reader")
        acc = account("slack", ref)
        key = "slack:list:" + ref
        try:
            if not callable(reader):
                raise DiscoveryError("slack_reader_binding_pending")
            identity = _unwrap(reader("auth.test", {}))
            team = road.get("workspace_id") or identity.get("team_id")
            verified_account_refs["slack"].add(ref)
            acc["status"] = "provider_observed"
            acc["metadata"].update(identity_state="provider_observed", identity_method="slack.auth.test")
            acc["metadata"].update(workspace_id=team, user_id=identity.get("user_id"), bot_id=identity.get("bot_id"))
            for conversation_type in ("public_channel", "private_channel", "im", "mpim"):
                type_key = key + ":" + conversation_type
                cursor = continuation.get(type_key, {}).get("cursor") or ""
                listed = int(continuation.get(type_key, {}).get("records", 0))
                complete = fresh_done(type_key)
                if continuation.get(type_key, {}).get("complete") and not complete:
                    cursor, listed = "", 0
                try:
                    while not complete and spend_page():
                        args = {"types": conversation_type, "exclude_archived": "false", "limit": 200}
                        if cursor:
                            args["cursor"] = cursor
                        if team:
                            args["team_id"] = team
                        response = _unwrap(reader(road.get("list_method") or "conversations.list", args))
                        for row in response.get("channels", []):
                            channel = _name(row.get("id"))
                            if not channel:
                                continue
                            channels.add(channel)
                            channel_metadata[ref + ":" + channel] = {"channel_id": channel, "account_ref": ref, "workspace_id": team, "archived": bool(row.get("is_archived")), "private": bool(row.get("is_private")), "is_im": bool(row.get("is_im")), "is_mpim": bool(row.get("is_mpim")), "name": _name(row.get("name"))}
                            listed += 1
                        next_cursor = response.get("response_metadata", {}).get("next_cursor") or ""
                        if next_cursor and next_cursor == cursor:
                            raise DiscoveryError("slack_cursor_stalled")
                        cursor = next_cursor
                        complete = not cursor
                        continuation[type_key] = {"cursor": cursor, "records": listed, "complete": complete, "completed_epoch": time.time() if complete else None}
                    coverage.append({"source": type_key, "status": "observed" if complete else "backfilling", "complete": complete, "records": listed, "cursor": cursor, "workspace_id": team,
                                     "observed_at": at, "scope": "all API-visible " + conversation_type + " conversations including archived", "unread_regions": [] if complete else ["conversations after cursor " + cursor]})
                except Exception as error:
                    read_error(type_key, error, continuation=continuation.get(type_key, {}))
                    source("slack", ref, "all " + conversation_type + " conversations and their retained contents", "conversations.list:" + conversation_type,
                           status="pending_recovery", reader={"road": "existing_secure_slack_client", "types": conversation_type})
        except Exception as error:
            read_error(key, error, continuation=continuation.get(key, {}))
            source("slack", ref, "all workspaces/conversations and their retained contents", "conversations.list", status="pending_recovery", reader={"road": "existing_secure_slack_client"})
    for row in channel_metadata.values():
        source("slack", row["account_ref"], "all provider-retained channel contents, history, replies, files, edits and deletions", row["channel_id"],
               workspace_id=row.get("workspace_id"), reader={"road": "existing_slack_service", "methods": SLACK_SCOPES}, listing_metadata=row,
               unread_regions=["all retained history pages", "all reply pages and file contents", "retained edit/deletion events and retention scope"])

    for snapshot in config.get("connector_slack_snapshots", []):
        ref = str(snapshot.get("account_ref") or "slack:installed-connector-account-unresolved")
        team = snapshot.get("workspace_id")
        account("slack", ref, workspace_id=team, connector="native installed Slack", identity_state="connector_account_unverified")
        coverage.append({"source": "account_binding:" + ref, "status": "pending_recovery", "complete": False,
                         "service": "slack", "account_ref": ref, "observed_at": snapshot.get("observed_at") or at,
                         "scope": "native connector snapshot account selector has not been confirmed by an account-specific identity response",
                         "unread_regions": ["provider-verified account identity and reader binding for this connector snapshot"]})
        try:
            rows, cursor, derived_complete = _connector_channels(snapshot.get("payload", {}))
            complete = bool(snapshot.get("complete", derived_complete if derived_complete is not None else cursor == ""))
            for row in rows:
                channel = _name(row.get("id"))
                if channel:
                    channels.add(channel)
                    channel_metadata[ref + ":" + channel] = {"channel_id": channel, "account_ref": ref, "workspace_id": team,
                                                             "archived": row.get("is_archived"), "private": row.get("is_private"), "is_im": row.get("is_im"), "is_mpim": row.get("is_mpim"), "name": row.get("name"),
                                                             "display_name": row.get("display_name"), "type": row.get("type"), "user_id": row.get("user_id"), "members_text": row.get("members_text"), "purpose": row.get("purpose"), "source_fields": row.get("source_fields")}
                    source("slack", ref, "all provider-retained channel history, replies, files, edits and deletion events", channel,
                           workspace_id=team, listing_metadata=channel_metadata[ref + ":" + channel], reader={"road": "native_installed_slack_connector", "methods": SLACK_SCOPES}, unread_regions=["full retained channel/thread/file content backfill"])
            coverage.append({"source": "slack:connector-list:" + ref, "status": "observed" if complete else "backfilling", "complete": complete,
                             "records": len(rows), "cursor": cursor, "workspace_id": team, "observed_at": snapshot.get("observed_at") or at,
                             "scope": "actual native connector conversation listing; full content backfill separate"})
        except Exception as error:
            read_error("slack:connector-list:" + ref, error)

    gh = config.get("gh") or "gh"
    gh_accounts = list(config.get("github_accounts") or [])
    for observed in accounts.values():
        ref = observed.get("account_ref", "")
        match = re.fullmatch(r"github:([A-Za-z0-9.-]+):([A-Za-z0-9][A-Za-z0-9-]{0,38})", ref)
        if match:
            gh_accounts.append({"account_ref": ref, "host": match.group(1), "login": match.group(2), "configured_secure_reference": True})
    try:
        native, config_files = _native_gh_accounts()
        if native:
            gh_accounts.extend(native)
        else:
            status = json.loads(_run([gh, "auth", "status", "--json", "hosts"], max(timeout, 45)))
            for host, entries in status.get("hosts", {}).items():
                for row in entries:
                    login = _name(row.get("login"))
                    if login:
                        gh_accounts.append({"account_ref": "github:" + str(host) + ":" + login, "host": host, "login": login, "active": bool(row.get("active")), "native_keyring": True})
        gh_accounts = list({(row.get("host") or "github.com", row.get("login")): row for row in gh_accounts}.values())
        coverage.append({"source": "native_gh_accounts", "status": "observed", "complete": True, "accounts": len(gh_accounts), "observed_at": at, "source_locator": config_files, "scope": "configured accounts/hosts metadata; provider authentication checked by actual listings"})
    except Exception as error:
        read_error("native_gh_accounts", error)
    github_readers = list(config.get("github_readers") or [])
    for row in gh_accounts:
        host = str(row.get("host") or "github.com")
        login = _name(row.get("login"))
        ref = str(row.get("account_ref") or "github:" + host + ":" + str(login or "current"))
        account("github", ref, host=host, login=login, active=bool(row.get("active")), credential_facility="existing shared secure facility; native gh keyring fallback")
        def read(endpoint, host=host, login=login):
            if not login:
                return json.loads(_run([gh, "api", "--hostname", host, "--method", "GET", endpoint], timeout))
            try:
                token = _existing_credential(config, "github/" + login) if host == "github.com" else None
            except Exception:
                token = None
            if not isinstance(token, str) or not token:
                token = _run([gh, "auth", "token", "--hostname", host, "--user", login], max(timeout, 45)).strip()
            api = "https://api.github.com/" if host == "github.com" else "https://" + host + "/api/v3/"
            result = _http_json(api + endpoint.lstrip("/"), timeout, bearer=token)
            token = None
            return result
        github_readers.append({"account_ref": ref, "host": host, "reader": read})
    unique_github_roads = {str(row.get("account_ref") or "github:connector-account-unresolved"): row for row in github_readers}
    for snapshot in config.get("connector_github_snapshots", []):
        ref = str(snapshot.get("account_ref") or "github:installed-connector-account-unresolved")
        host = str(snapshot.get("host") or "github.com")
        account("github", ref, host=host, connector="native installed GitHub", identity_state="connector_account_unverified")
        coverage.append({"source": "account_binding:" + ref, "status": "pending_recovery", "complete": False,
                         "service": "github", "account_ref": ref, "observed_at": snapshot.get("observed_at") or at,
                         "scope": "native connector snapshot account selector has not been confirmed by an account-specific identity response",
                         "unread_regions": ["provider-verified account identity and reader binding for this connector snapshot"]})
        try:
            payload = _unwrap(snapshot.get("payload", {}))
            rows = payload if isinstance(payload, list) else payload.get("repositories", payload.get("repos", []))
            for row in rows:
                repo = _name(row.get("full_name") or row.get("repository_full_name") or row.get("repo_full_name") or row.get("nameWithOwner"))
                if repo:
                    repositories.add(repo)
                    visibility = row.get("visibility")
                    private = row.get("private")
                    if private is None and visibility in {"public", "private", "internal"}:
                        private = visibility != "public"
                    repo_metadata[ref + ":" + repo] = {"account_ref": ref, "host": host, "repository": repo, "private": private, "visibility": visibility, "archived": row.get("archived"), "default_branch": _name(row.get("default_branch")), "id": row.get("id")}
            coverage.append({"source": "github:connector-list:" + ref, "status": "observed" if snapshot.get("complete") else "backfilling", "complete": bool(snapshot.get("complete")),
                             "records": len(rows), "cursor": snapshot.get("cursor"), "observed_at": snapshot.get("observed_at") or at, "scope": "actual native connector repository listing; full content backfill separate"})
        except Exception as error:
            read_error("github:connector-list:" + ref, error)
    for ref, road in unique_github_roads.items():
        host = str(road.get("host") or "github.com")
        reader = road.get("reader")
        acc = account("github", ref, host=host)
        try:
            if callable(reader):
                identity = _unwrap(reader("user"))
                verified_account_refs["github"].add(ref)
                acc["status"] = "provider_observed"
                acc["metadata"].update(provider_login=_name(identity.get("login")), provider_account_id=identity.get("id"), identity_state="provider_observed")
                coverage.append({"source": "github:identity:" + ref, "status": "observed", "complete": True, "provider_login": _name(identity.get("login")), "observed_at": at})
        except Exception as error:
            read_error("github:identity:" + ref, error)
        for kind, endpoint in (("repos", "user/repos?affiliation=owner,collaborator,organization_member&visibility=all&per_page=100"), ("orgs", "user/orgs?per_page=100")):
            key = "github:" + ref + ":" + kind
            page = int(continuation.get(key, {}).get("page", 1))
            listed = int(continuation.get(key, {}).get("records", 0))
            complete = fresh_done(key)
            if continuation.get(key, {}).get("complete") and not complete:
                page, listed = 1, 0
            try:
                if not callable(reader):
                    raise DiscoveryError("github_reader_binding_pending")
                while not complete and spend_page():
                    response = _unwrap(reader(endpoint + "&page=" + str(page)))
                    rows = response if isinstance(response, list) else response.get("repositories", response.get("organizations", []))
                    for row in rows:
                        if kind == "repos" and _name(row.get("full_name")):
                            repo = str(row["full_name"])
                            repositories.add(repo)
                            repo_metadata[ref + ":" + repo] = {"account_ref": ref, "host": host, "repository": repo, "private": bool(row.get("private")), "archived": bool(row.get("archived")), "default_branch": _name(row.get("default_branch")), "id": row.get("id")}
                        elif kind == "orgs" and _name(row.get("login")):
                            org = str(row["login"])
                            org_metadata[ref + ":" + org] = {"account_ref": ref, "host": host, "organization": org}
                            source("github", ref, "all organization-owned repositories, available audit logs and retained organization events", "orgs/" + org,
                                   reader={"road": "existing_github_account", "endpoint": "orgs/" + org + "/repos?type=all&per_page=100", "audit_log_endpoint": "orgs/" + org + "/audit-log?per_page=100"},
                                   unread_regions=["organization repository pages and available audit log/event spans"])
                    listed += len(rows)
                    complete = len(rows) < 100
                    page += 1
                    continuation[key] = {"page": 1 if complete else page, "records": listed, "complete": complete, "completed_epoch": time.time() if complete else None}
                coverage.append({"source": key, "status": "observed" if complete else "backfilling", "complete": complete, "records": listed, "next_page": None if complete else page, "observed_at": at,
                                 "unread_regions": [] if complete else [kind + " after page " + str(page - 1)]})
            except Exception as error:
                read_error(key, error, continuation=continuation.get(key, {"page": page}))
                source("github", ref, "all visible " + kind, endpoint, status="pending_recovery", reader={"road": "existing_github_account", "host": host})
    for org in org_metadata.values():
        ref = org["account_ref"]
        name = org["organization"]
        source("github", ref, "all organization repositories, audit logs and retained organization events", "orgs/" + name,
               reader={"road": "existing_github_account", "host": org["host"], "endpoint": "orgs/" + name + "/repos?type=all&per_page=100", "audit_log_endpoint": "orgs/" + name + "/audit-log?per_page=100"},
               unread_regions=["organization repository pages and available audit log/event spans"])
        road = unique_github_roads.get(ref)
        if not road:
            continue
        key = "github:" + ref + ":org-repos:" + name
        page = int(continuation.get(key, {}).get("page", 1))
        listed = int(continuation.get(key, {}).get("records", 0))
        complete = fresh_done(key)
        if continuation.get(key, {}).get("complete") and not complete:
            page, listed = 1, 0
        try:
            while not complete and spend_page():
                response = _unwrap(road["reader"]("orgs/" + name + "/repos?type=all&per_page=100&page=" + str(page)))
                rows = response if isinstance(response, list) else response.get("repositories", [])
                for row in rows:
                    if _name(row.get("full_name")):
                        repo = str(row["full_name"])
                        repositories.add(repo)
                        repo_metadata[ref + ":" + repo] = {"account_ref": ref, "host": org["host"], "repository": repo, "private": bool(row.get("private")), "archived": bool(row.get("archived")), "default_branch": _name(row.get("default_branch")), "id": row.get("id")}
                listed += len(rows)
                complete = len(rows) < 100
                page += 1
                continuation[key] = {"page": 1 if complete else page, "records": listed, "complete": complete, "completed_epoch": time.time() if complete else None}
            coverage.append({"source": key, "status": "observed" if complete else "backfilling", "complete": complete, "records": listed, "next_page": None if complete else page, "observed_at": at})
        except Exception as error:
            read_error(key, error, continuation=continuation.get(key, {"page": page}))
    for row in repo_metadata.values():
        repo, ref = row["repository"], row["account_ref"]
        for scope, endpoint in GITHUB_SCOPES.items():
            source("github", ref, scope + ": all available retained records and referenced content", endpoint.replace("{repo}", repo),
                   reader={"road": "existing_github_account", "host": row["host"], "endpoint": endpoint.replace("{repo}", repo), "pagination": "provider cursors/page=100", "full_content": True},
                   repository=repo, unread_regions=["all retained " + scope + " records not yet ingested"])

    unresolved_account_scopes = 0
    for service, details in sorted(unresolved_bindings.items()):
        verified = verified_account_refs.get(service, set())
        pending_evidence = [evidence_id for evidence_id, reference in details["evidence"].items() if reference not in verified]
        for source_row in sources.values():
            if source_row.get("service") == service and source_row.get("account_ref") in verified:
                source_row["identity_state"] = "provider_observed"
                source_row["identity_verified_by"] = "matching_connected_account_reader"
                # Identity can be verified while this source/reference still has
                # no reader binding or content backfill.
                if source_row.get("status") == "pending_recovery":
                    source_row["status"] = "reader_binding_pending"
        if pending_evidence:
            unresolved_account_scopes += 1
            coverage.append({"source": "account_binding:" + service, "status": "pending_recovery", "complete": False,
                             "service": service, "unresolved_evidence_references": len(pending_evidence),
                             "evidence_roads": sorted(details["origins"]), "observed_at": at,
                             "unread_regions": ["account identity for existing service/credential evidence not matched to an authenticated connected account",
                                                "provider reader binding for each unresolved account reference"]})
        else:
            coverage.append({"source": "account_binding:" + service, "status": "observed", "complete": True,
                             "service": service, "unresolved_evidence_references": 0,
                             "evidence_roads": sorted(details["origins"]), "observed_at": at,
                             "scope": "identity binding for supplied evidence matched by an authenticated reader; content backfill remains separate"})
    for row in coverage:
        service = row.get("service")
        account_ref = row.get("account_ref")
        if service in verified_account_refs and account_ref in verified_account_refs[service]:
            row.update(status="observed", complete=True, identity_verified_by="matching_connected_account_reader",
                       scope="account selector matched an authenticated provider identity; content backfill remains separate")
    universe_recovery["unresolved_account_scopes"] = unresolved_account_scopes
    universe_recovery["verified_reader_accounts"] = sum(len(refs) for refs in verified_account_refs.values())

    state_out = {"continuation": continuation, "slack_channels": sorted(channels), "github_repositories": sorted(repositories), "repo_metadata": repo_metadata, "channel_metadata": channel_metadata, "org_metadata": org_metadata, "observed_at": at}
    return _safe_output({"sources": sorted(sources.values(), key=lambda row: row["source_id"]), "slack_channels": sorted(channels), "github_repositories": sorted(repositories),
                   "accounts": sorted(accounts.values(), key=lambda row: (row["service"], row["account_ref"])), "coverage": coverage, "state": state_out,
                   "observed_at": at, "complete": bool(sources) and all(row.get("complete") for row in sources.values()),
                   "discovery_complete": False, "universe_complete": False,
                   "discovery_scope": "known source evidence is enumerated per road; account and service universe closure is pending recovery",
                   "scope": "all discovered accounts/services, with full-content ingestion state separate from listing coverage"})


collect_discovery = discover_sources
discover_accounts_and_sources = discover_sources
